"""Offline contracts for deterministic model views (never load application .env)."""
import importlib
import json
from types import SimpleNamespace


def components(tmp_path):
    types = importlib.import_module("backend.context.tool_results.types")
    store_mod = importlib.import_module("backend.context.tool_results.store")
    manager_mod = importlib.import_module("backend.context.tool_results.manager")
    store = store_mod.ResultStore(tmp_path)
    return manager_mod.ResultManager(store), store, types.ResultScope("u1", "t1")


def test_long_json_protects_middle_fields_and_restores_original(tmp_path):
    manager, store, scope = components(tmp_path)
    raw = json.dumps({"noise": "x" * 20000, "job_id": "J731", "artifact_path": "/a/v2.bin",
                      "version": 17, "tail": "z" * 20000})
    prepared = manager.prepare(scope, "query", raw, max_chars=3000)
    assert prepared.managed
    assert len(prepared.content) <= 3000
    assert "J731" in prepared.content
    assert "/a/v2.bin" in prepared.content
    assert any(f["pointer"] == "/version" and f["value"] == 17 for f in prepared.protected)
    read = store.read(scope, prepared.artifact_id, json_pointer="/job_id")
    assert json.loads(read["content"]) == "J731"


def test_small_result_is_unchanged_and_view_hash_is_final_content(tmp_path):
    manager, _, scope = components(tmp_path)
    raw = '{"id": "A"}'
    prepared = manager.prepare(scope, "query", raw, max_chars=3000)
    assert prepared.content == raw
    final = "UNTRUSTED\n" + prepared.content
    metadata = manager.seal(prepared, final)
    import hashlib
    assert metadata["canonical_hash"] == hashlib.sha256(final.encode()).hexdigest()
    assert metadata["managed"] is True
    assert metadata["view_id"]


def test_multimodal_is_not_stringified(tmp_path):
    manager, _, scope = components(tmp_path)
    raw = [{"type": "image", "data": "abc"}, {"type": "text", "text": "hello"}]
    prepared = manager.prepare(scope, "vision", raw, max_chars=3000)
    assert prepared.content is raw
    assert not prepared.managed


def test_protected_overflow_is_explicit_and_original_still_readable(tmp_path):
    manager, store, scope = components(tmp_path)
    raw = json.dumps({"items": [{"job_id": f"J{i:04d}"} for i in range(300)]})
    prepared = manager.prepare(scope, "query", raw, max_chars=1000)
    body = json.loads(prepared.content)
    assert len(prepared.content) <= 1000
    assert body["omitted_protected_fields"] > 0
    assert json.loads(store.read(scope, prepared.artifact_id, json_pointer="/items/299/job_id")["content"]) == "J0299"


def test_capture_keeps_execution_status_and_uncropped_stdout(tmp_path):
    manager, store, scope = components(tmp_path)
    capture = SimpleNamespace(content="full stdout " * 1000, raw_complete=False,
                              captured_bytes=12000, dropped_bytes=None, attempt_id=2, closed_reason="timeout")
    prepared = manager.prepare(scope, "run_python", '{"success":false,"error":"timeout"}',
                               max_chars=3000, capture=capture)
    assert "timeout" in prepared.content
    assert not prepared.raw_complete
    saved = store.read(scope, prepared.artifact_id, json_pointer="/captured_output", max_chars=20000)
    assert json.loads(saved["content"]) == capture.content


def test_store_failure_falls_back_without_inventing_a_reference(tmp_path):
    manager, _, scope = components(tmp_path)
    def fail(*args, **kwargs):
        raise OSError("disk full")
    manager.store.put = fail
    prepared = manager.prepare(scope, "query", "A" * 9000, max_chars=2000)
    assert not prepared.managed
    assert prepared.artifact_id is None
    assert prepared.content == "A" * 9000


def test_default_view_cap_is_smaller_than_native_hermes_budget(tmp_path):
    manager, _, scope = components(tmp_path)
    prepared = manager.prepare(scope, "query", "x" * 60000, max_chars=100000)
    assert len(prepared.content) <= 8000
    assert prepared.action == "extract"


def test_unarchived_tail_is_never_claimed_as_recoverable_evidence(tmp_path):
    manager, store, scope = components(tmp_path)
    store.max_artifact_bytes = 100
    raw = "prefix " * 1000 + "\njob_id=NOT_CAPTURED"
    prepared = manager.prepare(scope, "query", raw, max_chars=1000)
    assert not prepared.raw_complete
    assert not any(f["value"] == "NOT_CAPTURED" for f in prepared.protected)
    assert "NOT_CAPTURED" not in prepared.content
