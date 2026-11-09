"""scheduling 模块公开契约：提醒计划与到期实例。"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.modules.delivery.contracts import DeliveryTarget

SCHEDULE_ONCE = "once"
SCHEDULE_INTERVAL = "interval"
SCHEDULE_DAILY = "daily"
SCHEDULE_WEEKLY = "weekly"

CONTENT_TEXT = "text"
CONTENT_BRIEFING = "briefing"
CONTENT_KINDS = frozenset({CONTENT_TEXT, CONTENT_BRIEFING})
BRIEFING_KINDS = frozenset({"morning", "evening", "weekly", "mood_weekly", "ai_news"})

OCCURRENCE_PENDING = "pending"
OCCURRENCE_QUEUED = "queued"
OCCURRENCE_MISSED = "missed"


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    """创建计划的完整输入；repository 只接受这一种形状，避免长参数散落。"""

    owner_id: int
    title: str
    text: str
    target: DeliveryTarget
    kind: str
    next_run_at: float
    interval_seconds: int = 0
    at_time: str = ""
    timezone: str = "Asia/Shanghai"
    weekday: int = 0
    content_kind: str = CONTENT_TEXT
    briefing_kind: str = ""


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
    weekday: int = 0
    content_kind: str = CONTENT_TEXT
    briefing_kind: str = ""


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
    job_id: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
