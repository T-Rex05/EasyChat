"""遗忘测试（Task 9）：墓碑不保留原文、版本清除、按来源/内容阻止重提取。"""
from __future__ import annotations

import json

import pytest

from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.platform.jobs import JobQueue
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


def test_forget_clears_quotes_tags_feedback_and_blocks_old_revisions(env):
    rig, service, user = env
    old = SourceRef(kind="message", ref="old-origin", quote="私密旧引文")
    new = SourceRef(kind="message", ref="new-origin", quote="私密新引文")
    record = service.remember(user, MemoryCandidate(
        kind="fact", content="私密旧正文", source_refs=(old,), tags=("私密标签",),
    ))
    service.record_feedback(user, record.memory_id, "feedback-1", "used", "私密反馈")
    service.revise(user, record.memory_id, 1, content="私密新正文", source_refs=(new,))
    service.forget(user, memory_id=record.memory_id, reason="私密旧正文")
    erased = service.repo.get(record.memory_id)
    assert erased.source_refs == ()
    assert erased.tags == ()
    assert service.repo.revisions(record.memory_id) == []
    conn = rig.db.connect()
    try:
        assert conn.execute("SELECT count(*) FROM memory_feedback").fetchone()[0] == 0
        assert "私密" not in json.dumps([dict(r) for r in conn.execute("SELECT * FROM forget_rules")], ensure_ascii=False)
    finally:
        conn.close()
    with pytest.raises(ForbiddenError):
        service.remember(user, _candidate("改写旧信息", old.ref))
    with pytest.raises(ForbiddenError):
        service.remember(user, _candidate("私密旧正文", "other-origin"))


def test_forget_clears_linked_signal_and_legacy_confirmation(env):
    from backend.modules.delivery.contracts import DeliveryTarget
    from backend.modules.delivery.repository import DeliveryRepository

    rig, service, user = env
    record = service.remember(user, _candidate("仅用于回归的秘密", "run-derived"))
    receipt = service.enqueue_signal(user, signal="correct", source_event_id="signal-derived", payload={
        "memory_id": record.memory_id, "content": "仅用于回归的秘密",
    })
    job_id = JobQueue(rig.db).enqueue(
        kind="memory.confirm", dedup_key="memory-confirm:run-derived", owner_id=user.user_id,
        payload={"owner_id": user.user_id, "run_id": "run-derived", "text": "已记住：仅用于回归的秘密"},
    )
    delivery_repo = DeliveryRepository(rig.db)
    delivery = delivery_repo.enqueue(
        owner_id=user.user_id, target=DeliveryTarget(kind="wechat", ref="synthetic"),
        content_text="已记住：仅用于回归的秘密",
        source="memory", dedup_key="memory-confirm:run-derived",
    )
    delivery_repo.ensure_parts(delivery, ["已发出的前缀", "仅用于回归的秘密"])
    delivery_repo.mark_part_sent(delivery, 0)
    service.forget(user, memory_id=record.memory_id)
    assert service.repo.get_signal(receipt.signal_id)["payload"] == "{}"
    conn = rig.db.connect()
    try:
        assert conn.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()[0] == "{}"
        assert tuple(conn.execute(
            "SELECT status, content_text FROM deliveries WHERE id=?", (delivery,),
        ).fetchone()) == ("cancelled", "")
    finally:
        conn.close()
    assert [(part["status"], part["content"]) for part in delivery_repo.parts(delivery)] == [
        ("sent", "已发出的前缀"), ("pending", ""),
    ]


