"""T5 持久 inbox：envelope 先落库、内部失败本地重放、毒消息 dead、游标安全。"""
from __future__ import annotations

import json
import uuid

import pytest

from backend.modules.channels.api import _message_from_envelope
from backend.modules.channels.contracts import (
    MAX_REPLAY_ATTEMPTS,
    PROCESSING_DEAD,
    PROCESSING_DONE,
    PROCESSING_FAILED,
)
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


def _mk_message(account, raw: dict):
    from backend.modules.channels.wechat.parser import parse_inbound

    message = parse_inbound(account, raw, now=1_000_000.0, fingerprint_window=5.0)
    assert message is not None
    return message


async def test_internal_failure_keeps_event_and_envelope_then_replays(rig) -> None:
    """P1 回归：内部失败不再删事件；本地重放成功后标记 done。"""
    channel_rig, _, _ = make_channel_rig(rig.tmp_path)
    service = channel_rig.channels
    admin, user = _admin(channel_rig), _user(channel_rig)
    account = _register(channel_rig, admin)
    _bind(channel_rig, admin, account, "wx_ext_1", user)

    original = service._process_event

    async def failing(_account, _message, _event_id):
        raise RuntimeError("内部存储故障")

    service._process_event = failing  # type: ignore[method-assign]
    outcome = await service.handle_inbound(
        _mk_message(account, text_message("你好", message_id="m1"))
    )
    assert outcome.accepted is False and outcome.reason == "internal"
    # 事件保留且带完整 envelope + failed 状态
    due = service.repo.due_replay_events(now=1_001_000.0, stale_pending_before=0, limit=10)
    assert len(due) == 1
    row = due[0]
    assert row["processing_state"] == PROCESSING_FAILED
    envelope = json.loads(row["envelope_json"])
    assert envelope["text"] == "你好"
    assert envelope["external_user_id"] == "wx_ext_1"

    # 恢复处理：本地重放成功
    service._process_event = original  # type: ignore[method-assign]
    replayed = await service.replay_due_events(now=1_001_000.0, limit=5)
    assert replayed == 1
    refreshed = service.repo.get_event(str(row["id"]))
    assert refreshed["processing_state"] == PROCESSING_DONE


async def test_poison_message_enters_dead_after_attempts(rig) -> None:
    channel_rig, _, _ = make_channel_rig(rig.tmp_path)
    service = channel_rig.channels
    admin, user = _admin(channel_rig), _user(channel_rig)
    account = _register(channel_rig, admin)
    _bind(channel_rig, admin, account, "wx_ext_1", user)

    async def failing(_account, _message, _event_id):
        raise RuntimeError("永久故障")

    service._process_event = failing  # type: ignore[method-assign]
    await service.handle_inbound(
        _mk_message(account, text_message("坏消息", message_id="m2"))
    )
    channel_rig.clock.advance(10_000)
    for _ in range(MAX_REPLAY_ATTEMPTS + 1):
        await service.replay_due_events(limit=5)
        channel_rig.clock.advance(10_000)
    # 重试耗尽：不再被重放捞起，进入可见 dead 状态
    assert service.repo.due_replay_events(
        now=channel_rig.clock(), stale_pending_before="", limit=10
    ) == []
    conn = channel_rig.db.connect()
    try:
        row = conn.execute(
            "SELECT processing_state, last_error FROM channel_events WHERE external_event_id=?",
            ("msg:wx_ext_1:m2",),
        ).fetchone()
    finally:
        conn.close()
    assert row["processing_state"] == PROCESSING_DEAD
    assert "永久故障" in str(row["last_error"])


