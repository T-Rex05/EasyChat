"""memory 模块公开契约（架构 §8、Task 9）。"""
from __future__ import annotations

from dataclasses import dataclass

KIND_FACT = "fact"
KIND_PREFERENCE = "preference"
KIND_EVENT = "event"
KIND_EXPERIENCE = "experience"
VALID_KINDS = frozenset({KIND_FACT, KIND_PREFERENCE, KIND_EVENT, KIND_EXPERIENCE})

STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"
STATUS_DELETED = "deleted"

SOURCE_USER_CONFIRMED = "user_confirmed"
SOURCE_MODEL_INFERRED = "model_inferred"

SIGNAL_REMEMBER = "remember"
SIGNAL_FORGET = "forget"
SIGNAL_CORRECT = "correct"
SIGNAL_STAGE_COMPLETE = "stage_complete"
SIGNAL_FEEDBACK = "feedback"

DEFAULT_CANDIDATE_LIMIT = 80
DEFAULT_TOP_K = 5
DEFAULT_TOKEN_BUDGET = 2000
DEFAULT_LIST_LIMIT = 50

# 中文检索的保守同义扩展（可测、可增补；不承诺语义全覆盖）
SYNONYMS: dict[str, tuple[str, ...]] = {
    "担心": ("焦虑", "害怕", "顾虑"),
    "直播": ("开播", "带货", "直播"),
    "工作": ("上班", "项目", "公司"),
    "孩子": ("女儿", "儿子", "小孩"),
    "旅行": ("旅游", "出行", "度假"),
    "健康": ("身体", "体检", "生病"),
    "学习": ("课程", "读书", "考试"),
    "咖啡": ("咖啡因", "饮品"),
}

OLD_MEMORY_HINTS = ("上次", "以前", "之前", "还记得", "曾经", "过去", "早先")


@dataclass(frozen=True, slots=True)
class SourceRef:
    kind: str  # message / event / user / run
    ref: str
    quote: str = ""


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    kind: str
    content: str
    source_refs: tuple[SourceRef, ...]
    scope: str = "user"
    event_at: str | None = None
    confidence: float = 0.5
    source_type: str = SOURCE_MODEL_INFERRED
    tags: tuple[str, ...] = ()
    supersedes: str | None = None
    pinned: bool = False


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    owner_id: int
    kind: str
    content: str
    source_refs: tuple[SourceRef, ...]
    scope: str
    event_at: str | None
    recorded_at: str
    version: int
    status: str
    pinned: bool
    confidence: float
    source_type: str
    tags: tuple[str, ...]
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class RecallItem:
    memory: MemoryRecord
    score: float
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecallResult:
    items: tuple[RecallItem, ...] = ()
    candidate_count: int = 0
    estimated_tokens: int = 0
    reason: str = ""
    include_archived: bool = False

    @property
    def no_result(self) -> bool:
        return not self.items


@dataclass(frozen=True, slots=True)
class ForgetResult:
    forgotten: int
    rule_recorded: bool
    affected_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SignalReceipt:
    signal_id: str
    state: str
    duplicate: bool
    memory_id: str = ""
