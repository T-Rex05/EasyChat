"""微信文本发送 Adapter：把 delivery 的目标映射到 Task 7 的 iLink 通道。

解绑/禁用检查在每次发送前通过 channels 公开方法执行；网络异常按“结果未知”
返回 uncertain，避免假称必达或盲目重发。
"""
from __future__ import annotations

import logging
from typing import Any

from backend.modules.delivery.contracts import DeliveryTarget, SendResult

logger = logging.getLogger(__name__)


class WeChatTextSender:
    def __init__(self, channels: Any) -> None:
        self.channels = channels

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
        except Exception as exc:  # noqa: BLE001  外部发送失败：结果可能已生效
            logger.warning("微信投递失败（进入 uncertain）: %s", exc)
            return SendResult.unsure(f"微信发送失败: {exc}")
