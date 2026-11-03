"""scheduling 模块公开契约：提醒计划与到期实例。"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.modules.delivery.contracts import DeliveryTarget

SCHEDULE_ONCE = "once"
SCHEDULE_INTERVAL = "interval"
SCHEDULE_DAILY = "daily"

OCCURRENCE_PENDING = "pending"
OCCURRENCE_QUEUED = "queued"
OCCURRENCE_MISSED = "missed"


@dataclass(frozen=True, slots=True)
class ScheduleView:
    schedule_id: str
    owner_id: int
    title: str
    text: str
    target: DeliveryTarget
    kind: str
    interval_seconds: int
    at_time: str
    timezone: str
    next_run_at: float
    enabled: bool
    last_run_at: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class OccurrenceView:
    occurrence_id: str
    schedule_id: str
    scheduled_at: str
    state: str
    delivery_id: str
    missed: int
    created_at: str
    processed_at: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
