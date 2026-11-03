"""evolution 模块公开契约（Task 11）：学习任务、证据、预算与经验。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

SYSTEM_USER_ID = 0

TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_DONE = "done"
TASK_REJECTED = "rejected"
TASK_PAUSED = "paused"

SOURCE_CHAT = "chat"
SOURCE_SCHEDULE = "schedule"
SOURCE_MEMORY = "memory"
SOURCE_SYSTEM = "system"
SOURCE_EVOLUTION = "evolution"  # 不允许学习任务再触发学习自身


@dataclass(frozen=True, slots=True)
class LearningEvidence:
    """一次反馈的可追溯证据；不把模型自评当用户事实。"""

    source_event_id: str
    run_id: str = ""
    source: str = SOURCE_CHAT
    task_kind: str = ""
    success: bool | None = None
    user_feedback: str = ""
    notes: str = ""
    counterexample: str = ""
    user_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class LearningResult:
    content: str
    tokens_used: int = 0
    usage_known: bool = True
    conditions: str = ""
    counterexample: str = ""
    confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class EvolutionTaskView:
    task_id: str
    owner_id: int
    source_event_id: str
    run_id: str
    source: str
    status: str
    error: str
    budget_reserved: int
    budget_used: int
    created_at: str


@dataclass(frozen=True, slots=True)
class ExperienceView:
    experience_id: str
    task_id: str
    owner_id: int
    run_id: str
    content: str
    conditions: str
    counterexample: str
    confidence: float
    source_type: str
    created_at: str


class Learner(Protocol):
    def __call__(self, task: EvolutionTaskView, evidence: LearningEvidence) -> LearningResult: ...
