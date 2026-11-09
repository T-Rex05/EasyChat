"""解析器公共构件：表头识别、单行标准化、控制总额与声明区间提取。

设计约束（F4）：
- 表头位置不固定（微信导出说明行数量可变），按内容识别而不是固定行号；
- 单行字段错误只记录在 `ParsedRow.errors`，绝不丢弃该行；
- 交易单号按字符串处理，浮点精度丢失一律标记为不可靠；
- 解析是纯本地确定性逻辑，无网络/无 LLM/无全局状态。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from backend.modules.ledger.contracts import (
    WECHAT_COLUMN_ALIASES,
    ColumnMapping,
    ParsedRow,
)
from backend.modules.ledger.normalization import (
    classify_event_role,
    clean_text,
    normalize_direction,
    normalize_external_id,
    parse_money,
    parse_occurred_at,
    status_key,
)

MAX_HEADER_SCAN = 40
MAX_CELL_TEXT = 200

_RANGE_PATTERNS = (
    re.compile(r"(?:起始时间|开始时间|账单开始)[:：]?\s*[\[【]?\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)"),
    re.compile(r"(?:结束时间|终止时间|截止时间|账单结束)[:：]?\s*[\[【]?\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)"),
)
_CONTROL_HINTS = ("笔", "收入", "支出", "中性", "合计", "总额")


class BillParseError(Exception):
    """结构性解析错误（文件不可读/找不到表头/缺必需列/需要列映射）。"""


@dataclass(frozen=True, slots=True)
class ParseOptions:
    timezone: str = "Asia/Shanghai"
    default_currency: str = "CNY"
    max_rows: int = 100_000
    # 审计 #8：控制行与数据行共用有界预算——无上限保留会让 50MB 输入
    # 在内存里放大 ~15-20 倍并阻塞共享事件循环。
    max_control_lines: int = 5_000
    sheet_names: tuple[str, ...] = ()
    mapping: ColumnMapping | None = None


def normalize_header(text: object) -> str:
    raw = str(text or "").strip().lower()
    raw = raw.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s\u3000]+", "", raw)


def match_header(cells: Sequence[object]) -> tuple[ColumnMapping | None, dict[str, int]]:
    """在候选行中识别微信账单表头；返回 (映射, canonical→列号)。"""
    normalized = [normalize_header(cell) for cell in cells]
    if not normalized:
        return None, {}
    indexes: dict[str, int] = {}
    headers: dict[str, str] = {}
    for canonical, aliases in WECHAT_COLUMN_ALIASES.items():
        for alias in aliases:
            target = normalize_header(alias)
            for index, value in enumerate(normalized):
                if value and (value == target or target in value):
                    indexes[canonical] = index
                    headers[canonical] = str(cells[index]).strip()
                    break
            if canonical in indexes:
                break
    if "occurred_at" not in indexes or "amount" not in indexes:
        return None, {}
    return (
        ColumnMapping(
            occurred_at=headers["occurred_at"],
            amount=headers["amount"],
            direction=headers.get("direction", ""),
            tx_type=headers.get("tx_type", ""),
            counterparty=headers.get("counterparty", ""),
            product=headers.get("product", ""),
            status=headers.get("status", ""),
            external_id=headers.get("external_id", ""),
            merchant_id=headers.get("merchant_id", ""),
            note=headers.get("note", ""),
            pay_method=headers.get("pay_method", ""),
            currency=headers.get("currency", ""),
        ),
        indexes,
    )


def mapping_indexes(mapping: ColumnMapping, header_cells: Sequence[object]) -> dict[str, int]:
    """按用户显式映射在表头中定位列号（列名精确/包含匹配）。"""
    normalized = [normalize_header(cell) for cell in header_cells]
    indexes: dict[str, int] = {}
    for canonical, header in mapping.as_dict().items():
        if not header:
            continue
        target = normalize_header(header)
        for index, value in enumerate(normalized):
            if value and (value == target or target == value or target in value):
                indexes[canonical] = index
                break
        else:
            if canonical in ("occurred_at", "amount"):
                raise BillParseError(f"缺少必需列: {header}")
    if "occurred_at" not in indexes or "amount" not in indexes:
        raise BillParseError("列映射至少需要时间列与金额列")
    return indexes


def build_row(
    *, values: Sequence[object], indexes: Mapping[str, int], sheet: str,
    row_number: int, options: ParseOptions,
) -> ParsedRow:
    def cell(canonical: str) -> object:
        index = indexes.get(canonical)
        if index is None or index >= len(values):
            return None
        return values[index]

    raw: dict[str, str] = {}
    for canonical, index in indexes.items():
        if index < len(values):
            text = clean_text(values[index], limit=MAX_CELL_TEXT)
            if text:
                raw[canonical] = text

    errors: list[str] = []
    amount, currency, amount_error = parse_money(
        cell("amount"), default_currency=options.default_currency,
    )
    if amount_error:
        errors.append(amount_error)
    occurred, time_error = parse_occurred_at(cell("occurred_at"), timezone=options.timezone)
    if time_error:
        errors.append(time_error)
    direction = normalize_direction(cell("direction"))
    external_id, reliable = normalize_external_id(cell("external_id"))
    merchant_id, _merchant_reliable = normalize_external_id(cell("merchant_id"))
    status_raw = clean_text(cell("status"), limit=60)
    tx_type = clean_text(cell("tx_type"), limit=60)
    product = clean_text(cell("product"), limit=MAX_CELL_TEXT)
    return ParsedRow(
        sheet=sheet,
        row_number=row_number,
        locator=f"{sheet}:{row_number}",
        raw=raw,
        occurred_at=occurred,
        amount_minor=amount,
        direction=direction,
        currency=currency,
        tx_type=tx_type,
        counterparty=clean_text(cell("counterparty"), limit=120),
        product=product,
        status=status_raw,
        external_id=external_id,
        merchant_id=merchant_id,
        note=clean_text(cell("note"), limit=MAX_CELL_TEXT),
        pay_method=clean_text(cell("pay_method"), limit=60),
        event_role=classify_event_role(tx_type, direction, status_raw, product),
        id_reliable=reliable,
        errors=tuple(errors),
    )


def looks_like_data(values: Sequence[object], indexes: Mapping[str, int]) -> bool:
    """有金额/单号/对方/类型任一非空即视为数据行（避免把空行计成差错）。"""
    for canonical in ("amount", "external_id", "counterparty", "tx_type", "occurred_at"):
        index = indexes.get(canonical)
        if index is not None and index < len(values) and clean_text(values[index]):
            return True
    return False


def is_control_line(values: Sequence[object]) -> bool:
    filled = [clean_text(v) for v in values if clean_text(v)]
    if len(filled) != 1:
        return False
    text = filled[0]
    return any(hint in text for hint in _CONTROL_HINTS) or "共" in text


def control_line(values: Sequence[object]) -> str:
    filled = [clean_text(v, limit=MAX_CELL_TEXT) for v in values if clean_text(v)]
    return filled[0] if len(filled) == 1 else ""


def declared_range(lines: Iterable[str]) -> tuple[str | None, str | None]:
    start = end = None
    for line in lines:
        for index, pattern in enumerate(_RANGE_PATTERNS):
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(1).replace("/", "-").replace(".", "-").replace("T", " ")
            if index == 0 and start is None:
                start = value
            elif index == 1 and end is None:
                end = value
    return start, end


def data_range(rows: Sequence[ParsedRow]) -> tuple[str | None, str | None]:
    moments = sorted(row.occurred_at for row in rows if row.occurred_at)
    if not moments:
        return None, None
    return moments[0], moments[-1]


def row_values(row: Iterable[Any]) -> list[object]:
    return list(row)


__all__ = [
    "BillParseError",
    "MAX_HEADER_SCAN",
    "ParseOptions",
    "build_row",
    "control_line",
    "data_range",
    "declared_range",
    "is_control_line",
    "looks_like_data",
    "mapping_indexes",
    "match_header",
    "normalize_header",
    "status_key",
]
