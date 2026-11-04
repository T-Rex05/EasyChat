"""ledger 模块公开契约（设计 §7–§10）。

金额一律整数最小货币单位（分）；交易身份由 identity_key 唯一；
查询只接受经过验证的 QueryPlan，不接受模型生成的 SQL。

本文件只放值对象/常量，不含 IO，便于解析器、身份、查询、报告各自独立测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# ---- 方向 ---------------------------------------------------------------------
DIRECTION_EXPENSE = "expense"
DIRECTION_INCOME = "income"
DIRECTION_NEUTRAL = "neutral"
DIRECTION_UNKNOWN = "unknown"
DIRECTIONS = frozenset(
    {DIRECTION_EXPENSE, DIRECTION_INCOME, DIRECTION_NEUTRAL, DIRECTION_UNKNOWN}
)

# ---- 事件角色（原支付 / 退款 / 中性） --------------------------------------------
EVENT_ROLE_PAYMENT = "payment"
EVENT_ROLE_REFUND = "refund"
EVENT_ROLE_NEUTRAL = "neutral"
EVENT_ROLES = frozenset({EVENT_ROLE_PAYMENT, EVENT_ROLE_REFUND, EVENT_ROLE_NEUTRAL})

# ---- 交易状态（保留原文 + 规范化 key） -------------------------------------------
STATUS_PAID = "paid"
STATUS_REFUNDED_FULL = "refunded_full"
STATUS_REFUNDED_PARTIAL = "refunded_partial"
STATUS_CLOSED = "closed"
STATUS_FAILED = "failed"
STATUS_RECEIVED = "received"
STATUS_PENDING = "pending"
STATUS_UNKNOWN = "unknown"
STATUS_KEYS = frozenset(
    {
        STATUS_PAID, STATUS_REFUNDED_FULL, STATUS_REFUNDED_PARTIAL, STATUS_CLOSED,
        STATUS_FAILED, STATUS_RECEIVED, STATUS_PENDING, STATUS_UNKNOWN,
    }
)

# ---- 来源可信度 ----------------------------------------------------------------
VERIFICATION_PARSED = "parsed"        # 确定性 XLSX/CSV 解析
VERIFICATION_IMAGE = "image_extracted"  # 图片识别，字段来自视觉结果
VERIFICATION_CANDIDATE = "candidate"  # 缺可靠 ID/金额，需要核对
VERIFICATION_CONFIRMED = "confirmed"  # 用户确认后入账
VERIFICATION_CORRECTED = "corrected"  # 用户手工修正
VERIFICATIONS = frozenset(
    {
        VERIFICATION_PARSED, VERIFICATION_IMAGE, VERIFICATION_CANDIDATE,
        VERIFICATION_CONFIRMED, VERIFICATION_CORRECTED,
    }
)

# ---- 导入批次状态 ----------------------------------------------------------------
IMPORT_SAVED = "saved"
IMPORT_PARSING = "parsing"
IMPORT_NEEDS_REVIEW = "needs_review"
IMPORT_VALIDATED = "validated"
IMPORT_COMMITTED = "committed"
IMPORT_FAILED = "failed"
IMPORT_SUPERSEDED = "superseded"
IMPORT_STATES = frozenset(
    {
        IMPORT_SAVED, IMPORT_PARSING, IMPORT_NEEDS_REVIEW, IMPORT_VALIDATED,
        IMPORT_COMMITTED, IMPORT_FAILED, IMPORT_SUPERSEDED,
    }
)

# ---- 覆盖完整性 ----------------------------------------------------------------
COVERAGE_COMPLETE = "complete"
COVERAGE_PARTIAL = "partial"
COVERAGE_OVERLAPPING = "overlapping"
COVERAGE_UNKNOWN = "unknown"
COVERAGE_KINDS = frozenset(
    {COVERAGE_COMPLETE, COVERAGE_PARTIAL, COVERAGE_OVERLAPPING, COVERAGE_UNKNOWN}
)

# ---- 退款匹配方式/确认度 ---------------------------------------------------------
MATCH_SAME_EXTERNAL_ID = "same_external_id"
MATCH_MERCHANT_ID = "merchant_id"
MATCH_NOTE_REFERENCE = "note_reference"
MATCH_AMOUNT_DATE = "amount_date"
MATCH_MANUAL = "manual"
MATCH_METHODS = frozenset(
    {
        MATCH_SAME_EXTERNAL_ID, MATCH_MERCHANT_ID, MATCH_NOTE_REFERENCE,
        MATCH_AMOUNT_DATE, MATCH_MANUAL,
    }
)
CONFIRMATION_CONFIRMED = "confirmed"
CONFIRMATION_SUGGESTED = "suggested"
CONFIRMATIONS = frozenset({CONFIRMATION_CONFIRMED, CONFIRMATION_SUGGESTED})

# ---- 统计口径 ------------------------------------------------------------------
BASIS_STATEMENT_FLOW = "statement_flow"
BASIS_CONSUMPTION_NET = "consumption_net"
BASIS_PERIOD_CASH_OUTFLOW = "period_cash_outflow"
BASES = frozenset(
    {BASIS_STATEMENT_FLOW, BASIS_CONSUMPTION_NET, BASIS_PERIOD_CASH_OUTFLOW}
)

# ---- 指标名 --------------------------------------------------------------------
METRIC_EXPENSE = "expense"
METRIC_INCOME = "income"
METRIC_NEUTRAL = "neutral"
METRIC_REFUND_RECEIVED = "refund_received"
METRIC_NET = "net"
METRICS = frozenset(
    {METRIC_EXPENSE, METRIC_INCOME, METRIC_NEUTRAL, METRIC_REFUND_RECEIVED, METRIC_NET}
)

GROUP_BY_MONTH = "month"
GROUP_BY_DAY = "day"
GROUP_BY_CATEGORY = "category"
GROUP_BY_MERCHANT = "merchant"
GROUP_BY_ACCOUNT = "account"
GROUP_BYS = frozenset(
    {GROUP_BY_MONTH, GROUP_BY_DAY, GROUP_BY_CATEGORY, GROUP_BY_MERCHANT, GROUP_BY_ACCOUNT}
)

OUTPUT_SUMMARY = "summary"
OUTPUT_TABLE = "table"
OUTPUT_CHART = "chart"
OUTPUT_PDF = "pdf"
OUTPUTS = frozenset({OUTPUT_SUMMARY, OUTPUT_TABLE, OUTPUT_CHART, OUTPUT_PDF})

# ---- 解析 ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    """canonical 字段 → 实际表头文本。只允许这些 canonical 键。"""

    occurred_at: str
    amount: str
    direction: str = ""
    tx_type: str = ""
    counterparty: str = ""
    product: str = ""
    status: str = ""
    external_id: str = ""
    merchant_id: str = ""
    note: str = ""
    pay_method: str = ""
    currency: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "occurred_at": self.occurred_at,
            "amount": self.amount,
            "direction": self.direction,
            "tx_type": self.tx_type,
            "counterparty": self.counterparty,
            "product": self.product,
            "status": self.status,
            "external_id": self.external_id,
            "merchant_id": self.merchant_id,
            "note": self.note,
            "pay_method": self.pay_method,
            "currency": self.currency,
        }


# 微信支付账单的常见列名（兼容“金额(元)”与“金额”两种写法）
WECHAT_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "occurred_at": ("交易时间", "时间", "交易日期"),
    "amount": ("金额(元)", "金额（元）", "金额", "金额(人民币)"),
    "direction": ("收/支", "收支", "收／支"),
    "tx_type": ("交易类型", "类型"),
    "counterparty": ("交易对方", "对方", "商户名称"),
    "product": ("商品", "商品说明", "商品名称"),
    "status": ("当前状态", "交易状态", "状态"),
    "external_id": ("交易单号", "微信支付订单号", "订单号"),
    "merchant_id": ("商户单号", "商户订单号"),
    "note": ("备注", "备注信息"),
    "pay_method": ("支付方式", "付款方式"),
    "currency": ("币种", "货币"),
}


@dataclass(frozen=True, slots=True)
class FormatMatch:
    """解析器对文件的判断；needs_mapping=True 时只能由用户显式给出列映射。"""

    format: str
    version: str
    confidence: float
    needs_mapping: bool = False
    mapping: ColumnMapping | None = None
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class ParsedRow:
    """一行标准化候选。金额/时间解析失败时保留原始值与错误，不静默丢弃。"""

    sheet: str
    row_number: int
    locator: str
    raw: Mapping[str, str]
    occurred_at: str | None
    amount_minor: int | None
    direction: str
    currency: str = "CNY"
    tx_type: str = ""
    counterparty: str = ""
    product: str = ""
    status: str = ""
    external_id: str = ""
    merchant_id: str = ""
    note: str = ""
    pay_method: str = ""
    event_role: str = EVENT_ROLE_PAYMENT
    id_reliable: bool = False
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors and self.amount_minor is not None and bool(self.occurred_at)


@dataclass(frozen=True, slots=True)
class ControlTotals:
    count: int | None = None
    income_minor: int | None = None
    expense_minor: int | None = None
    neutral_minor: int | None = None
    raw_lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlCheck:
    """控制总额核对结果：任一不符都不能直接提交，除非用户显式确认。"""

    ok: bool
    checked: bool
    mismatches: tuple[str, ...] = ()
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    format: str
    version: str
    rows: tuple[ParsedRow, ...]
    declared_from: str | None = None
    declared_to: str | None = None
    account_hint: str = ""
    currency: str = "CNY"
    control_totals: ControlTotals = field(default_factory=ControlTotals)
    warnings: tuple[str, ...] = ()
    truncated: bool = False


# ---- 导入/交易视图 ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImportView:
    import_id: str
    owner_id: int
    account_id: str
    file_id: str
    parser: str
    parser_version: str
    state: str
    declared_from: str | None
    declared_to: str | None
    coverage_kind: str
    currency: str
    revision: int
    row_counts: Mapping[str, Any] = field(default_factory=dict)
    control_totals: Mapping[str, Any] = field(default_factory=dict)
    quality: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TransactionView:
    transaction_id: str
    owner_id: int
    account_id: str
    external_id: str
    event_role: str
    amount_minor: int
    currency: str
    direction: str
    tx_type: str
    merchant: str
    product: str
    occurred_at: str
    status: str
    status_key: str
    category_id: str | None
    verification: str
    revision: int
    note: str = ""


@dataclass(frozen=True, slots=True)
class RefundLinkView:
    link_id: str
    refund_transaction_id: str
    original_transaction_id: str
    amount_minor: int
    match_method: str
    confirmation: str
    revision: int


@dataclass(frozen=True, slots=True)
class RefundSuggestion:
    """退款候选匹配：不自动确认，必须用户核对或命中同一可靠 ID。"""

    refund_transaction_id: str
    original_transaction_id: str
    amount_minor: int
    match_method: str
    confirmation: str
    reason: str = ""


# ---- 查询计划 ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Period:
    start: str | None = None
    end_exclusive: str | None = None
    timezone: str = "Asia/Shanghai"


@dataclass(frozen=True, slots=True)
class QueryFilters:
    directions: tuple[str, ...] = ()
    category_ids: tuple[str, ...] = ()
    merchants: tuple[str, ...] = ()
    min_amount_minor: int | None = None
    max_amount_minor: int | None = None
    include_unconfirmed_refunds: bool = False


@dataclass(frozen=True, slots=True)
class QueryPlan:
    version: int
    basis: str
    metrics: tuple[str, ...]
    scope: str = "all"  # all / account / import
    account_ids: tuple[str, ...] = ()
    import_ids: tuple[str, ...] = ()
    period: Period = field(default_factory=Period)
    group_by: tuple[str, ...] = ()
    filters: QueryFilters = field(default_factory=QueryFilters)
    top_n: int = 20
    output: str = OUTPUT_SUMMARY
    currency: str = "CNY"
    data_cutoff: str | None = None
    unsupported_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricResult:
    name: str
    amount_minor: int | None
    transaction_count: int = 0
    note: str = ""


@dataclass(frozen=True, slots=True)
class Coverage:
    start: str | None
    end_exclusive: str | None
    imports: tuple[str, ...]
    accounts: tuple[str, ...]
    category_names: tuple[str, ...]
    coverage_kind: str
    data_cutoff: str
    confidence: str = "high"
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analysis_id: str
    plan: QueryPlan
    basis: str
    currency: str
    metrics: tuple[MetricResult, ...]
    coverage: Coverage
    groups: tuple[Mapping[str, Any], ...] = ()
    transactions: tuple[TransactionView, ...] = ()
    warnings: tuple[str, ...] = ()
    data_cutoff: str = ""
    snapshot_revision: int = 0
    evidence: tuple[Mapping[str, str], ...] = ()


# ---- 图片提取 ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtractedField:
    value: str
    confidence: float
    source_text: str = ""
    needs_review: bool = False


@dataclass(frozen=True, slots=True)
class ImageCandidate:
    """图片识别候选：字段级置信度 + 原文 + 缺失字段，绝不直接入账。"""

    candidate_id: str
    image_file_id: str
    fields: Mapping[str, ExtractedField]
    missing_fields: tuple[str, ...]
    confidence: float
    raw_text: str
    merchant: str = ""
    amount_minor: int | None = None
    direction: str = DIRECTION_UNKNOWN
    occurred_at: str | None = None
    currency: str = "CNY"
    needs_review: bool = True
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommitResult:
    import_id: str
    state: str
    inserted: int
    updated: int
    unchanged: int
    conflicts: int
    skipped: int
    refund_links: int
    refund_suggestions: int
    duplicate: bool = False
    warnings: tuple[str, ...] = ()


def review_fields(candidate: ImageCandidate, min_confidence: float = 0.85) -> tuple[str, ...]:
    """返回需要用户核对的字段名（低置信度/缺失）。金额缺失时必然需要核对。"""
    needs: list[str] = []
    for name in ("amount", "occurred_at", "direction"):
        field_value = candidate.fields.get(name)
        if field_value is None or name in candidate.missing_fields:
            needs.append(name)
        elif field_value.needs_review or field_value.confidence < min_confidence:
            needs.append(name)
    if candidate.amount_minor is None and "amount" not in needs:
        needs.append("amount")
    return tuple(dict.fromkeys(needs))


def sum_minor(values: Sequence[int]) -> int:
    """金额求和只走整数；调用方不得用 float。"""
    return sum(int(v) for v in values)
