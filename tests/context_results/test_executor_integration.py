"""Exercise the real Hermes dispatch paths without providers or production config."""

import copy
import contextvars
import hashlib
import importlib
import json
import sys
import threading
import time
import types
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.context.tool_results import runtime as host_runtime


ACTIVE_CALL = contextvars.ContextVar("test_result_call", default=None)


def content_hash(content):
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Runtime:
    def __init__(self):
        self.prepared = []
        self.sealed = []
        self.dispatched = []

    @contextmanager
    def tool_context(self, name, call_id, max_chars):
        token = ACTIVE_CALL.set((name, call_id, max_chars))
        try:
            yield
        finally:
            ACTIVE_CALL.reset(token)

    def prepare(self, name, call_id, raw, max_chars):
        self.prepared.append((name, call_id, copy.deepcopy(raw), max_chars))
        return SimpleNamespace(content=copy.deepcopy(raw), managed=True, max_chars=max_chars, call_id=call_id)

    def seal(self, prepared, canonical):
        self.sealed.append(copy.deepcopy(canonical))
        return {"managed": True, "view_id": prepared.call_id, "canonical_hash": content_hash(canonical)}

    def budget_pressure(self, prepared, max_chars):
        return SimpleNamespace(content="budget_pressure", managed=True, max_chars=max_chars, call_id=prepared.call_id)


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "backend" / "hermes"))

    def module(name, **members):
        mod = types.ModuleType(name)
        mod.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    module("tools.terminal_tool", get_active_env=lambda _: None)
    module("agent.relay_tools", execute=lambda name, args, callback, **kw: (callback(args), args))
    module("hermes_cli.plugins", resolve_pre_tool_block=lambda *a, **kw: None)
    module("hermes_cli.middleware",
           apply_tool_request_middleware=lambda name, args, **kw: SimpleNamespace(payload=args, trace=[]),
           run_tool_execution_middleware=lambda name, args, callback, **kw: callback(args))
    module("agent.agent_runtime_helpers", agent_runtime_owns_post_tool_hook=lambda agent, name: False)
    module("tools.environments.base", set_activity_callback=lambda _: None)
    module("tools.tool_search", TOOL_CALL_NAME="tool_call")
    runtime = Runtime()
    module("backend.context.tool_results.runtime", current_runtime=lambda agent=None: runtime,
           managed_results_active=lambda: ACTIVE_CALL.get() is not None, active_tool=host_runtime.active_tool)
    executor = importlib.import_module("agent.tool_executor")
    from tools.budget_config import BudgetConfig
    monkeypatch.setattr(executor, "_budget_for_agent", lambda _: BudgetConfig(default_result_size=2400, turn_budget=6000))
    monkeypatch.setattr(executor, "get_active_env", lambda _: None)
    legacy = []
    monkeypatch.setattr(executor, "maybe_persist_tool_result", lambda **kw: legacy.append("L2") or kw["content"])
    monkeypatch.setattr(executor, "enforce_turn_budget", lambda *a, **kw: legacy.append("L3"))
    rows, events, invocations = [], [], []

    def dispatch(name, args, *a, **kw):
        invocations.append((name, ACTIVE_CALL.get()))
        if args.get("delay"):
            time.sleep(args["delay"])
        return args.get("result", "original " + name)

    monkeypatch.setattr(executor, "_ra", lambda: SimpleNamespace(handle_function_call=dispatch, _set_interrupt=lambda *a: None))
    module("tools.todo_tool", todo_tool=lambda **kw: dispatch("todo", {}))
    agent = SimpleNamespace(
        quiet_mode=True, verbose_logging=False, tool_progress_mode="off", log_prefix="", tool_delay=0,
        _interrupt_requested=False, _incremental_persistence_failed=False, _tool_worker_threads=set(),
        _tool_worker_threads_lock=threading.Lock(), _context_engine_tool_names=set(), _memory_manager=None,
        _todo_store=None, session_id="physical-session", valid_tool_names=set(), _pending_steer=None,
        _checkpoint_mgr=SimpleNamespace(enabled=False),
        _tool_guardrails=SimpleNamespace(before_call=lambda *a: SimpleNamespace(allows_execution=True)),
        _subdirectory_hints=SimpleNamespace(check_tool_call=lambda *a: "\nHINT"),
        _should_emit_quiet_tool_messages=lambda: False, _should_start_quiet_spinner=lambda: False,
        _touch_activity=lambda *a: None, _vprint=lambda *a, **kw: None,
        _append_guardrail_observation=lambda name, args, result, **kw: result,
        _record_file_mutation_result=lambda *a: None,
        _invoke_tool=dispatch,
        _tool_result_content_for_active_model=lambda name, result: result["content"] if isinstance(result, dict) else result,
        _flush_messages_to_session_db=lambda messages: rows.append(copy.deepcopy(messages)) or True,
        tool_start_callback=None, tool_complete_callback=None,
        tool_progress_callback=lambda *a, **kw: events.append((a, kw)),
    )
    def drain():
        pending, agent._pending_steer = agent._pending_steer, None
        return pending
    agent._drain_pending_steer = drain
    def legacy_steer(messages, count):
        steer = drain()
        if steer:
            messages[-1]["content"] += "\nUSER STEER: " + steer
    agent._apply_pending_steer_to_tool_results = legacy_steer
    return SimpleNamespace(executor=executor, agent=agent, runtime=runtime, rows=rows, events=events,
                           legacy=legacy, invocations=invocations)


