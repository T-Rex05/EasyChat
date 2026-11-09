"""记忆提取 worker：认领 memory.extract/memory.signal job，幂等应用后完成/重试。

`memory.extract` 读取 run 的用户原文与最终回复，调用受控 TextGenerator 生成
候选 JSON；用户原文是唯一事实来源，助手回复只用于消解指代。没有 generator
时退化为旧的正则提取，只支持句首「记住/记一下/别忘了」。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from backend.modules.memory.api import MemoryService
from backend.modules.memory.capture import (
    candidate_from_model_payload,
    candidate_from_user_message,
    should_capture,
    should_extract,
)
from backend.modules.memory.extractor import ExtractionError
from backend.platform.jobs import JobQueue

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 0.2
MAX_PER_TICK = 50
EXTRACT_JOB_KIND = "memory.extract"
LEGACY_CAPTURE_JOB_KIND = "memory.capture"

_EXTRACT_SYSTEM = """你是用户私人助理的记忆提取器。只提取用户明确表达、值得长期记住的事实或偏好。
用户消息是唯一事实来源；助手回复只能帮助理解指代，不能作为记忆内容。
只输出一个 JSON 对象，不要 Markdown、代码块或解释：
{"kind":"fact|preference|event|experience","content":"...","evidence":"..."}
content 不超过 200 字；evidence 必须逐字摘自用户消息，不超过 200 字。
如果用户没有明确要求记住、也没有表达稳定偏好/事实，输出 {"skip":true}。
不要猜测，不要把转述、假设或助手的话写进记忆。"""


class MemoryWorker:
    def __init__(
        self,
        service: MemoryService,
        queue: JobQueue,
        *,
        message_loader=None,
        generator: Any = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self.service = service
        self.queue = queue
        self.message_loader = message_loader
        self.generator = generator
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stopping = False
        if generator is None:
            logger.warning(
                "记忆提取未配置 TextGenerator，降级为句首正则；"
                "以后都/我喜欢/我讨厌/我习惯/过敏等表达不会自动入库"
            )

    def enqueue_capture_tx(self, conn, run) -> str | None:
        """在 run 终态事务内入队；只对完成且有显式表达的 web/wechat run。"""
        if str(run.get("status") or "") != "completed":
            return None
        if str(run.get("source") or "") not in ("web", "wechat"):
            return None
        if self.message_loader is None:
            return None
        messages = self.message_loader(int(run["owner_id"]), str(run["id"]))
        if not any(
            should_extract(str(item.get("content") or ""))
            for item in messages
            if item.get("role") == "user"
        ):
            return None
        return self.queue.enqueue_tx(
            conn,
            kind=EXTRACT_JOB_KIND,
            dedup_key=f"memory:{run['id']}",
            payload={"owner_id": int(run["owner_id"]), "run_id": str(run["id"])},
            owner_id=int(run["owner_id"]),
        )

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self.queue.recover_expired_leases()
        self._stopping = False
        self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._task = None

    async def tick(self) -> int:
        count = 0
        while count < MAX_PER_TICK:
            lease = self.queue.claim(
                "memory-worker",
                kinds=("memory.signal", EXTRACT_JOB_KIND, LEGACY_CAPTURE_JOB_KIND),
            )
            if lease is None:
                break
            payload = lease.payload_json()
            try:
                if lease.kind in (EXTRACT_JOB_KIND, LEGACY_CAPTURE_JOB_KIND):
                    await self._extract(payload)
                else:
                    signal_id = str(payload.get("signal_id") or "")
                    receipt = self.service.apply_signal(signal_id)
                    logger.info("记忆信号 %s -> %s", signal_id, receipt.state)
            except Exception as exc:  # noqa: BLE001  存储/依赖失败可重试
                logger.exception("记忆任务处理失败 kind=%s", lease.kind)
                self.queue.fail(lease, str(exc), retryable=True, retry_delay_seconds=60)
            else:
                # 无显式指令/模型非法输出/已遗忘也是确定性结果，不反复重试
                self.queue.complete(lease)
            count += 1
        return count

    def _context(self, owner_id: int, run_id: str) -> tuple[str, str] | None:
        if self.message_loader is None:
            return None
        messages = self.message_loader(owner_id, run_id)
        user_texts = [
            str(item.get("content") or "").strip()
            for item in messages
            if item.get("role") == "user" and str(item.get("content") or "").strip()
        ]
        if not user_texts:
            return None
        selected = next(
            (text for text in reversed(user_texts) if should_extract(text)), ""
        )
        if not selected:
            return None
        assistant_texts = [
            str(item.get("content") or "").strip()
            for item in messages
            if item.get("role") == "assistant"
            and str(item.get("content") or "").strip()
        ]
        return selected, (assistant_texts[-1] if assistant_texts else "")

    async def _extract(self, payload: dict) -> None:
        owner_id = int(payload.get("owner_id") or 0)
        run_id = str(payload.get("run_id") or "")
        if owner_id <= 0 or not run_id:
            return
        context = self._context(owner_id, run_id)
        if context is None:
            return
        user_text, assistant_text = context
        principal = self.service.access.snapshot_principal(owner_id)

        if self.generator is None:
            # 显式降级：只支持旧的句首触发词；新触发词不会在这里被猜测。
            if should_capture(user_text):
                candidate = candidate_from_user_message(run_id=run_id, text=user_text)
                if candidate is not None:
                    self.service.remember_explicit(principal, candidate)
            return

        try:
            raw = await self.generator.generate(
                _EXTRACT_SYSTEM,
                json.dumps(
                    {
                        "user_text": user_text[:2000],
                        "assistant_reply_for_coreference": assistant_text[-1000:],
                    },
                    ensure_ascii=False,
                ),
                owner_id=owner_id,
                max_chars=600,
            )
        except Exception:  # noqa: BLE001  模型失败按确定性失败处理，不重试
            logger.warning("记忆提取模型调用失败 run=%s", run_id)
            return

        text = (raw or "").strip()
        if not text.startswith("{") or not text.endswith("}"):
            logger.warning("记忆提取输出不是严格 JSON run=%s", run_id)
            return
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ExtractionError("模型输出不是 JSON 对象")
            candidate = candidate_from_model_payload(
                parsed, run_id=run_id, user_text=user_text
            )
        except (json.JSONDecodeError, ExtractionError):
            logger.warning("记忆提取候选不合法 run=%s", run_id)
            return
        if candidate is not None:
            self.service.remember_explicit(principal, candidate)

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("记忆 worker tick 失败")
            await asyncio.sleep(self.poll_interval)
