"""evolution 公开接口：唯一学习调度入口、证据、预算与经验写入。"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from backend.modules.evolution.budget import BudgetManager, Reservation
from backend.modules.evolution.contracts import (
    SOURCE_CHAT,
    SOURCE_EVOLUTION,
    SYSTEM_USER_ID,
    TASK_DONE,
    TASK_PAUSED,
    TASK_REJECTED,
    EvolutionTaskView,
    ExperienceView,
    LearningEvidence,
    LearningResult,
)
from backend.modules.evolution.evidence import default_learner
from backend.modules.evolution.repository import EvolutionRepository
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import ForbiddenError, InvalidInputError

logger = logging.getLogger(__name__)

DEFAULT_TASK_TOKENS = 5_000
DEFAULT_MAX_TASK_SECONDS = 120.0


class EvolutionService:
    def __init__(
        self,
        db: Database,
        *,
        access: Any,
        queue: Any,
        budget: BudgetManager | None = None,
        learner: Callable[[EvolutionTaskView, LearningEvidence], LearningResult] = default_learner,
        clock=time.time,
        task_tokens: int = DEFAULT_TASK_TOKENS,
        max_task_seconds: float = DEFAULT_MAX_TASK_SECONDS,
    ) -> None:
        self.db = db
        self.repo = EvolutionRepository(db)
        self.access = access
        self.queue = queue
        self.budget = budget or BudgetManager(db, clock=clock, task_limit=task_tokens)
        self.learner = learner
        self.clock = clock
        self.task_tokens = task_tokens
        self.max_task_seconds = max_task_seconds

    # ---- 入队 ------------------------------------------------------------------

    def enqueue_feedback(
        self,
        actor: Principal,
        *,
        source_event_id: str,
        run_id: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> tuple[EvolutionTaskView, bool]:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "chat.use")
        source = str((evidence or {}).get("source") or SOURCE_CHAT)
        if source == SOURCE_EVOLUTION:
            raise InvalidInputError("学习任务不能触发另一个学习任务")
        if not source_event_id:
            raise InvalidInputError("缺少 source_event_id")
        return self._enqueue(
            owner_id=principal.user_id,
            source_event_id=source_event_id,
            run_id=run_id,
            source=source,
            evidence=evidence or {},
        )

    def enqueue_system_feedback(
        self,
        *,
        source_event_id: str,
        run_id: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> tuple[EvolutionTaskView, bool]:
        """显式系统主体（SYSTEM_USER_ID=0），不猜测 user_id=1。"""
        payload = dict(evidence or {})
        payload["source"] = str(payload.get("source") or "system")
        return self._enqueue(
            owner_id=SYSTEM_USER_ID, source_event_id=source_event_id,
            run_id=run_id, source=str(payload["source"]), evidence=payload,
        )

    def _enqueue(
        self, *, owner_id: int, source_event_id: str, run_id: str, source: str, evidence: dict
    ) -> tuple[EvolutionTaskView, bool]:
        task, inserted = self.repo.create_task(
            owner_id=owner_id, source_event_id=source_event_id,
            run_id=run_id, source=source, evidence=evidence,
        )
        if inserted:
            self.queue.enqueue(
                kind="evolution.learn",
                dedup_key=f"evolution:{owner_id}:{source_event_id}",
                payload={"task_id": task.task_id},
                owner_id=owner_id if owner_id != SYSTEM_USER_ID else None,
            )
        return task, inserted

    # ---- 暂停/查询 ---------------------------------------------------------------

    def pause(self, actor: Principal, paused: bool) -> bool:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "system.manage")
        self.repo.set_paused(paused)
        return paused

    def paused(self) -> bool:
        return self.repo.paused()

    def task(self, task_id: str) -> EvolutionTaskView:
        return self.repo.get_task(task_id)

    def experiences(self, actor: Principal | None = None, limit: int = 50) -> list[ExperienceView]:
        if actor is None:
            return self.repo.experiences(None, limit=limit)
        principal = self.access.validate_principal(actor)
        if self.access.has_permission(principal, "evolution.view"):
            return self.repo.experiences(principal.user_id, limit=limit)
        raise ForbiddenError("缺少权限: evolution.view")

    # ---- 处理 ------------------------------------------------------------------

    def process_task(
        self, task_id: str, *,
        learner: Callable[[EvolutionTaskView, LearningEvidence], LearningResult] | None = None,
    ) -> ExperienceView | None:
        task = self.repo.get_task(task_id)
        if task.status in (TASK_DONE, TASK_REJECTED):
            return None
        if self.repo.paused():
            return None
        evidence_data = self.repo.task_evidence(task_id)
        evidence = LearningEvidence(
            source_event_id=evidence_data.get("source_event_id") or task.source_event_id,
            run_id=str(evidence_data.get("run_id") or task.run_id),
            source=str(evidence_data.get("source") or task.source),
            task_kind=str(evidence_data.get("task_kind") or ""),
            success=evidence_data.get("success"),
            user_feedback=str(evidence_data.get("user_feedback") or ""),
            notes=str(evidence_data.get("notes") or ""),
            counterexample=str(evidence_data.get("counterexample") or ""),
            user_confirmed=bool(evidence_data.get("user_confirmed", False)),
        )

        # 用户被禁用/权限撤销：后台任务立即停止，不再调用模型
        if task.owner_id != SYSTEM_USER_ID:
            try:
                principal = self.access.snapshot_principal(task.owner_id)
                self.access.require_permission(principal, "chat.use")
            except Exception as exc:  # noqa: BLE001  Forbidden/Unauthenticated 都拒绝
                self.repo.set_task_status(task_id, status=TASK_REJECTED, error=f"用户不可用: {exc}")
                return None

        reservation: Reservation | None = self.budget.reserve(
            task.owner_id, task_id=task_id, worst_tokens=self.task_tokens,
        )
        if reservation is None:
            self.repo.set_task_status(
                task_id, status=TASK_PAUSED, error="超出进化预算，暂停学习",
            )
            return None

        started = self.clock()
        try:
            if self.clock() - started > self.max_task_seconds:
                raise TimeoutError("学习任务超出时间预算")
            result = (learner or self.learner)(task, evidence)
            self.budget.settle(
                reservation, result.tokens_used, usage_known=result.usage_known,
            )
        except Exception as exc:  # noqa: BLE001  结算策略：未知失败保留预留
            self.budget.settle(reservation, 0, usage_known=False)
            self.repo.set_task_status(task_id, status=TASK_REJECTED, error=str(exc))
            logger.warning("学习任务失败 task=%s: %s", task_id, exc)
            return None

        source_type = "user_confirmed" if evidence.user_confirmed else "model_inferred"
        experience = self.repo.add_experience(
            task_id=task_id, owner_id=task.owner_id, run_id=task.run_id,
            content=result.content, conditions=result.conditions,
            counterexample=result.counterexample, confidence=result.confidence,
            source_type=source_type,
        )
        self.repo.set_task_status(
            task_id, status=TASK_DONE, budget_reserved=reservation.tokens,
            budget_used=result.tokens_used if result.usage_known else 0,
        )
        return experience
