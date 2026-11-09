"""微信发送异常分类：永久失败/可重试/结果未知不得混淆。"""
from __future__ import annotations

import asyncio

import pytest

from backend.modules.channels.wechat.account import TransportError
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.delivery.wechat import WeChatTextSender, classify_wechat_error
from backend.shared.errors import InvalidInputError


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (InvalidInputError("渠道账号不可用"), "failed"),
        (TransportError("unauthorized", status=401), "failed"),
        (TransportError("gone", status=404), "failed"),
        (TransportError("invalid receiver", ret=40001), "failed"),
        (TransportError("rate limited", ret=45009), "retry"),
        (TransportError("too many", status=429), "retry"),
        (TransportError("bad gateway", status=502), "uncertain"),
        (TransportError("timeout"), "uncertain"),
        (asyncio.TimeoutError(), "uncertain"),
        (ConnectionError("reset by peer"), "uncertain"),
        (RuntimeError("boom"), "uncertain"),
    ],
)
def test_classification(exc: BaseException, kind: str) -> None:
    assert classify_wechat_error(exc).kind == kind


class _Channels:
    def __init__(self, exc: BaseException | None = None) -> None:
        self.exc = exc

    def is_delivery_binding_active(self, *_args) -> bool:
        return True

    async def send_wechat_text(self, **_kwargs) -> None:
        if self.exc is not None:
            raise self.exc


@pytest.mark.asyncio
async def test_sender_maps_failure_to_non_retryable() -> None:
    sender = WeChatTextSender(_Channels(InvalidInputError("缺少凭证")))
    result = await sender.send_text(DeliveryTarget(kind="wechat", ref="u"), "hi")
    assert not result.ok and not result.retryable and not result.uncertain


@pytest.mark.asyncio
async def test_sender_maps_timeout_to_uncertain() -> None:
    sender = WeChatTextSender(_Channels(asyncio.TimeoutError()))
    result = await sender.send_text(DeliveryTarget(kind="wechat", ref="u"), "hi")
    assert result.uncertain and not result.retryable
