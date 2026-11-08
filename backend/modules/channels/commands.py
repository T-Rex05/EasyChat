"""微信命令路由（不经过模型、不产生模型费用）。

只依赖模块公开接口；ChannelService 在构造后晚绑定服务，避免把未构造的
对象塞进构造函数。所有命令先校验 Principal，再交给 service 做 owner 校验。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from backend.modules.channels.contracts import ChannelTarget, InboundMessage
from backend.modules.ledger.contracts import (
    LedgerAlreadyCommitted,
    LedgerControlMismatch,
)
from backend.modules.profiles.contracts import PRESET_NAMES
from backend.shared.context import Principal
from backend.shared.errors import AppError
from backend.shared.identifiers import is_valid_id

TargetResolver = Callable[[int], ChannelTarget | None]


class ProfilesCommands(Protocol):
    def get(self, actor: Principal) -> Any: ...
    def update(self, actor: Principal, **fields: Any) -> Any: ...
    def timezone_for(self, owner_id: int) -> str: ...
    def quiet_window(self, owner_id: int, *, now: float) -> Any: ...
    def list_mood(self, actor: Principal, *, days: int) -> list[Any]: ...
    def set_mood_enabled(self, actor: Principal, enabled: bool) -> Any: ...
    def delete_mood(self, actor: Principal) -> Any: ...


class MemoryCommands(Protocol):
    def list(self, actor: Principal, *, limit: int) -> list[Any]: ...
    def forget(
        self, actor: Principal, *, memory_id: str = "", query: str = "",
        reason: str = "",
    ) -> Any: ...


class LedgerCommands(Protocol):
    def commit_import(
        self, actor: Principal, import_id: str, *, request_id: str = "",
        confirm_mismatch: bool = False,
    ) -> Any: ...


class InboxCommands(Protocol):
    def save(self, actor: Principal, *, url: str, source: str) -> Any: ...


class SchedulingCommands(Protocol):
    def list(self, actor: Principal, *, limit: int) -> list[Any]: ...
    def create(self, actor: Principal, **fields: Any) -> Any: ...
    def set_enabled(self, actor: Principal, schedule_id: str, enabled: bool) -> Any: ...


class SuperagentIntakeCommands(Protocol):
    """superagent 微信命令入口（/开发 /任务 /补充 /取消 /重试）。"""

    async def handle(self, principal: Principal, message: InboundMessage) -> str | None: ...


@dataclass
class CommandServices:
    profiles: ProfilesCommands | None = None
    memory: MemoryCommands | None = None
    ledger: LedgerCommands | None = None
    inbox: InboxCommands | None = None
    scheduling: SchedulingCommands | None = None
    superagent: SuperagentIntakeCommands | None = None
    # 只暴露“按 owner 解析目标”的窄函数，命令层不持有 ChannelService。
    target_for_owner: TargetResolver | None = None


class WeChatCommands:
    def __init__(self, services: CommandServices) -> None:
        self.services = services

    async def handle(
        self, principal: Principal, message: InboundMessage, session_id: str
    ) -> tuple[str, str] | None:
        text = message.text.strip()
        if not text.startswith("/"):
            return None
        parts = text.split()
        command = parts[0].lower()
        if self.services.superagent is not None and command in (
            "/开发", "/任务", "/任务列表", "/补充", "/取消", "/重试",
        ):
            reply = await self.services.superagent.handle(principal, message)
            return (reply, session_id) if reply is not None else (None, session_id)
        if command in ("/账单确认", "/confirm"):
            return await self._confirm_ledger(principal, message, parts, session_id), session_id
        if command in ("/人设", "/persona"):
            return self._persona(principal, parts), session_id
        if command in ("/记忆", "/memory"):
            return self._memory_list(principal, parts), session_id
        if command in ("/忘掉", "/forget"):
            return self._memory_forget(principal, parts), session_id
        if command in ("/简报", "/briefing"):
            return await self._briefing(principal, parts), session_id
        if command in ("/存", "/save"):
            return await self._inbox_save(principal, parts), session_id
        if command in ("/情绪", "/mood"):
            return await self._mood(principal, parts), session_id
        return None

    async def _confirm_ledger(
        self, principal: Principal, message: InboundMessage, parts: list[str], session_id: str
    ) -> str:
        if self.services.ledger is None:
            return "账本功能未启用。"
        if len(parts) not in (2, 3):
            return "用法：/账单确认 <import_id>，控制总额不一致时加「强制」。"
        import_id = parts[1].strip()
        if not is_valid_id(import_id, prefix="lim"):
            return "请提供完整的 import_id（以 lim_ 开头），不支持前缀匹配。"
        force = len(parts) == 3
        if force and parts[2] != "强制":
            return "第三个参数只能是「强制」，且仅在核对控制总额后使用。"
        message_id = message.external_event_id
        if message_id.startswith("msg:"):
            message_id = message_id[4:]
        request_id = f"wechat:{message_id}"
        try:
            result = self.services.ledger.commit_import(
                principal, import_id, request_id=request_id, confirm_mismatch=force
            )
        except LedgerControlMismatch as exc:
            return f"{exc}。确认无误后回复 /账单确认 {import_id} 强制"
        except LedgerAlreadyCommitted:
            return f"这批账单已经提交过了（ID {import_id}），没有重复导入。"
        except AppError as exc:
            return f"账单提交失败：{exc}"
        if result.duplicate:
            return f"这批账单已经提交过了（ID {import_id}），没有重复导入。"
        return (
            f"✅ 已导入 {result.inserted} 笔，更新 {result.updated} 笔，"
            f"跳过 {result.skipped} 笔。明细和报告在 Web 账本页。"
        )

    def _persona(self, principal: Principal, parts: list[str]) -> str:
        profiles = self.services.profiles
        if profiles is None:
            return "人格设置未启用。"
        try:
            current = profiles.get(principal)
            if len(parts) == 1:
                return (
                    f"当前人设：{current.persona_preset}，称呼「{current.address_form}」，"
                    f"微信最多 {current.max_chars} 字。"
                    "可发送 /人设 温柔|干练|俏皮|直给 或 /人设 自定义 <文字>。"
                )
            if parts[1] in ("自定义", "custom"):
                instruction = " ".join(parts[2:]).strip()
                if not instruction:
                    return "用法：/人设 自定义 <你希望我说话的风格>"
                profile = profiles.update(
                    principal, persona_preset="custom", custom_instruction=instruction
                )
                return f"✅ 已切换自定义人设（{profile.persona_revision}）。"
            preset = PRESET_NAMES.get(parts[1])
            if preset is None:
                return "可选：温柔 / 干练 / 俏皮 / 直给 / 自定义 <文字>。"
            profiles.update(principal, persona_preset=preset)
            return f"✅ 已切换为「{parts[1]}」人设。"
        except AppError as exc:
            return f"人设设置失败：{exc}"

    def _memory_list(self, principal: Principal, parts: list[str]) -> str:
        if self.services.memory is None:
            return "记忆功能未启用。"
        try:
            records = self.services.memory.list(principal, limit=10)
        except AppError as exc:
            return f"读取记忆失败：{exc}"
        if not records:
            return "还没有长期记忆。说「记住…」我才会记。"
        lines = ["我记住的最近 10 条："]
        for item in records:
            lines.append(
                f"• [{item.kind}] {item.content[:60]}（{item.recorded_at[:10]}，"
                f"{item.memory_id[:12]}）"
            )
        return "\n".join(lines)

    def _memory_forget(self, principal: Principal, parts: list[str]) -> str:
        memory = self.services.memory
        if memory is None:
            return "记忆功能未启用。"
        query = " ".join(parts[1:]).strip()
        if not query:
            return "用法：/忘掉 <记忆ID前缀或关键词>"
        try:
            if query.startswith("mem_"):
                records = memory.list(principal, limit=200)
                matches = [r for r in records if r.memory_id.startswith(query)]
                if len(matches) != 1:
                    return f"找到 {len(matches)} 条匹配记忆，请提供更长的 ID 前缀。"
                result = memory.forget(principal, memory_id=matches[0].memory_id, reason="wechat")
            else:
                result = memory.forget(principal, query=query, reason="wechat")
        except AppError as exc:
            return f"删除记忆失败：{exc}"
        return f"已删除 {result.forgotten} 条相关记忆。"

    async def _briefing(self, principal: Principal, parts: list[str]) -> str:
        scheduling = self.services.scheduling
        if scheduling is None or self.services.target_for_owner is None:
            return "简报功能未启用。"
        if len(parts) == 1:
            return (
                "用法：/简报 早 08:00、/简报 晚 21:30、"
                "/简报 周 开、/简报 周 关、/简报 关。"
            )
        resolved = self.services.target_for_owner(principal.user_id)
        if not resolved:
            return "还没绑定微信，暂时没法发简报。"
        from backend.modules.delivery.contracts import target_from_channel

        target = target_from_channel(resolved)
        tz_name = (
            self.services.profiles.timezone_for(principal.user_id)
            if self.services.profiles is not None else ""
        )
        try:
            if parts[1] in ("关", "off"):
                count = 0
                for item in scheduling.list(principal, limit=100):
                    if (
                        item.content_kind == "briefing"
                        and item.briefing_kind in ("morning", "evening", "weekly")
                        and item.enabled
                    ):
                        scheduling.set_enabled(principal, item.schedule_id, False)
                        count += 1
                return f"已停用 {count} 条普通简报；情绪周报不受影响。"
            if parts[1] in ("周", "weekly"):
                if len(parts) < 3 or parts[2] not in ("开", "关", "on", "off"):
                    return "用法：/简报 周 开 或 /简报 周 关"
                enabled = parts[2] in ("开", "on")
                if not enabled:
                    count = 0
                    for item in scheduling.list(principal, limit=100):
                        if item.briefing_kind == "weekly" and item.enabled:
                            scheduling.set_enabled(principal, item.schedule_id, False)
                            count += 1
                    return f"已停用周报（{count} 条）。"
                schedule = scheduling.create(
                    principal, title="周报", text="", target=target,
                    weekly_at="20:00", weekday=6, timezone=tz_name,
                    content_kind="briefing", briefing_kind="weekly",
                )
                self._disable_briefing_kind(
                    principal, "weekly", keep_id=schedule.schedule_id
                )
                return "✅ 周报已开启：每周日 20:00。"
            kind = {"早": "morning", "morning": "morning",
                    "晚": "evening", "evening": "evening"}.get(parts[1])
            if kind is None or len(parts) < 3:
                return "用法：/简报 早 08:00 或 /简报 晚 21:30"
            at_time = parts[2]
            schedule = scheduling.create(
                principal, title="早间简报" if kind == "morning" else "晚间简报",
                text="", target=target, daily_at=at_time, timezone=tz_name,
                content_kind="briefing", briefing_kind=kind,
            )
            # 先创建（校验失败不会动旧配置），再停用旧计划但保留刚创建/命中的这条。
            self._disable_briefing_kind(
                principal, kind, keep_id=schedule.schedule_id
            )
            quiet = self.services.profiles.quiet_window(
                principal.user_id, now=schedule.next_run_at
            ) if self.services.profiles is not None else None
            suffix = "会延到安静时段结束后发。" if quiet and quiet.active else ""
            return f"✅ 已设置每天 {at_time} 的{schedule.title}。{suffix}"
        except AppError as exc:
            return f"简报设置失败：{exc}"

    def _disable_briefing_kind(
        self, principal: Principal, kind: str, *, keep_id: str = ""
    ) -> None:
        scheduling = self.services.scheduling
        if scheduling is None:
            return
        for item in scheduling.list(principal, limit=100):
            if item.schedule_id == keep_id:
                continue
            if item.briefing_kind == kind and item.enabled:
                scheduling.set_enabled(principal, item.schedule_id, False)

    async def _inbox_save(self, principal: Principal, parts: list[str]) -> str:
        inbox = self.services.inbox
        if inbox is None:
            return "收件箱功能未启用。"
        if len(parts) < 2:
            return "用法：/存 <链接>"
        url = parts[1].strip()
        try:
            item = inbox.save(principal, url=url, source="wechat")
        except AppError as exc:
            return f"保存失败：{exc}"
        return f"已存：{item.title or item.url}"

    async def _mood(self, principal: Principal, parts: list[str]) -> str:
        profiles = self.services.profiles
        if profiles is None:
            return "情绪功能未启用。"
        if len(parts) == 1:
            try:
                entries = profiles.list_mood(principal, days=7)
            except AppError as exc:
                return f"读取情绪失败：{exc}"
            if not entries:
                return "最近 7 天没有情绪记录。发 /情绪 on 才会开始按天记录。"
            lines = ["最近 7 天："]
            for entry in entries:
                labels = "、".join(entry.labels) or "未标注"
                lines.append(f"• {entry.entry_date} {entry.score:+d} 分（{labels}）")
            lines.append("/情绪 关闭 停止记录；/情绪 删除 删除全部。")
            return "\n".join(lines)
        action = parts[1].lower()
        if action in ("on", "开", "开启"):
            try:
                profiles.set_mood_enabled(principal, True)
            except AppError as exc:
                return f"开启失败：{exc}"
            self._ensure_mood_schedule(principal, enabled=True)
            return (
                "✅ 已开启情绪记录：会分析你发给我的文字，按天记录分数和标签，"
                "只你自己可见；可随时 /情绪 关闭 或 /情绪 删除。"
            )
        if action in ("off", "关", "关闭"):
            try:
                profiles.set_mood_enabled(principal, False)
            except AppError as exc:
                return f"关闭失败：{exc}"
            self._ensure_mood_schedule(principal, enabled=False)
            return "已停止情绪采样，历史记录保留；要清除请发 /情绪 删除。"
        if action in ("删除", "delete"):
            try:
                result = profiles.delete_mood(principal)
            except AppError as exc:
                return f"删除失败：{exc}"
            return f"已删除 {result.deleted} 条情绪记录。"
        return "用法：/情绪、/情绪 on、/情绪 关闭、/情绪 删除。"

    def _ensure_mood_schedule(self, principal: Principal, *, enabled: bool) -> None:
        scheduling = self.services.scheduling
        if scheduling is None:
            return
        for item in scheduling.list(principal, limit=100):
            if item.briefing_kind == "mood_weekly":
                if item.enabled != enabled:
                    scheduling.set_enabled(principal, item.schedule_id, enabled)
                return
        if not enabled or self.services.target_for_owner is None:
            return
        resolved = self.services.target_for_owner(principal.user_id)
        if not resolved:
            return
        from backend.modules.delivery.contracts import target_from_channel

        target = target_from_channel(resolved)

        tz_name = (
            self.services.profiles.timezone_for(principal.user_id)
            if self.services.profiles is not None else ""
        )
        try:
            scheduling.create(
                principal, title="情绪周报", text="", target=target,
                weekly_at="20:30", weekday=6, timezone=tz_name,
                content_kind="briefing", briefing_kind="mood_weekly",
            )
        except AppError:
            pass
