"""CSV 账单解析：编码/分隔符自适应，表头按内容识别，支持引号内换行。"""
from __future__ import annotations

import csv
import io
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
    mapping_indexes,
    match_header,
)

PARSER_NAME = "wechat_csv"
PARSER_VERSION = "1"
MAX_FILE_BYTES = 64 * 1024 * 1024
ENCODINGS = ("utf-8-sig", "gb18030", "utf-8")


def decode_text(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise BillParseError(f"CSV 文件超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 上限")
    data = path.read_bytes()
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise BillParseError("无法识别 CSV 编码（支持 UTF-8/GB18030）")


def detect_delimiter(sample: str) -> str:
    """按“出现该分隔符且列数>1 的行数”打分，避免被说明行带偏。"""
    lines = [line for line in sample.splitlines() if line.strip()]
    best = ","
    best_score = -1
    for candidate in (",", "\t", ";"):
        score = sum(
            line.count(candidate) for line in lines[:20] if line.count(candidate)
        )
        if score > best_score:
            best = candidate
            best_score = score
    return best


def iter_csv_rows(text: str, delimiter: str):
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    for row in reader:
        yield [cell for cell in row]


def parse_wechat_csv(path: Path, options: ParseOptions) -> ParsedStatement:
    text = decode_text(path)
    delimiter = detect_delimiter(text[:8192])
    return parse_csv_text(
        path, options, text=text, delimiter=delimiter, parser_name=PARSER_NAME,
    )


def parse_csv_text(
    path: Path, options: ParseOptions, *, text: str, delimiter: str, parser_name: str,
) -> ParsedStatement:
    rows: list[ParsedRow] = []
    control_lines: list[str] = []
    warnings: list[str] = []
    indexes: dict[str, int] | None = None
    truncated = False
    explicit_mapping = options.mapping

    for row_number, values in enumerate(iter_csv_rows(text, delimiter), start=1):
        if indexes is None:
            if explicit_mapping is not None:
                try:
                    candidate = mapping_indexes(explicit_mapping, values)
                except BillParseError:
                    candidate = None
                if candidate is not None:
                    indexes = candidate
                    continue
            else:
                _mapping, header_indexes = match_header(values)
                if header_indexes:
                    indexes = header_indexes
                    continue
            if row_number > MAX_HEADER_SCAN:
                raise BillParseError("未找到账单表头（前 40 行无时间/金额列）")
            text_line = control_line(values)
            if text_line:
                control_lines.append(text_line)
            continue
        if not any(str(v).strip() for v in values if v is not None):
            continue
        if is_control_line(values):
            text_line = control_line(values)
            if text_line:
                control_lines.append(text_line)
            continue
        if not looks_like_data(values, indexes):
            continue
        rows.append(
            build_row(
                values=values, indexes=indexes, sheet="csv", row_number=row_number,
                options=options,
            )
        )
        if len(rows) >= options.max_rows:
            truncated = True
            warnings.append(f"账单行数超过上限 {options.max_rows}，已截断")
            break

    if indexes is None:
        raise BillParseError("未找到账单表头（前 40 行无时间/金额列）")
    if not rows:
        raise BillParseError("账单没有可解析的交易行")
    totals = parse_control_totals(control_lines)
    declared_from, declared_to = declared_range(control_lines)
    data_from, data_to = data_range(rows)
    return ParsedStatement(
        format=parser_name,
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