def call(name, call_id, **args):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


@pytest.mark.parametrize("route", ["sequential", "concurrent", "segmented"])
def test_real_dispatch_routes_prepare_then_seal_before_persistence(harness, route):
    h = harness
    calls = [call("web_search", "a", result="raw " * 90, delay=0.02), call("query", "b")]
    if route == "segmented":
        calls += [call("todo", "c"), call("query", "d")]
    messages = []
    kwargs = {"segments": [("parallel", calls[:2]), ("sequential", calls[2:])]} if route == "segmented" else {}
    getattr(h.executor, "execute_tool_calls_" + route)(h.agent, SimpleNamespace(tool_calls=calls), messages, "task", **kwargs)
    assert len(h.runtime.prepared) == len(calls)
    assert h.legacy == []
    assert [row["tool_call_id"] for row in messages] == [tc.id for tc in calls]
    for row, sealed in zip(messages, h.runtime.sealed):
        assert row["content"] == sealed
        assert row["display_metadata"]["context_result"]["canonical_hash"] == content_hash(row["content"])
    assert "<untrusted_tool_result" in messages[0]["content"]
    assert "HINT" in messages[0]["content"]
    assert all("display_metadata" in snapshot[-1] for snapshot in h.rows)
    assert all(ctx is not None for _, ctx in h.invocations)
    prepared_tickets = {call_id: budget for _, call_id, _, budget in h.runtime.prepared}
    assert sum(prepared_tickets.values()) <= 6000
    assert all(ctx[2] >= prepared_tickets[ctx[1]] for _, ctx in h.invocations)
    for event, details in h.events:
        if event[0] == "tool.completed":
            assert details["context_result"]["managed"] is True


def test_inline_todo_uses_same_boundary(harness):
    h = harness
    messages = []
    h.executor.execute_tool_calls_sequential(h.agent, SimpleNamespace(tool_calls=[call("todo", "todo-1")]), messages, "task")
    assert h.runtime.prepared[0][0:3] == ("todo", "todo-1", "original todo")
    assert h.invocations[0][1][1] == "todo-1"
    assert len(h.runtime.sealed) == 1


def test_managed_steer_does_not_mutate_sealed_view(harness):
    h = harness
    h.agent._pending_steer = "new user direction"
    messages = []
    h.executor.execute_tool_calls_sequential(h.agent, SimpleNamespace(tool_calls=[call("query", "a"), call("query", "b")]), messages, "task")
    assert messages[0]["content"] == h.runtime.sealed[0]
    assert messages[1]["content"] == h.runtime.sealed[1]
    assert messages[2] == {"role": "user", "content": "new user direction"}


def test_multimodal_blocks_survive_risk_wrapping(harness):
    h = harness
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
    raw = {"_multimodal": True, "content": [{"type": "text", "text": "raw " * 90}, image], "text_summary": "raw"}
    messages = []
    h.executor.execute_tool_calls_sequential(h.agent, SimpleNamespace(tool_calls=[call("web_search", "a", result=raw)]), messages, "task")
    assert messages[0]["content"][1] == image
    assert h.runtime.prepared[0][2] == raw
    assert h.runtime.sealed[0] == messages[0]["content"]


def test_absent_host_retains_legacy_budget_paths(harness, monkeypatch):
    h = harness
    monkeypatch.setattr(sys.modules["backend.context.tool_results.runtime"], "current_runtime", lambda agent=None: None)
    messages = []
    h.executor.execute_tool_calls_sequential(h.agent, SimpleNamespace(tool_calls=[call("query", "a")]), messages, "task")
    assert h.legacy == ["L2", "L3"]
    assert "display_metadata" not in messages[0]


