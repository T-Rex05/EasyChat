import importlib
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("backend.observer.trace_observer", reason="legacy trace observer removed")
pytest.importorskip("backend.service.trace", reason="legacy trace service removed")


def usage(raw):
    return importlib.import_module("backend.utils.llm_usage").trace_usage(raw)


def test_normalized_zero_input_is_not_replaced_by_prompt_total():
    result = usage({"input_tokens": 0, "prompt_tokens": 100, "output_tokens": 5,
                    "cache_read_tokens": 100, "cache_write_tokens": 0, "total_tokens": 105})
    assert result["input_tokens"] == 0
    assert result["total_tokens"] == 105


def test_raw_chat_usage_subtracts_cache_once():
    result = usage(SimpleNamespace(prompt_tokens=100, completion_tokens=8,
                                  prompt_tokens_details=SimpleNamespace(cached_tokens=75),
                                  completion_tokens_details=SimpleNamespace(reasoning_tokens=3)))
    assert result["input_tokens"] == 25
    assert result["cache_read_tokens"] == 75
    assert result["reasoning_tokens"] == 3
    assert result["total_tokens"] == 108


def test_anthropic_buckets_are_additive():
    result = usage({"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 90,
                    "cache_creation_input_tokens": 20})
    assert result["input_tokens"] == 10
    assert result["total_tokens"] == 125


def test_unknown_usage_does_not_become_zero():
    result = usage(None)
    assert result["input_tokens"] is None
    assert result["total_tokens"] is None
    assert result["usage_complete"] is False


def test_invalid_cache_count_does_not_create_negative_input():
    result = usage({"prompt_tokens": 10, "completion_tokens": 2,
                    "prompt_tokens_details": {"cached_tokens": 20}})
    assert result["usage_complete"] is False
    assert result["input_tokens"] is None


def test_context_restores_and_distinguishes_runs():
    module = importlib.import_module("backend.utils.llm_usage")
    assert module.current_trace_context() is None
    with module.trace_context("run-a", "thread-a"):
        first = module.current_trace_context()
        assert first["run_id"] == "run-a"
        with module.trace_context("run-b", "thread-b"):
            assert module.current_trace_context()["session_id"] == "thread-b"
        assert module.current_trace_context() == first
    assert module.current_trace_context() is None


def test_observer_passes_real_zero_and_unknown_to_storage(monkeypatch):
    import types
    updates = []
    service = types.ModuleType("backend.service.trace.trace_service")
    service.update_trace = lambda **kw: updates.append(kw)
    service.is_detail_enabled = lambda: False
    monkeypatch.setitem(sys.modules, service.__name__, service)
    observer = importlib.import_module("backend.observer.trace_observer").TraceObserver()
    observer.on_post_api_request(api_request_id="a", usage={
        "input_tokens": 0, "output_tokens": 5, "prompt_tokens": 100, "cache_read_tokens": 100})
    observer.on_post_api_request(api_request_id="b", usage=None)
    assert updates[0]["input_tokens"] == 0
    assert updates[0]["cache_read_tokens"] == 100
    assert updates[1]["input_tokens"] is None
    assert updates[1]["estimated_cost_usd"] is None


def test_auxiliary_client_records_cache_and_run_identity_without_network(monkeypatch):
    import types
    saved, updates, options, closed = [], [], [], []
    for name, members in {
        "backend.service.model_router": {"router": object()},
        "backend.service.trace.write": {
            "record_trace": lambda **kw: saved.append(kw) or 1,
            "update_trace": lambda **kw: updates.append(kw),
            "mark_trace_error": lambda *a: None},
        "backend.service.llm_gateway": {"gateway": SimpleNamespace(report_success=lambda *a: None)},
        "backend.service.scene_registry": {"scenes": None},
    }.items():
        mod = types.ModuleType(name)
        mod.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, mod)
    class Client:
        def __init__(self, **kwargs):
            options.append(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def close(self):
            closed.append(True)
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
                model="fixture-model", usage=SimpleNamespace(prompt_tokens=100, completion_tokens=5,
                                                            prompt_tokens_details={"cached_tokens": 100}))
    import openai
    monkeypatch.setattr(openai, "OpenAI", Client)
    module = importlib.import_module("backend.utils.llm_usage")
    traced = importlib.import_module("backend.utils.traced_llm")
    monkeypatch.setattr(traced, "count_messages_tokens", lambda messages: 0)
    config = {"api_url": "http://localhost/v1", "api_key": "fixture-not-a-secret", "model_name": "fixture-model"}
    with module.trace_context("run-731", "thread-42"):
        first = traced.TracedLLMClient().invoke([], source="test", model_override=config)
        second = traced.TracedLLMClient().invoke([], source="test", model_override=config)
    assert first.is_error is False
    assert updates[0]["input_tokens"] == 0
    assert updates[0]["cache_read_tokens"] == 100
    assert saved[0]["session_id"] == "thread-42"
    assert "run-731" in saved[0]["api_request_id"]
    assert saved[0]["api_request_id"] != saved[1]["api_request_id"]
    assert first.correlation["run_id"] == second.correlation["run_id"]
    assert options[0]["max_retries"] == 0
    assert len(closed) == 2


def test_unknown_usage_can_be_written_without_counting_daily_tokens(monkeypatch):
    module = importlib.import_module("backend.service.trace.write")
    statements = []
    class Connection:
        def execute(self, sql, values):
            statements.append((sql, values))
            return SimpleNamespace(fetchall=lambda: [])
        def commit(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(module, "_conn", lambda: Connection())
    module.update_trace("request", input_tokens=None, output_tokens=None, total_tokens=None,
                        cache_read_tokens=None, cache_write_tokens=None, reasoning_tokens=None,
                        estimated_cost_usd=None)
    assert len(statements) == 1
    assert statements[0][1][0] is None
    assert not any("daily_user_stats" in sql for sql, values in statements)


def test_tool_span_uses_completed_request_without_cross_session_fallback(monkeypatch):
    import types
    spans = []
    service = types.ModuleType("backend.service.trace.trace_service")
    service.update_trace = lambda **kw: None
    service.is_detail_enabled = lambda: False
    service.record_span = lambda **kw: spans.append(kw)
    monkeypatch.setitem(sys.modules, service.__name__, service)
    package = importlib.import_module("backend.service.trace")
    monkeypatch.setattr(package, "trace_service", service, raising=False)
    observer = importlib.import_module("backend.observer.trace_observer").TraceObserver()
    observer._pending["req-a"] = {"trace_id": 11, "session_id": "a", "created_at": 0}
    observer.on_post_api_request(api_request_id="req-a", usage=None)
    observer.on_post_tool_call(api_request_id="req-a", session_id="a", tool_name="query")
    assert spans and spans[0]["trace_id"] == 11
    observer._pending["req-b"] = {"trace_id": 22, "session_id": "b", "created_at": 0}
    observer.on_post_tool_call(tool_name="unknown-owner")
    observer.on_post_tool_call(api_request_id="missing", session_id="b", tool_name="wrong-id")
    assert len(spans) == 1
