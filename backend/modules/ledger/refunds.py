"""退款匹配建议与退款额度校验（设计 §8/§9）。

纯函数：不查库、不写日志、不抛业务异常。原则是「宁可交给人工，也不猜」：
- 只有备注里出现原交易单号、或退款与原支付共用同一可靠交易单号时才 `confirmed`；
- 商户单号/金额+日期只是 `suggested`，必须用户核对；
- 同一规则命中多个原支付时一律不生成建议（不按「金额相同+日期相近」自动吞并）；
- 退款金额不得超过原支付剩余可退金额，累计超额直接拒绝。
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.modules.ledger.contracts import (
    CONFIRMATIONS,
    CONFIRMATION_CONFIRMED,
    CONFIRMATION_SUGGESTED,
    DIRECTION_EXPENSE,
    EVENT_ROLE_PAYMENT,
    EVENT_ROLE_REFUND,
    MATCH_AMOUNT_DATE,
    MATCH_MERCHANT_ID,
    MATCH_NOTE_REFERENCE,
    MATCH_SAME_EXTERNAL_ID,
    ParsedRow,
    RefundSuggestion,
)
from backend.modules.ledger.identity import row_fingerprint
from backend.modules.ledger.normalization import (
    clean_text,
    normalize_external_id,
    parse_occurred_at,
)

_REFERENCE_RE = re.compile(r"[0-9A-Za-z_-]{6,64}")
_SECONDS_PER_DAY = 86_400.0
_AMBIGUOUS: Any = object()  # 同一规则命中多个原支付


@dataclass(frozen=True, slots=True)
class _Original:
    """已入账原支付的只读视图，只保留匹配需要的字段。"""

    ref: str
    external_id: str
    merchant_id: str
    amount_minor: int
    moment: datetime | None
    counterparty: str


def _int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _moment(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        iso, error = parse_occurred_at(value)
    except (TypeError, ValueError, OverflowError):  # pragma: no cover - 防御性
        return None
    if error is not None or not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:  # pragma: no cover - parse_occurred_at 已保证 ISO
        return None


def _within_days(left: datetime | None, right: datetime | None, window_days: int) -> bool:
    if left is None or right is None:
        return False
    try:
        delta = left - right
    except TypeError:  # 一个带时区一个不带：无法可靠比较，按不匹配处理
        return False
    limit = max(0, int(window_days)) * _SECONDS_PER_DAY
    return abs(delta.total_seconds()) <= limit


def _note_tokens(note: object) -> set[str]:
    return {match.group(0) for match in _REFERENCE_RE.finditer(clean_text(note, limit=400))}


def _collect_originals(originals: Sequence[Mapping[str, Any]]) -> list[_Original]:
    collected: list[_Original] = []
    for item in originals or ():
        if not isinstance(item, Mapping):
            continue
        if str(item.get("event_role") or EVENT_ROLE_PAYMENT) != EVENT_ROLE_PAYMENT:
            continue
        if str(item.get("direction") or "") != DIRECTION_EXPENSE:
            continue
        ref = clean_text(item.get("id") or item.get("transaction_id"), limit=64)
        amount = _int_or_none(item.get("amount_minor"))
        if not ref or amount is None or amount <= 0:
            continue
        external_id, _reliable = normalize_external_id(item.get("external_id"))
        merchant_id, _merchant_reliable = normalize_external_id(item.get("merchant_id"))
        collected.append(
            _Original(
                ref=ref,
                external_id=external_id,
                merchant_id=merchant_id,
                amount_minor=amount,
                moment=_moment(item.get("occurred_at")),
                counterparty=clean_text(item.get("merchant"), limit=120),
            )
        )
    return collected


def _resolve(matches: Sequence[_Original]) -> Any:
    """唯一命中 → 该原支付；多个不同原支付 → _AMBIGUOUS；无命中 → None。"""
    if not matches:
        return None
    unique: dict[str, _Original] = {}
    for item in matches:
        unique.setdefault(item.ref, item)
    if len(unique) > 1:
        return _AMBIGUOUS
    return next(iter(unique.values()))


def _note_matches(row: ParsedRow, pool: Sequence[_Original]) -> list[_Original]:
    tokens = _note_tokens(row.note)
    if not tokens:
        return []
    return [item for item in pool if item.external_id and item.external_id in tokens]


def _external_id_matches(row: ParsedRow, pool: Sequence[_Original]) -> list[_Original]:
    refund_external_id, _reliable = normalize_external_id(row.external_id)
    if not refund_external_id:
        return []
    return [item for item in pool if item.external_id == refund_external_id]


def _merchant_id_matches(row: ParsedRow, pool: Sequence[_Original]) -> list[_Original]:
    refund_merchant_id, _reliable = normalize_external_id(row.merchant_id)
    if not refund_merchant_id:
        return []
    return [item for item in pool if item.merchant_id == refund_merchant_id]


def _amount_date_matches(
    row: ParsedRow, pool: Sequence[_Original], *, window_days: int
) -> list[_Original]:
    amount = int(row.amount_minor or 0)
    name = clean_text(row.counterparty, limit=120).casefold()
    moment = _moment(row.occurred_at)
    if not name or moment is None:
        return []
    return [
        item
        for item in pool
        if item.amount_minor == amount
        and item.counterparty.casefold() == name
        and _within_days(moment, item.moment, window_days)
    ]


def _build(
    row: ParsedRow,
    original: _Original,
    *,
    match_method: str,
    confirmation: str,
    reason: str,
) -> RefundSuggestion:
    return RefundSuggestion(
        refund_transaction_id=refund_row_reference(row),
        original_transaction_id=original.ref,
        amount_minor=int(row.amount_minor or 0),
        match_method=match_method,
        confirmation=confirmation,
        reason=reason,
    )


def _suggest_for_row(
    row: ParsedRow, originals: Sequence[_Original], *, window_days: int
) -> RefundSuggestion | None:
    amount = int(row.amount_minor or 0)
    # 退款不可能大于原支付金额：先把这类候选整体剔除（剩余额度校验在 validate_link）。
    pool = [item for item in originals if amount <= item.amount_minor]
    if not pool:
        return None

    target = _resolve(_note_matches(row, pool))
    if target is _AMBIGUOUS:
        return None
    if target is not None:
        return _build(
            row,
            target,
            match_method=MATCH_NOTE_REFERENCE,
            confirmation=CONFIRMATION_CONFIRMED,
            reason="退款备注包含原交易单号",
        )

    target = _resolve(_external_id_matches(row, pool))
    if target is _AMBIGUOUS:
        return None
    if target is not None:
        return _build(
            row,
            target,
            match_method=MATCH_SAME_EXTERNAL_ID,
            confirmation=CONFIRMATION_CONFIRMED,
            reason="退款与原支付使用同一交易单号",
        )

    target = _resolve(_merchant_id_matches(row, pool))
    if target is _AMBIGUOUS:
        return None
    if target is not None:
        return _build(
            row,
            target,
            match_method=MATCH_MERCHANT_ID,
            confirmation=CONFIRMATION_SUGGESTED,
            reason="商户单号相同，需人工确认",
        )

    target = _resolve(_amount_date_matches(row, pool, window_days=window_days))
    if target is _AMBIGUOUS:
        return None
    if target is not None:
        return _build(
            row,
            target,
            match_method=MATCH_AMOUNT_DATE,
            confirmation=CONFIRMATION_SUGGESTED,
            reason="金额相同且发生时间在匹配窗口内，需人工确认",
        )
    return None


def refund_row_reference(row: ParsedRow) -> str:
    """退款候选的稳定引用：优先显式 transaction_id，否则用内容指纹。

    `ParsedRow` 是提交前的候选，没有数据库主键；调用方按该引用回查/回填
    真实 transaction_id。同一内容重复导出会得到同一引用（利于去重）。
    """
    explicit = clean_text(getattr(row, "transaction_id", ""), limit=64)
    if explicit:
        return explicit
    return "parsed:" + row_fingerprint(row)


def is_refund_row(row: ParsedRow) -> bool:
    """退款行：event_role 为 refund 且金额为正（方向由账单原文决定）。"""
    return (
        row.event_role == EVENT_ROLE_REFUND
        and row.amount_minor is not None
        and int(row.amount_minor) > 0
    )


def suggest_refund_links(
    refunds: Sequence[ParsedRow],
    originals: Sequence[Mapping[str, Any]],
    *,
    window_days: int = 180,
) -> list[RefundSuggestion]:
    """为退款行建议唯一原支付；找不到或命中多个候选时不生成建议。

    匹配顺序：备注原交易单号 → 同一交易单号 → 商户单号 → 金额+日期+对方。
    前两者可 `confirmed`，后两者只能是 `suggested`。
    """
    pool = _collect_originals(originals)
    if not pool:
        return []
    suggestions: list[RefundSuggestion] = []
    for row in refunds or ():
        if not is_refund_row(row):
            continue
        suggestion = _suggest_for_row(row, pool, window_days=window_days)
        if suggestion is not None:
            suggestions.append(suggestion)
    return suggestions


def link_capacity(original_amount_minor: int, existing_amounts: Sequence[int]) -> int:
    """原支付剩余可退金额 = 原金额 − 已占用退款合计，最小 0。"""
    original = int(original_amount_minor or 0)
    used = 0
    for value in existing_amounts or ():
        amount = _int_or_none(value)
        if amount is not None and amount > 0:
            used += amount
    return max(0, original - used)


def validate_link(
    *,
    refund_amount_minor: int,
    original_amount_minor: int,
    existing_amounts: Sequence[int],
) -> tuple[bool, str]:
    """校验一笔退款能否挂到原支付上；返回 (是否允许, 拒绝原因)。"""
    amount = _int_or_none(refund_amount_minor)
    if amount is None or amount <= 0:
        return False, "退款金额必须为正数"
    original = int(original_amount_minor or 0)
    if original <= 0:
        return False, "原支付金额非法"
    if amount > link_capacity(original, existing_amounts):
        return False, "退款金额超过原支付剩余可退金额"
    return True, ""


def refund_balance(original_amount_minor: int, links: Sequence[Mapping[str, Any]]) -> int:
    """原支付剩余可退金额（含 suggested）；已拒绝/非法确认度的关联不计入。"""
    original = int(original_amount_minor or 0)
    used = 0
    for link in links or ():
        if not isinstance(link, Mapping):
            continue
        amount = _int_or_none(link.get("amount_minor"))
        if amount is None:
            continue
        confirmation = clean_text(link.get("confirmation"), limit=20)
        if confirmation and confirmation not in CONFIRMATIONS:
            continue
        if amount > 0:
            used += amount
    return max(0, original - used)


__all__ = [
    "is_refund_row",
    "link_capacity",
    "refund_balance",
    "refund_row_reference",
    "suggest_refund_links",
    "validate_link",
]
