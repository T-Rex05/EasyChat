"""delivery 模块公开接口：把已确定的最终内容可靠地投递到目标渠道。

发送适配器由 bootstrap 注入（微信文本 / 邮件）；本模块只负责账本、分块、
重试与 uncertain 语义，不生成内容、不重跑 Agent。
"""
from __future__ import annotations

import logging
import time
from typing import Any

from backend.modules.delivery.contracts import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_DELAYS,
    DELIVERY_FAILED,
    DELIVERY_SENT,
    DELIVERY_UNCERTAIN,
    PART_SENT,
    DeliveryLease,
    DeliverySender,
    DeliveryTarget,
    DeliveryView,
    SendResult,
)
from backend.modules.delivery.repository import DeliveryRepository
from backend.platform.sqlite import Database
from backend.shared.errors import InvalidInputError, NotFoundError
from backend.shared.text import split_text

logger = logging.getLogger(__name__)

WORKER_ID = "delivery-worker"
WECHAT_CHUNK_CHARS = 500
EMAIL_CHUNK_CHARS = 1800


class CompositeDeliverySender:
    """按目标类型路由到微信/邮件发送器；只有能投递的实现才被调用。"""

    def __init__(self, senders: list[Any]) -> None:
        self.senders = senders

    async def can_deliver(self, target: DeliveryTarget) -> bool:
        return await self.resolve(target) is not None

    async def resolve(self, target: DeliveryTarget):
        """一次解析出实际 sender；调用方可复用结果，避免 can/send 双探测。"""
        last_error: Exception | None = None
        for sender in self.senders:
            try:
                if await sender.can_deliver(target):
                    return sender
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error is not None:
            raise last_error
        return None

    async def _sender_for(self, target: DeliveryTarget):
        return await self.resolve(target)

    async def send_text(
        self, target: DeliveryTarget, text: str, *, context_token: str = ""
    ) -> SendResult:
        sender = await self._sender_for(target)
        if sender is None:
            return SendResult.failed("没有可用的投递渠道")
        return await sender.send_text(target, text, context_token=context_token)

    async def send_artifact(
        self, target: DeliveryTarget, artifact_path: str, *, subject: str, body: str = ""
    ) -> SendResult:
        sender = await self._sender_for(target)
        if sender is None:
            return SendResult.failed("没有可用的投递渠道")
        artifact_sender = getattr(sender, "send_artifact", None)
        if artifact_sender is None:
            return SendResult.failed("当前渠道不支持附件投递")
        return await artifact_sender(
            target, artifact_path, subject=subject, body=body
        )


