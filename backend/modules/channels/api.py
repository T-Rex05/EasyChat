"""channels 模块公开接口：账号/绑定/扫码生命周期 + 入站归一化处理。

执行统一走 Assistant.submit（source='wechat'），本模块不选模型、不写 run 状态。
身份只认 channel_bindings（平台+账号+外部用户），昵称/openid 不参与 owner 判定。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from backend.modules.channels.contracts import (
    ACCOUNT_ACTIVE,
    ACCOUNT_DISABLED,
    BINDING_DISABLED,
    DEFAULT_FINGERPRINT_WINDOW_SECONDS,
    EVENT_PROCESSED,
    EVENT_REJECTED,
    PLATFORM_WECHAT,
    REASON_ACCOUNT_DISABLED,
    REASON_BUSY,
    REASON_DUPLICATE,
    REASON_EMPTY,
    REASON_FORBIDDEN,
    REASON_INVALID,
    REASON_MEDIA_FAILED,
    REASON_INTERNAL,
    REASON_OK,
    REASON_UNBOUND,
    REASON_USER_DISABLED,
    ChannelAccount,
    ChannelAccountView,
    ChannelBinding,
    InboundMessage,
    InboundOutcome,
    ListenerState,
    QrSessionView,
)
from backend.modules.channels.repository import ChannelRepository
from backend.modules.channels.wechat.account import AiohttpTransport, QrLoginManager
from backend.modules.channels.wechat.listener import WeChatListener
from backend.modules.channels.wechat.media import MediaFetchError, MediaFetcher
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.context import Principal
from backend.shared.crypto import decrypt_secret, encrypt_secret
from backend.shared.errors import AppError, BusyError, ForbiddenError, InvalidInputError, NotFoundError

logger = logging.getLogger(__name__)

_WECHAT_COMMANDS_HELP = (
    "📖 可用命令：\n"
    "/new 新对话\n"
    "/history 会话列表\n"
    "/1、/2 … 切换会话\n"
    "/status 当前会话\n"
    "/rename 标题 重命名\n"
    "/rm 删除当前会话"
)


class ChannelService:
    def __init__(
        self,
        db: Database,
        *,
        assistant: Any,
        access: Any,
        encryption_secret: str,
        transport: Any = None,
        media_fetcher: MediaFetcher | None = None,
        media_dir: Path | None = None,
        clock=time.time,
        fingerprint_window: float = DEFAULT_FINGERPRINT_WINDOW_SECONDS,
    ) -> None:
        if not encryption_secret:
            raise InvalidInputError("渠道凭证加密密钥不能为空")
        self.db = db
        self.repo = ChannelRepository(db)
        self.assistant = assistant
        self.access = access
        self._secret = encryption_secret
        self.transport = transport or AiohttpTransport()
        self.qr = QrLoginManager(self.transport, clock=clock)
        self.listener = WeChatListener(self, self.transport, clock=clock)
        self.media_fetcher = media_fetcher
        self.media_dir = Path(media_dir) if media_dir is not None else None
        self.clock = clock
        self.fingerprint_window = fingerprint_window

    # ---- 生命周期 ----------------------------------------------------------------

    async def start_listeners(self) -> list[ListenerState]:
        self.purge_old_events()
        states = []
        for account in self.repo.list_accounts():
            if account.platform == PLATFORM_WECHAT and account.status == ACCOUNT_ACTIVE:
                states.append(await self.listener.start(account.id))
        return states

    def purge_old_events(self, *, retention_days: int = 7) -> int:
        """有界保留接收事件；仍在 received 的保留供人工对账。启动时执行一次。"""
        from datetime import datetime, timedelta, timezone

        before = (
            datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
        ).isoformat(timespec="milliseconds")
        return self.repo.purge_events(before)

    async def aclose(self) -> None:
        await self.listener.stop_all()
        aclose = getattr(self.transport, "aclose", None)
        if aclose is not None:
            await aclose()

    # ---- 账号管理（system.manage） -------------------------------------------------

    def list_accounts(self, actor: Principal) -> list[ChannelAccountView]:
        self._require_admin(actor)
        return [self._view(a) for a in self.repo.list_accounts()]

    def register_account(
        self,
        actor: Principal,
        *,
        platform: str = PLATFORM_WECHAT,
        account_id: str,
        token: str,
        base_url: str = "",
        bot_user_id: str = "",
        display_name: str = "",
    ) -> ChannelAccountView:
        self._require_admin(actor)
        if not account_id or not token:
            raise InvalidInputError("account_id 与 token 必填")
        existing = self.repo.get_account_by_platform_id(platform, account_id)
        resolved_base_url = base_url or (existing.base_url if existing else "")
        credentials_ref = self._credentials_ref(
            token=token, base_url=resolved_base_url, bot_user_id=bot_user_id,
        )
        account = self.repo.upsert_account(
            platform=platform,
            account_id=account_id,
            display_name=display_name,
            base_url=resolved_base_url,
            bot_user_id=bot_user_id,
            credentials_ref=credentials_ref,
        )
        return self._view(account)

    async def set_account_status(
        self, actor: Principal, account_pk: str, status: str
    ) -> ChannelAccountView:
        self._require_admin(actor)
        self.repo.set_account_status(account_pk, status)
        if status == ACCOUNT_DISABLED:
            await self.listener.stop(account_pk)
        return self._view(self._require_account(account_pk))

    async def start_account(self, actor: Principal, account_pk: str) -> ListenerState:
        self._require_admin(actor)
        self._require_account(account_pk)
        return await self.listener.start(account_pk)

    async def stop_account(self, actor: Principal, account_pk: str) -> ListenerState:
        self._require_admin(actor)
        self._require_account(account_pk)
        return await self.listener.stop(account_pk)

    def list_listener_states(self, actor: Principal) -> list[ListenerState]:
        self._require_admin(actor)
        return self.listener.statuses()

    # ---- 扫码 ------------------------------------------------------------------

    async def start_qr_login(self, actor: Principal) -> QrSessionView:
        self._require_admin(actor)
        return await self.qr.start()

    async def poll_qr_login(self, actor: Principal, session_id: str) -> QrSessionView:
        self._require_admin(actor)
        return await self.qr.poll(session_id)

    async def bind_after_qr(self, actor: Principal, session_id: str) -> dict[str, Any]:
        """扫码确认后保存 bot 凭证；把扫码者自己的微信 ID 绑到当前用户。"""
        self._require_admin(actor)
        credentials = self.qr.take_credentials(session_id)
        if credentials is None:
            raise InvalidInputError("二维码尚未确认或已过期，请重新扫码")
        account = self.repo.upsert_account(
            platform=PLATFORM_WECHAT,
            account_id=credentials["account_id"],
            display_name=f"微信机器人 {credentials['account_id'][-6:]}",
            base_url=credentials.get("base_url", ""),
            bot_user_id=credentials.get("bot_user_id", ""),
            credentials_ref=self._credentials_ref(
                token=credentials["token"],
                base_url=credentials.get("base_url", ""),
                bot_user_id=credentials.get("bot_user_id", ""),
            ),
        )
        binding = None
        if credentials.get("bot_user_id"):
            binding = self.repo.upsert_binding(
                platform=PLATFORM_WECHAT,
                account_id=account.account_id,
                external_user_id=credentials["bot_user_id"],
                user_id=actor.user_id,
            )
        self.qr.discard(session_id)
        state = await self.listener.start(account.id)
        from dataclasses import asdict

        return {
            "account": asdict(self._view(account)),
            "binding": _binding_dict(binding) if binding else None,
            "listener": {"status": state.status, "last_error": state.last_error},
        }

    # ---- 绑定 ------------------------------------------------------------------

    def list_bindings(self, actor: Principal) -> list[dict[str, Any]]:
        principal = self.access.validate_principal(actor)
        if self.access.has_permission(principal, "system.manage"):
            return self.repo.list_bindings()
        return self.repo.list_bindings(owner_id=principal.user_id)

    def bind_user(
        self,
        actor: Principal,
        *,
        platform: str,
        account_id: str,
        external_user_id: str,
        user_id: int | None = None,
        account_pk: str = "",
    ) -> ChannelBinding:
        principal = self.access.validate_principal(actor)
        # 绑定创建是管理操作：外部 openid 不能作为自证身份，避免用户抢绑他人微信。
        # 扫码路径 bind_after_qr 使用真实扫码返回的 ilink_user_id，不经此入口。
        self.access.require_permission(principal, "system.manage")
        target_id = user_id if user_id is not None else principal.user_id
        target = self.access.snapshot_principal(int(target_id))  # 禁用用户不能获得绑定
        account = (
            self._require_account(account_pk)
            if account_pk
            else self.repo.get_account_by_platform_id(platform, account_id)
        )
        if account is None:
            raise NotFoundError(f"渠道账号不存在: {platform}/{account_id}")
        return self.repo.upsert_binding(
            platform=account.platform,
            account_id=account.account_id,
            external_user_id=external_user_id,
            user_id=target.user_id,
        )

    def set_binding_status(self, actor: Principal, binding_id: str, status: str) -> ChannelBinding:
        principal = self.access.validate_principal(actor)
        binding = self.repo.get_binding(binding_id)
        if binding is None:
            raise NotFoundError(f"绑定不存在: {binding_id}")
        if binding.user_id == principal.user_id and status == BINDING_DISABLED:
            pass  # 本人可解绑自己；重新启用或操作他人绑定需要 system.manage
        else:
            self.access.require_permission(principal, "system.manage")
        self.repo.set_binding_status(binding_id, status)
        updated = self.repo.get_binding(binding_id)
        assert updated is not None
        return updated

    def unbind(self, actor: Principal, binding_id: str) -> ChannelBinding:
        """解绑 = status=disabled（保审计）；下一条消息立即按未绑定拒绝。"""
        return self.set_binding_status(actor, binding_id, BINDING_DISABLED)

    # ---- listener 依赖（内部 Interface，供 WeChatListener 调用） ---------------------

    def listener_account(self, account_pk: str) -> tuple[ChannelAccount | None, dict[str, str]]:
        account = self.repo.get_account(account_pk)
        if account is None:
            return None, {}
        payload = self.repo.get_credentials_payload(account_pk)
        token = ""
        if payload.get("token"):
            try:
                token = decrypt_secret(str(payload["token"]), self._secret)
            except Exception:  # noqa: BLE001  解密失败按缺凭证处理，不泄露详情
                logger.error("渠道凭证解密失败 account=%s", account_pk)
        return account, {"token": token, "base_url": str(payload.get("base_url") or "")}

    def record_poll(
        self,
        account_pk: str,
        *,
        cursor: str | None = None,
        error: str | None = None,
    ) -> None:
        self.repo.update_poll_state(
            account_pk, cursor=cursor, last_error=error, polled_at=utc_now_iso()
        )

    # ---- 入站处理 ----------------------------------------------------------------

    async def handle_inbound(self, message: InboundMessage) -> InboundOutcome:
        """去重 → 绑定 → 权限 → 会话 → Assistant.submit；拒绝也持久化事件。"""
        account = self.repo.get_account(message.account_pk)
        if account is None or account.platform != message.platform or account.account_id != message.external_account_id:
            return InboundOutcome(accepted=False, reason=REASON_INVALID)

        event_id, inserted = self.repo.insert_event(
            platform=message.platform,
            account_id=message.external_account_id,
            external_event_id=message.external_event_id,
            event_kind=message.event_kind,
            payload={
                "mode": message.event_kind,
                "window_seconds": message.fingerprint_window if message.event_kind == "fingerprint" else None,
                "external_user_id": message.external_user_id,
                "external_chat_id": message.external_chat_id,
                "text_length": len(message.text),
                "media": [ref.to_payload() for ref in message.media],
            },
            fingerprint=message.fingerprint,
            received_at=_iso_from_epoch(message.received_at or self.clock()),
        )
        if not inserted:
            existing = self.repo.get_event(event_id) or {}
            return InboundOutcome(
                accepted=False,
                reason=REASON_DUPLICATE,
                duplicate=True,
                run_id=str(existing.get("run_id") or ""),
                session_id=str(existing.get("session_id") or ""),
                event_id=event_id,
            )

        try:
            return await self._process_event(account, message, event_id)
        except Exception:  # noqa: BLE001  未产生业务结果的内部失败允许平台重投
            logger.exception("渠道入站处理失败，撤回事件等待重投 event=%s", event_id)
            self.repo.delete_event(event_id)
            return InboundOutcome(accepted=False, reason=REASON_INTERNAL)

    async def _process_event(
        self, account: ChannelAccount, message: InboundMessage, event_id: str
    ) -> InboundOutcome:
        if account.status != ACCOUNT_ACTIVE:
            return self._reject(event_id, REASON_ACCOUNT_DISABLED, "渠道账号已禁用")

        if not message.text.strip() and not message.media:
            return self._reject(event_id, REASON_EMPTY, "空消息")

        resolved = self.repo.find_active_binding(
            message.platform, message.external_account_id, message.external_user_id
        )
        if resolved is None:
            return self._reject(event_id, REASON_UNBOUND, "微信账号未绑定")
        binding, user_row = resolved
        if int(user_row.get("status") or 0) != 1:
            return self._reject(event_id, REASON_USER_DISABLED, "账号已被禁用", user_id=binding.user_id)

        try:
            principal = self.access.snapshot_principal(binding.user_id)
            self.access.require_permission(principal, "chat.use")
        except ForbiddenError as exc:
            return self._reject(event_id, REASON_FORBIDDEN, str(exc), user_id=binding.user_id)

        try:
            session_id = await self._resolve_session(principal, account, message)
        except AppError as exc:
            return self._reject(event_id, REASON_INVALID, str(exc), user_id=principal.user_id)

        command_result = await self._handle_command(principal, account, message, session_id)
        if command_result is not None:
            reply_text, command_session = command_result
            self.repo.update_event(
                event_id, state=EVENT_PROCESSED, session_id=command_session,
                processed_at=utc_now_iso(),
            )
            return InboundOutcome(
                accepted=True, reason=REASON_OK, session_id=command_session,
                event_id=event_id, reply_text=reply_text,
            )

        attachment_ids = await self._ingest_media(principal, session_id, event_id, message)
        if message.media and not attachment_ids and not message.text.strip():
            # 只有媒体且全部接收失败：不要用"请描述图片"空跑一次模型
            return self._reject(event_id, REASON_MEDIA_FAILED, "媒体接收失败且无文字")
        text = message.text.strip() or _default_media_text(message)
        from backend.modules.assistant.contracts import RunCommand

        try:
            receipt = await self.assistant.submit(RunCommand(
                principal=principal,
                session_id=session_id,
                source="wechat",
                client_message_id=message.external_event_id,
                text=text,
                attachment_ids=attachment_ids,
                channel_account_id=account.id,
            ))
        except BusyError as exc:
            return self._reject(event_id, REASON_BUSY, str(exc), user_id=principal.user_id)
        except AppError as exc:
            return self._reject(event_id, REASON_INVALID, str(exc), user_id=principal.user_id)

        self.repo.update_event(
            event_id, state=EVENT_PROCESSED, session_id=session_id,
            run_id=receipt.run_id, processed_at=utc_now_iso(),
        )
        return InboundOutcome(
            accepted=True, reason=REASON_OK, run_id=receipt.run_id,
            session_id=session_id, duplicate=receipt.duplicate, event_id=event_id,
        )

    # ---- 内部 ------------------------------------------------------------------

    async def _resolve_session(
        self, principal: Principal, account: ChannelAccount, message: InboundMessage
    ) -> str:
        cursor = self.repo.get_session_cursor(
            message.platform, account.account_id, message.external_user_id, message.external_chat_id
        )
        if cursor:
            existing = await self.assistant.get_session(principal, cursor)
            if (
                existing is not None
                and existing.get("active")
                and str(existing.get("source") or "") == "wechat"
                and str(existing.get("channel_account_id") or "") == account.id
            ):
                return cursor
        external_chat_key = f"{account.account_id}:{message.external_chat_id}"
        session_id = await self.assistant.get_or_create_session(
            principal,
            external_chat_id=external_chat_key,
            source="wechat",
            channel_account_id=account.id,
            title=message.text[:60],
        )
        self.repo.set_session_cursor(
            message.platform, account.account_id, message.external_user_id,
            message.external_chat_id, session_id,
        )
        return session_id

    async def _handle_command(
        self,
        principal: Principal,
        account: ChannelAccount,
        message: InboundMessage,
        session_id: str,
    ) -> tuple[str, str] | None:
        """微信内命令；返回 (回复文本, 当前会话)，None 表示走 Assistant。

        未知 / 命令按旧语义当普通文本交给模型。
        """
        command = message.text.strip()
        lowered = command.lower()
        if not lowered.startswith("/"):
            return None
        if lowered in ("/help", "/帮助", "/?"):
            return _WECHAT_COMMANDS_HELP, session_id
        if lowered in ("/new", "/新对话", "/新会话"):
            new_session = await self.assistant.create_session(
                principal,
                source="wechat",
                external_chat_id=f"{account.account_id}:{message.external_chat_id}:{int(self.clock() * 1000)}",
                channel_account_id=account.id,
                title="微信对话",
            )
            self.repo.set_session_cursor(
                message.platform, account.account_id, message.external_user_id,
                message.external_chat_id, new_session,
            )
            return "✅ 已开启新对话", new_session
        if lowered in ("/status", "/当前"):
            return f"📌 当前会话: {session_id[:20]}...", session_id
        if lowered in ("/history", "/历史", "/会话列表", "/list"):
            sessions = await self._recent_sessions(principal, account)
            if not sessions:
                return "📭 暂无微信对话记录", session_id
            lines = ["📚 最近会话："]
            for index, item in enumerate(sessions, start=1):
                mark = "▶" if item["id"] == session_id else " "
                lines.append(f"{mark}{index}. {item['title'] or item['id'][:16]}")
            lines.append("发送 /序号 切换")
            return "\n".join(lines), session_id
        if command.startswith("/") and command[1:].isdigit():
            index = int(command[1:])
            sessions = await self._recent_sessions(principal, account)
            if 1 <= index <= len(sessions):
                target = sessions[index - 1]
                self.repo.set_session_cursor(
                    message.platform, account.account_id, message.external_user_id,
                    message.external_chat_id, target["id"],
                )
                return f"✅ 已切换到：{target['title'] or target['id'][:16]}", target["id"]
            return f"❌ 序号无效，范围 1-{len(sessions)}", session_id
        if lowered.startswith("/rename") or lowered.startswith("/重命名"):
            parts = command.split(maxsplit=1)
            title = parts[1].strip() if len(parts) > 1 else ""
            if not title or len(title) > 30:
                return "❌ 标题不能为空且不超过 30 个字符", session_id
            await self.assistant.rename_session(principal, session_id, title)
            return f"✅ 已重命名为：{title}", session_id
        if lowered in ("/rm", "/删除", "/删除会话", "/delete"):
            await self.assistant.delete_session(principal, session_id)
            self.repo.clear_session_cursor(
                message.platform, account.account_id, message.external_user_id,
                message.external_chat_id,
            )
            return "✅ 已删除当前会话", ""
        if lowered.split(maxsplit=1)[0] in (
            "/model", "/模型", "/send", "/restart", "/restart-all", "/stop", "/stop-all",
        ):
            return "⚠️ 该命令已停用：模型切换请到 Web 控制台操作", session_id
        return None

    async def _recent_sessions(self, principal: Principal, account: ChannelAccount) -> list[dict[str, Any]]:
        """只列当前机器人账号下的微信会话，防止 /N 把 A 账号会话切给 B 账号。"""
        sessions = await self.assistant.list_sessions(principal, limit=10)
        return [
            s for s in sessions
            if s.get("source") == "wechat"
            and s.get("active")
            and str(s.get("channel_account_id") or "") == account.id
        ]

    async def _ingest_media(
        self,
        principal: Principal,
        session_id: str,
        event_id: str,
        message: InboundMessage,
    ) -> tuple[str, ...]:
        if not message.media or self.media_fetcher is None or self.media_dir is None:
            return ()
        dest_dir = self.media_dir / event_id
        attachment_ids: list[str] = []
        for ref in message.media:
            try:
                fetched = await self.media_fetcher.fetch(ref, dest_dir)
            except MediaFetchError as exc:
                logger.warning("渠道媒体接收失败 event=%s kind=%s: %s", event_id, ref.kind, exc)
                continue
            attachment_id = await self.assistant.register_attachment(
                principal,
                file_name=fetched.file_name,
                file_path=str(fetched.path),
                mime=fetched.mime,
                file_size=fetched.size,
                sha256=fetched.sha256,
                session_id=session_id,
            )
            attachment_ids.append(attachment_id)
        return tuple(attachment_ids)

    def _reject(
        self, event_id: str, reason: str, error: str, *, user_id: int | None = None
    ) -> InboundOutcome:
        self.repo.update_event(
            event_id, state=EVENT_REJECTED, error=f"{reason}: {error}",
            processed_at=utc_now_iso(),
        )
        return InboundOutcome(accepted=False, reason=reason, event_id=event_id)

    def _require_admin(self, actor: Principal) -> Principal:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "system.manage")
        return principal

    def _require_account(self, account_pk: str) -> ChannelAccount:
        account = self.repo.get_account(account_pk)
        if account is None:
            raise NotFoundError(f"渠道账号不存在: {account_pk}")
        return account

    def _credentials_ref(self, *, token: str, base_url: str, bot_user_id: str) -> str:
        return json.dumps(
            {
                "token": encrypt_secret(token, self._secret),
                "base_url": base_url,
                "bot_user_id": bot_user_id,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _view(account: ChannelAccount) -> ChannelAccountView:
        return ChannelAccountView(
            id=account.id,
            platform=account.platform,
            account_id=account.account_id,
            display_name=account.display_name,
            status=account.status,
            base_url=account.base_url,
            bot_user_id=account.bot_user_id,
            last_poll_at=account.last_poll_at,
            last_error=account.last_error,
            has_credentials=account.has_credentials,
        )


def _binding_dict(binding: ChannelBinding) -> dict[str, Any]:
    return {
        "id": binding.id,
        "platform": binding.platform,
        "account_id": binding.account_id,
        "external_user_id": binding.external_user_id,
        "user_id": binding.user_id,
        "status": binding.status,
    }


def _default_media_text(message: InboundMessage) -> str:
    kinds = {ref.kind for ref in message.media}
    if "image" in kinds:
        return "请描述这张图片的内容"
    if "file" in kinds:
        return "请阅读我发送的文件"
    return "请处理我发送的内容"


def _iso_from_epoch(epoch: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat(timespec="milliseconds")