async def test_envelope_roundtrip_and_legacy_rows_not_replayable(rig) -> None:
    channel_rig, _, _ = make_channel_rig(rig.tmp_path)
    service = channel_rig.channels
    admin, user = _admin(channel_rig), _user(channel_rig)
    account = _register(channel_rig, admin)
    _bind(channel_rig, admin, account, "wx_ext_1", user)
    await service.handle_inbound(
        _mk_message(account, text_message("带全文", message_id="m3"))
    )
    conn = channel_rig.db.connect()
    try:
        row = dict(conn.execute(
            "SELECT * FROM channel_events WHERE external_event_id=?", ("msg:wx_ext_1:m3",)
        ).fetchone())
    finally:
        conn.close()
    assert row["envelope_version"] == 1
    message = _message_from_envelope(row)
    assert message.text == "带全文"
    assert message.external_user_id == "wx_ext_1"
    assert message.account_pk == account.id
    # 历史行（无 envelope）不可重放
    with pytest.raises(ValueError):
        _message_from_envelope({"envelope_version": 0, "envelope_json": "{}"})


async def test_stale_pending_is_replayed_after_restart(rig) -> None:
    """停机遗留的 pending（received 未完成）：陈旧后被 replay 兜底。"""
    channel_rig, _, _ = make_channel_rig(rig.tmp_path)
    service = channel_rig.channels
    admin, user = _admin(channel_rig), _user(channel_rig)
    account = _register(channel_rig, admin)
    _bind(channel_rig, admin, account, "wx_ext_1", user)

    import asyncio as _asyncio

    original = service._process_event

    async def cancelled_mid(_account, _message, _event_id):
        raise _asyncio.CancelledError()

    service._process_event = cancelled_mid  # type: ignore[method-assign]
    with pytest.raises(_asyncio.CancelledError):
        await service.handle_inbound(
            _mk_message(account, text_message("停机时被取消", message_id="m4"))
        )
    # 事件保留（未删除），状态 pending；陈旧后重放成功
    conn = channel_rig.db.connect()
    try:
        row = conn.execute(
            "SELECT id, processing_state FROM channel_events WHERE external_event_id=?",
            ("msg:wx_ext_1:m4",),
        ).fetchone()
    finally:
        conn.close()
    assert row["processing_state"] == "pending"
    service._process_event = original  # type: ignore[method-assign]
    # 陈旧阈值走 service 内部计算（ISO 比较）；FakeClock 前推 20 分钟
    channel_rig.clock.advance(60 * 20)
    replayed = await service.replay_due_events(limit=5)
    assert replayed == 1


async def test_cursor_advances_and_batch_continues_after_internal_failure(rig) -> None:
    """核心丢失路径修复：批内第一条失败，游标仍推进，后续消息正常处理。"""
    channel_rig, transport, _ = make_channel_rig(rig.tmp_path)
    from backend.modules.channels.wechat.listener import WeChatListener

    service = channel_rig.channels
    admin, user = _admin(channel_rig), _user(channel_rig)
    account = _register(channel_rig, admin)
    _bind(channel_rig, admin, account, "wx_ext_1", user)
    channel_rig.runtime.script_events([])
    listener = WeChatListener(service, transport, clock=channel_rig.clock)
    # 第一批第一条让 submit 阶段抛错（消息文本触发 runtime 无事件 → 不抛，
    # 这里直接用 process_event 包装：第一条抛，第二条正常）
    original = service._process_event
    seen: list[str] = []

    async def flaky(_account, message, event_id):
        seen.append(message.text)
        if message.text == "第一条":
            raise RuntimeError("批内失败")
        return await original(_account, message, event_id)

    service._process_event = flaky  # type: ignore[method-assign]
    transport.script_updates({
        "ret": 0, "get_updates_buf": "cursor-1",
        "msgs": [text_message("第一条", message_id="m10"),
                 text_message("第二条", message_id="m11")],
    })
    processed = await listener.poll_once(account.id)
    assert processed == 2  # 批内两条都被处理（即使第一条失败）
    assert seen == ["第一条", "第二条"]
    # 游标推进成功（envelope 已持久化，本地重放兜底）
    refreshed = service.repo.get_account(account.id)
    assert refreshed.sync_cursor == "cursor-1"
    # 失败的事件在本地重放队列里
    due = service.repo.due_replay_events(now=1_001_000.0, stale_pending_before=0, limit=10)
    assert [json.loads(e["envelope_json"])["text"] for e in due] == ["第一条"]
