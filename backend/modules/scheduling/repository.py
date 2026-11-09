"""scheduling 数据访问：计划、实例与下次执行时间。"""
from __future__ import annotations

from typing import Any

from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.scheduling.contracts import (
    CONTENT_BRIEFING,
    CONTENT_TEXT,
    SCHEDULE_DAILY,
    SCHEDULE_INTERVAL,
    SCHEDULE_ONCE,
    SCHEDULE_WEEKLY,
    OccurrenceView,
    ScheduleSpec,
    ScheduleView,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import NotFoundError
from backend.shared.identifiers import new_occurrence_id, new_schedule_id


def _schedule(row: Any) -> ScheduleView:
    d = dict(row)
    return ScheduleView(
        schedule_id=str(d["id"]),
        owner_id=int(d["owner_id"]),
        title=str(d["title"] or ""),
        text=str(d["text"] or ""),
        target=DeliveryTarget(
            kind=str(d["target_kind"]),
            ref=str(d["target_ref"]),
            channel_account_id=str(d.get("channel_account_id") or ""),
        ),
        kind=str(d["schedule_kind"]),
        interval_seconds=int(d["interval_seconds"] or 0),
        at_time=str(d["at_time"] or ""),
        timezone=str(d["timezone"] or "Asia/Shanghai"),
        next_run_at=float(d["next_run_at"]),
        enabled=bool(d["enabled"]),
        last_run_at=d.get("last_run_at"),
        created_at=str(d["created_at"]),
        weekday=int(d.get("weekday") or 0),
        content_kind=str(d.get("content_kind") or CONTENT_TEXT),
        briefing_kind=str(d.get("briefing_kind") or ""),
    )


def _occurrence(row: Any) -> OccurrenceView:
    d = dict(row)
    return OccurrenceView(
        occurrence_id=str(d["id"]),
        schedule_id=str(d["schedule_id"]),
        scheduled_at=str(d["scheduled_at"]),
        state=str(d["state"]),
        delivery_id=str(d["delivery_id"] or ""),
        job_id=str(d.get("job_id") or ""),
        missed=int(d["missed"] or 0),
        created_at=str(d["created_at"]),
        processed_at=d.get("processed_at"),
    )


class SchedulingRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, spec: ScheduleSpec) -> ScheduleView:
        if spec.kind not in (SCHEDULE_ONCE, SCHEDULE_INTERVAL, SCHEDULE_DAILY, SCHEDULE_WEEKLY):
            raise ValueError(f"未知计划类型: {spec.kind}")
        if spec.content_kind not in (CONTENT_TEXT, CONTENT_BRIEFING):
            raise ValueError(f"未知内容类型: {spec.content_kind}")
        schedule_id = new_schedule_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO scheduled_jobs(id, owner_id, title, text, target_kind, target_ref, "
                "channel_account_id, schedule_kind, interval_seconds, at_time, timezone, next_run_at, "
                "weekday, content_kind, briefing_kind, enabled, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (
                    schedule_id, spec.owner_id, spec.title, spec.text,
                    spec.target.kind, spec.target.ref,
                    spec.target.channel_account_id, spec.kind,
                    int(spec.interval_seconds), spec.at_time, spec.timezone,
                    float(spec.next_run_at), int(spec.weekday),
                    spec.content_kind, spec.briefing_kind, now, now,
                ),
            )
        return self.get(schedule_id)

    def find_recent_duplicate(self, spec: ScheduleSpec) -> ScheduleView | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE owner_id=? AND text=? AND schedule_kind=? "
                "AND content_kind=? AND briefing_kind=? AND weekday=? AND enabled=1 "
                "AND target_kind=? AND target_ref=? AND channel_account_id=? "
                "AND interval_seconds=? "
                "AND abs(next_run_at-?)<1.0 AND (at_time=? OR at_time='') "
                "ORDER BY created_at DESC LIMIT 1",
                (
                    spec.owner_id, spec.text, spec.kind, spec.content_kind,
                    spec.briefing_kind, int(spec.weekday), spec.target.kind,
                    spec.target.ref, spec.target.channel_account_id,
                    int(spec.interval_seconds), float(spec.next_run_at), spec.at_time,
                ),
            ).fetchone()
            return _schedule(row) if row else None
        finally:
            conn.close()

    def get(self, schedule_id: str) -> ScheduleView:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM scheduled_jobs WHERE id=?", (schedule_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"提醒计划不存在: {schedule_id}")
            return _schedule(row)
        finally:
            conn.close()

    def list_for_owner(self, owner_id: int, limit: int = 50) -> list[ScheduleView]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
            return [_schedule(r) for r in rows]
        finally:
            conn.close()

    def delete(self, schedule_id: str) -> None:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM scheduled_jobs WHERE id=?", (schedule_id,))
            if cur.rowcount != 1:
                raise NotFoundError(f"提醒计划不存在: {schedule_id}")

    def set_enabled(self, schedule_id: str, enabled: bool) -> None:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE scheduled_jobs SET enabled=?, updated_at=? WHERE id=?",
                (1 if enabled else 0, utc_now_iso(), schedule_id),
            )
            if cur.rowcount != 1:
                raise NotFoundError(f"提醒计划不存在: {schedule_id}")

    def due(self, now: float, limit: int = 20) -> list[ScheduleView]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE enabled=1 AND next_run_at<=? "
                "ORDER BY next_run_at LIMIT ?",
                (now, limit),
            ).fetchall()
            return [_schedule(r) for r in rows]
        finally:
            conn.close()

    def insert_occurrence_tx(
        self, conn: Any, schedule_id: str, scheduled_at: str, *, missed: int = 0
    ) -> tuple[str, bool]:
        occurrence_id = new_occurrence_id()
        cur = conn.execute(
            "INSERT INTO scheduled_occurrences(id, schedule_id, scheduled_at, state, missed, created_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(schedule_id, scheduled_at) DO NOTHING",
            (occurrence_id, schedule_id, scheduled_at, "pending", int(missed), utc_now_iso()),
        )
        if cur.rowcount == 1:
            return occurrence_id, True
        row = conn.execute(
            "SELECT id FROM scheduled_occurrences WHERE schedule_id=? AND scheduled_at=?",
            (schedule_id, scheduled_at),
        ).fetchone()
        return (str(row["id"]) if row else occurrence_id), False

    def mark_occurrence_queued_tx(
        self, conn: Any, occurrence_id: str, delivery_id: str = "", *, job_id: str = ""
    ) -> None:
        conn.execute(
            "UPDATE scheduled_occurrences SET state='queued', delivery_id=?, job_id=?, "
            "processed_at=? WHERE id=?",
            (delivery_id, job_id, utc_now_iso(), occurrence_id),
        )

    def advance_tx(
        self,
        conn: Any,
        schedule_id: str,
        *,
        next_run_at: float,
        enabled: bool,
        last_run_at: str | None = None,
    ) -> None:
        conn.execute(
            "UPDATE scheduled_jobs SET next_run_at=?, enabled=?, last_run_at=?, updated_at=? WHERE id=?",
            (float(next_run_at), 1 if enabled else 0, last_run_at, utc_now_iso(), schedule_id),
        )

    def upcoming_for_owner(
        self,
        owner_id: int,
        until: float,
        limit: int | None = None,
        *,
        content_kind: str = "",
    ) -> list[ScheduleView]:
        """返回 next_run_at<=until 的计划；不先 SQL LIMIT，供上层展开 occurrence。"""
        sql = (
            "SELECT * FROM scheduled_jobs WHERE owner_id=? AND enabled=1 "
            "AND next_run_at<=?"
        )
        params: list[Any] = [owner_id, float(until)]
        if content_kind:
            sql += " AND content_kind=?"
            params.append(content_kind)
        sql += " ORDER BY next_run_at"
        conn = self.db.connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            schedules = [_schedule(r) for r in rows]
            return schedules if limit is None else schedules[:limit]
        finally:
            conn.close()

    def occurrences(self, schedule_id: str, limit: int = 20) -> list[OccurrenceView]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM scheduled_occurrences WHERE schedule_id=? "
                "ORDER BY scheduled_at DESC LIMIT ?",
                (schedule_id, limit),
            ).fetchall()
            return [_occurrence(r) for r in rows]
        finally:
            conn.close()
