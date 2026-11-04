"""人工合成账单/截图夹具生成器（F0）。

只用虚构商户与订单号；不读取桌面真实账单，不访问网络。
生成的文件写在测试的 tmp_path 下，不进入仓库。

设计要点：
- 微信 XLSX 允许说明行在前、表头位置可移动（不能固定第18行）；
- 订单号一律用字符串写入，超长ID用于验证“不能经 float/科学计数法截断”；
- CSV 覆盖 BOM/GB18030、逗号/制表符、引号内换行；
- 截图用标准库 zlib 生成合法 PNG（不依赖 Pillow）。
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

WECHAT_COLUMNS: tuple[str, ...] = (
    "交易时间",
    "交易类型",
    "交易对方",
    "商品",
    "收/支",
    "金额(元)",
    "支付方式",
    "当前状态",
    "交易单号",
    "商户单号",
    "备注",
)

# 虚构交易单号：刻意超长（28位），模拟真实微信支付单号长度
LONG_TX_ID = "4200001234202610021234567890"
LONG_MERCHANT_ID = "19000001092026100212345678"


@dataclass(frozen=True, slots=True)
class BillRow:
    occurred: str
    type: str = "商户消费"
    counterparty: str = "示例便利店"
    product: str = "矿泉水"
    direction: str = "支出"
    amount: str = "100.00"
    pay_method: str = "零钱"
    status: str = "支付成功"
    tx_id: str = LONG_TX_ID
    merchant_id: str = LONG_MERCHANT_ID
    note: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "交易时间": self.occurred,
            "交易类型": self.type,
            "交易对方": self.counterparty,
            "商品": self.product,
            "收/支": self.direction,
            "金额(元)": self.amount,
            "支付方式": self.pay_method,
            "当前状态": self.status,
            "交易单号": self.tx_id,
            "商户单号": self.merchant_id,
            "备注": self.note,
        }


@dataclass(frozen=True, slots=True)
class SyntheticBill:
    path: Path
    rows: tuple[BillRow, ...]
    control_totals: Mapping[str, Any] = field(default_factory=dict)

    @property
    def expense_minor(self) -> int:
        return sum(_to_minor(r.amount) for r in self.rows if r.direction == "支出")

    @property
    def income_minor(self) -> int:
        return sum(_to_minor(r.amount) for r in self.rows if r.direction == "收入")


def _to_minor(text: str) -> int:
    whole, _, frac = str(text).partition(".")
    frac = (frac + "00")[:2]
    return int(whole.replace(",", "")) * 100 + int(frac)


# ---- 场景 -------------------------------------------------------------------


def standard_scenario() -> tuple[BillRow, ...]:
    """原消费100、部分退款30、转账50、充值200（设计 §9 的对账用例）。"""
    return (
        BillRow(occurred="2026-10-02 12:00:00", amount="100.00", tx_id=LONG_TX_ID,
                merchant_id=LONG_MERCHANT_ID, note="午餐"),
        BillRow(occurred="2026-10-05 09:30:00", type="退款", counterparty="示例便利店",
                product="退款", direction="收入", amount="30.00", status="已全额退款",
                tx_id="RFD00000000000000000000000001", merchant_id=LONG_MERCHANT_ID,
                note=f"原交易单号 {LONG_TX_ID}"),
        BillRow(occurred="2026-10-08 18:20:00", type="转账", counterparty="示例好友",
                product="转账", amount="50.00", status="对方已收钱",
                tx_id="TRF00000000000000000000000001", merchant_id="",
                note=""),
        BillRow(occurred="2026-10-10 08:00:00", type="零钱充值", counterparty="零钱充值",
                product="零钱充值", direction="", amount="200.00", status="充值成功",
                tx_id="TOP00000000000000000000000001", merchant_id="", note=""),
    )


def full_refund_scenario() -> tuple[BillRow, ...]:
    """消费100全额退款100：消费净额必须是0，不能是-100。"""
    return (
        BillRow(occurred="2026-10-02 12:00:00", amount="100.00", status="已全额退款",
                tx_id="ORD00000000000000000000000001"),
        BillRow(occurred="2026-10-03 12:00:00", type="退款", direction="收入",
                product="退款", amount="100.00", status="已退款",
                tx_id="RFD00000000000000000000000002",
                note="原交易单号 ORD00000000000000000000000001"),
    )


def same_id_refund_scenario() -> tuple[BillRow, ...]:
    """原单与退款共用同一交易单号：身份必须按 event_role 区分。"""
    same = "SHR00000000000000000000000001"
    return (
        BillRow(occurred="2026-10-02 12:00:00", amount="100.00", status="已全额退款", tx_id=same),
        BillRow(occurred="2026-10-03 12:00:00", type="退款", direction="收入", product="退款",
                amount="100.00", status="已退款", tx_id=same),
    )


def overlap_export_scenario() -> tuple[BillRow, ...]:
    """重叠区间导出：同一交易在两个文件里都出现（含一次状态更新）。"""
    return (
        BillRow(occurred="2026-09-28 10:00:00", amount="88.00", status="支付成功",
                tx_id="OVL00000000000000000000000001"),
        BillRow(occurred="2026-10-02 12:00:00", amount="100.00", status="支付成功",
                tx_id=LONG_TX_ID),
    )


def status_update_scenario() -> tuple[BillRow, ...]:
    """同一订单号，后一次导出状态变为已全额退款。"""
    return (
        BillRow(occurred="2026-10-02 12:00:00", amount="100.00", status="已全额退款",
                tx_id=LONG_TX_ID, note="导出2"),
    )


def mismatched_control_totals() -> dict[str, Any]:
    """控制总额与明细不一致（测试必须能发现而不是默默接受）。"""
    return {"count": 99, "income_minor": 123456, "expense_minor": 999999}


# ---- XLSX -------------------------------------------------------------------


def _preamble_lines(start: str = "2026-10-01 00:00:00", end: str = "2026-10-31 23:59:59") -> list[str]:
    return [
        "微信支付账单明细",
        "微信昵称：[示例用户]",
        "起始时间：[%s] 终止时间：[%s]" % (start, end),
        "导出类型：[全部]",
        "导出时间：[2026-11-01 09:00:00]",
    ]


def write_wechat_xlsx(
    path: Path,
    rows: Sequence[BillRow],
    *,
    header_row: int = 7,
    sheet_name: str = "Sheet1",
    extra_sheets: Mapping[str, Sequence[BillRow]] | None = None,
    control_totals: Mapping[str, Any] | None = None,
    preamble: bool = True,
) -> Path:
    """写一个合成微信 XLSX；header_row 从 1 开始，说明行数量可变。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    write_row = 1
    if preamble:
        lines = _preamble_lines()
        for line in lines[: max(0, header_row - 1)]:
            ws.cell(row=write_row, column=1, value=line)
            write_row += 1
    # 补齐到表头位置
    while write_row < header_row:
        write_row += 1
    for col, name in enumerate(WECHAT_COLUMNS, start=1):
        ws.cell(row=header_row, column=col, value=name)

    current = header_row + 1
    for row in rows:
        for col, name in enumerate(WECHAT_COLUMNS, start=1):
            ws.cell(row=current, column=col, value=row.as_dict()[name])
        current += 1

    current += 1
    totals = dict(control_totals) if control_totals is not None else {
        "count": len(rows),
        "income_minor": sum(_to_minor(r.amount) for r in rows if r.direction == "收入"),
        "expense_minor": sum(_to_minor(r.amount) for r in rows if r.direction == "支出"),
        "neutral_minor": sum(_to_minor(r.amount) for r in rows if r.direction not in ("收入", "支出")),
    }
    if totals:
        ws.cell(row=current, column=1, value=f"共{totals.get('count', 0)}笔记录")
        ws.cell(row=current + 1, column=1,
                value=f"收入：{_minor_text(totals.get('income_minor', 0))}元")
        ws.cell(row=current + 2, column=1,
                value=f"支出：{_minor_text(totals.get('expense_minor', 0))}元")
        ws.cell(row=current + 3, column=1,
                value=f"中性交易：{_minor_text(totals.get('neutral_minor', 0))}元")

    for name, sheet_rows in (extra_sheets or {}).items():
        extra = wb.create_sheet(title=name)
        for col, header in enumerate(WECHAT_COLUMNS, start=1):
            extra.cell(row=1, column=col, value=header)
        for index, row in enumerate(sheet_rows, start=2):
            for col, header in enumerate(WECHAT_COLUMNS, start=1):
                extra.cell(row=index, column=col, value=row.as_dict()[header])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _minor_text(minor: Any) -> str:
    value = int(minor or 0)
    return f"{value // 100}.{value % 100:02d}"


