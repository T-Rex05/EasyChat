"""History-anchored evidence projections; no hidden cursor survives compaction."""
import json

_ROW_FIELDS = frozenset({
    "artifact_id", "source_hash", "tool_call_id", "tool_name", "observed_at", "protected",
    "expires_at", "source_expired", "raw_complete", "omitted_protected_fields", "extraction_partial",
})


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _chain(history, scope):
    chain = []
    for message in history or []:
        meta = message.get("display_metadata", {}).get("task_state_snapshot", {})
        if not meta or any(meta.get(key) != getattr(scope, key) for key in ("user_id", "thread_id", "agent_id")):
            continue
        try:
            body = json.loads(message["content"])
            if (message.get("role") != "assistant" or not isinstance(body.get("untrusted_task_evidence"), list)
                    or type(meta.get("version")) is not int or body.get("evidence_version") != meta["version"]):
                raise ValueError("Invalid projection anchor")
            mode = meta.get("projection_mode", "full")
            if mode == "full":
                chain = [body]
            elif (mode == "delta" and chain and body.get("base_version") == chain[-1]["evidence_version"]
                  and body["evidence_version"] >= chain[-1]["evidence_version"]
                  and body.get("ledger_generation") == chain[-1].get("ledger_generation")):
                chain.append(body)
            else:
                chain = []
        except (ValueError, TypeError, KeyError, AttributeError):
            chain = []
    return chain


def evidence_message(snapshot, scope, *, mode="full", history=None, max_chars=4000):
    if mode == "off" or max_chars < 512:
        return None
    evidence = snapshot["tool_evidence"]
    rows = [{key: value for key, value in row.items() if key in _ROW_FIELDS} for row in evidence["results"]]
    chain = _chain(history, scope) if mode == "delta" else []
    generation = evidence.get("generation", "legacy")
    reset = bool(chain and (chain[-1].get("ledger_generation") != generation
                           or evidence["version"] < chain[-1]["evidence_version"]))
    if reset:
        chain = []
    unchanged = 0
    if chain:
        seen = {_encode(row) for body in chain for row in body["untrusted_task_evidence"]
                if isinstance(row, dict) and not row.get("fields_omitted")}
        eligible = [row for row in rows if _encode(row) not in seen]
        unchanged = len(rows) - len(eligible)
        last = chain[-1]
        if (not eligible and last.get("sync_error") == snapshot["evidence_sync_error"]
                and last.get("evicted_results") == evidence["evicted_results"]):
            return None
        rows = eligible
    elif not rows and not snapshot["evidence_sync_error"] and not reset:
        return None
    body = {"untrusted_task_evidence": [], "evidence_version": evidence["version"],
            "omitted_results": len(rows), "evicted_results": evidence["evicted_results"],
            "sync_error": snapshot["evidence_sync_error"]}
    actual_mode = "delta" if chain else "full"
    if mode == "delta":
        body["ledger_generation"] = generation
    if reset:
        body["ledger_reset"] = True
    if chain:
        body.update(base_version=chain[-1]["evidence_version"], unchanged_results=unchanged)
    for row in reversed(rows):
        candidate = {**body, "untrusted_task_evidence": body["untrusted_task_evidence"] + [row],
                     "omitted_results": body["omitted_results"] - 1}
        if len(json.dumps(candidate, ensure_ascii=False)) > max_chars:
            omitted = row.get("omitted_protected_fields", 0) + len(row.get("protected", []))
            row = {key: value for key, value in row.items() if key != "protected"}
            row.update(fields_omitted=True, omitted_protected_fields=omitted)
            candidate["untrusted_task_evidence"] = body["untrusted_task_evidence"] + [row]
        if len(json.dumps(candidate, ensure_ascii=False)) > max_chars:
            break
        body = candidate
    content = json.dumps(body, ensure_ascii=False)
    if len(content) > max_chars:
        return None
    return {"role": "assistant", "content": content,
            "display_metadata": {"task_state_snapshot": {
                "user_id": scope.user_id, "thread_id": scope.thread_id, "agent_id": scope.agent_id,
                "version": evidence["version"], "projection_mode": actual_mode, "projection_strategy": mode}}}
