"""memory 数据访问：单一 SQLite 记忆模型、版本、反馈、遗忘规则与幂等信号。"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from backend.modules.memory.contracts import (
    MemoryCandidate,
    MemoryRecord,
    SourceRef,
    STATUS_ACTIVE,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import ConflictError, NotFoundError
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
    )


class MemoryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- 写入 ------------------------------------------------------------------

    def create_memory(
        self, *, owner_id: int, candidate: MemoryCandidate, status: str = STATUS_ACTIVE
    ) -> MemoryRecord:
        memory_id = new_memory_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO memories(id, owner_id, kind, content, source_refs, scope, event_at, "
                "recorded_at, version, status, pinned, confidence, source_type, supersedes, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?)",
                (
                    memory_id, owner_id, candidate.kind, candidate.content,
                    dump_sources(candidate.source_refs), candidate.scope,
                    candidate.event_at, now, status, 1 if candidate.pinned else 0,
                    float(candidate.confidence), candidate.source_type,
                    candidate.supersedes, now, now,
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
        return self.get(memory_id)

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
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id=? AND owner_id=?", (memory_id, owner_id)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"记忆不存在: {memory_id}")
            if str(row["status"]) == "deleted":
                raise ConflictError("已遗忘的记忆不能修改")
            if int(row["version"]) != int(expected_version):
                raise ConflictError(
                    f"记忆版本已变化（期望 {expected_version}，当前 {row['version']}）"
                )
            new_version = int(row["version"]) + 1
            cur = conn.execute(
                "UPDATE memories SET content=?, source_refs=?, version=?, updated_at=? "
                "WHERE id=? AND owner_id=? AND version=?",
                (content, dump_sources(source_refs), new_version, now,
                 memory_id, owner_id, expected_version),
            )
            if cur.rowcount != 1:
                raise ConflictError("记忆版本并发更新失败")
            conn.execute(
                "INSERT INTO memory_revisions(id, memory_id, version, content, reason, "
                "source_refs, actor, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (new_revision_id(), memory_id, new_version, content, reason[:200],
                 dump_sources(source_refs), actor, now),
            )
        return self.get(memory_id)

    def add_feedback(
        self, *, owner_id: int, memory_id: str, source_event_id: str, signal: str, note: str = ""
    ) -> bool:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM memories WHERE id=? AND owner_id=?", (memory_id, owner_id)
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

    # ---- 读取 ------------------------------------------------------------------

    def get(self, memory_id: str) -> MemoryRecord:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"记忆不存在: {memory_id}")
            tags = tuple(
                str(r["tag"]) for r in conn.execute(
                    "SELECT tag FROM memory_tags WHERE memory_id=? ORDER BY tag", (memory_id,)
                ).fetchall()
            )
            return _memory(row, tags)
        finally:
            conn.close()

    def candidates(
        self, owner_id: int, *, include_archived: bool, limit: int = 80
    ) -> list[MemoryRecord]:
        statuses = (STATUS_ACTIVE, "archived") if include_archived else (STATUS_ACTIVE,)
        placeholders = ",".join("?" * len(statuses))
        conn = self.db.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM memories WHERE owner_id=? AND status IN ({placeholders}) "
                "ORDER BY recorded_at DESC LIMIT ?",
                (owner_id, *statuses, limit),
            ).fetchall()
            ids = [str(r["id"]) for r in rows]
            tags: dict[str, list[str]] = {i: [] for i in ids}
            if ids:
                for trow in conn.execute(
                    f"SELECT memory_id, tag FROM memory_tags WHERE memory_id IN "
                    f"({','.join('?' * len(ids))})",
                    ids,
                ).fetchall():
                    tags[str(trow["memory_id"])].append(str(trow["tag"]))
            return [_memory(r, tuple(sorted(tags.get(str(r["id"]), [])))) for r in rows]
        finally:
            conn.close()

    def find_active_content(self, owner_id: int, kind: str, content: str) -> MemoryRecord | None:
        """同 owner/kind/正文的 active 记忆视为重复写入，返回既有记录。"""
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM memories WHERE owner_id=? AND kind=? AND content=? "
                "AND status='active' LIMIT 1",
                (owner_id, kind, content),
            ).fetchone()
            return _memory(row) if row else None
        finally:
            conn.close()

    def set_status(self, memory_id: str, status: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE memories SET status=?, updated_at=? WHERE id=?",
                (status, utc_now_iso(), memory_id),
            )

    def list_for_owner(
        self, owner_id: int, *, statuses: tuple[str, ...] = (STATUS_ACTIVE,), limit: int = 50
    ) -> list[MemoryRecord]:
        placeholders = ",".join("?" * len(statuses))
        conn = self.db.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM memories WHERE owner_id=? AND status IN ({placeholders}) "
                "ORDER BY recorded_at DESC LIMIT ?",
                (owner_id, *statuses, limit),
            ).fetchall()
            return [_memory(r) for r in rows]
        finally:
            conn.close()

    def revisions(self, memory_id: str) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM memory_revisions WHERE memory_id=? ORDER BY version", (memory_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 遗忘 ------------------------------------------------------------------

    def find_forget_rule(self, owner_id: int, target_kind: str, target_hash: str) -> bool:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT id FROM forget_rules WHERE owner_id=? AND target_kind=? AND target_hash=?",
                (owner_id, target_kind, target_hash),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def forget_memories(
        self,
        *,
        owner_id: int,
        memory_ids: list[str],
        target_kind: str,
        target_hash: str,
        reason: str,
    ) -> int:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            count = 0
            for memory_id in memory_ids:
                row = conn.execute(
                    "SELECT id, version FROM memories WHERE id=? AND owner_id=? AND status!='deleted'",
                    (memory_id, owner_id),
                ).fetchone()
                if row is None:
                    continue
                # 墓碑不保留原文：内容清空并删除所有历史版本
                conn.execute(
                    "UPDATE memories SET content='', status='deleted', version=version+1, "
                    "updated_at=? WHERE id=? AND owner_id=?",
                    (now, memory_id, owner_id),
                )
                conn.execute("DELETE FROM memory_revisions WHERE memory_id=?", (memory_id,))
                count += 1
            conn.execute(
                "INSERT INTO forget_rules(id, owner_id, target_kind, target_hash, reason, created_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(owner_id, target_kind, target_hash) DO NOTHING",
                (new_signal_id(), owner_id, target_kind, target_hash, reason[:200], now),
            )
            return count

    # ---- 信号 ------------------------------------------------------------------

    def insert_signal(
        self, *, owner_id: int, source_event_id: str, signal: str, payload: dict[str, Any]
    ) -> tuple[str, bool, str]:
        signal_id = new_signal_id()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO memory_signals(id, owner_id, source_event_id, signal, payload, state, "
                "created_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(owner_id, source_event_id) DO NOTHING",
                (signal_id, owner_id, source_event_id, signal,
                 json.dumps(payload, ensure_ascii=False), "pending", utc_now_iso()),
            )
            if cur.rowcount == 1:
                return signal_id, True, "pending"
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
                "UPDATE memory_signals SET state=?, error=?, processed_at=? WHERE id=?",
                (state, error[:500], utc_now_iso(), signal_id),
            )

    def purge_deleted_content(self) -> int:
        """兜底：清掉已删除记忆仍残留的内容/版本（正常情况下 forget 已处理）。"""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE memories SET content='' WHERE status='deleted' AND content != ''"
            )
            conn.execute(
                "DELETE FROM memory_revisions WHERE memory_id IN "
                "(SELECT id FROM memories WHERE status='deleted')"
            )
            return int(cur.rowcount)


def content_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode("utf-8")).hexdigest()


def source_hash(ref: str) -> str:
    return hashlib.sha256(str(ref).encode("utf-8")).hexdigest()
