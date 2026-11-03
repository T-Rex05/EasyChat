"""Search-to-read contracts using real originals, scoped storage and tool budgets."""

import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.context.tool_results.store import ResultStore
from backend.context.tool_results.types import ResultScope


@pytest.fixture
def scope():
    return ResultScope("alice", "thread", tool_call_id="source")


@pytest.fixture
def store(tmp_path):
    return ResultStore(tmp_path / "originals")


def search_value(store, scope, value, query, *, ensure_ascii=False):
    source = json.dumps(value, ensure_ascii=ensure_ascii)
    saved = store.put(scope, source)
    matches = store.search(scope, query, artifact_ids=[saved["artifact_id"]])["matches"]
    assert matches
    for match in matches:
        assert source[match["start_char"]:match["end_char"]] == match["content"]
        assert match["source_hash"] == saved["source_hash"]
    return saved, matches


def test_nested_alias_key_and_value_recover_without_guessing(store, scope):
    value = {"legacy": {"alias": "ALIAS-OLD", "version": 2, "details": {"secret": "not-in-structure"}},
             "current": {"alias": "ALIAS-NEW"}}
    saved, matches = search_value(store, scope, value, '"alias"')
    assert [m["json_pointer"] for m in matches] == ["/legacy/alias", "/current/alias"]
    match = matches[0]
    assert match["parent_pointer"] == "/legacy"
    assert match["json_type"] == "string"
    assert match["json_location_status"] == "ok"
    assert match["neighbors"] == [
        {"json_pointer": "/legacy/version", "json_type": "number"},
        {"json_pointer": "/legacy/details", "json_type": "object"},
    ]
    assert "not-in-structure" not in json.dumps(match["neighbors"])
    read = store.read(scope, saved["artifact_id"], json_pointer=match["json_pointer"])
    assert json.loads(read["content"]) == "ALIAS-OLD"
    value_match = store.search(scope, "ALIAS-NEW")["matches"][0]
    assert value_match["json_pointer"] == "/current/alias"


@pytest.mark.parametrize("key", ["a/b", "~key", "", "用户", "quote\"key", "line\nkey"])
def test_array_and_escaped_keys_produce_readable_pointers(store, scope, key):
    value = {"items": [{key: "UNIQUE-NEEDLE", "other": True}]}
    saved, matches = search_value(store, scope, value, "UNIQUE-NEEDLE")
    pointer = "/items/0/" + key.replace("~", "~0").replace("/", "~1")
    assert matches[0]["json_pointer"] == pointer
    assert json.loads(store.read(scope, saved["artifact_id"], json_pointer=pointer)["content"]) == "UNIQUE-NEEDLE"


def test_escaped_unicode_source_key_uses_decoded_path(store, scope):
    saved, matches = search_value(store, scope, {"用户": {"alias": "OLD"}}, "u7528", ensure_ascii=True)
    assert matches[0]["json_pointer"] == "/用户"
    assert json.loads(store.read(scope, saved["artifact_id"], json_pointer="/用户")["content"]) == {"alias": "OLD"}


@pytest.mark.parametrize(("value", "query", "kind"), [
    ("root-needle", "needle", "string"), (False, "false", "boolean"),
    (None, "null", "null"), (12345, "234", "number"),
])
def test_root_scalar_has_empty_pointer(store, scope, value, query, kind):
    saved, matches = search_value(store, scope, value, query)
    assert matches[0]["json_pointer"] == ""
    assert matches[0]["parent_pointer"] is None
    assert matches[0]["json_type"] == kind
    assert json.loads(store.read(scope, saved["artifact_id"], json_pointer="")["content"]) == value


def test_same_scalar_in_long_single_line_does_not_confuse_paths(store, scope):
    value = {"padding": "x" * 20000, "rows": [{"alias": "repeat"}, {"alias": "repeat"}]}
    _, matches = search_value(store, scope, value, '"repeat"')
    assert [m["json_pointer"] for m in matches] == ["/rows/0/alias", "/rows/1/alias"]
    assert all(m["start_line"] == 1 for m in matches)


def test_array_neighbors_have_indices_and_a_fixed_count_limit(store, scope):
    value = {"rows": ["needle"] + list(range(30))}
    _, matches = search_value(store, scope, value, "needle")
    match = matches[0]
    assert match["json_pointer"] == "/rows/0"
    assert len(match["neighbors"]) == 8
    assert match["neighbors_omitted"] == 22
    assert match["neighbors"][0] == {"json_pointer": "/rows/1", "json_type": "number"}


