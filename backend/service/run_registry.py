"""
AgentForge Run Registry — SSE 流式会话管理

管理后台 SSE 生成器生命周期：
- 幂等去重（同 client_msg_id 不重复创建 run）
- 同 thread 串行（ThreadBusyError 拒绝并发）
- 断线续传（ring buffer + from_seq）
- 超时回收（TTL + max_runs）

这是一个精简实现，满足脚手架核心需求。
"""
import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any, AsyncIterator

logger = logging.getLogger(__name__)


class ThreadBusyError(Exception):
    """同一 thread 已有活跃 run，拒绝并发请求。"""
    pass


@dataclass
class Run:
    """一次 SSE 生成 run 的状态。"""
    thread_id: str
    client_msg_id: str
    status: str = "RUNNING"  # RUNNING / DONE / ERROR / CANCELLED
    created_at: float = field(default_factory=time.time)
    last_frame_at: float = field(default_factory=time.time)  # 最后一次帧追加时间，用于 sweep 判断
    completed_at: Optional[float] = None  # 完成时间戳，用于 sweep 延迟清理
    task: Optional[asyncio.Task] = None
    frames: list = field(default_factory=list)  # ring buffer
    seq: int = 0  # 当前序列号
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)  # 帧到达/终结通知


class RunRegistry:
    """进程内 SSE run 注册表。"""

    MAX_RUNS = 200
    RUN_TTL = 300  # 5 分钟

    def __init__(self):
        self._runs: Dict[str, Run] = OrderedDict()  # run_key → Run（有序，支持 LRU 淘汰）
        self._thread_active: Dict[str, str] = {}  # thread_id → run_key（活跃 run）

    def _make_key(self, thread_id: str, client_msg_id: str) -> str:
        return f"{thread_id}:{client_msg_id}"

    def get_or_create(
        self,
        thread_id: str,
        client_msg_id: str,
        producer_factory: Callable,
    ) -> tuple:
        """
        获取已有 run 或创建新 run。

        返回: (run, created) — created=True 表示新创建的
        """
        key = self._make_key(thread_id, client_msg_id)

        # 已有 → 直接返回（断线续传 / 幂等去重），并做 LRU 触摸
        if key in self._runs:
            run = self._runs[key]
            self._runs.move_to_end(key)
            return run, False

        # 同 thread 有其他活跃 run → 拒绝
        active_key = self._thread_active.get(thread_id)
        if active_key and active_key in self._runs:
            active = self._runs[active_key]
            if active.status == "RUNNING":
                raise ThreadBusyError(f"thread {thread_id} 已有进行中的请求")

        # 创建新 run
        run = Run(thread_id=thread_id, client_msg_id=client_msg_id)

        # 启动后台任务
        async def _producer():
            try:
                gen = producer_factory()
                async for frame in gen:
                    run.frames.append((run.seq, frame))
                    run.seq += 1
                    run.last_frame_at = time.time()  # 更新最后帧时间
                    # 限制 ring buffer 大小（deque 风格，不替换引用）
                    if len(run.frames) > 1000:
                        dropped = len(run.frames) - 500
                        del run.frames[:dropped]
                        if not getattr(run, "_truncated_warned", False):
                            logger.warning(
                                f"⚠️ ring buffer 截断: run={run.thread_id}:{run.client_msg_id[:8]} "
                                f"丢弃 {dropped} 帧旧数据（断线续传可能丢失部分历史）"
                            )
                            run._truncated_warned = True
                    async with run.cond:
                        run.cond.notify_all()
                run.status = "DONE"
                run.completed_at = time.time()
            except asyncio.CancelledError:
                run.status = "CANCELLED"
                run.completed_at = time.time()
            except Exception as e:
                logger.error(f"Run producer 异常: {e}")
                run.status = "ERROR"
                run.completed_at = time.time()
            finally:
                # 忙标记清理：值相等才删，避免越权清理新 run
                if self._thread_active.get(thread_id) == key:
                    self._thread_active.pop(thread_id, None)
                async with run.cond:
                    run.cond.notify_all()

        loop = asyncio.get_running_loop()
        run.task = loop.create_task(_producer())

        self._runs[key] = run
        self._thread_active[thread_id] = key

        # 清理过期 run
        self._evict()

        return run, True

    async def subscribe(self, run: Run, from_seq: int = 0) -> AsyncIterator[str]:
        """
        订阅一个 run 的帧流（重放 + 续传）。

        from_seq: 从哪个序列号开始（0 = 全部重放）

        事件驱动实现：生产者每追加一帧（或终结时）通过 run.cond.notify_all()
        唤醒订阅者，取代旧的 50ms busy-poll；谓词检查在 Condition 锁内完成，
        避免丢失唤醒。60s 超时仅为防挂死兜底。
        """
        last_seq = from_seq - 1
        while True:
            # 增量取帧（seq 连续，直接从游标之后扫描）
            for seq, frame in run.frames:
                if seq > last_seq:
                    # SSE id 行：浏览器收到后会记住，重连时发 Last-Event-ID
                    yield f"id: {seq}\n"
                    yield frame
                    last_seq = seq

            if run.status != "RUNNING":
                break

            async with run.cond:
                # 锁内复查谓词：扫描与加锁之间到达的帧不会丢
                if run.seq - 1 > last_seq or run.status != "RUNNING":
                    continue
                try:
                    await asyncio.wait_for(run.cond.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass  # 超时兜底：重新扫描，若确无新帧则继续等待

    def user_cancel(self, thread_id: str, client_msg_id: str) -> bool:
        """用户取消 run。返回 True 表示找到并取消了活跃 run。"""
        key = self._make_key(thread_id, client_msg_id)
        run = self._runs.get(key)
        if not run or run.status != "RUNNING":
            return False
        if run.task and not run.task.done():
            run.task.cancel()
        run.status = "CANCELLED"
        # 忙标记清理：值相等才删，避免越权清理新 run
        if self._thread_active.get(thread_id) == key:
            self._thread_active.pop(thread_id, None)
        return True

    def sweep(self):
        """清理过期/挂死的 run。"""
        now = time.time()
        to_remove = []
        for key, run in self._runs.items():
            # 超时（基于最后帧时间，而非创建时间）
            # 语义：超过 TTL 无任何输出才 cancel，不杀健康的长 run
            if now - run.last_frame_at > self.RUN_TTL:
                # 对 RUNNING 的 run 先取消任务
                if run.status == "RUNNING" and run.task and not run.task.done():
                    run.task.cancel()
                    run.status = "CANCELLED"
                to_remove.append(key)
                continue
            # 已完成超过 60 秒再清理（而非立即清理，保证断线续传可用）
            if run.status in ("DONE", "ERROR", "CANCELLED"):
                if run.completed_at and now - run.completed_at > 60:
                    to_remove.append(key)
                elif run.task and run.task.done() and not run.completed_at:
                    # 兼容没有 completed_at 的旧 run
                    to_remove.append(key)
        for key in to_remove:
            run = self._runs.pop(key, None)
            if run:
                # 忙标记清理：值相等才删，避免越权清理新 run
                if self._thread_active.get(run.thread_id) == key:
                    self._thread_active.pop(run.thread_id, None)

    def _evict(self):
        """超量时 LRU 淘汰。"""
        while len(self._runs) > self.MAX_RUNS:
            oldest_key = next(iter(self._runs))
            run = self._runs.get(oldest_key)
            if run:
                # 对 RUNNING 的 run 先取消任务（与 sweep 行为一致）
                if run.status == "RUNNING" and run.task and not run.task.done():
                    run.task.cancel()
                    run.status = "CANCELLED"
                self._runs.pop(oldest_key, None)
                # 忙标记清理：值相等才删，避免越权清理新 run
                if self._thread_active.get(run.thread_id) == oldest_key:
                    self._thread_active.pop(run.thread_id, None)
