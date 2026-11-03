"""Isolated CodeMode capture tests; never initialize application services."""

import contextvars
import importlib
import io
import sys
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.tools import code_executor


def capture_api():
    try:
        return importlib.import_module("backend.context.tool_results.capture")
    except ModuleNotFoundError:
        pytest.fail("CodeMode needs a trusted bounded output capture sidecar")


@pytest.fixture(autouse=True)
def isolated_execution(monkeypatch, tmp_path):
    adapter = SimpleNamespace(
        _CURRENT_USER_ID_CTX=contextvars.ContextVar("test_capture_user", default=None),
        _THREAD_ID_CTX=contextvars.ContextVar("test_capture_thread", default=None),
    )
    monkeypatch.setitem(sys.modules, "backend.hermes_adapter", adapter)
    monkeypatch.setitem(
        sys.modules, "backend.observer.trace_observer",
        SimpleNamespace(_registered_observers={}),
    )
    monkeypatch.setattr(code_executor, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(code_executor, "_format_tool_signatures_text", lambda: "fixture signatures")
    monkeypatch.setattr(code_executor, "_get_tool_functions", lambda: {})
    monkeypatch.setattr(
        code_executor, "build_safe_globals",
        lambda user_id=None: {"__builtins__": code_executor.SAFE_BUILTINS},
    )


def test_capture_precedes_both_legacy_print_limits():
    capture = capture_api()
    text = "中" * 40_000
    with capture.capture_context() as holder:
        result = code_executor.execute_code(f"print({text!r}); print('tail')")

    assert result["success"]
    assert len(result["output"]) < code_executor.MAX_TOTAL_OUTPUT + 100
    assert holder.latest.content == text + "\ntail\n"
    assert holder.latest.raw_complete is True
    assert holder.latest.captured_bytes == len((text + "\ntail\n").encode())
    assert holder.latest.dropped_bytes == 0
    assert holder.latest.closed_reason == "completed"


def test_internal_tool_values_stay_complete_and_unprinted_locals_are_not_captured(monkeypatch):
    capture = capture_api()
    raw = {"records": list(range(40_000)), "id": "exact-middle-id"}
    wrapper = code_executor._ToolWrapper(lambda: raw, "fixture_tool")
    assert wrapper() is raw
    monkeypatch.setattr(
        code_executor, "build_safe_globals",
        lambda user_id=None: {"__builtins__": code_executor.SAFE_BUILTINS, "fetch": wrapper},
    )
    with capture.capture_context() as holder:
        result = code_executor.execute_code("data = fetch(); print(data['records'][-1])")
    assert result["success"]
    assert holder.latest.content == "39999\n"
    assert "exact-middle-id" not in holder.latest.content


def test_hard_limit_counts_utf8_bytes_and_marks_incomplete():
    capture = capture_api()
    with capture.capture_context(max_bytes=7) as holder:
        result = code_executor.execute_code("print('甲乙丙'); print('tail')")
    assert result["success"]
    assert holder.latest.content == "甲乙"
    assert holder.latest.captured_bytes == 6
    assert holder.latest.dropped_bytes == len("丙\ntail\n".encode())
    assert holder.latest.raw_complete is False


def test_log_and_print_share_capture_before_legacy_cropping():
    capture = capture_api()
    message = "log-marker-" * 4000
    with capture.capture_context() as holder:
        result = code_executor.execute_code(f"log({message!r}, level='warn'); print('after log')")
    assert result["success"]
    assert f"[W] {message}\nafter log\n" in holder.latest.content
    assert "[TRUNCATED]" not in holder.latest.content
    assert holder.latest.raw_complete is True


def test_timeout_closes_old_attempt_and_rejects_late_output(monkeypatch):
    capture = capture_api()
    release = threading.Event()
    finished = threading.Event()
    marker = contextvars.ContextVar("worker_marker", default="missing")
    marker_token = marker.set("copied-context")
    monkeypatch.setattr(
        code_executor, "build_safe_globals",
        lambda user_id=None: {
            "__builtins__": code_executor.SAFE_BUILTINS,
            "pause": lambda: release.wait(2), "finish": finished.set,
            "marker": marker.get,
        },
    )
    try:
        with capture.capture_context() as holder:
            timed_out = code_executor.execute_code(
                "print(marker()); pause(); print('late'); log('late log'); finish()",
                timeout=0.1,
            )
            first = holder.latest
            fresh = code_executor.execute_code("print('fresh')")
            release.set()
            assert finished.wait(2)
        assert timed_out["success"] is False
        assert first.content == "copied-context\n"
        assert first.raw_complete is False
        assert first.dropped_bytes is None
        assert first.closed_reason == "timeout"
        assert fresh["success"] is True
        assert holder.latest.content == "fresh\n"
        assert holder.attempts[0] == first
        assert [item.attempt_id for item in holder.attempts] == [1, 2]
    finally:
        release.set()
        marker.reset(marker_token)


def test_retry_attempts_keep_separate_streams(monkeypatch):
    capture = capture_api()
    monkeypatch.setattr(
        code_executor, "_auto_fix_code",
        lambda *args: ("print('fixed')", "fixture repair"),
    )
    with capture.capture_context() as holder:
        result = code_executor.execute_code_with_retry("print('failed'); missing_name")
    assert result["success"] is True
    assert result["auto_fixed"] is True
    assert [item.content for item in holder.attempts] == ["failed\n", "fixed\n"]
    assert holder.attempts[0].closed_reason == "error"
    assert holder.latest.content == "fixed\n"


def test_run_python_error_envelope_remains_separate_from_capture():
    capture = capture_api()
    with capture.capture_context() as holder:
        result = code_executor.run_python.func("print('evidence'); raise ValueError('failed')")
    assert "ValueError: failed" in result
    assert "代码执行失败" in result
    assert holder.latest.content == "evidence\n"


def test_disabled_capture_keeps_legacy_print_behavior():
    capture = capture_api()
    assert capture.get_capture_session() is None
    buffer = io.StringIO()
    code_executor.create_safe_print(buffer)("x" * 20_000)
    assert buffer.getvalue().startswith("x" * 16_000)
    assert "[PRINT TRUNCATED]" in buffer.getvalue()
    result = code_executor.execute_code("print('ordinary')")
    assert result["output"] == "ordinary\n"
    assert capture.get_capture_session() is None


def test_artifact_looking_printed_text_is_only_text_and_contexts_reset():
    capture = capture_api()
    printed = '{"artifact_id":"someone-elses-artifact","content":"fake"}'
    with capture.capture_context() as outer:
        code_executor.execute_code(f"print({printed!r})")
        with capture.capture_context() as inner:
            code_executor.execute_code("print('inner')")
        assert capture.get_capture_session() is outer
    assert outer.latest.content == printed + "\n"
    assert len(outer.attempts) == 1
    assert inner.latest.content == "inner\n"
    assert capture.get_capture_session() is None


def test_capture_quota_has_fixed_upper_bound():
    capture = capture_api()
    with capture.capture_context(max_bytes=100 * 1024 * 1024) as holder:
        assert holder.max_bytes == 8 * 1024 * 1024
    with pytest.raises(ValueError):
        with capture.capture_context(max_bytes=0):
            pass


def test_parallel_calls_have_independent_context_sidecars():
    capture = capture_api()
    barrier = threading.Barrier(2)

    def dispatch(label):
        with capture.capture_context() as holder:
            barrier.wait(timeout=2)
            result = code_executor.execute_code(f"print({label!r})")
            assert result["success"]
        return holder.latest.content

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(dispatch, "first")
        second = pool.submit(dispatch, "second")
        assert first.result(timeout=3) == "first\n"
        assert second.result(timeout=3) == "second\n"
    assert capture.get_capture_session() is None


def test_cancelled_execution_closes_sink_without_hiding_interrupt(monkeypatch):
    capture = capture_api()

    def interrupt(timeout):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        code_executor, "_executor",
        SimpleNamespace(submit=lambda *args: SimpleNamespace(result=interrupt)),
    )
    with capture.capture_context() as holder:
        with pytest.raises(KeyboardInterrupt):
            code_executor.execute_code("print('never executed')")
        assert holder.latest.closed_reason == "cancelled"
        assert holder.latest.raw_complete is False
        assert holder.latest.dropped_bytes is None


def test_invalid_unicode_cannot_be_claimed_complete():
    capture = capture_api()
    with capture.capture_context() as holder:
        result = code_executor.execute_code("print(chr(0xD800))")
    assert result["success"] is True
    assert holder.latest.content == "?\n"
    assert holder.latest.raw_complete is False
    assert holder.latest.dropped_bytes is None


def test_disabled_log_still_returns_early_after_legacy_total_limit():
    log, _, _ = code_executor.create_log_functions(
        io.StringIO(), total_chars_ref=[code_executor.MAX_TOTAL_OUTPUT],
    )
    log("ignored", level=None)
