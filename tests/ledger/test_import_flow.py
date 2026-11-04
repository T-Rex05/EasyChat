"""F4/F5：导入状态机、控制总额、去重、状态更新、退款与三口径统计的端到端测试。

所有账单由 tests/support/ledger_fixtures.py 生成（虚构商户/单号），
真实临时 SQLite + 临时文件目录，不触网、不用真实账单。
"""
from __future__ import annotations

import pytest

from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError
from tests.ledger.helpers import import_bill, make_ledger_rig, upload_bill
from tests.support.ledger_fixtures import (
    BillRow,
    full_refund_scenario,
    mismatched_control_totals,
    overlap_export_scenario,
    standard_scenario,
    status_update_scenario,
    write_wechat_csv,
    write_wechat_xlsx,
)


def _rows(rig, sql: str, params=()):
    conn = rig.db.connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _plan(basis: str, *, start="2026-10-01", end="2026-11-01", metrics=None, **extra):
    plan = {
        "version": 1, "basis": basis,
        "metrics": metrics or ["expense", "income", "refund_received", "net"],
        "period": {"start": start, "end_exclusive": end},
        "output": "summary",
    }
    plan.update(extra)
    return plan


def _metric(result, name: str) -> int | None:
    for item in result.metrics:
        if item.name == name:
            return item.amount_minor
    raise AssertionError(f"缺少指标 {name}")


# ---- 迁移与基本导入 -------------------------------------------------------------


async def test_migration_0012_creates_ledger_tables(tmp_path):
    from backend.platform.sqlite import Database

    db = Database(tmp_path / "data" / "app.db")
    db.migrate()
    conn = db.connect()
    try:
        names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        indexes = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    finally:
        conn.close()
    for table in (
        "ledger_accounts", "ledger_imports", "ledger_source_rows",
        "ledger_transactions", "ledger_transaction_sources", "ledger_refund_links",
        "ledger_categories", "ledger_category_rules", "ledger_changes", "ledger_analyses",
    ):
        assert table in names
    assert "uq_ledger_tx_identity" not in indexes  # 唯一约束建在表内
    assert "idx_tx_owner_time" in indexes


async def test_standard_xlsx_parse_and_commit(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "微信支付账单.xlsx", standard_scenario())
        view, _saved = await import_bill(rig, principal, path)
        assert view.state == "validated", view
        summary = rig.ledger.import_summary(principal, view.import_id)
        assert summary["rows"] == 4
        assert summary["totals"]["expense_minor"] == 15000
        assert summary["totals"]["income_minor"] == 3000
        assert summary["totals"]["neutral_minor"] == 20000
        assert summary["control"]["checked"] is True
        assert summary["control"]["ok"] is True

        result = rig.ledger.commit_import(
            principal, view.import_id, request_id="req-1",
        )
        assert result.inserted == 4
        assert result.state == "committed"
        assert len(_rows(rig, "SELECT * FROM ledger_transactions")) == 4

        again = rig.ledger.commit_import(principal, view.import_id, request_id="req-1")
        assert again.duplicate is True
        assert len(_rows(rig, "SELECT * FROM ledger_transactions")) == 4
        with pytest.raises(InvalidInputError):
            rig.ledger.commit_import(principal, view.import_id, request_id="req-2")
    finally:
        await rig.aclose()


