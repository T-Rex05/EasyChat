"""禁用提示通过真实入站与去重流程，iLink 和模型都使用测试替身。"""
from __future__ import annotations

import pytest

from backend.modules.channels.wechat.account import TransportError
from backend.modules.channels.wechat.parser import parse_inbound
from tests.support.wechat import make_channel_rig, text_message


NOTICE = "账号被禁用，请找伟大的啊嘟嘟大人解封！"


@pytest.fixture
async def disabled_env(tmp_path):
    rig, transport, media = make_channel_rig(tmp_path)
    admin = rig.seed_user(role="super_admin")
    user = rig.seed_user(grants=("chat.use",))
    view = rig.channels.register_account(
        admin, account_id="bot", token="test-token", base_url="https://ilink.test",
    )
    binding = rig.channels.bind_user(
        admin, platform="wechat", account_id="bot", external_user_id="wx_ext_1",
        user_id=user.user_id,
    )
    try:
        yield rig, transport, media, admin, user, view.id, binding
    finally:
        await rig.aclose()


async def test_disabled_sender_receives_one_notice_per_message_without_processing(disabled_env):
    rig, transport, media, admin, user, account_id, binding = disabled_env
    rig.access.set_user_status(admin, user.user_id, 0)
    raws = [text_message("你好", message_id="text"), text_message("/new", message_id="command")]
    for item_type, kind in [(2, "image"), (3, "voice"), (4, "file"), (5, "video")]:
        raw = text_message("", message_id=kind, context_token=f"ctx-{kind}")
        raw["item_list"] = [{"type": item_type, f"{kind}_item": {"url": "https://cdn.test/media"}}]
        raws.append(raw)
    no_media = text_message("", message_id="missing-download")
    no_media["item_list"] = [{"type": 3, "voice_item": {}}]
    raws.append(no_media)
    unsupported = text_message("", message_id="unsupported")
    unsupported["item_list"] = [{"type": 6}]
    raws.append(unsupported)
    outbound_echo = text_message("回执回声", message_id="echo") | {"message_type": 2}
    bot_echo = text_message("机器人自身", message_id="bot", from_user="bot")
    unbound = text_message("陌生人", message_id="unbound", from_user="stranger")
    empty = text_message("", message_id="empty") | {"item_list": []}

    transport.script_updates({"ret": 0, "msgs": [*raws, *raws, outbound_echo, bot_echo, unbound, empty]})
    await rig.channels.listener.poll_once(account_id)

    sent = [post["payload"]["msg"] for post in transport.posts if post["url"].endswith("/sendmessage")]
    assert transport.sent == [NOTICE] * len(raws)
    assert [message["to_user_id"] for message in sent] == ["wx_ext_1"] * len(raws)
    assert [message["context_token"] for message in sent] == [raw["context_token"] for raw in raws]
    assert all(post["token"] == "test-token" for post in transport.posts)
    assert media.calls == []
    assert rig.runtime.execute_count == 0
    conn = rig.db.connect()
    try:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM llm_calls").fetchone()[0] == 0
    finally:
        conn.close()
    assert not rig.channels.is_delivery_binding_active(account_id, "wx_ext_1")

    rig.channels.unbind(admin, binding.id)
    transport.script_updates({"ret": 0, "msgs": [text_message("解绑后", message_id="unlinked")]})
    await rig.channels.listener.poll_once(account_id)
    assert transport.sent == [NOTICE] * len(raws)


async def test_disabled_during_principal_lookup_returns_notice(disabled_env, monkeypatch):
    rig, transport, _, admin, user, account_id, _ = disabled_env
    snapshot = rig.access.snapshot_principal

    def disable_before_snapshot(user_id):
        rig.access.set_user_status(admin, user.user_id, 0)
        return snapshot(user_id)

    monkeypatch.setattr(rig.access, "snapshot_principal", disable_before_snapshot)
    raw = text_message("/new", message_id="race")
    transport.script_updates({"ret": 0, "msgs": [raw]})
    await rig.channels.listener.poll_once(account_id)

    assert transport.sent == [NOTICE]
    assert rig.runtime.execute_count == 0

    rig.access.set_user_status(admin, user.user_id, 1)
    monkeypatch.setattr(rig.access, "snapshot_principal", snapshot)
    transport.script_updates({"ret": 0, "msgs": [raw]})
    await rig.channels.listener.poll_once(account_id)
    assert transport.sent == [NOTICE]
    account = rig.channels.repo.get_account(account_id)
    outcome = await rig.channels.handle_inbound(parse_inbound(
        account, text_message("恢复后", message_id="re-enabled"), now=rig.clock(),
    ))
    assert outcome.accepted and outcome.run_id


