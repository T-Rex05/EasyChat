"""微信文本发送 Adapter：把 delivery 的目标映射到 Task 7 的 iLink 通道。

解绑/禁用检查在每次发送前通过 channels 公开方法执行；网络异常按“结果未知”
返回 uncertain，避免假称必达或盲目重发。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.modules.channels.contracts import ChannelTransportError
from backend.modules.delivery.contracts import DeliveryTarget, SendResult
from backend.shared.errors import InvalidInputError

logger = logging.getLogger(__name__)

# 微信 iLink 明确可重试的业务码；其他非零 ret 视为永久拒绝。
RETRY_RET_CODES = frozenset({45009})


@dataclass(frozen=True, slots=True)
class WeChatErrorClass:
    kind: str  # retry / failed / uncertain
    reason: str


def classify_wechat_error(exc: BaseException) -> WeChatErrorClass:
    """把外部异常分成可重试、永久失败、结果未知三类。

    只有明确的业务拒绝才进入永久失败；网络中断/超时/5xx 一律 unknown，
    不得假装“未发出”后盲目重发。
    """
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return WeChatErrorClass("uncertain", "网络超时/中断，无法确认是否送达")
    if isinstance(exc, InvalidInputError):
        return WeChatErrorClass("failed", str(exc))
    if isinstance(exc, ChannelTransportError):
        status = exc.status
        if status in (400, 401, 403, 404):
            return WeChatErrorClass("failed", str(exc)[:300])
        if status in (408, 429):
            return WeChatErrorClass("retry", str(exc)[:300])
        if status is not None and status >= 500:
            return WeChatErrorClass("uncertain", str(exc)[:300])
        if exc.retryable is True:
            return WeChatErrorClass("retry", str(exc)[:300])
        if exc.retryable is False:
            return WeChatErrorClass("failed", str(exc)[:300])
        if exc.ret in RETRY_RET_CODES:
            return WeChatErrorClass("retry", str(exc)[:300])
        if exc.ret is not None:
            return WeChatErrorClass("failed", str(exc)[:300])
        return WeChatErrorClass("uncertain", str(exc)[:300])
    return WeChatErrorClass("uncertain", f"未分类发送异常: {exc}"[:300])


class DisabledDeliverySender:
    """无渠道时的显式 sender：不接受投递，避免静默成功。"""

    async def can_deliver(self, target: DeliveryTarget) -> bool:
        return False

    async def send_text(
        self, target: DeliveryTarget, text: str, *, context_token: str = ""
    ) -> SendResult:
        return SendResult.failed("未配置任何渠道发送器")

    async def send_artifact(
        self, target: DeliveryTarget, artifact_path: str, *, subject: str, body: str = ""
    ) -> SendResult:
        return SendResult.failed("未配置任何渠道发送器")


class WeChatTextSender:
    def __init__(self, channels: Any) -> None:
        # 允许注入零参 provider：bootstrap 需要先装配 delivery/scheduling，
        # 再构造 ChannelService，发送时才解析实际渠道。
        if callable(channels) and not hasattr(channels, "is_delivery_binding_active"):
            self._provider = channels
        else:
            self._provider = lambda: channels

    @property
    def channels(self) -> Any:
        return self._provider()

    async def can_deliver(self, target: DeliveryTarget) -> bool:
        if target.kind != "wechat" or not target.ref:
            return False
        return bool(self.channels.is_delivery_binding_active(
            target.channel_account_id, target.ref
        ))

    async def send_text(
        self, target: DeliveryTarget, text: str, *, context_token: str = ""
    ) -> SendResult:
        try:
            await self.channels.send_wechat_text(
                account_pk=target.channel_account_id,
                external_user_id=target.ref,
                text=text,
                context_token=context_token or target.context_token,
            )
            return SendResult.sent()
        except Exception as exc:  # noqa: BLE001  外部发送失败需按证据分类
            classified = classify_wechat_error(exc)
            logger.warning("微信投递失败 kind=%s: %s", classified.kind, exc)
            if classified.kind == "retry":
                return SendResult.retry(f"微信发送失败: {classified.reason}")
            if classified.kind == "failed":
                return SendResult.failed(f"微信发送失败: {classified.reason}")
            return SendResult.unsure(f"微信发送失败: {classified.reason}")