class DeliveryService:
    def __init__(
        self,
        db: Database,
        *,
        sender: DeliverySender,
        clock=time.time,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
        retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        email_recipient_check: Any = None,
        on_sent: Any = None,
    ) -> None:
        self.db = db
        self.repo = DeliveryRepository(db)
        self.sender = sender
        self.clock = clock
        self.chunk_chars = chunk_chars
        self.retry_delays = retry_delays or DEFAULT_RETRY_DELAYS
        self.max_attempts = max_attempts
        # 邮箱目标必须是 owner 自己登记的收件人，避免平台 SMTP 变成开放中继。
        self.email_recipient_check = email_recipient_check
        # 投递终态成功回调；bootstrap 用它把 care 从“已入队”推进到“已发送”。
        self.on_sent = on_sent

    # ---- 入队 ------------------------------------------------------------------

    def enqueue_text(
        self,
        *,
        owner_id: int,
        target: DeliveryTarget,
        text: str,
        dedup_key: str,
        source: str = "wechat",
        run_id: str = "",
        artifact_id: str = "",
        subject: str = "",
        delay_seconds: float = 0.0,
    ) -> str:
        if not target.kind or not target.ref:
            raise InvalidInputError("投递目标缺少 kind/ref")
        if not text.strip() and not artifact_id:
            raise InvalidInputError("投递内容为空")
        return self.repo.enqueue(
            owner_id=owner_id, target=target, content_text=text, dedup_key=dedup_key,
            source=source, run_id=run_id, artifact_id=artifact_id, subject=subject,
            delay_seconds=delay_seconds, now=self.clock(),
        )

    def enqueue_run_in_transaction(
        self, conn: Any, run: dict[str, Any], target: DeliveryTarget, content: str
    ) -> str:
        """助手完成事务内调用：run 终态、投影和投递请求同事务提交。"""
        if not content.strip():
            return ""
        return self.repo.enqueue_in_transaction(
            conn,
            owner_id=int(run["owner_id"]),
            target=target,
            content_text=content,
            dedup_key=f"run:{run['id']}:{target.kind}:{target.ref}",
            source=str(run.get("source") or "wechat"),
            run_id=str(run["id"]),
            now=self.clock(),
        )

    def enqueue_in_transaction(
        self,
        conn: Any,
        *,
        owner_id: int,
        target: DeliveryTarget,
        text: str,
        dedup_key: str,
        source: str = "schedule",
        subject: str = "",
    ) -> str:
        """供 scheduling 在同一事务内写“实例 + 投递”的窄协调入口。"""
        return self.repo.enqueue_in_transaction(
            conn, owner_id=owner_id, target=target, content_text=text,
            dedup_key=dedup_key, source=source, subject=subject, now=self.clock(),
        )

    # ---- 取消 ------------------------------------------------------------------

    def cancel(self, delivery_id: str, *, reason: str = "用户取消") -> bool:
        """作废单条尚未发送的投递；已进入 sending 的记录不会被假装撤回。"""
        return self.repo.cancel(delivery_id, reason=reason)

    def cancel_unsent(
        self, owner_id: int, *, source: str = "", reason: str = "用户取消"
    ) -> int:
        """按 owner/source 批量作废 pending/retry_wait，供 bootstrap 注入回调。"""
        return self.repo.cancel_unsent_by_owner(
            owner_id, source=source, reason=reason
        )

    def count_sent_reminders(
        self, owner_id: int, start_iso: str, end_iso: str
    ) -> int:
        """提醒送达数：由 delivery 账本回答，调用方无需知道表结构。"""
        return self.repo.count_sent_reminders(owner_id, start_iso, end_iso)

    # ---- 发送 ------------------------------------------------------------------

    async def process_next(self) -> bool:
        """认领并尝试一条到期投递；返回是否处理了记录（测试直接调用）。"""
        lease = self.repo.claim_due(
            WORKER_ID, now=self.clock(), max_attempts=self.max_attempts,
        )
        if lease is None:
            return False
        try:
            await self._deliver(lease)
        except Exception as exc:  # noqa: BLE001  任何未预期异常都不能让账本卡在 sending
            logger.exception("投递处理异常 delivery=%s", lease.delivery_id)
            try:
                self.repo.finish(
                    lease.delivery_id, status=DELIVERY_UNCERTAIN,
                    error=f"投递处理异常: {exc}",
                )
            except Exception:  # noqa: BLE001  DB 已不可用时只能记录日志
                logger.exception("投递异常状态回写失败 delivery=%s", lease.delivery_id)
        return True

    async def _deliver(self, lease: DeliveryLease) -> None:
        if not lease.content_text.strip() and not lease.artifact_id:
            self.repo.finish(lease.delivery_id, status=DELIVERY_FAILED, error="投递内容为空")
            return

        if lease.target.kind == "email" and self.email_recipient_check is not None:
            try:
                allowed = bool(self.email_recipient_check(lease.owner_id, lease.target.ref))
            except Exception as exc:  # noqa: BLE001  校验失败按未知处理，不能降级成可发
                raise RuntimeError(f"邮箱收件人校验失败: {exc}") from exc
            if not allowed:
                self.repo.finish(
                    lease.delivery_id, status=DELIVERY_FAILED,
                    error="邮箱不在本人收件人列表，拒绝投递",
                )
                return

        sender = await self._resolve_sender(lease.target)
        if sender is None:
            # 解绑/禁用后不再继续发；保留账本可审计，不重试
            self.repo.finish(
                lease.delivery_id, status=DELIVERY_FAILED,
                error="投递目标不可用（未绑定或渠道未配置）",
            )
            return

        if lease.artifact_id:
            await self._deliver_artifact(lease, sender)
            return

        text = _render_for_target(lease.target, lease.content_text)
        if not text.strip():
            self.repo.finish(lease.delivery_id, status=DELIVERY_FAILED, error="投递内容为空")
            return
        chunks = split_text(text, self._chunk_chars_for(lease.target)) or [""]
        parts = self.repo.ensure_parts(lease.delivery_id, chunks)
        for part in parts:
            if part["status"] == PART_SENT:
                continue
            seq = int(part["seq"])
            try:
                result = await sender.send_text(
                    lease.target, str(part["content"]),
                    context_token=lease.target.context_token,
                )
            except Exception as exc:  # noqa: BLE001  外部调用异常=结果未知
                result = SendResult.unsure(f"发送异常: {exc}")
            if result.ok:
                self.repo.mark_part_sent(lease.delivery_id, seq, result.external_id)
                continue

            self.repo.mark_part_failed(lease.delivery_id, seq, result.error or "发送失败")
            self._finish_result(lease, result)
            return

        self._mark_sent(lease)

    async def _resolve_sender(self, target: DeliveryTarget):
        resolve = getattr(self.sender, "resolve", None)
        if resolve is not None:
            return await resolve(target)
        if not await self.sender.can_deliver(target):
            return None
        return self.sender

    async def _deliver_artifact(self, lease: DeliveryLease, sender) -> None:
        try:
            artifact = self.repo.get_artifact(lease.artifact_id)
        except NotFoundError:
            self.repo.finish(lease.delivery_id, status=DELIVERY_FAILED, error="投递产物不存在")
            return
        sender_method = getattr(sender, "send_artifact", None)
        if sender_method is None:
            self.repo.finish(
                lease.delivery_id, status=DELIVERY_FAILED,
                error="当前发送器不支持附件投递",
            )
            return
        try:
            result = await sender_method(
                lease.target, str(artifact["file_path"]),
                subject=lease.subject or "EasyChat 报告", body=lease.content_text,
            )
        except Exception as exc:  # noqa: BLE001  外部调用异常=结果未知
            result = SendResult.unsure(f"附件发送异常: {exc}")
        self._finish_result(lease, result)

    def _mark_sent(self, lease: DeliveryLease) -> None:
        if not self.repo.finish(
            lease.delivery_id, status=DELIVERY_SENT, sent_at=True
        ):
            return
        if self.on_sent is None:
            return
        try:
            self.on_sent({
                "delivery_id": lease.delivery_id,
                "owner_id": lease.owner_id,
                "run_id": lease.run_id,
                "source": lease.source,
                "dedup_key": lease.dedup_key,
                "created_at": lease.created_at,
            })
        except Exception:  # noqa: BLE001  投递已成功，回调失败不能把账本改回失败
            logger.exception("投递成功回调失败 delivery=%s", lease.delivery_id)

    def _finish_result(self, lease: DeliveryLease, result: SendResult) -> None:
        if result.ok:
            self._mark_sent(lease)
            return
        if result.uncertain:
            self.repo.finish(
                lease.delivery_id, status=DELIVERY_UNCERTAIN,
                error=result.error or "发送结果不确定",
            )
            return
        if result.retryable and lease.attempts < lease.max_attempts:
            delay = self.retry_delays[min(lease.attempts - 1, len(self.retry_delays) - 1)]
            self.repo.set_retry(
                lease.delivery_id, next_attempt_at=self.clock() + delay,
                error=result.error or "发送失败，稍后重试",
            )
            return
        self.repo.finish(
            lease.delivery_id, status=DELIVERY_FAILED,
            error=result.error or "发送失败且不可重试",
        )

    def _chunk_chars_for(self, target: DeliveryTarget) -> int:
        """微信固定 500；邮件默认 1800 且尊重更小的显式配置。"""
        if _is_wechat_target(target):
            return WECHAT_CHUNK_CHARS
        if target.kind == "email":
            if self.chunk_chars == DEFAULT_CHUNK_CHARS:
                return EMAIL_CHUNK_CHARS
            return min(self.chunk_chars, EMAIL_CHUNK_CHARS)
        return self.chunk_chars

    # ---- 查询 ------------------------------------------------------------------

    def status(self, owner_id: int, delivery_id: str) -> DeliveryView:
        row = self.repo.get(delivery_id)
        if int(row["owner_id"]) != owner_id:
            raise NotFoundError(f"投递不存在: {delivery_id}")
        return _view(row)

    def list_for_owner(self, owner_id: int, limit: int = 50) -> list[DeliveryView]:
        return [_view(r) for r in self.repo.list_for_owner(owner_id, limit=limit)]

    def recover_inflight(self) -> int:
        return self.repo.recover_inflight()


def _is_wechat_target(target: DeliveryTarget) -> bool:
    return target.kind.lower() in ("wechat", "weixin", "ilink")


def _render_for_target(target: DeliveryTarget, text: str) -> str:
    if _is_wechat_target(target):
        from backend.shared.wechat_text import to_wechat_text

        return to_wechat_text(text)
    return text


def _view(row: dict[str, Any]) -> DeliveryView:
    return DeliveryView(
        delivery_id=str(row["id"]),
        owner_id=int(row["owner_id"]),
        run_id=str(row.get("run_id") or ""),
        source=str(row.get("source") or ""),
        target=DeliveryTarget(
            kind=str(row["target_kind"]),
            ref=str(row["target_ref"]),
            channel_account_id=str(row.get("channel_account_id") or ""),
            context_token=str(row.get("context_token") or ""),
        ),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        error=str(row.get("error") or ""),
        created_at=str(row["created_at"]),
        sent_at=row.get("sent_at"),
    )
