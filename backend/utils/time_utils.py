from datetime import datetime, timedelta


def now_local_naive() -> datetime:
    """Return current server-local wall-clock time without tzinfo for legacy JSON/UI fields."""
    return datetime.now().replace(tzinfo=None)


def now_local_iso(timespec: str = "seconds") -> str:
    return now_local_naive().isoformat(timespec=timespec)


def days_start(days: int):
    """时间筛选起点（自然日语义，数据库无关）。

    - days=1  → 今天 0 点
    - days=N  → N 个自然日前的 0 点（含今天，即「最近 N 天」）
    - days<=0 → None（不限时间）

    用于 trace 筛选等场景，替代 MySQL 专有的 DATE_SUB(NOW(), INTERVAL n DAY)。
    """
    if not days or days <= 0:
        return None
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=days - 1)
