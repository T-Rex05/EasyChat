"""F4 解析器测试：表头不定行、编码/分隔符、控制总额、坏行保留、截断、格式探测。

全部使用 tests/support/ledger_fixtures.py 的合成账单（虚构商户/单号）。
"""
from __future__ import annotations

import pytest

from backend.modules.ledger.contracts import ColumnMapping
from backend.modules.ledger.parsers import (
    BillParseError, ParseOptions, detect_format, parse_saved_file,
)
from backend.modules.ledger.parsers.wechat_csv import parse_wechat_csv
from backend.modules.ledger.parsers.wechat_xlsx import parse_wechat_xlsx
from tests.support.ledger_fixtures import (
    BillRow,
    LONG_TX_ID,
    WECHAT_COLUMNS,
    mismatched_control_totals,
    standard_scenario,
    write_generic_csv,
    write_quoted_multiline_csv,
    write_wechat_csv,
    write_wechat_xlsx,
)


def _parse(path, *, name=None, mapping=None, max_rows=100_000):
    return parse_saved_file(
        path, file_name=name or path.name, mime="",
        options=ParseOptions(max_rows=max_rows, mapping=mapping),
    )


def _options():
    return ParseOptions(max_rows=100_000)


@pytest.mark.parametrize("header_row", [3, 7, 12])
def test_header_position_is_detected_by_content(tmp_path, header_row):
    path = write_wechat_xlsx(
        tmp_path / f"h{header_row}.xlsx", standard_scenario(), header_row=header_row,
    )
    statement = _parse(path)
    assert len(statement.rows) == 4
    assert statement.rows[0].amount_minor == 10000
    assert statement.rows[0].occurred_at.startswith("2026-10-02T12:00:00")
    assert statement.format == "wechat_xlsx"


def test_long_transaction_id_is_not_truncated(tmp_path):
    path = write_wechat_xlsx(tmp_path / "long.xlsx", standard_scenario())
    statement = _parse(path)
    first = statement.rows[0]
    assert first.external_id == LONG_TX_ID
    assert first.id_reliable is True
    assert len(first.external_id) == 28


def test_extra_sheets_are_parsed_with_sheet_in_locator(tmp_path):
    extra = {
        "退款明细": (
            BillRow(occurred="2026-10-05 09:30:00", type="退款", direction="收入",
                    product="退款", amount="30.00", status="已退款",
                    tx_id="RFDX000000000000000000000001"),
        )
    }
    path = write_wechat_xlsx(tmp_path / "multi.xlsx", standard_scenario(), extra_sheets=extra)
    statement = _parse(path)
    assert len(statement.rows) == 5
    refund_rows = [row for row in statement.rows if row.sheet == "退款明细"]
    assert len(refund_rows) == 1
    assert refund_rows[0].locator.startswith("退款明细:")


def test_standard_scenario_roles_and_directions(tmp_path):
    path = write_wechat_xlsx(tmp_path / "roles.xlsx", standard_scenario())
    statement = _parse(path)
    by_amount = {row.amount_minor: row for row in statement.rows}
    assert by_amount[10000].event_role == "payment"
    assert by_amount[10000].direction == "expense"
    assert by_amount[3000].event_role == "refund"
    assert by_amount[3000].direction == "income"
    assert by_amount[5000].event_role == "payment"
    assert by_amount[20000].event_role == "neutral"
    assert by_amount[20000].direction == "unknown"


def test_control_totals_are_extracted(tmp_path):
    path = write_wechat_xlsx(tmp_path / "totals.xlsx", standard_scenario())
    totals = _parse(path).control_totals
    assert totals.count == 4
    assert totals.expense_minor == 15000
    assert totals.income_minor == 3000
    assert totals.neutral_minor == 20000
    assert totals.raw_lines


def test_mismatched_totals_are_reported_not_rejected(tmp_path):
    path = write_wechat_xlsx(
        tmp_path / "bad-totals.xlsx", standard_scenario(),
        control_totals=mismatched_control_totals(),
    )
    totals = _parse(path).control_totals
    assert totals.count == 99
    assert totals.expense_minor == 999999


