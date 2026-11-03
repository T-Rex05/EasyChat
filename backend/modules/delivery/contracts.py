"""delivery 模块公开契约（架构 §5.2/§5.3、Task 8）。

投递只处理“已确定的最终内容”；生成由 assistant/报告模块完成。发送适配器
只替换外部 Seam（微信/邮件），重试和状态由本模块账本负责。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

TARGET_WECHAT = "wechat"
TARGET_EMAIL = "email"

DELIVERY_PENDING = "pending"
DELIVERY_SENDING = "sending"
DELIVERY_SENT = "sent"
DELIVERY_RETRY_WAIT = "retry_wait"
DELIVERY_UNCERTAIN = "uncertain"
DELIVERY_FAILED = "failed"

PART_PENDING = "pending"
PART_SENT = "sent"
PART_FAILED = "failed"

DEFAULT_CHUNK_CHARS = 1800
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_DELAYS = (30.0, 120.0, 600.0)


@dataclass(frozen=True, slots=True)
class DeliveryTarget:
    """投递目标；ref 是平台外部用户标识（如微信 openid）。"""

    kind: str
    ref: str
    channel_account_id: str = ""
    context_token: str = ""


@dataclass(frozen=True, slots=True)
class SendResult:
    """一次外部发送的结果；区分成功、可重试、结果不确定与永久失败。"""

    ok: bool = False
    retryable: bool = False
    uncertain: bool = False
    external_id: str = ""
    error: str = ""

    @classmethod
    def sent(cls, external_id: str = "") -> "SendResult":
        return cls(ok=True, external_id=external_id)

    @classmethod
    def retry(cls, error: str) -> "SendResult":
        return cls(retryable=True, error=error)

    @classmethod
    def unsure(cls, error: str) -> "SendResult":
        return cls(uncertain=True, error=error)

    @classmethod
    def failed(cls, error: str) -> "SendResult":
        return cls(error=error)


class DeliverySender(Protocol):
    """外部发送 Adapter；can_deliver 在发送前做绑定/能力校验（解绑立即停止）。"""

    async def can_deliver(self, target: DeliveryTarget) -> bool: ...

    async def send_text(
        self, target: DeliveryTarget, text: str, *, context_token: str = ""
    ) -> SendResult: ...


@dataclass(frozen=True, slots=True)
class DeliveryLease:
    delivery_id: str
    owner_id: int
    run_id: str
    source: str
    target: DeliveryTarget
    content_text: str
    artifact_id: str
    attempts: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class DeliveryView:
    delivery_id: str
    owner_id: int
    run_id: str
    source: str
    target: DeliveryTarget
    status: str
    attempts: int
    error: str
    created_at: str
    sent_at: str | None
