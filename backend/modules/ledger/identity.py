"""交易身份、去重、合并与状态机（设计 §8「账本模型、幂等和导入事务」）。

纯函数：不查库、不写日志、不抛业务异常（仅对非法 `Mapping` 抛 `TypeError`）。

身份只由「账户 + 事件角色 + 业务标识」决定：
- 绝不让行号、工作表名、文件路径、导入批次参与，否则同一笔交易在两次导出里
  行号不同就会被记成两笔；
- `event_role` 必须进 key：退款与原支付可能共用同一个交易单号（微信「同一订单
  退款」），只按 external_id 去重会让退款覆盖原支付；
- 标识不可靠（float 截断、科学计数法、全 0）时按商户单号 → 商户+金额+时间回退，
  并给出 `candidate` 提示：候选记录必须能在用户确认后升级，不能当作已核对。
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.modules.ledger.contracts import (
    DIRECTIONS,
    DIRECTION_UNKNOWN,
    EVENT_ROLE_PAYMENT,
    EVENT_ROLES,
    STATUS_CLOSED,
    STATUS_KEYS,
    STATUS_PAID,
    STATUS_REFUNDED_FULL,
    STATUS_REFUNDED_PARTIAL,
    STATUS_UNKNOWN,
    VERIFICATION_CANDIDATE,
    VERIFICATION_PARSED,
    ParsedRow,
)
from backend.modules.ledger.normalization import (
    clean_text,
    fingerprint,
    normalize_external_id,
    parse_occurred_at,
    status_key,
)

# ---- 身份方案（identity_key 前缀，审计时能看出这条记录靠什么去重） -----------------
IDENTITY_EXTERNAL_ID = "external_id"
IDENTITY_MERCHANT_ID = "merchant_id"
IDENTITY_COUNTERPARTY = "counterparty_amount_time"
IDENTITY_SCHEMES = frozenset(
    {IDENTITY_EXTERNAL_ID, IDENTITY_MERCHANT_ID, IDENTITY_COUNTERPARTY}
)

# ---- 去重结论 -----------------------------------------------------------------
DUPLICATE_SAME_IDENTITY = "same_identity"
DUPLICATE_CONTENT = "content_duplicate"
DUPLICATE_NEW = "new"
DUPLICATE_KINDS = frozenset(
    {DUPLICATE_SAME_IDENTITY, DUPLICATE_CONTENT, DUPLICATE_NEW}
)

# ---- 状态变更结论 -------------------------------------------------------------
TRANSITION_UPDATE = "update"
TRANSITION_KEEP = "keep"
TRANSITION_CONFLICT = "conflict"
TRANSITIONS = frozenset({TRANSITION_UPDATE, TRANSITION_KEEP, TRANSITION_CONFLICT})

# ---- 核对度提示 ---------------------------------------------------------------
HINT_PARSED = "parsed"
HINT_CANDIDATE = "candidate"
HINTS = frozenset({HINT_PARSED, HINT_CANDIDATE})

_SEP = "|"
_SCOPELESS_ACCOUNT = "unscoped"

# 允许前进的状态变更：退款只会越来越多，已关闭不会重新支付。
_FORWARD_TRANSITIONS = frozenset(
    {
        (STATUS_PAID, STATUS_REFUNDED_PARTIAL),
        (STATUS_PAID, STATUS_REFUNDED_FULL),
        (STATUS_PAID, STATUS_CLOSED),
        (STATUS_REFUNDED_PARTIAL, STATUS_REFUNDED_FULL),
    }
)

# 拒绝回退的状态变更：出现即说明上游状态不一致，交给审计告警而不是静默覆盖。
_CONFLICT_TRANSITIONS = frozenset(
    {
        (STATUS_REFUNDED_FULL, STATUS_PAID),
        (STATUS_REFUNDED_FULL, STATUS_REFUNDED_PARTIAL),
        (STATUS_CLOSED, STATUS_PAID),
        (STATUS_REFUNDED_FULL, STATUS_CLOSED),
        (STATUS_REFUNDED_PARTIAL, STATUS_CLOSED),
    }
)


# ---- 内部小工具 ---------------------------------------------------------------


def _int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _account_part(account_id: object) -> str:
    """账户标识参与身份；缺失时归入同一「无账户」作用域，而不是省略该段。"""
    return clean_text(account_id, limit=64) or _SCOPELESS_ACCOUNT


def _role_part(event_role: object) -> str:
    text = clean_text(event_role, limit=20)
    return text if text in EVENT_ROLES else EVENT_ROLE_PAYMENT


def _direction_part(direction: object) -> str:
    text = clean_text(direction, limit=20)
    return text if text in DIRECTIONS else DIRECTION_UNKNOWN


def _iso_text(value: object) -> str:
    """尽量把时间文本规范成 ISO；失败时只做空格→T 的轻量规整，不抛异常。"""
    text = clean_text(value, limit=40)
    if not text:
        return ""
    try:
        iso, error = parse_occurred_at(text)
    except (TypeError, ValueError, OverflowError):  # pragma: no cover - 防御性
        return text.replace(" ", "T")
    if error is not None or not iso:
        return text.replace(" ", "T")
    return iso


def _minute_bucket(value: object) -> str:
    """时间截到分钟：同一笔交易在不同导出里秒级抖动不应改变身份。"""
    return _iso_text(value)[:16]


def _timestamp_key(value: object) -> str:
    """内容指纹用完整时间（到秒）：同分钟的两笔同额消费仍是两笔交易。"""
    return _iso_text(value)


def _content_fingerprint(
    *,
    amount_minor: int | None,
    occurred_at: object,
    merchant: object,
    tx_type: object,
    direction: object,
) -> str:
    """内容指纹：同账户由调用方另判；刻意不含 event_role/status/external_id。"""
    return fingerprint(
        "" if amount_minor is None else int(amount_minor),
        _timestamp_key(occurred_at),
        clean_text(merchant, limit=120),
        clean_text(tx_type, limit=60),
        _direction_part(direction),
    )


def _row_from_mapping(existing: Mapping[str, Any]) -> ParsedRow:
    """把 `ledger_transactions` 行映射回 ParsedRow，复用同一套身份算法。"""
    occurred = existing.get("occurred_at")
    return ParsedRow(
        sheet="",
        row_number=0,
        locator="",
        raw={},
        occurred_at=None if occurred is None else str(occurred),
        amount_minor=_int_or_none(existing.get("amount_minor")),
        direction=str(existing.get("direction") or ""),
        tx_type=str(existing.get("tx_type") or ""),
        counterparty=str(existing.get("merchant") or ""),
        product=str(existing.get("product") or ""),
        status=str(existing.get("status") or ""),
        external_id=str(existing.get("external_id") or ""),
        merchant_id=str(existing.get("merchant_id") or ""),
        pay_method=str(existing.get("pay_method") or ""),
        event_role=str(existing.get("event_role") or EVENT_ROLE_PAYMENT),
    )


def _normalize_status_key(value: object) -> str:
    """接受规范化 key 或状态原文；空值统一成 unknown。"""
    text = clean_text(value, limit=40)
    if not text:
        return STATUS_UNKNOWN
    if text in STATUS_KEYS:
        return text
    return status_key(text)


def _existing_status_key(existing: Mapping[str, Any]) -> str:
    key = _normalize_status_key(existing.get("status_key"))
    if key == STATUS_UNKNOWN:
        # status_key 缺失/未识别时，用原文兜底，避免旧记录永远停在 unknown。
        derived = _normalize_status_key(existing.get("status"))
        if derived != STATUS_UNKNOWN:
            return derived
    return key


def _verification_hint(row: ParsedRow) -> str:
    """可靠 ID + 可解析金额/时间才算 parsed；其余一律 candidate。"""
    _external_id, reliable = normalize_external_id(row.external_id)
    if reliable and row.amount_minor is not None and clean_text(row.occurred_at, limit=40):
        return HINT_PARSED
    return HINT_CANDIDATE


# ---- 公开接口 -----------------------------------------------------------------


def identity_components(row: ParsedRow, *, account_id: str) -> tuple[str, tuple[str, ...]]:
    """返回 (身份方案, 参与身份的分量)。分量里绝不含行号/工作表/文件路径。

    方案优先级：
    1. 可靠交易单号 -> external_id；
    2. 可靠商户单号 -> merchant_id + 金额 + 分钟 + 方向；
    3. 兜底 -> 对方名称 + 金额 + 分钟 + 支付方式。
    """
    account = _account_part(account_id)
    role = _role_part(row.event_role)

    external_id, reliable = normalize_external_id(row.external_id)
    if reliable:
        return IDENTITY_EXTERNAL_ID, (account, role, external_id)

    amount = "" if row.amount_minor is None else str(int(row.amount_minor))
    minute = _minute_bucket(row.occurred_at)

    merchant_id, merchant_reliable = normalize_external_id(row.merchant_id)
    if merchant_reliable:
        return IDENTITY_MERCHANT_ID, (
            account,
            role,
            merchant_id,
            amount,
            minute,
            _direction_part(row.direction),
        )

    counterparty = clean_text(row.counterparty, limit=120)
    return IDENTITY_COUNTERPARTY, (
        account,
        role,
        counterparty,
        amount,
        minute,
        clean_text(row.pay_method, limit=40),
    )


def identity_key(row: ParsedRow, *, account_id: str) -> str:
    """稳定身份键：`<方案>:账户|事件角色|业务分量...`。

    同一行解析两次必须得到同一个 key；换账户、换事件角色必须是不同 key。
    """
    scheme, parts = identity_components(row, account_id=account_id)
    escaped = (part.replace(_SEP, "/") for part in parts)
    return scheme + ":" + _SEP.join(escaped)


def row_fingerprint(row: ParsedRow) -> str:
    """内容指纹：金额 + 发生时间（到秒）+ 对方 + 交易类型 + 方向。"""
    return _content_fingerprint(
        amount_minor=row.amount_minor,
        occurred_at=row.occurred_at,
        merchant=row.counterparty,
        tx_type=row.tx_type,
        direction=row.direction,
    )


def duplicate_kind(existing: Mapping[str, Any], row: ParsedRow, *, account_id: str) -> str:
    """判断候选行与已存在交易的关系：same_identity / content_duplicate / new。

    - same_identity：同账户、同事件角色、同身份（重复导出/重叠 CSV）；
    - content_duplicate：身份不同但内容指纹相同（换单号、同金额/时间/对方/类型），
      只能提示人工核对，不能直接吞并；
    - new：其余。
    """
    if not isinstance(existing, Mapping):
        return DUPLICATE_NEW

    existing_account = clean_text(existing.get("account_id"), limit=64)
    if existing_account and existing_account != _account_part(account_id):
        return DUPLICATE_NEW

    existing_row = _row_from_mapping(existing)
    if identity_key(existing_row, account_id=account_id) == identity_key(
        row, account_id=account_id
    ):
        return DUPLICATE_SAME_IDENTITY
    if row_fingerprint(existing_row) == row_fingerprint(row):
        return DUPLICATE_CONTENT
    return DUPLICATE_NEW


def merge_transaction(existing: Mapping[str, Any], row: ParsedRow) -> dict[str, Any]:
    """返回需要对既有记录执行的 UPDATE 字段；空 dict 表示「没有可安全更新」。

    只允许单调增强：
    - 状态按 `status_transition` 前进，冲突回退整条拒绝（返回 {} 由调用方记冲突）；
    - 金额/时间/方向冲突不覆盖，整条拒绝；
    - 空字段被非空字段补全（merchant/product/status/external_id）；
    - verification 只能 candidate → parsed，绝不把 parsed/confirmed 降级。
    """
    if not isinstance(existing, Mapping):
        raise TypeError("existing 必须是 Mapping")

    existing_amount = _int_or_none(existing.get("amount_minor"))
    if (
        existing_amount is not None
        and row.amount_minor is not None
        and existing_amount != int(row.amount_minor)
    ):
        return {}

    existing_occurred = clean_text(existing.get("occurred_at"), limit=40)
    row_occurred = clean_text(row.occurred_at, limit=40)
    if (
        existing_occurred
        and row_occurred
        and _timestamp_key(existing_occurred) != _timestamp_key(row_occurred)
    ):
        return {}

    existing_direction = _direction_part(existing.get("direction"))
    row_direction = _direction_part(row.direction)
    if (
        existing_direction != DIRECTION_UNKNOWN
        and row_direction != DIRECTION_UNKNOWN
        and existing_direction != row_direction
    ):
        return {}

    old_status_key = _existing_status_key(existing)
    new_status_key = _normalize_status_key(row.status)
    transition = status_transition(old_status_key, new_status_key)
    if transition == TRANSITION_CONFLICT:
        return {}

    updates: dict[str, Any] = {}
    if transition == TRANSITION_UPDATE and can_apply_status(row):
        updates["status"] = clean_text(row.status, limit=40)
        updates["status_key"] = new_status_key
    elif not clean_text(existing.get("status"), limit=40) and clean_text(row.status, limit=40):
        # 状态没前进，但旧记录状态原文缺失：只补文本，不动 status_key。
        updates["status"] = clean_text(row.status, limit=40)

    if not clean_text(existing.get("merchant"), limit=200):
        merchant = clean_text(row.counterparty, limit=200)
        if merchant:
            updates["merchant"] = merchant

    if not clean_text(existing.get("product"), limit=200):
        product = clean_text(row.product, limit=200)
        if product:
            updates["product"] = product

    if not clean_text(existing.get("external_id"), limit=64):
        external_id, reliable = normalize_external_id(row.external_id)
        if reliable:
            updates["external_id"] = external_id

    old_verification = clean_text(existing.get("verification"), limit=20)
    if old_verification == VERIFICATION_CANDIDATE and _verification_hint(row) == HINT_PARSED:
        updates["verification"] = VERIFICATION_PARSED

    return updates


def status_transition(old_status_key: str, new_status_key: str) -> str:
    """单调状态机：update / keep / conflict（拒绝回退供审计，不静默覆盖）。"""
    old = _normalize_status_key(old_status_key)
    new = _normalize_status_key(new_status_key)
    if old == new:
        return TRANSITION_KEEP
    if old == STATUS_UNKNOWN:
        return TRANSITION_UPDATE
    if (old, new) in _CONFLICT_TRANSITIONS:
        return TRANSITION_CONFLICT
    if (old, new) in _FORWARD_TRANSITIONS:
        return TRANSITION_UPDATE
    return TRANSITION_KEEP


def can_apply_status(row: ParsedRow) -> bool:
    """只有金额与发生时间都可解析的行才允许驱动状态更新。"""
    return row.amount_minor is not None and bool(clean_text(row.occurred_at, limit=40))


def choose_identity(row: ParsedRow, *, account_id: str) -> tuple[str, str]:
    """返回 (identity_key, verification_hint)；hint ∈ {parsed, candidate}。"""
    return identity_key(row, account_id=account_id), _verification_hint(row)


__all__ = [
    "DUPLICATE_CONTENT",
    "DUPLICATE_KINDS",
    "DUPLICATE_NEW",
    "DUPLICATE_SAME_IDENTITY",
    "HINT_CANDIDATE",
    "HINT_PARSED",
    "HINTS",
    "IDENTITY_COUNTERPARTY",
    "IDENTITY_EXTERNAL_ID",
    "IDENTITY_MERCHANT_ID",
    "IDENTITY_SCHEMES",
    "TRANSITION_CONFLICT",
    "TRANSITION_KEEP",
    "TRANSITION_UPDATE",
    "TRANSITIONS",
    "can_apply_status",
    "choose_identity",
    "duplicate_kind",
    "identity_components",
    "identity_key",
    "merge_transaction",
    "row_fingerprint",
    "status_transition",
]
