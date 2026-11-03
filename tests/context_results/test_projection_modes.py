"""Projection modes share a ledger; delta correctness depends on retained history."""
import json
from types import SimpleNamespace

import pytest

from backend.context.tool_results.runtime import bind_runtime, current_runtime


def observe(host, call, value):
    prepared = host.prepare("query", call, json.dumps({"job_id": value}), 4000)
    host.seal(prepared, prepared.content)
    return prepared


def project(host, history):
    message = host.task_state_message(history=history)
    if message:
        history.append(message)
    return json.loads(message["content"]) if message else None


@pytest.mark.parametrize("mode", ["full", "delta", "off"])
def test_projection_mode_never_disables_the_evidence_ledger(tmp_path, mode):
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True, projection_mode=mode):
        host = current_runtime(agent)
        observe(host, "c", "J1")
        assert len(host.task_snapshot()["tool_evidence"]["results"]) == 1
        body = project(host, [])
        assert (body is None) == (mode == "off")


def test_delta_only_projects_new_records_and_rebases_after_history_loss(tmp_path):
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True, projection_mode="delta"):
        host = current_runtime(agent)
        first = observe(host, "c1", "J1")
        history = []
        full = project(host, history)
        assert history[-1]["display_metadata"]["task_state_snapshot"]["projection_mode"] == "full"
        assert len(full["untrusted_task_evidence"]) == 1
        assert project(host, history) is None
        second = observe(host, "c2", "J2")
        delta = project(host, history)
        assert delta["base_version"] == full["evidence_version"]
        assert [r["artifact_id"] for r in delta["untrusted_task_evidence"]] == [second.artifact_id]
        assert delta["unchanged_results"] == 1
        rebased = project(host, history[1:])
        assert {r["artifact_id"] for r in rebased["untrusted_task_evidence"]} == {first.artifact_id, second.artifact_id}


def test_full_remains_full_after_each_new_record(tmp_path):
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True, projection_mode="full"):
        host = current_runtime(agent)
        history = []
        observe(host, "c1", "J1")
        project(host, history)
        observe(host, "c2", "J2")
        assert len(project(host, history)["untrusted_task_evidence"]) == 2


def test_delta_does_not_treat_omitted_fields_as_sent(tmp_path):
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True, projection_mode="delta"):
        host = current_runtime(agent)
        observe(host, "c1", "p" * 1200)
        small = host.task_state_message(history=[], max_chars=800)
        assert json.loads(small["content"])["untrusted_task_evidence"][0]["fields_omitted"] is True
        expanded = host.task_state_message(history=[small], max_chars=4000)
        assert "p" * 1200 in expanded["content"]


def test_delta_rejects_other_agent_anchor_and_broken_version_chain(tmp_path):
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True, projection_mode="delta"):
        host = current_runtime(agent)
        observe(host, "c1", "J1")
        message = host.task_state_message(history=[])
        message["display_metadata"]["task_state_snapshot"]["agent_id"] = "other"
        assert host.task_state_message(history=[message]) is not None
        history = []
        project(host, history)
        observe(host, "c2", "J2")
        project(host, history)
        body = json.loads(history[-1]["content"])
        body["base_version"] = -1
        history[-1]["content"] = json.dumps(body)
        reset = host.task_state_message(history=history)
        assert reset["display_metadata"]["task_state_snapshot"]["projection_mode"] == "full"


def test_invalid_options_fail_explicitly_instead_of_switching_to_legacy(tmp_path):
    with pytest.raises(ValueError):
        with bind_runtime(SimpleNamespace(session_id="s"), user_id="u", thread_id="t", root=tmp_path,
                          enabled=True, projection_mode="typo"):
            pass


def test_delta_rebases_after_ledger_clear_even_when_version_is_reused(tmp_path):
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True, projection_mode="delta"):
        host = current_runtime(agent)
        observe(host, "c1", "OLD")
        history = []
        project(host, history)
        host.binding.task_state.evidence_store.clear(host.scope)
        observe(host, "c2", "NEW")
        reset = host.task_state_message(history=history)
        assert reset["display_metadata"]["task_state_snapshot"]["projection_mode"] == "full"
        assert json.loads(reset["content"])["ledger_reset"] is True
        assert "OLD" not in reset["content"]


def test_delta_reports_expiry_and_sync_error_transitions_without_repeating_facts(tmp_path):
    import time
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True, projection_mode="delta"):
        host = current_runtime(agent)
        host.manager.store.ttl_seconds = 1
        observe(host, "c1", "J1")
        history = []
        project(host, history)
        host.binding.task_state.evidence_store.clock = lambda: time.time() + 2
        expired = project(host, history)
        assert expired["untrusted_task_evidence"][0]["source_expired"] is True
        assert project(host, history) is None
        host._evidence_error = "OSError"
        failure = project(host, history)
        assert failure["sync_error"] == "OSError"
        assert failure["untrusted_task_evidence"] == []
        host._evidence_error = None
        assert project(host, history)["sync_error"] is None


def test_finalizer_forwards_history_and_keeps_incomplete_tool_group_atomic(tmp_path, monkeypatch):
    import importlib
    from pathlib import Path
    import sys
    import types
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "backend/hermes"))
    helper = importlib.import_module("agent.result_finalizer")
    executor = types.ModuleType("agent.tool_executor")
    executor._flush_session_db_after_tool_progress = lambda *a, **kw: True
    monkeypatch.setitem(sys.modules, "agent.tool_executor", executor)
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True, projection_mode="delta"):
        host = current_runtime(agent)
        monkeypatch.setattr(helper, "_runtime", lambda _: host)
        observe(host, "c1", "J1")
        messages = [{"role": "assistant", "tool_calls": [{"id": "c1"}]}]
        assert helper.sync_task_snapshot(agent, messages)
        assert len(messages) == 1
        messages.append({"role": "tool", "tool_call_id": "c1", "content": "unchanged"})
        assert helper.sync_task_snapshot(agent, messages)
        assert len(messages) == 3
        assert helper.sync_task_snapshot(agent, messages)
        assert len(messages) == 3
