"""ledger QueryPlan 验证与参数化 SQL 编译测试（全部离线，不连数据库）。

断言都直接针对真实生成的 SQL 文本与参数元组，不 mock compile_plan，
以便发现“看起来能用、实际拼错列名/丢参数”的编译错误。
"""
from __future__ import annotations

import pytest

from backend.modules.ledger.contracts import (
    BASIS_CONSUMPTION_NET,
    BASIS_STATEMENT_FLOW,
    GROUP_BY_ACCOUNT,
    GROUP_BY_DAY,
    GROUP_BY_MERCHANT,
    GROUP_BY_MONTH,
    METRIC_EXPENSE,
    METRIC_INCOME,
    METRIC_REFUND_RECEIVED,
    OUTPUT_SUMMARY,
    OUTPUT_TABLE,
    QueryPlan,
)
from backend.modules.ledger.query import (
    MAX_TOP_N,
    CompiledQuery,
    compile_plan,
    escape_like,
    validate_plan,
)
from backend.shared.errors import InvalidInputError

NOW = "2026-11-04T20:00:00+08:00"


def _raw(**overrides):
    """一份最小合法计划，用例只覆盖自己关心的字段。"""
    raw = {
        "version": 1,
        "basis": BASIS_STATEMENT_FLOW,
        "metrics": [METRIC_EXPENSE, METRIC_INCOME],
        "scope": "all",
        "period": {
            "start": "2026-10-01",
            "end_exclusive": "2026-11-01",
            "timezone": "Asia/Shanghai",
        },
        "top_n": 20,
        "output": OUTPUT_SUMMARY,
    }
    raw.update(overrides)
    return raw


def _plan(**overrides) -> QueryPlan:
    return validate_plan(_raw(**overrides), now_iso=NOW)


def _compiled(**overrides) -> CompiledQuery:
    return compile_plan(_plan(**overrides), owner_id=1)


# ---- 合法计划 -------------------------------------------------------------------


def test_summary_plan_validates_and_compiles() -> None:
    plan = _plan()
    assert plan.version == 1
    assert plan.basis == BASIS_STATEMENT_FLOW
    assert plan.metrics == (METRIC_EXPENSE, METRIC_INCOME)
    assert plan.period.timezone == "Asia/Shanghai"
    assert plan.currency == "CNY"
    assert plan.data_cutoff == NOW

    compiled = _compiled()
    for sql, params in (
        (compiled.aggregate_sql, compiled.aggregate_params),
        (compiled.detail_sql, compiled.detail_params),
    ):
        assert "?" in sql
        assert params[0] == 1


def test_aggregate_has_six_metric_columns() -> None:
    compiled = _compiled()
    for column in (
        "expense_minor",
        "income_minor",
        "neutral_minor",
        "refund_received_minor",
        "refund_applied_minor",
        "tx_count",
    ):
        assert column in compiled.aggregate_sql
    # 单一 SQL：一个 CTE + 一组标量子查询，避免多次 round-trip
    assert compiled.aggregate_sql.count("WITH scope AS") == 1
    assert compiled.aggregate_sql.startswith("WITH scope AS (SELECT")


def test_month_group_plan_shape() -> None:
    compiled = _compiled(group_by=[GROUP_BY_MONTH], output=OUTPUT_TABLE)
    assert "substr(t.occurred_at,1,7)" in compiled.group_sql
    assert "substr(t.occurred_at,1,7) AS bucket1" in compiled.group_sql
    assert "GROUP BY 1,2" in compiled.group_sql
    assert "ORDER BY expense_minor DESC" in compiled.group_sql
    assert "LIMIT ?" in compiled.group_sql
    assert compiled.group_params[-1] == 20
    assert compiled.group_params[0] == 1
    assert "bucket2" in compiled.group_sql


