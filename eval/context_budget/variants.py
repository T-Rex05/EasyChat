"""Pure validation and scheduling; no credentials, providers or MCP imports."""
import random
import re

from backend.context.tool_results.options import validate_options


def resolve_profiles(config):
    variants = config.get("variants", [{"name": arm, "arm": arm} for arm in ("off", "rules", "context_mode")])
    if not isinstance(variants, list) or not 1 <= len(variants) <= 8:
        raise ValueError("variants must contain between 1 and 8 profiles")
    result, names = [], set()
    allowed = {"name", "arm", "result_policy", "task_state_projection"}
    for variant in variants:
        if not isinstance(variant, dict) or set(variant) - allowed:
            raise ValueError("Unknown profile option")
        name, arm = variant.get("name"), variant.get("arm")
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", name)
                or name in names or not isinstance(arm, str) or arm not in {"off", "rules", "context_mode"}):
            raise ValueError("Profiles require unique safe names and a supported runtime arm")
        names.add(name)
        policy, mode = validate_options(
            variant.get("result_policy", config.get("result_policy", "rules-v1")),
            variant.get("task_state_projection", config.get("task_state_projection", "full") if arm == "rules" else "off"))
        result.append({"name": name, "arm": arm, "result_policy": policy, "task_state_projection": mode})
    return result


def prepare_plan(config, tasks, *, repeats=1, parallel=1):
    if type(repeats) is not int or repeats < 1 or type(parallel) is not int or not 1 <= parallel <= 8:
        raise ValueError("repeats must be positive; parallel must be between 1 and 8")
    if not tasks or len(set(tasks)) != len(tasks):
        raise ValueError("Tasks must be nonempty and unique")
    profiles = resolve_profiles(config)
    jobs = [{"task": task, "repeat": repeat, "profile": profile["name"]}
            for task in tasks for repeat in range(repeats) for profile in profiles]
    random.Random(731).shuffle(jobs)
    return {"seed": 731, "repeats": repeats, "parallel": parallel, "cases": list(tasks),
            "profiles": profiles, "arms": [p["name"] for p in profiles], "jobs": jobs,
            "planned_runs": len(jobs), "model_calls_executed": 0, "executed": False,
            "model": config.get("model"), "base_url": config.get("base_url")}
