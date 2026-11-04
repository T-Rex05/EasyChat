"""QueryPlan 验证与参数化 SQL 编译（files-ledger 设计 §9–§10，增量计划 F8）。

模型只能提交受控的 ``QueryPlan``：SQL 文本、表名、列名全部来自本模块常量，
用户输入一律进 ``?`` 占位符，绝不拼接进 SQL 文本。编译产出三条 SQL：

* ``aggregate_sql`` —— 一行六项指标（支出/收入/中性/退款入账/退款冲抵/笔数），
  内部复用同一个 ``scope`` CTE，一次 round-trip 拿全量口径；
* ``group_sql`` —— 1~2 个受控维度分桶，``LIMIT top_n``；
* ``detail_sql`` —— 证据明细行，``LIMIT min(top_n, MAX_TOP_N)``。

本文件是纯函数、无 IO：可用假数据独立单测，不连数据库。
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.modules.ledger.contracts import (
    BASES,
    CONFIRMATION_CONFIRMED,
    DIRECTION_EXPENSE,
    DIRECTION_INCOME,
    DIRECTION_NEUTRAL,
    DIRECTIONS,
    EVENT_ROLE_NEUTRAL,
    EVENT_ROLE_PAYMENT,
    EVENT_ROLE_REFUND,
    GROUP_BY_ACCOUNT,
    GROUP_BY_CATEGORY,
    GROUP_BY_DAY,
    GROUP_BY_MERCHANT,
    GROUP_BY_MONTH,
    GROUP_BYS,
    METRICS,
    OUTPUT_SUMMARY,
    OUTPUTS,
    Period,
    QueryFilters,
    QueryPlan,
)
from backend.shared.errors import InvalidInputError

# ---- 上限（均为硬上限，超出即拒绝或截断） ------------------------------------------
MAX_TOP_N = 200
MAX_RANGE_DAYS = 3660
MAX_METRICS = 5
MAX_GROUP_BY = 2
MAX_MERCHANTS = 20
MAX_MERCHANT_LEN = 100
MAX_CATEGORY_IDS = 50
MAX_TEXT_LEN = 200
MAX_USER_NOTES = 10
MAX_TIMEZONE_LEN = 64

# 契约里没有 scope 常量，按设计 §10 的三种范围在此定义（不进 SQL）。
SCOPE_ALL = "all"
SCOPE_ACCOUNT = "account"
SCOPE_IMPORT = "import"
SCOPES = frozenset({SCOPE_ALL, SCOPE_ACCOUNT, SCOPE_IMPORT})

# ---- 字段白名单：schema 拒绝未知字段，不静默忽略 -----------------------------------
ALLOWED_PLAN_KEYS = frozenset(
    {
        "version",
        "basis",
        "metrics",
        "scope",
        "account_ids",
        "import_ids",
        "period",
        "group_by",
        "filters",
        "top_n",
        "output",
        "currency",
        "data_cutoff",
        "unsupported_notes",
    }
)
ALLOWED_PERIOD_KEYS = frozenset({"start", "end_exclusive", "timezone"})
ALLOWED_FILTER_KEYS = frozenset(
    {
        "directions",
        "category_ids",
        "merchants",
        "min_amount_minor",
        "max_amount_minor",
        "include_unconfirmed_refunds",
    }
)

# ---- 受控 SQL 标识符：只来自本模块常量，永远不由输入拼接 ---------------------------
_TX_TABLE = "ledger_transactions"
_LINK_TABLE = "ledger_refund_links"
_SOURCE_TABLE = "ledger_transaction_sources"

# 固定枚举值以字面量嵌入 SQL（值本身来自契约常量，不是用户输入）。
_EV_PAYMENT = f"'{EVENT_ROLE_PAYMENT}'"
_EV_REFUND = f"'{EVENT_ROLE_REFUND}'"
_EV_NEUTRAL = f"'{EVENT_ROLE_NEUTRAL}'"
_DIR_EXPENSE = f"'{DIRECTION_EXPENSE}'"
_DIR_INCOME = f"'{DIRECTION_INCOME}'"
_DIR_NEUTRAL = f"'{DIRECTION_NEUTRAL}'"
_CONFIRM_CONFIRMED = f"'{CONFIRMATION_CONFIRMED}'"

# 分组表达式只能是这些常量，模型给不出任意表达式。
_BUCKET_EXPRESSIONS: dict[str, str] = {
    GROUP_BY_MONTH: "substr(t.occurred_at,1,7)",
    GROUP_BY_DAY: "substr(t.occurred_at,1,10)",
    GROUP_BY_CATEGORY: "COALESCE(t.category_id, '')",
    GROUP_BY_MERCHANT: "t.merchant",
    GROUP_BY_ACCOUNT: "t.account_id",
}

_SCOPE_COLUMNS = (
    "t.id, t.occurred_at, t.direction, t.event_role, t.amount_minor,"
    " t.merchant, t.account_id, t.category_id"
)
_DETAIL_COLUMNS = (
    "t.id, t.owner_id, t.account_id, t.external_id, t.occurred_at, t.tx_type,"
    " t.merchant, t.product, t.amount_minor, t.currency, t.direction, t.event_role,"
    " t.status, t.status_key, t.verification, t.category_id, t.revision"
)

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
# 只接受 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM[:SS[.ffffff]][+08:00]（含 Z），
# 不接受“地摊式”输入；小数秒仅为兼容数据库里带微秒的 data_cutoff。
_ISO_BOUND_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:[+-]\d{2}:\d{2}|Z)?)?$"
)


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    """编译产物：三条 SQL 各自带独立参数元组，参数顺序与 ``?`` 出现顺序一致。"""

    aggregate_sql: str
    aggregate_params: tuple[Any, ...]
    group_sql: str
    group_params: tuple[Any, ...]
    detail_sql: str
    detail_params: tuple[Any, ...]
    notes: tuple[str, ...] = ()


def escape_like(text: str) -> str:
    """转义 LIKE 通配符，配合 SQL 中的 ``ESCAPE '\\'`` 使用（反斜杠优先）。"""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---- 通用校验小工具 -------------------------------------------------------------


def _require_int(value: Any, field: str) -> int:
    """显式排除 bool：``isinstance(True, int)`` 为真是 Python 的经典陷阱。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidInputError(f"{field} 必须是整数")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidInputError(f"{field} 必须是布尔值")
    return value