async def test_control_total_mismatch_blocks_commit_until_confirmed(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        rows = standard_scenario()
        path = write_wechat_xlsx(
            tmp_path / "bills" / "错账.xlsx", rows,
            control_totals=mismatched_control_totals(),
        )
        view, _ = await import_bill(rig, principal, path)
        assert view.state == "needs_review"
        assert view.quality["control"]["ok"] is False
        with pytest.raises(InvalidInputError, match="控制总额"):
            rig.ledger.commit_import(principal, view.import_id)
        result = rig.ledger.commit_import(
            principal, view.import_id, confirm_mismatch=True,
        )
        assert result.inserted == 4
    finally:
        await rig.aclose()


async def test_bad_rows_are_reported_not_dropped(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        rows = (
            BillRow(occurred="2026-10-02 12:00:00", amount="12.00",
                    tx_id="OK00000000000000000000000001"),
            BillRow(occurred="不是时间", amount="abc", tx_id="BAD0000000000000000000000001"),
        )
        path = write_wechat_xlsx(tmp_path / "bills" / "坏行.xlsx", rows, control_totals={})
        view, _ = await import_bill(rig, principal, path)
        assert view.state == "needs_review"
        summary = rig.ledger.import_summary(principal, view.import_id)
        assert summary["error_rows"] >= 1
        assert summary["errors"]
        result = rig.ledger.commit_import(principal, view.import_id, confirm_mismatch=True)
        assert result.skipped >= 1
        assert result.inserted == 1
    finally:
        await rig.aclose()


async def test_overlapping_exports_do_not_double_count(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        rows = overlap_export_scenario()
        # 第一份只含第 1 笔；第二份含全部 2 笔（重叠 1 笔 + 新增 1 笔），内容不同 → 不同文件
        path_a = write_wechat_xlsx(tmp_path / "bills" / "九月.xlsx", rows[:1],
                                   control_totals={})
        path_b = write_wechat_xlsx(tmp_path / "bills" / "十月.xlsx", rows,
                                   control_totals={})
        view_a, _ = await import_bill(rig, principal, path_a)
        rig.ledger.commit_import(principal, view_a.import_id, confirm_mismatch=True)
        view_b, _ = await import_bill(rig, principal, path_b)
        assert view_b.coverage_kind in ("overlapping", "complete")
        result = rig.ledger.commit_import(principal, view_b.import_id, confirm_mismatch=True)
        # 第二份包含第一份的行：只新增 1 笔
        assert result.inserted == 1
        assert result.unchanged == 1
        total = len(_rows(rig, "SELECT * FROM ledger_transactions"))
        assert total == 2
    finally:
        await rig.aclose()


async def test_later_export_updates_status_without_duplicate(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        rows = status_update_scenario()
        path_paid = write_wechat_xlsx(tmp_path / "bills" / "paid.xlsx", rows[:1])
        path_refunded = write_wechat_csv(tmp_path / "bills" / "refunded.csv", rows)
        view_paid, _ = await import_bill(rig, principal, path_paid)
        rig.ledger.commit_import(principal, view_paid.import_id)
        view_refunded, _ = await import_bill(rig, principal, path_refunded)
        rig.ledger.commit_import(
            principal, view_refunded.import_id, confirm_mismatch=True,
        )
        transactions = _rows(rig, "SELECT * FROM ledger_transactions ORDER BY occurred_at")
        assert len(transactions) == 1
        assert transactions[0]["status_key"] in ("refunded_full", "refunded_partial")
        assert transactions[0]["verification"] in ("parsed", "candidate")
    finally:
        await rig.aclose()


# ---- 退款与三口径 ---------------------------------------------------------------


async def test_refund_linked_and_consumption_net_excludes_it(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "退款.xlsx", standard_scenario())
        view, _ = await import_bill(rig, principal, path)
        rig.ledger.commit_import(principal, view.import_id)
        links = _rows(rig, "SELECT * FROM ledger_refund_links")
        assert len(links) == 1
        assert links[0]["confirmation"] == "confirmed"
        assert links[0]["amount_minor"] == 3000
        assert links[0]["match_method"] == "note_reference"

        flow = rig.ledger.analyze(principal, _plan("statement_flow"))
        net = rig.ledger.analyze(principal, _plan("consumption_net"))
        cash = rig.ledger.analyze(principal, _plan("period_cash_outflow"))
        assert _metric(flow, "expense") == 15000  # 100 + 50，退款不冲减
        assert _metric(flow, "refund_received") == 3000
        assert _metric(net, "expense") == 12000  # 扣掉关联到本期消费的退款
        assert _metric(cash, "expense") == 12000
        assert flow.coverage.coverage_kind in ("complete", "partial")
    finally:
        await rig.aclose()


async def test_cross_period_refund_differs_between_bases(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        september = (
            BillRow(occurred="2026-09-30 20:00:00", amount="100.00",
                    tx_id="SEP00000000000000000000000001"),
        )
        october = (
            BillRow(occurred="2026-10-05 09:00:00", type="退款", direction="收入",
                    product="退款", amount="30.00", status="已退款",
                    tx_id="SEPRFD00000000000000000000001",
                    note="原交易单号 SEP00000000000000000000000001"),
            BillRow(occurred="2026-10-06 12:00:00", amount="50.00",
                    tx_id="OCT00000000000000000000000001"),
        )
        path_sep = write_wechat_xlsx(tmp_path / "bills" / "sep.xlsx", september,
                                     control_totals={})
        path_oct = write_wechat_xlsx(tmp_path / "bills" / "oct.xlsx", october,
                                     control_totals={})
        view_sep, _ = await import_bill(rig, principal, path_sep)
        rig.ledger.commit_import(principal, view_sep.import_id)
        view_oct, _ = await import_bill(rig, principal, path_oct)
        rig.ledger.commit_import(
            principal, view_oct.import_id, confirm_mismatch=True,
        )
        links = _rows(rig, "SELECT * FROM ledger_refund_links")
        assert len(links) == 1 and links[0]["confirmation"] == "confirmed"

        flow = rig.ledger.analyze(principal, _plan("statement_flow"))
        net = rig.ledger.analyze(principal, _plan("consumption_net"))
        cash = rig.ledger.analyze(principal, _plan("period_cash_outflow"))
        # 10 月账单内：# 支出 50；退款 30 到账（对应 9 月消费）
        assert _metric(flow, "expense") == 5000
        assert _metric(flow, "refund_received") == 3000
        assert _metric(flow, "net") == -2000
        # 消费净额：9 月消费不在本期，退款不冲减本期消费
        assert _metric(net, "expense") == 5000
        # 本期现金口径：退到账抵消本期流出
        assert _metric(cash, "expense") == 2000
    finally:
        await rig.aclose()


async def test_full_refund_scenario_consumption_net_is_zero(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "全退.xlsx",
                                 full_refund_scenario())
        view, _ = await import_bill(rig, principal, path)
        rig.ledger.commit_import(principal, view.import_id)
        net = rig.ledger.analyze(principal, _plan("consumption_net"))
        assert _metric(net, "expense") == 0
        assert _metric(net, "net") == 0
        flow = rig.ledger.analyze(principal, _plan("statement_flow"))
        assert _metric(flow, "expense") == 10000
        assert _metric(flow, "refund_received") == 10000
    finally:
        await rig.aclose()


async def test_manual_refund_link_respects_capacity(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "手工退款.xlsx", standard_scenario())
        view, _ = await import_bill(rig, principal, path)
        rig.ledger.commit_import(principal, view.import_id)
        transactions = _rows(rig, "SELECT * FROM ledger_transactions")
        original = next(t for t in transactions if t["event_role"] == "payment"
                        and t["amount_minor"] == 10000)
        refund = next(t for t in transactions if t["event_role"] == "refund")
        with pytest.raises(InvalidInputError):
            rig.ledger.link_refund(
                principal, refund_transaction_id=refund["id"],
                original_transaction_id=original["id"], amount_minor=12000,
            )
    finally:
        await rig.aclose()


# ---- 权限与隔离 -----------------------------------------------------------------


async def test_cross_owner_import_is_invisible(tmp_path):
    rig, owner = make_ledger_rig(tmp_path)
    try:
        other = rig.seed_user(role="user")
        path = write_wechat_xlsx(tmp_path / "bills" / "私有.xlsx", standard_scenario())
        view, _ = await import_bill(rig, owner, path)
        with pytest.raises(NotFoundError):
            rig.ledger.get_import(other, view.import_id)
        with pytest.raises(NotFoundError):
            rig.ledger.commit_import(other, view.import_id)
        assert rig.ledger.list_imports(other) == []
    finally:
        await rig.aclose()


async def test_ledger_import_requires_permission(tmp_path):
    rig, principal = make_ledger_rig(tmp_path, revokes=("ledger.import",))
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "无权限.xlsx", standard_scenario())
        saved = await upload_bill(rig, principal, path)
        with pytest.raises(ForbiddenError):
            await rig.ledger.register_import(principal, saved.file.file_id)
    finally:
        await rig.aclose()


async def test_ledger_view_denied_without_permission(tmp_path):
    rig, principal = make_ledger_rig(tmp_path, revokes=("ledger.view",))
    try:
        with pytest.raises(ForbiddenError):
            rig.ledger.list_transactions(principal)
        with pytest.raises(ForbiddenError):
            rig.ledger.analyze(principal, _plan("statement_flow"))
    finally:
        await rig.aclose()


# ---- QueryPlan 安全 -------------------------------------------------------------


async def test_analyze_rejects_model_supplied_sql(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        with pytest.raises(InvalidInputError):
            rig.ledger.analyze(
                principal, {**_plan("statement_flow"), "sql": "SELECT 1"},
            )
        with pytest.raises(InvalidInputError):
            rig.ledger.analyze(principal, _plan("gross_sum"))
        with pytest.raises(InvalidInputError):
            rig.ledger.analyze(principal, _plan("statement_flow", top_n=0))
    finally:
        await rig.aclose()


async def test_analyze_merchant_filter_is_parameterized(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "注入.xlsx", standard_scenario())
        view, _ = await import_bill(rig, principal, path)
        rig.ledger.commit_import(principal, view.import_id)
        result = rig.ledger.analyze(
            principal,
            _plan("statement_flow", filters={"merchants": ["x' OR 1=1 --"]}),
        )
        assert _metric(result, "expense") == 0
        assert result.transactions == ()
    finally:
        await rig.aclose()


# ---- 图片候选 ------------------------------------------------------------------


async def test_image_candidate_requires_review_then_confirm(tmp_path):
    from backend.modules.files.contracts import SaveMetadata
    from tests.support.ledger_fixtures import fake_vision_payload, write_png

    rig, principal = make_ledger_rig(tmp_path)
    try:
        png = write_png(tmp_path / "shot.png")
        saved = await rig.files.save_stream(
            principal, [png.read_bytes()],
            SaveMetadata(original_name="shot.png", declared_mime="image/png"),
        )
        candidate = await rig.ledger.save_image_candidate(
            principal, saved.file.file_id,
            fake_vision_payload(amount=None, direction=None),
        )
        assert candidate["amount_minor"] is None
        assert "amount" in candidate["missing_fields"]
        with pytest.raises(InvalidInputError):
            rig.ledger.confirm_image_candidate(principal, candidate["extraction_id"])

        confirmed = rig.ledger.confirm_image_candidate(
            principal, candidate["extraction_id"],
            corrections={"amount": "23.50", "direction": "expense",
                         "occurred_at": "2026-10-02 12:00:00"},
        )
        transaction = confirmed["transaction"]
        assert transaction.amount_minor == 2350
        assert transaction.verification == "confirmed"
        assert transaction.direction == "expense"
    finally:
        await rig.aclose()


async def test_high_confidence_image_still_needs_explicit_confirm(tmp_path):
    from backend.modules.files.contracts import SaveMetadata
    from tests.support.ledger_fixtures import fake_vision_payload, write_png

    rig, principal = make_ledger_rig(tmp_path)
    try:
        png = write_png(tmp_path / "shot2.png")
        saved = await rig.files.save_stream(
            principal, [png.read_bytes()],
            SaveMetadata(original_name="shot2.png", declared_mime="image/png"),
        )
        candidate = await rig.ledger.save_image_candidate(
            principal, saved.file.file_id, fake_vision_payload(),
        )
        assert candidate["needs_review"] is False
        assert _rows(rig, "SELECT * FROM ledger_transactions") == []
        rig.ledger.confirm_image_candidate(principal, candidate["extraction_id"])
        rows = _rows(rig, "SELECT * FROM ledger_transactions")
        assert len(rows) == 1 and rows[0]["amount_minor"] == 2350
    finally:
        await rig.aclose()


# ---- 批次维护 ------------------------------------------------------------------


async def test_delete_uncommitted_import_unlinks_file_but_keeps_content(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "临时.xlsx", standard_scenario())
        view, saved = await import_bill(rig, principal, path)
        result = rig.ledger.delete_import(principal, view.import_id)
        assert result["removed_rows"] == 4
        with pytest.raises(NotFoundError):
            rig.ledger.get_import(principal, view.import_id)
        still = rig.files.get(principal, saved.file.file_id)
        assert still.status == "ready"
        assert rig.files.reference_counts(principal, saved.file.file_id).get("import", 0) == 0
    finally:
        await rig.aclose()


async def test_committed_import_cannot_be_deleted(tmp_path):
    rig, principal = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "已提交.xlsx", standard_scenario())
        view, _ = await import_bill(rig, principal, path)
        rig.ledger.commit_import(principal, view.import_id)
        with pytest.raises(InvalidInputError):
            rig.ledger.delete_import(principal, view.import_id)
    finally:
        await rig.aclose()
