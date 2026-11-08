"""superagent 数据访问：任务（CAS 状态机）、attempt、输入、报告与部署级配置。

并发约定（方案 §5）：
- 所有任务写操作走 `transition_task` / `update_task_fields` 的条件更新
  （id + version [+ status 白名单]），成功则 version+1；
- attempt 写操作走 `update_attempt`（按 attempt_id 与运行态条件）；
- 事件与状态变更同事务提交；
- worker 认领一次只取一个任务（真实并发固定 1），认领即创建 attempt。
"""
from __future__ import annotations

import json
from typing import Any

from backend.modules.superagent.contracts import (
    ATTEMPT_RUNNING,
    CHECKPOINT_ORDER,
    MAX_EVENTS_PER_TASK,
    TASK_QUEUED,
    TASK_RUNNING,
    SuperagentSettings,
    SuperagentTask,
    TaskAttempt,
    TaskInput,
    TaskReport,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.identifiers import (
    new_superagent_attempt_id,
    new_superagent_input_id,
    new_superagent_report_id,
    new_superagent_task_id,
)


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
        repo_url_snapshot=str(d.get("repo_url_snapshot") or ""),
        base_branch_snapshot=str(d.get("base_branch_snapshot") or ""),
        base_sha=str(d.get("base_sha") or ""),
        settings_revision=str(d.get("settings_revision") or ""),
        policy_revision=int(d.get("policy_revision") or 0),
        source_event_id=str(d.get("source_event_id") or ""),
        source_channel_account_id=str(d.get("source_channel_account_id") or ""),
        source_chat_id=str(d.get("source_chat_id") or ""),
        source_ref=str(d.get("source_ref") or ""),
        source_kind=str(d.get("source_kind") or ""),
        executor_session_id=str(d.get("executor_session_id") or ""),
        active_attempt_id=str(d.get("active_attempt_id") or ""),
        version=int(d.get("version") or 1),
        phase=str(d.get("phase") or ""),
        cancel_requested_at=str(d.get("cancel_requested_at") or ""),
        pr_state=str(d.get("pr_state") or ""),
        outcome=str(d.get("outcome") or ""),
    )


def _attempt(row: Any) -> TaskAttempt:
    d = dict(row)
    return TaskAttempt(
        attempt_id=str(d["id"]),
        task_id=str(d["task_id"]),
        attempt_no=int(d["attempt_no"]),
        run_id=str(d["run_id"] or ""),
        session_id=str(d["session_id"] or ""),
        workspace_key=str(d["workspace_key"] or ""),
        state=str(d["state"] or ""),
        checkpoint=str(d["checkpoint"] or ""),
        head_sha=str(d["head_sha"] or ""),
        remote_head_sha=str(d["remote_head_sha"] or ""),
        pr_number=int(d["pr_number"] or 0),
        pr_url=str(d["pr_url"] or ""),
        started_at=str(d["started_at"] or ""),
        heartbeat_at=str(d["heartbeat_at"] or ""),
        finished_at=str(d["finished_at"] or ""),
        error_code=str(d["error_code"] or ""),
        error_summary=str(d["error_summary"] or ""),
    )


def _input(row: Any) -> TaskInput:
    d = dict(row)
    return TaskInput(
        input_id=str(d["id"]),
        task_id=str(d["task_id"]),
        source=str(d["source"] or ""),
        external_event_id=str(d["external_event_id"] or ""),
        actor_id=int(d["actor_id"] or 0),
        text=str(d["text"] or ""),
        attachment_refs=str(d["attachment_refs"] or "[]"),
        created_at=str(d["created_at"]),
        consumed_attempt_id=str(d["consumed_attempt_id"] or ""),
    )


def _report(row: Any) -> TaskReport:
    d = dict(row)
    return TaskReport(
        report_id=str(d["id"]),
        task_id=str(d["task_id"]),
        attempt_id=str(d["attempt_id"] or ""),
        kind=str(d["kind"] or ""),
        summary=str(d["summary"] or ""),
        question=str(d["question"] or ""),
        head_sha=str(d["head_sha"] or ""),
        verification_ref=str(d["verification_ref"] or ""),
        created_at=str(d["created_at"]),
    )


