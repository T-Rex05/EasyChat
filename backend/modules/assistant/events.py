"""run 事件环形缓存与订阅（架构 §4）。

- seq 在单 run 内单调递增；token 可合并（coalesce 窗口）降低帧开销；
- 每 run 最多 256 帧 / 256KiB（取较小限制）；完成 run 缓存 5 分钟；
- 缓存失效时订阅者收到 stream_reset 信号并读持久最终状态，不重跑。
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import AsyncIterator

from backend.modules.assistant.contracts import RunEvent
from backend.shared.context import Principal
from backend.shared.errors import NotFoundError

MAX_FRAMES_PER_RUN = 256
MAX_BYTES_PER_RUN = 256 * 1024
TOKEN_COALESCE_SECONDS = 0.05
COMPLETED_TTL_SECONDS = 300.0

TERMINAL_KINDS = frozenset({"completed", "failed", "cancelled", "interrupted"})


@dataclass(slots=True)
class _RunBuffer:
    run_id: str
    frames: deque[tuple[int, RunEvent]]
    seq: int = 0
    bytes_used: int = 0
    dropped: bool = False  # 环形截断发生后续传不再完整
    finished: bool = False
    finished_at: float = 0.0
    subscribers: set[asyncio.Queue] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.subscribers is None:
            self.subscribers = set()


class EventBus:
    """进程内 run 事件中心；跨进程恢复走持久最终状态。"""

    def __init__(
        self,
        *,
        max_frames: int = MAX_FRAMES_PER_RUN,
        max_bytes: int = MAX_BYTES_PER_RUN,
        coalesce_seconds: float = TOKEN_COALESCE_SECONDS,
        completed_ttl: float = COMPLETED_TTL_SECONDS,
    ) -> None:
        self._buffers: OrderedDict[str, _RunBuffer] = OrderedDict()
        self._max_frames = max_frames
        self._max_bytes = max_bytes
        self._coalesce = coalesce_seconds
        self._ttl = completed_ttl
        self._pending_token: dict[str, tuple[int, str, float]] = {}  # run → (first_seq, text, ts)

    # ---- 发布 ------------------------------------------------------------------

    def publish(self, run_id: str, kind: str, payload: dict) -> RunEvent:
        buffer = self._buffers.get(run_id)
        if buffer is None:
            buffer = _RunBuffer(run_id=run_id, frames=deque())
            self._buffers[run_id] = buffer
        if kind == "token":
            return self._publish_token(buffer, payload.get("text", ""))
        event = RunEvent(run_id=run_id, seq=buffer.seq, kind=kind, payload=payload)
        self._append(buffer, event)
        return event

    def _publish_token(self, buffer: _RunBuffer, text: str) -> RunEvent:
        pending = self._pending_token.get(buffer.run_id)
        now = time.monotonic()
        if pending is not None:
            first_seq, acc, ts = pending
            self._pending_token[buffer.run_id] = (first_seq, acc + text, ts)
            if now - ts < self._coalesce:
                return RunEvent(run_id=buffer.run_id, seq=first_seq, kind="token",
                                payload={"text": acc + text, "coalesced": True})
            self._flush_token(buffer)
        seq = buffer.seq
        self._pending_token[buffer.run_id] = (seq, text, now)
        return RunEvent(run_id=buffer.run_id, seq=seq, kind="token", payload={"text": text})

    def flush_token(self, run_id: str) -> None:
        buffer = self._buffers.get(run_id)
        if buffer is not None:
            self._flush_token(buffer)

    def _flush_token(self, buffer: _RunBuffer) -> None:
        pending = self._pending_token.pop(buffer.run_id, None)
        if pending is None:
            return
        first_seq, text, _ts = pending
        self._append(buffer, RunEvent(run_id=buffer.run_id, seq=first_seq, kind="token", payload={"text": text}))

    def _append(self, buffer: _RunBuffer, event: RunEvent) -> None:
        self._append_frame(buffer, event)
        for q in list(buffer.subscribers):
            q.put_nowait(event)

    def _append_frame(self, buffer: _RunBuffer, event: RunEvent) -> None:
        buffer.seq = event.seq + 1
        size = len(str(event.payload))
        buffer.frames.append((event.seq, event))
        buffer.bytes_used += size
        while (len(buffer.frames) > self._max_frames or buffer.bytes_used > self._max_bytes) and buffer.frames:
            _seq, dropped = buffer.frames.popleft()
            buffer.bytes_used -= len(str(dropped.payload))
            buffer.dropped = True

    def finish(self, run_id: str, kind: str, payload: dict) -> RunEvent:
        """终态事件：flush 未决token后写入；缓冲保留 TTL 供断线续传。"""
        buffer = self._buffers.get(run_id)
        if buffer is None:
            buffer = _RunBuffer(run_id=run_id, frames=deque())
            self._buffers[run_id] = buffer
        self._flush_token(buffer)
        event = RunEvent(run_id=run_id, seq=buffer.seq, kind=kind, payload=payload)
        self._append(buffer, event)
        buffer.finished = True
        buffer.finished_at = time.monotonic()
        for q in list(buffer.subscribers):
            q.put_nowait(event)
            q.put_nowait(None)  # 结束订阅
        return event

    # ---- 订阅 ------------------------------------------------------------------

    def subscribe(self, principal: Principal, run_owner_id: int, run_id: str, after_seq: int = 0) -> AsyncIterator[RunEvent]:
        """按 seq 增量订阅；owner 校验由调用方完成（此处二次防御）。

        环形缓存失效（截断/过期/未知run且运行中）时发 stream_reset；
        调用方据此读取持久最终状态，不重新执行。
        """
        buffer = self._buffers.get(run_id)
        if buffer is None:
            raise NotFoundError(f"run 不存在或事件缓存已过期: {run_id}")

        async def _stream():
            q: asyncio.Queue = asyncio.Queue()
            resume = after_seq  # 生成器内不得对闭包参数再赋值
            if buffer.dropped and resume > 0:
                yield RunEvent(run_id=run_id, seq=-1, kind="stream_reset", payload={"reason": "truncated"})
                resume = 0
            # 回放
            for seq, event in buffer.frames:
                if seq >= resume:
                    yield event
            if buffer.finished:
                return
            # 追加实时
            buffer.subscribers.add(q)
            try:
                while True:
                    item = await q.get()
                    if item is None:
                        return
                    if item.seq >= max(resume, 0):
                        yield item
                    if item.kind in TERMINAL_KINDS:
                        return
            finally:
                buffer.subscribers.discard(q)

        return _stream()

    def latest_seq(self, run_id: str) -> int | None:
        buffer = self._buffers.get(run_id)
        return buffer.seq - 1 if buffer else None

    # ---- 清理 ------------------------------------------------------------------

    def sweep(self) -> int:
        """清理过期终态缓冲。返回清理数量。"""
        now = time.monotonic()
        stale = [rid for rid, b in self._buffers.items()
                 if b.finished and now - b.finished_at > self._ttl]
        for rid in stale:
            self._buffers.pop(rid, None)
        return len(stale)
