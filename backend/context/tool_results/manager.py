"""Choose bounded model views while retaining exact source values and originals."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from .types import ResultScope
from .options import validate_options

logger = logging.getLogger(__name__)
RECOVERY_TOOLS = frozenset({"context_read", "context_search"})
_EXACT_KEYS = frozenset({
    "id", "path", "file", "filename", "version", "status", "success", "error", "error_code",
    "code", "timestamp", "amount", "currency", "unit", "count", "total", "url",
})


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _protected_key(key: str) -> bool:
    key = key.lower()
    return key in _EXACT_KEYS or key.endswith(("_id", "_path", "_version", "_code"))


def extract_protected(content: str) -> tuple[list[dict], bool]:
    """Copy scalars with JSON Pointer provenance; no semantic inference or rewrites."""
    facts: list[dict] = []
    try:
        data = json.loads(content)
    except (ValueError, RecursionError):
        # Line-oriented receipts/logs. Keep the exact text after the delimiter.
        for line_number, line in enumerate(content.splitlines(), 1):
            match = re.match(r"^\s{0,8}([\w.-]+)\s*[:=]\s*(.*)$", line)
            if match and _protected_key(match[1]):
                facts.append({"pointer": f"line:{line_number}", "key": match[1], "value": match[2]})
                if len(facts) == 512:
                    return facts, True
        return facts, False
    stack = [("", data)]
    visited = 0
    while stack:
        pointer, value = stack.pop()
        visited += 1
        if visited > 50000 or len(facts) >= 512:
            return facts, True
        if isinstance(value, dict):
            for key, item in value.items():
                escaped = key.replace("~", "~0").replace("/", "~1")
                location = pointer + "/" + escaped
                if _protected_key(key) and isinstance(item, (str, int, float, bool, type(None))):
                    facts.append({"pointer": location, "key": key, "value": item})
                    if len(facts) >= 512:
                        return facts, True
                elif isinstance(item, (dict, list)):
                    stack.append((location, item))
        elif isinstance(value, list):
            stack.extend((pointer + "/" + str(i), item) for i, item in reversed(list(enumerate(value))))
    return facts, False


@dataclass
class PreparedResult:
    content: Any
    managed: bool = False
    scope: ResultScope | None = None
    artifact_id: str | None = None
    source_hash: str | None = None
    action: str = "legacy"
    protected: list[dict] = field(default_factory=list)
    raw_complete: bool = True
    max_chars: int = 8000
    expires_at: float | None = None
    omitted_protected_fields: int = 0
    failure: str | None = None
    view_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tool_name: str = ""
    task_state_version: int = 0
    evidence_protected: list[dict] = field(default_factory=list)
    evidence_scan_partial: bool = False
    presented_other_fields: int = 0
    omitted_other_fields: int | None = 0
    other_field_scan_partial: bool = False


class ResultManager:
    """The store and rule policy are deliberately independent of the Hermes runtime."""

    def __init__(self, store, max_view_chars=8000, *, policy="rules-v1"):
        self.policy, _ = validate_options(policy)
        self.store = store
        self.max_view_chars = max(256, min(16000, int(max_view_chars)))

    def prepare(self, scope, tool_name, raw_result, max_chars=8000, capture=None) -> PreparedResult:
        budget = min(self.max_view_chars, max(0, int(max_chars)))
        if not isinstance(raw_result, str):
            return PreparedResult(raw_result, scope=scope, max_chars=budget)
        if tool_name in RECOVERY_TOOLS:
            # Recovery already has a page budget. Do not create an artifact of an artifact.
            return PreparedResult(raw_result, managed=True, scope=scope, action="recovery", max_chars=budget)
        raw = raw_result
        complete = True
        if capture is not None:
            try:
                execution = json.loads(raw_result)
            except ValueError:
                execution = raw_result
            complete = capture.raw_complete
            raw = _dump({
                "execution_result": execution, "captured_output": capture.content,
                "capture": {"attempt_id": capture.attempt_id, "raw_complete": complete,
                            "captured_bytes": capture.captured_bytes, "dropped_bytes": capture.dropped_bytes,
                            "closed_reason": capture.closed_reason},
            })
        try:
            saved = self.store.put(scope, raw, tool_name=tool_name, raw_complete=complete)
            if saved.get("status") != "ok":
                raise OSError(saved.get("status", "store unavailable"))
        except Exception as exc:
            logger.warning("Tool-result archive unavailable (%s); preserving legacy result", type(exc).__name__)
            return PreparedResult(raw_result, scope=scope, max_chars=budget, failure="archive_unavailable")
        all_archived = saved["captured_bytes"] == saved["original_bytes"]
        if not all_archived:
            # Never select evidence from a tail that cannot be recovered from this artifact.
            raw = raw.encode("utf-8")[:saved["captured_bytes"]].decode("utf-8")
        facts, partial = extract_protected(raw)
        if capture is not None and all_archived:
            captured_facts, capture_partial = extract_protected(capture.content)
            facts.extend({**item, "source": "captured_output"} for item in captured_facts)
            partial = partial or capture_partial
        complete = bool(saved["raw_complete"])
        prepared = PreparedResult(
            raw_result, True, scope, saved["artifact_id"], saved["source_hash"], "keep", facts,
            complete, budget, saved.get("expires_at"),
        )
        prepared.evidence_protected = facts
        prepared.evidence_scan_partial = partial
        # The CodeMode result envelope may have been cropped before it reached us.
        # Show a bounded view of the archived capture, with status/error fields intact.
        if len(raw_result) <= budget and capture is None and complete:
            retained = []
            for fact in facts:
                if len(_dump(retained + [fact])) <= 4000:
                    retained.append(fact)
            prepared.protected = retained
            prepared.omitted_protected_fields = len(facts) - len(retained)
            return prepared
        body = {
            "artifact_id": saved["artifact_id"], "raw_complete": complete,
            "action": "extract", "protected": [], "omitted_protected_fields": len(facts),
            "field_scan_partial": partial, "read_with": "context_read", "preview": "",
        }
        extras, total_other = [], 0
        if self.policy == "conservative-v1":
            from .selection import other_fields
            extras, total_other, scan_status = other_fields(raw, _protected_key)
            if capture is not None and all_archived:
                captured, captured_count, captured_status = other_fields(capture.content, _protected_key)
                extras.extend({**item, "source": "captured_output"} for item in captured)
                total_other = total_other + captured_count if total_other is not None and captured_count is not None else None
                if captured_status != "ok":
                    scan_status = captured_status
            body.update(other_fields=[], omitted_other_fields=total_other,
                        other_field_scan_partial=scan_status != "ok", other_field_scan_status=scan_status)
            prepared.other_field_scan_partial = scan_status != "ok"
        kept = []
        # Reserve room for context around the selected facts, never shorten field values.
        field_budget = max(0, budget - min(600, budget // 4))
        for fact in facts:
            trial = {**body, "protected": kept + [fact], "omitted_protected_fields": len(facts) - len(kept) - 1}
            if len(_dump(trial)) <= field_budget:
                kept.append(fact)
        body["protected"] = kept
        body["omitted_protected_fields"] = len(facts) - len(kept)
        if self.policy == "conservative-v1":
            selected = []
            for fact in extras:
                omitted = total_other - len(selected) - 1 if total_other is not None else None
                trial = {**body, "other_fields": selected + [fact], "omitted_other_fields": omitted}
                if len(_dump(trial)) <= field_budget:
                    selected.append(fact)
            body.update(other_fields=selected,
                        omitted_other_fields=total_other - len(selected) if total_other is not None else None)
            prepared.presented_other_fields = len(selected)
            prepared.omitted_other_fields = body["omitted_other_fields"]
        prepared.protected = kept
        prepared.omitted_protected_fields = len(facts) - len(kept)
        # Binary-search the escaped JSON budget, including all metadata overhead.
        low, high = 0, min(len(raw), budget)
        while low < high:
            mid = (low + high + 1) // 2
            head = mid * 2 // 3
            preview = raw[:head] + ("\n…\n" + raw[-(mid - head):] if mid > head else "")
            if len(_dump({**body, "preview": preview})) <= budget:
                low = mid
            else:
                high = mid - 1
        if low:
            head = low * 2 // 3
            body["preview"] = raw[:head] + ("\n…\n" + raw[-(low - head):] if low > head else "")
        prepared.content = _dump(body)
        prepared.action = "extract"
        if len(prepared.content) > budget:
            prepared.presented_other_fields = 0
            prepared.omitted_other_fields = total_other
            prepared.protected = []
            prepared.action = "pointer"
            prepared.content = _dump({"artifact_id": saved["artifact_id"], "status": "budget_pressure"})
            if len(prepared.content) > budget:
                # Runtime tickets normally reserve metadata space; explicit no-room result otherwise.
                prepared.content = "budget_pressure"[:budget]
        return prepared

    def seal(self, prepared: PreparedResult, canonical_content: Any) -> dict:
        if not prepared.managed:
            return {}
        serialized = canonical_content if isinstance(canonical_content, str) else _dump(canonical_content)
        metadata = {
            "managed": True, "artifact_id": prepared.artifact_id, "view_id": prepared.view_id,
            "source_hash": prepared.source_hash, "canonical_hash": hashlib.sha256(serialized.encode()).hexdigest(),
            "action": prepared.action, "raw_complete": prepared.raw_complete, "protected": prepared.protected,
            "omitted_protected_fields": prepared.omitted_protected_fields, "expires_at": prepared.expires_at,
            "presented_chars": len(serialized), "policy_version": self.policy,
            "task_state_version": prepared.task_state_version,
        }
        if self.policy == "conservative-v1":
            metadata.update(presented_other_fields=prepared.presented_other_fields,
                            omitted_other_fields=prepared.omitted_other_fields,
                            other_field_scan_partial=prepared.other_field_scan_partial)
        if prepared.artifact_id:
            try:
                self.store.persist_view(prepared.scope, prepared.artifact_id, prepared.view_id,
                                        serialized, metadata)
            except Exception as exc:
                # The original is still durable; failure to save a view is separate from tool execution.
                metadata["view_persistence"] = "unavailable"
                logger.warning("Tool-result view persistence failed (%s)", type(exc).__name__)
        return metadata
