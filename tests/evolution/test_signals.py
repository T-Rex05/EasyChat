"""学习信号测试（Task 11）：去重、禁用/撤权、暂停、lease 恢复、系统主体。"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.evolution.api import EvolutionService
from backend.modules.evolution.budget import BudgetManager
from backend.modules.evolution.contracts import SYSTEM_USER_ID, TASK_DONE, TASK_REJECTED
from backend.modules.evolution.worker import EvolutionWorker
from backend.platform.jobs import JobQueue
from backend.shared.errors import InvalidInputError
from tests.support.rig import FakeClock, make_rig


def _user(rig):
    return rig.seed_user(
        role="user", grants=("chat.use", "evolution.view"),
        username=f"evo_{uuid.uuid4().hex[:6]}",
    )


def _admin(rig):
    return rig.seed_user(role="super_admin", username=f"adm_{uuid.uuid4().hex[:6]}")


@pytest.fixture
def env(tmp_path):
    clock = FakeClock(1_000_000.0)
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    queue = JobQueue(rig.db, clock=clock)
    budget = BudgetManager(rig.db, clock=clock, daily_limit=20_000, task_limit=5_000)
    service = EvolutionService(
        rig.db, access=rig.access, queue=queue, budget=budget, clock=clock,
    )
    yield rig, service, queue, budget, clock
    rig.db.close()


def test_duplicate_feedback_learns_once(env):
    rig, service, queue, _, _ = env
    user = _user(rig)
    first, inserted = service.enqueue_feedback(
        user, source_event_id="fb-1", run_id="run-1",
        evidence={"task_kind": "chat", "success": True, "user_feedback": "回答很好"},
    )
    second, inserted_again = service.enqueue_feedback(
        user, source_event_id="fb-1", run_id="run-1",
        evidence={"task_kind": "chat", "success": True, "user_feedback": "回答很好"},
    )
    assert inserted is True and inserted_again is False
    assert first.task_id == second.task_id
    worker = EvolutionWorker(service, queue)
    assert worker.tick() == 1
    assert worker.tick() == 0
    assert len(service.experiences(user)) == 1
    assert service.task(first.task_id).status == TASK_DONE


def test_disabled_user_blocks_learning(env):
    rig, service, queue, _, _ = env
    user = _user(rig)
    admin = _admin(rig)
    task, _ = service.enqueue_feedback(
        user, source_event_id="fb-disabled", evidence={"success": False},
    )
    rig.access.set_user_status(admin, user.user_id, 0)
    EvolutionWorker(service, queue).tick()
    assert service.task(task.task_id).status == TASK_REJECTED
    assert service.repo.experiences(user.user_id) == []


def test_revoked_permission_blocks_learning(env):
    rig, service, queue, _, _ = env
    user = _user(rig)
    admin = _admin(rig)
    task, _ = service.enqueue_feedback(
        user, source_event_id="fb-revoke", evidence={"success": True},
    )
    rig.access.set_user_permission(admin, user.user_id, "chat.use", False)
    EvolutionWorker(service, queue).tick()
    assert service.task(task.task_id).status == TASK_REJECTED


def test_pause_prevents_claim_until_resumed(env):
    rig, service, queue, _, _ = env
    admin = _admin(rig)
    user = _user(rig)
    task, _ = service.enqueue_feedback(
        user, source_event_id="fb-pause", evidence={"success": True},
    )
    service.pause(admin, True)
    assert EvolutionWorker(service, queue).tick() == 0
    assert service.task(task.task_id).status == "pending"

    service.pause(admin, False)
    assert EvolutionWorker(service, queue).tick() == 1
    assert service.task(task.task_id).status == TASK_DONE


def test_learning_task_cannot_trigger_itself(env):
    rig, service, _, _, _ = env
    user = _user(rig)
    with pytest.raises(InvalidInputError):
        service.enqueue_feedback(
            user, source_event_id="fb-self",
            evidence={"source": "evolution", "success": True},
        )


def test_system_feedback_uses_explicit_system_owner(env):
    _, service, queue, _, _ = env
    task, inserted = service.enqueue_system_feedback(
        source_event_id="fb-system", evidence={"source": "system", "success": True},
    )
    assert inserted is True
    assert task.owner_id == SYSTEM_USER_ID
    EvolutionWorker(service, queue).tick()
    experiences = service.experiences()
    assert experiences and experiences[0].owner_id == SYSTEM_USER_ID


def test_expired_lease_is_recovered(env):
    rig, service, queue, _, clock = env
    user = _user(rig)
    task, _ = service.enqueue_feedback(
        user, source_event_id="fb-lease", evidence={"success": True},
    )
    # 模拟上一个进程认领后崩溃：lease 已过期
    with rig.db.transaction() as conn:
        conn.execute(
            "UPDATE jobs SET state='leased', lease_until=?, lease_owner='dead-worker' "
            "WHERE dedup_key=?",
            (clock() - 10, f"evolution:{user.user_id}:fb-lease"),
        )
    assert queue.recover_expired_leases()
    assert EvolutionWorker(service, queue).tick() == 1
    assert service.task(task.task_id).status == TASK_DONE
