"""F7：分类、规则、手工修正、软删除与审计（真实 SQLite）。"""
from __future__ import annotations

import pytest

from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError
from tests.ledger.helpers import import_bill, make_ledger_rig
from tests.support.ledger_fixtures import standard_scenario, write_wechat_xlsx


async def _committed(rig, principal, tmp_path, name="rules.xlsx"):
    path = write_wechat_xlsx(tmp_path / "bills" / name, standard_scenario())
    view, _ = await import_bill(rig, principal, path)
    rig.ledger.commit_import(principal, view.import_id)
    return view


def _rows(rig, sql, params=()):
    conn = rig.db.connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


async def test_category_crud_and_duplicate_name(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        category = rig.ledger.create_category(user, name="餐饮", kind="expense")
        assert category["name"] == "餐饮"
        with pytest.raises(InvalidInputError):
            rig.ledger.create_category(user, name="餐饮")
        renamed = rig.ledger.rename_category(user, category["id"], name="餐饮美食")
        assert renamed["name"] == "餐饮美食"
        assert len(rig.ledger.list_categories(user)) == 1
        assert rig.ledger.delete_category(user, category["id"])["deleted"] is True
        with pytest.raises(NotFoundError):
            rig.ledger.delete_category(user, category["id"])
    finally:
        await rig.aclose()


async def test_category_requires_manage_permission(tmp_path):
    rig, user = make_ledger_rig(tmp_path)  # 普通用户没有被授予 ledger.manage
    try:
        with pytest.raises(ForbiddenError):
            rig.ledger.create_category(user, name="餐饮")
        with pytest.raises(ForbiddenError):
            rig.ledger.create_rule(
                user, category_id="lct_x", match_value="便利店",
            )
    finally:
        await rig.aclose()


async def test_rule_applies_only_to_uncategorized_and_respects_priority(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _committed(rig, user, tmp_path)
        food = rig.ledger.create_category(user, name="餐饮")
        wide = rig.ledger.create_category(user, name="便利店")
        rig.ledger.create_rule(
            user, category_id=food["id"], match_value="示例", priority=10,
        )
        rig.ledger.create_rule(
            user, category_id=wide["id"], match_value="示例便利店", priority=1,
        )
        result = rig.ledger.apply_rules(user)
        # 只有能匹配到规则的行被处理；优先级数字小的先匹配
        assert result["matched"] == 3
        transactions = rig.ledger.list_transactions(user)
        by_amount = {t.amount_minor: t for t in transactions}
        assert by_amount[10000].category_id == wide["id"]  # 优先级 1 的规则先命中
        assert by_amount[20000].category_id is None  # 零钱充值不匹配任何规则
        assert len({t.category_id for t in transactions if t.category_id}) == 2

        # 再次套用不会覆盖已分类
        again = rig.ledger.apply_rules(user)
        assert again["matched"] == 0
    finally:
        await rig.aclose()


async def test_rule_validation_rejects_unknown_field_and_op(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        category = rig.ledger.create_category(user, name="餐饮")
        with pytest.raises(InvalidInputError):
            rig.ledger.create_rule(
                user, category_id=category["id"], match_value="x", match_field="sql",
            )
        with pytest.raises(InvalidInputError):
            rig.ledger.create_rule(
                user, category_id=category["id"], match_value="x", match_op="regex",
            )
        with pytest.raises(InvalidInputError):
            rig.ledger.create_rule(user, category_id=category["id"], match_value="   ")
        with pytest.raises(NotFoundError):
            rig.ledger.create_rule(user, category_id="lct_missing", match_value="x")
    finally:
        await rig.aclose()


async def test_update_transaction_writes_audit_change(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _committed(rig, user, tmp_path)
        category = rig.ledger.create_category(user, name="餐饮")
        target = next(t for t in rig.ledger.list_transactions(user) if t.amount_minor == 10000)
        before_revision = target.revision
        detail = rig.ledger.update_transaction(
            user, target.transaction_id, category_id=category["id"],
            merchant="手工改正的商户", note="对账", reason="核对小票",
        )
        assert detail["transaction"].category_id == category["id"]
        assert detail["transaction"].merchant == "手工改正的商户"
        assert detail["transaction"].revision == before_revision + 1
        changes = _rows(
            rig, "SELECT * FROM ledger_changes WHERE entity='transaction' ORDER BY created_at",
        )
        assert len(changes) == 1
        assert changes[0]["entity"] == "transaction"
        assert changes[0]["reason"] == "核对小票"
        assert "category_id" in changes[0]["change"]

        # 分类被使用时不允许删除
        with pytest.raises(InvalidInputError):
            rig.ledger.delete_category(user, category["id"])
        # 清空分类后可以删除
        rig.ledger.update_transaction(user, target.transaction_id, category_id="")
        assert rig.ledger.delete_category(user, category["id"])["deleted"] is True
    finally:
        await rig.aclose()


async def test_update_transaction_requires_fields_and_edit_permission(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _committed(rig, user, tmp_path)
        target = rig.ledger.list_transactions(user)[0]
        with pytest.raises(InvalidInputError):
            rig.ledger.update_transaction(user, target.transaction_id)
        with pytest.raises(NotFoundError):
            rig.ledger.update_transaction(user, "ltx_missing", note="x")
    finally:
        await rig.aclose()


async def test_update_transaction_denied_without_edit_permission(tmp_path):
    rig, user = make_ledger_rig(tmp_path, revokes=("ledger.edit",))
    try:
        await _committed(rig, user, tmp_path)
        target = rig.ledger.list_transactions(user)[0]
        with pytest.raises(ForbiddenError):
            rig.ledger.update_transaction(user, target.transaction_id, note="x")
        with pytest.raises(ForbiddenError):
            rig.ledger.delete_transaction(user, target.transaction_id)
    finally:
        await rig.aclose()


async def test_soft_delete_hides_transaction_from_list_and_metrics(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _committed(rig, user, tmp_path)
        target = next(t for t in rig.ledger.list_transactions(user) if t.amount_minor == 5000)
        result = rig.ledger.delete_transaction(user, target.transaction_id, reason="重复行")
        assert result["deleted"] is True
        remaining = rig.ledger.list_transactions(user)
        assert all(t.transaction_id != target.transaction_id for t in remaining)
        with pytest.raises(NotFoundError):
            rig.ledger.get_transaction(user, target.transaction_id)
        with pytest.raises(InvalidInputError):
            rig.ledger.delete_transaction(user, target.transaction_id)

        plan = {
            "version": 1, "basis": "statement_flow",
            "metrics": ["expense"],
            "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
            "output": "summary",
        }
        result = rig.ledger.analyze(user, plan)
        metrics = {m.name: m.amount_minor for m in result.metrics}
        assert metrics["expense"] == 10000  # 50 元那笔已删除
    finally:
        await rig.aclose()


async def test_analyze_group_by_and_category_filter(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _committed(rig, user, tmp_path)
        category = rig.ledger.create_category(user, name="餐饮")
        target = next(t for t in rig.ledger.list_transactions(user) if t.amount_minor == 10000)
        rig.ledger.update_transaction(user, target.transaction_id, category_id=category["id"])

        plan = {
            "version": 1, "basis": "statement_flow",
            "metrics": ["expense"],
            "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
            "group_by": ["merchant"], "output": "table", "top_n": 2,
        }
        result = rig.ledger.analyze(user, plan)
        assert 1 <= len(result.groups) <= 2
        assert all("bucket1" in group and "expense_minor" in group for group in result.groups)
        assert len(result.transactions) <= 50

        filtered = rig.ledger.analyze(
            user,
            {
                **plan,
                "filters": {"category_ids": [category["id"]]},
                "output": "summary",
            },
        )
        metrics = {m.name: m.amount_minor for m in filtered.metrics}
        assert metrics["expense"] == 10000
        assert filtered.coverage.category_names == ("餐饮",)
    finally:
        await rig.aclose()


async def test_analysis_is_persisted_and_listed(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        plan = {
            "version": 1, "basis": "statement_flow", "metrics": ["expense"],
            "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
        }
        first = rig.ledger.analyze(user, plan, request_id="same")
        second = rig.ledger.analyze(user, plan, request_id="same")
        assert first.analysis_id != second.analysis_id  # 每次都留痕，不做隐式去重
        listed = rig.ledger.list_analyses(user)
        assert len(listed) == 2
        stored = rig.ledger.get_analysis(user, first.analysis_id)
        assert stored["query_plan"]["basis"] == "statement_flow"
        other = rig.seed_user(role="user")
        with pytest.raises(NotFoundError):
            rig.ledger.get_analysis(other, first.analysis_id)
        assert rig.ledger.list_analyses(other) == []
    finally:
        await rig.aclose()


async def test_empty_ledger_metrics_are_zero_with_unknown_coverage(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        result = rig.ledger.analyze(
            user,
            {
                "version": 1, "basis": "consumption_net", "metrics": ["expense", "net"],
                "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
            },
        )
        assert {m.name: m.amount_minor for m in result.metrics} == {"expense": 0, "net": 0}
        assert result.coverage.coverage_kind == "unknown"
        assert result.coverage.notes  # 明确提示没有可用账单
    finally:
        await rig.aclose()
