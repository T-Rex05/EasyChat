"""账本语义标准化：金额、时间、方向、状态、事件角色、稳定指纹。

纯函数、无 IO，可独立单测。所有金额进入系统前必须转成整数最小单位（分），
避免浮点误差与“0.1+0.2”式对账失败。
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from backend.modules.ledger.contracts import (
    DIRECTION_EXPENSE,
    DIRECTION_INCOME,
    DIRECTION_NEUTRAL,
    DIRECTION_UNKNOWN,
    DIRECTIONS,
    EVENT_ROLE_NEUTRAL,
    EVENT_ROLE_PAYMENT,
    EVENT_ROLE_REFUND,
    STATUS_CLOSED,
    STATUS_FAILED,
    STATUS_PAID,
    STATUS_PENDING,
    STATUS_RECEIVED,
    STATUS_REFUNDED_FULL,
    STATUS_REFUNDED_PARTIAL,
    STATUS_UNKNOWN,
    ControlTotals,
)

DEFAULT_TIMEZONE = "Asia/Shanghai"

_CURRENCY_SYMBOLS = {
    "¥": "CNY", "￥": "CNY", "元": "CNY", "人民币": "CNY", "RMB": "CNY", "CNY": "CNY",
    "$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR", "HK$": "HKD", "HKD": "HKD",
}
_MONEY_NOISE = re.compile(r"[\s,，\u00a0]")
_MONEY_RE = re.compile(r"^([+-]?)(\d{1,15})(?:\.(\d{1,2}))?$")

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
)

_STATUS_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("已全额退款", "全额退款", "已退款", "退款成功"), STATUS_REFUNDED_FULL),
    (("已部分退款", "部分退款"), STATUS_REFUNDED_PARTIAL),
    (("已关闭", "交易关闭", "已取消", "已撤销"), STATUS_CLOSED),
    (("支付失败", "交易失败", "已失败", "失败"), STATUS_FAILED),
    (("已收钱", "已存入零钱", "已到账", "收款成功", "已转账", "对方已收钱"), STATUS_RECEIVED),
    (("处理中", "支付中", "待支付", "等待付款"), STATUS_PENDING),
    (("支付成功", "已支付", "交易成功", "充值成功", "已成功"), STATUS_PAID),
)

_REFUND_WORDS = ("退款", "退货退款", "退回", "已退款")
_NEUTRAL_TYPE_WORDS = (
    "零钱充值", "充值", "零钱提现", "提现", "转入零钱", "转出零钱", "微信红包-退还",
)


def detect_currency(text: str, *, default: str = "CNY") -> str:
    """从金额/币种文本识别币种；无法识别返回 default。"""
    raw = (text or "").strip()
    if not raw:
        return default
    for symbol in ("HK$", "USD", "CNY", "EUR", "HKD", "RMB", "€", "$", "¥", "￥", "元", "人民币"):
        if symbol in raw:
            mapped = _CURRENCY_SYMBOLS.get(symbol)
            if mapped:
                return mapped
    return default


def parse_money(
    text: object, *, default_currency: str = "CNY"
) -> tuple[int | None, str, str | None]:
    """返回 (最小单位金额, 币种, 错误)。错误非空时金额为 None，绝不静默当 0。

    规则：去掉货币符号/千分位/空白；允许前导 +/-（+ 视为正数）；
    最多 2 位小数；超过 2 位视为精度错误（不做四舍五入，避免账目对不上）。
    """
    if text is None:
        return None, default_currency, "金额为空"
    if isinstance(text, bool):
        return None, default_currency, "金额类型非法"
    if isinstance(text, int):
        return text * 100, default_currency, None
    if isinstance(text, float):
        # 浮点金额只能作为兜底；用 Decimal 走字符串，避免二进制误差
        text = repr(text)
    raw = str(text).strip()
    if not raw:
        return None, default_currency, "金额为空"
    currency = detect_currency(raw, default=default_currency)
    cleaned = raw
    for symbol in sorted(_CURRENCY_SYMBOLS, key=len, reverse=True):
        cleaned = cleaned.replace(symbol, "")
    cleaned = _MONEY_NOISE.sub("", cleaned)
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    match = _MONEY_RE.match(cleaned)
    if not match:
        return None, currency, f"无法解析金额: {raw[:40]}"
    sign, whole, fraction = match.groups()
    fraction = (fraction or "").ljust(2, "0")
    try:
        minor = int(whole) * 100 + int(fraction)
    except ValueError:  # pragma: no cover - 正则已保证
        return None, currency, f"无法解析金额: {raw[:40]}"
    if sign == "-":
        minor = -minor
    return minor, currency, None


def format_money(minor: int | None, currency: str = "CNY") -> str:
    """整数分 → 人类可读金额（仅用于展示/报告）。"""
    if minor is None:
        return "—"
    sign = "-" if minor < 0 else ""
    value = abs(int(minor))
    return f"{sign}{value // 100}.{value % 100:02d} {currency}".strip()


def _localize(moment: datetime, tz: ZoneInfo) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    else:
        moment = moment.astimezone(tz)
    return moment.isoformat(timespec="seconds")


def parse_occurred_at(
    text: object, *, timezone: str = DEFAULT_TIMEZONE, excel_epoch: str = "1900"
) -> tuple[str | None, str | None]:
    """返回 (ISO 时间, 错误)。支持微信常见文本日期与 Excel 序列号。"""
    tz = ZoneInfo(timezone)
    if text is None:
        return None, "交易时间为空"
    if isinstance(text, datetime):
        return _localize(text, tz), None
    if isinstance(text, date):
        return _localize(datetime(text.year, text.month, text.day), tz), None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return _from_excel_serial(float(text), tz, excel_epoch)
    raw = str(text).strip()
    if not raw:
        return None, "交易时间为空"
    raw = raw.replace("上午", "AM").replace("下午", "PM")
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None and ("%z" not in fmt and "Z" not in fmt):
            return _localize(parsed, tz), None
        return _localize(parsed, tz), None
    # 纯数字字符串按 Excel 序列号兜底（部分导出为文本数字）
    if re.fullmatch(r"\d{5}(?:\.\d+)?", raw):
        return _from_excel_serial(float(raw), tz, excel_epoch)
    return None, f"无法解析交易时间: {raw[:40]}"


def _from_excel_serial(
    value: float, tz: ZoneInfo, epoch: str = "1900"
) -> tuple[str | None, str | None]:
    if value <= 0 or value > 2958465:  # 9999-12-31
        return None, "交易时间序列号越界"
    base = datetime(1899, 12, 30) if epoch == "1900" else datetime(1904, 1, 1)
    try:
        moment = base + timedelta(days=value)
    except (OverflowError, ValueError):  # pragma: no cover
        return None, "交易时间序列号越界"
    # 序列号精度约 1 秒，四舍五入到秒（避免 23:59:59.999 → 次日误差）
    moment = moment.replace(microsecond=0) + timedelta(
        seconds=1 if moment.microsecond >= 500_000 else 0
    )
    return _localize(moment, tz), None


def normalize_direction(raw: object) -> str:
    """收/支文本 → expense/income/neutral/unknown。"""
    text = str(raw or "").strip()
    if not text:
        return DIRECTION_UNKNOWN
    lowered = text.lower()
    if lowered in DIRECTIONS:
        return lowered
    if text in ("支出", "支", "付款", "消费", "-"):
        return DIRECTION_EXPENSE
    if text in ("收入", "收", "收款", "+"):
        return DIRECTION_INCOME
    if text in ("中性", "不计收支", "/", "其他"):
        return DIRECTION_NEUTRAL
    return DIRECTION_UNKNOWN


def status_key(raw: object) -> str:
    """把状态原文映射成稳定 key；未知原文返回 unknown 但保留原文。"""
    text = str(raw or "").strip()
    if not text:
        return STATUS_UNKNOWN
    for words, key in _STATUS_RULES:
        if any(word in text for word in words):
            return key
    return STATUS_UNKNOWN


def classify_event_role(
    tx_type: str, direction: str, status: str = "", product: str = ""
) -> str:
    """区分原支付 / 退款 / 中性事件（充值提现等不参与消费统计）。

    只看交易类型/商品/方向，**不看状态文本**：微信账单里“已全额退款”的原支付
    仍是原支付行，退款是独立一行；若按状态判角色，同一订单的角色会随状态翻转，
    导致去重身份漂移、退款匹配找不到原支付。
    """
    text = f"{tx_type or ''}{product or ''}"
    if any(word in text for word in _REFUND_WORDS):
        return EVENT_ROLE_REFUND
    if direction in (DIRECTION_EXPENSE, DIRECTION_INCOME):
        return EVENT_ROLE_PAYMENT
    if any(word in text for word in _NEUTRAL_TYPE_WORDS) or direction == DIRECTION_NEUTRAL:
        return EVENT_ROLE_NEUTRAL
    return EVENT_ROLE_NEUTRAL


def normalize_external_id(value: object) -> tuple[str, bool]:
    """返回 (规范化 ID, 是否可靠)。

    不可靠（Excel 浮点精度丢失、纯 0、含空格/科学计数法）的 ID 不得用于身份去重。
    """
    if value is None:
        return "", False
    if isinstance(value, bool):
        return "", False
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if not value.is_integer() or abs(value) > 2**53:
            return "", False
        text = str(int(value))
    else:
        text = str(value).strip()
    if not text:
        return "", False
    if not re.fullmatch(r"[0-9A-Za-z_-]{6,64}", text):
        return "", False
    if set(text) <= {"0"}:
        return "", False
    if not any(ch.isdigit() for ch in text):
        return "", False
    return text, True


def clean_text(value: object, *, limit: int = 200) -> str:
    """去掉控制字符/NUL 与首尾空白，限制长度（原文另存 raw_fields）。"""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 0x20)
    text = text.replace("\x00", "")
    return text.strip()[:limit]


def fingerprint(*parts: object, length: int = 32) -> str:
    """稳定指纹（sha256 前 N 位）；None 与空串统一成 ""，避免环境差异。"""
    joined = "\u241f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


def amount_to_minor(text: object, *, default_currency: str = "CNY") -> int | None:
    minor, _currency, _error = parse_money(text, default_currency=default_currency)
    return minor


# ---- 控制总额 -------------------------------------------------------------------

_CONTROL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("count", re.compile(r"(?:笔数|交易笔数|总笔数|共)[^\d]{0,6}(\d{1,7})\s*笔?")),
    ("expense", re.compile(r"(?:支出|总支出|支出合计)[^\d]{0,8}([-\d.,]+)")),
    ("income", re.compile(r"(?:收入|总收入|收入合计)[^\d]{0,8}([-\d.,]+)")),
    ("neutral", re.compile(r"(?:中性|不计收支|其他)[^\d]{0,8}([-\d.,]+)")),
)


def parse_control_totals(lines: object) -> ControlTotals:
    """从账单头部/尾部说明行提取控制总额；缺失字段保持 None。"""
    if isinstance(lines, str):
        candidates = [lines]
    else:
        candidates = [str(line) for line in (lines or []) if str(line).strip()]
    found: dict[str, int | None] = {"count": None, "expense": None, "income": None,
                                    "neutral": None}
    raw_lines: list[str] = []
    for line in candidates:
        hit = False
        for name, pattern in _CONTROL_PATTERNS:
            if found[name] is not None:
                continue
            match = pattern.search(line)
            if not match:
                continue
            if name == "count":
                found[name] = int(match.group(1))
            else:
                minor, _currency, error = parse_money(match.group(1))
                if error is None and minor is not None:
                    found[name] = abs(minor)
            hit = True
        if hit:
            raw_lines.append(line.strip())
    return ControlTotals(
        count=found["count"],
        income_minor=found["income"],
        expense_minor=found["expense"],
        neutral_minor=found["neutral"],
        raw_lines=tuple(raw_lines),
    )


def money_decimal(minor: int) -> Decimal:
    """整数分 → Decimal（仅用于导出/展示计算，不参与数据库求和）。"""
    return (Decimal(int(minor)) / Decimal(100)).quantize(Decimal("0.01"))


__all__ = [
    "DEFAULT_TIMEZONE",
    "amount_to_minor",
    "classify_event_role",
    "clean_text",
    "detect_currency",
    "fingerprint",
    "format_money",
    "money_decimal",
    "normalize_direction",
    "normalize_external_id",
    "parse_control_totals",
    "parse_money",
    "parse_occurred_at",
    "status_key",
]

_ = InvalidOperation  # 保留导入给后续扩展的 Decimal 错误处理