def test_two_dimension_group_and_empty_group() -> None:
    two = _compiled(group_by=[GROUP_BY_MONTH, GROUP_BY_MERCHANT])
    assert "substr(t.occurred_at,1,7) AS bucket1" in two.group_sql
    assert "t.merchant AS bucket2" in two.group_sql

    none = _compiled()
    assert none.group_sql == ""
    assert none.group_params == ()
    assert any("未指定分组维度" in note for note in none.notes)

    account = _compiled(group_by=[GROUP_BY_ACCOUNT])
    assert "t.account_id AS bucket1" in account.group_sql


def test_table_output_detail_columns_and_order() -> None:
    compiled = _compiled(output=OUTPUT_TABLE)
    detail = compiled.detail_sql
    for column in (
        "t.id",
        "t.occurred_at",
        "t.merchant",
        "t.product",
        "t.amount_minor",
        "t.currency",
        "t.direction",
        "t.event_role",
        "t.status",
        "t.verification",
        "t.category_id",
    ):
        assert column in detail
    assert "ORDER BY t.occurred_at DESC, t.id DESC" in detail
    assert "t.deleted_at IS NULL" in detail


def test_scope_account_and_import_generate_dynamic_placeholders() -> None:
    account = _compiled(scope="account", account_ids=["acc-1", "acc-2"])
    assert "t.account_id IN (?,?)" in account.aggregate_sql
    assert account.aggregate_params == (1, "2026-10-01", "2026-11-01", "acc-1", "acc-2")

    imported = _compiled(scope="import", import_ids=["imp-1"])
    assert "EXISTS (SELECT 1 FROM ledger_transaction_sources AS s" in imported.aggregate_sql
    assert "s.transaction_id = t.id" in imported.aggregate_sql
    assert "s.import_id IN (?)" in imported.aggregate_sql
    assert imported.aggregate_params == (1, "2026-10-01", "2026-11-01", "imp-1")


def test_metrics_deduped_and_kept_in_order() -> None:
    plan = _plan(metrics=[METRIC_EXPENSE, METRIC_EXPENSE, METRIC_INCOME])
    assert plan.metrics == (METRIC_EXPENSE, METRIC_INCOME)


def test_period_keeps_iso_prefix_without_timezone_padding() -> None:
    compiled = _compiled()
    assert "2026-10-01" in compiled.aggregate_params
    assert "2026-11-01" in compiled.aggregate_params
    assert "t.occurred_at >= ?" in compiled.aggregate_sql
    assert "t.occurred_at < ?" in compiled.aggregate_sql
    # 不强行补 T00:00:00+08:00
    assert "2026-10-01T00:00:00" not in compiled.aggregate_sql

    # 带时刻/时区（含小数秒）的边界原样保留，只进参数
    precise = _compiled(
        period={
            "start": "2026-10-01T00:00:00.000+08:00",
            "end_exclusive": "2026-11-01T00:00:00+08:00",
            "timezone": "Asia/Shanghai",
        }
    )
    assert "2026-10-01T00:00:00.000+08:00" in precise.aggregate_params
    assert "2026-10-01T00:00:00.000+08:00" not in precise.aggregate_sql


def test_open_period_records_note() -> None:
    plan = _plan(period={})
    assert plan.period.start is None
    assert plan.period.end_exclusive is None
    assert any("未限定时间范围" in note for note in plan.unsupported_notes)
    compiled = compile_plan(plan, owner_id=7)
    assert "t.occurred_at >= ?" not in compiled.aggregate_sql
    assert compiled.aggregate_params == (7,)


# ---- 拒绝：白名单/枚举/上限 -------------------------------------------------------


@pytest.mark.parametrize("key", ["sql", "python", "code", "table"])
def test_reject_unknown_key(key: str) -> None:
    with pytest.raises(InvalidInputError, match=f"不支持的查询计划字段: {key}"):
        _plan(**{key: "SELECT 1"})


