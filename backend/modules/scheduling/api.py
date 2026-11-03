"""scheduling 模块公开接口：建立提醒、恢复到期实例、生成投递请求。

到期只生成“最新未完成实例”，错过多次时记录 missed 计数，不补发无限历史；
实例与投递请求在同一 SQLite 事务提交。调度器只有一个生命周期入口。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.scheduling.contracts import (
    SCHEDULE_DAILY,
    SCHEDULE_INTERVAL,
    SCHEDULE_ONCE,
    OccurrenceView,
    ScheduleView,
)
from backend.modules.scheduling.repository import SchedulingRepository
from backend.platform.sqlite import Database
from backend.shared.errors import InvalidInputError

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Asia/Shanghai"
MIN_INTERVAL_SECONDS = 60


class SchedulingService:
    def __init__(
        self,
        db: Database,
        *,
        delivery: DeliveryService,
        access: Any,
        clock=time.time,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> None:
        self.db = db
        self.repo = SchedulingRepository(db)
        self.delivery = delivery
        self.access = access
        self.clock = clock
        self.timezone_name = timezone_name

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
    ) -> ScheduleView:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "cron.create")
        if not text.strip():
            raise InvalidInputError("提醒内容不能为空")
        if not target.ref:
            raise InvalidInputError("提醒目标不能为空")
        now = self.clock()
        chosen = sum(1 for value in (at, every_seconds, daily_at) if value)
        if chosen != 1:
            raise InvalidInputError("必须且只能指定 at / every_seconds / daily_at 之一")

        if at:
            next_run_at = _parse_at(at, self.timezone_name)
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
        else:
            at_time = _validate_daily(daily_at)
            kind = SCHEDULE_DAILY
            interval = 0
            next_run_at = _next_daily(now, at_time, self.timezone_name)

        return self.repo.create(
            owner_id=principal.user_id,
            title=title.strip()[:120],
            text=text,
            target=target,
            kind=kind,
            next_run_at=next_run_at,
            interval_seconds=interval,
            at_time=at_time,
            timezone=self.timezone_name,
        )

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

    def occurrences(self, actor, schedule_id: str, limit: int = 20) -> list[OccurrenceView]:
        principal = self.access.validate_principal(actor)
        schedule = self.repo.get(schedule_id)
        if schedule.owner_id != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        return self.repo.occurrences(schedule_id, limit=limit)

    # ---- 到期处理 ----------------------------------------------------------------

    def tick(self, now: float | None = None) -> list[str]:
        """处理到期计划；返回本次新建的 delivery id 列表（测试直接调用）。"""
        current = self.clock() if now is None else float(now)
        created: list[str] = []
        for schedule in self.repo.due(current):
            slot, missed, next_run_at, enabled = _next_slot(schedule, current, self.timezone_name)
            scheduled_at = _iso_from_epoch(slot)
            with self.db.transaction() as conn:
                occurrence_id, inserted = self.repo.insert_occurrence_tx(
                    conn, schedule.schedule_id, scheduled_at, missed=missed,
                )
                if inserted:
                    delivery_id = self.delivery.enqueue_in_transaction(
                        conn,
                        owner_id=schedule.owner_id,
                        target=schedule.target,
                        text=schedule.text,
                        dedup_key=f"schedule:{schedule.schedule_id}:{scheduled_at}",
                        source="schedule",
                    )
                    self.repo.mark_occurrence_queued_tx(conn, occurrence_id, delivery_id)
                    created.append(delivery_id)
                self.repo.advance_tx(
                    conn, schedule.schedule_id,
                    next_run_at=next_run_at, enabled=enabled,
                    last_run_at=scheduled_at,
                )
        return created


# ---- 时间计算（纯函数，便于测试） ------------------------------------------------


def _parse_at(value: str, timezone_name: str) -> float:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidInputError(f"at 不是合法 ISO 时间: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.timestamp()


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


def _next_slot(schedule: ScheduleView, now: float, timezone_name: str) -> tuple[float, int, float, bool]:
    """返回 (本次实例时间, 错过次数, 下次执行时间, 是否继续启用)。"""
    slot = schedule.next_run_at
    missed = 0
    if schedule.kind == SCHEDULE_INTERVAL:
        interval = max(MIN_INTERVAL_SECONDS, schedule.interval_seconds)
        if now > slot:
            missed = int((now - slot) // interval)
            slot = slot + missed * interval
        return slot, missed, slot + interval, True
    if schedule.kind == SCHEDULE_DAILY:
        next_at = _next_daily(slot, schedule.at_time, timezone_name)
        while next_at <= now and missed < 10000:
            missed += 1
            slot = next_at
            next_at = _next_daily(slot, schedule.at_time, timezone_name)
        return slot, missed, next_at, True
    # once：错过也只在当前时刻补一次，随后停用
    return slot, 0, slot, False


def _iso_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat(timespec="milliseconds")
