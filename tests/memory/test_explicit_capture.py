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
        self.calls = 0

    async def generate(self, system, user, *, owner_id=0, max_chars=0):
        self.calls += 1
        if self._raises:
            raise ConnectionError("模型不可用")
        return self._result


async def _capture_env(rig, generator, confirm_writer=None, *, client_msg="cap-e2e",
                       text="记住：我喜欢少糖咖啡", status="completed"):
    ready = rig if rig.assistant is not None else make_rig(
        rig.tmp_path, seed_access=True, clock=rig.clock)
    ready.db = ready.db
    queue = JobQueue(ready.db, clock=ready.clock)
    memory = MemoryService(ready.db, access=ready.access, queue=queue)
    if ready.assistant is None:
        from backend.modules.assistant.api import AssistantService
        ready.assistant = AssistantService(
            ready.db, runtime=None, models=None, access=ready.access)
    user = ready.seed_user(role="user", grants=("chat.use", "memory.edit"))
    session_id = await ready.assistant.create_session(user, source="wechat")
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
            "status": status, "source": "wechat",
        })
    assert job_id
    return ready, memory, queue, user, receipt.run_id, worker


def _job_state(rig, job_id: str) -> str:
    conn = rig.db.connect()
    try:
        row = conn.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
        return str(row["state"]) if row else "absent"
    finally:
        conn.close()


def _jobs(rig, kind: str, *, dedup_key: str | None = None):
    conn = rig.db.connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, state, dedup_key FROM jobs WHERE kind=? ORDER BY id", (kind,)
        ).fetchall()]
    finally:
        conn.close()
    if dedup_key is not None:
        rows = [r for r in rows if r["dedup_key"] == dedup_key]
    return rows


@pytest.mark.asyncio
async def test_empty_generator_output_is_diagnosable(rig) -> None:
    """自然表达+空生成器：状态 empty_output、零记忆如实呈现，且可恢复(有界重试)。"""
    ready, memory, queue, user, run_id, worker = await _capture_env(
        rig, _Gen(result=""), text="我喜欢少糖咖啡", client_msg="cap-empty")
    await worker.tick()
    assert worker.extraction_status_counts().get("empty_output") == 1
    assert len(memory.list(user)) == 0
    extract = _jobs(ready, "memory.extract")
    assert extract and extract[0]["state"] == "retry_wait", "模型不可用不应记为成功"


@pytest.mark.asyncio
async def test_explicit_remember_never_depends_on_generator(rig) -> None:
    """缺陷①核心：生产装配存在生成器但模型异常/空输出时，
    明确"记住…"仍必须确定性写入并确认，不允许零记忆+job成功。"""
    for index, gen in enumerate((_Gen(raises=True), _Gen(result=""))):
        ready, memory, queue, user, run_id, worker = await _capture_env(
            rig, gen, client_msg=f"cap-gen-{index}")
        await worker.tick()
        assert gen.calls == 0, "显式请求不应调用辅助模型"
        assert worker.extraction_status_counts().get("captured_deterministic") == 1
        items = memory.list(user)
        assert any("少糖咖啡" in i.content for i in items)
        current = _jobs(ready, "memory.extract", dedup_key=f"memory:{run_id}")
        assert current and current[0]["state"] == "succeeded"


@pytest.mark.asyncio
async def test_deterministic_capture_writes_confirmation(rig) -> None:
    """显式'记住'+无生成器 → 写入记忆并经持久 confirm job 注入会话内确认。"""
    ready, memory, queue, user, run_id, worker = await _capture_env(
        rig, None, client_msg="cap-confirm")
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
async def test_explicit_remember_enqueued_on_failed_and_interrupted_run(rig) -> None:
    """缺陷①：主回答失败/中断不阻断显式记忆入队；cancelled 尊重用户意图不入队。"""
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    ready.attach_assistant()
    principal = ready.seed_user(grants=("chat.use", "memory.edit"))
    session_id = await ready.assistant.create_session(principal, source="wechat")
    receipt = await ready.assistant.submit(RunCommand(
        principal=principal, session_id=session_id, source="wechat",
        client_message_id="cap-failed", text="记住：牛奶没了",
    ))
    service = MemoryService(ready.db, access=ready.access, queue=JobQueue(ready.db))
    worker = MemoryWorker(
        service, JobQueue(ready.db),
        message_loader=lambda o, r: load_run_messages(ready.db, o, r),
        generator=_Gen(raises=True),
    )
    for status in ("failed", "interrupted"):
        with ready.db.transaction() as conn:
            assert worker.enqueue_capture_tx(conn, {
                "id": receipt.run_id, "owner_id": principal.user_id,
                "status": status, "source": "wechat",
            }), f"{status} run 显式记忆应入队"
    with ready.db.transaction() as conn:
        assert worker.enqueue_capture_tx(conn, {
            "id": receipt.run_id, "owner_id": principal.user_id,
            "status": "cancelled", "source": "wechat",
        }) is None, "取消的 run 不复活记忆"
    await worker.tick()
    assert any(r.content == "牛奶没了" for r in service.list(principal))


