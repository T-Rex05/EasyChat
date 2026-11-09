"""提醒四工具：身份只来自 ToolContext，目标只来自用户有效绑定。"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.shared.tool_context import resolve


class ReminderCreateInput(BaseModel):
    text: str = Field(description="提醒内容，例如「交周报」")
    title: str = Field(default="", description="可读标题，可留空")
    at: str = Field(default="", description="一次性提醒的 ISO 时间，如 2026-11-06T09:00:00+08:00")
    daily_at: str = Field(default="", description="每天重复的 HH:MM")
    weekly_at: str = Field(default="", description="每周重复的 HH:MM")
    weekday: int | None = Field(default=None, description="每周重复的星期：0=周一…6=周日")
    every_seconds: int = Field(default=0, description="固定间隔秒数，最小 60")


class ReminderListInput(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


class ReminderIdInput(BaseModel):
    schedule_id: str = Field(description="提醒 ID，例如 sch_xxx")


class ReminderSnoozeInput(BaseModel):
    schedule_id: str = Field(description="原提醒 ID")
    minutes: int = Field(ge=1, le=10080, description="稍后多少分钟")


def _ctx(config: RunnableConfig = None):
    context = resolve(config)
    if context is None:
        raise RuntimeError("缺少可信用户身份，拒绝操作提醒")
    return context


def _target(channels: Any, owner_id: int):
    if channels is None:
        return None
    resolved = channels.delivery_target_for_owner(owner_id)
    if not resolved:
        return None
    from backend.modules.delivery.contracts import target_from_channel

    return target_from_channel(resolved)


def _fmt(epoch: float, timezone: str) -> str:
    try:
        return datetime.fromtimestamp(epoch, ZoneInfo(timezone)).strftime("%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return str(epoch)


def build_reminder_tools(
    *, scheduling: Any, channels: Any, profiles: Any
) -> list[Any]:
    @tool(args_schema=ReminderCreateInput)
    def reminder_create(
        text: str,
        title: str = "",
        at: str = "",
        daily_at: str = "",
        weekly_at: str = "",
        weekday: int | None = None,
        every_seconds: int = 0,
        config: RunnableConfig = None,
    ) -> str:
        """创建提醒。一次性用 at；每天用 daily_at；每周用 weekly_at + weekday。"""
        try:
            context = _ctx(config)
            target = _target(channels, context.principal.user_id)
            if target is None:
                return "还没绑定微信，暂时没法提醒你。"
            timezone = profiles.timezone_for(context.principal.user_id) if profiles else "Asia/Shanghai"
            schedule = scheduling.create(
                context.principal,
                title=title or text,
                text=text,
                target=target,
                at=at,
                daily_at=daily_at,
                weekly_at=weekly_at,
                weekday=weekday,
                every_seconds=every_seconds,
                timezone=timezone,
            )
            return (
                f"✅ 已设置：{_fmt(schedule.next_run_at, schedule.timezone)} "
                f"提醒你{text}（ID {schedule.schedule_id}）。"
                "要改时间或取消，直接说。"
            )
        except Exception as exc:  # noqa: BLE001  工具错误必须可读，不抛给模型栈
            return f"提醒创建失败：{exc}"

    @tool(args_schema=ReminderListInput)
    def reminder_list(limit: int = 10, config: RunnableConfig = None) -> str:
        """列出本人提醒（默认最近 10 条）。"""
        try:
            context = _ctx(config)
            schedules = scheduling.list(context.principal, limit=limit)
            if not schedules:
                return "还没有提醒。"
            lines = ["当前提醒："]
            for item in schedules:
                state = "开" if item.enabled else "停"
                lines.append(
                    f"[{state}] {_fmt(item.next_run_at, item.timezone)} {item.text or item.title} "
                    f"（ID {item.schedule_id}）"
                )
            return "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            return f"读取提醒失败：{exc}"

    @tool(args_schema=ReminderIdInput)
    def reminder_cancel(schedule_id: str, config: RunnableConfig = None) -> str:
        """停用一条提醒，保留历史。"""
        try:
            context = _ctx(config)
            schedule = scheduling.set_enabled(context.principal, schedule_id, False)
            return f"已取消提醒（ID {schedule.schedule_id}）。"
        except Exception as exc:  # noqa: BLE001
            return f"取消失败：{exc}"

    @tool(args_schema=ReminderSnoozeInput)
    def reminder_snooze(
        schedule_id: str, minutes: int, config: RunnableConfig = None
    ) -> str:
        """稍后提醒：新建一次性提醒，原提醒保持不变。"""
        try:
            context = _ctx(config)
            source = scheduling.get(context.principal, schedule_id)
            timezone = source.timezone or "Asia/Shanghai"
            when = datetime.fromtimestamp(
                scheduling.clock() + int(minutes) * 60, ZoneInfo(timezone)
            ).isoformat()
            schedule = scheduling.create(
                context.principal,
                title=source.title or "稍后提醒",
                text=source.text or source.title,
                target=source.target,
                at=when,
                timezone=timezone,
            )
            return f"好，{_fmt(schedule.next_run_at, timezone)} 再提醒你（ID {schedule.schedule_id}）。"
        except Exception as exc:  # noqa: BLE001
            return f"稍后提醒失败：{exc}"

    tools = [reminder_create, reminder_list, reminder_cancel, reminder_snooze]
    for item in tools:
        item._toolset = "__always_available__"
    return tools
