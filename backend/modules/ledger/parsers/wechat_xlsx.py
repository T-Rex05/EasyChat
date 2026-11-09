"""微信支付 XLSX 账单解析：表头按内容识别，说明/汇总行不计入数据。"""
from __future__ import annotations

from pathlib import Path

from backend.modules.ledger.contracts import ControlTotals, ParsedRow, ParsedStatement
from backend.modules.ledger.normalization import parse_control_totals
from backend.modules.ledger.parsers.base import (
    MAX_HEADER_SCAN,
    BillParseError,
    ParseOptions,
    build_row,
    control_line,
    data_range,
    declared_range,
    is_control_line,
    looks_like_data,
    match_header,
)

PARSER_NAME = "wechat_xlsx"
PARSER_VERSION = "1"


def parse_wechat_xlsx(path: Path, options: ParseOptions) -> ParsedStatement:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - 依赖固定在 requirements
        raise BillParseError("缺少 openpyxl，无法解析 XLSX") from exc
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001  损坏/加密/非 XLSX
        raise BillParseError(f"无法打开 XLSX 文件: {exc}") from exc

    rows: list[ParsedRow] = []
    control_lines: list[str] = []
    warnings: list[str] = []
    truncated = False
    found_sheet = False
    try:
        for sheet in workbook.worksheets:
            if options.sheet_names and sheet.title not in options.sheet_names:
                continue
            found, cut = _parse_sheet(sheet, options, rows, control_lines, warnings)
            found_sheet = found_sheet or found
            truncated = truncated or cut
            if len(rows) >= options.max_rows:
                truncated = True
                break
    finally:
        workbook.close()

    if not found_sheet:
        raise BillParseError("未找到微信账单表头（可按通用 CSV 指定列映射导入）")
    if not rows:
        raise BillParseError("账单没有可解析的交易行")
    if len(rows) > options.max_rows:
        rows = rows[: options.max_rows]
        truncated = True
        warnings.append(f"账单行数超过上限 {options.max_rows}，已截断")
    totals = parse_control_totals(control_lines)
    declared_from, declared_to = declared_range(control_lines)
    data_from, data_to = data_range(rows)
    return ParsedStatement(
        format=PARSER_NAME,
        version=PARSER_VERSION,
        rows=tuple(rows),
        declared_from=declared_from or data_from,
        declared_to=declared_to or data_to,
        currency=options.default_currency,
        control_totals=totals if _has_totals(totals) else ControlTotals(),
        warnings=tuple(warnings),
        truncated=truncated,
    )


def _has_totals(totals: ControlTotals) -> bool:
    return any(
        value is not None
        for value in (totals.count, totals.income_minor, totals.expense_minor, totals.neutral_minor)
    )


def _parse_sheet(sheet, options, rows, control_lines, warnings) -> tuple[bool, bool]:
    """解析单个工作表；返回 (是否识别到表头, 是否因上限截断)。"""
    header_indexes: dict[str, int] | None = None
    preamble: list[list[object]] = []
    truncated = False
    row_number = 0

    def _consume_remainder(remainder, header_row: int) -> None:
        nonlocal truncated
        for offset, pending in enumerate(remainder, start=1):
            truncated = truncated or _consume(
                pending, header_indexes, sheet.title, header_row + offset, options,
                rows, control_lines, warnings,
            )

    for row_number, values in enumerate(sheet.iter_rows(values_only=True), start=1):
        values = list(values)
        if header_indexes is None:
            preamble.append(values)
            if len(preamble) < MAX_HEADER_SCAN:
                continue
            header_indexes, header_row, remainder = _adopt_header(preamble, control_lines)
            preamble = []
            if header_indexes is None:
                return False, truncated
            _consume_remainder(remainder, header_row)
            continue
        truncated = truncated or _consume(
            values, header_indexes, sheet.title, row_number, options,
            rows, control_lines, warnings,
        )
        if len(rows) >= options.max_rows:
            return True, True
    if header_indexes is None:
        header_indexes, header_row, remainder = _adopt_header(preamble, control_lines)
        if header_indexes is None:
            return False, truncated
        _consume_remainder(remainder, header_row)
    return True, truncated


def _adopt_header(
    buffer: list[list[object]], control_lines: list[str],
) -> tuple[dict[str, int] | None, int, list[list[object]]]:
    """在缓冲区里找表头；返回 (列号, 表头绝对行号, 表头之后的缓冲行)。"""
    for offset, values in enumerate(buffer):
        _mapping, indexes = match_header(values)
        if indexes:
            for preamble_row in buffer[:offset]:
                text = control_line(preamble_row)
                if text:
                    control_lines.append(text)
            return indexes, offset + 1, buffer[offset + 1:]
    return None, 0, []


def _consume(
    values: list[object], indexes: dict[str, int], sheet: str, row_number: int,
    options: ParseOptions, rows: list[ParsedRow], control_lines: list[str],
    warnings: list[str],
) -> bool:
    if not any(str(v).strip() for v in values if v is not None):
        return False
    if is_control_line(values):
        text = control_line(values)
        if text and len(control_lines) < options.max_control_lines:
            control_lines.append(text)
        return False
    if not looks_like_data(values, indexes):
        return False
    rows.append(
        build_row(
            values=values, indexes=indexes, sheet=sheet, row_number=row_number,
            options=options,
        )
    )
    return False
