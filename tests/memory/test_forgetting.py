"""遗忘测试（Task 9）：墓碑不保留原文、版本清除、按来源/内容阻止重提取。"""
from __future__ import annotations

import json

import pytest

from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.shared.errors import ForbiddenError, NotFoundError
from tests.memory.helpers import make_memory_rig, owner_a, owner_b


@pytest.fixture
def env(tmp_path):
    rig, service = make_memory_rig(tmp_path)
    user = owner_a(rig)
    yield rig, service, user
    rig.db.close()


def _candidate(content: str, ref: str, kind: str = "event") -> MemoryCandidate:
    return MemoryCandidate(
        kind=kind, content=content,
        source_refs=(SourceRef(kind="message", ref=ref),),
        source_type="user_confirmed",
    )


def test_forget_by_memory_id_scrubs_content_and_history(env):
    rig, service, user = env
    record = service.remember(user, _candidate("小林对花生过敏", "msg-allergy"))
    result = service.forget(user, memory_id=record.memory_id, reason="用户要求删除")
    assert result.forgotten == 1
    assert result.affected_ids == (record.memory_id,)

    row = rig.db.connect()
    try:
        memory = row.execute("SELECT content, status FROM memories WHERE id=?", (record.memory_id,)).fetchone()
        revisions = row.execute("SELECT count(*) AS c FROM memory_revisions WHERE memory_id=?", (record.memory_id,)).fetchone()
        rules = row.execute("SELECT * FROM forget_rules WHERE owner_id=?", (user.user_id,)).fetchall()
    finally:
        row.close()
    assert memory["content"] == ""
    assert memory["status"] == "deleted"
    assert revisions["c"] == 0
    assert rules
    # 墓碑不含原文
    assert "花生" not in json.dumps([dict(r) for r in rules], ensure_ascii=False)
    assert service.list(user) == []


def test_forget_by_memory_id_blocks_reextraction(env):
    rig, service, user = env
    record = service.remember(user, _candidate("小林对花生过敏", "msg-allergy"))
    service.forget(user, memory_id=record.memory_id)
    with pytest.raises(ForbiddenError):
        service.remember(user, _candidate("小林对花生过敏", "msg-allergy"))


def test_forget_by_source_ref_cascades_and_blocks_source(env):
    _, service, user = env
    first = service.remember(user, _candidate("项目 A 在九月上线", "msg-src"))
    second = service.remember(user, _candidate("项目 A 上线前要回归", "msg-src", kind="experience"))
    result = service.forget(user, source_ref="msg-src")
    assert result.forgotten == 2
    assert set(result.affected_ids) == {first.memory_id, second.memory_id}
    with pytest.raises(ForbiddenError):
        service.remember(user, _candidate("同一来源的新记忆", "msg-src"))


def test_forget_by_query_scrubs_matching_content(env):
    rig, service, user = env
    service.remember(user, _candidate("小林对花生过敏", "msg-query"))
    result = service.forget(user, query="花生")
    assert result.forgotten == 1
    with pytest.raises(ForbiddenError):
        service.remember(user, _candidate("小林对花生过敏", "msg-new-source"))


def test_forget_rule_can_precede_extraction(env):
    _, service, user = env
    service.forget(user, source_ref="msg-future", reason="先禁止该来源")
    with pytest.raises(ForbiddenError):
        service.remember(user, _candidate("未来才提取的内容", "msg-future"))


def test_cannot_forget_other_users_memory(env):
    rig, service, user = env
    other = owner_b(rig)
    record = service.remember(user, _candidate("A 的记忆", "msg-a"))
    with pytest.raises(NotFoundError):
        service.forget(other, memory_id=record.memory_id)
    with pytest.raises(NotFoundError):
        service.revise(other, record.memory_id, 1, content="越权修改")


def test_deleted_memory_cannot_be_revised(env):
    _, service, user = env
    record = service.remember(user, _candidate("会被遗忘", "msg-del"))
    service.forget(user, memory_id=record.memory_id)
    from backend.shared.errors import ConflictError

    with pytest.raises(ConflictError):
        service.revise(user, record.memory_id, 1, content="改不回来")