def test_actual_model_dispatch_skips_lossy_hook_but_keeps_safety_hooks(harness, monkeypatch):
    hooks = []
    lifecycle = types.ModuleType("hermes_cli.lifecycle")
    lifecycle.has_hook = lambda _: True
    def invoke_hook(name, **kw):
        hooks.append(name)
        return ["LOSSY RESULT"] if name == "transform_tool_result" else []
    lifecycle.invoke_hook = invoke_hook
    monkeypatch.setitem(sys.modules, "hermes_cli.lifecycle", lifecycle)
    monkeypatch.setattr(sys.modules["tools.tool_search"], "is_bridge_tool", lambda _: False, raising=False)
    # Prevent optional dependency discovery; this test exercises the actual dispatcher.
    registry_module = importlib.import_module("tools.registry")
    monkeypatch.setattr(registry_module, "discover_builtin_tools", lambda *a, **kw: None)
    model_tools = importlib.import_module("model_tools")
    monkeypatch.setattr(model_tools, "coerce_tool_args", lambda name, args: args)
    monkeypatch.setattr(model_tools.registry, "dispatch", lambda *a, **kw: "ORIGINAL RESULT")
    file_tools = types.ModuleType("tools.file_tools")
    file_tools.notify_other_tool_call = lambda *a: None
    monkeypatch.setitem(sys.modules, "tools.file_tools", file_tools)
    approval = types.ModuleType("acp_adapter.edit_approval")
    approval.maybe_require_edit_approval = lambda *a: None
    monkeypatch.setitem(sys.modules, "acp_adapter.edit_approval", approval)
    def dispatch():
        return model_tools.handle_function_call("query", {}, skip_tool_request_middleware=True,
                                                skip_tool_execution_middleware=True)
    assert dispatch() == "LOSSY RESULT"
    assert "transform_tool_result" in hooks
    hooks.clear()
    with harness.runtime.tool_context("query", "a", 2000):
        assert dispatch() == "ORIGINAL RESULT"
    assert "transform_tool_result" not in hooks
    assert "post_tool_call" in hooks


@pytest.mark.parametrize("route", ["sequential", "concurrent"])
def test_malformed_calls_are_sealed_without_execution(harness, route):
    h = harness
    malformed = call("query", "bad")
    malformed.function.arguments = "[1, 2]"
    messages = []
    getattr(h.executor, "execute_tool_calls_" + route)(h.agent, SimpleNamespace(tool_calls=[malformed]), messages, "task")
    assert h.invocations == []
    assert messages[0]["display_metadata"]["context_result"]["canonical_hash"] == content_hash(messages[0]["content"])


def test_canonical_overflow_is_explicit_without_mutating_sealed_content(harness):
    h = harness
    h.agent._tool_result_content_for_active_model = lambda *a: "adapter-expanded " * 1000
    messages = []
    h.executor.execute_tool_calls_sequential(h.agent, SimpleNamespace(tool_calls=[call("query", "a")]), messages, "task")
    assert len(messages[0]["content"]) <= 2400
    assert "budget_pressure" in messages[0]["content"]
    assert messages[0]["content"] == h.runtime.sealed[0]


@pytest.mark.parametrize("phase", ["prepare", "seal"])
def test_callback_failure_preserves_result_without_reexecution(harness, phase, monkeypatch):
    h = harness
    def fail(*a):
        raise OSError("archive offline")
    monkeypatch.setattr(h.runtime, phase, fail)
    messages = []
    h.executor.execute_tool_calls_sequential(h.agent, SimpleNamespace(tool_calls=[call("query", "a")]), messages, "task")
    assert len(h.invocations) == 1
    assert messages[0]["content"] == "original query\nHINT"
    assert "display_metadata" not in messages[0]


@pytest.mark.parametrize("route", ["sequential", "concurrent"])
def test_completion_callbacks_receive_canonical_content_and_optional_metadata(harness, route):
    h = harness
    completions = []
    h.agent.tool_complete_callback = lambda call_id, name, args, result, **kw: completions.append((result, kw))
    messages = []
    getattr(h.executor, "execute_tool_calls_" + route)(h.agent, SimpleNamespace(tool_calls=[call("query", "a")]), messages, "task")
    assert completions[0][0] == messages[0]["content"]
    assert completions[0][1]["context_result"] == messages[0]["display_metadata"]["context_result"]
    h.agent.tool_complete_callback = lambda call_id, name, args, result: completions.append((result, {}))
    getattr(h.executor, "execute_tool_calls_" + route)(h.agent, SimpleNamespace(tool_calls=[call("query", "b")]), messages, "task")
    assert len(completions) == 2


