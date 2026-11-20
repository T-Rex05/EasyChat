"""memory 数据访问：单一 SQLite 记忆模型、版本、反馈、遗忘规则与幂等信号。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Iterable

from backend.modules.memory.contracts import (
    MemoryCandidate,
    MemoryRecord,
    SourceRef,
    STATUS_ACTIVE,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import ConflictError, ForbiddenError, NotFoundError
from backend.shared.identifiers import new_memory_id, new_revision_id, new_signal_id


def _sources(raw: str) -> tuple[SourceRef, ...]:
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return ()
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not item.get("ref"):
            continue
        out.append(SourceRef(
            kind=str(item.get("kind") or "message"),
            ref=str(item["ref"]),
            quote=str(item.get("quote") or ""),
        ))
    return tuple(out)


def dump_sources(refs: Iterable[SourceRef]) -> str:
    return json.dumps(
        [{"kind": r.kind, "ref": r.ref, "quote": r.quote} for r in refs],
        ensure_ascii=False,
    )


def _memory(row: Any, tags: tuple[str, ...] = ()) -> MemoryRecord:
    d = dict(row)
    return MemoryRecord(
        memory_id=str(d["id"]),
        owner_id=int(d["owner_id"]),
        kind=str(d["kind"]),
        content=str(d["content"]),
        source_refs=_sources(str(d["source_refs"] or "[]")),
        scope=str(d["scope"]),
        event_at=d.get("event_at"),
        recorded_at=str(d["recorded_at"]),
        version=int(d["version"]),
        status=str(d["status"]),
        pinned=bool(d["pinned"]),
        confidence=float(d["confidence"]),
        source_type=str(d["source_type"]),
        tags=tags,
        created_at=str(d["created_at"]),
        updated_at=str(d["updated_at"]),
        persona_id=d["persona_id"],
        is_shared=bool(d["is_shared"]),
        supersedes=d["supersedes"],
    )


def _visibility(persona_id: str | None, all_personas: bool, shared_only: bool = False):
    if shared_only:
        return " AND is_shared=1", ()
    if all_personas:
        return "", ()
    clause = " AND (persona_id IS ? OR is_shared=1)"
    if persona_id is None:
        return clause, (None,)
    return clause + (
        " AND EXISTS (SELECT 1 FROM persona_catalog p "
        "WHERE p.id=? AND p.owner_id=memories.owner_id AND p.active=1)"
    ), (persona_id, persona_id)


def _forget_hashes(content: str, refs: tuple[SourceRef, ...]) -> set[tuple[str, str]]:
    rules = {("source_ref", source_hash(ref.ref)) for ref in refs if ref.ref}
    if content.strip():
        rules.add(("content", content_hash(content)))
    return rules


def _visible_memory(
    conn: sqlite3.Connection, owner_id: int, memory_id: str,
    *, persona_id: str | None, all_personas: bool,
) -> sqlite3.Row:
    clause, args = _visibility(persona_id, all_personas)
    rows = conn.execute(
        "SELECT * FROM memories WHERE owner_id=? AND id GLOB ? AND status!='deleted'"
        + clause + " ORDER BY id LIMIT 2",
        (owner_id, memory_id + "*", *args),
    ).fetchall()
    if not rows:
        raise NotFoundError("记忆不存在或不可见")
    if len(rows) > 1:
        raise ConflictError("匹配多条记忆，请提供更长的 ID 前缀")
    return rows[0]


def _with_tags(conn: sqlite3.Connection, row: sqlite3.Row) -> MemoryRecord:
    tags = tuple(r["tag"] for r in conn.execute(
        "SELECT tag FROM memory_tags WHERE memory_id=? ORDER BY tag", (row["id"],)
    ))
    return _memory(row, tags)


def _has_forget_rule(conn: sqlite3.Connection, owner_id: int, kind: str, digest: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM forget_rules WHERE owner_id=? AND target_kind=? AND target_hash=?",
        (owner_id, kind, digest),
    ).fetchone() is not None


def _assert_not_forgotten(
    conn: sqlite3.Connection, owner_id: int, content: str, refs: tuple[SourceRef, ...],
) -> None:
    if any(_has_forget_rule(conn, owner_id, kind, digest) for kind, digest in _forget_hashes(content, refs)):
        raise ForbiddenError("该内容或来源已被遗忘，不能重新写入")


def _signal_rules(payload: dict[str, Any], source_event_id: str) -> set[tuple[str, str]]:
    refs = _sources(json.dumps(payload.get("source_refs")))
    rules = _forget_hashes(str(payload.get("content") or ""), refs)
    if query := payload.get("query"):
        rules.add(("content", content_hash(str(query))))
    if source_ref := payload.get("source_ref"):
        rules.add(("source_ref", source_hash(str(source_ref))))
    if memory_id := payload.get("memory_id"):
        rules.add(("memory", source_hash(str(memory_id))))
    rules.add(("source_ref", source_hash(source_event_id)))
    return rules


class MemoryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- 写入 ------------------------------------------------------------------

    def create_memory(
        self, *, owner_id: int, candidate: MemoryCandidate, status: str = STATUS_ACTIVE,
        persona_id: str | None = None, is_shared: bool = False, deduplicate: bool = False,
    ) -> MemoryRecord:
        memory_id = new_memory_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            if persona_id is not None:
                self.require_active_persona(conn, owner_id, persona_id)
            _assert_not_forgotten(conn, owner_id, candidate.content, candidate.source_refs)
            if deduplicate:
                existing = conn.execute(
                    "SELECT * FROM memories WHERE owner_id=? AND kind=? AND content=? "
                    "AND status='active' AND persona_id IS ? AND is_shared=? LIMIT 1",
                    (owner_id, candidate.kind, candidate.content, persona_id, int(is_shared)),
                ).fetchone()
                if existing is not None:
                    return _with_tags(conn, existing)
            if candidate.supersedes:
                updated = conn.execute(
                    "UPDATE memories SET status='archived', updated_at=? "
                    "WHERE id=? AND owner_id=? AND status!='deleted' AND persona_id IS ? AND is_shared=?",
                    (now, candidate.supersedes, owner_id, persona_id, int(is_shared)),
                )
                if updated.rowcount != 1:
                    raise NotFoundError("被取代的记忆不存在")
            conn.execute(
                "INSERT INTO memories(id, owner_id, kind, content, source_refs, scope, event_at, "
                "recorded_at, version, status, pinned, confidence, source_type, supersedes, "
                "created_at, updated_at, persona_id, is_shared) VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?)",
                (
                    memory_id, owner_id, candidate.kind, candidate.content,
                    dump_sources(candidate.source_refs), candidate.scope,
                    candidate.event_at, now, status, 1 if candidate.pinned else 0,
                    float(candidate.confidence), candidate.source_type,
                    candidate.supersedes, now, now, persona_id, int(is_shared),
                ),
            )
            conn.execute(
                "INSERT INTO memory_revisions(id, memory_id, version, content, reason, "
                "source_refs, actor, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (new_revision_id(), memory_id, 1, candidate.content, "created",
                 dump_sources(candidate.source_refs), "system", now),
            )
            for tag in sorted(set(candidate.tags)):
                if tag.strip():
                    conn.execute(
                        "INSERT INTO memory_tags(memory_id, tag) VALUES(?,?) "
                        "ON CONFLICT(memory_id, tag) DO NOTHING",
                        (memory_id, tag.strip()[:60]),
                    )
            return _with_tags(conn, conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone())

    def revise(
        self,
        *,
        memory_id: str,
        owner_id: int,
        expected_version: int,
        content: str,
        source_refs: tuple[SourceRef, ...],
        reason: str,
        actor: str = "user",
    ) -> MemoryRecord:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id=? AND owner_id=?", (memory_id, owner_id)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"记忆不存在: {memory_id}")
            return self._revise(conn, row, expected_version, content, source_refs, reason, actor)

    def revise_from_channel(
        self, *, owner_id: int, memory_id: str, persona_id: str | None, event_id: str,
        expected_version: int, content: str,
    ) -> tuple[str, int]:
        with self.db.transaction() as conn:
            receipt = self._channel_revision_receipt(conn, owner_id, event_id, persona_id)
            if receipt is not None:
                return receipt
            row = _visible_memory(conn, owner_id, memory_id, persona_id=persona_id, all_personas=False)
            revised = self._revise(
                conn, row, expected_version, content, (), "微信纠正", "wechat",
                new_source=SourceRef(kind="channel_event", ref=event_id),
            )
            conn.execute(
                "INSERT INTO memory_channel_operations "
                "(owner_id, channel_event_id, action, memory_id, result_version) "
                "VALUES(?,?,'revise',?,?)",
                (owner_id, event_id, revised.memory_id, revised.version),
            )
            return revised.memory_id, revised.version

    def channel_revision_receipt(
        self, *, owner_id: int, event_id: str, persona_id: str | None,
    ) -> tuple[str, int] | None:
        with self.db.transaction(immediate=False) as conn:
            return self._channel_revision_receipt(conn, owner_id, event_id, persona_id)

    @staticmethod
    def _channel_revision_receipt(
        conn: sqlite3.Connection, owner_id: int, event_id: str, persona_id: str | None,
    ) -> tuple[str, int] | None:
        receipt = conn.execute(
            "SELECT memory_id, result_version FROM memory_channel_operations "
            "WHERE owner_id=? AND channel_event_id=? AND action='revise'",
            (owner_id, event_id),
        ).fetchone()
        if receipt is None:
            return None
        _visible_memory(conn, owner_id, receipt["memory_id"], persona_id=persona_id, all_personas=False)
        return receipt["memory_id"], receipt["result_version"]

    @staticmethod
    def _revise(
        conn: sqlite3.Connection, row: sqlite3.Row, expected_version: int,
        content: str, source_refs: tuple[SourceRef, ...], reason: str, actor: str,
        *, new_source: SourceRef | None = None,
    ) -> MemoryRecord:
        if row["status"] == "deleted":
            raise ConflictError("已遗忘的记忆不能修改")
        if row["version"] != expected_version:
            raise ConflictError(
                f"记忆版本已变化（期望 {expected_version}，当前 {row['version']}）"
            )
        refs = source_refs or _sources(row["source_refs"])
        if new_source is not None:
            refs = (*refs, new_source)
        _assert_not_forgotten(conn, row["owner_id"], content, (new_source,) if new_source else source_refs)
        new_version = expected_version + 1
        now = utc_now_iso()
        encoded_refs = dump_sources(refs)
        cur = conn.execute(
            "UPDATE memories SET content=?, source_refs=?, version=?, updated_at=? "
            "WHERE id=? AND owner_id=? AND version=?",
            (content, encoded_refs, new_version, now, row["id"], row["owner_id"], expected_version),
        )
        if cur.rowcount != 1:
            raise ConflictError("记忆版本并发更新失败")
        conn.execute(
            "INSERT INTO memory_revisions(id, memory_id, version, content, reason, "
            "source_refs, actor, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (new_revision_id(), row["id"], new_version, content, reason[:200], encoded_refs, actor, now),
        )
        return _with_tags(conn, conn.execute("SELECT * FROM memories WHERE id=?", (row["id"],)).fetchone())

    def set_sharing(self, *, owner_id: int, memory_id: str, is_shared: bool) -> MemoryRecord:
        with self.db.transaction() as conn:
            row = _visible_memory(conn, owner_id, memory_id, persona_id=None, all_personas=True)
            conn.execute(
                "UPDATE memories SET is_shared=?, updated_at=? WHERE id=? AND owner_id=?",
                (int(is_shared), utc_now_iso(), row["id"], owner_id),
            )
            return _with_tags(conn, conn.execute("SELECT * FROM memories WHERE id=?", (row["id"],)).fetchone())

    def add_feedback(
        self, *, owner_id: int, memory_id: str, source_event_id: str, signal: str, note: str = ""
    ) -> bool:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM memories WHERE id=? AND owner_id=? AND status!='deleted'", (memory_id, owner_id)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"记忆不存在: {memory_id}")
            cur = conn.execute(
                "INSERT INTO memory_feedback(id, owner_id, memory_id, source_event_id, signal, "
                "note, created_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(memory_id, source_event_id) DO NOTHING",
                (new_signal_id(), owner_id, memory_id, source_event_id, signal,
                 note[:200], utc_now_iso()),
            )
            return cur.rowcount == 1

    @staticmethod
    def require_active_persona(conn: sqlite3.Connection, owner_id: int, persona_id: str) -> None:
        if not conn.execute(
            "SELECT 1 FROM persona_catalog WHERE owner_id=? AND id=? AND active=1",
            (owner_id, persona_id),
        ).fetchone():
            raise NotFoundError("角色不存在或已停用")

    # ---- 读取 ------------------------------------------------------------------

    def get(self, memory_id: str) -> MemoryRecord:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"记忆不存在: {memory_id}")
            return _with_tags(conn, row)
        finally:
            conn.close()

    def get_visible(
        self, owner_id: int, memory_id: str, *, persona_id: str | None, all_personas: bool,
    ) -> MemoryRecord:
        with self.db.transaction(immediate=False) as conn:
            return _with_tags(conn, _visible_memory(
                conn, owner_id, memory_id, persona_id=persona_id, all_personas=all_personas,
            ))

    def candidates(
        self, owner_id: int, *, include_archived: bool, limit: int = 80, persona_id: str | None = None,
    ) -> list[MemoryRecord]:
        statuses = (STATUS_ACTIVE, "archived") if include_archived else (STATUS_ACTIVE,)
        return self.list_for_owner(
            owner_id, statuses=statuses, limit=limit, persona_id=persona_id, all_personas=False,
        )

    def set_status(self, memory_id: str, status: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE memories SET status=?, updated_at=? WHERE id=?",
                (status, utc_now_iso(), memory_id),
            )

    def list_for_owner(
        self, owner_id: int, *, statuses: tuple[str, ...] = (STATUS_ACTIVE,), limit: int = 50,
        persona_id: str | None = None, all_personas: bool = True, shared_only: bool = False,
        query: str = "", exact_scope: bool = False,
    ) -> list[MemoryRecord]:
        placeholders = ",".join("?" * len(statuses))
        if exact_scope and not all_personas and not shared_only:
            clause, args = " AND persona_id IS ? AND is_shared=0", (persona_id,)
        else:
            clause, args = _visibility(persona_id, all_personas, shared_only)
        if query:
            clause += (
                " AND (instr(lower(content), ?) > 0 OR instr(id, ?) > 0 OR EXISTS ("
                "SELECT 1 FROM memory_tags WHERE memory_id=memories.id AND instr(lower(tag), ?) > 0))"
            )
            term = query.strip().lower()
            args = (*args, term, term, term)
        with self.db.transaction(immediate=False) as conn:
            rows = conn.execute(
                f"SELECT * FROM memories WHERE owner_id=? AND status IN ({placeholders})"
                + clause + " ORDER BY recorded_at DESC, id LIMIT ?",
                (owner_id, *statuses, *args, limit),
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            tags: dict[str, list[str]] = {memory_id: [] for memory_id in ids}
            if ids:
                for row in conn.execute(
                    f"SELECT memory_id, tag FROM memory_tags WHERE memory_id IN "
                    f"({','.join('?' * len(ids))}) ORDER BY tag",
                    ids,
                ):
                    tags[row["memory_id"]].append(row["tag"])
            return [_memory(row, tuple(tags[row["id"]])) for row in rows]

    def revisions(self, memory_id: str) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM memory_revisions WHERE memory_id=? ORDER BY version", (memory_id,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def visible_revisions(
        self, owner_id: int, memory_id: str, *, persona_id: str | None, all_personas: bool,
        limit: int, offset: int,
    ) -> list[dict[str, Any]]:
        with self.db.transaction(immediate=False) as conn:
            row = _visible_memory(conn, owner_id, memory_id, persona_id=persona_id, all_personas=all_personas)
            return [
                dict(revision, source_refs=json.loads(dump_sources(_sources(revision["source_refs"]))))
                for revision in conn.execute(
                    "SELECT * FROM memory_revisions WHERE memory_id=? ORDER BY version LIMIT ? OFFSET ?",
                    (row["id"], limit, offset),
                )
            ]

    # ---- 遗忘 ------------------------------------------------------------------

    def forget_memories(
        self, *, owner_id: int, memory_id: str, source_ref: str, query: str,
        persona_id: str | None, all_personas: bool,
    ) -> tuple[str, ...]:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            if memory_id:
                clause, args = _visibility(persona_id, all_personas)
                deleted = conn.execute(
                    "SELECT 1 FROM memories WHERE owner_id=? AND id=? AND status='deleted'" + clause,
                    (owner_id, memory_id, *args),
                ).fetchone()
                if deleted:
                    return ()
                row = _visible_memory(conn, owner_id, memory_id, persona_id=persona_id, all_personas=all_personas)
                rows = [row]
                rules = {("memory", source_hash(row["id"]))}
            else:
                clause, args = _visibility(persona_id, all_personas)
                rows = conn.execute(
                    "SELECT * FROM memories WHERE owner_id=? AND status!='deleted'" + clause,
                    (owner_id, *args),
                ).fetchall()
                rules = (
                    {("source_ref", source_hash(source_ref))}
                    if source_ref else {("content", content_hash(query))}
                )

            affected = []
            for row in rows:
                if query and query not in row["content"].lower():
                    continue
                target = row["id"]
                revisions = conn.execute(
                    "SELECT content, source_refs FROM memory_revisions WHERE memory_id=?", (target,),
                ).fetchall()
                content_and_sources = [
                    (snapshot["content"], _sources(snapshot["source_refs"]))
                    for snapshot in (row, *revisions)
                ]
                if source_ref and not any(
                    ref.ref == source_ref for _, refs in content_and_sources for ref in refs
                ):
                    continue
                for content, refs in content_and_sources:
                    rules.update(_forget_hashes(content, refs))
                conn.execute(
                    "UPDATE memories SET content='', source_refs='[]', scope='user', event_at=NULL, "
                    "supersedes=NULL, status='deleted', version=version+1, updated_at=? WHERE id=?",
                    (now, target),
                )
                conn.execute("UPDATE memories SET supersedes=NULL WHERE owner_id=? AND supersedes=?", (owner_id, target))
                conn.execute("DELETE FROM memory_revisions WHERE memory_id=?", (target,))
                conn.execute("DELETE FROM memory_tags WHERE memory_id=?", (target,))
                conn.execute("DELETE FROM memory_feedback WHERE memory_id=?", (target,))
                affected.append(target)
            conn.executemany(
                "INSERT INTO forget_rules(id, owner_id, target_kind, target_hash, created_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(owner_id, target_kind, target_hash) DO NOTHING",
                ((new_signal_id(), owner_id, kind, digest, now) for kind, digest in sorted(rules)),
            )
            self._scrub_signals(conn, owner_id, set(affected), rules)
            self._scrub_confirmations(conn, owner_id, set(affected), rules)
            return tuple(affected)

    def source_is_forgotten(self, owner_id: int, source_ref: str) -> bool:
        conn = self.db.connect()
        try:
            return _has_forget_rule(conn, owner_id, "source_ref", source_hash(source_ref))
        finally:
            conn.close()

    @staticmethod
    def _scrub_confirmations(conn, owner_id: int, affected: set[str], rules: set[tuple[str, str]]) -> None:
        from backend.modules.delivery.api import DeliveryService

        rows = conn.execute(
            "SELECT id, json_extract(payload, '$.memory_id') AS memory_id, "
            "json_extract(payload, '$.run_id') AS run_id FROM jobs "
            "WHERE owner_id=? AND kind='memory.confirm' AND payload!='{}' AND json_valid(payload)",
            (owner_id,),
        ).fetchall()
        matching = [
            row for row in rows
            if row["memory_id"] in affected
            or (row["run_id"] and ("source_ref", source_hash(row["run_id"])) in rules)
        ]
        conn.executemany(
            "UPDATE jobs SET payload='{}', last_error=NULL, updated_at=? WHERE id=?",
            ((utc_now_iso(), row["id"]) for row in matching),
        )
        DeliveryService.cancel_memory_confirmations_in_transaction(
            conn, owner_id, {row["run_id"] for row in matching if row["run_id"]},
        )

    @staticmethod
    def _scrub_signals(conn, owner_id: int, affected: set[str], rules: set[tuple[str, str]]) -> None:
        for row in conn.execute(
            "SELECT id, source_event_id, payload FROM memory_signals WHERE owner_id=? AND payload!='{}'",
            (owner_id,),
        ).fetchall():
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            related = _signal_rules(payload, row["source_event_id"])
            if str(payload.get("memory_id")) in affected or not related.isdisjoint(rules):
                conn.execute(
                    "UPDATE memory_signals SET payload='{}', error='', "
                    "state=CASE WHEN state IN ('processed','rejected') THEN state ELSE 'rejected' END WHERE id=?",
                    (row["id"],),
                )

    # ---- 信号 ------------------------------------------------------------------

    def insert_signal(
        self, *, owner_id: int, source_event_id: str, signal: str, payload: dict[str, Any]
    ) -> tuple[str, bool, str]:
        signal_id = new_signal_id()
        with self.db.transaction() as conn:
            target = str(payload.get("memory_id") or "")
            deleted = target and conn.execute(
                "SELECT 1 FROM memories WHERE owner_id=? AND id=? AND status='deleted'",
                (owner_id, target),
            ).fetchone()
            blocked = deleted or any(
                _has_forget_rule(conn, owner_id, kind, digest)
                for kind, digest in _signal_rules(payload, source_event_id)
            )
            state = "rejected" if blocked else "pending"
            cur = conn.execute(
                "INSERT INTO memory_signals(id, owner_id, source_event_id, signal, payload, state, "
                "created_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(owner_id, source_event_id) DO NOTHING",
                (signal_id, owner_id, source_event_id, signal,
                 "{}" if blocked else json.dumps(payload, ensure_ascii=False), state, utc_now_iso()),
            )
            if cur.rowcount == 1:
                return signal_id, True, state
            row = conn.execute(
                "SELECT id, state FROM memory_signals WHERE owner_id=? AND source_event_id=?",
                (owner_id, source_event_id),
            ).fetchone()
            return str(row["id"]), False, str(row["state"])

    def get_signal(self, signal_id: str) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM memory_signals WHERE id=?", (signal_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"记忆信号不存在: {signal_id}")
            return dict(row)
        finally:
            conn.close()

    def mark_signal(self, signal_id: str, *, state: str, error: str = "") -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE memory_signals SET state=?, error=?, processed_at=? WHERE id=? AND state!='rejected'",
                (state, error[:500], utc_now_iso(), signal_id),
            )



def content_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode("utf-8")).hexdigest()


def source_hash(ref: str) -> str:
    return hashlib.sha256(str(ref).encode("utf-8")).hexdigest()
