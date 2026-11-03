"""记忆版本/反馈/幂等信号测试（Task 9）。"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.memory.api import MemoryService
from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.modules.memory.worker import MemoryWorker
from backend.platform.jobs import JobQueue
from backend.shared.errors import ConflictError, ForbiddenError, InvalidInputError
from tests.memory.helpers import make_memory_rig, owner_a


def _candidate(content: str = "喜欢黑咖啡", ref: str = "msg-1") -> MemoryCandidate:
    return MemoryCandidate(
        kind="preference", content=content,
        source_refs=(SourceRef(kind="message", ref=ref),),
        source_type="user_confirmed", confidence=0.9,
    )


@pytest.fixture
def env(tmp_path):
    rig, service = make_memory_rig(tmp_path)
    user = owner_a(rig)
    yield rig, service, user
    rig.db.close()


def test_revise_increments_version_and_keeps_history(env):
    _, service, user = env
    record = service.remember(user, _candidate())
    assert record.version == 1
    assert len(service.repo.revisions(record.memory_id)) == 1

    revised = service.revise(
        user, record.memory_id, 1, content="喜欢美式咖啡，不加糖", reason="用户纠正",
    )
    assert revised.version == 2
    assert revised.content == "喜欢美式咖啡，不加糖"
    revisions = service.repo.revisions(record.memory_id)
    assert [r["version"] for r in revisions] == [1, 2]
    assert revisions[1]["reason"] == "用户纠正"


def test_stale_expected_version_rejected(env):
    _, service, user = env
    record = service.remember(user, _candidate())
    service.revise(user, record.memory_id, 1, content="第一次修改")
    with pytest.raises(ConflictError):
        service.revise(user, record.memory_id, 1, content="过期修改")
    assert service.repo.get(record.memory_id).version == 2


def test_empty_revision_rejected(env):
    _, service, user = env
    record = service.remember(user, _candidate())
    with pytest.raises(InvalidInputError):
        service.revise(user, record.memory_id, 1, content="  ")


def test_feedback_is_idempotent(env):
    _, service, user = env
    record = service.remember(user, _candidate())
    assert service.record_feedback(user, record.memory_id, "evt-1", "used") is True
    assert service.record_feedback(user, record.memory_id, "evt-1", "used") is False


def test_source_type_and_confidence_retained(env):
    _, service, user = env
    confirmed = service.remember(user, _candidate("手写事实", "msg-c"))
    inferred = service.remember(user, MemoryCandidate(
        kind="fact", content="模型推断的偏好", confidence=0.3,
        source_type="model_inferred",
        source_refs=(SourceRef(kind="message", ref="msg-i"),),
    ))
    assert confirmed.source_type == "user_confirmed"
    assert inferred.source_type == "model_inferred"
    assert inferred.confidence == pytest.approx(0.3)


def test_signal_job_processed_once(tmp_path):
    rig, _ = make_memory_rig(tmp_path)
    queue = JobQueue(rig.db, clock=rig.clock)
    service = MemoryService(rig.db, access=rig.access, queue=queue)
    user = owner_a(rig)
    payload = {
        "kind": "fact", "content": "喜欢喝乌龙茶",
        "source_refs": [{"kind": "message", "ref": f"msg-{uuid.uuid4().hex[:6]}"}],
        "source_type": "user_confirmed",
    }
    first = service.enqueue_signal(
        user, signal="remember", source_event_id="sig-1", payload=payload,
    )
    second = service.enqueue_signal(
        user, signal="remember", source_event_id="sig-1", payload=payload,
    )
    assert first.duplicate is False and first.signal_id
    assert second.duplicate is True and second.signal_id == first.signal_id

    worker = MemoryWorker(service, queue)
    assert worker.tick() == 1
    assert worker.tick() == 0
    records = service.list(user)
    assert len([r for r in records if r.content == "喜欢喝乌龙茶"]) == 1


def test_correct_signal_uses_expected_version(tmp_path):
    rig, _ = make_memory_rig(tmp_path)
    queue = JobQueue(rig.db, clock=rig.clock)
    service = MemoryService(rig.db, access=rig.access, queue=queue)
    user = owner_a(rig)
    record = service.remember(user, _candidate("喜欢黑咖啡", "msg-correct"))
    receipt = service.enqueue_signal(
        user, signal="correct", source_event_id="sig-correct",
        payload={"memory_id": record.memory_id, "expected_version": 1,
                 "content": "喜欢拿铁", "reason": "用户纠正"},
    )
    assert receipt.duplicate is False
    MemoryWorker(service, queue).tick()
    assert service.repo.get(record.memory_id).content == "喜欢拿铁"
    assert service.repo.get(record.memory_id).version == 2


def test_stage_complete_without_content_is_noop(tmp_path):
    rig, _ = make_memory_rig(tmp_path)
    queue = JobQueue(rig.db, clock=rig.clock)
    service = MemoryService(rig.db, access=rig.access, queue=queue)
    user = owner_a(rig)
    service.enqueue_signal(
        user, signal="stage_complete", source_event_id="sig-stage",
        payload={"session_id": "sess-1"},
    )
    MemoryWorker(service, queue).tick()
    assert service.list(user) == []


def test_remember_requires_memory_edit(tmp_path):
    rig, service = make_memory_rig(tmp_path)
    user = rig.seed_user(
        role="user", revokes=("memory.edit",), username=f"no_edit_{uuid.uuid4().hex[:6]}",
    )
    with pytest.raises(ForbiddenError):
        service.remember(user, _candidate("不该写入", "msg-x"))


def test_service_rejects_candidate_without_source(env):
    _, service, user = env
    from backend.modules.memory.extractor import ExtractionError

    with pytest.raises(ExtractionError):
        service.remember(user, MemoryCandidate(kind="fact", content="无来源的推断", source_refs=()))
