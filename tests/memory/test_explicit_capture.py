"""显式记忆捕获：LLM 候选提取、服务端来源、幂等与确定性降级。"""
from __future__ import annotations

import json

import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.modules.assistant.transcript import load_run_messages
from backend.modules.memory.api import MemoryService
from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.modules.memory.worker import MemoryWorker
from backend.platform.jobs import JobQueue
from tests.support.rig import make_rig


@pytest.mark.asyncio
async def test_explicit_remember_writes_user_confirmed_memory(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()
    session_id = await rig.assistant.create_session(principal, source="wechat")
    receipt = await rig.assistant.submit(
        RunCommand(
            principal=principal, session_id=session_id, source="wechat",
            client_message_id="remember-1", text="记住：我周六通常加班，别约上午",
        )
    )
    service = MemoryService(rig.db, access=rig.access, queue=JobQueue(rig.db))
    worker = MemoryWorker(
        service, JobQueue(rig.db), message_loader=lambda owner_id, run_id: load_run_messages(rig.db, owner_id, run_id)
    )
    with rig.db.transaction() as conn:
        job_id = worker.enqueue_capture_tx(
            conn,
            {"id": receipt.run_id, "owner_id": principal.user_id,
             "status": "completed", "source": "wechat"},
        )
    assert job_id
    await worker.tick()
    records = service.list(principal)
    assert len(records) == 1
    assert records[0].source_type == "user_confirmed"
    assert "周六通常加班" in records[0].content


@pytest.mark.asyncio
async def test_plain_message_does_not_enqueue_capture(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()
    session_id = await rig.assistant.create_session(principal, source="wechat")
    receipt = await rig.assistant.submit(
        RunCommand(
            principal=principal, session_id=session_id, source="wechat",
            client_message_id="plain-1", text="今天好累，随便聊聊",
        )
    )
    service = MemoryService(rig.db, access=rig.access)
    worker = MemoryWorker(
        service, JobQueue(rig.db), message_loader=lambda owner_id, run_id: load_run_messages(rig.db, owner_id, run_id)
    )
    with rig.db.transaction() as conn:
        assert worker.enqueue_capture_tx(
            conn,
            {"id": receipt.run_id, "owner_id": principal.user_id,
             "status": "completed", "source": "wechat"},
        ) is None


def test_remember_word_inside_sentence_is_not_a_command() -> None:
    from backend.modules.memory.capture import should_capture

    assert should_capture("记住：牛奶没了") is True
    assert should_capture("别忘带伞") is True
    assert should_capture("我记住了，不用提醒") is False
    assert should_capture("他说别忘了带伞") is False
    assert should_capture("今天天气不错，随便聊聊") is False


def test_extract_trigger_covers_natural_explicit_expressions() -> None:
    from backend.modules.memory.capture import should_extract

    assert should_extract("以后都别约周六上午") is True
    assert should_extract("我以后都别约周六上午") is True
    assert should_extract("我喜欢少糖的咖啡") is True
    assert should_extract("我讨厌临时改计划") is True
    assert should_extract("我习惯晚上十点后不看消息") is True
    assert should_extract("我对花生过敏") is True
    assert should_extract("别忘带伞") is True
    assert should_extract("他说别忘了带伞") is False
    assert should_extract("他说我喜欢喝咖啡") is False
    assert should_extract("今天天气不错，随便聊聊") is False


class FakeGenerator:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[str, str]] = []

    async def generate(self, system: str, user: str, *, owner_id: int = 0, max_chars: int = 300) -> str:
        self.calls.append((system, user))
        return self.output


async def _submit(rig, principal, text: str):
    session_id = await rig.assistant.create_session(principal, source="wechat")
    return await rig.assistant.submit(
        RunCommand(
            principal=principal, session_id=session_id, source="wechat",
            client_message_id=f"m-{text[:8]}", text=text,
        )
    )


def _enqueue(rig, worker, principal, run_id: str):
    with rig.db.transaction() as conn:
        return worker.enqueue_capture_tx(
            conn,
            {"id": run_id, "owner_id": principal.user_id,
             "status": "completed", "source": "wechat"},
        )


@pytest.mark.asyncio
async def test_natural_expression_is_extracted_by_llm(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()
    receipt = await _submit(rig, principal, "以后都别约周六上午，我要睡懒觉")
    generator = FakeGenerator(json.dumps({
        "kind": "preference",
        "content": "用户希望以后都别约周六上午",
        "evidence": "以后都别约周六上午",
    }, ensure_ascii=False))
    service = MemoryService(rig.db, access=rig.access, queue=JobQueue(rig.db))
    worker = MemoryWorker(
        service, JobQueue(rig.db), message_loader=lambda owner_id, run_id: load_run_messages(rig.db, owner_id, run_id),
        generator=generator,
    )
    assert _enqueue(rig, worker, principal, receipt.run_id)
    await worker.tick()

    records = service.list(principal)
    assert len(records) == 1
    assert records[0].content == "用户希望以后都别约周六上午"
    assert records[0].source_type == "user_confirmed"
    assert records[0].source_refs[0].quote == "以后都别约周六上午"
    assert generator.calls


@pytest.mark.asyncio
async def test_invalid_json_is_dropped_without_retry(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()
    receipt = await _submit(rig, principal, "我喜欢少糖的咖啡")
    generator = FakeGenerator(
        '{"kind":"preference","content":"用户喜欢咖啡"}'
    )
    queue = JobQueue(rig.db)
    service = MemoryService(rig.db, access=rig.access, queue=queue)
    worker = MemoryWorker(
        service, queue, message_loader=lambda owner_id, run_id: load_run_messages(rig.db, owner_id, run_id),
        generator=generator,
    )
    job_id = _enqueue(rig, worker, principal, receipt.run_id)
    await worker.tick()
    assert service.list(principal) == []
    await worker.tick()
    conn = rig.db.connect()
    try:
        row = conn.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    assert row["state"] == "succeeded"


@pytest.mark.asyncio
async def test_duplicate_run_enqueues_and_extracts_once(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()
    receipt = await _submit(rig, principal, "我习惯晚上十点后不看消息")
    generator = FakeGenerator(json.dumps({
        "kind": "preference",
        "content": "用户习惯晚上十点后不看消息",
        "evidence": "我习惯晚上十点后不看消息",
    }, ensure_ascii=False))
    service = MemoryService(rig.db, access=rig.access, queue=JobQueue(rig.db))
    worker = MemoryWorker(
        service, JobQueue(rig.db), message_loader=lambda owner_id, run_id: load_run_messages(rig.db, owner_id, run_id),
        generator=generator,
    )
    first = _enqueue(rig, worker, principal, receipt.run_id)
    second = _enqueue(rig, worker, principal, receipt.run_id)
    assert first == second
    await worker.tick()
    assert await worker.tick() == 0
    assert len(service.list(principal)) == 1
    assert len(generator.calls) == 1


@pytest.mark.asyncio
async def test_no_generator_keeps_deterministic_prefix_fallback_only(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()
    natural = await _submit(rig, principal, "以后都别约周六上午")
    explicit = await _submit(rig, principal, "记住：牛奶没了")
    service = MemoryService(rig.db, access=rig.access, queue=JobQueue(rig.db))
    worker = MemoryWorker(
        service, JobQueue(rig.db), message_loader=lambda owner_id, run_id: load_run_messages(rig.db, owner_id, run_id),
    )
    assert _enqueue(rig, worker, principal, natural.run_id)
    assert _enqueue(rig, worker, principal, explicit.run_id)
    await worker.tick()
    records = service.list(principal)
    assert [r.content for r in records] == ["牛奶没了"]
    assert records[0].source_type == "user_confirmed"


def test_remember_explicit_overrides_model_supplied_source_type(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    principal = rig.seed_user()
    service = MemoryService(rig.db, access=rig.access)
    candidate = MemoryCandidate(
        kind="fact", content="用户住在杭州",
        source_refs=(SourceRef(kind="message", ref="run_x"),),
        source_type="model_inferred", confidence=0.1,
    )
    record = service.remember_explicit(principal, candidate)
    assert record.source_type == "user_confirmed"
    assert record.confidence == 1.0


class _Gen:
    """可编程 TextGenerator 替身。"""

    def __init__(self, result=None, raises=False):
        self._result, self._raises = result, raises

    async def generate(self, system, user, *, owner_id=0, max_chars=0):
        if self._raises:
            raise ConnectionError("模型不可用")
        return self._result


async def _capture_env(rig, generator, confirm_writer=None, *, client_msg="cap-e2e"):
    ready = rig if rig.assistant is not None else make_rig(
        rig.tmp_path, seed_access=True, clock=rig.clock)
    ready.db = ready.db
    memory = MemoryService(ready.db, access=ready.access, queue=JobQueue(ready.db))
    queue = JobQueue(ready.db)
    if ready.assistant is None:
        from backend.modules.assistant.api import AssistantService
        ready.assistant = AssistantService(
            ready.db, runtime=None, models=None, access=ready.access)
    user = ready.seed_user(role="user", grants=("chat.use", "memory.edit"))
    session_id = await ready.assistant.create_session(user, source="wechat")
    text = "记住：我喜欢少糖咖啡"
    receipt = await ready.assistant.submit(RunCommand(
        principal=user, session_id=session_id, source="wechat",
        client_message_id=client_msg, text=text,
    ))
    if confirm_writer is None:
        from backend.bootstrap import make_memory_confirm
        confirm_writer = make_memory_confirm(ready.db)
    worker = MemoryWorker(memory, queue,
                          message_loader=lambda o, r: load_run_messages(ready.db, o, r),
                          generator=generator, confirm_writer=confirm_writer)
    with ready.db.transaction() as conn:
        job_id = worker.enqueue_capture_tx(conn, {
            "id": receipt.run_id, "owner_id": user.user_id,
            "status": "completed", "source": "wechat",
        })
    assert job_id
    return ready, memory, queue, user, receipt.run_id, worker


@pytest.mark.asyncio
async def test_empty_generator_output_is_diagnosable(rig) -> None:
    """WP-D 复现:生成器返回空文本 → 状态 empty_output 可诊断,零记忆如实呈现。"""
    ready, memory, queue, user, run_id, worker = await _capture_env(rig, _Gen(result=""))
    await worker.tick()
    assert worker.extraction_status_counts().get("empty_output") == 1
    items = memory.list(user)
    assert len(items) == 0


@pytest.mark.asyncio
async def test_deterministic_capture_writes_confirmation(rig) -> None:
    """显式'记住'+无生成器 → 确定性提取写入记忆并注入会话内确认消息(真实 bootstrap 写入器)。"""
    ready, memory, queue, user, run_id, worker = await _capture_env(rig, None)
    await worker.tick()
    assert worker.extraction_status_counts().get("captured_deterministic") == 1
    items = memory.list(user)
    assert any("少糖咖啡" in i.content for i in items)
    conn = ready.db.connect()
    try:
        rows = conn.execute(
            "SELECT content, source FROM conversations WHERE run_id=? AND role='assistant'"
            " ORDER BY seq DESC", (run_id,),
        ).fetchall()
    finally:
        conn.close()
    assert rows and str(rows[0]["content"]).startswith("已记住")


@pytest.mark.asyncio
async def test_model_unavailable_and_invalid_output_states(rig) -> None:
    ready, memory, queue, user, run_id, worker = await _capture_env(rig, _Gen(raises=True))
    await worker.tick()
    assert worker.extraction_status_counts().get("model_unavailable") == 1

    ready2, memory2, queue2, user2, run_id2, worker2 = await _capture_env(
        rig, _Gen(result="42"), )
    await worker2.tick()
    assert worker2.extraction_status_counts().get("invalid_output") == 1
    items = memory2.list(user2)
    assert len(items) == 0


@pytest.mark.asyncio
async def test_valid_json_no_candidate_state(rig) -> None:
    ready, memory, queue, user, run_id, worker = await _capture_env(
        rig, _Gen(result=json.dumps({"skip": True})))
    await worker.tick()
    assert worker.extraction_status_counts().get("no_candidate") == 1
    assert memory.list(user) == []
