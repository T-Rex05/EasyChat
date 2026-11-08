"""assistant 的只读消息投影。

记忆模块需要读取 run 的最终投影，但不应依赖 AssistantRepository；这里提供
一个稳定、无状态的读取函数。写入口仍只属于 assistant。
"""
from __future__ import annotations

from typing import Any

from backend.platform.sqlite import Database


def load_run_messages(
    db: Database, owner_id: int, run_id: str
) -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT role, content, source, created_at FROM conversations "
            "WHERE owner_id=? AND run_id=? ORDER BY id",
            (owner_id, run_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
