"""Isolated, real-filesystem contracts for retained tool results."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace

import pytest


@pytest.fixture
def scope():
    from backend.context.tool_results.types import ResultScope

    return ResultScope("alice", "thread-1", session_id="session-1", tool_call_id="call-1")


@pytest.fixture
def store(tmp_path):
    from backend.context.tool_results.store import ResultStore

    return ResultStore(tmp_path / "results")


def test_scope_is_frozen_with_safe_defaults(scope):
    assert scope.agent_id == "root"
    assert scope.attempt_id == "1"
    with pytest.raises(FrozenInstanceError):
        scope.agent_id = "child"


def test_roundtrip_has_content_hash_and_capture_completeness(store, scope):
    content = 'First line\r\n{"job_id":"J731","value":"你好 🌍"}\n'
    saved = store.put(scope, content, tool_name="query", metadata={"origin": "fixture"})
    assert saved["status"] == "ok"
    assert saved["source_hash"] == hashlib.sha256(content.encode()).hexdigest()
    assert saved["raw_complete"] is True
    read = store.read(scope, saved["artifact_id"])
    assert read["status"] == "ok"
    assert read["content"] == content
    assert read["source_hash"] == saved["source_hash"]
    assert read["raw_complete"] is True
    assert read["selection_complete"] is True
    assert read["next_cursor"] is None


@pytest.mark.parametrize("changed", [{"user_id": "bob"}, {"thread_id": "thread-2"}, {"agent_id": "child"}])
def test_read_and_search_refuse_other_owners(store, scope, changed):
    saved = store.put(scope, "private matching secret")
    outsider = replace(scope, **changed)
    assert store.read(outsider, saved["artifact_id"])["status"] in {"forbidden", "not_found"}
    assert store.search(outsider, "secret")["matches"] == []
    assert store.search(outsider, "secret", artifact_ids=[saved["artifact_id"]])["matches"] == []


def test_grant_is_per_artifact_persisted_and_cannot_be_reshared(store, scope, tmp_path):
    from backend.context.tool_results.store import ResultStore

    saved = store.put(scope, "shared result")
    private = store.put(scope, "private result")
    store.grant(scope, saved["artifact_id"], "child")
    child = replace(scope, agent_id="child", session_id="new-session")
    restarted = ResultStore(tmp_path / "results")
    assert restarted.read(child, saved["artifact_id"])["content"] == "shared result"
    assert restarted.read(child, private["artifact_id"])["status"] == "forbidden"
    assert len(restarted.search(child, "result")["matches"]) == 1
    with pytest.raises(PermissionError):
        restarted.grant(child, saved["artifact_id"], "grandchild")
    outsider = replace(child, user_id="bob")
    assert restarted.read(outsider, saved["artifact_id"])["status"] == "forbidden"


def test_session_run_and_call_changes_do_not_change_authorization(store, scope):
    saved = store.put(scope, "retained")
    rotated = replace(scope, session_id="session-2", run_id="run-2", tool_call_id="read-1", attempt_id="2")
    assert store.read(rotated, saved["artifact_id"])["content"] == "retained"


@pytest.mark.parametrize(
    ("pointer", "expected"),
    [("/nested/value", 42), ("/a~1b/~0key/0", "你好"), ("/false", False), ("/empty", ""), ("", None)],
)
def test_json_pointer_preserves_values(store, scope, pointer, expected):
    value = {"nested": {"value": 42}, "a/b": {"~key": ["你好"]}, "false": False, "empty": ""}
    saved = store.put(scope, json.dumps(value, ensure_ascii=False))
    read = store.read(scope, saved["artifact_id"], json_pointer=pointer)
    assert read["status"] == "ok"
    assert json.loads(read["content"]) == (value if pointer == "" else expected)
    assert read["span"]["json_pointer"] == pointer


@pytest.mark.parametrize("pointer", ["nested", "/a~2b", "/items/-1", "/items/01", "/items/2", "/missing"])
def test_invalid_json_pointer_is_explicit(store, scope, pointer):
    saved = store.put(scope, '{"items":[1,2]}')
    assert store.read(scope, saved["artifact_id"], json_pointer=pointer)["status"] == "invalid_selector"


def test_line_selector_and_pagination_are_lossless_for_unicode(store, scope):
    saved = store.put(scope, "one\n你好🌍\nthird\nlast")
    page = store.read(scope, saved["artifact_id"], start_line=2, end_line=3, max_chars=2)
    parts = [page["content"]]
    while page["next_cursor"]:
        page = store.read(scope, saved["artifact_id"], cursor=page["next_cursor"], max_chars=2)
        assert page["status"] == "ok"
        assert len(page["content"]) <= 2
        parts.append(page["content"])
    assert "".join(parts) == "你好🌍\nthird\n"
    assert page["selection_complete"] is True


def test_json_selection_pages_reassemble_as_valid_json(store, scope):
    saved = store.put(scope, json.dumps({"x": ["🌍" * 10, 42]}))
    page = store.read(scope, saved["artifact_id"], json_pointer="/x", max_chars=5)
    parts = [page["content"]]
    while page["next_cursor"]:
        page = store.read(scope, saved["artifact_id"], cursor=page["next_cursor"], max_chars=5)
        parts.append(page["content"])
    assert json.loads("".join(parts)) == ["🌍" * 10, 42]


def test_cursor_is_bound_to_artifact_and_survives_restart(store, scope, tmp_path):
    from backend.context.tool_results.store import ResultStore

    first = store.put(scope, "abcdefgh")
    second = store.put(scope, "private")
    page = store.read(scope, first["artifact_id"], max_chars=3)
    cursor = page["next_cursor"]
    restarted = ResultStore(tmp_path / "results")
    assert restarted.read(scope, first["artifact_id"], cursor=cursor)["content"] == "defgh"
    assert restarted.read(scope, second["artifact_id"], cursor=cursor)["status"] == "invalid_cursor"
    assert restarted.read(scope, first["artifact_id"], cursor=cursor + "x")["status"] == "invalid_cursor"


def test_search_returns_literal_source_positions_and_bounded_content(store, scope):
    content = "header\n你好 ERROR[E42] at /tmp/a\ntrailer ERROR[E42]"
    saved = store.put(scope, content)
    found = store.search(scope, "ERROR[E42]", max_chars=19)
    assert found["status"] == "ok"
    assert len(found["content"]) <= 19
    assert found["matches"]
    first = found["matches"][0]
    assert first["artifact_id"] == saved["artifact_id"]
    assert first["start_line"] == 2
    assert content[first["start_char"] : first["end_char"]] == first["content"]
    assert first["source_hash"] == saved["source_hash"]
    assert found["truncated"] is True


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_search_lines_restore_exact_evidence_for_all_line_separators(store, scope, separator):
    content = separator.join(["header", "receipt_id=42", "footer"])
    saved = store.put(scope, content)
    match = store.search(scope, "receipt_id")["matches"][0]

    assert (match["start_line"], match["end_line"]) == (2, 2)
    assert match["content"] == "receipt_id=42"
    assert content[match["start_char"]:match["end_char"]] == match["content"]
    recovered = store.read(scope, saved["artifact_id"],
                           start_line=match["start_line"], end_line=match["end_line"])
    assert recovered["content"] == "receipt_id=42" + separator


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_multiline_search_evidence_can_be_paged_without_rewriting_line_endings(store, scope, separator):
    query = "receipt_id=42" + separator + "status=ok"
    saved = store.put(scope, separator.join(["header", query, "footer"]))
    match = store.search(scope, query)["matches"][0]

    assert (match["start_line"], match["end_line"]) == (2, 3)
    page = store.read(scope, saved["artifact_id"], start_line=match["start_line"],
                      end_line=match["end_line"], max_chars=4)
    parts = [page["content"]]
    while page["next_cursor"]:
        page = store.read(scope, saved["artifact_id"], cursor=page["next_cursor"], max_chars=4)
        parts.append(page["content"])
    assert "".join(parts) == query + separator


def test_expiry_releases_payload_and_returns_tombstone(tmp_path, scope):
    from backend.context.tool_results.store import ResultStore

    now = [100.0]
    store = ResultStore(tmp_path, ttl_seconds=10, max_user_bytes=8, clock=lambda: now[0])
    saved = store.put(scope, "12345678")
    assert saved["expires_at"] == 110.0
    now[0] = 111.0
    expired = store.read(scope, saved["artifact_id"])
    assert expired["status"] == "expired"
    assert expired["source_hash"] == saved["source_hash"]
    assert store.search(scope, "12345678")["matches"] == []
    assert store.put(scope, "new")["raw_complete"] is True
    assert store.read(replace(scope, user_id="bob"), saved["artifact_id"])["status"] == "forbidden"


def test_byte_quotas_crop_at_unicode_boundaries_and_report_loss(tmp_path, scope):
    from backend.context.tool_results.store import ResultStore

    store = ResultStore(tmp_path, max_artifact_bytes=5, max_user_bytes=8, max_total_bytes=9)
    first = store.put(scope, "你好世界")
    assert first["status"] == "ok"
    assert first["raw_complete"] is False
    assert first["captured_bytes"] == 3
    assert first["original_bytes"] == 12
    assert store.read(scope, first["artifact_id"])["content"] == "你"
    second = store.put(scope, "abcde")
    assert second["raw_complete"] is True
    third = store.put(scope, "blocked")
    assert third["status"] == "quota_exceeded"
    other = store.put(replace(scope, user_id="bob"), "xx")
    assert other["captured_bytes"] == 1
    assert other["raw_complete"] is False


def test_upstream_incomplete_stays_incomplete(store, scope):
    saved = store.put(scope, "partial source", raw_complete=False)
    assert saved["raw_complete"] is False
    assert store.read(scope, saved["artifact_id"])["raw_complete"] is False


def test_concurrent_writes_are_unique_and_enforce_user_quota(tmp_path, scope):
    from backend.context.tool_results.store import ResultStore

    stores = [ResultStore(tmp_path, max_user_bytes=40) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: stores[i % 4].put(scope, f"{i:04d}"), range(20)))
    saved = [result for result in results if result["status"] == "ok"]
    assert len(saved) == 10
    assert len({result["artifact_id"] for result in saved}) == 10
    assert sum(result["captured_bytes"] for result in saved) == 40
    assert all(stores[0].read(scope, result["artifact_id"])["status"] == "ok" for result in saved)


def test_restart_reconciles_missing_content_and_orphan_files(tmp_path, scope):
    from backend.context.tool_results.store import ResultStore

    store = ResultStore(tmp_path)
    saved = store.put(scope, "retained")
    payload = tmp_path / "artifacts" / f'{saved["artifact_id"]}.txt'
    payload.unlink()
    orphan = payload.with_name("ar_" + "a" * 32 + ".txt")
    orphan.write_text("orphan", encoding="utf-8")
    restarted = ResultStore(tmp_path)
    assert restarted.read(scope, saved["artifact_id"])["status"] == "unavailable"
    assert not orphan.exists()


def test_corrupted_content_is_not_returned_as_original(store, scope, tmp_path):
    saved = store.put(scope, "original")
    payload = tmp_path / "results" / "artifacts" / f'{saved["artifact_id"]}.txt'
    payload.write_text("corrupted", encoding="utf-8")
    assert store.read(scope, saved["artifact_id"])["status"] == "unavailable"


def test_artifact_ids_cannot_be_paths(store, scope, tmp_path):
    outside = tmp_path / "private.txt"
    outside.write_text("private data", encoding="utf-8")
    for bad_id in [str(outside), "../../private.txt", "ar_/../../private.txt"]:
        assert store.read(scope, bad_id)["status"] == "not_found"


def test_persisted_views_are_immutable_auditable_and_owner_only(store, scope, tmp_path):
    saved = store.put(scope, "original")
    store.persist_view(scope, saved["artifact_id"], "view-1", "canonical", {"action": "keep"})
    store.persist_view(scope, saved["artifact_id"], "view-1", "canonical", {"action": "keep"})
    with pytest.raises(ValueError):
        store.persist_view(scope, saved["artifact_id"], "view-1", "changed", {})
    store.grant(scope, saved["artifact_id"], "child")
    with pytest.raises(PermissionError):
        store.persist_view(replace(scope, agent_id="child"), saved["artifact_id"], "view-2", "child", {})
    with sqlite3.connect(tmp_path / "results" / "results.sqlite3") as db:
        row = db.execute("SELECT content, content_hash FROM views WHERE view_id = 'view-1'").fetchone()
    assert row == ("canonical", hashlib.sha256(b"canonical").hexdigest())


@pytest.mark.parametrize("kwargs", [{"max_chars": 0}, {"start_line": 0}, {"start_line": 2, "end_line": 1}])
def test_invalid_read_bounds_are_explicit(store, scope, kwargs):
    saved = store.put(scope, "content")
    assert store.read(scope, saved["artifact_id"], **kwargs)["status"] == "invalid_selector"


def test_search_does_not_report_truncation_due_to_unselected_artifacts(store, scope):
    ids = sorted(store.put(scope, "needle")["artifact_id"] for _ in range(4))
    result = store.search(scope, "needle", artifact_ids=[ids[0]], max_chars=6)
    assert result["content"] == "needle"
    assert result["truncated"] is False


def test_search_finds_literal_multiline_query(store, scope):
    source = "first\nsecond\nthird"
    store.put(scope, source)
    result = store.search(scope, "\nsecond\n")
    assert result["matches"]
    assert "\nsecond\n" in result["matches"][0]["content"]


def test_overlong_pointer_is_rejected_before_issuing_unusable_cursor(store, scope):
    key = "k" * 17000
    saved = store.put(scope, json.dumps({key: "value"}))
    assert store.read(scope, saved["artifact_id"], json_pointer="/" + key, max_chars=1)["status"] == "invalid_selector"


def test_failed_atomic_publication_leaves_no_record_or_files(store, scope, tmp_path, monkeypatch):
    def fail(*_):
        raise OSError("simulated publication failure")

    monkeypatch.setattr("backend.context.tool_results.store.os.replace", fail)
    with pytest.raises(OSError, match="simulated"):
        store.put(scope, "original")
    assert list((tmp_path / "results" / "artifacts").iterdir()) == []
    assert store.search(scope, "original")["matches"] == []


def test_empty_result_is_complete(store, scope):
    saved = store.put(scope, "")
    result = store.read(scope, saved["artifact_id"])
    assert result["status"] == "ok"
    assert result["raw_complete"] is True
    assert result["content"] == ""


def test_views_share_the_user_byte_quota(tmp_path, scope):
    from backend.context.tool_results.store import ResultStore

    store = ResultStore(tmp_path, max_user_bytes=12)
    saved = store.put(scope, "1234")
    store.persist_view(scope, saved["artifact_id"], "v", "abcdef", {})
    assert store.put(scope, "next")["status"] == "quota_exceeded"


def test_concurrent_cold_start_and_writes(tmp_path, scope):
    from backend.context.tool_results.store import ResultStore

    def save(index):
        store = ResultStore(tmp_path)
        saved = store.put(scope, str(index))
        return saved, store.read(scope, saved["artifact_id"])["content"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(save, range(12)))
    assert len({saved["artifact_id"] for saved, _ in results}) == 12
    assert {content for _, content in results} == {str(i) for i in range(12)}


def test_user_metadata_is_bounded(store, scope):
    with pytest.raises(ValueError, match="metadata"):
        store.put(scope, "content", metadata={"large": "x" * 20000})


@pytest.mark.parametrize("values", [("", "thread"), ("alice", ""), ("alice", "thread", ""), (12, "thread")])
def test_scope_rejects_missing_or_nonstring_identity(values):
    from backend.context.tool_results.types import ResultScope

    with pytest.raises(ValueError):
        ResultScope(*values)


@pytest.mark.parametrize("query", ['"', "AND", ":", "💥", "\x00"])
def test_search_treats_query_as_literal_data(store, scope, query):
    store.put(scope, f"prefix {query} suffix")
    result = store.search(scope, query)
    assert result["status"] == "ok"
    assert result["matches"]
    assert query in result["matches"][0]["content"]


def test_grant_metadata_cannot_grow_without_bound(store, scope):
    saved = store.put(scope, "content")
    for index in range(128):
        store.grant(scope, saved["artifact_id"], f"child-{index}")
    store.grant(scope, saved["artifact_id"], "child-0")
    with pytest.raises(ValueError, match="quota"):
        store.grant(scope, saved["artifact_id"], "one-too-many")
