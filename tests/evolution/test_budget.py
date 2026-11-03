"""进化预算测试（Task 11）：预留/核销/未知 usage/每日重置/超预算停止。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.modules.evolution.api import EvolutionService
from backend.modules.evolution.budget import BudgetManager
from backend.modules.evolution.worker import EvolutionWorker
from backend.platform.jobs import JobQueue
from tests.support.rig import FakeClock, make_rig


@pytest.fixture
def env(tmp_path):
    clock = FakeClock(datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp())
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    yield rig, clock
    rig.db.close()


def test_reserve_and_settle_known_usage(env):
    rig, clock = env
    budget = BudgetManager(rig.db, clock=clock, daily_limit=20_000, task_limit=5_000)
    reservation = budget.reserve(1, task_id="t1", worst_tokens=5_000)
    assert reservation is not None
    assert budget.status(1).reserved == 5_000
    budget.settle(reservation, 3_000, usage_known=True)
    status = budget.status(1)
    assert status.reserved == 0
    assert status.used == 3_000
    assert status.remaining == 17_000


def test_unknown_usage_keeps_reservation(env):
    rig, clock = env
    budget = BudgetManager(rig.db, clock=clock)
    reservation = budget.reserve(1, task_id="t1", worst_tokens=5_000)
    budget.settle(reservation, 0, usage_known=False)
    status = budget.status(1)
    assert status.reserved == 5_000  # 不立即返还，防无限透支
    assert status.used == 0


def test_daily_and_single_task_limits(env):
    rig, clock = env
    budget = BudgetManager(rig.db, clock=clock, daily_limit=10_000, task_limit=5_000)
    assert budget.reserve(1, task_id="too-big", worst_tokens=5_001) is None
    first = budget.reserve(1, task_id="t1", worst_tokens=5_000)
    second = budget.reserve(1, task_id="t2", worst_tokens=5_000)
    assert first is not None and second is not None
    assert budget.reserve(1, task_id="t3", worst_tokens=1) is None


def test_daily_reset_by_project_timezone(env):
    rig, clock = env
    budget = BudgetManager(rig.db, clock=clock, daily_limit=5_000, task_limit=5_000)
    assert budget.reserve(1, task_id="t1", worst_tokens=5_000) is not None
    assert budget.reserve(1, task_id="t2", worst_tokens=1) is None
    clock.advance(86400 + 60)
    assert budget.reserve(1, task_id="t3", worst_tokens=5_000) is not None


def test_new_manager_reads_persisted_budget(env):
    rig, clock = env
    first = BudgetManager(rig.db, clock=clock)
    first.reserve(1, task_id="t1", worst_tokens=4_000)
    second = BudgetManager(rig.db, clock=clock)
    assert second.status(1).reserved == 4_000


def test_over_budget_stops_before_learner(env):
    rig, clock = env
    user = rig.seed_user(role="user", grants=("chat.use",), username=f"b_{uuid.uuid4().hex[:6]}")
    queue = JobQueue(rig.db, clock=clock)
    budget = BudgetManager(rig.db, clock=clock, daily_limit=1_000, task_limit=5_000)
    called: list[int] = []

    def learner(task, evidence):
        called.append(1)
        from backend.modules.evolution.contracts import LearningResult

        return LearningResult(content="不应发生", tokens_used=100)

    service = EvolutionService(
        rig.db, access=rig.access, queue=queue, budget=budget, learner=learner, clock=clock,
    )
    task, _ = service.enqueue_feedback(
        user, source_event_id="budget-stop", evidence={"success": True},
    )
    EvolutionWorker(service, queue).tick()
    assert called == []
    assert service.task(task.task_id).status == "paused"
