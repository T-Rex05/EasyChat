"""渠道契约测试（Task 7）：iLink 归一化、绑定身份、持久去重、扫码与监听生命周期。

只替换网络 Seam；数据库是真实临时 SQLite，执行走统一 Assistant + FakeRuntime。
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from backend.modules.channels.contracts import (
    LISTENER_BACKOFF,
    LISTENER_ERROR,
    LISTENER_RUNNING,
    LISTENER_STARTING,
    LISTENER_STOPPED,
    QR_CONFIRMED,
    QR_WAIT,
)
from backend.modules.channels.wechat.account import TransportError
from backend.modules.channels.wechat.parser import parse_inbound
from backend.runtime.contracts import RuntimeEvent
from backend.shared.crypto import decrypt_secret
from backend.shared.errors import ForbiddenError
from tests.support.rig import TEST_ENCRYPTION_SECRET
from tests.support.wechat import (
    FakeTransport,
    image_message,
    inbound,
    make_channel_rig,
    text_message,
)


def _completed(text: str = "好的") -> list[RuntimeEvent]:
    return [RuntimeEvent(kind="completed", payload={"result": {"final_response": text, "completed": True}})]


def _rows(rig, sql: str, params=()):
    conn = rig.db.connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _admin(rig):
    return rig.seed_user(role="super_admin", username=f"admin_{uuid.uuid4().hex[:6]}")


def _user(rig, name: str | None = None):
    return rig.seed_user(role="user", grants=("chat.use",), username=name or f"u_{uuid.uuid4().hex[:6]}")


def _register(rig, admin, account_id: str = "bot_1", token: str = "bot-token"):
    view = rig.channels.register_account(
        admin, account_id=account_id, token=token,
        base_url="https://ilink.test", bot_user_id=f"botuser_{account_id}",
    )
    return rig.channels.repo.get_account(view.id)


def _bind(rig, admin, account, external_user: str, user):
    return rig.channels.bind_user(
        admin, platform="wechat", account_id=account.account_id,
        external_user_id=external_user, user_id=user.user_id, account_pk=account.id,
    )


async def _wait_until(predicate, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("等待条件超时")


@pytest.fixture
async def env(tmp_path):
    rig, transport, media = make_channel_rig(tmp_path)
    await rig.start_assistant()
    yield rig, transport, media
    await rig.aclose()


# ── 身份与拒绝 ────────────────────────────────────────────────────────────────


async def test_unbound_message_rejected_without_execution(env):
    rig, _, _ = env
    admin = _admin(rig)
    account = _register(rig, admin)
    outcome = await rig.channels.handle_inbound(inbound(rig, account, text_message("你好", message_id="m-unbound")))
    assert outcome.accepted is False
    assert outcome.reason == "unbound"
    await rig.drain_runs()
    assert rig.runtime.execute_count == 0
    events = _rows(rig, "SELECT state, error FROM channel_events WHERE external_event_id='msg:m-unbound'")
    assert events[0]["state"] == "rejected"
    assert "unbound" in events[0]["error"]


async def test_disabled_user_rejected_immediately_and_recovers(env):
    rig, _, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)

    rig.access.set_user_status(admin, user.user_id, 0)
    disabled = await rig.channels.handle_inbound(inbound(rig, account, text_message("还在吗", message_id="m-disabled")))
    assert disabled.reason == "user_disabled"
    await rig.drain_runs()
    assert rig.runtime.execute_count == 0

    rig.access.set_user_status(admin, user.user_id, 1)
    recovered = await rig.channels.handle_inbound(inbound(rig, account, text_message("现在呢", message_id="m-enabled")))
    assert recovered.accepted is True
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1


async def test_unbind_takes_effect_on_next_message(env):
    rig, _, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    binding = _bind(rig, admin, account, "wx_ext_1", user)

    first = await rig.channels.handle_inbound(inbound(rig, account, text_message("第一条", message_id="m-b1")))
    assert first.accepted is True
    await rig.drain_runs()

    rig.channels.unbind(admin, binding.id)
    second = await rig.channels.handle_inbound(inbound(rig, account, text_message("第二条", message_id="m-b2")))
    assert second.accepted is False
    assert second.reason == "unbound"
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1  # 解绑后未触发第二次执行


async def test_two_bot_accounts_same_message_id_do_not_conflict(env):
    rig, _, _ = env
    admin = _admin(rig)
    u1, u2 = _user(rig), _user(rig)
    a1 = _register(rig, admin, account_id="bot_a", token="token-a")
    a2 = _register(rig, admin, account_id="bot_b", token="token-b")
    _bind(rig, admin, a1, "openid_same", u1)
    _bind(rig, admin, a2, "openid_same", u2)

    msg = text_message("同一条平台消息ID", message_id="platform-msg-1", from_user="openid_same")
    first = await rig.channels.handle_inbound(inbound(rig, a1, msg))
    second = await rig.channels.handle_inbound(inbound(rig, a2, msg))
    assert first.accepted and second.accepted
    await rig.drain_runs()

    runs = _rows(rig, "SELECT owner_id, channel_account_scope, client_message_id FROM runs ORDER BY created_at")
    assert len(runs) == 2
    assert {r["owner_id"] for r in runs} == {u1.user_id, u2.user_id}
    # 事件唯一键包含 account_id：两个机器人账号各有一条事件
    events = _rows(rig, "SELECT account_id FROM channel_events WHERE external_event_id='msg:platform-msg-1'")
    assert {e["account_id"] for e in events} == {"bot_a", "bot_b"}


# ── 持久去重 ──────────────────────────────────────────────────────────────────


async def test_duplicate_stable_message_id_executes_once(env):
    rig, _, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)

    msg = text_message("只应执行一次", message_id="dup-1")
    first = await rig.channels.handle_inbound(inbound(rig, account, msg))
    second = await rig.channels.handle_inbound(inbound(rig, account, msg))
    assert first.accepted is True and first.duplicate is False
    assert second.accepted is False and second.duplicate is True
    assert second.run_id == first.run_id
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1
    user_messages = _rows(rig, "SELECT count(*) AS c FROM conversations WHERE role='user' AND run_id=?", (first.run_id,))
    assert user_messages[0]["c"] == 1


async def test_fingerprint_dedup_is_windowed_not_permanent(env):
    rig, _, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)

    now = rig.clock()
    msg = text_message("相同文本", message_id="")
    first = await rig.channels.handle_inbound(inbound(rig, account, msg, now=now))
    duplicate = await rig.channels.handle_inbound(inbound(rig, account, msg, now=now))
    assert first.accepted is True
    assert duplicate.reason == "duplicate"
    # 窗口过后相同文本必须能再次处理（不能永久吞掉）
    rig.clock.advance(6.0)
    later = await rig.channels.handle_inbound(inbound(rig, account, msg, now=rig.clock()))
    assert later.accepted is True and later.duplicate is False

    await rig.drain_runs()
    assert rig.runtime.execute_count == 2
    modes = _rows(rig, "SELECT event_kind FROM channel_events ORDER BY received_at")
    assert {m["event_kind"] for m in modes} == {"fingerprint"}


# ── 消息归一化与媒体 ─────────────────────────────────────────────────────────


async def test_parser_extracts_text_and_media_refs_without_bytes(env):
    rig, _, _ = env
    admin = _admin(rig)
    account = _register(rig, admin)
    msg = image_message(url="https://cdn.example/pic.png", file_name="pic.png", message_id="m-media-0")
    msg["item_list"].insert(0, {"type": 1, "text_item": {"text": "看图"}})
    parsed = parse_inbound(account, msg, now=rig.clock())
    assert parsed is not None
    assert parsed.text == "看图"
    assert len(parsed.media) == 1
    assert parsed.media[0].kind == "image"
    assert parsed.media[0].url == "https://cdn.example/pic.png"
    assert not hasattr(parsed.media[0], "data")


async def test_parser_bounds_media_refs_per_message(env):
    rig, _, _ = env
    admin = _admin(rig)
    account = _register(rig, admin)
    items = [
        {"type": 2, "image_item": {"url": f"https://cdn.example/{i}.png", "file_name": f"{i}.png"}}
        for i in range(30)
    ]
    parsed = parse_inbound(account, {"from_user_id": "wx_ext_1", "item_list": items}, now=rig.clock())
    assert parsed is not None
    assert len(parsed.media) == 10  # MAX_MEDIA_REFS_PER_MESSAGE


async def test_media_ingested_to_attachment_and_run_attachment_ids(env):
    rig, _, media = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)

    outcome = await rig.channels.handle_inbound(
        inbound(rig, account, image_message(message_id="m-media-1"))
    )
    assert outcome.accepted is True
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1

    request = rig.runtime.requests[-1]
    assert len(request.attachment_ids) == 1
    attachments = _rows(rig, "SELECT file_name, file_path, file_size FROM attachments")
    assert len(attachments) == 1
    assert attachments[0]["file_size"] > 0
    # 事件 payload 只有引用描述，不含文件字节/data URL
    payload = _rows(rig, "SELECT payload FROM channel_events WHERE external_event_id='msg:m-media-1'")[0]["payload"]
    assert "base64" not in payload.lower()
    assert "fake-image" not in payload


async def test_media_fetch_failure_does_not_block_text(env):
    rig, _, media = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)
    media.fail_next = True

    outcome = await rig.channels.handle_inbound(
        inbound(rig, account, image_message(message_id="m-media-fail"))
    )
    assert outcome.accepted is True  # 媒体失败不阻塞文字/默认指令
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1
    assert rig.runtime.requests[-1].attachment_ids == ()


# ── 会话切换与跨端隔离 ───────────────────────────────────────────────────────


async def test_new_and_switch_session_persist_to_next_message(env):
    rig, _, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)

    first = await rig.channels.handle_inbound(inbound(rig, account, text_message("第一句", message_id="s-1")))
    assert first.accepted and first.session_id
    await rig.drain_runs()
    session_one = first.session_id

    new_cmd = await rig.channels.handle_inbound(inbound(rig, account, text_message("/new", message_id="s-2")))
    assert new_cmd.accepted and "已开启新对话" in new_cmd.reply_text
    assert new_cmd.session_id != session_one

    second = await rig.channels.handle_inbound(inbound(rig, account, text_message("第二句", message_id="s-3")))
    await rig.drain_runs()
    assert second.session_id == new_cmd.session_id
    runs = _rows(rig, "SELECT session_id FROM runs ORDER BY created_at")
    assert runs[-1]["session_id"] == new_cmd.session_id

    history = await rig.channels.handle_inbound(inbound(rig, account, text_message("/history", message_id="s-4")))
    assert "最近会话" in history.reply_text

    switch = await rig.channels.handle_inbound(inbound(rig, account, text_message("/2", message_id="s-5")))
    assert switch.reply_text.startswith("✅ 已切换")
    assert switch.session_id == session_one
    follow = await rig.channels.handle_inbound(inbound(rig, account, text_message("切换后", message_id="s-6")))
    await rig.drain_runs()
    assert follow.session_id == session_one

    status = await rig.channels.handle_inbound(inbound(rig, account, text_message("/status", message_id="s-7")))
    assert "当前会话" in status.reply_text


async def test_unknown_or_removed_command_does_not_execute_model(env):
    rig, _, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)

    removed = await rig.channels.handle_inbound(inbound(rig, account, text_message("/model 1", message_id="cmd-1")))
    assert "已停用" in removed.reply_text
    await rig.drain_runs()
    assert rig.runtime.execute_count == 0


# ── 扫码、账号与监听生命周期 ─────────────────────────────────────────────────


async def test_qr_login_encrypts_token_and_binds_scanner(env):
    rig, transport, _ = env
    admin = _admin(rig)
    transport.script_qr(
        {"qrcode": "qr-value", "qrcode_img_content": "https://weixin.qq.com/qr"},
        {"status": "confirmed", "ilink_bot_id": "bot-qr-1", "bot_token": "plain-bot-token",
         "baseurl": "https://ilink.test", "ilink_user_id": "wx_scanner"},
    )
    started = await rig.channels.start_qr_login(admin)
    assert started.status == QR_WAIT

    polled = await rig.channels.poll_qr_login(admin, started.session_id)
    assert polled.status == QR_CONFIRMED
    result = await rig.channels.bind_after_qr(admin, started.session_id)
    assert result["account"]["account_id"] == "bot-qr-1"
    assert result["binding"]["user_id"] == admin.user_id

    # token 只以密文落库，可解密回原文
    row = _rows(rig, "SELECT credentials_ref FROM channel_accounts WHERE account_id='bot-qr-1'")[0]
    assert "plain-bot-token" not in row["credentials_ref"]
    stored = json.loads(row["credentials_ref"])["token"]
    assert decrypt_secret(stored, TEST_ENCRYPTION_SECRET) == "plain-bot-token"

    account = rig.channels.repo.get_account_by_platform_id("wechat", "bot-qr-1")
    await rig.channels.listener.stop(account.id)


async def test_qr_requires_admin(env):
    rig, transport, _ = env
    user = _user(rig)
    with pytest.raises(ForbiddenError):
        await rig.channels.start_qr_login(user)


async def test_listener_reports_real_running_then_stopped(env):
    rig, transport, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)
    rig.runtime.script_events(_completed())

    transport.script_updates({
        "ret": 0, "get_updates_buf": "cursor-1",
        "msgs": [text_message("监听收到的消息", message_id="listen-1")],
    })
    state = await rig.channels.listener.start(account.id)
    assert state.status == LISTENER_STARTING
    await _wait_until(lambda: rig.channels.listener.status(account.id).status == LISTENER_RUNNING)
    await _wait_until(lambda: rig.runtime.execute_count == 1)
    await rig.drain_runs()

    refreshed = rig.channels.repo.get_account(account.id)
    assert refreshed.sync_cursor == "cursor-1"
    assert refreshed.last_poll_at
    assert rig.channels.listener.status(account.id).polls >= 1

    stopped = await rig.channels.listener.stop(account.id)
    assert stopped.status == LISTENER_STOPPED


async def test_listener_error_is_persisted_and_backs_off(env):
    rig, transport, _ = env
    admin = _admin(rig)
    account = _register(rig, admin)
    rig.channels.listener.backoff = (0.01,)
    rig.channels.listener.poll_interval = 0.01
    transport.script_updates(*[TransportError("模拟断线")] * 100)

    await rig.channels.listener.start(account.id)
    await _wait_until(lambda: rig.channels.listener.status(account.id).status == LISTENER_BACKOFF)
    await _wait_until(
        lambda: "模拟断线" in (rig.channels.repo.get_account(account.id).last_error or "")
    )
    await rig.channels.listener.stop(account.id)


async def test_disabled_account_stops_listener_and_rejects_inbound(env):
    rig, transport, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)

    await rig.channels.set_account_status(admin, account.id, "disabled")
    assert rig.channels.listener.status(account.id).status == LISTENER_STOPPED

    outcome = await rig.channels.handle_inbound(inbound(rig, account, text_message("禁用后", message_id="off-1")))
    assert outcome.reason == "account_disabled"
    await rig.drain_runs()
    assert rig.runtime.execute_count == 0


async def test_listener_start_without_credentials_reports_error(env):
    rig, _, _ = env
    admin = _admin(rig)
    account = _register(rig, admin)
    # 清空凭证模拟损坏/未扫码状态
    with rig.db.transaction() as tx:
        tx.execute("UPDATE channel_accounts SET credentials_ref='' WHERE id=?", (account.id,))
    state = await rig.channels.listener.start(account.id)
    assert state.status == LISTENER_ERROR