def _assert_no_nul(value: Any, path: str = "") -> None:
    """任何位置出现 NUL 一律拒绝：驱动层会把 C 字符串截断，导致校验与执行不一致。"""
    if isinstance(value, str):
        if "\x00" in value:
            where = path or "查询计划"
            raise InvalidInputError(f"字段 {where} 包含非法字符 NUL")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _assert_no_nul(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for index, item in enumerate(value):
            _assert_no_nul(item, f"{path}[{index}]")


def _reject_unknown(
    mapping: Mapping[Any, Any],
    allowed: frozenset[str],
    *,
    prefix: str = "",
) -> None:
    """白名单之外一律拒绝（尤其 sql / python / code / table 这类越权键）。"""
    unknown = sorted(f"{prefix}{key}" for key in mapping if key not in allowed)
    if unknown:
        raise InvalidInputError(f"不支持的查询计划字段: {', '.join(unknown)}")


def _require_text(
    value: Any,
    field: str,
    notes: list[str],
    *,
    limit: int = MAX_TEXT_LEN,
) -> str:
    """校验并返回字符串；NUL 拒绝，超长截断并记 note。"""
    if not isinstance(value, str):
        raise InvalidInputError(f"{field} 必须是字符串")
    if "\x00" in value:
        raise InvalidInputError(f"字段 {field} 包含非法字符 NUL")
    text = value.strip()
    if not text:
        raise InvalidInputError(f"{field} 不能为空字符串")
    if len(text) > limit:
        notes.append(f"{field} 超长（{len(text)} 字符），已截断到 {limit} 字符")
        text = text[:limit]
    return text


def _string_list(
    value: Any,
    field: str,
    notes: list[str],
    *,
    limit: int = MAX_TEXT_LEN,
    max_items: int | None = None,
) -> tuple[str, ...]:
    """字符串数组 → 去重保序元组；空数组合法，空元素与非法类型拒绝。"""
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise InvalidInputError(f"{field} 必须是字符串数组")
    items: list[str] = []
    for index, item in enumerate(value):
        items.append(_require_text(item, f"{field}[{index}]", notes, limit=limit))
    deduped = tuple(dict.fromkeys(items))
    if max_items is not None and len(deduped) > max_items:
        raise InvalidInputError(f"{field} 最多 {max_items} 个")
    return deduped


def _parse_iso_bound(value: Any, field: str, notes: list[str]) -> str | None:
    """校验 ISO 边界并原样返回（不补时区，保持库内 ISO 前缀比较语义）。"""
    if value is None:
        return None
    if not isinstance(value, str) or isinstance(value, bool):
        raise InvalidInputError(f"{field} 必须是 ISO 日期或日期时间，或 null")
    text = value.strip()
    if not text or not _ISO_BOUND_RE.match(text):
        raise InvalidInputError(f"{field} 必须是 ISO 日期或日期时间（YYYY-MM-DD[THH:MM[:SS][+08:00]]）")
    if len(text) > MAX_TEXT_LEN:
        notes.append(f"{field} 超长（{len(text)} 字符），已截断到 {MAX_TEXT_LEN} 字符")
        text = text[:MAX_TEXT_LEN]
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidInputError(f"{field} 必须是 ISO 日期或日期时间") from exc
    return text


def _naive_instant(text: str) -> datetime:
    """剥离时区后比较“墙上时间”：混合带/不带时区的输入也要能稳定比较。"""
    return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)


