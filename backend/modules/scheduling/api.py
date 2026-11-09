"""scheduling 模块公开接口：建立提醒、恢复到期实例、生成投递请求。

到期只生成“最新未完成实例”，错过多次时记录 missed 计数，不补发无限历史；
实例与投递请求在同一 SQLite 事务提交。调度器只有一个生命周期入口。
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.scheduling.contracts import (
    BRIEFING_KINDS,
    CONTENT_BRIEFING,
    CONTENT_KINDS,
    SCHEDULE_DAILY,
    SCHEDULE_INTERVAL,
    SCHEDULE_ONCE,
    SCHEDULE_WEEKLY,
    OccurrenceView,
    ScheduleSpec,
    ScheduleView,
)
from backend.modules.scheduling.repository import SchedulingRepository
from backend.platform.sqlite import Database
from backend.shared.errors import InvalidInputError

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Asia/Shanghai"
MIN_INTERVAL_SECONDS = 60
MAX_FUTURE_SECONDS = 2 * 366 * 24 * 3600


class SchedulingService:
    def __init__(
        self,
        db: Database,
        *,
        delivery: DeliveryService,
        access: Any,
        clock=time.time,
        timezone_name: str = DEFAULT_TIMEZONE,
        queue: Any = None,
        briefing_enabled: bool = True,
    ) -> None:
        self.db = db
        self.repo = SchedulingRepository(db)
        self.delivery = delivery
        self.access = access
        self.clock = clock
        self.timezone_name = timezone_name
        self.queue = queue
        self.briefing_enabled = briefing_enabled

    # ---- 管理 ------------------------------------------------------------------

    def create(
        self,
        actor,
        *,
        title: str,
        text: str,
        target: DeliveryTarget,
        at: str = "",
        every_seconds: int = 0,
        daily_at: str = "",
        weekly_at: str = "",
        weekday: int | None = None,
        timezone: str = "",
        content_kind: str = "text",
        briefing_kind: str = "",
    ) -> ScheduleView:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "cron.create")
        if content_kind not in CONTENT_KINDS:
            raise InvalidInputError("content_kind 只能是 text/briefing")
        if content_kind == CONTENT_BRIEFING:
            if not self.briefing_enabled:
                raise InvalidInputError("简报功能未启用（缺少调度队列或用户配置）")
            if briefing_kind not in BRIEFING_KINDS:
                raise InvalidInputError(
                    "briefing_kind 只能是 morning/evening/weekly/mood_weekly/ai_news"
                )
            if self.queue is None:
                raise InvalidInputError("简报调度未装配 JobQueue")
        elif not text.strip():
            raise InvalidInputError("提醒内容不能为空")
        if not target.ref:
            raise InvalidInputError("提醒目标不能为空")
        tz_name = _validate_timezone(timezone or self.timezone_name)
        now = self.clock()
        chosen = sum(
            1 for value in (at, every_seconds, daily_at, weekly_at) if value
        )
        if chosen != 1:
            raise InvalidInputError(
                "必须且只能指定 at / every_seconds / daily_at / weekly_at 之一"
            )

        weekday_value = 0
        if at:
            next_run_at = _parse_at(at, tz_name)
            kind = SCHEDULE_ONCE
            interval = 0
            at_time = ""
        elif every_seconds:
            interval = int(every_seconds)
            if interval < MIN_INTERVAL_SECONDS:
                raise InvalidInputError(f"重复间隔不能小于 {MIN_INTERVAL_SECONDS} 秒")
            kind = SCHEDULE_INTERVAL
            next_run_at = now + interval
            at_time = ""
        elif daily_at:
            at_time = _validate_daily(daily_at)
            kind = SCHEDULE_DAILY
            interval = 0
            next_run_at = _next_daily(now, at_time, tz_name)
        else:
            if weekday is None:
                raise InvalidInputError("weekly_at 必须同时给 weekday（0=周一…6=周日）")
            if not isinstance(weekday, int) or not 0 <= weekday <= 6:
                raise InvalidInputError("weekday 必须是 0..6（0=周一）")
            weekday_value = weekday
            at_time = _validate_daily(weekly_at)
            kind = SCHEDULE_WEEKLY
            interval = 0
            next_run_at = _next_weekly(now, at_time, weekday_value, tz_name)

        if next_run_at <= now:
            raise InvalidInputError("提醒时间必须在未来")
        if next_run_at > now + MAX_FUTURE_SECONDS:
            raise InvalidInputError("提醒时间不能超过 2 年")

        spec = ScheduleSpec(
            owner_id=principal.user_id,
            title=title.strip()[:120],
            text=text,
            target=target,
            kind=kind,
            next_run_at=next_run_at,
            interval_seconds=interval,
            at_time=at_time,
            timezone=tz_name,
            weekday=weekday_value,
            content_kind=content_kind,
            briefing_kind=(
                briefing_kind if content_kind == CONTENT_BRIEFING else ""
            ),
        )
        duplicate = self.repo.find_recent_duplicate(spec)
        if duplicate is not None:
            return duplicate
        return self.repo.create(spec)

    def get(self, actor, schedule_id: str) -> ScheduleView:
        principal = self.access.validate_principal(actor)
        schedule = self.repo.get(schedule_id)
        if schedule.owner_id != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        return schedule

    def list(self, actor, limit: int = 50) -> list[ScheduleView]:
        principal = self.access.validate_principal(actor)
        return self.repo.list_for_owner(principal.user_id, limit=limit)

    def set_enabled(self, actor, schedule_id: str, enabled: bool) -> ScheduleView:
        principal = self.access.validate_principal(actor)
        schedule = self.repo.get(schedule_id)
        if schedule.owner_id != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        self.repo.set_enabled(schedule_id, enabled)
        return self.repo.get(schedule_id)

    def cancel(self, actor, schedule_id: str) -> ScheduleView:
        return self.set_enabled(actor, schedule_id, False)

    def remove(self, actor, schedule_id: str) -> None:
        principal = self.access.validate_principal(actor)
        schedule = self.repo.get(schedule_id)
        if schedule.owner_id != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        self.repo.delete(schedule_id)

    def occurrences(self, actor, schedule_id: str, limit: int = 20) -> list[OccurrenceView]:
        principal = self.access.validate_principal(actor)
        schedule = self.repo.get(schedule_id)
        if schedule.owner_id != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        return self.repo.occurrences(schedule_id, limit=limit)

    def upcoming(
        self,
        actor,
        until: float | str,
        limit: int = 50,
        *,
        content_kind: str = "",
        start: float | str | None = None,
    ) -> list[ScheduleView]:
        """列出未来计划；start 给出时把重复计划推进到 start 后的下一次 occurrence。

        返回的 ScheduleView.next_run_at 是“投影时间”，不修改数据库里的
        scheduled_jobs.next_run_at。先展开、排序，再按 limit 截断，避免 SQL
        LIMIT 在展开前漏掉更早的 occurrence。
        """
        principal = self.access.validate_principal(actor)
        end = _parse_until(until)
        begin = _parse_until(start) if start is not None else None
        if content_kind and content_kind not in CONTENT_KINDS:
            raise InvalidInputError("content_kind 只能是 text/briefing")
        schedules = self.repo.upcoming_for_owner(
            principal.user_id, end, content_kind=content_kind
        )
        if begin is None:
            return schedules[:limit]
        projected: list[ScheduleView] = []
        for schedule in schedules:
            occurrence = _next_occurrence_after(schedule, begin)
            if occurrence is None or occurrence < begin or occurrence > end:
                continue
            projected.append(replace(schedule, next_run_at=occurrence))
        projected.sort(key=lambda item: (item.next_run_at, item.schedule_id))
        return projected[:limit]

    def delivered_between(self, actor, start: str, end: str) -> int:
        principal = self.access.validate_principal(actor)
        start_iso = _iso_range_bound(start)
        end_iso = _iso_range_bound(end)
        if start_iso >= end_iso:
            raise InvalidInputError("start 必须早于 end")
        return self.delivery.count_sent_reminders(
            principal.user_id, start_iso, end_iso
        )

    # ---- 到期处理 ----------------------------------------------------------------

    def tick(self, now: float | None = None) -> list[str]:
        """处理到期计划；返回新建的 delivery id 或 briefing job id 列表。"""
        current = self.clock() if now is None else float(now)
        created: list[str] = []
        for schedule in self.repo.due(current):
            slot, missed, next_run_at, enabled = _next_slot(schedule, current)
            scheduled_at = _iso_from_epoch(slot)
            with self.db.transaction() as conn:
                occurrence_id, inserted = self.repo.insert_occurrence_tx(
                    conn, schedule.schedule_id, scheduled_at, missed=missed,
                )
                if inserted:
                    if schedule.content_kind == CONTENT_BRIEFING:
                        job_id = self._enqueue_briefing_tx(conn, schedule, slot)
                        self.repo.mark_occurrence_queued_tx(
                            conn, occurrence_id, job_id=job_id
                        )
                        created.append(job_id)
                    else:
                        delivery_id = self.delivery.enqueue_in_transaction(
                            conn,
                            owner_id=schedule.owner_id,
                            target=schedule.target,
                            text=schedule.text,
                            dedup_key=f"schedule:{schedule.schedule_id}:{scheduled_at}",
                            source="schedule",
                        )
                        self.repo.mark_occurrence_queued_tx(
                            conn, occurrence_id, delivery_id
                        )
                        created.append(delivery_id)
                self.repo.advance_tx(
                    conn, schedule.schedule_id,
                    next_run_at=next_run_at, enabled=enabled,
                    last_run_at=scheduled_at,
                )
        return created

    def _enqueue_briefing_tx(self, conn: Any, schedule: ScheduleView, slot: float) -> str:
        if self.queue is None:
            raise RuntimeError("简报调度未装配 JobQueue")
        local_date = datetime.fromtimestamp(
            slot, ZoneInfo(schedule.timezone or self.timezone_name)
        ).date().isoformat()
        return self.queue.enqueue_tx(
            conn,
            kind="briefing.build",
            dedup_key=(
                f"briefing:{schedule.owner_id}:{schedule.briefing_kind}:"
                f"{local_date}:{schedule.schedule_id}"
            ),
            payload={
                "owner_id": schedule.owner_id,
                "kind": schedule.briefing_kind,
                "schedule_id": schedule.schedule_id,
                "date": local_date,
                # 简报也必须尊重计划里显式选择的邮箱/微信目标；否则用户在
                # UI 选“邮箱”后 worker 仍只会去找已绑定的微信。
                "target_kind": schedule.target.kind,
                "target_ref": schedule.target.ref,
                "channel_account_id": schedule.target.channel_account_id,
            },
            owner_id=schedule.owner_id,
        )


# ---- 时间计算（纯函数，便于测试） ------------------------------------------------


def _validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001  ZoneInfoNotFoundError/ValueError
        raise InvalidInputError(f"无效时区: {name}") from exc
    return name


def _parse_iso_datetime(
    value: float | str, *, field: str, timezone_name: str = DEFAULT_TIMEZONE
) -> datetime:
    """解析带/不带时区的 ISO；统一按用户时区补齐 naive 时间。"""
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise InvalidInputError(f"{field} 不是合法 ISO 时间: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed


def _parse_until(value: float | str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return _parse_iso_datetime(value, field="until").timestamp()


def _iso_range_bound(value: str) -> str:
    parsed = _parse_iso_datetime(value, field="范围时间")
    return parsed.astimezone(dt_timezone.utc).isoformat(timespec="milliseconds")


def _parse_at(value: str, timezone_name: str) -> float:
    return _parse_iso_datetime(
        value, field="at", timezone_name=timezone_name
    ).timestamp()


def _validate_daily(value: str) -> str:
    try:
        hour, minute = value.strip().split(":")
        hour_i, minute_i = int(hour), int(minute)
    except (ValueError, AttributeError) as exc:
        raise InvalidInputError(f"daily_at 必须是 HH:MM，收到: {value}") from exc
    if not (0 <= hour_i < 24 and 0 <= minute_i < 60):
        raise InvalidInputError(f"daily_at 越界: {value}")
    return f"{hour_i:02d}:{minute_i:02d}"


def _next_daily(epoch: float, at_time: str, timezone_name: str) -> float:
    hour, minute = (int(part) for part in at_time.split(":"))
    tz = ZoneInfo(timezone_name)
    current = datetime.fromtimestamp(epoch, tz)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def _next_weekly(epoch: float, at_time: str, weekday: int, timezone_name: str) -> float:
    """按本地日历找下一个指定星期几，不使用 +7*86400 硬算。"""
    hour, minute = (int(part) for part in at_time.split(":"))
    tz = ZoneInfo(timezone_name)
    current = datetime.fromtimestamp(epoch, tz)
    days_ahead = (int(weekday) - current.weekday()) % 7
    candidate = (current + timedelta(days=days_ahead)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if candidate <= current:
        candidate = (candidate + timedelta(days=7)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
    return candidate.timestamp()


def _next_recurring(schedule: ScheduleView, after: float) -> float | None:
    """按本地日历推进 daily/weekly；其他类型由调用方处理。"""
    tz_name = schedule.timezone or DEFAULT_TIMEZONE
    if schedule.kind == SCHEDULE_DAILY:
        return _next_daily(after, schedule.at_time, tz_name)
    if schedule.kind == SCHEDULE_WEEKLY:
        return _next_weekly(
            after, schedule.at_time, schedule.weekday, tz_name
        )
    return None


def _next_occurrence_after(schedule: ScheduleView, start: float) -> float | None:
    """返回从 start（含）起该计划的下一次 occurrence；只读，不改 next_run_at。"""
    if schedule.kind == SCHEDULE_ONCE:
        return schedule.next_run_at if schedule.next_run_at >= start else None

    # 数据库里的 next_run_at 本身就是最早未执行的 occurrence；未来计划直接复用。
    if schedule.next_run_at >= start:
        return schedule.next_run_at

    if schedule.kind == SCHEDULE_INTERVAL:
        interval = max(MIN_INTERVAL_SECONDS, schedule.interval_seconds)
        steps = max(0, math.ceil((start - schedule.next_run_at) / interval))
        occurrence = schedule.next_run_at + steps * interval
        if occurrence < start:
            occurrence += interval
        return occurrence
    if schedule.kind in (SCHEDULE_DAILY, SCHEDULE_WEEKLY):
        occurrence = _next_recurring(schedule, start - 1.0)
        if occurrence is None:
            return None
        while occurrence < start:
            occurrence = _next_recurring(schedule, occurrence)
            if occurrence is None:
                return None
        return occurrence
    return None


def _next_slot(schedule: ScheduleView, now: float) -> tuple[float, int, float, bool]:
    """返回 (本次实例时间, 错过次数, 下次执行时间, 是否继续启用)。"""
    slot = schedule.next_run_at
    if schedule.kind == SCHEDULE_INTERVAL:
        interval = max(MIN_INTERVAL_SECONDS, schedule.interval_seconds)
        missed = 0
        if now > slot:
            missed = int((now - slot) // interval)
            slot = slot + missed * interval
        return slot, missed, slot + interval, True
    if schedule.kind in (SCHEDULE_DAILY, SCHEDULE_WEEKLY):
        next_at = _next_recurring(schedule, slot)
        missed = 0
        while next_at is not None and next_at <= now and missed < 10000:
            missed += 1
            slot = next_at
            next_at = _next_recurring(schedule, slot)
        return slot, missed, next_at if next_at is not None else slot, True
    # once：错过也只在当前时刻补一次，随后停用
    return slot, 0, slot, False


def _iso_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=dt_timezone.utc).isoformat(timespec="milliseconds")
