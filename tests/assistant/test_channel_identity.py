"""渠道身份契约（Task 7）：绑定决定 owner、跨账号不串联、跨端会话独立。"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.modules.channels.contracts import InboundMessage
from backend.runtime.contracts import RuntimeEvent
from backend.shared.errors import ForbiddenError, NotFoundError
from tests.support.wechat import inbound, make_channel_rig, text_message


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


def _register(rig, admin, account_id: str, token: str):
    view = rig.channels.register_account(
        admin, account_id=account_id, token=token,
        base_url="https://ilink.test", bot_user_id=f"bot_{account_id}",
    )
    return rig.channels.repo.get_account(view.id)


@pytest.fixture
async def env(tmp_path):
    rig, transport, media = make_channel_rig(tmp_path)
    await rig.start_assistant()
    rig.runtime.script_events([
        RuntimeEvent(kind="completed", payload={"result": {"final_response": "ok", "completed": True}}),
    ])
    yield rig, transport
    await rig.aclose()


async def test_binding_owner_decides_not_nickname(env):
    rig, _ = env
    admin = _admin(rig)
    alice, bob = _user(rig), _user(rig)
    account = _register(rig, admin, "bot-owner", "t1")
    rig.channels.bind_user(admin, platform="wechat", account_id=account.account_id,
                           external_user_id="wx_alice", user_id=alice.user_id, account_pk=account.id)
    rig.channels.bind_user(admin, platform="wechat", account_id=account.account_id,
                           external_user_id="wx_bob", user_id=bob.user_id, account_pk=account.id)

    alice_msg = text_message("同一个昵称", message_id="id-a", from_user="wx_alice")
    alice_msg["nickname"] = "张三"  # 协议昵称不参与 owner 判定
    bob_msg = text_message("同一个昵称", message_id="id-b", from_user="wx_bob")
    bob_msg["nickname"] = "张三"

    first = await rig.channels.handle_inbound(inbound(rig, account, alice_msg))
    second = await rig.channels.handle_inbound(inbound(rig, account, bob_msg))
    assert first.accepted and second.accepted
    await rig.drain_runs()

    runs = _rows(rig, "SELECT owner_id, source FROM runs")
    assert {r["owner_id"] for r in runs} == {alice.user_id, bob.user_id}
    assert {r["source"] for r in runs} == {"wechat"}


async def test_same_openid_on_two_accounts_routes_to_distinct_owners(env):
    rig, _ = env
    admin = _admin(rig)
    alice, bob = _user(rig), _user(rig)
    a1 = _register(rig, admin, "bot-x", "tx")
    a2 = _register(rig, admin, "bot-y", "ty")
    rig.channels.bind_user(admin, platform="wechat", account_id=a1.account_id,
                           external_user_id="same_openid", user_id=alice.user_id, account_pk=a1.id)
    rig.channels.bind_user(admin, platform="wechat", account_id=a2.account_id,
                           external_user_id="same_openid", user_id=bob.user_id, account_pk=a2.id)

    await rig.channels.handle_inbound(inbound(rig, a1, text_message("来自A", message_id="cross-1", from_user="same_openid")))
    await rig.channels.handle_inbound(inbound(rig, a2, text_message("来自B", message_id="cross-2", from_user="same_openid")))
    await rig.drain_runs()

    runs = _rows(rig, "SELECT owner_id, session_id, channel_account_scope FROM runs ORDER BY created_at")
    assert len(runs) == 2
    assert len({r["owner_id"] for r in runs}) == 2
    assert len({r["session_id"] for r in runs}) == 2
    assert len({r["channel_account_scope"] for r in runs}) == 2


async def test_account_pk_mismatch_is_rejected(env):
    rig, _ = env
    admin = _admin(rig)
    a1 = _register(rig, admin, "bot-p", "tp")
    a2 = _register(rig, admin, "bot-q", "tq")
    forged = InboundMessage(
        platform="wechat",
        account_pk=a1.id,
        external_account_id=a2.account_id,  # 内部账号与外部账号不一致
        external_user_id="wx_ext_1",
        external_chat_id="wx_ext_1",
        external_event_id="msg:forged-1",
        text="越权尝试",
        received_at=rig.clock(),
    )
    outcome = await rig.channels.handle_inbound(forged)
    assert outcome.accepted is False
    assert outcome.reason == "invalid"
    assert _rows(rig, "SELECT count(*) AS c FROM channel_events")[0]["c"] == 0


async def test_unbound_openid_on_second_account_is_not_inherited(env):
    rig, _ = env
    admin = _admin(rig)
    user = _user(rig)
    a1 = _register(rig, admin, "bot-bound", "tb1")
    a2 = _register(rig, admin, "bot-unbound", "tb2")
    rig.channels.bind_user(admin, platform="wechat", account_id=a1.account_id,
                           external_user_id="wx_shared", user_id=user.user_id, account_pk=a1.id)

    ok = await rig.channels.handle_inbound(inbound(rig, a1, text_message("A收到", message_id="inh-1", from_user="wx_shared")))
    rejected = await rig.channels.handle_inbound(inbound(rig, a2, text_message("B收到", message_id="inh-2", from_user="wx_shared")))
    assert ok.accepted is True
    assert rejected.accepted is False
    assert rejected.reason == "unbound"
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1


async def test_rebinding_changes_owner_on_next_message(env):
    rig, _ = env
    admin = _admin(rig)
    alice, bob = _user(rig), _user(rig)
    account = _register(rig, admin, "bot-rebind", "tr")
    rig.channels.bind_user(admin, platform="wechat", account_id=account.account_id,
                           external_user_id="wx_moving", user_id=alice.user_id, account_pk=account.id)
    await rig.channels.handle_inbound(inbound(rig, account, text_message("第一段", message_id="rb-1", from_user="wx_moving")))
    await rig.drain_runs()

    rig.channels.bind_user(admin, platform="wechat", account_id=account.account_id,
                           external_user_id="wx_moving", user_id=bob.user_id, account_pk=account.id)
    await rig.channels.handle_inbound(inbound(rig, account, text_message("第二段", message_id="rb-2", from_user="wx_moving")))
    await rig.drain_runs()

    owners = [r["owner_id"] for r in _rows(rig, "SELECT owner_id FROM runs ORDER BY created_at")]
    assert owners == [alice.user_id, bob.user_id]


async def test_cross_channel_shares_owner_but_sessions_are_independent(env):
    rig, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin, "bot-memory", "tm")
    rig.channels.bind_user(admin, platform="wechat", account_id=account.account_id,
                           external_user_id="wx_ext_1", user_id=user.user_id, account_pk=account.id)

    web_session = await rig.assistant.create_session(user, source="web")
    await rig.assistant.submit(RunCommand(
        principal=user, session_id=web_session, source="web",
        client_message_id="web-identity-1", text="Web 端提问",
    ))
    await rig.drain_runs()

    wechat = await rig.channels.handle_inbound(inbound(rig, account, text_message("微信端提问", message_id="wx-identity-1")))
    assert wechat.accepted is True
    await rig.drain_runs()

    assert len(rig.runtime.requests) == 2
    web_ctx = rig.runtime.requests[0].context
    wx_ctx = rig.runtime.requests[1].context
    assert web_ctx.principal.user_id == wx_ctx.principal.user_id == user.user_id
    assert web_ctx.session_id != wx_ctx.session_id
    assert (web_ctx.source, wx_ctx.source) == ("web", "wechat")
    assert wx_ctx.channel_account_id == account.id
    assert web_ctx.channel_account_id is None

    sessions = _rows(rig, "SELECT id, owner_id, source, external_chat_id FROM sessions ORDER BY created_at")
    assert len(sessions) == 2
    assert {s["source"] for s in sessions} == {"web", "wechat"}
    assert all(s["owner_id"] == user.user_id for s in sessions)
    wechat_row = next(s for s in sessions if s["source"] == "wechat")
    assert wechat_row["external_chat_id"].startswith("bot-memory:")


async def test_binding_rejects_disabled_user_and_missing_account(env):
    rig, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin, "bot-bind-check", "tc")
    rig.access.set_user_status(admin, user.user_id, 0)
    with pytest.raises(ForbiddenError):
        rig.channels.bind_user(admin, platform="wechat", account_id=account.account_id,
                               external_user_id="wx_disabled", user_id=user.user_id, account_pk=account.id)
    with pytest.raises(NotFoundError):
        rig.channels.bind_user(admin, platform="wechat", account_id="missing-bot",
                               external_user_id="wx_missing", user_id=admin.user_id)


async def test_binding_creation_and_reactivation_require_manage(env):
    rig, _ = env
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin, "bot-perm", "tp")
    # 普通用户不能用任意 openid 自绑（外部 id 不是身份证明）
    with pytest.raises(ForbiddenError):
        rig.channels.bind_user(user, platform="wechat", account_id=account.account_id,
                               external_user_id="wx_claim", user_id=user.user_id, account_pk=account.id)
    binding = rig.channels.bind_user(admin, platform="wechat", account_id=account.account_id,
                                     external_user_id="wx_claim", user_id=user.user_id, account_pk=account.id)
    rig.channels.set_binding_status(admin, binding.id, "disabled")
    # 本人可以解绑，但不能把管理员禁用的绑定重新启用
    with pytest.raises(ForbiddenError):
        rig.channels.set_binding_status(user, binding.id, "active")
    # 本人对自己仍启用的绑定执行解绑是允许的
    other = rig.channels.bind_user(admin, platform="wechat", account_id=account.account_id,
                                   external_user_id="wx_self_off", user_id=user.user_id, account_pk=account.id)
    disabled = rig.channels.unbind(user, other.id)
    assert disabled.status == "disabled"