def _load_timezone(name: Any, field: str, notes: list[str]) -> str:
    """时区必须是 zoneinfo 真实可加载的名字，否则拒绝。"""
    text = _require_text(name, field, notes, limit=MAX_TIMEZONE_LEN)
    try:
        ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise InvalidInputError(f"无法识别时区: {text}") from exc
    return text


def _resolve_period(raw: Any, default_timezone: str, notes: list[str]) -> Period:
    period_raw: Any = {} if raw is None else raw
    if not isinstance(period_raw, Mapping):
        raise InvalidInputError("period 必须是对象")
    _reject_unknown(period_raw, ALLOWED_PERIOD_KEYS, prefix="period.")

    start = _parse_iso_bound(period_raw.get("start"), "period.start", notes)
    end = _parse_iso_bound(period_raw.get("end_exclusive"), "period.end_exclusive", notes)
    timezone_name = _load_timezone(
        period_raw.get("timezone", default_timezone), "period.timezone", notes
    )

    if start is None and end is None:
        notes.append("未限定时间范围（统计全部已入账交易）")
    if start is not None and end is not None:
        start_at, end_at = _naive_instant(start), _naive_instant(end)
        if start_at >= end_at:
            raise InvalidInputError("period.start 必须早于 period.end_exclusive")
        if end_at - start_at > timedelta(days=MAX_RANGE_DAYS):
            raise InvalidInputError(f"查询跨度不能超过 {MAX_RANGE_DAYS} 天")
    return Period(start=start, end_exclusive=end, timezone=timezone_name)


