"""简报公开契约。"""
from __future__ import annotations

from dataclasses import dataclass, field

BRIEFING_MORNING = "morning"
BRIEFING_EVENING = "evening"
BRIEFING_WEEKLY = "weekly"
BRIEFING_MOOD_WEEKLY = "mood_weekly"
BRIEFING_AI_NEWS = "ai_news"

BRIEFING_KIND_LABELS = {
    BRIEFING_MORNING: "早间",
    BRIEFING_EVENING: "晚间",
    BRIEFING_WEEKLY: "周报",
    BRIEFING_MOOD_WEEKLY: "情绪周报",
    BRIEFING_AI_NEWS: "AI 前沿",
}


@dataclass(frozen=True, slots=True)
class BriefingData:
    kind: str
    local_date: str
    timezone: str
    upcoming: tuple[dict[str, object], ...] = ()
    delivered_today: int = 0
    upcoming_count: int = 0
    inbox_unread: int = 0
    mood_opt_in: bool = False
    mood: dict[str, object] = field(default_factory=dict)
    care: bool = False


@dataclass(frozen=True, slots=True)
class BriefingResult:
    text: str
    kind: str
    owner_id: int
    source: str
    skipped_reason: str = ""
