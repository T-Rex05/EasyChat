"""profiles 模块公开契约：人格、安静时段与情绪条目。"""
from __future__ import annotations

from dataclasses import dataclass, field

PERSONA_WARM = "warm"
PERSONA_CONCISE = "concise"
PERSONA_PLAYFUL = "playful"
PERSONA_DIRECT = "direct"
PERSONA_CUSTOM = "custom"
PERSONA_PRESETS = frozenset(
    {PERSONA_WARM, PERSONA_CONCISE, PERSONA_PLAYFUL, PERSONA_DIRECT, PERSONA_CUSTOM}
)

EMOJI_LEVELS = frozenset({"none", "sparse", "rich"})
PROACTIVITY_LEVELS = frozenset({"low", "normal", "high"})

PRESET_NAMES = {
    "温柔": PERSONA_WARM,
    "干练": PERSONA_CONCISE,
    "俏皮": PERSONA_PLAYFUL,
    "直给": PERSONA_DIRECT,
}

MAX_CUSTOM_INSTRUCTION = 500
MAX_EVIDENCE_CHARS = 60
MAX_MOOD_LABELS = 3
MOOD_LABELS = frozenset(
    {
        "开心", "平静", "焦虑", "低落", "疲惫", "生气", "孤独",
        "加班", "睡眠", "关系", "健康", "家庭", "工作", "学习", "金钱",
    }
)
MOOD_RETENTION_DEFAULT = 90


@dataclass(frozen=True, slots=True)
class ProfileView:
    owner_id: int
    persona_preset: str
    address_form: str
    max_chars: int
    emoji_level: str
    proactivity: str
    quiet_start: str
    quiet_end: str
    timezone: str
    custom_instruction: str
    mood_opt_in: bool
    mood_retention_days: int
    last_care_at: str | None
    persona_revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class QuietWindow:
    active: bool
    end_epoch: float
    timezone: str


@dataclass(frozen=True, slots=True)
class MoodEntry:
    entry_id: str
    owner_id: int
    entry_date: str
    score: int
    labels: tuple[str, ...]
    summary: str
    evidence: tuple[str, ...]
    source_run_id: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MoodWeek:
    days: tuple[MoodEntry, ...] = ()
    average: float = 0.0
    label_counts: tuple[tuple[str, int], ...] = ()
    low_days: int = 0
    missing_days: int = 7
    sufficient: bool = False
    consecutive_low_days: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CareDecision:
    message: str
    local_date: str


@dataclass(frozen=True, slots=True)
class MoodDeleteResult:
    deleted: int
