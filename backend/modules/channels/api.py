"""channels 模块公开接口：账号/绑定/扫码生命周期 + 入站归一化处理。

执行统一走 Assistant.submit（source='wechat'），本模块不选模型、不写 run 状态。
身份只认 channel_bindings（平台+账号+外部用户），昵称/openid 不参与 owner 判定。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from backend.modules.channels.contracts import (
    ACCOUNT_ACTIVE,
    ACCOUNT_DISABLED,
    BINDING_ACTIVE,
    BINDING_DISABLED,
    DEFAULT_FINGERPRINT_WINDOW_SECONDS,
    EVENT_PROCESSED,
    EVENT_RECEIVED,
    EVENT_REJECTED,
    MAX_REPLAY_ATTEMPTS,
    PLATFORM_WECHAT,
    REPLAY_DELAYS_SECONDS,
    STALE_PENDING_SECONDS,
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
    ChannelTarget,
    InboundMessage,
    InboundOutcome,
    ListenerState,
    MediaRef,
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
    "/rm 删除当前会话\n"
    "/人设 查看或切换说话风格\n"
    "/记忆 查看长期记忆；/忘掉 <ID或关键词>\n"
    "/账单确认 <import_id> 提交已预览账单\n\n"
    "直接说「明天 9 点提醒我交周报」即可创建提醒；"
    "发账单文件后可让我预览。"
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
        files: Any = None,
        stt: Any = None,
        voice_echo: bool = False,
        commands: Any = None,
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
        self.files = files
        self.stt = stt
        self.voice_echo = voice_echo
        self.clock = clock
        self.fingerprint_window = fingerprint_window
        # 命令处理器在构造时注入；渠道不反向持有/晚绑定各业务模块。
        self.commands: Any = commands

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

    # ---- 投递目标（delivery 模块通过公开方法调用，不碰 channels 内部表） -------------

    def delivery_credentials(self, account_pk: str) -> tuple[ChannelAccount | None, dict[str, str]]:
        return self.listener_account(account_pk)

    def make_session_target_provider(self):
        """WP-D:为记忆确认提供 (owner_id, session_id)->渠道投递目标 闭包。

        仅当会话归属当前 owner 且其 wechat 绑定仍活跃时返回目标
        (撤销/换绑后目标自然失效,fail-closed);入队走 delivery 既有
        dedup/账本机制,重复确认不双发。
        """

        def provider(owner_id: int, session_id: str) -> ChannelTarget | None:
            conn = self.db.connect()
            try:
                row = conn.execute(
                    "SELECT owner_id, channel_account_id, external_chat_id"
                    " FROM sessions WHERE id=?",
                    (session_id,),
                ).fetchone()
                if row is None or int(row["owner_id"]) != int(owner_id):
                    return None
                ext = str(row["external_chat_id"] or "")
                acct = str(row["channel_account_id"] or "")
                if not ext or not acct:
                    return None
                return ChannelTarget(kind="wechat", ref=ext, channel_account_id=acct)
            finally:
                conn.close()

        return provider

    def delivery_target_for_run(self, run: dict[str, Any]) -> ChannelTarget | None:
        """run 完成时按会话路由解析微信目标；未绑定/禁用返回 None（不投递）。"""
        route = self.repo.find_session_route(str(run.get("session_id") or ""))
        if route is None:
            return None
        platform = str(route["platform"])
        account_id = str(route["account_id"])
        external_user = str(route["external_user_id"])
        account = self.repo.get_account_by_platform_id(platform, account_id)
        if account is None or account.status != ACCOUNT_ACTIVE:
            return None
        resolved = self.repo.find_active_binding(platform, account_id, external_user)
        if resolved is None or int(resolved[1].get("status") or 0) != 1:
            return None
        return ChannelTarget(
            kind=platform,
            ref=external_user,
            channel_account_id=account.id,
            context_token=str(route.get("context_token") or ""),
        )

    def report_stale_token(self, account_pk: str) -> None:
        """公开入口：iLink -14 凭据失效 → 账号入站/出站暂停（session-guard 语义）。"""
        from backend.modules.channels.wechat.account import pause_session  # noqa: PLC0415

        pause_session(account_pk)

    def is_delivery_binding_active(self, account_pk: str, external_user_id: str) -> bool:
        account = self.repo.get_account(account_pk)
        if account is None or account.status != ACCOUNT_ACTIVE:
            return False
        resolved = self.repo.find_active_binding(account.platform, account.account_id, external_user_id)
        return resolved is not None and int(resolved[1].get("status") or 0) == 1

    def delivery_target_for_owner(self, owner_id: int) -> ChannelTarget | None:
        """用户默认微信目标：取该 owner 第一个有效绑定且账号启用。"""
        for row in self.repo.list_bindings(owner_id):
            if str(row.get("status") or "") != BINDING_ACTIVE:
                continue
            account = self.repo.get_account_by_platform_id(
                str(row["platform"]), str(row["account_id"])
            )
            if account is None or account.status != ACCOUNT_ACTIVE:
                continue
            return ChannelTarget(
                kind=str(row["platform"]),
                ref=str(row["external_user_id"]),
                channel_account_id=account.id,
                context_token=self.repo.latest_context_token(
                    str(row["platform"]), str(row["account_id"]),
                    str(row["external_user_id"]),
                ),
            )
        return None

    async def send_wechat_text(
        self, *, account_pk: str, external_user_id: str, text: str, context_token: str = ""
    ) -> None:
        """投递模块专用发送入口：凭证解析与协议细节留在 channels。"""
        from backend.modules.channels.wechat.account import send_text

        account, credentials = self.listener_account(account_pk)
        if account is None or account.status != ACCOUNT_ACTIVE:
            raise InvalidInputError("渠道账号不可用")
        token = str(credentials.get("token") or "")
        base_url = (account.base_url or credentials.get("base_url") or "").rstrip("/")
        if not token or not base_url:
            raise InvalidInputError("渠道账号缺少发送凭证")
        if not context_token:
            context_token = self.repo.latest_context_token(
                account.platform, account.account_id, external_user_id
            )
        await send_text(
            self.transport,
            base_url=base_url,
            token=token,
            to_user_id=external_user_id,
            text=text,
            context_token=context_token,
        )

    # ---- 入站处理 ----------------------------------------------------------------

    async def handle_inbound(self, message: InboundMessage) -> InboundOutcome:
        """持久 inbox（T5）：先事务保存完整可重放 envelope，再处理。

        内部失败不再删除事件（上游未必重投）：标记 failed + retry_at 退避，
        由本地 replay 重试；envelope 已持久化，listener 推进游标是安全的。
        """
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
            envelope_json=json.dumps(_envelope_of(message), ensure_ascii=False),
            envelope_version=1,
        )
        if not inserted:
            existing = self.repo.get_event(event_id) or {}
            try:
                payload = json.loads(existing.get("payload") or "{}")
            except ValueError:
                payload = {}
            if str(existing.get("state") or "") == EVENT_RECEIVED:
                # 上次处理在 mark processed 之前被取消/崩溃：平台重投时必须继续，
                # 否则事件永远卡在 received，而 purge 又不会清理它。
                try:
                    outcome = await self._process_event(account, message, event_id)
                    if outcome.reply_text:
                        self.repo.set_event_reply(event_id, outcome.reply_text)
                    self.repo.mark_event_processing_done(event_id)
                    return outcome
                except asyncio.CancelledError:
                    # 停机：事件保留 pending，重启后由 replay 兜底（陈旧 pending 会被重放）
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.exception("渠道事件重投处理失败 event=%s", event_id)
                    self._mark_replay_failed(event_id, exc)
                    return InboundOutcome(accepted=False, reason=REASON_INTERNAL)
            return InboundOutcome(
                accepted=False,
                reason=REASON_DUPLICATE,
                duplicate=True,
                run_id=str(existing.get("run_id") or ""),
                session_id=str(existing.get("session_id") or ""),
                event_id=event_id,
                # 上次 reply 发送失败时平台会重投；重发确定性回复，避免危机文案丢失。
                reply_text=str(payload.get("reply_text") or "") if isinstance(payload, dict) else "",
            )

        try:
            outcome = await self._process_event(account, message, event_id)
            if outcome.reply_text:
                self.repo.set_event_reply(event_id, outcome.reply_text)
            self.repo.mark_event_processing_done(event_id)
            return outcome
        except asyncio.CancelledError:
            # 停机：保留 pending（envelope 已落库），重启后由 replay 兜底重放。
            raise
        except Exception as exc:  # noqa: BLE001  内部失败：本地重放，不再删除事件
            logger.exception("渠道入站处理失败，标记待重放 event=%s", event_id)
            self._mark_replay_failed(event_id, exc)
            return InboundOutcome(accepted=False, reason=REASON_INTERNAL)

    # ---- 本地重放（envelope 已持久化；毒消息进入可见 dead 状态） --------------------

    async def replay_due_events(self, *, now: float | None = None, limit: int = 5) -> int:
        """重放到期失败事件与停机遗留的陈旧 pending；返回处理条数。"""
        current = self.clock() if now is None else now
        due = self.repo.due_replay_events(
            now=current,
            # received_at 是 ISO TEXT 列：阈值必须同为 ISO 字符串
            stale_pending_before=_iso_from_epoch(current - STALE_PENDING_SECONDS),
            limit=limit,
        )
        replayed = 0
        for row in due:
            try:
                message = _message_from_envelope(row)
            except Exception:  # noqa: BLE001  envelope 损坏 = 毒消息
                logger.exception("envelope 重建失败，标记 dead event=%s", row["id"])
                self.repo.mark_event_dead(str(row["id"]), error="envelope 损坏，无法重建消息")
                continue
            account = self.repo.get_account(message.account_pk)
            if account is None:
                self.repo.mark_event_dead(str(row["id"]), error="渠道账号不存在，无法重放")
                continue
            try:
                outcome = await self._process_event(account, message, str(row["id"]))
                if outcome.reply_text:
                    self.repo.set_event_reply(str(row["id"]), outcome.reply_text)
                self.repo.mark_event_processing_done(str(row["id"]))
                replayed += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._mark_replay_failed(str(row["id"]), exc)
        return replayed

    def _mark_replay_failed(self, event_id: str, exc: Exception) -> None:
        row = self.repo.get_event(event_id) or {}
        attempts = int(row.get("attempts") or 0) + 1
        error = f"{type(exc).__name__}: {exc}"[:500]
        if attempts >= MAX_REPLAY_ATTEMPTS:
            self.repo.mark_event_dead(event_id, error=error)
            logger.error("渠道事件重试耗尽，标记 dead event=%s attempts=%s", event_id, attempts)
            return
        delay = REPLAY_DELAYS_SECONDS[min(len(REPLAY_DELAYS_SECONDS) - 1, attempts - 1)]
        self.repo.mark_event_processing_failed(
            event_id, error=error, retry_at=self.clock() + delay, attempts=attempts,
        )

    def source_route_for_session(self, session_id: str) -> dict[str, str] | None:
        """服务端来源查询（窄接口）：会话 → 渠道来源标识（ToolContext 用）。"""
        route = self.repo.find_session_route(session_id)
        if route is None:
            return None
        return {
            "platform": str(route["platform"]),
            "external_user_id": str(route["external_user_id"]),
            "channel_account_id": str(route["account_id"]),
            "external_chat_id": str(route.get("external_chat_id") or ""),
        }

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

        ingested = await self._ingest_media(
            principal, session_id, event_id, message, account_id=account.id
        )
        attachment_ids = ingested.attachment_ids
        # 失败判据是“整条消息只有语音且没有可用文本”，不能看音频是否保存成功；
        # 语音+图片时图片仍应继续处理，语音+文字时按文字处理。
        all_voice = bool(message.media) and all(
            ref.kind == "voice" for ref in message.media
        )
        if all_voice and not ingested.transcripts and not message.text.strip():
            self.repo.update_event(
                event_id, state=EVENT_PROCESSED, session_id=session_id,
                processed_at=utc_now_iso(),
            )
            return InboundOutcome(
                accepted=True, reason=REASON_OK, session_id=session_id,
                event_id=event_id,
                reply_text="这条语音我没转出来，能打字或再说一遍吗？",
            )
        if message.media and not attachment_ids and not ingested.transcripts and not message.text.strip():
            return self._reject(event_id, REASON_MEDIA_FAILED, "媒体接收失败且无文字")
        text = message.text.strip() or "\n".join(ingested.transcripts)
        if text and ingested.transcripts and message.text.strip():
            text = text + "\n（语音转写）" + " ".join(ingested.transcripts)
        if not text:
            text = _default_media_text(message)
        from backend.modules.channels.safety import CRISIS_REPLY, detect_crisis

        if detect_crisis(text):
            # 危机表达立即确定性回复，不进入模型、不写入情绪样本。
            self.repo.update_event(
                event_id, state=EVENT_PROCESSED, session_id=session_id,
                processed_at=utc_now_iso(),
            )
            return InboundOutcome(
                accepted=True, reason=REASON_OK, session_id=session_id,
                event_id=event_id, reply_text=CRISIS_REPLY,
            )
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

        if self.voice_echo and ingested.transcripts:
            echo = "我听到：" + " ".join(ingested.transcripts)[:120]
            try:
                await self.send_wechat_text(
                    account_pk=account.id,
                    external_user_id=message.external_user_id,
                    text=echo,
                    context_token=message.context_token,
                )
            except Exception:  # noqa: BLE001  回显是可选体验，不阻塞已入队的回答
                logger.warning("语音回显失败 account=%s", account.id, exc_info=True)

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
                self.repo.set_session_cursor(
                    message.platform, account.account_id, message.external_user_id,
                    message.external_chat_id, cursor, context_token=message.context_token,
                )
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
            message.external_chat_id, session_id, context_token=message.context_token,
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
                message.external_chat_id, new_session, context_token=message.context_token,
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
                    message.external_chat_id, target["id"], context_token=message.context_token,
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
        if self.commands is not None:
            handled = await self.commands.handle(principal, message, session_id)
            if handled is not None:
                return handled
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
        *,
        account_id: str = "",
    ):
        """下载/解密后先转写语音，再委托 files 保存；失败只跳过该媒体。"""
        from backend.modules.channels.contracts import MediaIngestResult

        if not message.media or self.media_fetcher is None or self.media_dir is None:
            return MediaIngestResult()
        dest_dir = self.media_dir / event_id
        attachment_ids: list[str] = []
        transcripts: list[str] = []
        for index, ref in enumerate(message.media):
            try:
                fetched = await self.media_fetcher.fetch(ref, dest_dir)
            except MediaFetchError as exc:
                logger.warning("渠道媒体接收失败 event=%s kind=%s: %s", event_id, ref.kind, exc)
                continue
            if ref.kind == "voice" and self.stt is not None:
                from backend.integrations.speech import SpeechError

                try:
                    transcript = await self.stt.transcribe(fetched.path, fetched.mime)
                except SpeechError as exc:
                    logger.warning("语音转写失败 event=%s: %s", event_id, exc)
                except Exception:  # noqa: BLE001  转写失败不能阻塞其他媒体
                    logger.exception("语音转写异常 event=%s", event_id)
                else:
                    if transcript.text.strip():
                        transcripts.append(transcript.text.strip())
            if self.files is not None:
                attachment_id = await self._persist_media(
                    principal, session_id, message.external_event_id, event_id,
                    account_id, index, fetched,
                )
                if attachment_id:
                    attachment_ids.append(attachment_id)
                continue
            # 未装配 files 的降级路径（旧行为，保持兼容）
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
        return MediaIngestResult(tuple(attachment_ids), tuple(transcripts))

    async def _persist_media(
        self,
        principal: Principal,
        session_id: str,
        external_event_id: str,
        event_row_id: str,
        account_id: str,
        index: int,
        fetched,
    ) -> str:
        from backend.modules.files.contracts import REF_ATTACHMENT, SaveMetadata

        try:
            result = await self.files.ingest_local_path(
                principal,
                fetched.path,
                SaveMetadata(
                    original_name=fetched.file_name,
                    declared_mime=fetched.mime,
                    source="wechat",
                    channel=PLATFORM_WECHAT,
                    account_id=account_id,
                    # 幂等作用域用平台事件 ID（事件行被清理后仍可幂等），不是内部行 ID
                    external_event_id=external_event_id,
                    media_index=index,
                    session_id=session_id,
                ),
                remove_source=True,
            )
        except AppError as exc:
            logger.warning(
                "渠道媒体持久保存失败 event=%s index=%s: %s", event_row_id, index, exc,
            )
            return ""
        file = result.file
        attachment_id = await self.assistant.register_attachment(
            principal,
            file_name=file.original_name or fetched.file_name,
            file_path="",
            mime=file.verified_mime,
            file_size=file.size_bytes,
            sha256=file.sha256,
            session_id=session_id,
            stored_file_id=file.file_id,
        )
        self.files.link(principal, file.file_id, REF_ATTACHMENT, attachment_id)
        return attachment_id

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
    """纯媒体消息的中性说明：只告知已保存，绝不让模型编造内容。"""
    kinds = {ref.kind for ref in message.media}
    if "image" in kinds:
        return (
            "（用户发来一张图片，已保存；当前无法查看图片内容，不要描述图片。"
            "如果用户要识别图片，明确说明只能保存，看不到内容。）"
        )
    if "file" in kinds:
        return (
            "（用户发来一个文件，已保存。附件元数据里有 file_id；"
            "只有用户明确要求导入账单时才调用 ledger_import_preview，不要猜测文件内容。）"
        )
    return "（用户发来附件，已保存；不要猜测附件内容。）"


def _iso_from_epoch(epoch: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat(timespec="milliseconds")


def _envelope_of(message: InboundMessage) -> dict[str, Any]:
    """完整可重放 envelope：重建 InboundMessage 所需的全部字段。"""
    return {
        "platform": message.platform,
        "account_pk": message.account_pk,
        "external_account_id": message.external_account_id,
        "external_user_id": message.external_user_id,
        "external_chat_id": message.external_chat_id,
        "external_event_id": message.external_event_id,
        "text": message.text,
        "media": [ref.to_payload() for ref in message.media],
        "context_token": message.context_token,
        "received_at": float(message.received_at or 0.0),
        "fingerprint": message.fingerprint,
        "fingerprint_window": message.fingerprint_window,
        "event_kind": message.event_kind,
    }


def _message_from_envelope(row: dict[str, Any]) -> InboundMessage:
    """从持久化 envelope 重建消息；缺字段/坏结构抛 ValueError（→ dead）。"""
    envelope_version = int(row.get("envelope_version") or 0)
    if envelope_version < 1:
        raise ValueError("事件缺少 envelope（历史行不可重放）")
    try:
        data = json.loads(str(row.get("envelope_json") or "{}"))
    except ValueError as exc:
        raise ValueError("envelope JSON 损坏") from exc
    if not isinstance(data, dict) or not data.get("platform"):
        raise ValueError("envelope 字段缺失")
    media = tuple(
        MediaRef(
            kind=str(item.get("kind") or "file"),
            url=str(item.get("url") or ""),
            encrypt_query_param=str(item.get("encrypt_query_param") or ""),
            aes_key=str(item.get("aes_key") or ""),
            file_name=str(item.get("file_name") or ""),
            size=int(item.get("size") or 0),
        )
        for item in (data.get("media") or [])
        if isinstance(item, dict)
    )
    return InboundMessage(
        platform=str(data["platform"]),
        account_pk=str(data["account_pk"]),
        external_account_id=str(data["external_account_id"]),
        external_user_id=str(data["external_user_id"]),
        external_chat_id=str(data["external_chat_id"]),
        external_event_id=str(data["external_event_id"]),
        text=str(data.get("text") or ""),
        media=media,
        context_token=str(data.get("context_token") or ""),
        received_at=float(data.get("received_at") or 0.0),
        fingerprint=str(data.get("fingerprint") or ""),
        fingerprint_window=float(data.get("fingerprint_window") or DEFAULT_FINGERPRINT_WINDOW_SECONDS),
        event_kind=str(data.get("event_kind") or "message"),
    )
