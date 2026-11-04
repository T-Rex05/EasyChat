"""通用 CSV 解析：必须由用户显式提供列映射（模型不得猜列）。

仅在用户确认映射后使用；映射里的列名在表头中定位不到时抛 BillParseError。
"""
from __future__ import annotations

from pathlib import Path

from backend.modules.ledger.contracts import ParsedStatement
from backend.modules.ledger.parsers.base import BillParseError, ParseOptions
from backend.modules.ledger.parsers.wechat_csv import (
    PARSER_VERSION,
    decode_text,
    detect_delimiter,
    parse_csv_text,
)

PARSER_NAME = "generic_csv"


def parse_generic_csv(path: Path, options: ParseOptions) -> ParsedStatement:
    if options.mapping is None:
        raise BillParseError("该文件需要指定列映射（至少包含时间与金额列）")
    text = decode_text(path)
    delimiter = detect_delimiter(text[:8192])
    return parse_csv_text(
        path, options, text=text, delimiter=delimiter, parser_name=PARSER_NAME,
    )


__all__ = ["PARSER_NAME", "PARSER_VERSION", "parse_generic_csv"]
