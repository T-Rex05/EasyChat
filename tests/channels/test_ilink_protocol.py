"""iLink 协议回归：请求头编码、凭据失效分类与账号暂停（工作包二）。

官方参考：Tencent/openclaw-weixin @ 0ad1ae91347a（2026-11-11 固定）。
- docs/protocol.md L43：X-WECHAT-UIN = Base64(随机 uint32 的十进制字符串)；
  L48：QR 状态轮询仅带应用头（iLink-App-Id / iLink-App-ClientVersion），
  不带 AuthorizationType / Authorization / X-WECHAT-UIN。
- src/api/session-guard.ts：errcode/ret -14 = bot token 失效/过期
  （非风控），账号入站+出站暂停 1 小时后自动恢复。
"""
from __future__ import annotations

import asyncio
import base64

import pytest

from backend.modules.channels.contracts import ChannelTransportError
from backend.modules.channels.wechat.account import (
    STALE_TOKEN_CODE,
    TransportError,
    classify_channel_error,
    ilink_headers,
    is_session_paused,
    pause_session,
    remaining_pause_seconds,
    send_text,
)


def test_wechat_uin_encodes_decimal_uint32():
    value = ilink_headers()["X-WECHAT-UIN"]
    decoded = base64.b64decode(value, validate=True).decode("ascii")
    assert decoded.isdecimal()
    assert 0 <= int(decoded) <= 0xFFFFFFFF


def test_wechat_uin_is_random_per_call():
    values = {ilink_headers()["X-WECHAT-UIN"] for _ in range(8)}
    assert len(values) >= 6, "UIN 必须逐请求随机，而不是固定/时间戳单调"


def test_qr_status_polling_sends_app_headers_only():
    """官方 L48：二维码状态轮询仅带应用头，不带 UIN 与认证头。"""
    headers = ilink_headers(token="tok", app_only=True)
    assert "X-WECHAT-UIN" not in headers
    assert "AuthorizationType" not in headers
    assert "Authorization" not in headers
    assert headers["iLink-App-Id"] == "bot"
    assert "iLink-App-ClientVersion" in headers


def test_post_headers_carry_uin_and_auth():
    headers = ilink_headers(token="tok", body_len=128)
    assert "X-WECHAT-UIN" in headers
    assert headers["AuthorizationType"] == "ilink_bot_token"
    assert headers["Authorization"] == "Bearer tok"


def test_classify_channel_error_matches_ret_and_errcode():
    assert classify_channel_error({"ret": -14}) == "stale_token"
    assert classify_channel_error({"errcode": -14}) == "stale_token"
    assert classify_channel_error({"ret": 0, "errcode": -14}) == "stale_token"
    assert classify_channel_error({"ret": -14, "errcode": 0}) == "stale_token"
    assert classify_channel_error({"ret": 0, "errcode": 0}) == ""
    assert classify_channel_error({}) == ""


def _reset_guard():
    from backend.modules.channels.wechat.account import _reset_session_guard_for_test

    _reset_session_guard_for_test()


def test_session_guard_pauses_and_recovers(monkeypatch):
    _reset_guard()
    now = {"t": 1000.0}
    monkeypatch.setattr("backend.modules.channels.wechat.account._monotonic", lambda: now["t"])
    assert not is_session_paused("acct-1")
    pause_session("acct-1")
    assert is_session_paused("acct-1")
    assert remaining_pause_seconds("acct-1") == 3600
    now["t"] = 1000.0 + 3601  # 越过 1 小时窗口
    assert not is_session_paused("acct-1")
    # 账号隔离：另一账号不受影响
    pause_session("acct-2")
    assert not is_session_paused("acct-3")
    assert is_session_paused("acct-2")


class _FakeTransport:
    """最小 FakeTransport：记录请求头，返回预置响应。"""

    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.headers: list[dict] = []

    async def get_json(self, url: str, *, timeout: float = 15.0, headers: dict | None = None):
        self.headers.append(headers or {})
        return self.responses.pop(0)

    async def post_json(self, url: str, payload, *, token: str = "", timeout: float = 15.0, headers: dict | None = None):
        self.headers.append(headers or {})
        return self.responses.pop(0)

    async def download_to(self, *a, **k):  # pragma: no cover
        raise AssertionError("not used")


def test_delivery_uses_public_surface_only(tmp_path):
    """架构约束回归(测试时漏跑 architecture 套件的教训固化):
    delivery 不得私引 channels 实现文件;凭据失效经 ChannelService.report_stale_token
    公开方法,分类码来自 channels.contracts。"""
    import ast
    from pathlib import Path

    src = Path("backend/modules/delivery/wechat.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module]
        elif isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        for mod in mods:
            parts = mod.split(".")
            if parts[:2] == ["backend", "modules"] and parts[2] == "channels":
                assert parts[3:4] and parts[3] in {"api", "contracts"}, f"私有跨引: {mod}"
    assert "STALE_TOKEN_CODE" in src  # 分类仍感知 -14(经公开契约)


def test_send_text_marks_stale_token_and_pauses_account():
    _reset_guard()
    transport = _FakeTransport([{"ret": -14, "errmsg": "token expired"}])
    with pytest.raises(TransportError) as exc_info:
        asyncio.run(send_text(
            transport, base_url="https://ilinkai.weixin.qq.com", token="tok",
            to_user_id="u1", text="hi", account_id="acct-9",
        ))
    assert exc_info.value.ret == STALE_TOKEN_CODE
    assert is_session_paused("acct-9"), "-14 必须触发账号级暂停（入站/出站共享）"


def test_send_text_refuses_while_paused():
    _reset_guard()
    pause_session("acct-paused")
    transport = _FakeTransport([])
    with pytest.raises(ChannelTransportError):
        asyncio.run(send_text(
            transport, base_url="https://ilinkai.weixin.qq.com", token="tok",
            to_user_id="u1", text="hi", account_id="acct-paused",
        ))
    assert transport.headers == [], "暂停期内不得发出任何请求"


def test_send_text_success_has_no_pause():
    _reset_guard()
    transport = _FakeTransport([{"ret": 0}, {"ret": 0}])
    sent = asyncio.run(send_text(
        transport, base_url="https://ilinkai.weixin.qq.com", token="tok",
        to_user_id="u1", text="hello", account_id="acct-ok",
    ))
    assert sent == 1
    assert not is_session_paused("acct-ok")
