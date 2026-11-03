"""Protect managed results from legacy pruning; no active history-folding policy."""
from __future__ import annotations

import copy
import json

_MANIFEST_KEY = "context_result_manifest"


def _metadata(message):
    metadata = message.get("display_metadata")
    return metadata.get("context_result", {}) if isinstance(metadata, dict) else {}


def _manifest(messages, max_chars=8000):
    records = {}
    for message in messages:
        existing = message.get("display_metadata", {}).get(_MANIFEST_KEY, [])
        for record in existing:
            if record.get("artifact_id"):
                records[record["artifact_id"]] = record
        metadata = _metadata(message)
        if metadata.get("managed") and metadata.get("artifact_id"):
            records[metadata["artifact_id"]] = {
                key: metadata[key] for key in
                ("artifact_id", "view_id", "source_hash", "raw_complete", "protected", "expires_at")
                if key in metadata
            }
    selected = []
    # A bounded, newest-first inventory. Older originals remain discoverable via scoped search.
    for record in reversed(list(records.values())):
        trial = selected + [record]
        if len(json.dumps(trial, ensure_ascii=False)) > max_chars:
            record = {key: value for key, value in record.items() if key != "protected"}
            record["fields_omitted"] = True
            trial = selected + [record]
        if len(json.dumps(trial, ensure_ascii=False)) > max_chars:
            break
        selected = trial
    return selected, len(records) - len(selected)


class ManagedResultsCompressor:
    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        if name == "_inner":
            object.__setattr__(self, name, value)
        else:
            # Hermes mutates counters/flags on its configured compressor directly.
            # Forward to the state-owning engine even through a FactAnchor proxy.
            target = self._inner
            while "_inner" in vars(target) and name not in vars(target) and not hasattr(type(target), name):
                target = vars(target)["_inner"]
            setattr(target, name, value)

    def record_completed_compaction(self, *args, **kwargs):
        # Hermes probes this on type(compressor), so __getattr__ alone is insufficient.
        method = getattr(self._inner, "record_completed_compaction", None)
        return method(*args, **kwargs) if method is not None else None

    def prune_tool_results_only(self, messages, *args, **kwargs):
        protected = {message.get("tool_call_id"): copy.deepcopy(message) for message in messages
                     if message.get("role") == "tool" and _metadata(message).get("managed")}
        if not protected:
            return self._inner.prune_tool_results_only(messages, *args, **kwargs)
        result, _ = self._inner.prune_tool_results_only(copy.deepcopy(messages), *args, **kwargs)
        # Native pruning keeps rows and pairing. Restore canonical managed rows exactly.
        result = [protected.get(message.get("tool_call_id"), message)
                  if message.get("role") == "tool" else message for message in result]
        if result == messages:
            return messages, 0
        changed = sum(before != after for before, after in zip(messages, result)) + abs(len(messages) - len(result))
        return result, changed

    def compress(self, messages, current_tokens=None, focus_topic=None, force=False, memory_context=""):
        records, omitted = _manifest(messages)
        if not records:
            return self._inner.compress(messages, current_tokens=current_tokens, focus_topic=focus_topic,
                                        force=force, memory_context=memory_context)
        payload = {"untrusted_tool_evidence": records, "older_artifacts_omitted": omitted,
                   "recovery_tools": ["context_read", "context_search"]}
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        working = copy.deepcopy(messages)
        compressed = self._inner.compress(
            working, current_tokens=current_tokens, focus_topic=focus_topic, force=force,
            memory_context=(memory_context + "\n" + serialized).strip(),
        )
        if compressed == messages:
            return messages
        if not compressed:
            return compressed
        protected = {msg.get("tool_call_id"): msg for msg in messages
                     if msg.get("role") == "tool" and _metadata(msg).get("managed")}
        result = [copy.deepcopy(protected.get(msg.get("tool_call_id"), msg))
                  if msg.get("role") == "tool" else copy.deepcopy(msg) for msg in compressed]
        # This is a machine-generated context summary, not a new user instruction.
        result.append({"role": "assistant", "content": serialized,
                       "display_metadata": {_MANIFEST_KEY: records}})
        return result


def install_compression_guard(agent):
    compressor = getattr(agent, "context_compressor", None)
    if compressor is not None and not isinstance(compressor, ManagedResultsCompressor):
        agent.context_compressor = ManagedResultsCompressor(compressor)