def _resolve_filters(raw: Any, notes: list[str]) -> QueryFilters:
    filters_raw: Any = {} if raw is None else raw
    if not isinstance(filters_raw, Mapping):
        raise InvalidInputError("filters 必须是对象")
    _reject_unknown(filters_raw, ALLOWED_FILTER_KEYS, prefix="filters.")

    directions = _string_list(
        filters_raw.get("directions"), "filters.directions", notes, limit=32
    )
    for direction in directions:
        if direction not in DIRECTIONS:
            raise InvalidInputError(f"不支持的方向: {direction}")

    category_ids = _string_list(
        filters_raw.get("category_ids"),
        "filters.category_ids",
        notes,
        max_items=MAX_CATEGORY_IDS,
    )
    merchants = _string_list(
        filters_raw.get("merchants"),
        "filters.merchants",
        notes,
        limit=MAX_MERCHANT_LEN,
        max_items=MAX_MERCHANTS,
    )

    min_amount: int | None = None
    max_amount: int | None = None
    raw_min = filters_raw.get("min_amount_minor")
    raw_max = filters_raw.get("max_amount_minor")
    if raw_min is not None:
        min_amount = _require_int(raw_min, "filters.min_amount_minor")
    if raw_max is not None:
        max_amount = _require_int(raw_max, "filters.max_amount_minor")
    if min_amount is not None and min_amount < 0:
        raise InvalidInputError("filters.min_amount_minor 不能为负数")
    if max_amount is not None and max_amount < 0:
        raise InvalidInputError("filters.max_amount_minor 不能为负数")
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise InvalidInputError("min_amount_minor 不能大于 max_amount_minor")

    include_unconfirmed = filters_raw.get("include_unconfirmed_refunds", False)
    if include_unconfirmed is None:
        include_unconfirmed = False
    include_unconfirmed = _require_bool(
        include_unconfirmed, "filters.include_unconfirmed_refunds"
    )

    return QueryFilters(
        directions=directions,
        category_ids=category_ids,
        merchants=merchants,
        min_amount_minor=min_amount,
        max_amount_minor=max_amount,
        include_unconfirmed_refunds=include_unconfirmed,
    )


# ---- 验证 ----------------------------------------------------------------------


def validate_plan(
    raw: Mapping[str, Any],
    *,
    now_iso: str,
    default_timezone: str = "Asia/Shanghai",
    allowed_account_ids: frozenset[str] | None = None,
    allowed_import_ids: frozenset[str] | None = None,
) -> QueryPlan:
    """把模型给的 JSON 变成可信 QueryPlan；任何不合规一律 InvalidInputError。

    ``now_iso`` 只用于补 data_cutoff（调用方按用户时区生成），
    所有授权集合由调用方按 Principal 现查现传，本函数不查库。
    """
    if not isinstance(raw, Mapping):
        raise InvalidInputError("查询计划必须是 JSON 对象")
    _assert_no_nul(raw)
    _reject_unknown(raw, ALLOWED_PLAN_KEYS)
    notes: list[str] = []

    version = raw.get("version")
    if isinstance(version, bool) or version != 1:
        raise InvalidInputError(f"不支持的查询计划版本: {version}")

    basis = raw.get("basis")
    if not isinstance(basis, str) or basis not in BASES:
        raise InvalidInputError(f"不支持的统计口径: {basis}")

    metrics = _string_list(raw.get("metrics"), "metrics", notes)
    if not metrics:
        raise InvalidInputError("metrics 不能为空，必须至少指定一个指标")
    for metric in metrics:
        if metric not in METRICS:
            raise InvalidInputError(f"不支持的指标: {metric}")
    if len(metrics) > MAX_METRICS:
        raise InvalidInputError(f"metrics 最多 {MAX_METRICS} 个")

    group_by = _string_list(raw.get("group_by"), "group_by", notes, limit=32)
    for dimension in group_by:
        if dimension not in GROUP_BYS:
            raise InvalidInputError(f"不支持的分组维度: {dimension}")
    if len(group_by) > MAX_GROUP_BY:
        raise InvalidInputError(f"group_by 最多 {MAX_GROUP_BY} 个")
    if GROUP_BY_MONTH in group_by and GROUP_BY_DAY in group_by:
        raise InvalidInputError("不能同时按月（month）与按日（day）分组")

    output = raw.get("output", OUTPUT_SUMMARY)
    if not isinstance(output, str) or output not in OUTPUTS:
        raise InvalidInputError(f"不支持的输出形式: {output}")

    top_n = _require_int(raw.get("top_n", 20), "top_n")
    if top_n <= 0:
        raise InvalidInputError(f"top_n 必须在 1..{MAX_TOP_N} 之间")
    if top_n > MAX_TOP_N:
        notes.append(f"top_n={top_n} 超出上限，已截断为 {MAX_TOP_N}")
        top_n = MAX_TOP_N

    scope = raw.get("scope", SCOPE_ALL)
    if not isinstance(scope, str) or scope not in SCOPES:
        raise InvalidInputError(f"不支持的查询范围: {scope}")
    account_ids = _string_list(raw.get("account_ids"), "account_ids", notes)
    import_ids = _string_list(raw.get("import_ids"), "import_ids", notes)
    if scope == SCOPE_ACCOUNT:
        if not account_ids:
            raise InvalidInputError("scope=account 时必须提供 account_ids")
        if import_ids:
            raise InvalidInputError("scope=account 时不能同时指定 import_ids")
        import_ids = ()
    elif scope == SCOPE_IMPORT:
        if not import_ids:
            raise InvalidInputError("scope=import 时必须提供 import_ids")
        if account_ids:
            raise InvalidInputError("scope=import 时不能同时指定 account_ids")
        account_ids = ()
    else:
        if account_ids or import_ids:
            raise InvalidInputError("scope=all 时不能指定 account_ids/import_ids")

    if allowed_account_ids is not None:
        denied_accounts = [item for item in account_ids if item not in allowed_account_ids]
        if denied_accounts:
            raise InvalidInputError(f"无权访问账本账户: {', '.join(denied_accounts)}")
    if allowed_import_ids is not None:
        denied_imports = [item for item in import_ids if item not in allowed_import_ids]
        if denied_imports:
            raise InvalidInputError(f"无权访问导入批次: {', '.join(denied_imports)}")

    period = _resolve_period(raw.get("period"), default_timezone, notes)
    filters = _resolve_filters(raw.get("filters"), notes)

    currency_raw = raw.get("currency")
    if currency_raw is None:
        currency = "CNY"
    else:
        currency = _require_text(currency_raw, "currency", notes).upper()
        if not _CURRENCY_RE.match(currency):
            raise InvalidInputError("currency 必须是 3 位大写字母代码（如 CNY）")

    cutoff_raw = raw.get("data_cutoff")
    if cutoff_raw is None:
        data_cutoff = now_iso
    else:
        data_cutoff = _parse_iso_bound(cutoff_raw, "data_cutoff", notes) or now_iso

    extra_notes = _string_list(
        raw.get("unsupported_notes"), "unsupported_notes", notes, max_items=MAX_USER_NOTES
    )

    return QueryPlan(
        version=1,
        basis=basis,
        metrics=metrics,
        scope=scope,
        account_ids=account_ids,
        import_ids=import_ids,
        period=period,
        group_by=group_by,
        filters=filters,
        top_n=top_n,
        output=output,
        currency=currency,
        data_cutoff=data_cutoff,
        unsupported_notes=tuple(dict.fromkeys([*notes, *extra_notes])),
    )