@pytest.mark.parametrize("route", ["sequential", "concurrent"])
def test_native_guardrails_still_block_dispatch(harness, route):
    h = harness
    h.agent._tool_guardrails.before_call = lambda *a: SimpleNamespace(allows_execution=False, message="denied")
    h.agent._guardrail_block_result = lambda decision: json.dumps({"error": decision.message})
    messages = []
    getattr(h.executor, "execute_tool_calls_" + route)(h.agent, SimpleNamespace(tool_calls=[call("query", "a")]), messages, "task")
    assert h.invocations == []
    assert "denied" in messages[0]["content"]
    assert h.runtime.prepared[0][2] == '{"error": "denied"}'


@pytest.mark.parametrize("route", ["sequential", "concurrent", "segmented"])
def test_real_host_store_roundtrip_and_canonical_hash(harness, monkeypatch, tmp_path, route):
    h = harness
    monkeypatch.setattr(sys.modules["backend.context.tool_results.runtime"], "current_runtime", host_runtime.current_runtime)
    raw = json.dumps({"payload": "x" * 6000, "job_id": "J731", "file_path": "C:/exact/report.json"})
    calls = [call("web_search", "a", result=raw), call("query", "b", result=raw)]
    messages = []
    kwargs = {"segments": [("parallel", calls[:1]), ("sequential", calls[1:])]} if route == "segmented" else {}
    with host_runtime.bind_runtime(h.agent, user_id="u", thread_id="t", root=tmp_path, enabled=True):
        host = host_runtime.current_runtime(h.agent)
        getattr(h.executor, "execute_tool_calls_" + route)(h.agent, SimpleNamespace(tool_calls=calls), messages, "task", **kwargs)
        for message in messages:
            metadata = message["display_metadata"]["context_result"]
            assert "J731" in message["content"]
            assert "C:/exact/report.json" in message["content"]
            assert len(message["content"]) <= 2400
            assert metadata["canonical_hash"] == hashlib.sha256(message["content"].encode()).hexdigest()
            recovered = host.manager.store.read(host.scope, metadata["artifact_id"], max_chars=16000)
            assert recovered["status"] == "ok"
            assert recovered["content"] == raw


def test_recovery_page_uses_executor_ticket_before_tool_execution(harness, monkeypatch, tmp_path):
    from backend.context.tool_results import tools as recovery_tools
    h = harness
    monkeypatch.setattr(sys.modules["backend.context.tool_results.runtime"], "current_runtime", host_runtime.current_runtime)
    monkeypatch.setattr(recovery_tools, "active_tool", host_runtime.active_tool)
    budgets = []
    def dispatch(name, args, *a, **kw):
        budgets.append(host_runtime.active_tool().max_chars)
        return recovery_tools.context_read.invoke(args)
    monkeypatch.setattr(h.executor, "_ra", lambda: SimpleNamespace(handle_function_call=dispatch))
    messages = []
    with host_runtime.bind_runtime(h.agent, user_id="u", thread_id="t", root=tmp_path, enabled=True):
        host = host_runtime.current_runtime(h.agent)
        saved = host.manager.store.put(host.scope, "line\n" * 2000)
        calls = [call("context_read", str(i), artifact_id=saved["artifact_id"], max_chars=16000) for i in range(5)]
        h.executor.execute_tool_calls_sequential(h.agent, SimpleNamespace(tool_calls=calls), messages, "task")
    assert budgets == [688] * 5  # 6000 / 5, minus the native wrapper reserve.
    assert sum(len(message["content"]) for message in messages) <= 6000
    for message in messages:
        assert message["display_metadata"]["context_result"]["action"] == "recovery"
        assert message["tool_call_id"] in {str(i) for i in range(5)}


