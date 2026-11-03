"""进化预算：按用户每日/单次上限预留与核销，跨重启持久化。

发送 LLM 前预留最坏输出预算；未知 usage 保留未结算预留（不立即返还全部），
避免预算被反复透支。日期按项目时区切分。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.platform.sqlite import Database, utc_now_iso

DEFAULT_DAILY_TOKENS = 20_000
DEFAULT_TASK_TOKENS = 5_000


@dataclass
class Reservation:
    user_id: int
    stat_date: str
    tokens: int
    task_id: str
    settled: bool = False
    released: bool = False


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    stat_date: str
    reserved: int
    used: int
    daily_limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.reserved - self.used)


class BudgetManager:
    def __init__(
        self,
        db: Database,
        *,
        clock=time.time,
        timezone_name: str = "Asia/Shanghai",
        daily_limit: int = DEFAULT_DAILY_TOKENS,
        task_limit: int = DEFAULT_TASK_TOKENS,
    ) -> None:
        self.db = db
        self.clock = clock
        self.timezone_name = timezone_name
        self.daily_limit = int(daily_limit)
        self.task_limit = int(task_limit)

    def _date(self, now: float | None = None) -> str:
        moment = datetime.fromtimestamp(self.clock() if now is None else now, ZoneInfo(self.timezone_name))
        return moment.strftime("%Y-%m-%d")

    def status(self, user_id: int, *, now: float | None = None) -> BudgetStatus:
        stat_date = self._date(now)
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT reserved, used FROM evolution_budgets WHERE stat_date=? AND user_id=?",
                (stat_date, user_id),
            ).fetchone()
            reserved = int(row["reserved"]) if row else 0
            used = int(row["used"]) if row else 0
        finally:
            conn.close()
        return BudgetStatus(
            stat_date=stat_date, reserved=reserved, used=used, daily_limit=self.daily_limit,
        )

    def reserve(
        self, user_id: int, *, task_id: str, worst_tokens: int, now: float | None = None
    ) -> Reservation | None:
        worst = max(0, int(worst_tokens))
        if worst <= 0 or worst > self.task_limit:
            return None
        stat_date = self._date(now)
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT reserved, used FROM evolution_budgets WHERE stat_date=? AND user_id=?",
                (stat_date, user_id),
            ).fetchone()
            reserved = int(row["reserved"]) if row else 0
            used = int(row["used"]) if row else 0
            if reserved + used + worst > self.daily_limit:
                return None
            conn.execute(
                "INSERT INTO evolution_budgets(stat_date, user_id, reserved, used, updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(stat_date, user_id) DO UPDATE SET "
                "reserved=excluded.reserved, used=excluded.used, updated_at=excluded.updated_at",
                (stat_date, user_id, reserved + worst, used, utc_now_iso()),
            )
        return Reservation(user_id=user_id, stat_date=stat_date, tokens=worst, task_id=task_id)

    def settle(
        self, reservation: Reservation, actual_tokens: int, *, usage_known: bool = True
    ) -> None:
        """核销：已知 usage 释放预留并计入 used；未知 usage 保留预留（防无限透支）。"""
        if reservation.settled or reservation.released:
            raise ValueError("预算预留已结算")
        actual = max(0, int(actual_tokens)) if usage_known else 0
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT reserved, used FROM evolution_budgets WHERE stat_date=? AND user_id=?",
                (reservation.stat_date, reservation.user_id),
            ).fetchone()
            reserved = int(row["reserved"]) if row else 0
            used = int(row["used"]) if row else 0
            if usage_known:
                reserved = max(0, reserved - reservation.tokens)
                used += actual
            # 未知 usage：把预留留在账上，待后续对账；不假装预算已返还
            conn.execute(
                "INSERT INTO evolution_budgets(stat_date, user_id, reserved, used, updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(stat_date, user_id) DO UPDATE SET "
                "reserved=excluded.reserved, used=excluded.used, updated_at=excluded.updated_at",
                (reservation.stat_date, reservation.user_id, reserved, used, utc_now_iso()),
            )
        reservation.settled = True

    def release(self, reservation: Reservation) -> None:
        """确定未发起 LLM 调用时释放预留。"""
        if reservation.settled or reservation.released:
            return
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT reserved, used FROM evolution_budgets WHERE stat_date=? AND user_id=?",
                (reservation.stat_date, reservation.user_id),
            ).fetchone()
            reserved = int(row["reserved"]) if row else 0
            used = int(row["used"]) if row else 0
            conn.execute(
                "INSERT INTO evolution_budgets(stat_date, user_id, reserved, used, updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(stat_date, user_id) DO UPDATE SET "
                "reserved=excluded.reserved, used=excluded.used, updated_at=excluded.updated_at",
                (reservation.stat_date, reservation.user_id,
                 max(0, reserved - reservation.tokens), used, utc_now_iso()),
            )
        reservation.released = True
