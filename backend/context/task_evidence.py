"""Bounded synchronous evidence ledger. Semantic/LLM updates never write this table."""
import copy
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class EvidenceLedger:
    def __init__(self, path, *, max_results=64, max_bytes=65536, ttl_seconds=86400, clock=time.time):
        if max_results < 1 or max_bytes < 1024 or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("Invalid evidence limits")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_results, self.max_bytes, self.ttl = max_results, max_bytes, ttl_seconds
        self.clock = clock
        with self._connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS task_evidence(
                user_id TEXT, thread_id TEXT, agent_id TEXT, state TEXT, updated_at REAL,
                PRIMARY KEY(user_id,thread_id,agent_id))""")

    def _connection(self):
        # Context manager below commits/rolls back and closes every connection.
        return _Transaction(self.path)

    @staticmethod
    def _key(scope):
        return (scope.user_id, scope.thread_id, scope.agent_id)

    def _load(self, conn, scope):
        row = conn.execute("SELECT state FROM task_evidence WHERE user_id=? AND thread_id=? AND agent_id=?",
                           self._key(scope)).fetchone()
        if row:
            state = json.loads(row[0])
            state.setdefault("generation", "legacy")
            return state
        return {"version": 0, "results": [], "batches": [], "evicted_results": 0, "generation": "empty"}

    def commit_batch(self, scope, batch_id, events):
        if not batch_id or len(batch_id) > 256:
            raise ValueError("Invalid batch identity")
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = self._load(conn, scope)
            if batch_id in state["batches"]:
                return
            if state["generation"] in {"empty", "legacy"}:
                state["generation"] = uuid.uuid4().hex
            now = self.clock()
            retained = [row for row in state["results"] if now - row["observed_at"] <= self.ttl]
            state["evicted_results"] += len(state["results"]) - len(retained)
            known = {row["event_id"] for row in retained}
            for event in events:
                call = event.get("tool_call_id")
                if not isinstance(call, str) or not call or len(call) > 512:
                    raise ValueError("Evidence needs a trusted tool-call ID")
                event_id = _encode([scope.run_id, call, event.get("attempt_id", "1")])
                if event_id in known:
                    continue
                known.add(event_id)
                facts, omitted = [], int(event.get("omitted_protected_fields", 0))
                for fact in event.get("protected", [])[:512]:
                    if not isinstance(fact, dict) or not isinstance(fact.get("pointer"), str):
                        continue
                    clean = {k: fact[k] for k in ("pointer", "key", "value", "source") if k in fact}
                    try:
                        size = len(_encode(clean).encode())
                    except (ValueError, TypeError):
                        omitted += 1
                        continue
                    if size > 4096 or len(_encode(facts + [clean]).encode()) > 12000:
                        omitted += 1
                        continue
                    facts.append(clean)
                record = {
                    "event_id": event_id, "run_id": scope.run_id, "tool_call_id": call,
                    "attempt_id": event.get("attempt_id", "1"), "batch_id": batch_id,
                    "tool_name": str(event.get("tool_name", ""))[:256], "observed_at": now,
                    "artifact_id": event.get("artifact_id"), "source_hash": event.get("source_hash"),
                    "view_id": event.get("view_id"), "raw_complete": event.get("raw_complete", False),
                    "expires_at": event.get("expires_at"), "protected": facts,
                    "omitted_protected_fields": omitted,
                    "extraction_partial": bool(event.get("extraction_partial", False)),
                }
                if len(_encode(record).encode()) > self.max_bytes:
                    record["omitted_protected_fields"] += len(facts)
                    record["protected"] = []
                retained.append(record)
            while retained and (len(retained) > self.max_results or len(_encode(retained).encode()) > self.max_bytes):
                retained.pop(0)
                state["evicted_results"] += 1
            state.update(results=retained, version=state["version"] + 1,
                         batches=(state["batches"] + [batch_id])[-128:])
            conn.execute("DELETE FROM task_evidence WHERE updated_at < ?", (now - self.ttl,))
            count = conn.execute("SELECT COUNT(*) FROM task_evidence").fetchone()[0]
            exists = conn.execute("SELECT 1 FROM task_evidence WHERE user_id=? AND thread_id=? AND agent_id=?",
                                  self._key(scope)).fetchone()
            if count >= 500 and not exists:
                raise RuntimeError("Evidence partition quota exceeded")
            conn.execute("INSERT OR REPLACE INTO task_evidence VALUES(?,?,?,?,?)",
                         (*self._key(scope), _encode(state), now))

    def snapshot(self, scope):
        with self._connection() as conn:
            state = self._load(conn, scope)
        now = self.clock()
        rows = [row for row in state["results"] if now - row["observed_at"] <= self.ttl]
        values = {}
        for row in rows:
            row["source_expired"] = row.get("expires_at") is not None and row["expires_at"] <= now
            for fact in row["protected"]:
                key = fact.get("key", fact["pointer"])
                values.setdefault(key, set()).add(_encode(fact.get("value")))
        return copy.deepcopy({
            "generation": state["generation"],
            "version": state["version"], "results": rows,
            "evicted_results": state["evicted_results"] + len(state["results"]) - len(rows),
            "conflicts": [{"key": key, "kind": "multiple_observed_values", "values": [json.loads(v) for v in sorted(entries)]}
                          for key, entries in sorted(values.items()) if len(entries) > 1],
        })

    def clear(self, scope):
        with self._connection() as conn:
            conn.execute("DELETE FROM task_evidence WHERE user_id=? AND thread_id=? AND agent_id=?", self._key(scope))


class _Transaction:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        return self.conn

    def __exit__(self, kind, value, tb):
        try:
            self.conn.rollback() if kind else self.conn.commit()
        finally:
            self.conn.close()
