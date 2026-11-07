"""superagent 数据访问：任务队列、事件时间线与部署级配置。"""
from __future__ import annotations

from typing import Any

from backend.modules.superagent.contracts import (
    MAX_EVENTS_PER_TASK,
    TASK_QUEUED,
    TASK_RUNNING,
    SuperagentSettings,
    SuperagentTask,
    TaskEvent,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.identifiers import new_superagent_task_id


def _task(row: Any) -> SuperagentTask:
    d = dict(row)
    return SuperagentTask(
        task_id=str(d["id"]),
        owner_id=int(d["owner_id"]),
        title=str(d["title"] or ""),
        requirement=str(d["requirement"] or ""),
        context_extra=str(d["context_extra"] or ""),
        source=str(d["source"] or ""),
        session_id=str(d["session_id"] or ""),
        status=str(d["status"] or ""),
        branch=str(d["branch"] or ""),
        pr_url=str(d["pr_url"] or ""),
        pr_number=int(d["pr_number"] or 0),
        result_summary=str(d["result_summary"] or ""),
        error=str(d["error"] or ""),
        run_id=str(d["run_id"] or ""),
        attempts=int(d["attempts"] or 0),
        created_at=str(d["created_at"]),
        updated_at=str(d["updated_at"]),
        started_at=str(d["started_at"] or ""),
        finished_at=str(d["finished_at"] or ""),
    )


class SuperagentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- 配置 ------------------------------------------------------------------

    def get_settings(self) -> SuperagentSettings:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM superagent_settings WHERE id=1").fetchone()
        finally:
            conn.close()
        d = dict(row) if row else {}
        token_enc = str(d.get("github_token_enc") or "")
        return SuperagentSettings(
            enabled=bool(d.get("enabled")),
            repo_url=str(d.get("repo_url") or ""),
            base_branch=str(d.get("base_branch") or "main"),
            github_token_mask="已配置" if token_enc else "",
            has_github_token=bool(token_enc),
            pr_labels=str(d.get("pr_labels") or ""),
            max_concurrent=int(d.get("max_concurrent") or 1),
            updated_at=str(d.get("updated_at") or ""),
        )

    def get_token_encrypted(self) -> str:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT github_token_enc FROM superagent_settings WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        return str(row["github_token_enc"] or "") if row else ""

    def update_settings(
        self, *,
        enabled: bool | None = None,
        repo_url: str | None = None,
        base_branch: str | None = None,
        github_token_enc: str | None = None,
        pr_labels: str | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        """只更新传入字段；github_token_enc 传空串表示清除凭证。"""
        assignments: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            assignments.append("enabled=?")
            params.append(1 if enabled else 0)
        if repo_url is not None:
            assignments.append("repo_url=?")
            params.append(repo_url.strip())
        if base_branch is not None:
            assignments.append("base_branch=?")
            params.append(base_branch.strip() or "main")
        if github_token_enc is not None:
            assignments.append("github_token_enc=?")
            params.append(github_token_enc)
        if pr_labels is not None:
            assignments.append("pr_labels=?")
            params.append(pr_labels.strip())
        if max_concurrent is not None:
            assignments.append("max_concurrent=?")
            params.append(max(1, int(max_concurrent)))
        assignments.append("updated_at=?")
        params.append(utc_now_iso())
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE superagent_settings SET {', '.join(assignments)} WHERE id=1",
                params,
            )

    # ---- 任务 ------------------------------------------------------------------

    def create_task(
        self, *, owner_id: int, title: str, requirement: str, context_extra: str,
        source: str, session_id: str,
    ) -> SuperagentTask:
        task_id = new_superagent_task_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO superagent_tasks(id, owner_id, title, requirement, context_extra, "
                "source, session_id, status, branch, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    task_id, int(owner_id), title.strip(), requirement.strip(),
                    context_extra.strip(), source, session_id, TASK_QUEUED,
                    f"superagent/{task_id}", now, now,
                ),
            )
        return self.get_task(task_id)  # type: ignore[return-value]

    def get_task(self, task_id: str) -> SuperagentTask | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM superagent_tasks WHERE id=?", (task_id,)
            ).fetchone()
        finally:
            conn.close()
        return _task(row) if row else None

    def list_for_owner(self, owner_id: int, limit: int = 50) -> list[SuperagentTask]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM superagent_tasks WHERE owner_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (int(owner_id), int(limit)),
            ).fetchall()
        finally:
            conn.close()
        return [_task(r) for r in rows]

    def list_all(self, limit: int = 100) -> list[SuperagentTask]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM superagent_tasks ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        finally:
            conn.close()
        return [_task(r) for r in rows]

    def claim_due_tasks(self, limit: int) -> list[SuperagentTask]:
        """原子认领 queued 任务：置 running 并记 attempts/started_at。"""
        now = utc_now_iso()
        claimed_ids: list[str] = []
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id FROM superagent_tasks WHERE status=? ORDER BY created_at LIMIT ?",
                (TASK_QUEUED, int(limit)),
            ).fetchall()
            for row in rows:
                cur = conn.execute(
                    "UPDATE superagent_tasks SET status=?, attempts=attempts+1, "
                    "started_at=?, updated_at=? WHERE id=? AND status=?",
                    (TASK_RUNNING, now, now, str(row["id"]), TASK_QUEUED),
                )
                if cur.rowcount == 1:
                    claimed_ids.append(str(row["id"]))
        return [task for task in (self.get_task(t) for t in claimed_ids) if task]

    def update_fields(self, task_id: str, **fields: Any) -> None:
        """通用字段更新；值必须是列允许的标量。"""
        allowed = {
            "status", "branch", "pr_url", "pr_number", "result_summary",
            "error", "run_id", "finished_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"不允许更新字段: {sorted(unknown)}")
        assignments = [f"{name}=?" for name in fields]
        assignments.append("updated_at=?")
        params = [*fields.values(), utc_now_iso(), task_id]
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE superagent_tasks SET {', '.join(assignments)} WHERE id=?",
                params,
            )

    def requeue(self, task_id: str) -> bool:
        """重试：终态任务回 queued；错误/结果清空。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE superagent_tasks SET status=?, error='', result_summary='', "
                "pr_url='', pr_number=NULL, run_id='', finished_at=NULL, updated_at=? "
                "WHERE id=? AND status IN ('failed','cancelled')",
                (TASK_QUEUED, now, task_id),
            )
            return cur.rowcount == 1

    # ---- 事件 ------------------------------------------------------------------

    def append_event(self, task_id: str, kind: str, detail: str = "") -> None:
        """追加时间线条目；超出上限时丢弃最旧的非 created/started 条目。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO superagent_events(task_id, kind, detail, created_at) "
                "VALUES(?,?,?,?)",
                (task_id, kind, detail[:2000], now),
            )
            conn.execute(
                """DELETE FROM superagent_events WHERE id IN (
                     SELECT id FROM superagent_events
                     WHERE task_id=? AND kind NOT IN ('created','started')
                     ORDER BY id DESC LIMIT -1 OFFSET ?
                   )""",
                (task_id, MAX_EVENTS_PER_TASK),
            )

    def events_for_task(self, task_id: str, limit: int = 200) -> list[TaskEvent]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM superagent_events WHERE task_id=? ORDER BY id LIMIT ?",
                (task_id, int(limit)),
            ).fetchall()
        finally:
            conn.close()
        return [
            TaskEvent(
                event_id=int(r["id"]), task_id=str(r["task_id"]),
                kind=str(r["kind"]), detail=str(r["detail"] or ""),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]

    def reset_running_tasks(self) -> int:
        """启动恢复：上进程遗留的 running 任务标记失败（与 assistant 一致，不自动重跑）。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE superagent_tasks SET status='failed', "
                "error='服务重启导致执行中断，可重试', updated_at=?, finished_at=? "
                "WHERE status=?",
                (now, now, TASK_RUNNING),
            )
            return int(cur.rowcount)
