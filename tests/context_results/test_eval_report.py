import importlib


def test_report_keeps_failures_and_marks_partial_usage_unknown():
    report = importlib.import_module("eval.context_budget.report")
    rows = [
        {"arm": "off", "passed": True, "format_correct": True, "input_tokens": 100, "output_tokens": 10,
         "usage_complete": True, "agent_elapsed_s": 1, "elapsed_s": 2, "accounting": {"calls": 2}},
        {"arm": "off", "passed": False, "format_correct": False, "input_tokens": None, "output_tokens": None,
         "usage_complete": False, "agent_elapsed_s": 3, "elapsed_s": 5, "accounting": {"calls": 1}},
    ]
    summary = report.summarize(rows)["off"]
    assert summary["runs"] == 2
    assert summary["successes"] == 1
    assert summary["input_tokens"] is None
    assert summary["known_input_tokens"] == 100
    assert summary["model_calls"] == 3
    assert summary["median_agent_s"] == 2
