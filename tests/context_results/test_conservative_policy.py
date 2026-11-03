"""Candidate-field preservation is explicit, bounded and separate from protected facts."""
import json
from types import SimpleNamespace

import pytest

from backend.context.tool_results.manager import ResultManager
from backend.context.tool_results.store import ResultStore
from backend.context.tool_results.types import ResultScope


@pytest.fixture
def parts(tmp_path):
    store = ResultStore(tmp_path)
    return store, ResultScope("u", "t")


def view(parts, data, *, policy="conservative-v1", budget=2400):
    store, scope = parts
    manager = ResultManager(store, policy=policy)
    raw = json.dumps(data, ensure_ascii=False)
    prepared = manager.prepare(scope, "query", raw, max_chars=budget)
    return manager, prepared, json.loads(prepared.content)


def test_unknown_nested_fields_are_copied_without_becoming_protected(parts):
    manager, prepared, body = view(parts, {"padding": "x" * 15000,
        "record": {"label": "target", "reference": "REF-731", "committed": False},
        "legacy": {"alias": "OLD"}, "job_id": "J731"})
    extras = {f["pointer"]: f["value"] for f in body["other_fields"]}
    assert extras["/record/reference"] == "REF-731"
    assert extras["/record/committed"] is False
    assert extras["/legacy/alias"] == "OLD"
    assert all(f["key"] != "reference" for f in prepared.evidence_protected)
    assert any(f["value"] == "J731" for f in prepared.protected)
    assert manager.seal(prepared, prepared.content)["policy_version"] == "conservative-v1"
    assert len(prepared.content) <= 2400


def test_other_fields_have_real_array_and_escaped_pointers(parts):
    _, prepared, body = view(parts, {"padding": "x" * 15000, "rows": [{"a/b": {"~alias": "V"}}]})
    fact = next(f for f in body["other_fields"] if f["value"] == "V")
    assert fact["pointer"] == "/rows/0/a~1b/~0alias"
    store, scope = parts
    assert json.loads(store.read(scope, prepared.artifact_id, json_pointer=fact["pointer"])["content"]) == "V"


def test_long_values_are_omitted_without_silent_truncation_and_shallow_fields_win(parts):
    _, _, body = view(parts, {"rows": [{"deep": f"v{i}"} for i in range(100)],
                             "blob": "q" * 15000, "late_reference": "SHALLOW"})
    assert any(f["value"] == "SHALLOW" for f in body["other_fields"])
    assert not any(f["key"] == "blob" for f in body["other_fields"])
    assert body["omitted_other_fields"] > 0
    assert body["other_field_scan_partial"] is False


@pytest.mark.parametrize("source", [
    '{"alias":"wrong","alias":"right","pad":"' + "x" * 10000 + '"}',
    '{"alias":"unknown","pad":"' + "x" * 10000,
    json.dumps({"alias": "unknown", "pad": "x" * (2 * 1024 * 1024)}),
], ids=["duplicate", "incomplete", "scan_limit"])
def test_ambiguous_or_unscanned_json_does_not_claim_other_fields(parts, source):
    store, scope = parts
    prepared = ResultManager(store, policy="conservative-v1").prepare(scope, "query", source, max_chars=2400)
    body = json.loads(prepared.content)
    assert body["other_fields"] == []
    assert body["other_field_scan_partial"] is True
    assert body["omitted_other_fields"] is None


def test_legacy_and_default_policy_remain_an_identical_baseline(parts):
    store, scope = parts
    raw = json.dumps({"pad": "x" * 15000, "reference": "HIDDEN"})
    default = ResultManager(store).prepare(scope, "query", raw)
    legacy = ResultManager(store, policy="rules-v1").prepare(scope, "query", raw)
    for prepared in (default, legacy):
        assert "other_fields" not in json.loads(prepared.content)
    assert ResultManager(store).policy == "rules-v1"


def test_small_json_stays_verbatim_under_candidate_policy(parts):
    store, scope = parts
    raw = '{"reference": "EXACT"}'
    prepared = ResultManager(store, policy="conservative-v1").prepare(scope, "query", raw)
    assert prepared.content == raw


def test_unknown_policy_is_rejected(parts):
    with pytest.raises(ValueError):
        ResultManager(parts[0], policy="typo")


def test_captured_json_fields_disclose_their_relative_source(parts):
    store, scope = parts
    text = json.dumps({"pad": "x" * 15000, "reference": "CAPTURED"})
    capture = SimpleNamespace(content=text, raw_complete=True, captured_bytes=len(text),
                              dropped_bytes=0, attempt_id=1, closed_reason="completed")
    prepared = ResultManager(store, policy="conservative-v1").prepare(
        scope, "run_python", '{"success":true}', max_chars=2400, capture=capture)
    fact = next(f for f in json.loads(prepared.content)["other_fields"] if f["value"] == "CAPTURED")
    assert fact["pointer"] == "/reference"
    assert fact["source"] == "captured_output"
    assert store.read(scope, prepared.artifact_id, json_pointer="/reference")["status"] == "invalid_selector"


def test_pressure_receipt_does_not_claim_to_show_discarded_other_fields(tmp_path):
    from backend.context.tool_results.runtime import bind_runtime, current_runtime
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True,
                      result_policy="conservative-v1"):
        host = current_runtime(agent)
        prepared = host.prepare("query", "c1", json.dumps({"pad": "x" * 15000, "reference": "R1"}), 2400)
        before = {"presented_other_fields": prepared.presented_other_fields,
                  "omitted_other_fields": prepared.omitted_other_fields}
        assert before["presented_other_fields"] > 0
        receipt = host.budget_pressure(prepared, 200)
        after = host.manager.seal(receipt, receipt.content)
        assert after["presented_other_fields"] == 0
        assert after["omitted_other_fields"] == before["omitted_other_fields"] + before["presented_other_fields"]
