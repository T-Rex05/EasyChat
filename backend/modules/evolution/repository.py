"""evolution 数据访问：学习任务、经验与暂停开关。"""
from __future__ import annotations

import json
import uuid
from typing import Any

from backend.modules.evolution.contracts import (
    TASK_PENDING,
    EvolutionTaskView,
    ExperienceView,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import NotFoundError

_PAUSE_KEY = "evolution_paused"


def _task(row: Any) -> EvolutionTaskView:
    d = dict(row)
    return EvolutionTaskView(
        task_id=str(d["id"]),
        owner_id=int(d["owner_id"]),
        source_event_id=str(d["source_event_id"]),
        run_id=str(d.get("run_id") or ""),
        source=str(d["source"]),
        status=str(d["status"]),
        error=str(d.get("error") or ""),
        budget_reserved=int(d.get("budget_reserved") or 0),
        budget_used=int(d.get("budget_used") or 0),
        created_at=str(d["created_at"]),
    )


def _experience(row: Any) -> ExperienceView:
    d = dict(row)
    return ExperienceView(
        experience_id=str(d["id"]),
        task_id=str(d["task_id"]),
        owner_id=int(d["owner_id"]),
        run_id=str(d.get("run_id") or ""),
        content=str(d["content"]),
        conditions=str(d.get("conditions") or ""),
        counterexample=str(d.get("counterexample") or ""),
        confidence=float(d.get("confidence") or 0.0),
        source_type=str(d.get("source_type") or "model_inferred"),
        created_at=str(d["created_at"]),
    )


class EvolutionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_task(
        self,
        *,
        owner_id: int,
        source_event_id: str,
        run_id: str,
        source: str,
        evidence: dict[str, Any],
    ) -> tuple[EvolutionTaskView, bool]:
        task_id = f"evo_{uuid.uuid4().hex}"
        now = utc_now_iso()
        inserted = False
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO evolution_tasks(id, owner_id, source_event_id, run_id, source, status, "
                "evidence, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(owner_id, source_event_id) DO NOTHING",
                (task_id, owner_id, source_event_id, run_id or None, source, TASK_PENDING,
                 json.dumps(evidence, ensure_ascii=False), now, now),
            )
            if cur.rowcount == 1:
                inserted = True
            else:
                row = conn.execute(
                    "SELECT id FROM evolution_tasks WHERE owner_id=? AND source_event_id=?",
                    (owner_id, source_event_id),
                ).fetchone()
                task_id = str(row["id"])
        return self.get_task(task_id), inserted

    def get_task(self, task_id: str) -> EvolutionTaskView:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM evolution_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"学习任务不存在: {task_id}")
            return _task(row)
        finally:
            conn.close()

    def task_evidence(self, task_id: str) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT evidence FROM evolution_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"学习任务不存在: {task_id}")
            try:
                data = json.loads(str(row["evidence"] or "{}"))
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}
        finally:
            conn.close()

    def set_task_status(
        self,
        task_id: str,
        *,
        status: str,
        error: str = "",
        budget_reserved: int | None = None,
        budget_used: int | None = None,
    ) -> None:
        sets = ["status=?", "error=?", "updated_at=?"]
        params: list[Any] = [status, error[:500], utc_now_iso()]
        if budget_reserved is not None:
            sets.append("budget_reserved=?")
            params.append(int(budget_reserved))
        if budget_used is not None:
            sets.append("budget_used=?")
            params.append(int(budget_used))
        sets.append("finished_at=?")
        params.append(utc_now_iso() if status in ("done", "rejected") else None)
        params.append(task_id)
        with self.db.transaction() as conn:
            conn.execute(f"UPDATE evolution_tasks SET {', '.join(sets)} WHERE id=?", params)

    def add_experience(
        self,
        *,
        task_id: str,
        owner_id: int,
        run_id: str,
        content: str,
        conditions: str,
        counterexample: str,
        confidence: float,
        source_type: str,
    ) -> ExperienceView:
        experience_id = f"exp_{uuid.uuid4().hex}"
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO evolution_experiences(id, task_id, owner_id, run_id, content, conditions, "
                "counterexample, confidence, source_type, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (experience_id, task_id, owner_id, run_id or None, content, conditions,
                 counterexample, float(confidence), source_type, utc_now_iso()),
            )
            row = conn.execute(
                "SELECT * FROM evolution_experiences WHERE id=?", (experience_id,)
            ).fetchone()
            return _experience(row)

    def experiences(self, owner_id: int | None = None, limit: int = 50) -> list[ExperienceView]:
        conn = self.db.connect()
        try:
            if owner_id is None:
                rows = conn.execute(
                    "SELECT * FROM evolution_experiences ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM evolution_experiences WHERE owner_id=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (owner_id, limit),
                ).fetchall()
            return [_experience(r) for r in rows]
        finally:
            conn.close()

    def paused(self) -> bool:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key=?", (_PAUSE_KEY,)
            ).fetchone()
            return bool(row and str(row["value"]).strip('"').lower() in ("1", "true", "yes"))
        finally:
            conn.close()

    def set_paused(self, paused: bool) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO app_settings(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (_PAUSE_KEY, "true" if paused else "false", utc_now_iso()),
            )
