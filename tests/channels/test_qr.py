"""微信扫码登录：二维码内容必须渲染成可展示的 PNG data URL。"""
from __future__ import annotations

import pytest

from backend.modules.channels.wechat.account import (
    QrLoginManager,
    TransportError,
    _render_qr_data_url,
)


class FakeTransport:
    async def get_json(self, url: str, *, timeout: float = 15.0, headers=None):
        return {
            "qrcode": "qr-value",
            "qrcode_img_content": "https://liteapp.weixin.qq.com/q/demo",
        }

    async def post_json(self, url: str, payload, *, token: str = "", timeout: float = 15.0):
        return {}

    async def download_to(self, url: str, dest_path, *, max_bytes: int, timeout: float = 60.0, allowed_hosts=None):
        return 0


@pytest.mark.asyncio
async def test_qr_start_returns_png_data_url() -> None:
    pytest.importorskip("qrcode")
    manager = QrLoginManager(FakeTransport(), clock=lambda: 1793865600.0)
    view = await manager.start()
    assert view.status == "wait"
    assert view.qr_content == "https://liteapp.weixin.qq.com/q/demo"
    assert view.qr_image.startswith("data:image/png;base64,")
    assert len(view.qr_image) > 200


class PollTimeoutTransport(FakeTransport):
    async def get_json(self, url: str, *, timeout: float = 15.0, headers=None):
        if "get_qrcode_status" in url:
            raise TransportError("timeout")
        return await super().get_json(url, timeout=timeout)


@pytest.mark.asyncio
async def test_qr_poll_timeout_keeps_waiting_instead_of_500() -> None:
    pytest.importorskip("qrcode")
    manager = QrLoginManager(PollTimeoutTransport(), clock=lambda: 1793865600.0)
    started = await manager.start()
    view = await manager.poll(started.session_id)
    assert view.status == "wait"
    assert view.qr_image.startswith("data:image/png;base64,")


def test_qr_render_failure_returns_empty_fallback(monkeypatch) -> None:
    """qrcode 已装但 Pillow 缺失时不能抛 500，前端还有 qr_content 可点。"""
    qrcode = pytest.importorskip("qrcode")

    def broken(_self):
        raise ImportError("Pillow not installed")

    monkeypatch.setattr(qrcode.QRCode, "make_image", broken)
    assert _render_qr_data_url("https://liteapp.weixin.qq.com/q/demo") == ""
