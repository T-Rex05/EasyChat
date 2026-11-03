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
    ) -> None:
        self.db = db
        self.repo = DeliveryRepository(db)
        self.sender = sender
        self.clock = clock
        self.chunk_chars = chunk_chars
        self.retry_delays = retry_delays or DEFAULT_RETRY_DELAYS
        self.max_attempts = max_attempts

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
        delay_seconds: float = 0.0,
    ) -> str:
        if not target.kind or not target.ref:
            raise InvalidInputError("投递目标缺少 kind/ref")
        if not text.strip() and not artifact_id:
            raise InvalidInputError("投递内容为空")
        return self.repo.enqueue(
            owner_id=owner_id, target=target, content_text=text, dedup_key=dedup_key,
            source=source, run_id=run_id, artifact_id=artifact_id,
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
    ) -> str:
        """供 scheduling 在同一事务内写“实例 + 投递”的窄协调入口。"""
        return self.repo.enqueue_in_transaction(
            conn, owner_id=owner_id, target=target, content_text=text,
            dedup_key=dedup_key, source=source, now=self.clock(),
        )

    # ---- 发送 ------------------------------------------------------------------

    async def process_next(self) -> bool:
        """认领并尝试一条到期投递；返回是否处理了记录（测试直接调用）。"""
        lease = self.repo.claim_due(
            WORKER_ID, now=self.clock(), max_attempts=self.max_attempts,
        )
        if lease is None:
            return False
        await self._deliver(lease)
        return True

    async def _deliver(self, lease: DeliveryLease) -> None:
        if not lease.content_text.strip() and not lease.artifact_id:
            self.repo.finish(lease.delivery_id, status=DELIVERY_FAILED, error="投递内容为空")
            return

        if not await self.sender.can_deliver(lease.target):
            # 解绑/禁用后不再继续发；保留账本可审计，不重试
            self.repo.finish(
                lease.delivery_id, status=DELIVERY_FAILED, error="投递目标已解绑或渠道已禁用",
            )
            return

        chunks = split_text(lease.content_text, self.chunk_chars) or [""]
        parts = self.repo.ensure_parts(lease.delivery_id, chunks)
        for part in parts:
            if part["status"] == PART_SENT:
                continue
            seq = int(part["seq"])
            try:
                result = await self.sender.send_text(
                    lease.target, str(part["content"]),
                    context_token=lease.target.context_token,
                )
            except Exception as exc:  # noqa: BLE001  外部调用异常=结果未知
                result = SendResult.unsure(f"发送异常: {exc}")
            if result.ok:
                self.repo.mark_part_sent(lease.delivery_id, seq, result.external_id)
                continue

            self.repo.mark_part_failed(lease.delivery_id, seq, result.error or "发送失败")
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
            return

        self.repo.finish(lease.delivery_id, status=DELIVERY_SENT, sent_at=True)

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
