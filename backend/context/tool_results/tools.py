"""Model-visible recovery tools; identity and budgets are never model arguments."""
from __future__ import annotations

import json

from langchain_core.tools import tool

from .runtime import active_tool


def _encode(result):
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _compact_search_structure(result, *, omit=False):
    for match in result.get("matches", []):
        neighbors = match.get("neighbors", [])
        if neighbors:
            match["neighbors_omitted"] += len(neighbors)
            match["neighbors"] = []
        if omit and "json_pointer" in match:
            for key in ("json_pointer", "parent_pointer", "json_type", "neighbors", "neighbors_omitted"):
                match.pop(key, None)
            match["json_location_status"] = "budget_omitted"


def _bounded_call(operation, requested):
    active = active_tool()
    if active is None:
        return _encode({"status": "unavailable", "reason": "No authenticated result scope"})
    budget = min(max(0, active.max_chars), max(0, int(requested)), 16000)
    if budget < 256:
        return _encode({"status": "budget_pressure"}) if budget >= 28 else "{}"[:budget]
    # Include envelope/escaped content in the actual budget, not just the payload.
    payload_budget = max(1, budget - 512)
    for _ in range(12):
        result = operation(active, payload_budget)
        encoded = _encode(result)
        if len(encoded) > budget and "matches" in result:
            # Preserve complete selectors before sacrificing literal snippet size.
            _compact_search_structure(result, omit=payload_budget < 64)
            encoded = _encode(result)
        if len(encoded) <= budget:
            return encoded
        payload_budget //= 2
        if payload_budget < 1:
            break
    return _encode({"status": "budget_pressure", "reason": "Retry with a larger tool budget"})


@tool
def context_read(artifact_id: str, start_line: int = 1, end_line: int | None = None,
                 json_pointer: str | None = None, cursor: str | None = None, max_chars: int = 8000) -> str:
    """Read a saved tool result by artifact ID. Use line ranges or an exact JSON Pointer.

    Follow next_cursor for subsequent pages. Original text may be incomplete or expired;
    inspect status/raw_complete. This tool never reexecutes the original business action.
    """
    return _bounded_call(
        lambda active, budget: active.runtime.manager.store.read(
            active.scope, artifact_id, start_line=start_line, end_line=end_line,
            json_pointer=json_pointer, cursor=cursor, max_chars=budget), max_chars,
    )


@tool
def context_search(query: str, artifact_ids: list[str] | None = None, max_chars: int = 8000) -> str:
    """Search accessible saved tool outputs for literal terms and source positions.

    JSON key/scalar matches may include json_pointer, parent_pointer and bounded
    neighbor pointers/types. Pass json_pointer (including the empty root pointer)
    directly to context_read. Check json_location_status and neighbors_omitted;
    invalid/ambiguous/oversized JSON or tight budgets fall back to source lines.
    This searches literal source text, not decoded strings or embedded JSON.
    Searches are restricted to the authenticated conversation and logical agent.
    """
    return _bounded_call(
        lambda active, budget: active.runtime.manager.store.search(
            active.scope, query, artifact_ids=artifact_ids, max_chars=budget,
            max_structure_chars=min(max(0, active.max_chars - 256), max(0, max_chars - 256))), max_chars,
    )