def test_reject_unknown_nested_key() -> None:
    with pytest.raises(InvalidInputError, match="不支持的查询计划字段: period.year"):
        _plan(period={"start": "2026-10-01", "year": 2026})
    with pytest.raises(InvalidInputError, match="不支持的查询计划字段: filters.owner_id"):
        _plan(filters={"owner_id": 2})


def test_reject_version_two() -> None:
    with pytest.raises(InvalidInputError, match="不支持的查询计划版本"):
        _plan(version=2)
    with pytest.raises(InvalidInputError, match="不支持的查询计划版本"):
        _plan(version=True)


def test_reject_unknown_basis() -> None:
    with pytest.raises(InvalidInputError, match="不支持的统计口径"):
        _plan(basis="gross")
    assert _plan(basis=BASIS_CONSUMPTION_NET).basis == BASIS_CONSUMPTION_NET


def test_reject_empty_metrics_and_unknown_metric() -> None:
    with pytest.raises(InvalidInputError, match="metrics 不能为空"):
        _plan(metrics=[])
    with pytest.raises(InvalidInputError, match="不支持的指标"):
        _plan(metrics=["expense_sum"])


def test_reject_bad_group_by() -> None:
    with pytest.raises(InvalidInputError, match="不支持的分组维度"):
        _plan(group_by=["year"])
    with pytest.raises(InvalidInputError, match="不能同时按月"):
        _plan(group_by=[GROUP_BY_MONTH, GROUP_BY_DAY])
    with pytest.raises(InvalidInputError, match="group_by 最多 2 个"):
        _plan(group_by=[GROUP_BY_MONTH, GROUP_BY_MERCHANT, GROUP_BY_ACCOUNT])


def test_reject_bad_output_and_top_n() -> None:
    with pytest.raises(InvalidInputError, match="不支持的输出形式"):
        _plan(output="chat")
    with pytest.raises(InvalidInputError, match="top_n 必须在"):
        _plan(top_n=0)
    with pytest.raises(InvalidInputError, match="top_n 必须"):
        _plan(top_n=True)
    with pytest.raises(InvalidInputError, match="top_n 必须"):
        _plan(top_n="20")


# ---- 拒绝：范围/授权/时间 ---------------------------------------------------------


def test_reject_scope_account_without_ids() -> None:
    with pytest.raises(InvalidInputError, match="scope=account 时必须提供 account_ids"):
        _plan(scope="account")
    with pytest.raises(InvalidInputError, match="scope=import 时必须提供 import_ids"):
        _plan(scope="import")
    with pytest.raises(InvalidInputError, match="不支持的查询范围"):
        _plan(scope="ledger")


def test_reject_account_outside_allowlist() -> None:
    raw = _raw(scope="account", account_ids=["acc-1", "acc-2"])
    with pytest.raises(InvalidInputError, match="无权访问账本账户: acc-2"):
        validate_plan(raw, now_iso=NOW, allowed_account_ids=frozenset({"acc-1"}))
    # 全部在授权集合内时通过
    plan = validate_plan(raw, now_iso=NOW, allowed_account_ids=frozenset({"acc-1", "acc-2"}))
    assert plan.account_ids == ("acc-1", "acc-2")


def test_reject_import_outside_allowlist() -> None:
    raw = _raw(scope="import", import_ids=["imp-9"])
    with pytest.raises(InvalidInputError, match="无权访问导入批次: imp-9"):
        validate_plan(raw, now_iso=NOW, allowed_import_ids=frozenset({"imp-1"}))


def test_reject_period_start_not_before_end() -> None:
    with pytest.raises(InvalidInputError, match="必须早于"):
        _plan(period={"start": "2026-11-01", "end_exclusive": "2026-11-01"})
    with pytest.raises(InvalidInputError, match="必须早于"):
        _plan(period={"start": "2026-12-01", "end_exclusive": "2026-11-01"})


