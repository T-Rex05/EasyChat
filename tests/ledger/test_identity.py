"""F5：交易身份/去重/状态合并/退款匹配的纯函数测试。

全部使用虚构夹具；不读真实账单、不访问网络、不碰数据库。
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from backend.modules.ledger.contracts import (
    CONFIRMATION_CONFIRMED,
    CONFIRMATION_SUGGESTED,
    EVENT_ROLE_PAYMENT,
    EVENT_ROLE_REFUND,
    STATUS_CLOSED,
    STATUS_PAID,
    STATUS_PENDING,
    STATUS_REFUNDED_FULL,
    STATUS_REFUNDED_PARTIAL,
    STATUS_UNKNOWN,
    ParsedRow,
)
from backend.modules.ledger.identity import (
    DUPLICATE_CONTENT,
    DUPLICATE_NEW,
    DUPLICATE_SAME_IDENTITY,
    DUPLICATE_KINDS,
    HINT_CANDIDATE,
    HINT_PARSED,
    IDENTITY_COUNTERPARTY,
    IDENTITY_EXTERNAL_ID,
    can_apply_status,
    choose_identity,
    duplicate_kind,
    identity_components,
    identity_key,
    merge_transaction,
    row_fingerprint,
    status_transition,
)
from backend.modules.ledger.normalization import (
    classify_event_role,
    normalize_direction,
    normalize_external_id,
    parse_money,
    parse_occurred_at,
    status_key,
)
from backend.modules.ledger.refunds import (
    is_refund_row,
    link_capacity,
    refund_balance,
    refund_row_reference,
    suggest_refund_links,
    validate_link,
)
from tests.support import ledger_fixtures as fx

ACCOUNT = "acct-demo"


# ---- 夹具适配 -----------------------------------------------------------------


def _row(
    bill: fx.BillRow,
    *,
    row_number: int = 2,
    sheet: str = "Sheet1",
    role: str | None = None,
    external_id: str | None = None,
    merchant_id: str | None = None,
) -> ParsedRow:
    """BillRow → ParsedRow（走真实标准化函数，不手工拼字符串）。

    `role` 允许显式指定事件角色：`classify_event_role` 会把「已全额退款」这类
    状态文本判成 refund，而测试里需要「状态已退款、但仍是原支付」的行。
    """
    amount, currency, amount_error = parse_money(bill.amount)
    occurred, occurred_error = parse_occurred_at(bill.occurred)
    direction = normalize_direction(bill.direction)
    raw_external_id = bill.tx_id if external_id is None else external_id
    normalized_id, reliable = normalize_external_id(raw_external_id)
    errors = tuple(err for err in (amount_error, occurred_error) if err)
    event_role = role or classify_event_role(bill.type, direction, bill.status, bill.product)
    return ParsedRow(
        sheet=sheet,
        row_number=row_number,
        locator=f"{sheet}!A{row_number}",
        raw=bill.as_dict(),
        occurred_at=occurred,
        amount_minor=amount,
        direction=direction,
        currency=currency,
        tx_type=bill.type,
        counterparty=bill.counterparty,
        product=bill.product,
        status=bill.status,
        external_id=normalized_id or raw_external_id,
        merchant_id=bill.merchant_id if merchant_id is None else merchant_id,
        note=bill.note,
        pay_method=bill.pay_method,
        event_role=event_role,
        id_reliable=reliable,
        errors=errors,
    )


def _mapping(
    row: ParsedRow,
    *,
    transaction_id: str = "tx-1",
    account_id: str = ACCOUNT,
    **overrides: object,
) -> dict[str, object]:
    """ParsedRow → 模拟 ledger_transactions 行（键与列一致）。"""
    data: dict[str, object] = {
        "id": transaction_id,
        "transaction_id": transaction_id,
        "account_id": account_id,
        "amount_minor": row.amount_minor,
        "occurred_at": row.occurred_at,
        "merchant": row.counterparty,
        "external_id": row.external_id,
        "merchant_id": row.merchant_id,
        "direction": row.direction,
        "event_role": row.event_role,
        "status": row.status,
        "status_key": status_key(row.status),
        "verification": "parsed",
        "tx_type": row.tx_type,
        "product": row.product,
    }
    data.update(overrides)
    return data


# ---- 身份 ---------------------------------------------------------------------


def test_identity_key_is_stable_and_account_scoped():
    bill = fx.standard_scenario()[0]
    first = _row(bill)
    again = replace(first, row_number=99, sheet="Sheet2", locator="Sheet2!A99")

    assert identity_key(first, account_id=ACCOUNT) == identity_key(again, account_id=ACCOUNT)
    assert identity_key(first, account_id=ACCOUNT) != identity_key(first, account_id="acct-other")

    scheme, parts = identity_components(first, account_id=ACCOUNT)
    assert scheme == IDENTITY_EXTERNAL_ID
    assert parts[0] == ACCOUNT
    assert parts[1] == EVENT_ROLE_PAYMENT


def test_identity_key_preserves_28_digit_external_id():
    bill = fx.standard_scenario()[0]
    row = _row(bill)

    assert len(fx.LONG_TX_ID) == 28
    assert row.external_id == fx.LONG_TX_ID
    key, hint = choose_identity(row, account_id=ACCOUNT)
    assert fx.LONG_TX_ID in key
    assert hint == HINT_PARSED


def test_float_truncated_external_id_falls_back_to_candidate():
    bill = fx.standard_scenario()[0]
    row = _row(bill, external_id="4.20000123420261e+27")

    _normalized, reliable = normalize_external_id(row.external_id)
    assert reliable is False
    key, hint = choose_identity(row, account_id=ACCOUNT)
    assert hint == HINT_CANDIDATE
    # 回退到商户单号，绝不把截断的 ID 当身份
    assert fx.LONG_MERCHANT_ID in key
    assert "e+27" not in key


def test_payment_and_refund_sharing_external_id_have_distinct_keys():
    original_bill, refund_bill = fx.same_id_refund_scenario()
    original = _row(original_bill, role=EVENT_ROLE_PAYMENT)
    refund = _row(refund_bill, role=EVENT_ROLE_REFUND)

    assert original.external_id == refund.external_id
    assert identity_key(original, account_id=ACCOUNT) != identity_key(refund, account_id=ACCOUNT)
    assert duplicate_kind(_mapping(original), refund, account_id=ACCOUNT) != DUPLICATE_SAME_IDENTITY


def test_identity_without_ids_uses_merchant_amount_and_minute():
    bill = fx.standard_scenario()[0]
    row = _row(bill, external_id="", merchant_id="")
    moved = replace(row, row_number=50, sheet="Other", locator="Other!A50")

    assert identity_key(row, account_id=ACCOUNT) == identity_key(moved, account_id=ACCOUNT)
    scheme, parts = identity_components(row, account_id=ACCOUNT)
    assert scheme == IDENTITY_COUNTERPARTY
    assert parts[0] == ACCOUNT
    assert parts[1] == EVENT_ROLE_PAYMENT
    assert parts[2] == "示例便利店"
    assert parts[3] == "10000"
    assert parts[4] == "2026-10-02T12:00"
    assert "A2" not in identity_key(row, account_id=ACCOUNT)


def test_row_fingerprint_is_content_only():
    bill = fx.standard_scenario()[0]
    row = _row(bill)
    moved = replace(row, row_number=77, sheet="S2", locator="S2!A77")

    assert row_fingerprint(row) == row_fingerprint(moved)
    assert row_fingerprint(row) != row_fingerprint(replace(row, amount_minor=999))


def test_overlap_export_detects_same_identity_and_new_rows():
    first_export = fx.overlap_export_scenario()
    row_a = _row(first_export[0], row_number=2)
    row_b = _row(first_export[1], row_number=3)
    existing_a = _mapping(row_a, transaction_id="tx-a")

    assert duplicate_kind(existing_a, replace(row_a, row_number=40), account_id=ACCOUNT) == (
        DUPLICATE_SAME_IDENTITY
    )
    assert duplicate_kind(existing_a, row_b, account_id=ACCOUNT) == DUPLICATE_NEW
    # 账户不同就是新交易，不能跨账户合并
    assert duplicate_kind(existing_a, row_a, account_id="acct-other") == DUPLICATE_NEW
    assert {DUPLICATE_SAME_IDENTITY, DUPLICATE_CONTENT, DUPLICATE_NEW} == DUPLICATE_KINDS


def test_content_duplicate_when_external_id_changes():
    bill = fx.standard_scenario()[0]
    row = _row(bill)
    existing = _mapping(row, external_id="OTHER0000000000000000000001")

    assert existing["external_id"] != row.external_id
    assert duplicate_kind(existing, row, account_id=ACCOUNT) == DUPLICATE_CONTENT


# ---- 状态机与合并 --------------------------------------------------------------


def test_status_transition_is_monotonic():
    assert status_transition(STATUS_PAID, STATUS_REFUNDED_PARTIAL) == "update"
    assert status_transition(STATUS_REFUNDED_PARTIAL, STATUS_REFUNDED_FULL) == "update"
    assert status_transition(STATUS_PAID, STATUS_PAID) == "keep"
    assert status_transition(STATUS_UNKNOWN, STATUS_PAID) == "update"
    assert status_transition(STATUS_REFUNDED_FULL, STATUS_PAID) == "conflict"
    assert status_transition(STATUS_CLOSED, STATUS_PAID) == "conflict"
    assert status_transition(STATUS_PAID, STATUS_PENDING) == "keep"


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (STATUS_PAID, STATUS_REFUNDED_FULL, "update"),
        (STATUS_PAID, STATUS_CLOSED, "update"),
        ("", STATUS_PAID, "update"),
        (STATUS_UNKNOWN, STATUS_REFUNDED_FULL, "update"),
        (STATUS_REFUNDED_FULL, STATUS_REFUNDED_PARTIAL, "conflict"),
        (STATUS_REFUNDED_PARTIAL, STATUS_CLOSED, "conflict"),
        (STATUS_REFUNDED_FULL, STATUS_CLOSED, "conflict"),
        (STATUS_CLOSED, STATUS_REFUNDED_FULL, "keep"),
        ("支付成功", STATUS_REFUNDED_PARTIAL, "update"),
    ],
)
def test_status_transition_table(old, new, expected):
    assert status_transition(old, new) == expected


def test_merge_transaction_applies_status_progression():
    bill = fx.standard_scenario()[0]
    base = _row(bill, role=EVENT_ROLE_PAYMENT)
    existing = _mapping(base)
    assert existing["status_key"] == STATUS_PAID

    partial_updates = merge_transaction(existing, replace(base, status="已部分退款"))
    assert set(partial_updates) == {"status", "status_key"}
    assert partial_updates["status_key"] == STATUS_REFUNDED_PARTIAL
    merged = {**existing, **partial_updates}
    assert merged["status"] == "已部分退款"

    full_updates = merge_transaction(merged, replace(base, status="已全额退款"))
    assert full_updates["status_key"] == STATUS_REFUNDED_FULL
    final = {**merged, **full_updates}
    assert final["status"] == "已全额退款"
    # 已全额退款 → 支付成功 属于回退：不覆盖、只冲突
    assert merge_transaction(final, replace(base, status="支付成功")) == {}


def test_merge_transaction_rejects_status_rollback():
    bill = fx.standard_scenario()[0]
    row = _row(bill, role=EVENT_ROLE_PAYMENT)
    existing = _mapping(row, status="已全额退款", status_key=STATUS_REFUNDED_FULL)

    assert status_transition(STATUS_REFUNDED_FULL, STATUS_PAID) == "conflict"
    assert merge_transaction(existing, replace(row, status="支付成功")) == {}


def test_merge_transaction_never_blanks_or_downgrades():
    bill = fx.standard_scenario()[0]
    row = _row(bill, role=EVENT_ROLE_PAYMENT)
    existing = _mapping(row)
    sparse = replace(row, counterparty="", product="", external_id="", note="", merchant_id="")

    # 空值不能覆盖旧值，候选也不能把 parsed 降级
    assert merge_transaction(existing, sparse) == {}


def test_merge_transaction_upgrades_candidate_and_fills_empty_fields():
    bill = fx.standard_scenario()[0]
    row = _row(bill, role=EVENT_ROLE_PAYMENT)
    weak = _mapping(row, verification="candidate", external_id="", merchant="", product="")

    updates = merge_transaction(weak, row)

    assert updates["verification"] == "parsed"
    assert updates["merchant"] == "示例便利店"
    assert updates["product"] == "矿泉水"
    assert updates["external_id"] == fx.LONG_TX_ID
    assert merge_transaction(_mapping(row, verification="confirmed"), row).get("verification") is None


def test_merge_transaction_refuses_amount_time_and_direction_conflicts():
    bill = fx.standard_scenario()[0]
    row = _row(bill, role=EVENT_ROLE_PAYMENT)

    assert merge_transaction(_mapping(row, amount_minor=12345), row) == {}
    assert merge_transaction(
        _mapping(row, occurred_at="2026-10-02T13:00:00+08:00"), row
    ) == {}
    assert merge_transaction(_mapping(row, direction="income"), row) == {}


def test_can_apply_status_requires_amount_and_time():
    row = _row(fx.standard_scenario()[0], role=EVENT_ROLE_PAYMENT)

    assert can_apply_status(row) is True
    assert can_apply_status(replace(row, amount_minor=None)) is False
    assert can_apply_status(replace(row, occurred_at=None)) is False


# ---- 退款匹配 -----------------------------------------------------------------


def test_is_refund_row_requires_refund_role_and_positive_amount():
    original_bill, refund_bill = fx.same_id_refund_scenario()

    refund = _row(refund_bill, role=EVENT_ROLE_REFUND)
    assert is_refund_row(refund) is True
    assert is_refund_row(_row(original_bill, role=EVENT_ROLE_PAYMENT)) is False
    assert is_refund_row(replace(refund, amount_minor=0)) is False
    assert is_refund_row(replace(refund, amount_minor=None)) is False


def test_full_refund_scenario_matches_original():
    original_bill, refund_bill = fx.full_refund_scenario()
    original = _row(original_bill, role=EVENT_ROLE_PAYMENT)
    refund = _row(refund_bill, role=EVENT_ROLE_REFUND)

    suggestions = suggest_refund_links([refund], [_mapping(original, transaction_id="tx-original")])

    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.original_transaction_id == "tx-original"
    assert suggestion.amount_minor == 10_000
    assert suggestion.match_method in {"same_external_id", "note_reference"}
    assert suggestion.confirmation == CONFIRMATION_CONFIRMED
    assert suggestion.refund_transaction_id


def test_standard_scenario_partial_refund_matches_by_note_reference():
    rows = fx.standard_scenario()
    original = _row(rows[0], role=EVENT_ROLE_PAYMENT)
    refund = _row(rows[1], role=EVENT_ROLE_REFUND)
    transfer = _row(rows[2], role=EVENT_ROLE_PAYMENT)

    assert refund.amount_minor == 3_000
    originals = [
        _mapping(original, transaction_id="tx-100"),
        _mapping(transfer, transaction_id="tx-transfer"),
    ]
    suggestions = suggest_refund_links([refund], originals)

    assert len(suggestions) == 1
    assert suggestions[0].match_method == "note_reference"
    assert suggestions[0].confirmation == CONFIRMATION_CONFIRMED
    assert suggestions[0].original_transaction_id == "tx-100"
    assert suggestions[0].reason == "退款备注包含原交易单号"
    # 50 元转账不参与这次退款匹配
    assert all(item.original_transaction_id != "tx-transfer" for item in suggestions)


def test_refund_with_same_external_id_is_confirmed():
    original_bill, refund_bill = fx.same_id_refund_scenario()
    original = _row(original_bill, role=EVENT_ROLE_PAYMENT)
    refund = _row(refund_bill, role=EVENT_ROLE_REFUND)

    suggestions = suggest_refund_links([refund], [_mapping(original, transaction_id="tx-shared")])

    assert len(suggestions) == 1
    assert suggestions[0].match_method == "same_external_id"
    assert suggestions[0].confirmation == CONFIRMATION_CONFIRMED
    assert suggestions[0].original_transaction_id == "tx-shared"


def test_merchant_id_match_is_only_suggested():
    rows = fx.standard_scenario()
    original = _row(rows[0], role=EVENT_ROLE_PAYMENT)
    refund = replace(
        _row(rows[1], role=EVENT_ROLE_REFUND),
        note="",
        external_id="",
    )

    suggestions = suggest_refund_links([refund], [_mapping(original, transaction_id="tx-100")])

    assert len(suggestions) == 1
    assert suggestions[0].match_method == "merchant_id"
    assert suggestions[0].confirmation == CONFIRMATION_SUGGESTED


def test_multiple_candidates_produce_no_suggestion():
    bill = fx.standard_scenario()[0]
    refund_bill = fx.BillRow(
        occurred="2026-10-06 10:00:00",
        type="退款",
        counterparty="示例便利店",
        product="退款",
        direction="收入",
        amount="100.00",
        status="已退款",
        tx_id="RFD00000000000000000000000009",
        merchant_id="",
        note="",
    )
    refund = _row(refund_bill, role=EVENT_ROLE_REFUND)
    first = _mapping(
        _row(bill, role=EVENT_ROLE_PAYMENT),
        transaction_id="tx-1",
        external_id="ID00000000000000000000000A",
        merchant_id="",
    )
    second = _mapping(
        _row(bill, role=EVENT_ROLE_PAYMENT),
        transaction_id="tx-2",
        external_id="ID00000000000000000000000B",
        merchant_id="",
    )

    assert suggest_refund_links([refund], [first, second]) == []


def test_refund_amount_above_original_gets_no_suggestion():
    rows = fx.standard_scenario()
    original = _row(rows[0], role=EVENT_ROLE_PAYMENT)
    refund = replace(
        _row(rows[1], role=EVENT_ROLE_REFUND),
        amount_minor=20_000,
        note=f"原交易单号 {fx.LONG_TX_ID}",
    )

    assert suggest_refund_links([refund], [_mapping(original, transaction_id="tx-100")]) == []


def test_refund_row_reference_is_stable_and_not_a_row_number():
    rows = fx.standard_scenario()
    refund = _row(rows[1], role=EVENT_ROLE_REFUND, row_number=2)
    moved = replace(refund, row_number=81, locator="Sheet1!A81")

    assert refund_row_reference(refund) == refund_row_reference(moved)
    assert "A2" not in refund_row_reference(refund)


# ---- 额度校验 -----------------------------------------------------------------


def test_validate_link_rejects_over_amount():
    allowed, reason = validate_link(
        refund_amount_minor=5_000, original_amount_minor=10_000, existing_amounts=[]
    )
    assert (allowed, reason) == (True, "")

    allowed, reason = validate_link(
        refund_amount_minor=12_000, original_amount_minor=10_000, existing_amounts=[]
    )
    assert allowed is False
    assert "超过" in reason

    allowed, _reason = validate_link(
        refund_amount_minor=3_000, original_amount_minor=10_000, existing_amounts=[8_000]
    )
    assert allowed is False

    allowed, reason = validate_link(
        refund_amount_minor=0, original_amount_minor=10_000, existing_amounts=[]
    )
    assert allowed is False
    assert "正数" in reason


def test_two_partial_refunds_stay_within_original():
    assert validate_link(
        refund_amount_minor=3_000, original_amount_minor=10_000, existing_amounts=[]
    ) == (True, "")
    assert validate_link(
        refund_amount_minor=7_000, original_amount_minor=10_000, existing_amounts=[3_000]
    ) == (True, "")

    allowed, _reason = validate_link(
        refund_amount_minor=1, original_amount_minor=10_000, existing_amounts=[3_000, 7_000]
    )
    assert allowed is False
    assert link_capacity(10_000, [3_000, 7_000]) == 0
    assert link_capacity(10_000, [3_000]) == 7_000
    assert link_capacity(10_000, []) == 10_000


def test_refund_balance_clamps_to_zero():
    assert refund_balance(10_000, []) == 10_000
    assert refund_balance(10_000, [{"amount_minor": 3_000, "confirmation": "confirmed"}]) == 7_000
    assert (
        refund_balance(
            10_000,
            [
                {"amount_minor": 3_000, "confirmation": "suggested"},
                {"amount_minor": 7_000, "confirmation": "confirmed"},
            ],
        )
        == 0
    )
    assert refund_balance(10_000, [{"amount_minor": 12_000, "confirmation": "confirmed"}]) == 0
    assert refund_balance(10_000, [{"amount_minor": 5_000, "confirmation": "rejected"}]) == 10_000