@pytest.mark.parametrize(("source", "status"), [
    ('{"alias":"needle",}', "invalid_json"),
    ('{"alias":"needle","alias":"last"}', "ambiguous_keys"),
    ('{"nested":{"alias":"needle","alias":"last"}}', "ambiguous_keys"),
    ('log: alias=needle', "not_json"),
    ('{"alias":"needle"} trailing', "invalid_json"),
    ('{"bad":NaN,"alias":"needle"}', "invalid_json"),
    ('{"bad":[1,],"alias":"needle"}', "invalid_json"),
    ('{"alias":"needle"', "invalid_json"),
])
def test_unsafe_structure_falls_back_to_literal_source(store, scope, source, status):
    saved = store.put(scope, source)
    match = store.search(scope, "needle")["matches"][0]
    assert match["json_location_status"] == status
    assert "json_pointer" not in match
    assert "needle" in match["content"]
    assert store.read(scope, saved["artifact_id"])["content"] == source


def test_cross_token_query_keeps_literal_match_without_guessing_container(store, scope):
    saved = store.put(scope, '{"alias": "needle", "next": 1}')
    match = store.search(scope, 'needle", "next', artifact_ids=[saved["artifact_id"]])["matches"][0]
    assert match["json_location_status"] == "cross_node_match"
    assert "json_pointer" not in match


@pytest.mark.parametrize("source", [
    '[' * 70 + '"needle"' + ']' * 70,
    json.dumps(["needle"] + [0] * 20001),
    json.dumps({"large": "x" * (2 * 1024 * 1024), "alias": "needle"}),
    json.dumps({"k" * 2050: "needle"}),
], ids=["depth", "nodes", "source_size", "pointer_size"])
def test_structure_limits_do_not_break_literal_search(store, scope, source):
    saved = store.put(scope, source)
    match = store.search(scope, "needle", artifact_ids=[saved["artifact_id"]])["matches"][0]
    assert match["json_location_status"] == "limit_exceeded"
    assert "json_pointer" not in match


def test_partial_capture_never_looks_like_a_complete_business_result(store, scope):
    saved = store.put(scope, '{"alias":"needle"}', raw_complete=False)
    match = store.search(scope, "needle")["matches"][0]
    assert match["raw_complete"] is False
    assert match["json_pointer"] == "/alias"
    assert store.read(scope, saved["artifact_id"], json_pointer="/alias")["raw_complete"] is False


def test_tiny_structure_budget_omits_metadata_without_truncating_a_pointer(store, scope):
    store.put(scope, '{"legacy":{"alias":"needle"}}')
    match = store.search(scope, "needle", max_chars=1)["matches"][0]
    assert match["json_location_status"] == "budget_omitted"
    assert "json_pointer" not in match


def test_parallel_agents_do_not_share_structure_or_bypass_grants(store, scope):
    child = replace(scope, agent_id="child")
    private = store.put(scope, '{"private":{"alias":"needle"}}')
    shared = store.put(scope, '{"public":{"alias":"needle"}}')
    store.grant(scope, shared["artifact_id"], child.agent_id)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda s: store.search(s, "needle"), [scope, child, replace(scope, user_id="bob")]))
    assert {m["json_pointer"] for m in results[0]["matches"]} == {"/private/alias", "/public/alias"}
    assert [m["json_pointer"] for m in results[1]["matches"]] == ["/public/alias"]
    assert results[2]["matches"] == []
    assert store.read(child, private["artifact_id"], json_pointer="/private/alias")["status"] == "forbidden"


def test_expired_or_corrupt_json_never_yields_a_structured_match(tmp_path, scope):
    now = [100.0]
    retained = ResultStore(tmp_path / "retained", ttl_seconds=10, clock=lambda: now[0])
    expired = retained.put(scope, '{"legacy":{"alias":"needle"}}')
    now[0] = 111.0
    assert retained.search(scope, "needle")["matches"] == []
    assert retained.read(scope, expired["artifact_id"], json_pointer="/legacy/alias")["status"] == "expired"
    damaged = retained.put(scope, '{"private":{"alias":"needle"}}')
    # Use the actual published path rather than rely on the private directory name.
    original = next((tmp_path / "retained").rglob(damaged["artifact_id"] + ".txt"))
    original.write_text('{"changed":{"alias":"needle"}}', encoding="utf-8")
    assert retained.search(scope, "needle")["matches"] == []
    assert retained.read(scope, damaged["artifact_id"], json_pointer="/changed/alias")["status"] == "unavailable"


