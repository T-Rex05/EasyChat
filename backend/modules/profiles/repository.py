"""profiles 数据访问：assistant_profiles 与 mood_entries（模块内唯一 SQL）。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from backend.modules.profiles.contracts import (
    MOOD_RETENTION_DEFAULT,
    MoodEntry,
    MoodWeek,
    ProfileView,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.identifiers import new_mood_id


def _profile(row: Any) -> ProfileView:
    data = dict(row)
    return ProfileView(
        owner_id=int(data["owner_id"]),
        persona_preset=str(data["persona_preset"]),
        address_form=str(data["address_form"]),
        max_chars=int(data["max_chars"]),
        emoji_level=str(data["emoji_level"]),
        proactivity=str(data["proactivity"]),
        quiet_start=str(data["quiet_start"]),
        quiet_end=str(data["quiet_end"]),
        timezone=str(data["timezone"]),
        custom_instruction=str(data["custom_instruction"]),
        mood_opt_in=bool(data["mood_opt_in"]),
        mood_retention_days=int(data["mood_retention_days"]),
        last_care_at=data.get("last_care_at"),
        persona_revision=int(data["persona_revision"]),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
    )


def _timestamp_not_before(left: str, right: str) -> bool:
    """判断 left 是否不早于 right；解析失败按“已变更”保守处理。"""
    try:
        return datetime.fromisoformat(left) >= datetime.fromisoformat(right)
    except (TypeError, ValueError):
        return True


def _mood(row: Any) -> MoodEntry:
    data = dict(row)
    return MoodEntry(
        entry_id=str(data["id"]),
        owner_id=int(data["owner_id"]),
        entry_date=str(data["entry_date"]),
        score=int(data["score"]),
        labels=tuple(json.loads(data.get("labels_json") or "[]")),
        summary=str(data.get("summary") or ""),
        evidence=tuple(json.loads(data.get("evidence_json") or "[]")),
        source_run_id=str(data.get("source_run_id") or ""),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
    )


class ProfilesRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure(self, owner_id: int, *, timezone: str = "Asia/Shanghai") -> ProfileView:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO assistant_profiles(owner_id, timezone, mood_retention_days, "
                "created_at, updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(owner_id) DO NOTHING",
                (owner_id, timezone, MOOD_RETENTION_DEFAULT, now, now),
            )
        return self.get(owner_id)

    def get(self, owner_id: int) -> ProfileView | None:
        conn = self.db.connect()
        try:
            return self.get_tx(conn, owner_id)
        finally:
            conn.close()

    def get_tx(self, conn: Any, owner_id: int) -> ProfileView | None:
        row = conn.execute(
            "SELECT * FROM assistant_profiles WHERE owner_id=?", (owner_id,)
        ).fetchone()
        return _profile(row) if row else None

    def update(self, owner_id: int, fields: dict[str, Any]) -> ProfileView:
        allowed = {
            "persona_preset", "address_form", "max_chars", "emoji_level", "proactivity",
            "quiet_start", "quiet_end", "timezone", "custom_instruction", "mood_opt_in",
            "mood_retention_days", "last_care_at",
        }
        sets = {key: value for key, value in fields.items() if key in allowed}
        now = utc_now_iso()
        # 只有真正让 care 失效的状态变化才推进代际；普通资料更新不能误伤已发出的 care。
        if sets.get("mood_opt_in") == 0 or sets.get("proactivity") == "low":
            sets["care_epoch_at"] = now
        with self.db.transaction() as conn:
            sets["persona_revision"] = "persona_revision + 1"
            assignments = []
            params: list[Any] = []
            for key in sets:
                if key == "persona_revision":
                    assignments.append("persona_revision = persona_revision + 1")
                else:
                    assignments.append(f"{key}=?")
                    params.append(sets[key])
            assignments.append("updated_at=?")
            params.extend([now, owner_id])
            cur = conn.execute(
                f"UPDATE assistant_profiles SET {', '.join(assignments)} WHERE owner_id=?",
                params,
            )
            if cur.rowcount != 1:
                raise LookupError(f"profile 不存在: {owner_id}")
        return self.get(owner_id)  # type: ignore[return-value]

    # ---- mood ----------------------------------------------------------------

    def get_mood(self, owner_id: int, entry_date: str) -> MoodEntry | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM mood_entries WHERE owner_id=? AND entry_date=?",
                (owner_id, entry_date),
            ).fetchone()
            return _mood(row) if row else None
        finally:
            conn.close()

    def claim_mood_sample(
        self, owner_id: int, run_id: str, entry_date: str, *, daily_cap: int = 10
    ) -> bool:
        """原子登记一次采样；同一 run 只成功一次，按日限额。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT count(*) AS c FROM mood_samples WHERE owner_id=? AND entry_date=?",
                (int(owner_id), entry_date),
            ).fetchone()
            if row is not None and int(row["c"]) >= daily_cap:
                return False
            cur = conn.execute(
                "INSERT INTO mood_samples(id, owner_id, run_id, entry_date, created_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(owner_id, run_id) DO NOTHING",
                (new_mood_id(), int(owner_id), run_id, entry_date, now),
            )
            return cur.rowcount == 1

    def release_mood_sample(self, owner_id: int, run_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM mood_samples WHERE owner_id=? AND run_id=?",
                (int(owner_id), run_id),
            )

    def purge_mood_samples(self, owner_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM mood_samples WHERE owner_id=?", (int(owner_id),))

    def purge_mood_samples_before(self, owner_id: int, cutoff: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM mood_samples WHERE owner_id=? AND entry_date<?",
                (int(owner_id), cutoff),
            )

    def list_mood(self, owner_id: int, *, start: str | None = None, end: str | None = None,
                  limit: int = 400) -> list[MoodEntry]:
        sql = "SELECT * FROM mood_entries WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if start:
            sql += " AND entry_date>=?"
            params.append(start)
        if end:
            sql += " AND entry_date<=?"
            params.append(end)
        sql += " ORDER BY entry_date ASC LIMIT ?"
        params.append(limit)
        conn = self.db.connect()
        try:
            return [_mood(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def upsert_mood(
        self, *,
        owner_id: int,
        entry_date: str,
        score: int,
        labels: tuple[str, ...],
        evidence: tuple[str, ...],
        summary: str,
        source_run_id: str,
    ) -> MoodEntry:
        """同日多条：算术平均分数；证据最多 3 条；标签并集最多 3 个。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM mood_entries WHERE owner_id=? AND entry_date=?",
                (owner_id, entry_date),
            ).fetchone()
            if row is None:
                entry_id = new_mood_id()
                conn.execute(
                    "INSERT INTO mood_entries(id, owner_id, entry_date, score, score_total, "
                    "sample_count, labels_json, summary, evidence_json, source_run_id, "
                    "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        entry_id, owner_id, entry_date, score, score, 1,
                        json.dumps(list(labels), ensure_ascii=False),
                        summary, json.dumps(list(evidence), ensure_ascii=False),
                        source_run_id, now, now,
                    ),
                )
            else:
                old = _mood(row)
                old_count = int(row["sample_count"] or 1)
                if old_count >= 10:
                    # 每日最多 10 条；超限不再改变当天均值。
                    return old
                total = int(row["score_total"] or old.score)
                new_count = old_count + 1
                avg = _round_div(total + score, new_count)
                merged_labels = tuple(dict.fromkeys((*old.labels, *labels)))[:3]
                merged_evidence = tuple(dict.fromkeys((*old.evidence, *evidence)))[:3]
                conn.execute(
                    "UPDATE mood_entries SET score=?, score_total=?, sample_count=?, "
                    "labels_json=?, summary=?, evidence_json=?, source_run_id=?, updated_at=? "
                    "WHERE owner_id=? AND entry_date=?",
                    (
                        avg, total + score, new_count,
                        json.dumps(list(merged_labels), ensure_ascii=False),
                        summary or old.summary, json.dumps(list(merged_evidence), ensure_ascii=False),
                        source_run_id or old.source_run_id, now, owner_id, entry_date,
                    ),
                )
        return self.get_mood(owner_id, entry_date)  # type: ignore[return-value]

    def mark_care_sent(
        self,
        owner_id: int,
        at_iso: str,
        *,
        care_key: str = "",
        delivery_created_at: str = "",
    ) -> bool:
        """记录成功发送；在同一写事务内校验 opt-in 与 care 代际，避免删除竞态。"""
        from datetime import timedelta

        if care_key:
            digest = hashlib.sha256(
                f"{int(owner_id)}:{care_key}".encode("utf-8")
            ).hexdigest()[:24]
            care_id = f"mcl_{digest}"
        else:
            care_id = new_mood_id()
        cutoff = (datetime.fromisoformat(at_iso) - timedelta(days=7)).isoformat()
        with self.db.transaction() as conn:
            # 关键：检查和写入必须共享同一个 BEGIN IMMEDIATE，否则
            # delete_mood/关闭可以在检查通过后、INSERT 前提交，导致 care 复活。
            profile = conn.execute(
                "SELECT mood_opt_in, care_epoch_at FROM assistant_profiles WHERE owner_id=?",
                (int(owner_id),),
            ).fetchone()
            if profile is None or not int(profile["mood_opt_in"]):
                return False
            epoch = str(profile["care_epoch_at"] or "")
            if delivery_created_at and epoch and _timestamp_not_before(
                epoch, delivery_created_at
            ):
                return False
            cur = conn.execute(
                "INSERT INTO mood_care_log(id, owner_id, cared_at, created_at) "
                "VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (care_id, int(owner_id), at_iso, utc_now_iso()),
            )
            if cur.rowcount != 1:
                return False
            conn.execute(
                "UPDATE assistant_profiles SET last_care_at=?, updated_at=? WHERE owner_id=?",
                (at_iso, utc_now_iso(), int(owner_id)),
            )
            conn.execute(
                "DELETE FROM mood_care_log WHERE owner_id=? AND cared_at<?",
                (int(owner_id), cutoff),
            )
            return True

    def delete_care_logs_before(self, owner_id: int, cutoff_iso: str) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM mood_care_log WHERE owner_id=? AND cared_at<?",
                (int(owner_id), cutoff_iso),
            )
            return int(cur.rowcount)

    def care_count_since(self, owner_id: int, since_iso: str) -> int:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT count(*) AS c FROM mood_care_log WHERE owner_id=? AND cared_at>=?",
                (int(owner_id), since_iso),
            ).fetchone()
            return int(row["c"]) if row is not None else 0
        finally:
            conn.close()

    def find_by_run(self, owner_id: int, source_run_id: str) -> MoodEntry | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM mood_entries WHERE owner_id=? AND source_run_id=? "
                "ORDER BY entry_date DESC LIMIT 1",
                (int(owner_id), source_run_id),
            ).fetchone()
        finally:
            conn.close()
        return _mood(row) if row is not None else None

    def delete_mood(self, owner_id: int) -> int:
        """删除全部情绪数据，并同时关闭 opt-in、清空 last_care_at。"""
        with self.db.transaction() as conn:
            now = utc_now_iso()
            conn.execute(
                "UPDATE assistant_profiles SET mood_opt_in=0, last_care_at=NULL, "
                "care_epoch_at=?, updated_at=? WHERE owner_id=?",
                (now, now, owner_id),
            )
            cur = conn.execute("DELETE FROM mood_entries WHERE owner_id=?", (owner_id,))
            conn.execute("DELETE FROM mood_care_log WHERE owner_id=?", (owner_id,))
            return int(cur.rowcount)

    def purge_before(self, owner_id: int, cutoff_date: str) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM mood_entries WHERE owner_id=? AND entry_date<?",
                (owner_id, cutoff_date),
            )
            return int(cur.rowcount)

    def week(self, owner_id: int, start: str, end: str) -> MoodWeek:
        days = tuple(self.list_mood(owner_id, start=start, end=end, limit=7))
        counts: dict[str, int] = {}
        for day in days:
            for label in day.labels:
                counts[label] = counts.get(label, 0) + 1
        low_days = sum(1 for day in days if day.score <= -1)
        missing = max(0, 7 - len(days))
        consecutive = _consecutive_low(days)
        avg = round(sum(d.score for d in days) / len(days), 2) if days else 0.0
        return MoodWeek(
            days=days,
            average=avg,
            label_counts=tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            low_days=low_days,
            missing_days=missing,
            sufficient=len(days) >= 2,
            consecutive_low_days=consecutive,
        )


def _round_div(numerator: int, denominator: int) -> int:
    """四舍五入（half away from zero），避免 Python round 的银行家舍入。"""
    if denominator <= 0:
        return 0
    if numerator >= 0:
        return (numerator + denominator // 2) // denominator
    return -((-numerator + denominator // 2) // denominator)


def _consecutive_low(days: tuple[MoodEntry, ...]) -> int:
    """末尾连续低分天数；缺失日期不进入 days，因此自动中断。"""
    from datetime import date

    streak = 0
    expected: date | None = None
    for day in reversed(days):
        parsed = date.fromisoformat(day.entry_date)
        if expected is not None and (expected - parsed).days != 1:
            break
        if day.score > -1:
            break
        streak += 1
        expected = parsed
    return streak
