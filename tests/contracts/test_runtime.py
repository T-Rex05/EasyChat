"""Runtime Seam 契约测试：Protocol 符合性、事件桥接、缓存隔离、ContextVar传播、取消。"""
from __future__ import annotations

import asyncio
import contextvars
import inspect
import subprocess
import threading
from types import SimpleNamespace

import pytest

from backend.runtime.contracts import ExecutionRuntime, RuntimeRequest
from backend.runtime.hermes.adapter import HermesRuntimeAdapter
from backend.shared.context import ExecutionContext, Principal
from tests.support.rig import FakeRuntime


def _ctx(run_id="run_" + "a" * 32, session_id="sess_" + "b" * 32, user_id=7,
         source="chat", model_profile_id="mp1", policy_revision=1, perm_revision=3):
    return ExecutionContext(
        run_id=run_id, session_id=session_id,
        principal=Principal(user_id=user_id, role="user", permission_revision=perm_revision),
        source=source, channel_account_id=None,
        model_profile_id=model_profile_id, policy_revision=policy_revision,
    )


def _req(**kw):
    return RuntimeRequest(
        context=kw.get("ctx", _ctx()),
        text="你好",
        attachment_ids=(),
        system_context="",
        allowed_tools=kw.get("allowed_tools", frozenset({"web"})),
        skill_versions=kw.get("skill_versions", ()),
    )


# ---- Protocol 符合性 --------------------------------------------------------------


def test_fake_runtime_satisfies_protocol():
    """FakeRuntime 与 HermesRuntimeAdapter 均满足 ExecutionRuntime 结构契约。"""
    fake = FakeRuntime()
    for name in ("execute", "cancel", "aclose"):
        assert hasattr(fake, name)
        assert hasattr(HermesRuntimeAdapter, name)
    sig = inspect.signature(ExecutionRuntime.execute)
    assert "request" in sig.parameters


# ---- 事件桥接 ----------------------------------------------------------------------


class StubAgent:
    """无行为的agent替身；session_*计数器供usage桥测试。"""

    def __init__(self):
        for attr in ("session_input_tokens", "session_output_tokens", "session_total_tokens",
                     "session_cache_read_tokens", "session_cache_write_tokens",
                     "session_reasoning_tokens", "session_api_calls"):
            setattr(self, attr, 0)
        self.interrupt_calls: list[str] = []

    def interrupt(self, message: str):
        self.interrupt_calls.append(message)


def _adapter(**kw):
    return HermesRuntimeAdapter(
        hermes_home=kw.pop("hermes_home", __import__("pathlib").Path(".") / "unused"),
        agent_factory=lambda req, profile: StubAgent(),
        runner=kw.pop("runner", None),
        usage=kw.pop("usage", None),
        **kw,
    )


def test_execute_bridges_events_to_completed(tmp_path):
    async def scenario():
        def runner(agent, request, on_delta, on_reasoning, on_step):
            on_delta("你")
            on_delta("好")
            on_reasoning("思考片段")
            on_step(1, [{"name": "web_search"}])
            agent.session_total_tokens = 150
            agent.session_input_tokens = 100
            agent.session_output_tokens = 50
            agent.session_api_calls = 1
            return {"final_response": "你好！", "completed": True}

        adapter = _adapter(hermes_home=tmp_path, runner=runner)
        adapter._started = True
        events = []
        async for event in adapter.execute(_req()):
            events.append(event)
        kinds = [e.kind for e in events]
        assert kinds[0] == "token"
        assert kinds[-1] == "completed"
        token_texts = "".join(e.payload["text"] for e in events if e.kind == "token")
        assert token_texts == "你好"
        assert await adapter.aclose() is None

    asyncio.run(scenario())


def test_execute_failed_runner_yields_failed_event(tmp_path):
    async def scenario():
        def runner(agent, request, on_delta, on_reasoning, on_step):
            raise RuntimeError("模型连接失败")

        adapter = _adapter(hermes_home=tmp_path, runner=runner)
        adapter._started = True
        events = [e async for e in adapter.execute(_req())]
        assert events[-1].kind == "failed"
        assert "模型连接失败" in events[-1].payload["error"]

    asyncio.run(scenario())


def test_execute_after_close_rejected(tmp_path):
    async def scenario():
        adapter = _adapter(hermes_home=tmp_path, runner=lambda *a: {})
        await adapter.aclose()
        with pytest.raises(RuntimeError):
            async for _ in adapter.execute(_req()):
                pass

    asyncio.run(scenario())


# ---- 缓存隔离 ------------------------------------------------------------------------


