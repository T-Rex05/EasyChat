"""Validated, frozen per-run policy choices shared with offline experiment profiles."""
import os

RESULT_POLICIES = frozenset({"rules-v1", "conservative-v1"})
PROJECTION_MODES = frozenset({"full", "delta", "off"})


def validate_options(result_policy="rules-v1", projection_mode="full"):
    if (not isinstance(result_policy, str) or not isinstance(projection_mode, str)
            or result_policy not in RESULT_POLICIES or projection_mode not in PROJECTION_MODES):
        raise ValueError("Unknown result policy or TaskState projection mode")
    return result_policy, projection_mode


def runtime_options(result_policy=None, projection_mode=None):
    return validate_options(
        result_policy if result_policy is not None else os.getenv("AGENTFORGE_CONTEXT_POLICY", "rules-v1"),
        projection_mode if projection_mode is not None else os.getenv("AGENTFORGE_TASK_STATE_PROJECTION", "full"))
