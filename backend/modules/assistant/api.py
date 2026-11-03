"""Assistant 统一执行入口（架构 §4）：Web/微信/定时任务共用。

submit 持久化接收/去重/入队后立即返回，不等模型完成；
重复请求返回相同 run，不重跑工具。队列满明确 busy。
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from backend.modules.assistant.contracts import RunCommand, RunEvent, RunReceipt
from backend.modules.assistant.dispatcher import RunDispatcher
from backend.modules.assistant.events import EventBus
from backend.modules.assistant.repository import (
    RUN_CANCELLED,
    AssistantRepository,
    normalize_channel_scope,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.context import Principal
from backend.shared.errors import BusyError, InvalidInputError, NotFoundError

DEFAULT_WAIT_CAPACITY = 32


class AssistantService:
    def __init__(
        self,
        db: Database,
        *,
        runtime: Any,
        models: Any,
        access: Any,
        on_run_finished=None,
        wait_capacity: int = DEFAULT_WAIT_CAPACITY,
    ) -> None:
        self.db = db
        self.repo = AssistantRepository(db)
        self.events = EventBus()
        self.dispatcher = RunDispatcher(
            repo=self.repo, events=self.events, runtime=runtime,
            models=models, access=access, on_run_finished=on_run_finished,
        )
        self.access = access
        self.wait_capacity = wait_capacity

    # ---- 生命周期 ------------------------------------------------------------------

    async def start(self) -> None:
        await self.dispatcher.start()

    async def aclose(self) -> None:
        await self.dispatcher.stop()

    # ---- 会话 ------------------------------------------------------------------

    async def create_session(
        self,
        principal: Principal,
        *,
        source: str = "web",
        external_chat_id: str = "",
        title: str = "",
        channel_account_id: str = "",
    ) -> str:
        return self.repo.create_session(
            owner_id=principal.user_id, source=source,
            channel_account_id=normalize_channel_scope(channel_account_id),
            external_chat_id=external_chat_id, title=title,
        )

    async def get_or_create_session(
        self,
        principal: Principal,
        *,
        external_chat_id: str,
        source: str = "web",
        channel_account_id: str = "",
        title: str = "",
    ) -> str:
        """按外部会话标识解析（旧 thread_id 格式迁移）；归属 owner 唯一。"""
        existing = self.repo.find_session_by_external_chat(principal.user_id, external_chat_id)
        if existing is not None:
            return str(existing["id"])
        return await self.create_session(
            principal, source=source, external_chat_id=external_chat_id,
            channel_account_id=channel_account_id, title=title[:60],
        )

    async def list_sessions(self, principal: Principal, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.repo.list_sessions(principal.user_id, limit=limit, offset=offset)

    async def session_messages(self, principal: Principal, session_id: str) -> list[dict]:
        """UI 投影消息（仅 owner；投影不是模型历史）。"""
        session = self.repo.get_session(session_id, owner_id=principal.user_id)
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT id, run_id, role, content, status, created_at FROM conversations "
                "WHERE session_id=? ORDER BY id",
                (session["id"],),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 提交 ------------------------------------------------------------------

    async def submit(self, command: RunCommand) -> RunReceipt:
        principal = self.access.validate_principal(command.principal)
        self.access.require_permission(principal, "chat.use")

        session = self.repo.get_session(command.session_id, owner_id=principal.user_id)
        if not session["active"]:
            raise InvalidInputError("会话已停用")
        if not command.text.strip() and not command.attachment_ids:
            raise InvalidInputError("消息内容为空")
        if not command.client_message_id:
            raise InvalidInputError("缺少 client_message_id")

        scope = normalize_channel_scope(command.channel_account_id)
        queued = self._count_queued()
        if queued >= self.wait_capacity:
            raise BusyError(f"等待队列已满（{queued}/{self.wait_capacity}），请稍后重试")

        run_id, duplicate = self.repo.create_run(
            owner_id=principal.user_id,
            session_id=str(session["id"]),
            source=command.source,
            channel_account_scope=scope,
            client_message_id=command.client_message_id,
            input_summary=command.text,
            attachment_ids=list(command.attachment_ids),
        )
        if not duplicate:
            self._persist_user_message(str(session["id"]), principal.user_id, run_id,
                                       command.source, command.text)
            self.events.publish(run_id, "accepted", {"session_id": str(session["id"])})
            self.events.publish(run_id, "queued", {"position": queued + 1})
        state = self.repo.get_run(run_id)["status"]
        return RunReceipt(run_id=run_id, session_id=str(session["id"]), state=state, duplicate=duplicate)

    def _persist_user_message(self, session_id: str, owner_id: int, run_id: str,
                              source: str, text: str) -> None:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO conversations(session_id, owner_id, run_id, role, content, status, "
                "chat_mode, source, seq, created_at, updated_at) "
                "VALUES(?,?,?,?,?,1,'normal',?,0,?,?)",
                (session_id, owner_id, run_id, "user", text, source, now, now),
            )

    def _count_queued(self) -> int:
        return self.dispatcher._count_queued()

    # ---- 订阅 / 取消 ---------------------------------------------------------------

    def _require_run_access(self, principal: Principal, run_id: str) -> dict:
        run = self.repo.get_run(run_id)
        if int(run["owner_id"]) != principal.user_id:
            # 不泄露他人 run 的存在性
            raise NotFoundError(f"run 不存在: {run_id}")
        return run

    def iter_events(self, principal: Principal, run_id: str, after_seq: int = 0) -> AsyncIterator[RunEvent]:
        """订阅 run 事件流（owner 校验后）。注意与 self.events(EventBus) 属性区分。"""
        run = self._require_run_access(principal, run_id)
        return self.events.subscribe(principal, int(run["owner_id"]), run_id, after_seq=after_seq)

    async def cancel(self, principal: Principal, run_id: str) -> bool:
        self._require_run_access(principal, run_id)
        status = await self.dispatcher.request_cancel(run_id)
        return status in (RUN_CANCELLED, "cancel_requested")

    async def run_status(self, principal: Principal, run_id: str) -> dict:
        run = self._require_run_access(principal, run_id)
        return {
            "run_id": str(run["id"]),
            "session_id": str(run["session_id"]),
            "status": str(run["status"]),
            "error": run["error"],
            "created_at": run["created_at"],
            "finished_at": run["finished_at"],
        }

    # ---- 历史投影 ------------------------------------------------------------------

    async def rename_session(self, principal: Principal, session_id: str, title: str) -> None:
        session = self.repo.get_session(session_id, owner_id=principal.user_id)
        with self.db.transaction() as conn:
            conn.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?",
                         (title[:120], utc_now_iso(), session["id"]))

    async def delete_session(self, principal: Principal, session_id: str) -> None:
        """停用会话（active=0，保留数据）；投影行按旧语义标删除。"""
        session = self.repo.get_session(session_id, owner_id=principal.user_id)
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute("UPDATE sessions SET active=0, updated_at=? WHERE id=?", (now, session["id"]))
            conn.execute("UPDATE conversations SET status=0, updated_at=? WHERE session_id=?", (now, session["id"]))