def test_cache_key_isolates_owner_model_policy_skills(tmp_path):
    adapter = _adapter(hermes_home=tmp_path)
    base = adapter._cache_key(_req())
    same = adapter._cache_key(_req())
    assert base == same  # 相同维度复用

    different_owner = adapter._cache_key(_req(ctx=_ctx(user_id=8)))
    different_session = adapter._cache_key(_req(ctx=_ctx(session_id="sess_" + "c" * 32)))
    different_model = adapter._cache_key(_req(ctx=_ctx(model_profile_id="mp2")))
    different_policy = adapter._cache_key(_req(ctx=_ctx(policy_revision=2)))
    different_perms = adapter._cache_key(_req(ctx=_ctx(perm_revision=4)))
    different_tools = adapter._cache_key(_req(allowed_tools=frozenset({"terminal"})))
    different_skills = adapter._cache_key(_req(skill_versions=(("skill-a", "v2"),)))
    for other in (different_owner, different_session, different_model, different_policy,
                  different_perms, different_tools, different_skills):
        assert other != base


def test_lru_bounds_and_active_not_evicted(tmp_path):
    """缓存有界；正在执行的实例不被LRU回收。"""
    gate = threading.Event()

    def runner(agent, request, on_delta, on_reasoning, on_step):
        gate.wait(timeout=10)  # 模拟长执行
        return {"final_response": "x", "completed": True}

    async def scenario():
        adapter = _adapter(hermes_home=tmp_path, runner=runner, cache_size=2)
        adapter._started = True

        req1 = _req(ctx=_ctx(run_id="run_" + "1" * 32, session_id="sess_" + "1" * 32, user_id=1))
        task = asyncio.ensure_future(adapter.execute(req1).__anext__())
        await asyncio.sleep(0.05)
        handle1_key = next(iter(adapter._cache.keys()))
        assert adapter._cache[handle1_key].running is True

        # 再塞两个请求挤缓存：运行中的 handle1 不被逐出
        for uid in (2, 3):
            r = _req(ctx=_ctx(run_id="run_" + str(uid) * 32, session_id="sess_" + str(uid) * 32, user_id=uid))
            agen = adapter.execute(r)
            try:
                await asyncio.wait_for(agen.__anext__(), timeout=15)
            finally:
                await agen.aclose()
        assert handle1_key in adapter._cache
        gate.set()
        await task
        await adapter.aclose()

    asyncio.run(scenario())


# ---- ContextVar 传播 ----------------------------------------------------------------


def test_contextvar_propagates_to_worker_and_does_not_leak(tmp_path):
    var = contextvars.ContextVar("probe", default=None)

    async def scenario():
        seen = {}

        def runner(agent, request, on_delta, on_reasoning, on_step):
            seen["value"] = var.get()
            return {"final_response": "", "completed": True}

        adapter = _adapter(hermes_home=tmp_path, runner=runner)
        adapter._started = True
        token = var.set("hello-worker")
        try:
            async for _ in adapter.execute(_req()):
                pass
        finally:
            var.reset(token)
        assert seen["value"] == "hello-worker"  # 工作线程可见
        assert var.get() is None  # 调用方上下文未被污染（copy_context 语义）
        await adapter.aclose()

    asyncio.run(scenario())


# ---- 取消 ------------------------------------------------------------------------


def test_cancel_invokes_cooperative_interrupt(tmp_path):
    """取消走 agent.interrupt 协作机制（不用 asyncio cancel 强杀）。"""
    release = threading.Event()

    def runner(agent, request, on_delta, on_reasoning, on_step):
        release.wait(timeout=10)
        return {"final_response": "", "completed": True}

    async def scenario():
        adapter = _adapter(hermes_home=tmp_path, runner=runner)
        adapter._started = True
        run_id = "run_" + "d" * 32
        task = asyncio.ensure_future(adapter.execute(_req(ctx=_ctx(run_id=run_id))).__anext__())
        await asyncio.sleep(0.05)
        await adapter.cancel(run_id)
        handle = next(iter(adapter._by_run.values()))
        assert handle.agent.interrupt_calls == ["用户请求取消"]
        release.set()
        await task
        await adapter.aclose()

    asyncio.run(scenario())


def test_cancel_unknown_run_is_noop(tmp_path):
    async def scenario():
        adapter = _adapter(hermes_home=tmp_path)
        adapter._started = True
        await adapter.cancel("run_" + "0" * 32)  # 不抛错
        await adapter.aclose()

    asyncio.run(scenario())


# ---- usage 桥接 ------------------------------------------------------------------------