@pytest.mark.parametrize(
    "encoding,delimiter",
    [("utf-8-sig", ","), ("gb18030", ","), ("utf-8", "\t")],
)
def test_csv_encodings_and_delimiters(tmp_path, encoding, delimiter):
    path = write_wechat_csv(
        tmp_path / f"bills-{encoding}.csv", standard_scenario(),
        encoding=encoding, delimiter=delimiter,
    )
    statement = _parse(path)
    assert statement.format == "wechat_csv"
    assert len(statement.rows) == 4
    assert statement.rows[0].amount_minor == 10000
    assert statement.rows[0].external_id == LONG_TX_ID


def test_quoted_multiline_fields_do_not_shift_rows(tmp_path):
    path = write_quoted_multiline_csv(tmp_path / "quoted.csv")
    statement = _parse(path)
    assert len(statement.rows) == 1
    row = statement.rows[0]
    assert "第一行" in row.product and "第二行" in row.product
    assert row.amount_minor == 1234


def test_invalid_rows_are_kept_with_errors(tmp_path):
    rows = (
        BillRow(occurred="2026-10-02 12:00:00", amount="12.00",
                tx_id="OK00000000000000000000000001"),
        BillRow(occurred="不是时间", amount="abc", tx_id="BAD0000000000000000000000001"),
    )
    path = write_wechat_xlsx(tmp_path / "bad.xlsx", rows, control_totals={})
    statement = _parse(path)
    assert len(statement.rows) == 2
    bad = statement.rows[1]
    assert bad.errors
    assert bad.amount_minor is None
    assert bad.occurred_at is None


def test_max_rows_truncates_with_warning(tmp_path):
    path = write_wechat_xlsx(tmp_path / "many.xlsx", standard_scenario())
    statement = _parse(path, max_rows=2)
    assert len(statement.rows) == 2
    assert statement.truncated is True
    assert statement.warnings


def test_detect_format_variants(tmp_path):
    xlsx = write_wechat_xlsx(tmp_path / "a.xlsx", standard_scenario())
    csv = write_wechat_csv(tmp_path / "a.csv", standard_scenario())
    generic = write_generic_csv(
        tmp_path / "g.csv", [{"日期": "2026-10-01", "金额": "10.00"}], ["日期", "金额"],
    )
    assert detect_format(file_name=xlsx.name, mime="", head=xlsx.read_bytes()[:512]).format == "wechat_xlsx"
    match = detect_format(file_name=csv.name, mime="", head=b"", sample_text=csv.read_text("utf-8-sig"))
    assert match.format == "wechat_csv" and match.needs_mapping is False
    generic_match = detect_format(
        file_name=generic.name, mime="", head=b"", sample_text=generic.read_text("utf-8"),
    )
    assert generic_match.format == "generic_csv"
    assert generic_match.needs_mapping is True


def test_generic_csv_requires_mapping(tmp_path):
    path = write_generic_csv(
        tmp_path / "g.csv",
        [{"日期": "2026-10-01", "金额": "10.00", "备注": "早餐"}],
        ["日期", "金额", "备注"],
    )
    with pytest.raises(BillParseError):
        _parse(path)
    statement = _parse(
        path, mapping=ColumnMapping(occurred_at="日期", amount="金额", note="备注"),
    )
    assert len(statement.rows) == 1
    assert statement.rows[0].amount_minor == 1000
    assert statement.rows[0].note == "早餐"


def test_money_variants(tmp_path):
    rows = (
        BillRow(occurred="2026-10-02 12:00:00", amount="¥12.34",
                tx_id="MNY00000000000000000000000001"),
        BillRow(occurred="2026-10-03 12:00:00", amount="1,234.5",
                tx_id="MNY00000000000000000000000002"),
        BillRow(occurred="2026-10-04 12:00:00", amount="-5",
                tx_id="MNY00000000000000000000000003"),
    )
    path = write_wechat_xlsx(tmp_path / "money.xlsx", rows, control_totals={})
    statement = _parse(path)
    assert [row.amount_minor for row in statement.rows] == [1234, 123450, -500]


def test_empty_file_raises(tmp_path):
    path = tmp_path / "empty.xlsx"
    path.write_bytes(b"")
    with pytest.raises(BillParseError):
        _parse(path)


def test_unsupported_extension_raises(tmp_path):
    path = tmp_path / "bill.pdf"
    path.write_bytes(b"%PDF-1.4")
    with pytest.raises(BillParseError):
        _parse(path)


