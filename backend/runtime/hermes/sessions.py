"""会话映射与引擎历史恢复（架构 §5.1）。

app.db 的 sessions 表持有 (owner_id, app_session_id) → hermes_session_id
显式映射；state.db 是引擎消息历史权威。压缩会轮换 session_id，归属集合
须并集容忍旧 id。UI 投影（conversations 表）不作为第二套模型历史。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.platform.sqlite import Database
from backend.shared.errors import NotFoundError, StorageUnavailableError


class SessionMapper:
    def __init__(self, db: Database, *, hermes_home: Path) -> None:
        self.db = db
        self.hermes_home = Path(hermes_home)

    # ---- app.db 映射 -----------------------------------------------------------

    def bind(self, session_id: str, hermes_session_id: str) -> None:
        """登记/更新 app 会话 → 引擎会话映射。"""
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET hermes_session_id=?, updated_at=datetime('now') WHERE id=?",
                (hermes_session_id, session_id),
            )

    def resolve(self, owner_id: int, session_id: str) -> str | None:
        """读取归属该 owner 的引擎会话 ID（归属校验在 SQL 条件内）。"""
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT hermes_session_id FROM sessions WHERE id=? AND owner_id=?",
                (session_id, owner_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"会话不存在或不属于该用户: {session_id}")
            value = row["hermes_session_id"]
            return value if value else None
        finally:
            conn.close()

    # ---- state.db 引擎历史 -------------------------------------------------------

    def _open_session_db(self):
        from backend.runtime.hermes.paths import ensure_hermes_environment

        ensure_hermes_environment(self.hermes_home)
        from hermes_state import SessionDB  # noqa: PLC0415  (Hermes 顶层模块)

        return SessionDB(db_path=self.hermes_home / "state.db")

    def recover_conversation(self, hermes_session_id: str) -> list[dict[str, Any]]:
        """从 state.db 恢复引擎会话消息（含压缩旧 id 解析）。

        返回 [{role, content}, ...]；只读，不写入 UI 投影。
        """
        if not hermes_session_id:
            return []
        try:
            db = self._open_session_db()
        except Exception as exc:  # noqa: BLE001  引擎历史不可用不阻塞新会话
            raise StorageUnavailableError(f"state.db 不可用: {exc}") from exc
        try:
            resolved = db.resolve_session_id(hermes_session_id)
            if not resolved:
                return []
            messages = db.get_messages_as_conversation(resolved, repair_alternation=True)
            return [
                {"role": str(m.get("role")), "content": str(m.get("content") or "")}
                for m in messages
                if m.get("role") in ("user", "assistant")
            ]
        finally:
            db.close()

    def session_id_candidates(self, hermes_session_id: str) -> tuple[str, ...]:
        """归属判定候选：显式 id 与其压缩后的最新 id。"""
        if not hermes_session_id:
            return ()
        db = self._open_session_db()
        try:
            resolved = db.resolve_session_id(hermes_session_id)
            return (hermes_session_id,) if not resolved else (hermes_session_id, resolved)
        finally:
            db.close()