def test_usage_bridge_records_delta_once(tmp_path):
    from backend.modules.usage.api import UsageService
    from backend.platform.sqlite import Database
    from datetime import datetime, timezone

    db = Database(tmp_path / "app.db")
    db.migrate()
    clock_now = {"t": datetime(2026, 1, 5, 2, 0, tzinfo=timezone.utc)}
    usage = UsageService(db, clock=lambda: clock_now["t"])

    def runner(agent, request, on_delta, on_reasoning, on_step):
        agent.session_total_tokens = 150
        agent.session_input_tokens = 100
        agent.session_output_tokens = 50
        agent.session_api_calls = 2
        return {"final_response": "ok", "completed": True}

    adapter = _adapter(hermes_home=tmp_path, runner=runner, usage=usage)
    adapter._started = True

    async def scenario():
        events = [e async for e in adapter.execute(_req(ctx=_ctx(user_id=7)))]
        assert events[-1].kind == "completed"
        assert events[-1].payload["api_calls"] == 2

    asyncio.run(scenario())

    from backend.shared.context import Principal

    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    calls = usage.list_calls(admin, owner_id=7)
    assert len(calls) == 1
    row = calls[0]
    assert row["total_tokens"] == 150
    assert row["prompt_tokens"] == 100
    assert row["completion_tokens"] == 50
    db.close()


def test_easychat_prompt_isolation_and_coding_workspace(tmp_path, monkeypatch):
    from agent.coding_context import coding_system_prompt_parts
    from agent.conversation_loop import _stored_prompt_matches_runtime
    from agent.system_prompt import build_system_prompt
    from agent.runtime_cwd import resolve_context_cwd
    from backend.runtime.hermes.agent_factory import build_agent
    import run_agent
    import hermes_state

    server = tmp_path / "server"
    work = tmp_path / "task"
    for path in (server, work):
        path.mkdir()
        subprocess.run(["git", "init", "-q", "-b", f"{path.name}-branch", str(path)], check=True)
        (path / "AGENTS.md").write_text(f"private instructions of {path.name}", encoding="utf-8")
    monkeypatch.chdir(server)
    monkeypatch.setenv("TERMINAL_CWD", str(server))
    monkeypatch.setenv("HERMES_HOME", str(server / "hermes"))
    monkeypatch.setattr(hermes_state, "SessionDB", lambda: None)
    monkeypatch.setattr(run_agent, "AIAgent", lambda **kw: SimpleNamespace(
        **kw, valid_tool_names={"lookup"}, _tool_use_enforcement=False,
        model="local-test", provider="test", load_soul_identity=False,
        _memory_store=None, _memory_manager=None, pass_session_id=False,
        _emit_status=lambda message: None,
    ))
    adapter = HermesRuntimeAdapter(hermes_home=server / "hermes")
    chat_req = _req()
    code_req = _req(ctx=_ctx(source="superagent"))
    adapter.prepare_session_workspace(code_req.context.session_id, str(work))
    try:
        observed = []

        def probe(agent, text, **kwargs):
            observed.append((agent.platform, agent.skip_context_files, resolve_context_cwd(), kwargs,
                             build_system_prompt(agent)))
            return {}

        run = adapter._default_runner(probe)
        for req in (chat_req, code_req, chat_req):
            agent = build_agent(req, {}, hermes_home=adapter.hermes_home)
            run(agent, req, None, None, None)
        ordinary, coding, again = observed
        assert ordinary == again
        assert "server-branch" not in ordinary[4]
        assert "task-branch" in coding[4]
        assert str(server) not in ordinary[4]
        assert "private instructions of server" not in ordinary[4]
        assert "private instructions of task" in coding[4]
        assert "private instructions of server" not in coding[4]
        assert ordinary[0:2] == ("easychat", True)
        assert coding[:3] == ("easychat-coding", False, work)
        assert coding[3]["task_id"] == code_req.context.session_id
        assert adapter._cache_key(chat_req) != adapter._cache_key(code_req)
        for mode in ("auto", "on"):
            assert not any(coding_system_prompt_parts(
                platform=ordinary[0], cwd=server, config={"agent": {"coding_context": mode}},
            ))
        assert any(coding_system_prompt_parts(platform=coding[0], cwd=work))
        assert not _stored_prompt_matches_runtime(
            SimpleNamespace(platform=ordinary[0]), "legacy project instructions without platform marker",
        )
    finally:
        adapter.release_session_workspace(code_req.context.session_id)


def test_adopting_legacy_compression_child_preserves_history_and_rejects_host_prompt():
    from agent.conversation_compression import _adopt_live_compression_child

    history = [{"role": "user", "content": "我叫小明"}, {"role": "assistant", "content": "你好，小明"}]

    class ChildSessions:
        def find_live_compression_child(self, parent_id):
            return {"id": "child", "system_prompt": "Legacy server checkout and branch"}

        def get_messages_as_conversation(self, session_id):
            return list(history)

    agent = SimpleNamespace(
        platform="easychat", context_compressor=None, _memory_manager=None,
        _cached_system_prompt="old parent", _cached_system_prompt_static="old prefix",
    )
    recovered = contextvars.copy_context().run(
        _adopt_live_compression_child, agent, ChildSessions(), "parent",
    )
    assert recovered == history
    assert agent.session_id == "child"
    assert agent._cached_system_prompt is None and agent._cached_system_prompt_static is None
