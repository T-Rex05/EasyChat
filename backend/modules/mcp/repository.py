"""mcp_servers 表访问层。凭据以 enc:v1: 密文存取（service 层加解密）。"""
from __future__ import annotations

import json
from typing import Any

from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.identifiers import new_mcp_server_id


class McpRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, *, name: str, url: str, credential_enc: str,
               allowed_tools: list[str], excluded_tools: list[str],
               connect_timeout_s: int, call_timeout_s: int,
               audience: str, enabled: bool) -> str:
        server_id = new_mcp_server_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO mcp_servers(id, name, url, credential_enc, allowed_tools,"
                " excluded_tools, connect_timeout_s, call_timeout_s, audience, enabled,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (server_id, name, url, credential_enc,
                 json.dumps(allowed_tools, ensure_ascii=False),
                 json.dumps(excluded_tools, ensure_ascii=False),
                 connect_timeout_s, call_timeout_s, audience,
                 1 if enabled else 0, now, now),
            )
        return server_id

    def get(self, server_id: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM mcp_servers WHERE name=?", (name,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list(self) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM mcp_servers ORDER BY created_at"
            ).fetchall()]
        finally:
            conn.close()

    def update(self, server_id: str, **fields: Any) -> None:
        if not fields:
            return
        keys = [k for k in fields if k != "id"]
        now = utc_now_iso()
        sets = ", ".join(f"{k}=?" for k in keys) + ", updated_at=?"
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE mcp_servers SET {sets} WHERE id=?",
                (*[fields[k] for k in keys], now, server_id),
            )

    def set_check_result(self, server_id: str, *, state: str, error: str,
                         tools: list[str], checked_at: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE mcp_servers SET last_check_state=?, last_check_error=?,"
                " last_check_tools=?, last_checked_at=?, updated_at=?"
                " WHERE id=?",
                (state, error[:300], json.dumps(tools[:200], ensure_ascii=False),
                 checked_at, checked_at, server_id),
            )

    def delete(self, server_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM mcp_servers WHERE id=?", (server_id,))
