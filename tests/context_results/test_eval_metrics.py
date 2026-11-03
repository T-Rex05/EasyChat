"""Provider billable buckets must be complete and not double-count cached input."""
import importlib


def metrics():
    return importlib.import_module("eval.context_budget.metrics")


def test_zero_uncached_and_cache_read_are_not_counted_twice():
    result = metrics().normalize_usage({"prompt_tokens": 100, "completion_tokens": 5,
                                       "prompt_tokens_details": {"cached_tokens": 100}})
    assert result == {"uncached_input": 0, "cache_read": 100, "cache_write": 0,
                      "output": 5, "complete": True}


def test_missing_usage_is_unknown():
    assert metrics().normalize_usage(None)["complete"] is False
    assert metrics().cost(None, None) is None


def test_anthropic_input_does_not_already_include_cache():
    result = metrics().normalize_usage({"input_tokens": 10, "output_tokens": 5,
                                       "cache_read_input_tokens": 90, "cache_creation_input_tokens": 20})
    assert result["uncached_input"] == 10
    assert result["cache_read"] == 90
    assert result["cache_write"] == 20


def test_unknown_price_is_not_free():
    result = metrics().normalize_usage({"prompt_tokens": 100, "completion_tokens": 5})
    assert metrics().cost(result, None) is None
    assert metrics().cost(result, {"uncached_input": 1, "cache_read": .1, "cache_write": 1.2,
                                  "output": 2}) == 0.00011


def test_aggregate_includes_failed_calls_and_preserves_unknown():
    data = [{"status": "ok", "cost": .1, "elapsed_s": 1},
            {"status": "failed", "cost": .2, "elapsed_s": 2}]
    assert metrics().aggregate(data)["cost"] == .3
    assert metrics().aggregate(data + [{"status": "failed", "cost": None, "elapsed_s": 1}])["cost"] is None


def test_model_runner_cannot_execute_without_explicit_flag(tmp_path):
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "eval/context_budget/pilot.py", "--config", str(tmp_path/"absent.json"),
         "--output", str(tmp_path/"output"), "--upstream", str(tmp_path)],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert "--execute" in result.stderr
    assert not (tmp_path/"output").exists()