# ---- 编译：受控 SQL -------------------------------------------------------------


def _placeholders(count: int) -> str:
    """按列表长度生成 ``?,?,?``；值只进参数，绝不进 SQL 文本。"""
    return ",".join(["?"] * count)


def _scope_cte(where_sql: str) -> str:
    """三条 SQL 共用同一受控 CTE；过滤条件只有本函数生成的一份。"""
    return f"WITH scope AS (SELECT {_SCOPE_COLUMNS} FROM {_TX_TABLE} AS t WHERE {where_sql})"


def _build_where(plan: QueryPlan, owner_id: int) -> tuple[str, list[Any]]:
    """公共 WHERE：clause 顺序与参数追加顺序严格一致。"""
    clauses: list[str] = ["t.owner_id = ?", "t.deleted_at IS NULL"]
    params: list[Any] = [owner_id]

    if plan.period.start is not None:
        clauses.append("t.occurred_at >= ?")
        params.append(plan.period.start)
    if plan.period.end_exclusive is not None:
        clauses.append("t.occurred_at < ?")
        params.append(plan.period.end_exclusive)

    if plan.scope == SCOPE_ACCOUNT:
        if not plan.account_ids:
            raise InvalidInputError("scope=account 时必须提供 account_ids")
        clauses.append(f"t.account_id IN ({_placeholders(len(plan.account_ids))})")
        params.extend(plan.account_ids)
    elif plan.scope == SCOPE_IMPORT:
        if not plan.import_ids:
            raise InvalidInputError("scope=import 时必须提供 import_ids")
        clauses.append(
            "EXISTS (SELECT 1 FROM "
            f"{_SOURCE_TABLE} AS s WHERE s.transaction_id = t.id"
            f" AND s.import_id IN ({_placeholders(len(plan.import_ids))}))"
        )
        params.extend(plan.import_ids)
    elif plan.scope != SCOPE_ALL:
        raise InvalidInputError(f"不支持的查询范围: {plan.scope}")

    if plan.filters.directions:
        clauses.append(f"t.direction IN ({_placeholders(len(plan.filters.directions))})")
        params.extend(plan.filters.directions)

    if plan.filters.category_ids:
        clauses.append(
            f"t.category_id IN ({_placeholders(len(plan.filters.category_ids))})"
        )
        params.extend(plan.filters.category_ids)

    if plan.filters.merchants:
        like_clauses = " OR ".join(
            ["t.merchant LIKE ? ESCAPE '\\'"] * len(plan.filters.merchants)
        )
        clauses.append(f"({like_clauses})")
        params.extend(f"%{escape_like(item)}%" for item in plan.filters.merchants)

    if plan.filters.min_amount_minor is not None:
        clauses.append("t.amount_minor >= ?")
        params.append(plan.filters.min_amount_minor)
    if plan.filters.max_amount_minor is not None:
        clauses.append("t.amount_minor <= ?")
        params.append(plan.filters.max_amount_minor)

    return " AND ".join(clauses), params