async def test_failed_notice_send_stays_pending_until_platform_retries(disabled_env, monkeypatch):
    rig, transport, _, admin, user, account_id, _ = disabled_env
    rig.access.set_user_status(admin, user.user_id, 0)
    post_json = transport.post_json
    fail_next_send = True

    async def post_with_failure(url, payload, **kwargs):
        nonlocal fail_next_send
        if url.endswith("/sendmessage") and fail_next_send:
            fail_next_send = False
            raise TransportError("测试注入发送失败")
        return await post_json(url, payload, **kwargs)

    monkeypatch.setattr(transport, "post_json", post_with_failure)
    raw = text_message("重试", message_id="retry")
    response = {"ret": 0, "msgs": [raw], "get_updates_buf": "next"}
    transport.script_updates(response, response, response)

    with pytest.raises(TransportError, match="测试注入发送失败"):
        await rig.channels.listener.poll_once(account_id)
    assert rig.channels.repo.get_account(account_id).sync_cursor == ""

    await rig.channels.listener.poll_once(account_id)
    await rig.channels.listener.poll_once(account_id)
    assert transport.sent == [NOTICE]
    assert rig.channels.repo.get_account(account_id).sync_cursor == "next"


async def test_notice_uses_same_sender_context_when_media_has_no_token(disabled_env):
    rig, transport, _, admin, user, account_id, _ = disabled_env
    rig.channels.repo.set_session_cursor(
        "wechat", "bot", "wx_ext_1", "wx_ext_1", "session", context_token="prior-sender-token",
    )
    rig.access.set_user_status(admin, user.user_id, 0)
    raw = text_message("", message_id="voice", context_token="")
    raw["item_list"] = [{"type": 3, "voice_item": {}}]
    transport.script_updates({"ret": 0, "msgs": [raw]})

    await rig.channels.listener.poll_once(account_id)

    assert transport.sent == [NOTICE]
    assert transport.posts[-1]["payload"]["msg"]["context_token"] == "prior-sender-token"

    other_chat = raw | {"chat_id": "new-chat", "message_id": "other-chat"}
    transport.script_updates({"ret": 0, "msgs": [other_chat]})
    await rig.channels.listener.poll_once(account_id)
    assert transport.sent == [NOTICE, NOTICE]
    assert not transport.posts[-1]["payload"]["msg"].get("context_token")


async def test_pending_disabled_notice_requires_the_pinned_owner_and_chat(disabled_env):
    rig, transport, _, admin, user, account_id, binding = disabled_env
    rig.access.set_user_status(admin, user.user_id, 0)
    raw = text_message("重试", message_id="owner-chat")
    account = rig.channels.repo.get_account(account_id)
    original = parse_inbound(account, raw, now=rig.clock())
    assert (await rig.channels.handle_inbound(original)).reply_text == NOTICE

    other_chat = raw | {"chat_id": "different-chat"}
    transport.script_updates({"ret": 0, "msgs": [other_chat]})
    await rig.channels.listener.poll_once(account_id)
    assert transport.sent == []

    replacement = rig.seed_user(grants=("chat.use",))
    rig.channels.unbind(admin, binding.id)
    rig.channels.bind_user(
        admin, platform="wechat", account_id="bot", external_user_id="wx_ext_1",
        user_id=replacement.user_id,
    )
    rig.access.set_user_status(admin, replacement.user_id, 0)
    transport.script_updates({"ret": 0, "msgs": [raw]})
    await rig.channels.listener.poll_once(account_id)
    assert transport.sent == []