def test_reject_range_too_long_and_bad_bound() -> None:
    with pytest.raises(InvalidInputError, match="查询跨度不能超过 3660 天"):
        _plan(period={"start": "2000-01-01", "end_exclusive": "2026-11-01"})
    with pytest.raises(InvalidInputError, match="必须早于|必须是 ISO|跨度"):
        _plan(period={"start": 0, "end_exclusive": "2026-11-01"})
    with pytest.raises(InvalidInputError, match="必须是 ISO"):
        _plan(period={"start": "2026/10/01", "end_exclusive": "2026-11-01"})
    with pytest.raises(InvalidInputError, match="必须是 ISO"):
        _plan(period={"start": "", "end_exclusive": "2026-11-01"})


def test_accept_partial_period() -> None:
    plan = _plan(period={"start": "2026-10-01"})
    assert plan.period.end_exclusive is None
    assert not any("未限定时间范围" in note for note in plan.unsupported_notes)
    assert "t.occurred_at < ?" not in compile_plan(plan, owner_id=1).aggregate_sql


def test_reject_bad_currency_and_timezone() -> None:
    with pytest.raises(InvalidInputError, match="currency 必须是 3 位大写字母"):
        _plan(currency="RMB1")
    with pytest.raises(InvalidInputError, match="无法识别时区"):
        _plan(period={"start": "2026-10-01", "timezone": "Not/AZone"})
    assert _plan(currency="usd").currency == "USD"


def test_reject_nul_in_any_field() -> None:
    with pytest.raises(InvalidInputError, match="NUL"):
        _plan(filters={"merchants": ["acme\x00corp"]})
    with pytest.raises(InvalidInputError, match="NUL"):
        _plan(currency="CN\x00Y")


# ---- 过滤条件与注入安全 -----------------------------------------------------------


def test_filter_amounts_and_directions() -> None:
    compiled = _compiled(
        filters={
            "directions": ["expense", "unknown"],
            "min_amount_minor": 100,
            "max_amount_minor": 5000,
            "category_ids": ["cat-1"],
        }
    )
    sql = compiled.aggregate_sql
    assert "t.direction IN (?,?)" in sql
    assert "t.category_id IN (?)" in sql
    assert "t.amount_minor >= ?" in sql
    assert "t.amount_minor <= ?" in sql
    assert "expense" in compiled.aggregate_params
    assert 100 in compiled.aggregate_params
    assert 5000 in compiled.aggregate_params


def test_reject_bad_amount_bounds() -> None:
    with pytest.raises(InvalidInputError, match="min_amount_minor 不能大于"):
        _plan(filters={"min_amount_minor": 500, "max_amount_minor": 100})
    with pytest.raises(InvalidInputError, match="不能为负数"):
        _plan(filters={"min_amount_minor": -1})
    with pytest.raises(InvalidInputError, match="必须是整数"):
        _plan(filters={"min_amount_minor": True})


def test_reject_bad_direction() -> None:
    with pytest.raises(InvalidInputError, match="不支持的方向"):
        _plan(filters={"directions": ["out"]})


def test_reject_too_many_merchants() -> None:
    with pytest.raises(InvalidInputError, match="filters.merchants 最多 20 个"):
        _plan(filters={"merchants": [f"m{index}" for index in range(21)]})


def test_long_merchant_truncated_with_note() -> None:
    plan = _plan(filters={"merchants": ["商" * 300]})
    assert len(plan.filters.merchants[0]) == 100
    assert any("已截断到 100 字符" in note for note in plan.unsupported_notes)


def test_merchant_injection_stays_out_of_sql_text() -> None:
    payload = "x' OR 1=1 --"
    compiled = _compiled(filters={"merchants": [payload], "directions": ["expense"]})
    for sql in (compiled.aggregate_sql, compiled.group_sql, compiled.detail_sql):
        assert "OR 1=1" not in sql
        assert payload not in sql
    assert f"%{payload}%" in compiled.aggregate_params
    assert "ESCAPE '\\'" in compiled.aggregate_sql
    # LIKE 只以占位符出现：SQL 里不出现任何 %用户关键词%
    assert "LIKE '%" not in compiled.aggregate_sql


