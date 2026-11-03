"""Frozen small end-to-end system comparison; every run is a new process/home/store."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def tasks():
    noise = "padding informational line no actionable record " * 700
    rows = [{"group": "blue" if i % 3 == 0 else "red", "value": i % 97} for i in range(1800)]
    return [
        ("small", {"job_id": "J731", "value": 42},
         "Read the fixture and return JSON with job_id and value.", {"job_id": "J731", "value": 42}, None),
        ("protected", {"before": noise, "job_id": "J88421", "artifact_path": "/build/v17/report.json",
                       "version": 17, "after": noise},
         "Find the fixture job_id, artifact_path, version. Return exactly these JSON fields.",
         {"job_id": "J88421", "artifact_path": "/build/v17/report.json", "version": 17}, None),
        ("aggregate", {"rows": rows}, "Return JSON {count,sum} for rows where group equals blue.",
         {"count": 600, "sum": sum(r["value"] for r in rows if r["group"] == "blue")}, None),
        ("latent", {"before": noise, "record": {"label": "target", "reference": "REF-66042"}, "after": noise},
         "Find the record whose label is target. Return JSON {reference} using its reference value.",
         {"reference": "REF-66042"}, None),
        ("error", {"before": noise, "success": False, "error_code": "E_TIMEOUT_731",
                   "error": "execution stopped before commit", "committed": False, "after": noise},
         "Inspect the failed operation. Return JSON {error_code,committed}; do not retry or change data.",
         {"error_code": "E_TIMEOUT_731", "committed": False}, None),
        ("followup", {"before": noise, "job_id": "J910", "legacy": {"alias": "ARCH-58273"}, "after": noise},
         "Inspect the fixture and return JSON {job_id}.",
         {"alias": "ARCH-58273"}, "Now return JSON {alias} for the legacy alias in the same source.")
    ]


def parse_answer(text):
    from eval.context_budget.validation import strict_json
    return strict_json(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true")
    action.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--cases", default="")
    parser.add_argument("--parallel", type=int, default=2)
    args = parser.parse_args()
    if not args.execute and not args.prepare_only:
        parser.error("Choose --prepare-only (no model calls) or explicitly --execute.")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    items = [t for t in tasks() if not args.cases or t[0] in args.cases.split(",")]
    if args.cases and set(args.cases.split(",")) - {t[0] for t in items}:
        parser.error("Unknown task name in --cases")
    from eval.context_budget.variants import prepare_plan
    plan = prepare_plan(config, [t[0] for t in items], repeats=args.repeats, parallel=args.parallel)
    if not args.prepare_only and "context_mode" in {p["arm"] for p in plan["profiles"]} and args.upstream is None:
        parser.error("An upstream checkout is required to execute context-mode profiles")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [*sorted((REPO/"backend/context").rglob("*.py")),
               REPO/"backend/hermes/agent/tool_executor.py", REPO/"backend/hermes/agent/result_finalizer.py",
               REPO/"backend/hermes/agent/conversation_loop.py", *sorted(Path(__file__).parent.glob("*.py"))]
    plan["source_hashes"] = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    plan["configuration"] = {key: value for key, value in config.items() if "key" not in key.lower()}
    plan["config_sha256"] = hashlib.sha256(args.config.read_bytes()).hexdigest()
    plan["fixtures"] = {task[0]: hashlib.sha256(json.dumps(task[1], ensure_ascii=False).encode()).hexdigest() for task in items}
    (args.output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    if args.prepare_only:
        print(json.dumps({"planned_runs": plan["planned_runs"], "model_calls_executed": 0, "executed": False}))
        return
    manifest = {**plan, "executed": True, "model": config["model"],
                "base_url": config["base_url"],
                "scope": "real Hermes + upstream MCP tools; no platform hooks or Web/DB",
                "cost": config.get("cost_mode", "unknown until billing mode/rate source confirmed"),
                "context_mode_sha": subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"]).decode().strip() if args.upstream else None,
                "server_sha256": hashlib.sha256((args.upstream / "server.bundle.mjs").read_bytes()).hexdigest() if args.upstream else None}
    manifest["configuration"] = {key: value for key, value in config.items() if "key" not in key.lower()}
    # Zero means no execution only in plan.json. The actual per-attempt ledger
    # remains the authority; startup/interruption must not publish a false zero.
    manifest.pop("model_calls_executed", None)
    lock = args.upstream / "package-lock.json" if args.upstream else None
    manifest["dependency_lock_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest() if lock and lock.exists() else None
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    task_by_name = {item[0]: item for item in items}
    profiles = {profile["name"]: profile for profile in plan["profiles"]}

    def run(job):
        task, rep, profile = task_by_name[job["task"]], job["repeat"], profiles[job["profile"]]
        arm = profile["name"]
        name, data, question, expected, followup = task
        run_dir = args.output / f"{name}-{rep}-{arm}"
        run_dir.mkdir()
        fixture = run_dir / "fixture.json"
        fixture.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        frozen_config = {**config, "result_policy": profile["result_policy"],
                         "task_state_projection": profile["task_state_projection"], "profile": arm}
        frozen_config.pop("variants", None)
        run_config = run_dir / "config.json"
        # Credentials are provided by --key-file or environment, never per-run config.
        frozen_config = {key: value for key, value in frozen_config.items() if "key" not in key.lower() or key == "api_key_env"}
        run_config.write_text(json.dumps(frozen_config, indent=2), encoding="utf-8")
        cmd = [sys.executable, "-X", "utf8", str(Path(__file__).with_name("worker.py")),
               "--arm", profile["arm"], "--run-dir", str(run_dir), "--fixture", str(fixture),
               "--question", question, "--config", str(run_config), "--execute"]
        if args.upstream:
            cmd += ["--upstream", str(args.upstream)]
        if args.key_file:
            cmd += ["--key-file", str(args.key_file)]
        if followup:
            cmd += ["--followup", followup]
        start = time.perf_counter()
        try:
            proc = subprocess.run(cmd, cwd=REPO, capture_output=True, timeout=config.get("wall_seconds_per_run", 300))
            # Do not persist arbitrary SDK/log stderr; errors can contain request details.
            status = {"exit_code": proc.returncode}
        except subprocess.TimeoutExpired:
            status = {"timeout": True}
        outcome_path = run_dir / "outcome.json"
        outcome = json.loads(outcome_path.read_text(encoding="utf-8")) if outcome_path.exists() else {}
        usage_path = run_dir / "calls.json"
        calls = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else []
        from eval.context_budget.metrics import aggregate
        from eval.context_budget.validation import validate_answer
        validation = validate_answer(outcome.get("answer", ""), expected)
        row = {**status, "task": name, "repeat": rep, "arm": arm,
               "runtime_arm": profile["arm"], "result_policy": profile["result_policy"],
               "task_state_projection": profile["task_state_projection"],
               "passed": outcome.get("completed") is True and validation["facts_correct"],
               "format_correct": validation["format_correct"],
               "elapsed_s": time.perf_counter()-start, "agent_elapsed_s": outcome.get("elapsed_s"),
               "accounting": aggregate(calls), "usage_complete": bool(calls) and all(c.get("usage", {}).get("complete") for c in calls),
               "input_tokens": sum(sum(c.get("usage", {}).get(k) or 0 for k in ("uncached_input", "cache_read", "cache_write")) for c in calls),
               "output_tokens": sum(c.get("usage", {}).get("output") or 0 for c in calls),
               "uncached_input": sum(c.get("usage", {}).get("uncached_input") or 0 for c in calls),
               "cache_read": sum(c.get("usage", {}).get("cache_read") or 0 for c in calls)}
        if not row["usage_complete"]:
            for key in ("input_tokens", "output_tokens", "uncached_input", "cache_read"):
                row[key] = None
        (run_dir / "result.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
        return row

    results = []
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        for future in as_completed([pool.submit(run, job) for job in plan["jobs"]]):
            row = future.result()
            results.append(row)
            (args.output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
