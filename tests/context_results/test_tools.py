"""Trusted tool scope, runtime lifetime and bounded recovery."""
import importlib
import json
from types import SimpleNamespace
import pytest


def api():
    return importlib.import_module("backend.context.tool_results.runtime")


def test_unbound_tools_cannot_accept_identity_or_read(tmp_path):
    tools = importlib.import_module("backend.context.tool_results.tools")
    result = json.loads(tools.context_read.invoke({"artifact_id": "anything"}))
    assert result["status"] == "unavailable"
    assert "user_id" not in tools.context_read.args
    assert "thread_id" not in tools.context_read.args


def test_runtime_recovery_and_physical_session_rollover(tmp_path):
    runtime = api()
    agent = SimpleNamespace(session_id="physical-1")
    with runtime.bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True):
        host = runtime.current_runtime(agent)
        with host.tool_context("query", "c1", 4000):
            prepared = host.prepare("query", "c1", '{"job_id":"J731"}', 4000)
        tools = importlib.import_module("backend.context.tool_results.tools")
        agent.session_id = "physical-2"
        with host.tool_context("context_read", "c2", 4000):
            result = json.loads(tools.context_read.invoke({"artifact_id": prepared.artifact_id,
                                                          "json_pointer": "/job_id"}))
        assert result["status"] == "ok"
        assert json.loads(result["content"]) == "J731"
    assert runtime.current_runtime(agent) is None


def test_child_does_not_inherit_parent_artifact_permission(tmp_path):
    runtime = api()
    parent = SimpleNamespace(session_id="root-session")
    child = SimpleNamespace(session_id="child-session", _subagent_id="worker")
    with runtime.bind_runtime(parent, user_id="u", thread_id="t", root=tmp_path, enabled=True):
        host = runtime.current_runtime(parent)
        prepared = host.prepare("query", "c1", '{"job_id":"private"}', 4000)
        child_host = runtime.current_runtime(child)
        assert child_host.scope.agent_id != host.scope.agent_id
        response = child_host.manager.store.read(child_host.scope, prepared.artifact_id)
        assert response["status"] in {"forbidden", "not_found"}


def test_disabled_binding_preserves_no_runtime(tmp_path):
    runtime = api()
    agent = SimpleNamespace(session_id="s")
    with runtime.bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=False):
        assert runtime.current_runtime(agent) is None


def test_disabled_new_agent_still_protects_restored_sealed_history(tmp_path):
    runtime = api()
    class LegacyCompressor:
        def prune_tool_results_only(self, messages, **kwargs):
            return [{**m, "content": "legacy rewrite"} for m in messages], 1
    original = {"role": "tool", "tool_call_id": "old", "content": "exact receipt J731",
                "display_metadata": {"context_result": {"managed": True, "artifact_id": "ar_old"}}}
    agent = SimpleNamespace(session_id="fresh", context_compressor=LegacyCompressor())
    with runtime.bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=False):
        assert runtime.current_runtime(agent) is None
        pruned, count = agent.context_compressor.prune_tool_results_only([original])
    assert pruned == [original]
    assert count == 0


def test_recovery_respects_current_call_budget_and_is_not_rearchived(tmp_path):
    runtime = api()
    tools = importlib.import_module("backend.context.tool_results.tools")
    agent = SimpleNamespace(session_id="s")
    with runtime.bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True):
        host = runtime.current_runtime(agent)
        prepared = host.prepare("query", "c1", "line\n" * 5000, 4000)
        with host.tool_context("context_read", "c2", 1000):
            output = tools.context_read.invoke({"artifact_id": prepared.artifact_id, "max_chars": 20000})
            assert len(output) <= 1000
            view = host.prepare("context_read", "c2", output, 1000)
        assert view.content == output
        assert view.action == "recovery"


@pytest.mark.parametrize("tool_name", ["terminal", "process", "read_file", "write_file", "search_files", "patch"])
def test_managed_sessions_reject_tools_that_can_bypass_scoped_storage(tmp_path, tool_name):
    runtime = api()
    agent = SimpleNamespace(session_id="s")
    executed = False
    with runtime.bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True):
        host = runtime.current_runtime(agent)
        with pytest.raises(PermissionError, match="context_read"):
            with host.tool_context(tool_name, "unsafe", 4000):
                executed = True
    assert not executed


def test_default_config_cannot_put_private_results_in_source_workspace(monkeypatch):
    from pathlib import Path
    import uuid
    runtime = api()
    agent = SimpleNamespace(session_id="s")
    invalid = Path(__file__).resolve().parents[2] / (".private-results-test-" + uuid.uuid4().hex)
    monkeypatch.setenv("AGENTFORGE_CONTEXT_RESULTS_DIR", str(invalid))
    with runtime.bind_runtime(agent, user_id="u", thread_id="t", enabled=True):
        assert runtime.current_runtime(agent) is None
    assert not invalid.exists()