def test_many_exact_duplicate_values_can_all_be_restored_from_their_own_paths(store, scope):
    value = {"groups": [{"a/b": {"~field": "same-value", "index": i}} for i in range(50)]}
    saved, matches = search_value(store, scope, value, "same-value")
    # Structure enrichment is itself bounded across the search. Use targeted
    # source terms to obtain each path without claiming unlimited metadata.
    located = [match for match in matches if "json_pointer" in match]
    assert located
    for index, match in enumerate(located):
        assert match["json_pointer"] == f"/groups/{index}/a~1b/~0field"
        restored = store.read(scope, saved["artifact_id"], json_pointer=match["json_pointer"])
        assert json.loads(restored["content"]) == "same-value"
    assert any(match["json_location_status"] == "budget_omitted" for match in matches)


@pytest.mark.parametrize("number", ["9" * 4301, "1e9999"], ids=["integer_limit", "float_overflow"])
def test_unreadable_number_elsewhere_cannot_offer_an_unusable_selector(store, scope, number):
    store.put(scope, '{"big":' + number + ',"alias":"needle"}')
    match = store.search(scope, "needle")["matches"][0]
    assert match["json_location_status"] == "limit_exceeded"
    assert "json_pointer" not in match


@pytest.mark.parametrize("literal", [True, False], ids=["match_cap", "fts_only"])
def test_search_stops_structure_parsing_when_no_more_literal_matches_can_be_returned(store, scope, monkeypatch, literal):
    module = importlib.import_module("backend.context.tool_results.store")
    original = module.JsonLocations
    parsed = []

    def counted(source, **kwargs):
        parsed.append(source)
        return original(source, **kwargs)

    monkeypatch.setattr(module, "JsonLocations", counted)
    if literal:
        source = json.dumps(["needle"] * 150, indent=2)
        for _ in range(3):
            store.put(scope, source)
    else:
        store.put(scope, '{"alias":"NEEDLE"}')
    result = store.search(scope, "needle", max_chars=64000)
    assert len(result["matches"]) == (100 if literal else 0)
    assert len(parsed) == (1 if literal else 0)


def test_structure_work_limit_is_shared_across_all_matching_artifacts(store, scope, monkeypatch):
    module = importlib.import_module("backend.context.tool_results.store")
    original = module.JsonLocations
    parsed = []

    def counted(source, **kwargs):
        result = original(source, **kwargs)
        parsed.append(result)
        return result

    monkeypatch.setattr(module, "JsonLocations", counted)
    for _ in range(3):
        store.put(scope, json.dumps(["needle"] + [0] * 12000))
    found = store.search(scope, "needle", max_chars=64000)
    assert len(found["matches"]) == 3
    assert found["matches"][0]["json_location_status"] == "ok"
    assert all(m["json_location_status"] == "limit_exceeded" for m in found["matches"][1:])
    assert len(parsed) == 2
    assert sum(result.nodes_scanned for result in parsed) <= 20000


@pytest.mark.parametrize("budget", [512, 800, 1000, 1800])
def test_model_search_envelope_stays_bounded_and_its_pointer_can_be_read(tmp_path, budget):
    runtime = importlib.import_module("backend.context.tool_results.runtime")
    tools = importlib.import_module("backend.context.tool_results.tools")
    agent = SimpleNamespace(session_id="session")
    with runtime.bind_runtime(agent, user_id="alice", thread_id="thread", root=tmp_path, enabled=True):
        host = runtime.current_runtime(agent)
        value = {"legacy": {"alias": "needle", **{f"field{i}": i for i in range(20)}}}
        saved = host.manager.store.put(host.scope, json.dumps(value))
        with host.tool_context("context_search", "search", budget):
            encoded = tools.context_search.invoke({"query": "needle", "max_chars": 20000})
        assert len(encoded) <= budget
        found = json.loads(encoded)
        assert found["status"] == "ok"
        assert found["matches"]
        match = found["matches"][0]
        if budget >= 800:
            assert match["json_pointer"] == "/legacy/alias"
            with host.tool_context("context_read", "read", 1200):
                read = json.loads(tools.context_read.invoke({
                    "artifact_id": saved["artifact_id"], "json_pointer": match["json_pointer"],
                }))
            assert json.loads(read["content"]) == "needle"