# ---- CSV --------------------------------------------------------------------


def write_wechat_csv(
    path: Path,
    rows: Sequence[BillRow],
    *,
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
    preamble: bool = True,
) -> Path:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        if preamble:
            for line in _preamble_lines():
                writer.writerow([line])
            writer.writerow([])
        writer.writerow(WECHAT_COLUMNS)
        for row in rows:
            writer.writerow([row.as_dict()[name] for name in WECHAT_COLUMNS])
        writer.writerow([f"共{len(rows)}笔记录"])
        writer.writerow([f"收入：{_minor_text(sum(_to_minor(r.amount) for r in rows if r.direction == '收入'))}元"])
        writer.writerow([f"支出：{_minor_text(sum(_to_minor(r.amount) for r in rows if r.direction == '支出'))}元"])
    return path


def write_generic_csv(
    path: Path,
    rows: Iterable[Mapping[str, str]],
    columns: Sequence[str],
    *,
    encoding: str = "utf-8",
    delimiter: str = ",",
) -> Path:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow(list(columns))
        for row in rows:
            writer.writerow([str(row.get(c, "")) for c in columns])
    return path


def write_quoted_multiline_csv(path: Path) -> Path:
    """带引号字段内换行 + 转义引号 + 人民币符号的合成 CSV。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注\n"
        '2026-10-02 12:00:00,商户消费,示例便利店,"第一行\n第二行 ""引号"" 内容",支出,¥12.34,零钱,支付成功,'
        'ML00000000000000000000000001,MM00000000000000000000000001,"多行备注"\n'
    )
    path.write_text(content, encoding="utf-8")
    return path


# ---- PNG（标准库实现，不依赖 Pillow） -----------------------------------------


def write_png(path: Path, *, width: int = 320, height: int = 480, gray: int = 240) -> Path:
    """生成纯色 PNG；只用于“原件保存/像素限制”测试，不代表真实截图内容。"""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + bytes([gray]) * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path


# ---- 假视觉结果 ---------------------------------------------------------------


def fake_vision_payload(
    *,
    amount: str | None = "23.50",
    direction: str | None = "expense",
    occurred: str | None = "2026-10-02 12:00:00",
    merchant: str = "示例便利店",
    currency: str | None = "CNY",
    confidence: float = 0.93,
    text: str = "支付成功 ¥23.50 示例便利店",
) -> dict[str, Any]:
    """假视觉 Adapter 的输出：字段 + 置信度 + 原文 + 原图定位。"""
    fields: dict[str, Any] = {"merchant": merchant}
    if amount is not None:
        fields["amount"] = amount
    if direction is not None:
        fields["direction"] = direction
    if occurred is not None:
        fields["occurred_at"] = occurred
    if currency is not None:
        fields["currency"] = currency
    return {
        "fields": fields,
        "confidence": {name: confidence for name in fields},
        "text": text,
        "regions": [{"field": "amount", "box": [10, 20, 120, 44]}],
    }
