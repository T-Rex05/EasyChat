"""记忆确认目标解析（缺陷③回归）：provider 必须复用真实渠道路由。

sessions.external_chat_id 是 `account_id:chat_id`(/new 还追加时间戳)隔离键，
不是收件人；ref 必须来自 channel_session_cursors.external_user_id，并核验
账号活跃、绑定有效、绑定归属=当前 owner。覆盖普通会话、/new、解绑、换绑、
多账号隔离。
"""
from __future__ import annotations

import uuid

from backend.modules.channels.contracts import BINDING_DISABLED
from tests.support.wechat import make_channel_rig, text_message


def _admin(rig):
    return rig.seed_user(role="super_admin", username=f"admin_{uuid.uuid4().hex[:6]}")


def _user(rig):
    return rig.seed_user(role="user", grants=("chat.use",), username=f"u_{uuid.uuid4().hex[:6]}")


def _register(rig, admin, account_id: str = "bot_1"):
    view = rig.channels.register_account(
        admin, account_id=account_id, token="bot-token",
        base_url="https://ilink.test", bot_user_id=f"botuser_{account_id}",
    )
    return rig.channels.repo.get_account(view.id)


def _bind(rig, admin, account, external_user: str, user):
    return rig.channels.bind_user(
        admin, platform="wechat", account_id=account.account_id,
        external_user_id=external_user, user_id=user.user_id, account_pk=account.id,
    )


async def _inbound(rig, account, user_text: str, *, from_user="wx_ext_1", msg_id="m1"):
    from backend.modules.channels.wechat.parser import parse_inbound

    message = parse_inbound(
        account, text_message(user_text, message_id=msg_id, from_user=from_user),
        now=rig.clock(),
    )
    outcome = await rig.channels.handle_inbound(message)
    assert outcome.accepted
    return outcome.session_id


async def _provider_for_session(rig, owner_id: int, session_id: str):
    provider = rig.channels.make_session_target_provider()
    return provider(owner_id, session_id)


async def test_provider_ref_is_real_external_user_not_isolation_key(rig) -> None:
    """核心缺陷：ref 曾取 sessions.external_chat_id 拼接键→确定拒投路径。"""
    rig, _, _ = make_channel_rig(rig.tmp_path)
    admin, user = _admin(rig), _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)
    session_id = await _inbound(rig, account, "你好")

    conn = rig.db.connect()
    try:
        stored = str(conn.execute(
            "SELECT external_chat_id FROM sessions WHERE id=?", (session_id,)
        ).fetchone()[0])
    finally:
        conn.close()
    isolation_key = f"{account.account_id}:{stored.split(':', 1)[-1]}"
    assert stored == isolation_key and stored.count(":") >= 1, (
        "前置事实：sessions.external_chat_id 为账号隔离键拼接"
    )

    target = await _provider_for_session(rig, user.user_id, session_id)
    assert target is not None
    assert target.ref == "wx_ext_1", f"ref 必须是真实 external_user_id，实际 {target.ref!r}"
    assert target.ref != stored
    assert target.channel_account_id == account.id
    assert target.context_token == "ctx-1"


async def test_provider_after_new_command_resolves_current_session(rig) -> None:
    """缺陷补充：/new 会话键带时间戳，provider 仍须解析出真实收件人。"""
    rig, _, _ = make_channel_rig(rig.tmp_path)
    admin, user = _admin(rig), _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)
    await _inbound(rig, account, "你好", msg_id="m1")
    new_session = await _inbound(rig, account, "/new", msg_id="m2")

    conn = rig.db.connect()
    try:
        stored = str(conn.execute(
            "SELECT external_chat_id FROM sessions WHERE id=?", (new_session,)
        ).fetchone()[0])
    finally:
        conn.close()
    assert stored.count(":") >= 2, "前置事实：/new 键追加时间戳"

    target = await _provider_for_session(rig, user.user_id, new_session)
    assert target is not None
    assert target.ref == "wx_ext_1"


async def test_provider_none_after_unbind(rig) -> None:
    rig, _, _ = make_channel_rig(rig.tmp_path)
    admin, user = _admin(rig), _user(rig)
    account = _register(rig, admin)
    binding = _bind(rig, admin, account, "wx_ext_1", user)
    session_id = await _inbound(rig, account, "你好")

    assert (await _provider_for_session(rig, user.user_id, session_id)) is not None
    rig.channels.repo.set_binding_status(binding.id, BINDING_DISABLED)
    assert await _provider_for_session(rig, user.user_id, session_id) is None, (
        "解绑后目标必须失效(fail-closed)"
    )


async def test_provider_none_after_rebind_to_other_owner(rig) -> None:
    rig, _, _ = make_channel_rig(rig.tmp_path)
    admin = _admin(rig)
    user_a, user_b = _user(rig), _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user_a)
    session_id = await _inbound(rig, account, "你好")

    _bind(rig, admin, account, "wx_ext_1", user_b)  # 换绑：同一 openid 归 B
    # 旧 run 的会话属于 A：绑定已不归 A→拒(不给 A 发给现在属于 B 的 openid)；
    # 该会话也不属于 B→按 owner 边界拒。换绑后的确认必须落到 B 自己的新会话。
    assert await _provider_for_session(rig, user_a.user_id, session_id) is None
    assert await _provider_for_session(rig, user_b.user_id, session_id) is None
    b_session = await _inbound(rig, account, "你好", msg_id="m2")
    target = await _provider_for_session(rig, user_b.user_id, b_session)
    assert target is not None and target.ref == "wx_ext_1"


async def test_provider_multi_account_isolation(rig) -> None:
    """同一外部用户在两个机器人账号下会话：目标解析按各会话路由的账号。"""
    rig, _, _ = make_channel_rig(rig.tmp_path)
    admin, user = _admin(rig), _user(rig)
    acct1 = _register(rig, admin, account_id="bot_1")
    acct2 = _register(rig, admin, account_id="bot_2")
    _bind(rig, admin, acct1, "wx_ext_1", user)
    _bind(rig, admin, acct2, "wx_ext_1", user)
    s1 = await _inbound(rig, acct1, "你好", msg_id="m1")
    s2 = await _inbound(rig, acct2, "你好", msg_id="m2")

    t1 = await _provider_for_session(rig, user.user_id, s1)
    t2 = await _provider_for_session(rig, user.user_id, s2)
    assert t1 is not None and t2 is not None
    assert t1.channel_account_id == acct1.id
    assert t2.channel_account_id == acct2.id
    assert t1.ref == t2.ref == "wx_ext_1"


async def test_provider_other_owner_session_denied(rig) -> None:
    rig, _, _ = make_channel_rig(rig.tmp_path)
    admin, user = _admin(rig), _user(rig)
    stranger = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)
    session_id = await _inbound(rig, account, "你好")
    assert await _provider_for_session(rig, stranger.user_id, session_id) is None
