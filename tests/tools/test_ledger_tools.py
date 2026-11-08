"""账本工具：金额格式化、权限、无提交工具、async handler 与 owner 隔离。"""
from __future__ import annotations

import inspect

import pytest

from backend.runtime.hermes.tools import _make_handler
from backend.shared.tool_context import ToolContext, bind, config_with
from backend.tools.business.ledger_tools import build_ledger_tools, format_minor
from tests.ledger.helpers import make_ledger_rig, upload_bill
from tests.support.ledger_fixtures import standard_scenario, write_wechat_csv


def _tools(rig):
    return {item.name: item for item in build_ledger_tools(ledger=rig.ledger)}


def test_amount_format_without_model_math() -> None:
    assert format_minor(123456) == "¥1,234.56"
    assert format_minor(-5) == "-¥0.05"
    assert format_minor(None) == "—"


def test_no_commit_tool_exposed(rig) -> None:
    rig, _user = make_ledger_rig(rig.tmp_path)
    names = set(_tools(rig))
    assert names == {
        "ledger_import_preview", "ledger_analyze", "ledger_correct_transaction",
        "ledger_make_report", "ledger_refund_suggestions",
    }
    assert not any("commit" in name for name in names)


@pytest.mark.asyncio
async def test_preview_returns_full_import_id_and_amount_text(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path)
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    saved = await upload_bill(rig, user, path)
    tools = _tools(rig)
    context = ToolContext(principal=user, source="wechat")
    result = await tools["ledger_import_preview"].ainvoke(
        {"file_id": saved.file.file_id}, config=config_with(context)
    )
    assert "error" not in result
    import_id = result["import"]["import_id"]
    assert import_id.startswith("lim_")
    assert f"/账单确认 {import_id}" in result["message"]
    assert any(key.endswith("_text") for key in result["totals"])


@pytest.mark.asyncio
async def test_permission_denied_is_readable(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path, revokes=("ledger.view",))
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    saved = await upload_bill(rig, user, path)
    tools = _tools(rig)
    result = await tools["ledger_import_preview"].ainvoke(
        {"file_id": saved.file.file_id}, config=config_with(ToolContext(principal=user))
    )
    assert "error" in result
    assert "权限" in result["error"]


@pytest.mark.asyncio
async def test_async_handler_awaits_and_has_tool_context_in_config_only(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path)
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    saved = await upload_bill(rig, user, path)
    tool = _tools(rig)["ledger_import_preview"]
    handler = _make_handler(tool, lambda: "thread-x")
    # 同步工厂在返回 coroutine 前解析身份；外层 is_async=True 仍由运行时 await。
    assert not inspect.iscoroutinefunction(handler)
    # 模拟 _run_async 新线程：contextvar 清空，仅 config 携带身份
    context = ToolContext(principal=user, source="wechat")
    pending = handler({"file_id": saved.file.file_id}, config=config_with(context))
    assert inspect.isawaitable(pending)
    result = await pending
    assert "import" in result


@pytest.mark.asyncio
async def test_contextvar_fallback_when_config_missing(rig) -> None:
    rig, user = make_ledger_rig(rig.tmp_path)
    path = write_wechat_csv(rig.tmp_path / "bill.csv", standard_scenario())
    saved = await upload_bill(rig, user, path)
    tool = _tools(rig)["ledger_import_preview"]
    with bind(ToolContext(principal=user, source="wechat")):
        result = await tool.ainvoke({"file_id": saved.file.file_id})
    assert "import" in result


@pytest.mark.asyncio
async def test_internal_error_does_not_leak_exception_text() -> None:
    from types import SimpleNamespace

    class Boom:
        def refund_suggestions(self, *args, **kwargs):
            raise RuntimeError("sqlite3.OperationalError: SELECT * FROM bills secret")

    tools = {
        item.name: item for item in build_ledger_tools(ledger=Boom())
    }
    context = ToolContext(
        principal=SimpleNamespace(user_id=1, role="user", permission_revision=1),
        source="wechat",
    )
    result = await tools["ledger_refund_suggestions"].ainvoke(
        {}, config=config_with(context)
    )
    assert result["error"] == "账本操作失败，请稍后再试"
    assert "sqlite" not in result["error"]
    assert "secret" not in result["error"]


@pytest.mark.asyncio
async def test_missing_identity_is_error_not_default_user(rig) -> None:
    rig, _user = make_ledger_rig(rig.tmp_path)
    tool = _tools(rig)["ledger_refund_suggestions"]
    result = await tool.ainvoke({})
    assert "error" in result
    assert "身份" in result["error"]
