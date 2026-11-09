"""profiles 公开接口：人格渲染、安静时段、情绪设置与按日情绪条目。

本模块不读会话原文；情绪采样由 ContentWorker 在用户 opt-in 后执行。
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.modules.profiles.contracts import (
    EMOJI_LEVELS,
    MAX_CUSTOM_INSTRUCTION,
    MAX_EVIDENCE_CHARS,
    MAX_MOOD_LABELS,
    MOOD_LABELS,
    PERSONA_CUSTOM,
    PERSONA_PRESETS,
    PERSONA_WARM,
    PROACTIVITY_LEVELS,
    CareDecision,
    MoodDeleteResult,
    MoodEntry,
    MoodWeek,
    ProfileView,
    QuietWindow,
)
from backend.modules.profiles.repository import ProfilesRepository
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import InvalidInputError

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Asia/Shanghai"
_PRESET_RULES = {
    "warm": "温和但不腻；先接住，再给建议",
    "concise": "直接给结论，少寒暄",
    "playful": "轻松一点，可轻度调侃",
    "direct": "不绕弯，允许直接指出问题",
}
_EMOJI_RULES = {
    "none": "不要使用 emoji",
    "sparse": "最多 1 个 emoji",
    "rich": "可适量使用 emoji，但不要堆砌",
}
class ProfilesService:
    def __init__(
        self,
        db: Database,
        *,
        access: Any,
        clock=time.time,
        default_timezone: str = DEFAULT_TIMEZONE,
        queue: Any = None,
        generator: Any = None,
        care_canceller: Any = None,
    ) -> None:
        self.db = db
        self.repo = ProfilesRepository(db)
        self.access = access
        self.clock = clock
        self.default_timezone = _valid_timezone(default_timezone)
        self.queue = queue
        self.generator = generator
        # bootstrap 注入的窄取消接口：只取消该 owner 的 pending care delivery。
        # profiles 不 import delivery，保持模块边界。
        self.care_canceller = care_canceller

    # ---- 人格 ------------------------------------------------------------------

    def get(self, actor: Principal) -> ProfileView:
        principal = self.access.validate_principal(actor)
        return self._ensure(principal.user_id)

    def get_by_owner(self, owner_id: int) -> ProfileView:
        return self._ensure(int(owner_id))

    def mood_context_tx(self, conn, owner_id: int) -> tuple[bool, str] | None:
        """run 终态事务内读取 opt-in/时区；不创建 profile，不暴露 repository。"""
        profile = self.repo.get_tx(conn, int(owner_id))
        if profile is None:
            return None
        return profile.mood_opt_in, profile.timezone

    def update(self, actor: Principal, **fields: Any) -> ProfileView:
        principal = self.access.validate_principal(actor)
        self._ensure(principal.user_id)
        clean = _validate_update(fields)
        profile = self.repo.update(principal.user_id, clean)
        # 主动性降到 low 后，已经入队的 care 也不能再发；repo 同时推进 care 代际，
        # 让已经进入 sending 的迟到回调也无法重新记账。
        if profile.proactivity == "low":
            self._cancel_inflight_care(principal.user_id)
        return profile

    def set_mood_enabled(self, actor: Principal, enabled: bool) -> ProfileView:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "memory.edit")
        if enabled:
            return self.update(principal, mood_opt_in=1)
        # 先取消队列/账本里的在途 care，再关闭 opt-in；关闭后 callback 还会二次校验。
        self._cancel_inflight_care(principal.user_id)
        profile = self.update(principal, mood_opt_in=0)
        self._cancel_inflight_care(principal.user_id)
        self._purge_sample_payloads(principal.user_id)
        return profile

    def enable_mood_for_owner(self, owner_id: int, enabled: bool) -> ProfileView:
        self._ensure(owner_id)
        if enabled:
            profile = self.repo.update(owner_id, {"mood_opt_in": 1})
            if profile.proactivity == "low":
                self._cancel_inflight_care(int(owner_id))
            return profile
        self._cancel_inflight_care(int(owner_id))
        profile = self.repo.update(owner_id, {"mood_opt_in": 0})
        self._cancel_inflight_care(int(owner_id))
        self._purge_sample_payloads(int(owner_id))
        return profile

    def timezone_for(self, owner_id: int) -> str:
        return self._ensure(int(owner_id)).timezone

    def render_persona(self, owner_id: int, surface: str = "wechat") -> str:
        profile = self._ensure(int(owner_id))
        rule = _PRESET_RULES.get(profile.persona_preset, _PRESET_RULES[PERSONA_WARM])
        if profile.persona_preset == PERSONA_CUSTOM and profile.custom_instruction:
            rule = profile.custom_instruction.strip() or rule
        # proactivity 只驱动 C3 的确定性关怀任务，不进入普通回复提示词，
        # 否则模型会自行“主动关心”，绕过频率上限与安静时段。
        lines = [
            f"【说话方式】{rule}；称呼用户为「{profile.address_form.strip() or '你'}」。",
            f"【风格】{_EMOJI_RULES[profile.emoji_level]}。",
        ]
        if surface == "wechat":
            lines.append(
                f"微信里最多 {profile.max_chars} 字，最多 5 行；"
                "不要标题、表格、代码块；不确定就说「没查到」，不要编。一次只问一个问题。"
            )
        else:
            lines.append("不确定就说「没查到」，不要编。一次只问一个问题。")
        return "\n".join(lines)

    def quiet_window(self, owner_id: int, now: float | None = None) -> QuietWindow:
        profile = self._ensure(int(owner_id))
        tz = ZoneInfo(profile.timezone)
        current = datetime.fromtimestamp(self.clock() if now is None else float(now), tz)
        start = _parse_hhmm(profile.quiet_start)
        end = _parse_hhmm(profile.quiet_end)
        if start == end:
            return QuietWindow(active=False, end_epoch=current.timestamp(), timezone=profile.timezone)
        minute = current.hour * 60 + current.minute
        start_m, end_m = start[0] * 60 + start[1], end[0] * 60 + end[1]
        if start_m < end_m:
            active = start_m <= minute < end_m
        else:
            active = minute >= start_m or minute < end_m
        end_dt = current.replace(hour=end[0], minute=end[1], second=0, microsecond=0)
        if end_dt <= current:
            end_dt += timedelta(days=1)
        return QuietWindow(active=active, end_epoch=end_dt.timestamp(), timezone=profile.timezone)

    def in_quiet_hours(self, owner_id: int, now: float | None = None) -> bool:
        return self.quiet_window(owner_id, now).active

    # ---- 情绪 ------------------------------------------------------------------

    def mood_entry(self, actor: Principal, entry_date: str) -> MoodEntry | None:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "memory.view")
        return self.repo.get_mood(principal.user_id, entry_date)

    def list_mood(self, actor: Principal, *, days: int = 7) -> list[MoodEntry]:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "memory.view")
        profile = self._ensure(principal.user_id)
        today = datetime.fromtimestamp(self.clock(), ZoneInfo(profile.timezone)).date()
        start = (today - timedelta(days=max(1, days) - 1)).isoformat()
        return self.repo.list_mood(principal.user_id, start=start, end=today.isoformat())

    def record_mood(
        self,
        actor: Principal,
        *,
        entry_date: str,
        score: int,
        labels: tuple[str, ...],
        evidence: tuple[str, ...],
        summary: str = "",
        source_run_id: str = "",
    ) -> MoodEntry | None:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "memory.edit")
        return self.record_mood_for_owner(
            principal.user_id, entry_date=entry_date, score=score, labels=labels,
            evidence=evidence, summary=summary, source_run_id=source_run_id,
        )

    def record_mood_for_owner(
        self,
        owner_id: int,
        *,
        entry_date: str,
        score: int,
        labels: tuple[str, ...],
        evidence: tuple[str, ...],
        summary: str = "",
        source_run_id: str = "",
    ) -> MoodEntry | None:
        """后台采样入口：调用方已确认用户 opt-in 与 owner；仍做数据边界校验。"""
        profile = self._ensure(int(owner_id))
        if not profile.mood_opt_in:
            return None
        _validate_date(entry_date)
        if not -2 <= int(score) <= 2:
            raise InvalidInputError("情绪分数必须在 -2..2")
        clean_labels = tuple(dict.fromkeys(str(label) for label in labels))
        if len(clean_labels) > MAX_MOOD_LABELS:
            raise InvalidInputError("情绪标签最多 3 个")
        unknown = set(clean_labels) - MOOD_LABELS
        if unknown:
            raise InvalidInputError(f"未知情绪标签: {sorted(unknown)}")
        clean_evidence = tuple(str(text).strip() for text in evidence if str(text).strip())
        if len(clean_evidence) > 3:
            raise InvalidInputError("情绪证据最多 3 条")
        for text in clean_evidence:
            if len(text) > MAX_EVIDENCE_CHARS:
                raise InvalidInputError("情绪证据必须是原文短引文（≤60 字）")
        if abs(int(score)) < 1 and not clean_labels:
            return None
        if source_run_id:
            claimed = self.repo.claim_mood_sample(
                int(owner_id), source_run_id, entry_date
            )
            if not claimed:
                return (
                    self.repo.find_by_run(int(owner_id), source_run_id)
                    or self.repo.get_mood(int(owner_id), entry_date)
                )
        existing = self.repo.get_mood(int(owner_id), entry_date)
        if existing is not None:
            conn = self.db.connect()
            try:
                row = conn.execute(
                    "SELECT sample_count FROM mood_entries WHERE owner_id=? AND entry_date=?",
                    (int(owner_id), entry_date),
                ).fetchone()
                count = int(row["sample_count"] or 1) if row else 1
            finally:
                conn.close()
            if count >= 10:
                return existing
        try:
            return self.repo.upsert_mood(
                owner_id=int(owner_id), entry_date=entry_date, score=int(score),
                labels=clean_labels, evidence=clean_evidence, summary=summary[:200],
                source_run_id=source_run_id,
            )
        except Exception:
            if source_run_id:
                self.repo.release_mood_sample(int(owner_id), source_run_id)
            raise

    def sample_run_for_owner(
        self, owner_id: int, text: str, *, run_id: str, entry_date: str = ""
    ) -> MoodEntry | None:
        """确定性情绪采样：只看用户文字里的显式情绪词，不做诊断。"""
        profile = self._ensure(int(owner_id))
        if not profile.mood_opt_in or len(text.strip()) < 4 or not run_id:
            return None
        already = self.repo.find_by_run(int(owner_id), run_id)
        if already is not None:
            # JobQueue 已按 run 去重；这里再防运维补跑/重放跨天重复累加。
            return already
        positive = ("开心", "高兴", "顺利", "喜欢", "不错", "充实", "轻松", "期待", "感谢", "满足")
        negative = {
            "焦虑": ("焦虑", "紧张", "担心", "压力", "不安"),
            "疲惫": ("累", "疲惫", "熬夜", "失眠", "困"),
            "生气": ("生气", "烦", "恼火", "气死"),
            "低落": ("难过", "低落", "失望", "委屈", "孤独", "想哭", "崩溃"),
            "孤独": ("孤独", "一个人", "没人"),
        }
        topics = {
            "工作": ("工作", "上班", "项目", "客户"), "加班": ("加班", "熬夜"),
            "睡眠": ("失眠", "睡不着", "睡眠"), "关系": ("关系", "对象", "朋友", "吵架"),
            "健康": ("生病", "医院", "身体", "头疼"), "家庭": ("家里", "父母", "孩子"),
            "学习": ("考试", "学习", "论文"), "金钱": ("钱", "工资", "房租", "账单"),
        }
        pos = sum(1 for word in positive if word in text)
        matched_negative = [label for label, words in negative.items() if any(w in text for w in words)]
        if not pos and not matched_negative:
            return None
        if matched_negative:
            score = -2 if any(w in text for w in ("崩溃", "绝望", "想哭", "失眠")) else -1
        else:
            score = 2 if pos >= 2 else 1
        labels = ["开心"] if pos and not matched_negative else matched_negative[:2]
        for label, words in topics.items():
            if any(word in text for word in words):
                labels.append(label)
        labels = [label for label in dict.fromkeys(labels) if label in MOOD_LABELS][:3]
        sentence = next(
            (part.strip() for part in re.split(r"[。！？!?\n]", text)
             if any(word in part for word in (*positive, *(w for words in negative.values() for w in words)))),
            text.strip(),
        )
        return self.record_mood_for_owner(
            int(owner_id), entry_date=self._entry_date(profile, entry_date),
            score=score, labels=tuple(labels),
            evidence=(sentence[:MAX_EVIDENCE_CHARS],), summary="", source_run_id=run_id,
        )

    async def sample_run_for_owner_async(
        self, owner_id: int, text: str, *, run_id: str, entry_date: str = ""
    ) -> MoodEntry | None:
        """优先走受控 JSON 分类；无生成器时回退确定性词表。

        模型失败、非 JSON、标签越界或证据不是原文子串时按规范跳过当天，
        不重试、不猜，也不把用户原文写日志。
        """
        profile = self._ensure(int(owner_id))
        if not profile.mood_opt_in or len(text.strip()) < 4 or not run_id:
            return None
        already = self.repo.find_by_run(int(owner_id), run_id)
        if already is not None:
            return already
        if self.generator is None:
            return self.sample_run_for_owner(
                owner_id, text, run_id=run_id, entry_date=entry_date
            )
        raw = await self.generator.generate(
            "你是情绪记录器。只输出一个 JSON 对象，不要解释、不要 markdown。"
            '格式：{"score": -2..2 的整数, "labels": 最多 3 个固定标签, '
            '"evidence": 原文中的一句短引文（≤60 字）}。'
            f"固定标签只能是：{'/'.join(sorted(MOOD_LABELS))}。"
            "不做诊断，不编造原文没有的内容；无法判断时输出 "
            '{"score": 0, "labels": [], "evidence": ""}。',
            text,
            owner_id=int(owner_id),
            max_chars=400,
        )
        parsed = _parse_model_mood(raw, text)
        if parsed is None:
            return None
        score, labels, evidence = parsed
        return self.record_mood_for_owner(
            int(owner_id), entry_date=self._entry_date(profile, entry_date),
            score=score, labels=labels,
            evidence=(evidence,) if evidence else (), summary="", source_run_id=run_id,
        )

    def _entry_date(self, profile: ProfileView, entry_date: str) -> str:
        if entry_date:
            try:
                return date.fromisoformat(entry_date).isoformat()
            except ValueError:
                pass
        return datetime.fromtimestamp(
            self.clock(), ZoneInfo(profile.timezone)
        ).date().isoformat()

    def care_due(self, owner_id: int) -> CareDecision | None:
        """连续 3 个自然日偏低且 7 天未主动关心时，生成固定两句关怀。"""
        profile = self._ensure(int(owner_id))
        if not profile.mood_opt_in or profile.proactivity == "low":
            return None
        today = datetime.fromtimestamp(
            self.clock(), ZoneInfo(profile.timezone)
        ).date()
        start = today - timedelta(days=2)
        entries = self.repo.list_mood(
            int(owner_id), start=start.isoformat(), end=today.isoformat()
        )
        by_date = {entry.entry_date: entry for entry in entries}
        if len(by_date) < 3:
            return None
        recent = [by_date.get((start + timedelta(days=i)).isoformat()) for i in range(3)]
        if any(entry is None or entry.score > -1 for entry in recent):
            return None
        now = self.clock()
        last_epoch = 0.0
        if profile.last_care_at:
            try:
                last_epoch = datetime.fromisoformat(profile.last_care_at).timestamp()
            except ValueError:
                last_epoch = 0.0
        if profile.proactivity == "high":
            # high：距上次 ≥3 天，且最近 7 天成功主动关心 <2 次。
            if last_epoch and now - last_epoch < 3 * 24 * 3600:
                return None
            from datetime import timezone

            since = datetime.fromtimestamp(
                now - 7 * 24 * 3600, timezone.utc
            ).isoformat()
            if self.repo.care_count_since(int(owner_id), since) >= 2:
                return None
        elif last_epoch and now - last_epoch < 7 * 24 * 3600:
            return None
        labels: list[str] = []
        for entry in reversed(recent):
            if entry is not None:
                labels.extend(label for label in entry.labels if label not in labels)
        if labels:
            message = f"这两天你提到{'、'.join(labels[:2])}。不用马上回，我在。"
        else:
            message = "这两天看起来不太轻松。不用马上回，我在。"
        return CareDecision(message=message, local_date=today.isoformat())

    def mark_care_sent(
        self,
        owner_id: int,
        at_iso: str = "",
        *,
        care_key: str = "",
        delivery_created_at: str = "",
    ) -> bool:
        """投递 sent 回调；repo 在同一写事务内校验 opt-in 与 care 代际。"""
        if not at_iso:
            from datetime import timezone

            at_iso = datetime.fromtimestamp(
                self.clock(), timezone.utc
            ).isoformat()
        return self.repo.mark_care_sent(
            int(owner_id),
            at_iso,
            care_key=care_key,
            delivery_created_at=delivery_created_at,
        )

    def weekly_mood(self, actor: Principal, *, today: date | None = None) -> MoodWeek:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "memory.view")
        return self.weekly_mood_for_owner(principal.user_id, today=today)

    def weekly_mood_for_owner(self, owner_id: int, *, today: date | None = None) -> MoodWeek:
        profile = self._ensure(int(owner_id))
        if not profile.mood_opt_in:
            return MoodWeek()
        local_today = today or datetime.fromtimestamp(
            self.clock(), ZoneInfo(profile.timezone)
        ).date()
        start = local_today - timedelta(days=6)
        week = self.repo.week(int(owner_id), start.isoformat(), local_today.isoformat())
        self._purge_old(profile)
        return week

    def delete_mood(self, actor: Principal) -> MoodDeleteResult:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "memory.edit")
        # 两段取消夹住删除事务：前段减少竞态窗口，后段兜住删除提交前刚入队的 care。
        self._cancel_inflight_care(principal.user_id)
        deleted = self.repo.delete_mood(principal.user_id)
        self._cancel_inflight_care(principal.user_id)
        self.repo.purge_mood_samples(principal.user_id)
        self._purge_sample_payloads(principal.user_id)
        return MoodDeleteResult(deleted=deleted)

    def purge_expired_mood(self) -> int:
        total = 0
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT owner_id, mood_retention_days, timezone FROM assistant_profiles"
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            profile = self._ensure(int(row["owner_id"]))
            total += self._purge_old(profile)
        return total

    # ---- 内部 ------------------------------------------------------------------

    def _cancel_inflight_care(self, owner_id: int) -> None:
        """作废该 owner 的 pending care job 与 delivery；sending 只能靠 callback 守卫。"""
        purge = getattr(self.queue, "purge_payloads", None)
        if purge is not None:
            try:
                purge(int(owner_id), "mood.care")
            except Exception:  # noqa: BLE001  删除/关闭不应因队列清理失败而回滚
                logger.exception("清理关怀任务失败 owner=%s", owner_id)
        cancel = self.care_canceller
        if cancel is not None:
            try:
                cancel(int(owner_id))
            except Exception:  # noqa: BLE001  账本取消失败仍要靠 callback 二次校验兜底
                logger.exception("取消在途关怀投递失败 owner=%s", owner_id)

    def _purge_sample_payloads(self, owner_id: int) -> None:
        purge = getattr(self.queue, "purge_payloads", None)
        if purge is not None:
            try:
                purge(int(owner_id), "mood.sample")
            except Exception:  # noqa: BLE001  删除情绪数据不应因队列清理失败而回滚
                logger.exception("清理情绪采样任务 payload 失败 owner=%s", owner_id)

    def _purge_old(self, profile: ProfileView) -> int:
        from datetime import time as dtime
        from datetime import timezone

        today = datetime.fromtimestamp(self.clock(), ZoneInfo(profile.timezone)).date()
        cutoff_date = today - timedelta(days=max(1, profile.mood_retention_days))
        cutoff = cutoff_date.isoformat()
        cutoff_dt = datetime.combine(
            cutoff_date, dtime.min, ZoneInfo(profile.timezone)
        ).astimezone(timezone.utc).isoformat()
        self.repo.purge_mood_samples_before(profile.owner_id, cutoff)
        self.repo.delete_care_logs_before(profile.owner_id, cutoff_dt)
        return self.repo.purge_before(profile.owner_id, cutoff)

    def _ensure(self, owner_id: int) -> ProfileView:
        current = self.repo.get(int(owner_id))
        if current is not None:
            return current
        return self.repo.ensure(int(owner_id), timezone=self.default_timezone)


def _parse_model_mood(raw: str, text: str) -> tuple[int, tuple[str, ...], str] | None:
    """严格校验模型 JSON；任何越界/编造都按失败跳过，不允许“猜一个”。"""
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    score = data.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not -2 <= score <= 2:
        return None
    labels_raw = data.get("labels")
    if not isinstance(labels_raw, list) or len(labels_raw) > MAX_MOOD_LABELS:
        return None
    labels: list[str] = []
    for label in labels_raw:
        if not isinstance(label, str) or label not in MOOD_LABELS:
            return None
        if label not in labels:
            labels.append(label)
    evidence = data.get("evidence", "")
    if not isinstance(evidence, str):
        return None
    evidence = evidence.strip()
    if len(evidence) > MAX_EVIDENCE_CHARS:
        return None
    if evidence and evidence not in text:
        return None
    if abs(score) < 1 and not labels:
        return None
    return score, tuple(labels), evidence


def _valid_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidInputError(f"无效时区: {name}") from exc
    return name


def _parse_hhmm(value: str) -> tuple[int, int]:
    text = (value or "").strip()
    try:
        hour, minute = text.split(":")
        hour_i, minute_i = int(hour), int(minute)
    except (ValueError, AttributeError) as exc:
        raise InvalidInputError(f"时间必须是 HH:MM，收到: {value}") from exc
    if not (0 <= hour_i < 24 and 0 <= minute_i < 60):
        raise InvalidInputError(f"时间越界: {value}")
    return hour_i, minute_i


def _validate_date(value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidInputError(f"日期必须是 YYYY-MM-DD: {value}") from exc


def _validate_update(fields: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        if key == "persona_preset":
            if str(value) not in PERSONA_PRESETS:
                raise InvalidInputError(f"未知人格预设: {value}")
            clean[key] = str(value)
        elif key == "address_form":
            text = str(value).strip()
            if not text or len(text) > 12:
                raise InvalidInputError("称呼不能为空且不超过 12 字")
            clean[key] = text
        elif key == "max_chars":
            number = int(value)
            if not 40 <= number <= 1000:
                raise InvalidInputError("max_chars 必须在 40..1000")
            clean[key] = number
        elif key == "emoji_level":
            if str(value) not in EMOJI_LEVELS:
                raise InvalidInputError("emoji_level 只能是 none/sparse/rich")
            clean[key] = str(value)
        elif key == "proactivity":
            if str(value) not in PROACTIVITY_LEVELS:
                raise InvalidInputError("proactivity 只能是 low/normal/high")
            clean[key] = str(value)
        elif key in ("quiet_start", "quiet_end"):
            _parse_hhmm(str(value))
            clean[key] = str(value).strip()
        elif key == "timezone":
            clean[key] = _valid_timezone(str(value))
        elif key == "custom_instruction":
            text = str(value).strip()
            if len(text) > MAX_CUSTOM_INSTRUCTION:
                raise InvalidInputError(f"自定义人格不能超过 {MAX_CUSTOM_INSTRUCTION} 字")
            clean[key] = text
        elif key == "mood_opt_in":
            clean[key] = 1 if value else 0
        elif key == "mood_retention_days":
            number = int(value)
            if not 1 <= number <= 3650:
                raise InvalidInputError("mood_retention_days 必须在 1..3650")
            clean[key] = number
        elif key == "last_care_at":
            clean[key] = str(value) if value else None
        else:
            raise InvalidInputError(f"不支持的 profile 字段: {key}")
    # 自定义人格允许空指令（回退 warm 风格），不强行拒绝。
    return clean


def profile_as_dict(profile: ProfileView) -> dict[str, Any]:
    return {
        "owner_id": profile.owner_id,
        "persona_preset": profile.persona_preset,
        "address_form": profile.address_form,
        "max_chars": profile.max_chars,
        "emoji_level": profile.emoji_level,
        "proactivity": profile.proactivity,
        "quiet_start": profile.quiet_start,
        "quiet_end": profile.quiet_end,
        "timezone": profile.timezone,
        "custom_instruction": profile.custom_instruction,
        "mood_opt_in": profile.mood_opt_in,
        "mood_retention_days": profile.mood_retention_days,
        "last_care_at": profile.last_care_at,
        "persona_revision": profile.persona_revision,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def mood_as_dict(entry: MoodEntry) -> dict[str, Any]:
    return {
        "id": entry.entry_id,
        "entry_date": entry.entry_date,
        "score": entry.score,
        "labels": list(entry.labels),
        "summary": entry.summary,
        "evidence": list(entry.evidence),
        "source_run_id": entry.source_run_id,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }
