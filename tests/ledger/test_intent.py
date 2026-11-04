"""F9：意图路由与工具面（模型只理解/翻译，金额与 SQL 全由受控代码负责）。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.modules.ledger.intent import (
    INTENT_CORRECT,
    INTENT_IMPORT,
    INTENT_QUERY,
    INTENT_REPORT,
    INTENT_REVIEW_REFUND,
    INTENT_UNKNOWN,
    classify,
    plan_from_text,
)
from backend.modules.files.contracts import SaveMetadata
from backend.modules.ledger.tools import TOOL_NAMES, LedgerToolbox, handle_message
from backend.shared.errors import InvalidInputError
from tests.ledger.helpers import import_bill, make_ledger_rig
from tests.support.ledger_fixtures import standard_scenario, write_wechat_xlsx

NOW = datetime(2026, 11, 4, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_classify_common_intents():
    assert classify("帮我把这个账单导入一下").intent == INTENT_IMPORT
    assert classify("这张截图存一下").intent == INTENT_IMPORT
    assert classify("上个月吃饭花了多少").intent == INTENT_QUERY
    assert classify("帮我核对一下退款").intent == INTENT_REVIEW_REFUND
    assert classify("这笔记错了，改成餐饮").intent == INTENT_CORRECT
    assert classify("生成一份十月的消费报告").intent == INTENT_REPORT
    assert classify("把账单导入").intent == INTENT_IMPORT
    assert classify("导入这个文件", has_files=True).intent == INTENT_IMPORT


def test_classify_unknown_asks_for_clarification():
    decision = classify("今天天气怎么样")
    assert decision.intent == INTENT_UNKNOWN
    assert decision.needs_clarification is True
    assert decision.question


def test_plan_from_text_periods_and_basis():
    upper = plan_from_text("上个月一共花了多少", now=NOW)
    assert upper["period"] == {"start": "2026-10-01", "end_exclusive": "2026-11-01"}
    assert upper["basis"] == "consumption_net"
    assert "expense" in upper["metrics"] and "net" in upper["metrics"]

    this_month = plan_from_text("本月支出统计", now=NOW)
    assert this_month["period"]["start"] == "2026-11-01"
    assert this_month["period"]["end_exclusive"] == "2026-12-01"

    recent = plan_from_text("最近7天花了多少", now=NOW)
    assert recent["period"] == {"start": "2026-10-29", "end_exclusive": "2026-11-05"}

    year = plan_from_text("今年消费按分类", now=NOW)
    assert year["period"] == {"start": "2026-01-01", "end_exclusive": "2026-11-05"}
    assert year["group_by"] == ["category"]
    assert year["output"] == "table"

    explicit = plan_from_text("2026年9月账单流水", now=NOW)
    assert explicit["period"] == {"start": "2026-09-01", "end_exclusive": "2026-10-01"}
    assert explicit["basis"] == "statement_flow"

    cash = plan_from_text("上个月实际支出多少", now=NOW)
    assert cash["basis"] == "period_cash_outflow"


def test_plan_from_text_defaults_when_no_time_mentioned():
    plan = plan_from_text("我花了多少", now=NOW)
    assert plan["period"]["start"] == "2026-11-01"  # 默认本月，需由上层提示
    assert plan["version"] == 1


class FakePlanner:
    def __init__(self, plan):
        self.plan_value = plan
        self.calls = 0

    async def plan(self, text, *, schema_hint):
        self.calls += 1
        return self.plan_value


class BrokenPlanner:
    async def plan(self, text, *, schema_hint):
        raise RuntimeError("模型超时")


async def test_planner_output_with_sql_is_rejected_not_executed(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        rig.ledger.clock = lambda: NOW
        planner = FakePlanner({
            "version": 1, "basis": "statement_flow", "metrics": ["expense"],
            "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
            "sql": "SELECT * FROM ledger_transactions",
        })
        with pytest.raises(InvalidInputError):
            await handle_message(rig.ledger, user, "上个月花了多少", planner=planner)
        assert planner.calls == 1
        # analyze 白名单校验拒绝未知字段：没有执行任何模型给出的 SQL
    finally:
        await rig.aclose()


async def test_planner_failure_is_reported(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        rig.ledger.clock = lambda: NOW
        with pytest.raises(InvalidInputError):
            await handle_message(rig.ledger, user, "上个月花了多少", planner=BrokenPlanner())
    finally:
        await rig.aclose()


async def test_tool_specs_are_structured_and_do_not_expose_sql(tmp_path):
    rig, _user = make_ledger_rig(tmp_path)
    try:
        toolbox = LedgerToolbox(rig.ledger)
        specs = toolbox.specs()
        assert {spec["name"] for spec in specs} == set(TOOL_NAMES)
        for spec in specs:
            properties = spec["parameters"].get("properties", {})
            assert "sql" not in properties and "python" not in properties
            plan_props = properties.get("plan", {}).get("properties", {})
            assert "sql" not in plan_props and "code" not in plan_props
        assert "commit" not in {spec["name"] for spec in specs}  # 提交必须人工确认
        with pytest.raises(InvalidInputError):
            await toolbox.call(None, "ledger_drop_table", {})
    finally:
        await rig.aclose()


async def test_analyze_tool_computes_amounts_server_side(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "tool.xlsx", standard_scenario())
        view, _ = await import_bill(rig, user, path)
        rig.ledger.commit_import(user, view.import_id)
        toolbox = LedgerToolbox(rig.ledger)
        result = await toolbox.call(
            user, "ledger_analyze",
            {"plan": {
                "version": 1, "basis": "consumption_net",
                "metrics": ["expense", "net"],
                "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
            }},
        )
        metrics = {m["name"]: m["amount_minor"] for m in result["metrics"]}
        assert metrics == {"expense": 12000, "net": -12000}
        assert result["analysis_id"].startswith("lan_")
        assert result["evidence"]
    finally:
        await rig.aclose()


async def test_import_tool_previews_without_committing(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "preview.xlsx", standard_scenario())
        handle = await rig.files.save_stream(
            user, [path.read_bytes()],
            SaveMetadata(original_name="preview.xlsx", declared_mime=""),
        )
        toolbox = LedgerToolbox(rig.ledger)
        summary = await toolbox.call(
            user, "ledger_import_preview", {"file_id": handle.file.file_id},
        )
        assert summary["requires_user_confirmation"] is True
        assert summary["rows"] == 4
        assert summary["import"]["state"] == "validated"
        transactions = rig.ledger.list_transactions(user)
        assert transactions == []  # 预览不写交易
    finally:
        await rig.aclose()


async def test_handle_message_query_end_to_end(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        rig.ledger.clock = lambda: NOW
        path = write_wechat_xlsx(tmp_path / "bills" / "chat.xlsx", standard_scenario())
        view, _ = await import_bill(rig, user, path)
        rig.ledger.commit_import(user, view.import_id)
        result = await handle_message(rig.ledger, user, "上个月支出多少")
        assert result["intent"] == "analyze"
        metrics = {m["name"]: m["amount_minor"] for m in result["result"]["metrics"]}
        assert metrics["expense"] == 12000
        # 2026-10 与账单日期一致（账单在 2026-10），确认路由用了“相对本月”而不是硬编码
        assert result["result"]["coverage"]["start"] == "2026-10-01"
    finally:
        await rig.aclose()


async def test_handle_message_unknown_and_missing_file(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        unknown = await handle_message(rig.ledger, user, "你好")
        assert unknown["needs_clarification"] is True
        imp = await handle_message(rig.ledger, user, "帮我把这个账单导入")
        assert imp["needs_input"] == "file"
        correct = await handle_message(rig.ledger, user, "这笔记错了，改成餐饮")
        assert correct["needs_input"] == "transaction"
    finally:
        await rig.aclose()