_TASK_FIELD_WHITELIST = frozenset({
    "status", "branch", "pr_url", "pr_number", "result_summary", "error",
    "run_id", "finished_at", "phase", "pr_state", "outcome", "base_sha",
    "active_attempt_id", "cancel_requested_at", "executor_session_id",
    "requirement", "repo_url_snapshot", "base_branch_snapshot",
})

_ATTEMPT_FIELD_WHITELIST = frozenset({
    "state", "checkpoint", "head_sha", "remote_head_sha", "pr_number",
    "pr_url", "run_id", "session_id", "workspace_key", "heartbeat_at",
    "finished_at", "error_code", "error_summary",
})


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
            verify_profile=str(d.get("verify_profile") or "[]"),
            allow_unverified_draft=bool(d.get("allow_unverified_draft", 1)),
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
        verify_profile: str | None = None,
        allow_unverified_draft: bool | None = None,
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
        if verify_profile is not None:
            assignments.append("verify_profile=?")
            params.append(verify_profile)
        if allow_unverified_draft is not None:
            assignments.append("allow_unverified_draft=?")
            params.append(1 if allow_unverified_draft else 0)
        assignments.append("updated_at=?")
        params.append(utc_now_iso())
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE superagent_settings SET {', '.join(assignments)} WHERE id=1",
                params,
            )

    # ---- 任务创建 ----------------------------------------------------------------

    def create_task(
        self, *, owner_id: int, title: str, requirement: str, context_extra: str,
        source: str, session_id: str, branch: str,
        repo_url_snapshot: str = "", base_branch_snapshot: str = "",
        settings_revision: str = "", policy_revision: int = 0,
        source_event_id: str = "", source_channel_account_id: str = "",
        source_chat_id: str = "", source_ref: str = "", source_kind: str = "",
    ) -> SuperagentTask:
        task_id = new_superagent_task_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO superagent_tasks(id, owner_id, title, requirement, context_extra, "
                "source, session_id, status, branch, created_at, updated_at, "
                "repo_url_snapshot, base_branch_snapshot, settings_revision, policy_revision, "
                "source_event_id, source_channel_account_id, source_chat_id, source_ref, source_kind, "
                "version) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                (
                    task_id, int(owner_id), title.strip(), requirement.strip(),
                    context_extra.strip(), source, session_id, TASK_QUEUED,
                    branch, now, now,
                    repo_url_snapshot, base_branch_snapshot, settings_revision,
                    int(policy_revision),
                    source_event_id, source_channel_account_id, source_chat_id,
                    source_ref, source_kind,
                ),
            )
            conn.execute(
                "INSERT INTO superagent_events(task_id, kind, detail, created_at) VALUES(?,?,?,?)",
                (task_id, "created", f"来源 {source}；分支 {branch}", now),
            )
            if source_event_id:
                conn.execute(
                    "INSERT INTO superagent_inputs(id, task_id, source, external_event_id, "
                    "actor_id, text, attachment_refs, created_at, consumed_attempt_id) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        new_superagent_input_id(), task_id, source, source_event_id,
                        int(owner_id), requirement.strip(), "[]", now, "",
                    ),
                )
        return self.get_task(task_id)  # type: ignore[return-value]

    # ---- 任务读取 ------------------------------------------------------------------

    def get_task(self, task_id: str) -> SuperagentTask | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM superagent_tasks WHERE id=?", (task_id,)
            ).fetchone()
        finally:
            conn.close()
        return _task(row) if row else None

    def list_for_owner(
        self, owner_id: int, limit: int = 50, *,
        cursor_created_at: str = "", cursor_id: str = "",
    ) -> list[SuperagentTask]:
        conn = self.db.connect()
        try:
            if cursor_created_at:
                rows = conn.execute(
                    "SELECT * FROM superagent_tasks WHERE owner_id=? AND status<>? "
                    "AND (created_at < ? OR (created_at = ? AND id < ?)) "
                    "ORDER BY created_at DESC, id DESC LIMIT ?",
                    (int(owner_id), "cancelled_hidden", cursor_created_at, cursor_created_at,
                     cursor_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM superagent_tasks WHERE owner_id=? AND status<>? "
                    "ORDER BY created_at DESC, id DESC LIMIT ?",
                    (int(owner_id), "cancelled_hidden", int(limit)),
                ).fetchall()
        finally:
            conn.close()
        return [_task(r) for r in rows]

    def list_all(
        self, limit: int = 100, *,
        cursor_created_at: str = "", cursor_id: str = "",
    ) -> list[SuperagentTask]:
        conn = self.db.connect()
        try:
            if cursor_created_at:
                rows = conn.execute(
                    "SELECT * FROM superagent_tasks "
                    "WHERE (created_at < ? OR (created_at = ? AND id < ?)) "
                    "ORDER BY created_at DESC, id DESC LIMIT ?",
                    (cursor_created_at, cursor_created_at, cursor_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM superagent_tasks ORDER BY created_at DESC, id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        finally:
            conn.close()
        return [_task(r) for r in rows]

    def find_task_by_source_event(self, source: str, external_event_id: str) -> SuperagentTask | None:
        """幂等受理查询：同一 (source, external_event_id) 已存在时返回其任务。"""
        if not external_event_id:
            return None
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT t.* FROM superagent_inputs i JOIN superagent_tasks t ON t.id=i.task_id "
                "WHERE i.source=? AND i.external_event_id=? LIMIT 1",
                (source, external_event_id),
            ).fetchone()
        finally:
            conn.close()
        return _task(row) if row else None

    # ---- CAS 状态迁移（事件同事务） -----------------------------------------------

    def transition_task(
        self, task_id: str, *, from_statuses: frozenset[str] | tuple[str, ...],
        to_status: str, version_expected: int | None = None,
        event_kind: str = "", event_detail: str = "",
        **fields: Any,
    ) -> bool:
        """条件状态迁移：WHERE id + status 白名单 [+ version]；成功则 version+1 并写事件。"""
        unknown = set(fields) - _TASK_FIELD_WHITELIST
        if unknown:
            raise ValueError(f"不允许更新字段: {sorted(unknown)}")
        statuses = tuple(from_statuses)
        assignments = ["status=?", "version=version+1", "updated_at=?"]
        params: list[Any] = [to_status, utc_now_iso()]
        for name, value in fields.items():
            assignments.append(f"{name}=?")
            params.append(value)
        sql = (
            f"UPDATE superagent_tasks SET {', '.join(assignments)} WHERE id=? "
            f"AND status IN ({','.join('?' * len(statuses))})"
        )
        params.extend([task_id, *statuses])
        if version_expected is not None:
            sql += " AND version=?"
            params.append(int(version_expected))
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(sql, params)
            if cur.rowcount != 1:
                return False
            if event_kind:
                conn.execute(
                    "INSERT INTO superagent_events(task_id, kind, detail, created_at) "
                    "VALUES(?,?,?,?)",
                    (task_id, event_kind, event_detail[:2000], now),
                )
        return True

    def update_task_fields(self, task_id: str, **fields: Any) -> None:
        """worker 私有字段更新（run_id 等，不参与 CAS；终态判定仍走条件迁移）。"""
        unknown = set(fields) - _TASK_FIELD_WHITELIST
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

    def task_matches(self, task_id: str, *, status: str, attempt_id: str) -> bool:
        """迟到结果防护：任务仍处于该状态且活跃 attempt 未变。"""
        task = self.get_task(task_id)
        return (
            task is not None
            and task.status == status
            and (not attempt_id or task.active_attempt_id == attempt_id)
        )

    # ---- worker 认领（一次一个；认领即建 attempt，同事务） --------------------------

    def claim_next_task(self) -> tuple[SuperagentTask, TaskAttempt] | None:
        """认领一个 queued 任务（真实并发固定 1）：置 running + 建 attempt，同事务。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM superagent_tasks WHERE status=? ORDER BY created_at, id LIMIT 1",
                (TASK_QUEUED,),
            ).fetchone()
            if row is None:
                return None
            task_id = str(row["id"])
            attempt_no = int(conn.execute(
                "SELECT count(*) AS c FROM superagent_attempts WHERE task_id=?",
                (task_id,),
            ).fetchone()["c"]) + 1
            attempt_id = new_superagent_attempt_id()
            session_id = f"sagexec_{task_id}_{attempt_no}"
            conn.execute(
                "UPDATE superagent_tasks SET status=?, phase=?, active_attempt_id=?, "
                "executor_session_id=?, version=version+1, updated_at=? WHERE id=? AND status=?",
                (TASK_RUNNING, "preparing", attempt_id, session_id, now, task_id, TASK_QUEUED),
            )
            cur = conn.execute(
                "SELECT changes() AS n"
            ).fetchone()
            if int(cur["n"]) != 1:
                return None
            conn.execute(
                "INSERT INTO superagent_attempts(id, task_id, attempt_no, session_id, "
                "workspace_key, state, checkpoint, started_at, heartbeat_at, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    attempt_id, task_id, attempt_no, session_id,
                    "", ATTEMPT_RUNNING, "", now, now, now, now,
                ),
            )
            conn.execute(
                "INSERT INTO superagent_events(task_id, kind, detail, created_at) VALUES(?,?,?,?)",
                (task_id, "attempt_started", f"attempt #{attempt_no}；分支 {row['branch']}", now),
            )
        task = self.get_task(task_id)
        attempt = self.get_attempt(attempt_id)
        if task is None or attempt is None:
            return None
        return task, attempt

    # ---- attempt ------------------------------------------------------------------

    def get_attempt(self, attempt_id: str) -> TaskAttempt | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM superagent_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
        finally:
            conn.close()
        return _attempt(row) if row else None

    def attempts_for_task(self, task_id: str) -> list[TaskAttempt]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM superagent_attempts WHERE task_id=? ORDER BY attempt_no",
                (task_id,),
            ).fetchall()
        finally:
            conn.close()
        return [_attempt(r) for r in rows]

    def update_attempt(self, attempt_id: str, **fields: Any) -> bool:
        unknown = set(fields) - _ATTEMPT_FIELD_WHITELIST
        if unknown:
            raise ValueError(f"不允许更新字段: {sorted(unknown)}")
        if "checkpoint" in fields:
            new_ck = fields["checkpoint"]
            current = self.get_attempt(attempt_id)
            if current is not None and new_ck != current.checkpoint:
                order = CHECKPOINT_ORDER
                if new_ck not in order:
                    raise ValueError(f"未知检查点: {new_ck}")
                if current.checkpoint in order and order.index(new_ck) < order.index(current.checkpoint):
                    raise ValueError("检查点只能向前推进")
        assignments = [f"{name}=?" for name in fields]
        assignments.append("updated_at=?")
        params = [*fields.values(), utc_now_iso(), attempt_id]
        with self.db.transaction() as conn:
            cur = conn.execute(
                f"UPDATE superagent_attempts SET {', '.join(assignments)} WHERE id=?",
                params,
            )
            return cur.rowcount == 1

    def finish_attempt(
        self, attempt_id: str, *, state: str, error_code: str = "",
        error_summary: str = "", head_sha: str = "", pr_number: int | None = None,
        pr_url: str = "",
    ) -> bool:
        fields: dict[str, Any] = {
            "state": state, "finished_at": utc_now_iso(),
            "error_code": error_code, "error_summary": error_summary[:2000],
        }
        if head_sha:
            fields["head_sha"] = head_sha
        if pr_number is not None:
            fields["pr_number"] = pr_number
        if pr_url:
            fields["pr_url"] = pr_url
        return self.update_attempt(attempt_id, **fields)

    # ---- 输入 --------------------------------------------------------------------

    def append_input(
        self, *, task_id: str, source: str, external_event_id: str = "",
        actor_id: int = 0, text: str, attachment_refs: str = "[]",
    ) -> tuple[TaskInput | None, bool]:
        """幂等追加：(source, external_event_id) 唯一；重复返回 (既有, False)。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            if external_event_id:
                existing = conn.execute(
                    "SELECT * FROM superagent_inputs WHERE source=? AND external_event_id=?",
                    (source, external_event_id),
                ).fetchone()
                if existing is not None:
                    return _input(existing), False
            input_id = new_superagent_input_id()
            conn.execute(
                "INSERT INTO superagent_inputs(id, task_id, source, external_event_id, "
                "actor_id, text, attachment_refs, created_at, consumed_attempt_id) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (input_id, task_id, source, external_event_id, int(actor_id),
                 text.strip(), attachment_refs, now, ""),
            )
        return self.get_input(input_id), True  # type: ignore[return-value]

    def get_input(self, input_id: str) -> TaskInput | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM superagent_inputs WHERE id=?", (input_id,)
            ).fetchone()
        finally:
            conn.close()
        return _input(row) if row else None

    def unconsumed_inputs(self, task_id: str) -> list[TaskInput]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM superagent_inputs WHERE task_id=? AND consumed_attempt_id='' "
                "ORDER BY created_at, id",
                (task_id,),
            ).fetchall()
        finally:
            conn.close()
        return [_input(r) for r in rows]

    def mark_inputs_consumed(self, task_id: str, attempt_id: str) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE superagent_inputs SET consumed_attempt_id=? "
                "WHERE task_id=? AND consumed_attempt_id=''",
                (attempt_id, task_id),
            )
            return int(cur.rowcount)

    # ---- 报告 --------------------------------------------------------------------

    def insert_report(
        self, *, task_id: str, attempt_id: str = "", kind: str,
        summary: str = "", question: str = "", head_sha: str = "",
        verification_ref: str = "",
    ) -> TaskReport:
        report_id = new_superagent_report_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO superagent_reports(id, task_id, attempt_id, kind, summary, "
                "question, head_sha, verification_ref, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (report_id, task_id, attempt_id, kind, summary[:SUMMARY_LIMIT],
                 question[:1000], head_sha, verification_ref, now),
            )
        return self.get_report(report_id)  # type: ignore[return-value]

    def get_report(self, report_id: str) -> TaskReport | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM superagent_reports WHERE id=?", (report_id,)
            ).fetchone()
        finally:
            conn.close()
        return _report(row) if row else None

    def reports_for_task(self, task_id: str, limit: int = 50) -> list[TaskReport]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM superagent_reports WHERE task_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (task_id, int(limit)),
            ).fetchall()
        finally:
            conn.close()
        return [_report(r) for r in rows]

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

    def events_for_task(self, task_id: str, limit: int = 200, after_id: int = 0) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM superagent_events WHERE task_id=? AND id>? ORDER BY id LIMIT ?",
                (task_id, int(after_id), int(limit)),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    # ---- 重试与恢复 ----------------------------------------------------------------

    def requeue(self, task_id: str) -> bool:
        """重试：可重试状态回 queued（新 attempt 由 worker 认领时创建）。"""
        from backend.modules.superagent.contracts import RETRYABLE_TASK_STATUSES

        return self.transition_task(
            task_id,
            from_statuses=RETRYABLE_TASK_STATUSES,
            to_status=TASK_QUEUED,
            event_kind="created",
            event_detail="手动重试，重新入队",
            error="", result_summary="", run_id="", finished_at="",
        )

    def reset_running_to_interrupted(self) -> int:
        """启动恢复：遗留 running 任务/attempt 标 interrupted（与 assistant 一致，不自动重跑）。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE superagent_attempts SET state='interrupted', "
                "error_code='interrupted', error_summary='服务重启导致执行中断', "
                "finished_at=?, updated_at=? WHERE state='running'",
                (now, now),
            )
            cur = conn.execute(
                "UPDATE superagent_tasks SET status='interrupted', phase='', "
                "error='服务重启导致执行中断，重试前将先对账远端', updated_at=? WHERE status=?",
                (now, TASK_RUNNING),
            )
            return int(cur.rowcount)


SUMMARY_LIMIT = 2000


def load_verify_profile(profile_json: str) -> list[dict[str, Any]]:
    """解析验证策略 JSON；损坏时返回空列表（fail-open 到「未配置验证」路径）。"""
    try:
        data = json.loads(profile_json or "[]")
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict) and item.get("command")]
    except ValueError:
        return []