@pytest.mark.asyncio
async def test_model_unavailable_and_invalid_output_states(rig) -> None:
    """自然表达在模型故障/非法输出下的状态区分（显式请求已不依赖模型）。"""
    ready, memory, queue, user, run_id, worker = await _capture_env(
        rig, _Gen(raises=True), text="我喜欢少糖咖啡", client_msg="cap-mu")
    await worker.tick()
    assert worker.extraction_status_counts().get("model_unavailable") == 1

    ready2, memory2, queue2, user2, run_id2, worker2 = await _capture_env(
        rig, _Gen(result="42"), text="我讨厌临时改计划", client_msg="cap-io")
    await worker2.tick()
    assert worker2.extraction_status_counts().get("invalid_output") == 1
    assert memory2.list(user2) == []
    # 非法输出是确定性结果：不重试，如实 succeeded 并保留状态计数
    invalid = _jobs(ready2, "memory.extract", dedup_key=f"memory:{run_id2}")
    assert invalid and invalid[0]["state"] == "succeeded"


@pytest.mark.asyncio
async def test_valid_json_no_candidate_state(rig) -> None:
    ready, memory, queue, user, run_id, worker = await _capture_env(
        rig, _Gen(result=json.dumps({"skip": True})),
        text="我习惯晚上十点后不看消息", client_msg="cap-nc")
    await worker.tick()
    assert worker.extraction_status_counts().get("no_candidate") == 1
    assert memory.list(user) == []


@pytest.mark.asyncio
async def test_confirm_intent_is_durable_and_recovers(rig) -> None:
    """缺陷④：确认不随 extract job 直接发送；持久 memory.confirm 意图，
    渠道瞬时故障只让确认有界重试，记忆写入幂等不重复。"""
    attempts: list[str] = []
    state = {"fail": True}

    def flaky_writer(owner_id: int, run_id: str, text: str) -> None:
        attempts.append(text)
        if state["fail"]:
            raise ConnectionError("渠道目标解析暂时失败")

    ready, memory, queue, user, run_id, worker = await _capture_env(
        rig, None, confirm_writer=flaky_writer, client_msg="cap-durable")
    await worker.tick()   # 写入记忆 + confirm 入队 + 消费(confirm 抛错)
    assert len(memory.list(user)) == 1, "记忆已持久"
    confirms = _jobs(ready, "memory.confirm")
    assert len(confirms) == 1
    assert confirms[0]["state"] == "retry_wait", "确认失败必须可恢复而非丢失"
    assert confirms[0]["dedup_key"] == f"memory-confirm:{run_id}"

    ready.clock.advance(61.0)  # 有界重试退避到期
    state["fail"] = False
    await worker.tick()
    assert _jobs(ready, "memory.confirm")[0]["state"] == "succeeded"
    assert len(attempts) == 2  # 恰好一次失败 + 一次成功
    assert len(memory.list(user)) == 1, "重试不得重复写记忆"


@pytest.mark.asyncio
async def test_confirm_intent_survives_extract_retry(rig) -> None:
    """extract 租约恢复重放时：记忆幂等 + confirm 意图 dedup 复用，不产生第二条。"""
    ready, memory, queue, user, run_id, worker = await _capture_env(
        rig, None, confirm_writer=lambda *a: None, client_msg="cap-idem")
    await worker.tick()
    # 模拟租约恢复：extract job 退回重放（attempts 已计，dedup 复用同一 confirm）
    conn = ready.db.connect()
    try:
        conn.execute("UPDATE jobs SET state='pending', lease_until=NULL WHERE kind='memory.extract'")
        conn.commit()
    finally:
        conn.close()
    await worker.tick()
    assert len(memory.list(user)) == 1
    assert len(_jobs(ready, "memory.confirm")) == 1, "确认意图必须稳定操作身份去重"


@pytest.mark.asyncio
async def test_session_confirmation_idempotent_within_run(rig) -> None:
    """缺陷⑤：同一 run 重复执行确认(崩溃恢复/重复消费)只落一条会话消息。"""
    from backend.bootstrap import make_memory_confirm
    ready, memory, queue, user, run_id, worker = await _capture_env(
        rig, None, confirm_writer=lambda *a: None, client_msg="cap-twice")
    confirm = make_memory_confirm(ready.db)
    confirm(user.user_id, run_id, "已记住：少糖咖啡")
    confirm(user.user_id, run_id, "已记住：少糖咖啡")
    conn = ready.db.connect()
    try:
        rows = conn.execute(
            "SELECT id FROM conversations WHERE run_id=? AND role='assistant'"
            " AND source='system' AND content=?",
            (run_id, "已记住：少糖咖啡"),
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1, f"稳定操作身份(run+content)必须幂等，实际 {len(rows)} 条"
