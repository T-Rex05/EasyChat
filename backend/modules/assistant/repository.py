"""assistant 模块数据访问：sessions/runs/conversations 写入口。

run 状态机（架构 §5.3）：queued → running → completed/failed/cancelled/interrupted；
running 可先进入 cancel_requested。只有本模块推进状态，更新以旧状态为条件。
"""
from __future__ import annotations

import json
from typing import Any, Callable

from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import InvalidInputError, NotFoundError
from backend.shared.identifiers import new_session_id

RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_CANCEL_REQUESTED = "cancel_requested"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"
RUN_INTERRUPTED = "interrupted"

# 合法状态迁移（条件更新的来源状态集合）
_TRANSITIONS: dict[str, frozenset[str]] = {
    RUN_RUNNING: frozenset({RUN_QUEUED, RUN_CANCEL_REQUESTED}),
    RUN_CANCEL_REQUESTED: frozenset({RUN_RUNNING, RUN_QUEUED}),
    RUN_COMPLETED: frozenset({RUN_RUNNING, RUN_CANCEL_REQUESTED}),
    RUN_FAILED: frozenset({RUN_RUNNING, RUN_CANCEL_REQUESTED}),
    RUN_CANCELLED: frozenset({RUN_QUEUED, RUN_RUNNING, RUN_CANCEL_REQUESTED}),
    RUN_INTERRUPTED: frozenset({RUN_RUNNING, RUN_CANCEL_REQUESTED, RUN_QUEUED}),
}


def normalize_channel_scope(channel_account_id: str | None) -> str:
    """可空渠道账号规范化为非空 scope（Web 用空串，架构 §5.2）。"""
    return channel_account_id or ""


class AssistantRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- sessions ---------------------------------------------------------------

    def create_session(self, *, owner_id: int, source: str = "web",
                       channel_account_id: str = "", external_chat_id: str = "",
                       title: str = "") -> str:
        sid = new_session_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO sessions(id, owner_id, title, source, channel_account_id, "
                "external_chat_id, active, created_at, updated_at) VALUES(?,?,?,?,?,?,1,?,?)",
                (sid, owner_id, title, source, channel_account_id, external_chat_id, now, now),
            )
        return sid

    def get_session(self, session_id: str, owner_id: int | None = None) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            if owner_id is None:
                row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE id=? AND owner_id=?", (session_id, owner_id)
                ).fetchone()
            if row is None:
                raise NotFoundError(f"会话不存在: {session_id}")
            return dict(row)
        finally:
            conn.close()

    def find_session_by_external_chat(
        self,
        owner_id: int,
        external_chat_id: str,
        *,
        source: str | None = None,
        channel_account_id: str | None = None,
    ) -> dict[str, Any] | None:
        """按可信 owner + 外部会话标识解析会话。

        source/channel_account_id 用于渠道隔离：两个机器人账号下的同一 openid
        不共享会话；Web 不传渠道账号（规范为空串）。
        """
        sql = "SELECT * FROM sessions WHERE owner_id=? AND external_chat_id=? AND active=1"
        params: list[Any] = [owner_id, external_chat_id]
        if source is not None:
            sql += " AND source=?"
            params.append(source)
        if channel_account_id is not None:
            sql += " AND channel_account_id=?"
            params.append(normalize_channel_scope(channel_account_id))
        sql += " ORDER BY created_at DESC LIMIT 1"
        conn = self.db.connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ---- 附件（用户附件元信息归 assistant；大内容只存文件路径） ------------------

    def create_attachment(
        self,
        *,
        owner_id: int,
        file_name: str,
        file_path: str,
        file_size: int,
        mime: str,
        sha256: str,
        session_id: str = "",
        run_id: str | None = None,
        file_type: int = 0,
    ) -> str:
        from backend.shared.identifiers import new_attachment_id

        attachment_id = new_attachment_id()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO attachments(id, owner_id, session_id, run_id, file_name, file_path, "
                "file_size, mime, file_type, sha256, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (attachment_id, owner_id, session_id, run_id, file_name, file_path,
                 int(file_size), mime, int(file_type), sha256, utc_now_iso()),
            )
        return attachment_id

    def get_attachment(self, attachment_id: str, *, owner_id: int) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM attachments WHERE id=? AND owner_id=?", (attachment_id, owner_id)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"附件不存在: {attachment_id}")
            return dict(row)
        finally:
            conn.close()

    def list_sessions(self, owner_id: int, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT id, owner_id, title, source, channel_account_id, external_chat_id, "
                "active, created_at, updated_at FROM sessions "
                "WHERE owner_id=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (owner_id, limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- runs -------------------------------------------------------------------

    def create_run(self, *, owner_id: int, session_id: str, source: str,
                   channel_account_scope: str, client_message_id: str,
                   input_summary: str, attachment_ids: list[str]) -> tuple[str, bool]:
        """创建 run；同幂等键返回已存在 run（duplicate=True），不重跑。"""
        from backend.shared.identifiers import new_run_id

        now = utc_now_iso()
        run_id = new_run_id()
        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM runs WHERE owner_id=? AND session_id=? AND source=? "
                "AND channel_account_scope=? AND client_message_id=?",
                (owner_id, session_id, source, channel_account_scope, client_message_id),
            ).fetchone()
            if existing is not None:
                return str(existing["id"]), True
            conn.execute(
                "INSERT INTO runs(id, owner_id, session_id, source, channel_account_scope, "
                "client_message_id, status, input_summary, attachment_ids, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (run_id, owner_id, session_id, source, channel_account_scope, client_message_id,
                 RUN_QUEUED, input_summary[:500], json.dumps(attachment_ids), now),
            )
            return run_id, False

    def get_run(self, run_id: str) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"run 不存在: {run_id}")
            return dict(row)
        finally:
            conn.close()

    def transition_run(self, run_id: str, *, to_status: str, **sets: Any) -> bool:
        """条件状态推进：以合法旧状态为条件，cancelled 不得被 completed 覆盖。"""
        allowed = _TRANSITIONS.get(to_status)
        if allowed is None:
            raise InvalidInputError(f"未知目标状态: {to_status}")
        now = utc_now_iso()
        with self.db.transaction() as conn:
            sets_full = dict(sets)
            if to_status in (RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED, RUN_INTERRUPTED):
                sets_full["finished_at"] = now
            if to_status == RUN_RUNNING:
                sets_full["started_at"] = now
            set_items = ["status=?"] + [f"{k}=?" for k in sets_full] + ["updated_at=?"]
            params = [to_status, *[sets_full[k] for k in sets_full], now]
            cur = conn.execute(
                f"UPDATE runs SET {', '.join(set_items)} "
                f"WHERE id=? AND status IN ({','.join('?' * len(allowed))})",
                [*params, run_id, *allowed],
            )
            if cur.rowcount != 1:
                return False
            return True

    def request_cancel(self, run_id: str) -> str:
        """请求取消：queued→cancelled 直接取消；running→cancel_requested。"""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"run 不存在: {run_id}")
            status = str(row["status"])
        if status in (RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED, RUN_INTERRUPTED):
            return status  # 已终态：幂等，不再变更
        if status == RUN_QUEUED:
            self.transition_run(run_id, to_status=RUN_CANCELLED)
            return RUN_CANCELLED
        if self.transition_run(run_id, to_status=RUN_CANCEL_REQUESTED):
            return RUN_CANCEL_REQUESTED
        return status

    # ---- 投影与终态（同事务） -------------------------------------------------------

    def finish_run_with_projection(
        self,
        run_id: str,
        *,
        to_status: str,
        final_content: str,
        error: str | None = None,
        artifact_refs: list[str] | None = None,
        on_finish: Callable[[Any, dict[str, Any]], None] | None = None,
    ) -> bool:
        """终态推进 + UI 投影 + 注入回调（投递/学习 job）在同一 app.db 事务提交。

        on_finish(conn, run_row) 由 bootstrap 注入（如 evolution 入队）；
        投影失败/回调失败会回滚终态推进，run 保持 running 待对账（interrupted）。
        """
        run = self.get_run(run_id)
        now = utc_now_iso()
        try:
            with self.db.transaction() as conn:
                allowed = _TRANSITIONS[to_status]
                cur = conn.execute(
                    f"UPDATE runs SET status=?, finished_at=?, error=?, artifact_refs=?, updated_at=? "
                    f"WHERE id=? AND status IN ({','.join('?' * len(allowed))})",
                    (to_status, now, error, json.dumps(artifact_refs or []), now, run_id, *allowed),
                )
                if cur.rowcount != 1:
                    return False
                # UI 投影（conversations = 展示投影，非第二套模型历史）
                conn.execute(
                    "INSERT INTO conversations(session_id, owner_id, run_id, role, content, status, "
                    "chat_mode, source, seq, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,1,'normal',?,0,?,?)",
                    (run["session_id"], run["owner_id"], run_id, "assistant",
                     final_content, run["source"], now, now),
                )
                if on_finish is not None:
                    on_finish(conn, run)
                return True
        except Exception:
            # 投影失败：run 保持原状态，重启对账标 interrupted（架构 §5.3 双库恢复）
            raise