def test_pre_api_steer_waits_for_all_replies_then_preserves_sealed_view(harness):
    from agent.result_finalizer import drain_pre_api_steer
    h = harness
    h.agent._pending_steer = "arrived during the API call"
    original = {"role": "tool", "tool_call_id": "a", "content": "sealed result",
                "display_metadata": {"context_result": {"managed": True, "canonical_hash": content_hash("sealed result")}}}
    messages = [{"role": "assistant", "tool_calls": [{"id": "a"}, {"id": "b"}]} , copy.deepcopy(original)]
    assert drain_pre_api_steer(h.agent, messages) is True
    assert h.agent._pending_steer
    assert len(messages) == 2
    messages.append({**copy.deepcopy(original), "tool_call_id": "b"})
    assert drain_pre_api_steer(h.agent, messages) is True
    assert messages[1] == original
    assert messages[-1] == {"role": "user", "content": "arrived during the API call"}
    assert h.rows[-1] == messages
    assert drain_pre_api_steer(h.agent, messages) is True
    assert len(messages) == 4


def test_pre_api_steer_reports_flush_failure_before_request(harness):
    from agent.result_finalizer import drain_pre_api_steer
    h = harness
    h.agent._pending_steer = "user direction"
    h.agent._flush_messages_to_session_db = lambda messages: False
    messages = [{"role": "tool", "tool_call_id": "a", "content": "sealed",
                 "display_metadata": {"context_result": {"managed": True}}}]
    assert drain_pre_api_steer(h.agent, messages) is False
    assert h.agent._incremental_persistence_failed is True
    assert messages[0]["content"] == "sealed"


def test_large_native_wrapper_cannot_overflow_small_canonical_ticket(harness, monkeypatch):
    h = harness
    from tools.budget_config import BudgetConfig
    monkeypatch.setattr(h.executor, "_budget_for_agent", lambda _: BudgetConfig(default_result_size=620, turn_budget=620))
    def pressure(prepared, max_chars):
        receipt = json.dumps({"status": "budget_pressure", "artifact_id": "artifact"})
        content = receipt if len(receipt) <= max_chars else "budget_pressure"[:max_chars]
        return SimpleNamespace(content=content, managed=True, call_id=prepared.call_id, max_chars=max_chars)
    monkeypatch.setattr(h.runtime, "budget_pressure", pressure)
    messages = []
    h.executor.execute_tool_calls_sequential(
        h.agent, SimpleNamespace(tool_calls=[call("mcp_" + "x" * 500, "a", result="raw " * 300)]), messages, "task")
    assert len(messages[0]["content"]) <= 620
    assert "budget_pressure" in messages[0]["content"]
    assert h.runtime.sealed[0] == messages[0]["content"]


@pytest.mark.parametrize("route", ["sequential", "concurrent", "segmented"])
def test_fallback_rows_only_receive_remaining_aggregate_budget(harness, monkeypatch, route):
    h = harness
    prepare = h.runtime.prepare
    def mixed_prepare(name, call_id, raw, max_chars):
        prepared = prepare(name, call_id, raw, max_chars)
        prepared.managed = call_id == "a"
        return prepared
    monkeypatch.setattr(h.runtime, "prepare", mixed_prepare)
    budgets = []
    monkeypatch.setattr(h.executor, "enforce_turn_budget",
                        lambda rows, **kw: budgets.append((copy.deepcopy(rows), kw["config"].turn_budget)))
    calls = [call("query", "a"), call("query", "b")]
    messages = []
    kwargs = {"segments": [("parallel", calls[:1]), ("sequential", calls[1:])]} if route == "segmented" else {}
    getattr(h.executor, "execute_tool_calls_" + route)(h.agent, SimpleNamespace(tool_calls=calls), messages, "task", **kwargs)
    assert len(budgets) == 1
    assert budgets[0][0] == [messages[1]]
    assert budgets[0][1] == 6000 - len(messages[0]["content"])
    assert messages[0]["content"] == h.runtime.sealed[0]


def test_unmanaged_multimodal_blocks_are_not_sent_to_text_budget_rewriter(harness, monkeypatch):
    h = harness
    raw = {"_multimodal": True, "content": [{"type": "text", "text": "picture"},
           {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}], "text_summary": "picture"}
    prepare = h.runtime.prepare
    def multimodal_prepare(name, call_id, raw, max_chars):
        prepared = prepare(name, call_id, raw, max_chars)
        prepared.managed = isinstance(raw, str)
        return prepared
    monkeypatch.setattr(h.runtime, "prepare", multimodal_prepare)
    messages = []
    h.executor.execute_tool_calls_sequential(h.agent, SimpleNamespace(tool_calls=[call("query", "a", result=raw)]), messages, "task")
    assert h.legacy == []
    assert messages[0]["content"][1] == raw["content"][1]