def _aggregate_select(*, confirmed_only: bool) -> str:
    """一行六项指标；退款冲抵取 ledger_refund_links.amount_minor（不重复扣原单）。"""
    confirmed = (
        f" AND l.confirmation = {_CONFIRM_CONFIRMED}" if confirmed_only else ""
    )
    return (
        " SELECT"
        " COALESCE((SELECT SUM(amount_minor) FROM scope"
        f" WHERE event_role = {_EV_PAYMENT} AND direction = {_DIR_EXPENSE}), 0)"
        " AS expense_minor,"
        " COALESCE((SELECT SUM(amount_minor) FROM scope"
        f" WHERE event_role = {_EV_PAYMENT} AND direction = {_DIR_INCOME}), 0)"
        " AS income_minor,"
        " COALESCE((SELECT SUM(amount_minor) FROM scope"
        f" WHERE (event_role = {_EV_NEUTRAL} OR direction = {_DIR_NEUTRAL})), 0)"
        " AS neutral_minor,"
        f" COALESCE((SELECT SUM(amount_minor) FROM scope WHERE event_role = {_EV_REFUND}), 0)"
        " AS refund_received_minor,"
        " COALESCE((SELECT SUM(l.amount_minor)"
        f" FROM scope AS o JOIN {_LINK_TABLE} AS l ON l.original_transaction_id = o.id"
        f" JOIN {_TX_TABLE} AS r ON r.id = l.refund_transaction_id"
        f" WHERE o.event_role = {_EV_PAYMENT} AND o.direction = {_DIR_EXPENSE}"
        f"{confirmed}), 0) AS refund_applied_minor,"
        " (SELECT COUNT(id) FROM scope) AS tx_count"
    )


def _bucket_expression(dimension: str) -> str:
    try:
        return _BUCKET_EXPRESSIONS[dimension]
    except KeyError as exc:  # 手写计划绕过 validate_plan 时同样拒绝
        raise InvalidInputError(f"不支持的分组维度: {dimension}") from exc


def _group_select(bucket1: str, bucket2: str) -> str:
    return (
        f" SELECT {bucket1} AS bucket1, {bucket2} AS bucket2,"
        " COALESCE(SUM(CASE WHEN t.event_role = "
        f"{_EV_PAYMENT} AND t.direction = {_DIR_EXPENSE}"
        " THEN t.amount_minor ELSE 0 END), 0) AS expense_minor,"
        " COALESCE(SUM(CASE WHEN t.event_role = "
        f"{_EV_PAYMENT} AND t.direction = {_DIR_INCOME}"
        " THEN t.amount_minor ELSE 0 END), 0) AS income_minor,"
        " COALESCE(SUM(CASE WHEN t.event_role = "
        f"{_EV_REFUND} THEN t.amount_minor ELSE 0 END), 0) AS refund_received_minor,"
        " COUNT(t.id) AS tx_count"
        " FROM scope AS t GROUP BY 1,2 ORDER BY expense_minor DESC LIMIT ?"
    )


