"""简报生成：数据只来自模块公开接口；模板兜底，模型输出必须过数字护栏。"""
from __future__ import annotations

import json
import logging
import re
import time as time_module
from datetime import date, datetime, time as dtime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from backend.modules.briefing.contracts import (
    BRIEFING_AI_NEWS,
    BRIEFING_EVENING,
    BRIEFING_KIND_LABELS,
    BRIEFING_MORNING,
    BRIEFING_MOOD_WEEKLY,
    BRIEFING_WEEKLY,
    BriefingData,
    BriefingResult,
)
from backend.shared.errors import InvalidInputError

ALL_KINDS = (
    BRIEFING_MORNING, BRIEFING_EVENING, BRIEFING_WEEKLY, BRIEFING_MOOD_WEEKLY,
    BRIEFING_AI_NEWS,
)

logger = logging.getLogger(__name__)

_WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")


class BriefingService:
    def __init__(
        self,
        *,
        access: Any,
        scheduling: Any,
        profiles: Any,
        inbox: Any = None,
        news: Any = None,
        generator: Any = None,
        clock=time_module.time,
    ) -> None:
        self.access = access
        self.scheduling = scheduling
        self.profiles = profiles
        self.inbox = inbox
        self.news = news
        self.generator = generator
        self.clock = clock

    async def build(
        self, owner_id: int, kind: str, *, local_date: str = ""
    ) -> BriefingResult:
        if kind not in ALL_KINDS:
            raise InvalidInputError(f"未知简报类型: {kind}")
        principal = self.access.snapshot_principal(int(owner_id))
        if kind == BRIEFING_AI_NEWS:
            return await self._build_ai_news(principal)
        data = self._data(principal, kind, local_date)
        fallback = self._template(data)
        if kind == BRIEFING_MOOD_WEEKLY and not data.mood.get("sufficient"):
            return BriefingResult(
                "", kind, principal.user_id, "schedule",
                skipped_reason="mood_insufficient",
            )
        if not fallback:
            return BriefingResult(
                "", kind, principal.user_id, "schedule", skipped_reason="empty"
            )
        text = await self._generate(data, fallback, owner_id=principal.user_id)
        return BriefingResult(text or fallback, kind, principal.user_id, "schedule")

    async def _build_ai_news(self, principal) -> BriefingResult:
        if self.news is None:
            return BriefingResult(
                "", BRIEFING_AI_NEWS, principal.user_id, "schedule",
                skipped_reason="news_unavailable",
            )
        try:
            digest = await self.news.build(principal.user_id)
        except Exception:  # noqa: BLE001 新闻源失败不能阻塞简报 worker
            logger.exception("AI 前沿日报抓取失败 owner=%s", principal.user_id)
            return BriefingResult(
                "", BRIEFING_AI_NEWS, principal.user_id, "schedule",
                skipped_reason="news_unavailable",
            )
        text = str(getattr(digest, "text", "") or "").strip()
        if not text:
            return BriefingResult(
                "", BRIEFING_AI_NEWS, principal.user_id, "schedule",
                skipped_reason="news_empty",
            )
        return BriefingResult(text, BRIEFING_AI_NEWS, principal.user_id, "schedule")

    # ---- 数据 ------------------------------------------------------------------

    def _data(self, principal, kind: str, local_date: str) -> BriefingData:
        timezone = self.profiles.timezone_for(principal.user_id)
        tz = ZoneInfo(timezone)
        current = datetime.fromtimestamp(self.clock(), tz)
        today = date.fromisoformat(local_date) if local_date else current.date()
        day_start = datetime.combine(today, dtime.min, tz)
        day_end = day_start + timedelta(days=1)
        profile = self.profiles.get(principal)
        upcoming: list[dict[str, object]] = []
        delivered = 0
        if kind in (BRIEFING_MORNING, BRIEFING_WEEKLY):
            # “下周”是明天 00:00 起的 7 天；不能用 day_start 把今天未到点的算进去。
            # start 让 scheduling 把每日/每周/间隔计划推进到窗口内的下一次 occurrence。
            if kind == BRIEFING_MORNING:
                start = day_start
                until = day_end
            else:
                start = day_end
                until = day_end + timedelta(days=7)
            schedules = self.scheduling.upcoming(
                principal, until=until.timestamp(), limit=50, content_kind="text",
                start=start.timestamp(),
            )
            for item in schedules:
                upcoming.append({
                    "time": datetime.fromtimestamp(item.next_run_at, tz).strftime("%H:%M"),
                    "text": item.text or item.title or "提醒",
                })
        if kind == BRIEFING_EVENING:
            delivered = self.scheduling.delivered_between(
                principal, day_start.isoformat(), day_end.isoformat()
            )
            schedules = self.scheduling.upcoming(
                principal, until=(day_end + timedelta(days=1)).timestamp(), limit=50,
                content_kind="text", start=day_end.timestamp(),
            )
            for item in schedules:
                upcoming.append({
                    "time": datetime.fromtimestamp(item.next_run_at, tz).strftime("%H:%M"),
                    "text": item.text or item.title or "提醒",
                })
        if kind == BRIEFING_WEEKLY:
            # 周报统计“过去 7 天已送达”，而不是未来一周的 occurrence。
            delivered = self.scheduling.delivered_between(
                principal,
                (day_start - timedelta(days=6)).isoformat(),
                day_end.isoformat(),
            )
            upcoming = [item for item in upcoming if item["text"]]
        mood = {}
        care = False
        if kind == BRIEFING_MOOD_WEEKLY:
            week = self.profiles.weekly_mood_for_owner(principal.user_id, today=today)
            mood = {
                "sufficient": week.sufficient,
                "average": round(week.average, 1),
                "days": len(week.days),
                "labels": [label for label, _ in week.label_counts[:3]],
                "low_days": week.low_days,
                "missing_days": week.missing_days,
                "consecutive_low_days": week.consecutive_low_days,
            }
            # average 恒在 -2..2，不能作为“低落”阈值；只看实际低分天数。
            care = bool(week.sufficient and week.low_days >= 3)
        return BriefingData(
            kind=kind,
            local_date=today.isoformat(),
            timezone=timezone,
            upcoming=tuple(upcoming[:5]),
            delivered_today=delivered,
            upcoming_count=len(upcoming),
            inbox_unread=self._inbox_unread(principal.user_id),
            mood_opt_in=bool(profile.mood_opt_in),
            mood=mood,
            care=care,
        )

    def _inbox_unread(self, owner_id: int) -> int:
        if self.inbox is None:
            return 0
        try:
            return int(self.inbox.unread_count(owner_id))
        except Exception:  # noqa: BLE001  简报不能因收件箱故障失败
            return 0

    # ---- 模板 ------------------------------------------------------------------

    def _template(self, data: BriefingData) -> str:
        if data.kind == BRIEFING_MOOD_WEEKLY:
            return self._mood_template(data)
        if data.kind == BRIEFING_MORNING:
            if not data.upcoming and not data.inbox_unread and not data.mood_opt_in:
                return ""
            lines = [f"早上好。今天 {self._date_cn(data.local_date)}，星期{self._weekday(data.local_date)}。"]
            for item in data.upcoming:
                lines.append(f"• {item['time']} {item['text']}")
            if data.upcoming_count > len(data.upcoming):
                lines.append(f"另有 {data.upcoming_count - len(data.upcoming)} 条提醒。")
            if not data.upcoming:
                lines.append("今天没有排定的提醒。")
            if data.inbox_unread:
                lines.append(f"收件箱还有 {data.inbox_unread} 条没看。")
            if data.mood_opt_in:
                lines.append("今天感觉怎么样？")
            return "\n".join(lines)
        if data.kind == BRIEFING_EVENING:
            if not data.delivered_today and not data.upcoming:
                return ""
            lines = [f"今天已送达 {data.delivered_today} 条提醒。"]
            if data.upcoming:
                first = data.upcoming[0]
                lines.append(f"明天最早 {first['time']}：{first['text']}。")
            else:
                lines.append("明天暂时没有排定的提醒。")
            return "\n".join(lines)
        if data.kind == BRIEFING_WEEKLY:
            lines = [f"本周回顾（{self._date_cn(data.local_date)}）："]
            lines.append(f"• 已送达 {data.delivered_today} 条提醒。")
            if data.upcoming:
                first = data.upcoming[0]
                lines.append(
                    f"• 下周 {data.upcoming_count} 条，最早 {first['time']}：{first['text']}。"
                )
            else:
                lines.append("• 下周没有排定的提醒。")
            if data.inbox_unread:
                lines.append(f"• 收件箱未读 {data.inbox_unread} 条。")
            return "\n".join(lines)
        return ""

    def _mood_template(self, data: BriefingData) -> str:
        mood = data.mood
        if not mood.get("sufficient") or not data.mood_opt_in:
            return ""
        if data.care:
            return (
                "这几周有些天看起来不太轻松。先不用急着安排什么，"
                "照顾好吃饭和睡觉；如果愿意，说说今天最累的一件事。"
                "不想继续记录可以发 /情绪 关闭。"
            )
        average = mood.get("average", 0)
        days = mood.get("days", 0)
        labels = "、".join(str(x) for x in mood.get("labels") or []) or "平稳"
        return (
            f"本周情绪：平均 {average} 分（{days} 天记录），"
            f"常见感受是{labels}。下周也慢慢来。"
        )

    # ---- 受控生成 --------------------------------------------------------------

    async def _generate(self, data: BriefingData, fallback: str, *, owner_id: int) -> str:
        if self.generator is None:
            return ""
        allowed = self._allowed_tokens(data)
        system = (
            "你在写一条微信简报。只根据给定 JSON 事实，不编造。"
            "最多 5 行、300 字；不用 Markdown、标题、表格、代码块；"
            "不出现 JSON 里没有的数字或时间；语气自然，不用感叹号轰炸。"
        )
        user = json.dumps({
            "kind": data.kind,
            "date": data.local_date,
            "data": {
                "upcoming": list(data.upcoming),
                "upcoming_count": data.upcoming_count,
                "delivered_today": data.delivered_today,
                "inbox_unread": data.inbox_unread,
            },
            "template": fallback,
        }, ensure_ascii=False)
        try:
            text = await self.generator.generate(
                system, user, owner_id=owner_id, max_chars=300
            )
        except Exception:  # noqa: BLE001  生成失败回退模板
            return ""
        text = text.strip().strip("`").strip()
        if not text or len(text) > 300:
            return ""
        if "**" in text or "|" in text or "\n#" in text:
            return ""
        if not self._numbers_allowed(text, allowed):
            return ""
        return text

    def _allowed_tokens(self, data: BriefingData) -> set[str]:
        numbers = {
            str(data.delivered_today), str(data.upcoming_count),
            str(data.inbox_unread), str(len(data.upcoming)),
        }
        for part in re.findall(r"\d+", data.local_date):
            numbers.add(part)
        for item in data.upcoming:
            numbers.update(re.findall(r"\d+", str(item.get("time") or "")))
        if data.mood:
            numbers.update(re.findall(r"\d+", json.dumps(data.mood, ensure_ascii=False)))
        return numbers

    @staticmethod
    def _numbers_allowed(text: str, allowed: set[str]) -> bool:
        for token in re.findall(r"\d+", text):
            if token not in allowed:
                return False
        return True

    @staticmethod
    def _date_cn(iso: str) -> str:
        parsed = date.fromisoformat(iso)
        return f"{parsed.month} 月 {parsed.day} 日"

    @staticmethod
    def _weekday(iso: str) -> str:
        return _WEEKDAYS[date.fromisoformat(iso).weekday()]


def kind_label(kind: str) -> str:
    return BRIEFING_KIND_LABELS.get(kind, kind)