def test_escape_like() -> None:
    assert escape_like("50%_off") == "50\\%\\_off"
    assert escape_like("a\\b") == "a\\\\b"
    assert escape_like("plain") == "plain"
    compiled = _compiled(filters={"merchants": ["50%_off"]})
    assert "%50\\%\\_off%" in compiled.aggregate_params


# ---- SQL 形状 ------------------------------------------------------------------


def test_placeholder_count_matches_params_for_all_sql() -> None:
    compiled = _compiled(
        scope="account",
        account_ids=["acc-1", "acc-2"],
        group_by=[GROUP_BY_MONTH, GROUP_BY_MERCHANT],
        filters={
            "directions": ["expense", "income"],
            "category_ids": ["cat-1", "cat-2", "cat-3"],
            "merchants": ["星巴克", "50%_off"],
            "min_amount_minor": 100,
            "max_amount_minor": 90000,
        },
    )
    assert compiled.aggregate_sql.count("?") == len(compiled.aggregate_params)
    assert compiled.group_sql.count("?") == len(compiled.group_params)
    assert compiled.detail_sql.count("?") == len(compiled.detail_params)


def test_refund_confirmation_toggle_changes_sql_only() -> None:
    strict = _compiled()
    loose = _compiled(filters={"include_unconfirmed_refunds": True})

    assert "l.confirmation = 'confirmed'" in strict.aggregate_sql
    assert "confirmation" not in loose.aggregate_sql
    assert strict.aggregate_sql != loose.aggregate_sql
    assert "sum(l.amount_minor)" in strict.aggregate_sql.lower()
    assert "ledger_refund_links AS l ON l.original_transaction_id = o.id" in strict.aggregate_sql
    assert "r.id = l.refund_transaction_id" in strict.aggregate_sql
    assert any("未确认退款关联不计入" in note for note in strict.notes)
    assert any("未确认候选" in note for note in loose.notes)


def test_top_n_overflow_truncated_to_max() -> None:
    plan = _plan(top_n=999)
    assert plan.top_n == MAX_TOP_N
    assert any("已截断为 200" in note for note in plan.unsupported_notes)

    compiled = compile_plan(plan, owner_id=1)
    assert compiled.group_params == ()
    assert compiled.detail_params[-1] == MAX_TOP_N
    assert any("已截断为 200" in note for note in compiled.notes)


def test_detail_and_group_limits_use_top_n() -> None:
    compiled = _compiled(top_n=20, group_by=[GROUP_BY_MONTH])
    assert compiled.detail_params[-1] == 20
    assert compiled.group_params[-1] == 20

    wide = _compiled(top_n=50, group_by=[GROUP_BY_MONTH])
    assert wide.detail_params[-1] == 50
    assert wide.group_params[-1] == 50
    # LIMIT 在两条 SQL 里都只用占位符绑定
    assert wide.detail_sql.rstrip().endswith("LIMIT ?")
    assert wide.group_sql.rstrip().endswith("LIMIT ?")


def test_compile_requires_int_owner_and_valid_plan() -> None:
    plan = _plan()
    with pytest.raises(InvalidInputError, match="owner_id 必须是整数"):
        compile_plan(plan, owner_id=True)
    with pytest.raises(InvalidInputError, match="owner_id 必须是整数"):
        compile_plan(plan, owner_id="1")
    with pytest.raises(InvalidInputError, match="QueryPlan"):
        compile_plan({"version": 1}, owner_id=1)  # type: ignore[arg-type]


def test_handwritten_plan_guard_rejects_bad_group_by() -> None:
    plan = QueryPlan(
        version=1,
        basis=BASIS_STATEMENT_FLOW,
        metrics=(METRIC_REFUND_RECEIVED,),
        group_by=("year",),
    )
    with pytest.raises(InvalidInputError, match="不支持的分组维度"):
        compile_plan(plan, owner_id=1)
