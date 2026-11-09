"""usage 模块 SQLite 数据访问：明细与日汇总同事务写入。

daily_user_stats 按 stat_date(上海时区) + user_id + source 唯一；
所有变更通过差额(delta)更新，保证重复回调/晚到补全不重复累计。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.modules.usage.contracts import NormalizedUsage
from backend.platform.sqlite import Database

# 项目时区（架构 §5.2：初始 Asia/Shanghai，UTC+8 无夏令时）
_PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def stat_date_for(utc_dt: datetime) -> str:
    """UTC 时间 → 项目时区日期（YYYY-MM-DD）。时区规则变化必须重算对应日汇总。"""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(_PROJECT_TZ).strftime("%Y-%m-%d")


def _usage_row(usage: NormalizedUsage | None) -> dict[str, Any]:
    if usage is None:
        return {
            "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
            "reasoning_tokens": None, "cached_tokens": None, "usage_complete": 0,
            "raw_usage": "{}",
        }
    raw = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "total_tokens": usage.total_tokens,
    }
    # 有些 OpenAI 兼容端点只给 prompt/completion，不给 total；排行仍应可算。
    total_tokens = usage.total_tokens
    prompt_tokens = usage.prompt_tokens()
    if total_tokens is None and prompt_tokens is not None and usage.output_tokens is not None:
        total_tokens = prompt_tokens + usage.output_tokens
        raw["total_tokens"] = total_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": usage.output_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cached_tokens": usage.cache_read_tokens,
        "usage_complete": 1 if usage.usage_complete else 0,
        "raw_usage": json.dumps(raw, ensure_ascii=False),
    }


class UsageRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_call(
        self,
        *,
        call_id: str,
        owner_id: int,
        source: str,
        provider: str,
        model: str,
        run_id: str | None,
        session_id: str | None,
        created_utc: datetime,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO llm_calls(call_id, owner_id, source, provider, model, run_id, session_id, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (call_id, owner_id, source, provider, model, run_id, session_id,
                 created_utc.isoformat(timespec="milliseconds")),
            )

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM llm_calls WHERE call_id=?", (call_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def complete_call(
        self,
        *,
        call_id: str,
        usage: NormalizedUsage | None,
        estimated: bool,
        completed_utc: datetime,
        error: str | None = None,
    ) -> bool:
        """首次完成：写明细并按完整值累加日汇总（同事务）。

        条件更新保证同一 call_id 的重复回调只计一次。返回是否实际生效。
        """
        u = _usage_row(usage)
        stat_date = stat_date_for(completed_utc)
        with self.db.transaction() as conn:
            cur = conn.execute(
                """UPDATE llm_calls SET prompt_tokens=?, completion_tokens=?, total_tokens=?,
                    reasoning_tokens=?, cached_tokens=?, usage_complete=?, estimated=?, raw_usage=?,
                    status=?, error=?, completed_at=?
                   WHERE call_id=? AND completed_at IS NULL""",
                (
                    u["prompt_tokens"], u["completion_tokens"], u["total_tokens"],
                    u["reasoning_tokens"], u["cached_tokens"], u["usage_complete"], 1 if estimated else 0,
                    u["raw_usage"],
                    "error" if error else "ok", error,
                    completed_utc.isoformat(timespec="milliseconds"),
                    call_id,
                ),
            )
            if cur.rowcount != 1:
                return False  # 重复回调：不产生新计量
            row = conn.execute("SELECT owner_id, source FROM llm_calls WHERE call_id=?", (call_id,)).fetchone()
            delta_total = u["total_tokens"] or 0
            delta_prompt = u["prompt_tokens"] or 0
            delta_completion = u["completion_tokens"] or 0
            self._apply_stats_delta(
                conn, stat_date=stat_date, owner_id=int(row["owner_id"]), source=str(row["source"]),
                d_prompt=delta_prompt, d_completion=delta_completion, d_total=delta_total, d_calls=1,
            )
            return True

    def report_usage(
        self,
        *,
        call_id: str,
        usage: NormalizedUsage,
        completed_utc: datetime,
    ) -> bool:
        """晚到/修正补全：同事务按新旧差额更新明细与日汇总。

        与 complete_call 的差值（旧值可为 NULL 视为 0）一次性应用；重复提交
        相同 usage 时差额为 0，不重复累计。
        """
        u = _usage_row(usage)
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT owner_id, source, prompt_tokens, completion_tokens, total_tokens, completed_at, created_at "
                "FROM llm_calls WHERE call_id=?",
                (call_id,),
            ).fetchone()
            if row is None:
                return False
            old_prompt = row["prompt_tokens"] or 0
            old_completion = row["completion_tokens"] or 0
            old_total = row["total_tokens"] or 0
            d_prompt = (u["prompt_tokens"] or 0) - old_prompt
            d_completion = (u["completion_tokens"] or 0) - old_completion
            d_total = (u["total_tokens"] or 0) - old_total
            conn.execute(
                """UPDATE llm_calls SET prompt_tokens=?, completion_tokens=?, total_tokens=?,
                    reasoning_tokens=?, cached_tokens=?, usage_complete=?, raw_usage=?
                   WHERE call_id=?""",
                (
                    u["prompt_tokens"], u["completion_tokens"], u["total_tokens"],
                    u["reasoning_tokens"], u["cached_tokens"], u["usage_complete"], u["raw_usage"],
                    call_id,
                ),
            )
            # 未完成就收到 usage：这次补全同时完成调用，避免之后 complete_call
            # 再把同一份 usage 加一遍。
            if not row["completed_at"]:
                conn.execute(
                    "UPDATE llm_calls SET status='ok', error=NULL, completed_at=? "
                    "WHERE call_id=? AND completed_at IS NULL",
                    (completed_utc.isoformat(timespec="milliseconds"), call_id),
                )
            if d_prompt == 0 and d_completion == 0 and d_total == 0:
                return True  # 明细已更新，汇总无变化
            # 首次完成/补全都归属同一完成日；否则跨午夜会把 tokens 拆到两天。
            accounting_at = row["completed_at"] or completed_utc
            stat_date = stat_date_for(datetime.fromisoformat(str(accounting_at)))
            self._apply_stats_delta(
                conn, stat_date=stat_date, owner_id=int(row["owner_id"]), source=str(row["source"]),
                d_prompt=d_prompt, d_completion=d_completion, d_total=d_total,
                d_calls=0 if row["completed_at"] else 1,
            )
            return True

    def mark_error(self, *, call_id: str, error: str, completed_utc: datetime) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE llm_calls SET status='error', error=?, completed_at=? "
                "WHERE call_id=? AND completed_at IS NULL",
                (error, completed_utc.isoformat(timespec="milliseconds"), call_id),
            )

    def cleanup_calls_before(self, cutoff_utc: datetime) -> int:
        """清理排障明细；日汇总不受影响（架构 §7：清理Trace不清理排行）。"""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM llm_calls WHERE created_at < ?",
                (cutoff_utc.isoformat(timespec="milliseconds"),),
            )
            return cur.rowcount

    def list_calls(self, *, owner_id: int | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            if owner_id is None:
                rows = conn.execute(
                    "SELECT call_id, owner_id, source, provider, model, run_id, session_id, "
                    "prompt_tokens, completion_tokens, total_tokens, usage_complete, estimated, "
                    "status, error, created_at, completed_at FROM llm_calls "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT call_id, owner_id, source, provider, model, run_id, session_id, "
                    "prompt_tokens, completion_tokens, total_tokens, usage_complete, estimated, "
                    "status, error, created_at, completed_at FROM llm_calls "
                    "WHERE owner_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (owner_id, limit, offset),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 排行 ------------------------------------------------------------------

    def ranking(self, *, days: int = 7, limit: int = 20, today_utc: datetime) -> list[dict[str, Any]]:
        cutoff = stat_date_for(today_utc - timedelta(days=days - 1))
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """SELECT s.user_id,
                          COALESCE(u.username, CASE WHEN s.user_id=0 THEN '系统任务' ELSE NULL END) AS username,
                          SUM(s.prompt_tokens) AS input_tokens,
                          SUM(s.completion_tokens) AS output_tokens,
                          SUM(s.total_tokens) AS total_tokens,
                          SUM(s.call_count) AS api_calls,
                          COUNT(DISTINCT s.stat_date) AS active_days,
                          SUM(CASE WHEN s.source='chat' THEN s.total_tokens ELSE 0 END) AS chat_tokens,
                          SUM(CASE WHEN s.source='memory' THEN s.total_tokens ELSE 0 END) AS memory_tokens,
                          SUM(CASE WHEN s.source='evolution' THEN s.total_tokens ELSE 0 END) AS evolution_tokens,
                          SUM(CASE WHEN s.source='schedule' THEN s.total_tokens ELSE 0 END) AS schedule_tokens
                   FROM daily_user_stats s LEFT JOIN users u ON u.id = s.user_id
                   WHERE s.stat_date >= ?
                   GROUP BY s.user_id, username
                   ORDER BY total_tokens DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
            out = []
            for i, r in enumerate(rows):
                user_id = int(r["user_id"])
                api_calls = int(r["api_calls"] or 0)
                total_tokens = int(r["total_tokens"] or 0)
                out.append(
                    {
                        "rank": i + 1,
                        "user_id": user_id,
                        # 旧 Trace 前端字段兼容；新调用方仍可使用 user_id。
                        "owner_id": user_id,
                        "username": r["username"] or f"用户{user_id}",
                        "input_tokens": int(r["input_tokens"] or 0),
                        "output_tokens": int(r["output_tokens"] or 0),
                        "total_tokens": total_tokens,
                        "api_calls": api_calls,
                        "call_count": api_calls,
                        "active_days": int(r["active_days"] or 0),
                        "sources": {
                            "chat": int(r["chat_tokens"] or 0),
                            "memory": int(r["memory_tokens"] or 0),
                            "evolution": int(r["evolution_tokens"] or 0),
                            "schedule": int(r["schedule_tokens"] or 0),
                        },
                    }
                )
            return out
        finally:
            conn.close()

    def daily_totals(self, *, owner_id: int, days: int, today_utc: datetime) -> list[dict[str, Any]]:
        cutoff = stat_date_for(today_utc - timedelta(days=days - 1))
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """SELECT stat_date,
                          SUM(prompt_tokens) AS input_tokens,
                          SUM(completion_tokens) AS output_tokens,
                          SUM(total_tokens) AS total_tokens,
                          SUM(call_count) AS call_count
                   FROM daily_user_stats
                   WHERE user_id=? AND stat_date>=?
                   GROUP BY stat_date ORDER BY stat_date""",
                (owner_id, cutoff),
            ).fetchall()
            return [
                {
                    "stat_date": str(r["stat_date"]),
                    "input_tokens": int(r["input_tokens"] or 0),
                    "output_tokens": int(r["output_tokens"] or 0),
                    "total_tokens": int(r["total_tokens"] or 0),
                    "call_count": int(r["call_count"] or 0),
                }
                for r in rows
            ]
        finally:
            conn.close()

    @staticmethod
    def _apply_stats_delta(
        conn: Any,
        *,
        stat_date: str,
        owner_id: int,
        source: str,
        d_prompt: int,
        d_completion: int,
        d_total: int,
        d_calls: int,
    ) -> None:
        conn.execute(
            """INSERT INTO daily_user_stats(stat_date, user_id, source, prompt_tokens, completion_tokens, total_tokens, call_count)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(stat_date, user_id, source) DO UPDATE SET
                 prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                 completion_tokens = completion_tokens + excluded.completion_tokens,
                 total_tokens = total_tokens + excluded.total_tokens,
                 call_count = call_count + excluded.call_count""",
            (stat_date, owner_id, source, d_prompt, d_completion, d_total, d_calls),
        )
