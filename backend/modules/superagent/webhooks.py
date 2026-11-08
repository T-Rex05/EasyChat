"""GitHub webhook 回流（T7，方案 §9）。

边界：
- HMAC-SHA256 验签（常量时间比较）→ 事件先落库（delivery_id 唯一去重）→
  持久 job 异步处理 → 快速应答；
- 仓库 allowlist：只处理当前配置仓库的事件；
- 关联：PR body 的 EasyChat-Superagent-Task 标记 → repo+pr 反查；
- 乱序防护：head 不属于任务任何 attempt 的 CI/评论不触发工作；
- 机器人循环防护：Bot 账号不触发（自身 PR 机器人不会评论自己）。

处理为纯 DB 操作（无外呼），由 SuperagentWorker 的 tick 消费持久 job；
自动修复规则（最多两轮）暂缓——见方案 §10 T7 与总结报告待验证项。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from backend.modules.delivery.contracts import DeliveryTarget, target_from_channel
from backend.modules.superagent.contracts import (
    OUTCOME_CLOSED_UNMERGED,
    PR_CLOSED,
    PR_MERGED,
    PR_OPEN,
    REPORT_BLOCKED,
    REPORT_PROGRESS,
    TASK_AWAITING_REVIEW,
)
from backend.modules.superagent.credentials import parse_repo_url
from backend.platform.jobs import JobQueue
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.identifiers import (
    new_superagent_input_id,
    new_superagent_report_id,
    new_superagent_webhook_event_id,
)

logger = logging.getLogger(__name__)

WEBHOOK_JOB_KIND = "superagent.webhook.process"
SUPPORTED_EVENTS = frozenset({"pull_request", "pull_request_review", "issue_comment", "check_run"})
TASK_MARKER_RE = re.compile(r"EasyChat-Superagent-Task:\s*(sag_[0-9a-f]{32})")


def verify_signature(secret: str, body: bytes, signature_header: str) -> bool:
    """X-Hub-Signature-256 验签；常量时间比较；缺配置/缺头一律拒绝。"""
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.strip())


def extract_fields(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """从 GitHub payload 提取处理所需字段；结构异常返回空值集（事件仍在库可查）。"""
    repository = payload.get("repository") or {}
    pr = payload.get("pull_request") or {}
    issue = payload.get("issue") or {}
    check = payload.get("check_run") or {}
    review = payload.get("review") or {}
    comment = payload.get("comment") or {}
    sender = payload.get("sender") or {}
    sender_login = str(sender.get("login") or "")
    return {
        "event_type": event_type,
        "action": str(payload.get("action") or ""),
        "repo_full_name": str(repository.get("full_name") or ""),
        "pr_number": int(pr.get("number") or issue.get("number") or 0),
        "head_sha": str((pr.get("head") or {}).get("sha") or check.get("head_sha") or ""),
        "sender_login": sender_login,
        "sender_is_bot": bool(sender.get("type") == "Bot" or sender_login.endswith("[bot]")),
        "pr_body": str(pr.get("body") or ""),
        "pr_merged": bool(pr.get("merged")),
        "review_state": str(review.get("state") or ""),
        "review_body": str(review.get("body") or ""),
        "comment_body": str(comment.get("body") or ""),
        "check_conclusion": str(check.get("conclusion") or ""),
        "check_name": str(check.get("name") or ""),
    }


class WebhookService:
    """入库（HTTP 入口调用）+ 处理（worker 的持久 job 消费）。"""

    def __init__(self, db: Database, *, superagent: Any, queue: JobQueue,
                 webhook_secret: str = "") -> None:
        self.db = db
        self.superagent = superagent
        self.queue = queue
        self.webhook_secret = webhook_secret

    # ---- HTTP 入口 ----------------------------------------------------------------

    def ingest(
        self, *, event_type: str, delivery_id: str, signature: str, body: bytes,
    ) -> tuple[int, dict[str, Any]]:
        """验签 → 落库 → 持久 job 入队（与事件同事务）；返回 (http_status, body)。"""
        if event_type not in SUPPORTED_EVENTS:
            return 200, {"ok": True, "ignored": "unsupported_event"}
        if not verify_signature(self.webhook_secret, body, signature):
            return 403, {"error": "invalid_signature"}
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return 400, {"error": "invalid_json"}
        if not isinstance(payload, dict):
            return 400, {"error": "invalid_json"}
        fields = extract_fields(event_type, payload)
        if not self._repo_allowed(fields["repo_full_name"]):
            return 200, {"ok": True, "ignored": "repo_not_allowed"}
        event_id = new_superagent_webhook_event_id()
        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM superagent_webhook_events WHERE delivery_id=?",
                (delivery_id,),
            ).fetchone()
            if existing is not None:
                return 200, {"ok": True, "duplicate": True}
            conn.execute(
                "INSERT INTO superagent_webhook_events(id, delivery_id, event_type, action, "
                "repo_full_name, pr_number, head_sha, sender_login, sender_is_bot, payload, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id, delivery_id, event_type, fields["action"],
                    fields["repo_full_name"], fields["pr_number"], fields["head_sha"],
                    fields["sender_login"], 1 if fields["sender_is_bot"] else 0,
                    json.dumps(payload, ensure_ascii=False)[:100_000], utc_now_iso(),
                ),
            )
            self.queue.enqueue_tx(
                conn, kind=WEBHOOK_JOB_KIND, dedup_key=f"webhook:{delivery_id}",
                payload={"event_id": event_id},
            )
        return 202, {"ok": True, "event_id": event_id}

    # ---- worker 处理（job 幂等：dedup=delivery_id；事件行 processed_at 幂等） ---------

    def process_event(self, event_id: str) -> str:
        row = self._get_event(event_id)
        if row is None:
            return "missing"
        if row["processed_at"]:
            return "already_processed"
        try:
            payload = json.loads(str(row["payload"] or "{}"))
        except ValueError:
            payload = {}
        fields = extract_fields(str(row["event_type"]), payload if isinstance(payload, dict) else {})
        if fields["sender_is_bot"]:
            return self._finish(row, "bot_skipped")
        task = self._find_task(fields)
        if task is None:
            return self._finish(row, "no_task")
        outcome = self._dispatch(task, fields, payload if isinstance(payload, dict) else {})
        return self._finish(row, outcome)

    # ---- 具体事件 ------------------------------------------------------------------

    def _dispatch(self, task, fields: dict[str, Any], payload: dict[str, Any]) -> str:
        event_type, action = fields["event_type"], fields["action"]
        if event_type == "pull_request" and action == "closed":
            return self._on_pr_closed(task, fields)
        if event_type == "pull_request" and action in ("opened", "synchronize"):
            return self._on_pr_activity(task)
        if event_type == "pull_request_review" and action == "submitted":
            return self._on_review(task, fields)
        if event_type == "issue_comment" and action == "created":
            return self._on_comment(task, fields)
        if event_type == "check_run" and action == "completed":
            return self._on_check_run(task, fields)
        return "unhandled_action"

    def _on_pr_closed(self, task, fields: dict[str, Any]) -> str:
        merged = bool(fields.get("pr_merged"))
        if merged:
            self._update_task_pr(task, pr_state=PR_MERGED, outcome="merged")
            self._insert_report(task, REPORT_PROGRESS, "PR 已被合并。")
            self._notify(task, f"🎉 PR 已合并：{task.pr_url}\n「{task.title}」任务完成。")
            return "merged"
        self._update_task_pr(task, pr_state=PR_CLOSED, outcome=OUTCOME_CLOSED_UNMERGED)
        self._insert_report(task, REPORT_BLOCKED, "PR 被关闭且未合并（closed_unmerged）。")
        self._notify(task, f"⚠️ Draft PR 被关闭（未合并）：{task.pr_url}\n任务 {task.task_id[-6:]} 如需继续可重新提交需求。")
        return "closed_unmerged"

    def _on_pr_activity(self, task) -> str:
        """PR opened/synchronize：draft → open 展示；任务已在评审态则跳过。"""
        if task.pr_state == PR_OPEN or task.status == TASK_AWAITING_REVIEW:
            return "already_current"
        self._update_task_pr(task, pr_state=PR_OPEN)
        return "pr_state_updated"

    def _on_review(self, task, fields: dict[str, Any]) -> str:
        body = (fields.get("review_body") or "").strip()
        state = fields.get("review_state") or ""
        summary = f"评审（{state}）：{body[:500]}" if body else f"评审状态：{state}"
        self._insert_report(task, REPORT_PROGRESS, summary)
        if body:
            self._append_input(task, f"[GitHub 评审 {state}] {body[:2000]}")
        self._notify(task, f"💬 任务收到新评审（{state}）：{body[:200] or '（无内容）'}")
        return "review_recorded"

    def _on_comment(self, task, fields: dict[str, Any]) -> str:
        body = (fields.get("comment_body") or "").strip()
        if not body:
            return "empty_comment"
        self._append_input(task, f"[GitHub 评论] {body[:2000]}")
        self._insert_report(task, REPORT_PROGRESS, f"PR 评论已作为补充输入：{body[:200]}")
        self._notify(task, f"💬 PR 新评论：{body[:200]}")
        return "comment_recorded"

    def _on_check_run(self, task, fields: dict[str, Any]) -> str:
        if (fields.get("check_conclusion") or "") != "failure":
            return "check_not_failure"
        head_sha = fields.get("head_sha") or ""
        if head_sha and not self._head_belongs_to_task(task, head_sha):
            logger.info("忽略旧 head CI 事件 task=%s head=%s", task.task_id, head_sha[:12])
            return "stale_head_ignored"
        summary = f"CI 失败：{fields.get('check_name') or 'check'}（head {head_sha[:12]}）"
        self._insert_report(task, REPORT_BLOCKED, summary)
        self._notify(
            task,
            f"❌ {summary}\n详情见 GitHub Checks；需要修复可在 Web 面板重试，"
            f"或回复「/补充 {task.task_id[-6:]} 修复说明」。",
        )
        return "ci_failure_reported"

    # ---- 工具 --------------------------------------------------------------------

    def _get_event(self, event_id: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM superagent_webhook_events WHERE id=?", (event_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _finish(self, row: dict[str, Any], result: str) -> str:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE superagent_webhook_events SET processed_at=?, process_error=? WHERE id=?",
                (utc_now_iso(), result, str(row["id"])),
            )
        return result

    def _repo_allowed(self, repo_full_name: str) -> bool:
        if not repo_full_name:
            return False
        settings = self.superagent.repo.get_settings()
        if not settings.repo_url:
            return False
        try:
            ref = parse_repo_url(settings.repo_url)
        except ValueError:
            return False
        return ref.full_name.lower() == repo_full_name.lower()

    def _find_task(self, fields: dict[str, Any]):
        """PR body 标记优先，repo+pr 反查兜底；取最近一条匹配。"""
        marker = TASK_MARKER_RE.search(fields.get("pr_body") or "")
        if marker:
            task = self.superagent.task(marker.group(1))
            if task is not None:
                return task
        repo = (fields.get("repo_full_name") or "").lower()
        pr_number = int(fields.get("pr_number") or 0)
        if not repo or not pr_number:
            return None
        for task in self.superagent.repo.list_all(limit=200):
            if task.pr_number == pr_number and repo in (task.repo_url_snapshot or "").lower():
                return task
        return None

    def _head_belongs_to_task(self, task, head_sha: str) -> bool:
        """乱序防护：head 属于任务任一 attempt 才触发工作。"""
        for attempt in self.superagent.repo.attempts_for_task(task.task_id):
            if head_sha and head_sha in (attempt.head_sha, attempt.remote_head_sha):
                return True
        return False

    def _update_task_pr(self, task, *, pr_state: str, outcome: str = "") -> None:
        with self.db.transaction() as conn:
            assignments = ["pr_state=?", "version=version+1", "updated_at=?"]
            params: list[Any] = [pr_state, utc_now_iso()]
            if outcome:
                assignments.append("outcome=?")
                params.append(outcome)
            params.append(task.task_id)
            conn.execute(
                f"UPDATE superagent_tasks SET {', '.join(assignments)} WHERE id=?",
                params,
            )

    def _insert_report(self, task, kind: str, summary: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO superagent_reports(id, task_id, attempt_id, kind, summary, "
                "question, head_sha, verification_ref, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (new_superagent_report_id(), task.task_id, "", kind,
                 summary[:2000], "", "", "", utc_now_iso()),
            )

    def _append_input(self, task, text: str) -> None:
        """评审/评论转任务输入：待评审/等待补充/失败的任务重新回到队列。"""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO superagent_inputs(id, task_id, source, external_event_id, "
                "actor_id, text, attachment_refs, created_at, consumed_attempt_id) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (new_superagent_input_id(), task.task_id, "webhook", "", 0,
                 text, "[]", utc_now_iso(), ""),
            )
            conn.execute(
                "UPDATE superagent_tasks SET status='queued', version=version+1, updated_at=? "
                "WHERE id=? AND status IN ('waiting_input','blocked','failed')",
                (utc_now_iso(), task.task_id),
            )

    def _notify(self, task, text: str) -> None:
        delivery = getattr(self.superagent, "delivery", None)
        if delivery is None:
            return
        target = self._notify_target(task)
        if target is None:
            return
        try:
            delivery.enqueue_text(
                owner_id=task.owner_id, target=target, text=text,
                dedup_key=f"superagent:wh:{task.task_id}:{utc_now_iso()}",
                source="superagent",
            )
        except Exception:  # noqa: BLE001
            logger.exception("webhook 通知入队失败 task=%s", task.task_id)

    def _notify_target(self, task) -> DeliveryTarget | None:
        if task.source_kind and task.source_ref:
            return DeliveryTarget(
                kind=task.source_kind, ref=task.source_ref,
                channel_account_id=task.source_channel_account_id,
            )
        channels = getattr(self.superagent, "channels", None)
        resolved = channels.delivery_target_for_owner(task.owner_id) if channels else None
        if resolved is None:
            return None
        return resolved if isinstance(resolved, DeliveryTarget) else target_from_channel(resolved)


def build_superagent_webhook_router(webhook_service: Any) -> Any:
    """公开路由：仅验签保护（无 JWT）；任何事件先落库。"""
    router = APIRouter(prefix="/api/superagent/webhook", tags=["superagent-webhook"])

    @router.post("")
    async def receive(
        request: Request,
        x_github_event: Annotated[str, Header()] = "",
        x_github_delivery: Annotated[str, Header()] = "",
        x_hub_signature_256: Annotated[str, Header()] = "",
    ):
        body = await request.body()
        status, payload = webhook_service.ingest(
            event_type=x_github_event, delivery_id=x_github_delivery,
            signature=x_hub_signature_256, body=body,
        )
        return JSONResponse(payload, status_code=status)

    return router