def _guard_plan(plan: QueryPlan) -> None:
    """compile_plan 也可能被手写计划调用：再做一次廉价不变量检查。"""
    if not isinstance(plan, QueryPlan):
        raise InvalidInputError("compile_plan 只接受经验证的 QueryPlan")
    if isinstance(plan.version, bool) or plan.version != 1:
        raise InvalidInputError(f"不支持的查询计划版本: {plan.version}")
    if plan.basis not in BASES:
        raise InvalidInputError(f"不支持的统计口径: {plan.basis}")
    if not plan.metrics:
        raise InvalidInputError("metrics 不能为空，必须至少指定一个指标")
    for metric in plan.metrics:
        if metric not in METRICS:
            raise InvalidInputError(f"不支持的指标: {metric}")
    if plan.output not in OUTPUTS:
        raise InvalidInputError(f"不支持的输出形式: {plan.output}")
    if len(plan.group_by) > MAX_GROUP_BY:
        raise InvalidInputError(f"group_by 最多 {MAX_GROUP_BY} 个")
    if GROUP_BY_MONTH in plan.group_by and GROUP_BY_DAY in plan.group_by:
        raise InvalidInputError("不能同时按月（month）与按日（day）分组")


def compile_plan(plan: QueryPlan, *, owner_id: int) -> CompiledQuery:
    """把经验证的 QueryPlan 编译成三条纯参数化 SQL。

    ``owner_id`` 必须由可信 Principal 传入（QueryPlan 里没有所有者字段），
    绑定为 ``t.owner_id = ?``，是隔离不同用户账本的第一道闸门。
    """
    _guard_plan(plan)
    if isinstance(owner_id, bool) or not isinstance(owner_id, int):
        raise InvalidInputError("owner_id 必须是整数")

    top_n = plan.top_n
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise InvalidInputError(f"top_n 必须在 1..{MAX_TOP_N} 之间")

    notes: list[str] = list(plan.unsupported_notes)
    if top_n > MAX_TOP_N:
        notes.append(f"top_n={top_n} 超出上限，已截断为 {MAX_TOP_N}")
        top_n = MAX_TOP_N

    if plan.filters.include_unconfirmed_refunds:
        notes.append("退款关联包含未确认候选（suggested），报告中必须标注待核实")
    else:
        notes.append("未确认退款关联不计入（仅统计 confirmation='confirmed'）")
    notes.append("金额按库内原始币种汇总，未做汇率换算")
    notes.append("明细 SQL 始终生成，供证据引用")

    where_sql, params = _build_where(plan, owner_id)
    scope_cte = _scope_cte(where_sql)

    aggregate_sql = scope_cte + _aggregate_select(
        confirmed_only=not plan.filters.include_unconfirmed_refunds
    )

    if plan.group_by:
        bucket1 = _bucket_expression(plan.group_by[0])
        bucket2 = _bucket_expression(plan.group_by[1]) if len(plan.group_by) > 1 else "''"
        group_sql = scope_cte + _group_select(bucket1, bucket2)
        group_params = tuple([*params, top_n])
    else:
        notes.append("未指定分组维度，group_sql 为空")
        group_sql, group_params = "", ()

    detail_limit = min(top_n, MAX_TOP_N)
    detail_sql = (
        f"SELECT {_DETAIL_COLUMNS} FROM {_TX_TABLE} AS t"
        f" WHERE {where_sql}"
        " ORDER BY t.occurred_at DESC, t.id DESC LIMIT ?"
    )
    detail_params = tuple([*params, detail_limit])

    return CompiledQuery(
        aggregate_sql=aggregate_sql,
        aggregate_params=tuple(params),
        group_sql=group_sql,
        group_params=group_params,
        detail_sql=detail_sql,
        detail_params=detail_params,
        notes=tuple(dict.fromkeys(notes)),
    )
