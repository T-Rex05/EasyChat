"""收件箱 SQL（owner 隔离在每条查询的 WHERE 中）。"""
from __future__ import annotations

import json
from typing import Any

from backend.modules.inbox.contracts import InboxItem
from backend.platform.sqlite import Database, utc_now_iso

_COLUMNS = (
    "id, owner_id, kind, title, url, file_id, note, summary, tags_json, status, "
    "enrich_state, source_run_id, created_at, updated_at"
)


def _view(row: Any) -> InboxItem:
    return InboxItem(
        item_id=str(row["id"]),
        owner_id=int(row["owner_id"]),
        kind=str(row["kind"]),
        title=str(row["title"]),
        url=str(row["url"]),
        file_id=str(row["file_id"]),
        note=str(row["note"]),
        summary=str(row["summary"]),
        tags=tuple(json.loads(row["tags_json"] or "[]")),
        status=str(row["status"]),
        enrich_state=str(row["enrich_state"]),
        source_run_id=str(row["source_run_id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class InboxRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, owner_id: int, item_id: str) -> InboxItem | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM inbox_items WHERE owner_id=? AND id=?",
                (owner_id, item_id),
            ).fetchone()
            return _view(row) if row else None
        finally:
            conn.close()

    def get_by_url(self, owner_id: int, url: str) -> InboxItem | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM inbox_items WHERE owner_id=? AND url=?",
                (owner_id, url),
            ).fetchone()
            return _view(row) if row else None
        finally:
            conn.close()

    def insert(
        self, owner_id: int, *, item_id: str, kind: str, title: str, url: str,
        file_id: str, note: str, tags: tuple[str, ...], status: str,
        enrich_state: str, source_run_id: str,
    ) -> InboxItem:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                f"INSERT INTO inbox_items({_COLUMNS}) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item_id, owner_id, kind, title[:200], url, file_id, note[:2000], "",
                    json.dumps(list(tags), ensure_ascii=False), status, enrich_state,
                    source_run_id, now, now,
                ),
            )
        return self.get(owner_id, item_id)

    def update(self, owner_id: int, item_id: str, **fields: Any) -> InboxItem:
        allowed = {"title", "note", "tags_json", "summary", "status", "enrich_state"}
        values = {k: v for k, v in fields.items() if k in allowed}
        if values:
            values["updated_at"] = utc_now_iso()
            assignments = ", ".join(f"{key}=?" for key in values)
            with self.db.transaction() as conn:
                conn.execute(
                    f"UPDATE inbox_items SET {assignments} WHERE owner_id=? AND id=?",
                    (*values.values(), owner_id, item_id),
                )
        item = self.get(owner_id, item_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def list(self, owner_id: int, *, status: str = "", limit: int = 20) -> list[InboxItem]:
        limit = max(1, min(int(limit), 100))
        conn = self.db.connect()
        try:
            if status:
                rows = conn.execute(
                    f"SELECT {_COLUMNS} FROM inbox_items WHERE owner_id=? AND status=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (owner_id, status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {_COLUMNS} FROM inbox_items WHERE owner_id=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (owner_id, limit),
                ).fetchall()
            return [_view(row) for row in rows]
        finally:
            conn.close()

    def search(self, owner_id: int, query: str, limit: int = 5) -> list[InboxItem]:
        raw = query[:100].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{raw}%"
        conn = self.db.connect()
        try:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM inbox_items WHERE owner_id=? AND ("
                "title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' "
                "OR note LIKE ? ESCAPE '\\' OR tags_json LIKE ? ESCAPE '\\') "
                "ORDER BY updated_at DESC LIMIT ?",
                (owner_id, like, like, like, like, max(1, min(limit, 20))),
            ).fetchall()
            return [_view(row) for row in rows]
        finally:
            conn.close()

    def unread_count(self, owner_id: int) -> int:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM inbox_items WHERE owner_id=? AND status='unread'",
                (owner_id,),
            ).fetchone()
            return int(row["n"])
        finally:
            conn.close()

    def delete(self, owner_id: int, item_id: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM inbox_items WHERE owner_id=? AND id=?", (owner_id, item_id)
            )
            return cursor.rowcount > 0
