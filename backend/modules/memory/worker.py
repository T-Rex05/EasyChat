"""记忆提取 worker：认领 memory.extract/memory.signal/memory.confirm job。

- `memory.extract`：读取 run 的用户原文与最终回复。明确"记住…"先走确定性
  提取（缺陷①：不依赖辅助模型可用，也不依赖主回答成功）；自然表达才调用
  受控 TextGenerator。用户原文是唯一事实来源，助手回复只用于消解指代。
- `memory.confirm`：持久确认意图（缺陷④）。记忆写入成功后同身份入队，
  渠道/写入异常只让确认有界重试，不回滚已持久记忆；重复执行由稳定
  dedup 身份与下游幂等保证逻辑上恰好一次。
- 没有 generator 时自然表达 fail-closed 不猜测；状态计数区分
  无候选/模型不可用/模型未配置/空输出/非法输出/写入失败。
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
CONFIRM_JOB_KIND = "memory.confirm"
LEGACY_CAPTURE_JOB_KIND = "memory.capture"
# 瞬时基础设施类结果：交给队列有界重试（max_attempts 封顶），不记成功。
_RETRYABLE_EXTRACT_STATES = frozenset(
    {"model_unavailable", "empty_output", "write_failed"}
)

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
        confirm_writer=None,
    ) -> None:
        self.service = service
        self.queue = queue
        self.message_loader = message_loader
        self.generator = generator
        self.poll_interval = poll_interval
        # WP-D:写入后向会话注入确认消息的回调(bootstrap 绑定,避免 memory→assistant 反向依赖)
        self.confirm_writer = confirm_writer
        self._status_counts: dict[str, int] = {}
        self._task: asyncio.Task | None = None
        self._stopping = False
        if generator is None:
            logger.warning(
                "记忆提取未配置 TextGenerator，降级为句首正则；"
                "以后都/我喜欢/我讨厌/我习惯/过敏等表达不会自动入库"
            )

    def enqueue_capture_tx(self, conn, run) -> str | None:
        """在 run 终态事务内入队；只对 web/wechat run。

        completed：全部触发词（自然表达需要完整回答上下文）；
        failed/interrupted：仅显式"记住…"——显式记忆的可靠性不依赖主
        回答成功（缺陷①）。cancelled 尊重用户意图，不入队。
        """
        status = str(run.get("status") or "")
        if status not in ("completed", "failed", "interrupted"):
            return None
        if str(run.get("source") or "") not in ("web", "wechat"):
            return None
        if self.message_loader is None:
            return None
        messages = self.message_loader(int(run["owner_id"]), str(run["id"]))
        user_texts = [
            str(item.get("content") or "")
            for item in messages
            if item.get("role") == "user"
        ]
        if status == "completed":
            hit = any(should_extract(text) for text in user_texts)
        else:
            hit = any(should_capture(text) for text in user_texts)
        if not hit:
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
                kinds=(
                    "memory.signal", EXTRACT_JOB_KIND,
                    CONFIRM_JOB_KIND, LEGACY_CAPTURE_JOB_KIND,
                ),
            )
            if lease is None:
                break
            payload = lease.payload_json()
            try:
                if lease.kind == CONFIRM_JOB_KIND:
                    self._run_confirm(payload)
                elif lease.kind in (EXTRACT_JOB_KIND, LEGACY_CAPTURE_JOB_KIND):
                    status = await self._extract(payload)
                    if status:
                        self._status_counts[status] = self._status_counts.get(status, 0) + 1
                    if status in _RETRYABLE_EXTRACT_STATES:
                        # 缺陷①：模型故障/空输出/写入失败是瞬时结果，不能记成功；
                        # 有界重试期间记忆写入幂等(find_active_content 去重)。
                        self.queue.fail(
                            lease, f"记忆提取待重试({status})",
                            retryable=True, retry_delay_seconds=60,
                        )
                        count += 1
                        continue
                else:
                    signal_id = str(payload.get("signal_id") or "")
                    receipt = self.service.apply_signal(signal_id)
                    logger.info("记忆信号 %s -> %s", signal_id, receipt.state)
            except Exception as exc:  # noqa: BLE001  存储/依赖失败可重试
                logger.exception("记忆任务处理失败 kind=%s", lease.kind)
                self.queue.fail(lease, str(exc), retryable=True, retry_delay_seconds=60)
            else:
                # 无显式指令/模型非法输出/已遗忘是确定性结果，不反复重试
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

    async def _extract(self, payload: dict) -> str | None:
        owner_id = int(payload.get("owner_id") or 0)
        run_id = str(payload.get("run_id") or "")
        if owner_id <= 0 or not run_id:
            return None
        context = self._context(owner_id, run_id)
        if context is None:
            return None
        user_text, assistant_text = context
        principal = self.service.access.snapshot_principal(owner_id)

        if should_capture(user_text):
            # 缺陷①：明确"记住…"永远先走可信确定性提取——覆盖辅助模型
            # 空输出/异常/未配置，以及主回答失败/中断的 run。
            candidate = candidate_from_user_message(run_id=run_id, text=user_text)
            if candidate is None:
                return "no_candidate"
            if not self._write(principal, candidate, run_id):
                return "write_failed"
            self._confirm(owner_id, run_id, candidate.content)
            return "captured_deterministic"

        if self.generator is None:
            # 自然表达没有模型不可靠入库：fail-closed，状态可诊断。
            return "model_unconfigured"

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
        except Exception:  # noqa: BLE001  瞬时基础设施失败：有界重试恢复
            logger.warning("记忆提取模型调用失败 run=%s", run_id)
            return "model_unavailable"

        text = (raw or "").strip()
        if not text:
            logger.warning("记忆提取模型返回空文本 run=%s(未写入)", run_id)
            return "empty_output"
        if not text.startswith("{") or not text.endswith("}"):
            logger.warning("记忆提取输出不是严格 JSON run=%s", run_id)
            return "invalid_output"
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ExtractionError("模型输出不是 JSON 对象")
            candidate = candidate_from_model_payload(
                parsed, run_id=run_id, user_text=user_text
            )
        except (json.JSONDecodeError, ExtractionError):
            logger.warning("记忆提取候选不合法 run=%s", run_id)
            return "invalid_output"
        if candidate is None:
            return "no_candidate"
        if not self._write(principal, candidate, run_id):
            return "write_failed"
        self._confirm(owner_id, run_id, candidate.content)
        return "captured_model"

    def _write(self, principal, candidate, run_id: str) -> bool:
        """记忆写入：权限/fail-closed 校验在 service.remember_explicit 内；
        失败按写入失败状态上报供重试。成功重放由内容去重保证幂等。"""
        try:
            self.service.remember_explicit(principal, candidate)
        except Exception:  # noqa: BLE001  存储/校验失败区分状态，交重试
            logger.exception("记忆写入失败 run=%s", run_id)
            return False
        return True

    def _confirm(self, owner_id: int, run_id: str, content: str) -> None:
        """缺陷④：确认是持久意图（memory.confirm job），不在 extract 内
        直接触达渠道。入队异常上抛 → extract job 有界重试：记忆写入幂等、
        确认意图按 run 稳定 dedup 复用，不产生第二条。"""
        if self.confirm_writer is None or not content:
            return
        self.queue.enqueue(
            kind=CONFIRM_JOB_KIND,
            dedup_key=f"memory-confirm:{run_id}",
            payload={
                "owner_id": owner_id, "run_id": run_id,
                "text": f"已记住：{content[:120]}",
            },
            owner_id=owner_id,
        )

    def _run_confirm(self, payload: dict) -> None:
        """消费持久确认意图：会话消息 + 渠道回执由 bootstrap 注入的
        confirm_writer 完成（其内部为独立小事务；异常上抛交队列重试）。"""
        if self.confirm_writer is None:
            return
        owner_id = int(payload.get("owner_id") or 0)
        run_id = str(payload.get("run_id") or "")
        text = str(payload.get("text") or "")
        if owner_id <= 0 or not run_id or not text:
            return
        self.confirm_writer(owner_id, run_id, text)

    def extraction_status_counts(self) -> dict[str, int]:
        return dict(self._status_counts)

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("记忆 worker tick 失败")
            await asyncio.sleep(self.poll_interval)
