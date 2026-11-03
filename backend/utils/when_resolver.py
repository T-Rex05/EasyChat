"""
自然语言时间解析 — 借鉴 Eyes when_resolver 的纯规则引擎（零 LLM 成本、可单测）

支持短语：今天/昨天/前天、本周/上周/本月/上月/本季度/上季度/今年/去年、
最近N天/最近N周/最近N月/最近N小时/最近N分钟（N 支持阿拉伯数字与中文数字一到十）、
近N天/过去N天/未来N天（未来→end 为 now）。
返回 (start, end) naive datetime；无法解析的非空短语抛 ValueError（诚实态）。

用法：
    from backend.utils.when_resolver import resolve_when
    start, end = resolve_when("最近7天")
"""
import calendar
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_COUNT = r"(\d+|[一两二三四五六七八九十])"

# (匹配顺序即优先级)
_PATTERNS = [
    ("最近N分钟", re.compile(r"^(?:最近|近|过去|未来)\s*" + _COUNT + r"\s*(?:分钟|min)s?$")),
    ("最近N小时", re.compile(r"^(?:最近|近|过去|未来)\s*" + _COUNT + r"\s*(?:小时|个?钟头|h)s?$")),
    ("最近N天", re.compile(r"^(?:最近|近|过去|未来)\s*" + _COUNT + r"\s*(?:天|日)s?$")),
    ("最近N周", re.compile(r"^(?:最近|近|过去|未来)\s*" + _COUNT + r"\s*(?:周|个?星期)s?$")),
    ("最近N月", re.compile(r"^(?:最近|近|过去|未来)\s*" + _COUNT + r"\s*(?:个?月)s?$")),
    ("今天", re.compile(r"^(?:今天|今日|当天)$")),
    ("昨天", re.compile(r"^(?:昨天|昨日)$")),
    ("前天", re.compile(r"^(?:前天|前日)$")),
    ("本周", re.compile(r"^(?:本周|这周|本星期)$")),
    ("上周", re.compile(r"^(?:上周|上个?星期)$")),
    ("本月", re.compile(r"^(?:本月|这个月)$")),
    ("上月", re.compile(r"^(?:上月|上个月)$")),
    ("本季度", re.compile(r"^(?:本季度|本季|这个季度)$")),
    ("上季度", re.compile(r"^(?:上季度|上季|上个季度)$")),
    ("今年", re.compile(r"^(?:今年|本年度?)$")),
    ("去年", re.compile(r"^(?:去年|上年度?)$")),
]


def _parse_count(token: str) -> int:
    token = (token or "").strip()
    if token.isdigit():
        return int(token)
    if token in _CN_NUM:
        return _CN_NUM[token]
    raise ValueError(f"无法解析数量: {token!r}")


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week(dt: datetime) -> datetime:
    return _start_of_day(dt) - timedelta(days=dt.weekday())


def _start_of_month(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _start_of_quarter(dt: datetime) -> datetime:
    first_month = ((dt.month - 1) // 3) * 3 + 1
    return dt.replace(month=first_month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    base = dt.month - 1 + months
    year = dt.year + base // 12
    month = base % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def resolve_when(phrase: Optional[str], now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """解析时间短语，返回 (start, end)。None/空串 → 默认「今天」。"""
    if now is None:
        now = datetime.now()
    phrase = (phrase or "").strip()
    if not phrase:
        return _start_of_day(now), now

    for label, pattern in _PATTERNS:
        m = pattern.match(phrase)
        if not m:
            continue
        # 相对区间：未来 → end=now，start=now-N；过去 → end=now，start=now-N
        if label.startswith("最近"):
            n = _parse_count(m.group(1))
            unit = label.replace("最近N", "")
            if unit == "分钟":
                delta = timedelta(minutes=n)
            elif unit == "小时":
                delta = timedelta(hours=n)
            elif unit == "天":
                delta = timedelta(days=n)
            elif unit == "周":
                delta = timedelta(weeks=n)
            elif unit == "月":
                delta = timedelta(days=n * 30)
            else:
                raise ValueError(f"未支持的单位: {unit}")
            if phrase.startswith("未来"):
                return now, now + delta
            return now - delta, now
        if label == "今天":
            return _start_of_day(now), now
        if label == "昨天":
            return _start_of_day(now - timedelta(days=1)), _start_of_day(now)
        if label == "前天":
            return _start_of_day(now - timedelta(days=2)), _start_of_day(now - timedelta(days=1))
        if label == "本周":
            return _start_of_week(now), now
        if label == "上周":
            return _start_of_week(now) - timedelta(days=7), _start_of_week(now)
        if label == "本月":
            return _start_of_month(now), now
        if label == "上月":
            return _start_of_month(_add_months(now, -1)), _start_of_month(now)
        if label == "本季度":
            return _start_of_quarter(now), now
        if label == "上季度":
            return _start_of_quarter(_add_months(now, -3)), _start_of_quarter(now)
        if label == "今年":
            return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), now
        if label == "去年":
            _y0 = now.replace(year=now.year - 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            _y1 = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            return _y0, _y1
    raise ValueError(f"无法识别的时间短语: {phrase!r}")