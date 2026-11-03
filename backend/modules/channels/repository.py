"""channels 模块数据访问：账号、绑定、接收事件。

表的唯一写入口在本类；路由只调 api.py。事件去重依赖
UNIQUE(platform, account_id, external_event_id)，同一事件只插入一次。
"""
from __future__ import annotations

import json
from typing import Any

from backend.modules.channels.contracts import (
    ACCOUNT_ACTIVE,
    ACCOUNT_DISABLED,
    BINDING_ACTIVE,
    BINDING_DISABLED,
    EVENT_RECEIVED,
    ChannelAccount,
    ChannelBinding,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import ConflictError, NotFoundError
from backend.shared.identifiers import (
    new_channel_account_id,
    new_channel_binding_id,
    new_channel_event_id,
)


def _account_from_row(row: Any, payload: dict[str, Any] | None = None) -> ChannelAccount:
    d = dict(row)
    creds = payload or {}
    return ChannelAccount(
        id=str(d["id"]),
        platform=str(d["platform"]),
        account_id=str(d["account_id"]),
        display_name=str(d["display_name"] or ""),
        status=str(d["status"]),
        base_url=str(creds.get("base_url") or ""),
        bot_user_id=str(d.get("bot_user_id") or ""),
        sync_cursor=str(d.get("sync_cursor") or ""),
        last_poll_at=d.get("last_poll_at"),
        last_error=str(d.get("last_error") or ""),
        has_credentials=bool(d.get("credentials_ref")),
        created_at=str(d["created_at"]),
        updated_at=str(d["updated_at"]),
    )


def _binding_from_row(row: Any) -> ChannelBinding:
    d = dict(row)
    return ChannelBinding(
        id=str(d["id"]),
        platform=str(d["platform"]),
        account_id=str(d["account_id"]),
        external_user_id=str(d["external_user_id"]),
        user_id=int(d["user_id"]),
        status=str(d["status"]),
        created_at=str(d["created_at"]),
        updated_at=str(d["updated_at"]),
    )


class ChannelRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- 账号 ------------------------------------------------------------------

    def upsert_account(
        self,
        *,
        platform: str,
        account_id: str,
        display_name: str = "",
        base_url: str = "",
        bot_user_id: str = "",
        credentials_ref: str = "",
    ) -> ChannelAccount:
        """按 (platform, account_id) 幂等登记；重新扫码只更新凭证与显示信息。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM channel_accounts WHERE platform=? AND account_id=?",
                (platform, account_id),
            ).fetchone()
            if existing is not None:
                pk = str(existing["id"])
                # 重新登记凭证不静默解除管理员的禁用状态；启用需显式 set_account_status。
                conn.execute(
                    "UPDATE channel_accounts SET display_name=?, credentials_ref=?, "
                    "bot_user_id=?, updated_at=? WHERE id=?",
                    (display_name, credentials_ref, bot_user_id, now, pk),
                )
            else:
                pk = new_channel_account_id()
                conn.execute(
                    "INSERT INTO channel_accounts(id, platform, account_id, display_name, status, "
                    "credentials_ref, bot_user_id, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (pk, platform, account_id, display_name, ACCOUNT_ACTIVE, credentials_ref,
                     bot_user_id, now, now),
                )
        account = self.get_account(pk)
        assert account is not None
        if base_url:
            self._set_base_url(pk, base_url)
            account = self.get_account(pk)
        return account

    def _set_base_url(self, account_pk: str, base_url: str) -> None:
        """base_url 存入 credentials_ref JSON 的连接元数据（不单独加冗余列）。"""
        row = self._raw_account(account_pk)
        if row is None:
            return
        payload = _load_credentials(str(row["credentials_ref"] or ""))
        payload["base_url"] = base_url
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE channel_accounts SET credentials_ref=?, updated_at=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), utc_now_iso(), account_pk),
            )

    def _raw_account(self, account_pk: str) -> Any:
        conn = self.db.connect()
        try:
            return conn.execute("SELECT * FROM channel_accounts WHERE id=?", (account_pk,)).fetchone()
        finally:
            conn.close()

    def get_account(self, account_pk: str) -> ChannelAccount | None:
        row = self._raw_account(account_pk)
        if row is None:
            return None
        return _account_from_row(row, _load_credentials(str(row["credentials_ref"] or "")))

    def get_account_by_platform_id(self, platform: str, account_id: str) -> ChannelAccount | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT id FROM channel_accounts WHERE platform=? AND account_id=?",
                (platform, account_id),
            ).fetchone()
        finally:
            conn.close()
        return self.get_account(str(row["id"])) if row else None

    def list_accounts(self) -> list[ChannelAccount]:
        conn = self.db.connect()
        try:
            rows = conn.execute("SELECT id FROM channel_accounts ORDER BY created_at").fetchall()
        finally:
            conn.close()
        return [a for a in (self.get_account(str(r["id"])) for r in rows) if a is not None]

    def set_account_status(self, account_pk: str, status: str) -> None:
        if status not in (ACCOUNT_ACTIVE, ACCOUNT_DISABLED):
            raise ConflictError(f"未知账号状态: {status}")
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE channel_accounts SET status=?, updated_at=? WHERE id=?",
                (status, utc_now_iso(), account_pk),
            )
            if cur.rowcount != 1:
                raise NotFoundError(f"渠道账号不存在: {account_pk}")

    def get_credentials_payload(self, account_pk: str) -> dict[str, Any]:
        row = self._raw_account(account_pk)
        if row is None:
            raise NotFoundError(f"渠道账号不存在: {account_pk}")
        return _load_credentials(str(row["credentials_ref"] or ""))

    def update_poll_state(
        self,
        account_pk: str,
        *,
        cursor: str | None = None,
        last_error: str | None = None,
        polled_at: str | None = None,
    ) -> None:
        """记录真实轮询结果（游标/错误/时间），用于重启恢复与可观测状态。"""
        sets = ["updated_at=?"]
        params: list[Any] = [utc_now_iso()]
        if cursor is not None:
            sets.append("sync_cursor=?")
            params.append(cursor)
        if last_error is not None:
            sets.append("last_error=?")
            params.append(last_error[:500])
        if polled_at is not None:
            sets.append("last_poll_at=?")
            params.append(polled_at)
        params.append(account_pk)
        with self.db.transaction() as conn:
            conn.execute(f"UPDATE channel_accounts SET {', '.join(sets)} WHERE id=?", params)

    # ---- 绑定 ------------------------------------------------------------------

    def upsert_binding(
        self,
        *,
        platform: str,
        account_id: str,
        external_user_id: str,
        user_id: int,
    ) -> ChannelBinding:
        """同一 (platform, account_id, external_user_id) 只保留一条有效绑定。

        重新绑定到另一个用户时直接改 owner 并恢复 active；解绑是 status=disabled，
        保留历史以便审计，不影响下一次消息立即拒绝。
        """
        if not external_user_id:
            raise ConflictError("external_user_id 不能为空")
        now = utc_now_iso()
        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM channel_bindings WHERE platform=? AND account_id=? AND external_user_id=?",
                (platform, account_id, external_user_id),
            ).fetchone()
            if existing is not None:
                binding_id = str(existing["id"])
                conn.execute(
                    "UPDATE channel_bindings SET user_id=?, status=?, updated_at=? WHERE id=?",
                    (user_id, BINDING_ACTIVE, now, binding_id),
                )
            else:
                binding_id = new_channel_binding_id()
                conn.execute(
                    "INSERT INTO channel_bindings(id, platform, account_id, external_user_id, user_id, "
                    "status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (binding_id, platform, account_id, external_user_id, user_id, BINDING_ACTIVE, now, now),
                )
        binding = self.get_binding(binding_id)
        assert binding is not None
        return binding

    def get_binding(self, binding_id: str) -> ChannelBinding | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM channel_bindings WHERE id=?", (binding_id,)).fetchone()
            return _binding_from_row(row) if row else None
        finally:
            conn.close()

    def set_binding_status(self, binding_id: str, status: str) -> None:
        if status not in (BINDING_ACTIVE, BINDING_DISABLED):
            raise ConflictError(f"未知绑定状态: {status}")
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE channel_bindings SET status=?, updated_at=? WHERE id=?",
                (status, utc_now_iso(), binding_id),
            )
            if cur.rowcount != 1:
                raise NotFoundError(f"绑定不存在: {binding_id}")

    def find_active_binding(
        self, platform: str, account_id: str, external_user_id: str
    ) -> tuple[ChannelBinding, dict[str, Any]] | None:
        """返回有效绑定及用户状态；解绑/禁用在下一条消息立即生效。"""
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT b.*, u.username, u.status AS user_status FROM channel_bindings b "
                "JOIN users u ON u.id=b.user_id "
                "WHERE b.platform=? AND b.account_id=? AND b.external_user_id=? AND b.status=?",
                (platform, account_id, external_user_id, BINDING_ACTIVE),
            ).fetchone()
            if row is None:
                return None
            return _binding_from_row(row), {"username": row["username"], "status": int(row["user_status"])}
        finally:
            conn.close()

    def list_bindings(self, owner_id: int | None = None) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            if owner_id is None:
                rows = conn.execute(
                    "SELECT b.*, u.username FROM channel_bindings b "
                    "LEFT JOIN users u ON u.id=b.user_id ORDER BY b.created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT b.*, u.username FROM channel_bindings b "
                    "LEFT JOIN users u ON u.id=b.user_id WHERE b.user_id=? "
                    "ORDER BY b.created_at DESC",
                    (owner_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 接收事件（持久去重） ------------------------------------------------------

    def insert_event(
        self,
        *,
        platform: str,
        account_id: str,
        external_event_id: str,
        event_kind: str,
        payload: dict[str, Any],
        fingerprint: str,
        received_at: str,
    ) -> tuple[str, bool]:
        """插入事件；唯一键冲突返回已存在 id 且 inserted=False（不重复执行）。"""
        event_id = new_channel_event_id()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO channel_events(id, platform, account_id, external_event_id, event_kind, "
                "payload, fingerprint, received_at, state) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(platform, account_id, external_event_id) DO NOTHING",
                (event_id, platform, account_id, external_event_id, event_kind,
                 json.dumps(payload, ensure_ascii=False), fingerprint, received_at, EVENT_RECEIVED),
            )
            if cur.rowcount == 1:
                return event_id, True
            row = conn.execute(
                "SELECT id FROM channel_events WHERE platform=? AND account_id=? AND external_event_id=?",
                (platform, account_id, external_event_id),
            ).fetchone()
            return (str(row["id"]) if row else event_id), False

    def update_event(
        self,
        event_id: str,
        *,
        state: str,
        session_id: str = "",
        run_id: str = "",
        error: str = "",
        processed_at: str | None = None,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE channel_events SET state=?, session_id=?, run_id=?, error=?, processed_at=? "
                "WHERE id=?",
                (state, session_id, run_id, error[:500], processed_at or utc_now_iso(), event_id),
            )

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM channel_events WHERE id=?", (event_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_event(self, event_id: str) -> None:
        """撤回收件记录，让平台重投时重新处理（仅用于未产生业务结果的内部失败）。"""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM channel_events WHERE id=?", (event_id,))

    def purge_events(self, before_iso: str) -> int:
        """清理旧事件（有界增长）；不清理仍被活动 run 引用的事件。"""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM channel_events WHERE received_at < ? AND state != ?",
                (before_iso, EVENT_RECEIVED),
            )
            return int(cur.rowcount)

    # ---- 会话指针（渠道侧路由状态；会话本身归 assistant） --------------------------

    def get_session_cursor(
        self, platform: str, account_id: str, external_user_id: str, external_chat_id: str
    ) -> str:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT session_id FROM channel_session_cursors WHERE platform=? AND account_id=? "
                "AND external_user_id=? AND external_chat_id=?",
                (platform, account_id, external_user_id, external_chat_id),
            ).fetchone()
            return str(row["session_id"]) if row else ""
        finally:
            conn.close()

    def set_session_cursor(
        self,
        platform: str,
        account_id: str,
        external_user_id: str,
        external_chat_id: str,
        session_id: str,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO channel_session_cursors(platform, account_id, external_user_id, "
                "external_chat_id, session_id, updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(platform, account_id, external_user_id, external_chat_id) "
                "DO UPDATE SET session_id=excluded.session_id, updated_at=excluded.updated_at",
                (platform, account_id, external_user_id, external_chat_id, session_id, utc_now_iso()),
            )

    def clear_session_cursor(
        self, platform: str, account_id: str, external_user_id: str, external_chat_id: str
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM channel_session_cursors WHERE platform=? AND account_id=? "
                "AND external_user_id=? AND external_chat_id=?",
                (platform, account_id, external_user_id, external_chat_id),
            )


def _load_credentials(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
