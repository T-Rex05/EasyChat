"""`/账单确认`：完整 ID、owner、权限、控制总额、消息幂等，不经过模型。"""
from __future__ import annotations

import pytest

from backend.modules.channels.commands import CommandServices, WeChatCommands
from backend.modules.channels.contracts import InboundMessage
from backend.modules.ledger.contracts import IMPORT_COMMITTED
from tests.ledger.helpers import make_ledger_rig, upload_bill
from tests.support.ledger_fixtures import (
    mismatched_control_totals,
    standard_scenario,
    write_wechat_csv,
    write_wechat_xlsx,
)


def _msg(event_id: str = "msg-1", text: str = "") -> InboundMessage:
    return InboundMessage(
        platform="wechat", account_pk="chn_1", external_account_id="bot",
        external_user_id="wx_u", external_chat_id="chat",
        external_event_id=event_id, text=text,
    )


def _commands(ledger) -> WeChatCommands:
    return WeChatCommands(CommandServices(ledger=ledger))


async def _imported(rig, user, path, *, parse=True):
    saved = await upload_bill(rig, user, path)
    return await rig.ledger.register_import(user, saved.file.file_id, parse_now=parse)


@pytest.mark.asyncio
async def test_confirm_submits_and_duplicate_message_is_idempotent(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path, grants=("ledger.import",))
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    view = await _imported(rig, user, path)
    commands = _commands(rig.ledger)
    text = f"/账单确认 {view.import_id}"
    first = await commands.handle(user, _msg("msg-42", text), "")
    assert first is not None
    assert "已导入" in first[0]
    assert "Web 账本页" in first[0]

    second = await commands.handle(user, _msg("msg-42", text), "")
    assert second is not None
    assert ("已经提交过" in second[0]) or ("已经提交" in second[0])


@pytest.mark.asyncio
async def test_bare_bill_alias_does_not_trigger_confirmation(rig) -> None:
    _rig, user = make_ledger_rig(rig.tmp_path, grants=("ledger.import",))
    commands = _commands(_rig.ledger)
    assert await commands.handle(user, _msg(text="/账单"), "") is None


@pytest.mark.asyncio
async def test_other_owner_cannot_confirm(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path, grants=("ledger.import",))
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    view = await _imported(rig, user, path)
    other = rig.seed_user(grants=("ledger.import",))
    result = await _commands(rig.ledger).handle(
        other, _msg(text=f"/账单确认 {view.import_id}"), ""
    )
    assert result is not None and "失败" in result[0]
    conn = rig.db.connect()
    try:
        state = conn.execute(
            "SELECT state FROM ledger_imports WHERE id=?", (view.import_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert state != IMPORT_COMMITTED


@pytest.mark.asyncio
async def test_control_mismatch_requires_explicit_force(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path, grants=("ledger.import", "ledger.view"))
    path = write_wechat_xlsx(
        rig.tmp_path / "bill.xlsx", standard_scenario(),
        control_totals=mismatched_control_totals(),
    )
    view = await _imported(rig, user, path)
    commands = _commands(rig.ledger)
    refused = await commands.handle(user, _msg("m1", f"/账单确认 {view.import_id}"), "")
    assert refused is not None
    assert "强制" in refused[0]
    accepted = await commands.handle(
        user, _msg("m2", f"/账单确认 {view.import_id} 强制"), ""
    )
    assert accepted is not None and "已导入" in accepted[0]


@pytest.mark.asyncio
async def test_prefix_id_rejected_without_lookup(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path, grants=("ledger.import",))
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    view = await _imported(rig, user, path)
    result = await _commands(rig.ledger).handle(
        user, _msg(text=f"/账单确认 {view.import_id[:12]}"), ""
    )
    assert result is not None
    assert "完整" in result[0]


@pytest.mark.asyncio
async def test_permission_denied(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path, grants=("ledger.import",))
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    view = await _imported(rig, user, path)
    rig.access.repo.set_user_permission(user.user_id, "ledger.import", False)
    rig.access.invalidate_all()
    result = await _commands(rig.ledger).handle(
        user, _msg(text=f"/账单确认 {view.import_id}"), ""
    )
    assert result is not None and "权限" in result[0]


@pytest.mark.asyncio
async def test_bad_third_arg_rejected(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path, grants=("ledger.import",))
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    view = await _imported(rig, user, path)
    result = await _commands(rig.ledger).handle(
        user, _msg(text=f"/账单确认 {view.import_id} yes"), ""
    )
    assert result is not None and "强制" in result[0]
