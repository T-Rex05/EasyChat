"""账单解析入口：格式探测 + 按文件类型分发。

对上层（LedgerService）只暴露 `detect_format` 与 `parse_saved_file`；
识别失败必须抛 `BillParseError`，不能用“猜列”掩盖。
"""
from __future__ import annotations

from pathlib import Path

from backend.modules.ledger.contracts import WECHAT_COLUMN_ALIASES, FormatMatch
from backend.modules.ledger.parsers.base import (
    BillParseError,
    ParseOptions,
    match_header,
    normalize_header,
)
from backend.modules.ledger.parsers.generic_csv import PARSER_NAME as GENERIC_CSV
from backend.modules.ledger.parsers.generic_csv import parse_generic_csv
from backend.modules.ledger.parsers.wechat_csv import (
    PARSER_NAME as WECHAT_CSV,
)
from backend.modules.ledger.parsers.wechat_csv import (
    PARSER_VERSION,
    decode_text,
    detect_delimiter,
    parse_csv_text,
)
from backend.modules.ledger.parsers.wechat_xlsx import PARSER_NAME as WECHAT_XLSX
from backend.modules.ledger.parsers.wechat_xlsx import parse_wechat_xlsx

XLSX_SUFFIXES = (".xlsx", ".xlsm")
CSV_SUFFIXES = (".csv", ".tsv", ".txt")

__all__ = [
    "BillParseError",
    "ParseOptions",
    "detect_format",
    "parse_saved_file",
]


def detect_format(
    *, file_name: str, mime: str, head: bytes, sample_text: str = ""
) -> FormatMatch:
    suffix = Path(file_name or "").suffix.lower()
    lowered_mime = (mime or "").lower()
    text = sample_text or _decode_head(head)
    if suffix in XLSX_SUFFIXES or "spreadsheetml" in lowered_mime:
        return FormatMatch(
            format=WECHAT_XLSX, version=PARSER_VERSION, confidence=0.7,
            notes=("XLSX 表头将在解析时按内容确认",),
        )
    if suffix in CSV_SUFFIXES or "csv" in lowered_mime or "tab-separated" in lowered_mime:
        if _has_wechat_header(text):
            return FormatMatch(
                format=WECHAT_CSV, version=PARSER_VERSION, confidence=0.9,
            )
        return FormatMatch(
            format=GENERIC_CSV, version=PARSER_VERSION, confidence=0.4,
            needs_mapping=True,
            notes=("未识别出微信账单表头，需要用户指定时间/金额列",),
        )
    if _has_wechat_header(text):
        return FormatMatch(
            format=WECHAT_CSV, version=PARSER_VERSION, confidence=0.6,
            notes=("按文本内容识别为微信 CSV，但扩展名未知",),
        )
    return FormatMatch(
        format=GENERIC_CSV, version=PARSER_VERSION, confidence=0.2,
        needs_mapping=True, notes=("未知格式，需要用户指定列映射",),
    )


def parse_saved_file(
    path: Path, *, file_name: str, mime: str, options: ParseOptions | None = None,
) -> "object":
    options = options or ParseOptions()
    suffix = Path(file_name or path.name).suffix.lower()
    if suffix in (".xls",):
        raise BillParseError("暂不支持旧版 .xls，请在微信中导出为 xlsx 或 csv")
    if suffix in XLSX_SUFFIXES or "spreadsheetml" in (mime or "").lower():
        return parse_wechat_xlsx(path, options)
    if suffix in CSV_SUFFIXES or "csv" in (mime or "").lower():
        text = decode_text(path)
        delimiter = detect_delimiter(text[:8192])
        first_lines = text.splitlines()[:40]
        for line in first_lines:
            if options.mapping is not None:
                break
            candidate = [cell.strip() for cell in line.split(delimiter)]
            _mapping, indexes = match_header(candidate)
            if indexes:
                return parse_csv_text(
                    path, options, text=text, delimiter=delimiter,
                    parser_name=WECHAT_CSV,
                )
        if options.mapping is not None:
            return parse_generic_csv(path, options)
        raise BillParseError(
            "未识别出微信账单表头；若是其它平台账单，请先指定时间与金额列映射"
        )
    raise BillParseError(f"不支持的文件类型: {suffix or mime or '未知'}")


def _decode_head(head: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return head.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def _has_wechat_header(text: str) -> bool:
    required = ("occurred_at", "amount")
    found: set[str] = set()
    for line in (text or "").splitlines()[:40]:
        cells = [normalize_header(cell) for cell in _split_any(line)]
        for canonical in required:
            if canonical in found:
                continue
            for alias in WECHAT_COLUMN_ALIASES[canonical]:
                target = normalize_header(alias)
                if any(cell and (cell == target or target in cell) for cell in cells):
                    found.add(canonical)
                    break
    if found == set(required):
        return True
    return False


def _split_any(line: str) -> list[str]:
    for delimiter in ("\t", ",", ";"):
        if delimiter in line:
            return [cell.strip().strip('"') for cell in line.split(delimiter)]
    return [line.strip()]