def test_declared_range_from_preamble(tmp_path):
    path = write_wechat_xlsx(tmp_path / "range.xlsx", standard_scenario(), header_row=7)
    statement = _parse(path)
    assert statement.declared_from and statement.declared_from.startswith("2026-10-01")
    assert statement.declared_to and statement.declared_to.startswith("2026-10-31")


def test_column_names_tolerate_fullwidth_and_amount_suffix(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    headers = list(WECHAT_COLUMNS)
    headers[headers.index("金额(元)")] = "金额（元）"
    ws.append(headers)
    ws.append(["2026-10-02 12:00:00", "商户消费", "示例便利店", "水", "支出", "9.90",
               "零钱", "支付成功", "FW00000000000000000000000001", "", ""])
    path = tmp_path / "fullwidth.xlsx"
    wb.save(path)
    statement = _parse(path)
    assert len(statement.rows) == 1
    assert statement.rows[0].amount_minor == 990


# ---- WP-A：用户同款"笔数+金额"摘要（此前把首数字当金额，精准产生错总额） ----

USER_SUMMARY = (
    "共4笔记录",
    "收入：1笔 10410.86元",
    "支出：1笔 23708.48元",
    "中性交易：2笔 9518.11元",
)


def _user_summary_rows():
    from tests.support.ledger_fixtures import BillRow

    return [
        BillRow(occurred="2026-10-01 09:00:00", type="商户消费", direction="支出",
                product="消费A", amount="23708.48", status="支付成功"),
        BillRow(occurred="2026-10-02 09:00:00", type="退款", direction="收入",
                product="退款B", amount="10410.86", status="已到账"),
        BillRow(occurred="2026-10-03 09:00:00", type="零钱充值", direction="中性",
                product="充值C", amount="4759.05", status="已到账"),
        BillRow(occurred="2026-10-04 09:00:00", type="零钱提现", direction="中性",
                product="提现D", amount="4759.06", status="已到账"),
    ]


def test_user_style_summary_csv_amounts_accurate(tmp_path):
    """WP-A 真实入口：'支出：385笔 23708.48元' 形态——金额必须是 2370848 分而非 38500。"""
    path = write_wechat_csv(tmp_path / "微信支付账单.csv", _user_summary_rows(),
                            summary_lines=USER_SUMMARY)
    statement = parse_wechat_csv(path, _options())
    totals = statement.control_totals
    assert totals.count == 4
    assert totals.expense_minor == 2370848, f"实际 {totals.expense_minor}（缺陷值 38500）"
    assert totals.income_minor == 1041086
    assert totals.neutral_minor == 951811
    assert statement.warnings == () or all("控制" not in w for w in statement.warnings)


def test_user_style_summary_xlsx_amounts_accurate(tmp_path):
    path = write_wechat_xlsx(tmp_path / "微信支付账单.xlsx", _user_summary_rows(),
                             summary_lines=USER_SUMMARY)
    statement = parse_wechat_xlsx(path, _options())
    totals = statement.control_totals
    assert totals.expense_minor == 2370848
    assert totals.income_minor == 1041086
    assert totals.neutral_minor == 951811
    assert totals.count == 4


def test_control_totals_text_variants():
    """文本变体矩阵：分类后可选笔数再金额/直接金额/千分位/零值/仅笔数。"""
    from backend.modules.ledger.normalization import parse_control_totals

    # 逗号连接变体：不得把金额 23708.48 当成总笔数
    t = parse_control_totals(["支出：385笔，共23708.48元"])
    assert t.expense_minor == 2370848
    assert t.count is None, "分类行的'385笔'不是总笔数"

    # 直接金额（旧格式）
    assert parse_control_totals(["支出合计：23708.48元"]).expense_minor == 2370848
    # 千分位
    assert parse_control_totals(["收入：33笔 1,041.08元"]).income_minor == 104108
    # 零值
    assert parse_control_totals(["支出：0笔 0.00元"]).expense_minor == 0
    # 只有笔数：金额保持 None（不得让首数字抢占）
    only_count = parse_control_totals(["支出：385笔"])
    assert only_count.expense_minor is None
    # 空摘要
    empty = parse_control_totals([])
    assert empty.expense_minor is None and empty.income_minor is None
    assert empty.count is None and empty.neutral_minor is None
