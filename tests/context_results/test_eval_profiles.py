"""Experiment preparation must be useful without credentials or model execution."""
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


def profiles():
    return importlib.import_module("eval.context_budget.variants")


def config():
    return {"model": "local-test", "base_url": "http://127.0.0.1:9/v1", "variants": [
        {"name": "candidate_full", "arm": "rules", "result_policy": "conservative-v1", "task_state_projection": "full"},
        {"name": "candidate_delta", "arm": "rules", "result_policy": "conservative-v1", "task_state_projection": "delta"},
        {"name": "candidate_off", "arm": "rules", "result_policy": "conservative-v1", "task_state_projection": "off"},
    ]}


def test_plan_crosses_tasks_repeats_profiles_and_pins_all_modes():
    plan = profiles().prepare_plan(config(), ["latent", "followup"], repeats=3, parallel=1)
    assert plan["planned_runs"] == 18
    assert len({(j["task"], j["repeat"], j["profile"]) for j in plan["jobs"]}) == 18
    assert plan["jobs"] == profiles().prepare_plan(config(), ["latent", "followup"], repeats=3, parallel=1)["jobs"]
    assert [p["task_state_projection"] for p in plan["profiles"]] == ["full", "delta", "off"]
    assert plan["model_calls_executed"] == 0


@pytest.mark.parametrize("bad", [
    [{"name": "../escape", "arm": "rules"}],
    [{"name": "duplicate", "arm": "rules"}, {"name": "duplicate", "arm": "rules"}],
    [{"name": "x", "arm": "rules", "result_policy": "typo"}],
    [{"name": "x", "arm": "rules", "task_state_projection": "typo"}],
    [{"name": "x", "arm": "rules", "api_key": "must-never-be-a-profile-option"}],
    [],
], ids=["path", "duplicate", "policy", "projection", "unknown_option", "empty"])
def test_invalid_profile_is_rejected_before_execution(bad):
    with pytest.raises(ValueError):
        profiles().prepare_plan({**config(), "variants": bad}, ["latent"], repeats=1, parallel=1)


@pytest.mark.parametrize(("repeats", "parallel"), [(0, 1), (1, 0), (-1, 1), (True, 1)])
def test_invalid_schedule_limits_are_rejected(repeats, parallel):
    with pytest.raises(ValueError):
        profiles().prepare_plan(config(), ["latent"], repeats=repeats, parallel=parallel)


def test_prepare_only_cli_needs_no_upstream_or_credentials(tmp_path):
    source = tmp_path / "config.json"
    source.write_text(json.dumps(config()), encoding="utf-8")
    output = tmp_path / "prepared"
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run([
        sys.executable, "-X", "utf8", str(repo / "eval/context_budget/pilot.py"),
        "--prepare-only", "--config", str(source), "--output", str(output), "--cases", "latent,error",
        "--repeats", "2", "--parallel", "1", "--key-file", str(tmp_path / "nonexistent-key"),
    ], cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr[-1500:]
    prepared = json.loads((output / "plan.json").read_text(encoding="utf-8"))
    assert prepared["planned_runs"] == 12
    assert prepared["model_calls_executed"] == 0
    assert not list(output.rglob("calls.json"))


def test_upstream_audit_recognizes_a_custom_profile_name(tmp_path):
    report = importlib.import_module("eval.context_budget.report")
    details = report.audit(tmp_path, [{"arm": "cm_reference", "runtime_arm": "context_mode", "task": "x", "repeat": 0}])
    assert details["context_mode_runs_without_recorded_mcp"] == ["x-0-cm_reference"]


def test_execute_manifest_never_inherits_a_false_zero_call_count(tmp_path, monkeypatch):
    from types import SimpleNamespace
    pilot = importlib.import_module("eval.context_budget.pilot")
    source = tmp_path / "config.json"
    source.write_text(json.dumps({**config(), "variants": config()["variants"][:1]}), encoding="utf-8")
    output = tmp_path / "executed"

    def fake_worker(command, **kwargs):
        run = Path(command[command.index("--run-dir") + 1])
        (run / "outcome.json").write_text(json.dumps({
            "completed": True, "answer": '{"job_id":"J731","value":42}', "elapsed_s": 0.1}), encoding="utf-8")
        (run / "calls.json").write_text(json.dumps([{"status": "ok", "usage": {
            "complete": True, "uncached_input": 1, "cache_read": 0, "cache_write": 0, "output": 1}}]), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pilot.subprocess, "run", fake_worker)
    monkeypatch.setattr(sys, "argv", ["pilot", "--execute", "--config", str(source), "--output", str(output),
                                     "--cases", "small", "--parallel", "1"])
    pilot.main()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("model_calls_executed") != 0
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))[0]
    assert result["accounting"]["calls"] == 1
    assert result["arm"] == "candidate_full"


def test_custom_profile_report_keeps_an_entirely_failed_arm(tmp_path, monkeypatch):
    report = importlib.import_module("eval.context_budget.report")
    source, output = tmp_path / "input", tmp_path / "report"
    source.mkdir()
    rows = [{"task": "latent", "repeat": 0, "arm": name, "runtime_arm": "rules", "passed": False,
             "format_correct": False, "usage_complete": False, "input_tokens": None, "output_tokens": None,
             "elapsed_s": 2, "agent_elapsed_s": None, "accounting": {"calls": 0}}
            for name in ("candidate_full", "candidate_delta", "candidate_off")]
    (source / "results.json").write_text(json.dumps(rows), encoding="utf-8")
    (source / "manifest.json").write_text(json.dumps({
        "model": "fake", "cases": ["latent"], "repeats": 1, "parallel": 1,
        "context_mode_sha": None, "arms": [row["arm"] for row in rows]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["report", "--input", str(source), "--output", str(output)])
    report.main()
    text = (output / "report.md").read_text(encoding="utf-8")
    assert all(f"| {row['arm']} |" in text for row in rows)
    assert "unknown" in text