def test_upgrade_from_0026_scrubs_legacy_tombstones(tmp_path):
    import shutil

    from backend.modules.memory.repository import MemoryRepository, source_hash
    from backend.platform.migrations import MIGRATIONS_DIR
    from backend.platform.sqlite import Database, run_migrations, utc_now_iso

    old_migrations = tmp_path / "old-migrations"
    old_migrations.mkdir()
    for migration in MIGRATIONS_DIR.glob("*.sql"):
        if migration.name[:4] <= "0026":
            shutil.copyfile(migration, old_migrations / migration.name)
    db = Database(tmp_path / "upgraded.db")
    assert run_migrations(db, old_migrations)[-1] == "0026"
    now = utc_now_iso()
    secret = "历史私密信息"
    delivery_cases = [
        ("pending", "memory", "pending", True),
        ("retry", "memory", "retry_wait", True),
        ("sent", "memory", "sent", True),
        ("uncertain", "memory", "uncertain", True),
        ("other-source", "assistant", "pending", True),
        ("unlinked", "memory", "pending", False),
        ("other-owner", "memory", "pending", True),
    ]
    with db.transaction() as conn:
        owner_id = conn.execute(
            "INSERT INTO users(username, password, created_at, updated_at) VALUES(?,?,?,?)",
            ("legacy-owner", "unused", now, now),
        ).lastrowid
        other_owner_id = conn.execute(
            "INSERT INTO users(username, password, created_at, updated_at) VALUES(?,?,?,?)",
            ("other-owner", "unused", now, now),
        ).lastrowid
        conn.executemany(
            "INSERT INTO memories(id, owner_id, kind, content, source_refs, recorded_at, "
            "status, created_at, updated_at) VALUES(?,?,'fact',?,?,?,?,?,?)",
            [
                ("legacy-active", owner_id, "仍可读", "[]", now, "active", now, now),
                ("legacy-deleted", owner_id, "", json.dumps([
                    "legacy-invalid-item",
                    {"ref": "legacy-reference", "kind": "message", "quote": secret},
                    *({"ref": case, "kind": "message"} for case, _, _, linked in delivery_cases if linked),
                ]), now, "deleted", now, now),
            ],
        )
        conn.execute("INSERT INTO memory_tags VALUES(?,?)", ("legacy-deleted", secret))
        conn.execute(
            "INSERT INTO forget_rules(id, owner_id, target_kind, target_hash, reason, created_at) "
            "VALUES(?,?,'source_ref',?,?,?)",
            ("legacy-rule", owner_id, source_hash("legacy-reference"), secret, now),
        )
        conn.executemany(
            "INSERT INTO deliveries(id, owner_id, source, target_kind, target_ref, content_text, "
            "dedup_key, status, created_at, updated_at) VALUES(?,?,?,'wechat','test',?,?,?,?,?)",
            (
                (case, other_owner_id if case == "other-owner" else owner_id, source, secret,
                 f"memory-confirm:{case}", status, now, now)
                for case, source, status, _ in delivery_cases
            ),
        )
        conn.executemany(
            "INSERT INTO delivery_parts(id, delivery_id, seq, content, status) VALUES(?,'retry',?,?,?)",
            [("sent-part", 0, secret, "sent"), ("unsent-part", 1, secret, "failed")],
        )
    JobQueue(db).enqueue(
        kind="memory.confirm", dedup_key="legacy-confirm", owner_id=owner_id,
        payload={"owner_id": owner_id, "run_id": "legacy-reference", "text": secret},
    )
    assert "0027" in db.migrate()
    assert db.migrate() == []
    repo = MemoryRepository(db)
    assert repo.get("legacy-active").persona_id is None
    assert repo.get("legacy-active").is_shared is False
    assert repo.get("legacy-active").content == "仍可读"
    assert repo.get("legacy-deleted").source_refs == ()
    assert repo.get("legacy-deleted").tags == ()
    assert repo.source_is_forgotten(owner_id, "legacy-reference")
    conn = db.connect()
    try:
        assert conn.execute("SELECT payload FROM jobs WHERE dedup_key='legacy-confirm'").fetchone()[0] == "{}"
        assert {
            row["id"]: (row["status"], row["content_text"])
            for row in conn.execute("SELECT id, status, content_text FROM deliveries")
        } == {
            case: ("cancelled", "") if case in ("pending", "retry") else (status, secret)
            for case, _, status, _ in delivery_cases
        }
        assert {
            row["id"]: row["content"] for row in conn.execute("SELECT id, content FROM delivery_parts")
        } == {"sent-part": secret, "unsent-part": ""}
    finally:
        conn.close()
    db.close()


def test_forgotten_signal_replay_is_persisted_without_content(env):
    _, service, user = env
    record = service.remember(user, _candidate("合成敏感正文", "original-source"))
    service.forget(user, memory_id=record.memory_id)
    receipt = service.enqueue_signal(user, signal="remember", source_event_id="replayed-message", payload={
        "kind": "fact",
        "content": "合成敏感正文",
        "source_refs": [{"kind": "message", "ref": "original-source", "quote": "合成敏感引文"}],
    })
    assert receipt.state == "rejected"
    assert service.repo.get_signal(receipt.signal_id)["payload"] == "{}"


def test_forget_wins_when_extraction_waits_to_persist(env, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    _, service, user = env
    initial = service.remember(user, _candidate("待忘记的信息", "racing-source"))
    prepared = Event()
    resume = Event()
    create_memory = service.repo.create_memory

    def pause_before_persist(**kwargs):
        prepared.set()
        assert resume.wait(5)
        return create_memory(**kwargs)

    monkeypatch.setattr(service.repo, "create_memory", pause_before_persist)
    with ThreadPoolExecutor(max_workers=1) as pool:
        extracting = pool.submit(service.remember, user, _candidate("重新提取的改写", "racing-source"))
        try:
            assert prepared.wait(5)
            assert service.forget(user, memory_id=initial.memory_id).forgotten == 1
        finally:
            resume.set()
        with pytest.raises(ForbiddenError):
            extracting.result(timeout=5)
    assert service.list(user) == []
