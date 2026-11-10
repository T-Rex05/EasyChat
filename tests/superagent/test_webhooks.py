"""T7 GitHub webhook 回归：验签、去重、allowlist、任务关联、乱序与机器人防护。"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.delivery.wechat import DisabledDeliverySender
from backend.modules.superagent.api import SuperagentService
from backend.modules.superagent.webhooks import (
    WEBHOOK_JOB_KIND,
    WebhookService,
    verify_signature,
)
from backend.platform.jobs import JobQueue
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig

SECRET = "whsec_test_12345"
REPO_URL = "https://github.com/foo/bar.git"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _admin(rig):
    return rig.seed_user(role="super_admin", username=f"adm_{uuid.uuid4().hex[:6]}")


def _user(rig):
    return rig.seed_user(role="user", grants=("superagent.view", "superagent.create"),
                         username=f"u_{uuid.uuid4().hex[:6]}")


async def _env(rig):
    ready = rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)
    rig.db, rig.access = ready.db, ready.access
    delivery = DeliveryService(ready.db, sender=DisabledDeliverySender())
    service = SuperagentService(ready.db, access=ready.access, delivery=delivery)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    service.runner_ready = True
    admin = _admin(ready)
    user = _user(ready)
    service.update_settings(admin, enabled=True, repo_url=REPO_URL, base_branch="main",
                            github_token="ghp_t_1234567890")
    queue = JobQueue(ready.db, clock=ready.clock)
    hooks = WebhookService(ready.db, superagent=service, queue=queue, webhook_secret=SECRET)
    return ready, service, hooks, queue, admin, user, delivery


def _pr_payload(*, action: str, number: int = 7, merged: bool = False,
                body: str = "EasyChat-Superagent-Task: sag_placeholder",
                sender: dict | None = None, head_sha: str = "") -> dict:
    return {
        "action": action,
        "repository": {"full_name": "foo/bar"},
        "pull_request": {"number": number, "merged": merged, "body": body,
                         "head": {"sha": head_sha}},
        "sender": sender or {"login": "maintainer", "type": "User"},
    }


def _ingest(hooks: WebhookService, event_type: str, payload: dict, *,
            delivery_id: str = "d1", secret: str = SECRET):
    body = json.dumps(payload).encode()
    return hooks.ingest(
        event_type=event_type, delivery_id=delivery_id,
        signature=_sign(body, secret), body=body,
    )


async def test_signature_verification(rig) -> None:
    ready, service, hooks, queue, admin, user, _ = await _env(rig)
    body = json.dumps(_pr_payload(action="closed")).encode()
    assert verify_signature(SECRET, body, _sign(body))
    assert not verify_signature(SECRET, body, "sha256=deadbeef")
    assert not verify_signature(SECRET, body, "")
    assert not verify_signature("", body, _sign(body))  # 缺配置一律拒绝
    status, payload = hooks.ingest(
        event_type="pull_request", delivery_id="d-sig",
        signature="sha256=bad", body=body,
    )
    assert status == 403


async def test_ingest_dedups_and_allowlists(rig) -> None:
    ready, service, hooks, queue, admin, user, _ = await _env(rig)
    payload = _pr_payload(action="closed")
    status1, p1 = _ingest(hooks, "pull_request", payload, delivery_id="d-dup")
    status2, p2 = _ingest(hooks, "pull_request", payload, delivery_id="d-dup")
    assert status1 == 202 and status2 == 200
    assert p2.get("duplicate") is True
    # allowlist：其他仓库被忽略
    status3, p3 = _ingest(hooks, "pull_request",
                          {**payload, "repository": {"full_name": "evil/repo"}},
                          delivery_id="d-other")
    assert status3 == 200 and p3.get("ignored") == "repo_not_allowed"
    # 不支持的事件
    status4, p4 = _ingest(hooks, "push", {"repository": {"full_name": "foo/bar"}},
                          delivery_id="d-push")
    assert p4.get("ignored") == "unsupported_event"
    # 坏 JSON
    bad = hooks.ingest(event_type="pull_request", delivery_id="d-bad",
                       signature=_sign(b"not json"), body=b"not json")
    assert bad[0] == 400


async def test_pr_closed_merged_updates_task_and_notifies(rig) -> None:
    ready, service, hooks, queue, admin, user, delivery = await _env(rig)
    task = service.create_task(
        user, title="t", requirement="r", source="wechat",
        source_target=DeliveryTarget(kind="wechat", ref="wx_u", channel_account_id="chn_1"),
        idempotency_key="wh-1",
    )
    # 任务已发布 PR（模拟 worker 完成后的状态）
    service.repo.update_task_fields(
        task.task_id, pr_url="https://github.com/foo/bar/pull/7", pr_number=7, pr_state="draft",
    )
    marker_body = f"EasyChat-Superagent-Task: {task.task_id}"
    _ingest(hooks, "pull_request",
            _pr_payload(action="closed", merged=True, body=marker_body), delivery_id="d-m")
    _drain_with(hooks, queue)
    final = service.task(task.task_id)
    assert final.pr_state == "merged"
    assert final.outcome == "merged"
    conn = rig.db.connect()
    try:
        rows = conn.execute("SELECT content_text FROM deliveries WHERE source='superagent'").fetchall()
        reports = conn.execute("SELECT kind FROM superagent_reports WHERE task_id=?", (task.task_id,)).fetchall()
    finally:
        conn.close()
    assert any("合并" in str(r["content_text"]) for r in rows)
    assert any(r["kind"] == "progress" for r in reports)


async def test_pr_closed_unmerged_records_outcome(rig) -> None:
    ready, service, hooks, queue, admin, user, _ = await _env(rig)
    task = service.create_task(user, title="t", requirement="r", idempotency_key="wh-2")
    service.repo.update_task_fields(task.task_id, pr_url="u", pr_number=9, pr_state="draft")
    _ingest(hooks, "pull_request",
            _pr_payload(action="closed", merged=False, number=9,
                        body=f"EasyChat-Superagent-Task: {task.task_id}"),
            delivery_id="d-c")
    _drain_with(hooks, queue)
    final = service.task(task.task_id)
    assert final.pr_state == "closed"
    assert final.outcome == "closed_unmerged"


async def test_review_and_comment_become_task_inputs(rig) -> None:
    ready, service, hooks, queue, admin, user, _ = await _env(rig)
    task = service.create_task(user, title="t", requirement="r", idempotency_key="wh-3")
    service.repo.transition_task(task.task_id, from_statuses=frozenset({"queued"}),
                                 to_status="failed", event_kind="failed", event_detail="x")
    base = {"repository": {"full_name": "foo/bar"},
            "pull_request": {"number": 7, "body": f"EasyChat-Superagent-Task: {task.task_id}"}}
    _ingest(hooks, "pull_request_review",
            {**base, "action": "submitted",
             "review": {"state": "changes_requested", "body": "请补测试"},
             "sender": {"login": "rev", "type": "User"}},
            delivery_id="d-r1")
    _ingest(hooks, "issue_comment",
            {**base, "action": "created",
             "issue": {"number": 7},
             "comment": {"body": "顺手升级依赖"},
             "sender": {"login": "dev", "type": "User"}},
            delivery_id="d-c1")
    _drain_with(hooks, queue)
    inputs = service.repo.unconsumed_inputs(task.task_id)
    texts = [i.text for i in inputs]
    assert any("[GitHub 评审 changes_requested] 请补测试" in x for x in texts)
    assert any("[GitHub 评论] 顺手升级依赖" in x for x in texts)
    # 输入把 failed 任务带回队列（可续跑）
    assert service.task(task.task_id).status == "queued"


async def test_bot_and_stale_head_are_ignored(rig) -> None:
    ready, service, hooks, queue, admin, user, _ = await _env(rig)
    task = service.create_task(user, title="t", requirement="r", idempotency_key="wh-4")
    service.repo.update_task_fields(task.task_id, pr_url="u", pr_number=11, pr_state="draft")
    marker = f"EasyChat-Superagent-Task: {task.task_id}"
    # Bot 发的评审不触发输入
    _ingest(hooks, "pull_request_review",
            {"action": "submitted", "repository": {"full_name": "foo/bar"},
             "pull_request": {"number": 11, "body": marker},
             "review": {"state": "approved", "body": "lgtm"},
             "sender": {"login": "easychat-bot", "type": "Bot"}},
            delivery_id="d-b1")
    # 旧 head 的 CI 失败不触发报告
    _ingest(hooks, "check_run",
            {"action": "completed", "repository": {"full_name": "foo/bar"},
             "check_run": {"name": "ci", "conclusion": "failure", "head_sha": "old" + "0" * 37},
             "pull_request": {"number": 11, "body": marker, "head": {"sha": "old" + "0" * 37}},
             "sender": {"login": "maintainer", "type": "User"}},
            delivery_id="d-b2")
    results = _drain_with(hooks, queue)
    assert "bot_skipped" in results
    assert "stale_head_ignored" in results
    # 没有任何 webhook 来源的输入/报告产生（受理本身的 requirement input 不算）
    assert all(i.source != "webhook" for i in service.repo.unconsumed_inputs(task.task_id))
    assert service.repo.reports_for_task(task.task_id) == []


async def test_check_run_failure_on_known_head_reports(rig) -> None:
    ready, service, hooks, queue, admin, user, _ = await _env(rig)
    service.create_task(user, title="t", requirement="r", idempotency_key="wh-5")
    # 写一条 attempt（head 匹配）模拟已发布
    claimed = service.repo.claim_next_task()
    assert claimed is not None
    claimed_task, attempt = claimed
    from backend.modules.superagent.contracts import CK_PUSHED

    service.repo.update_attempt(attempt.attempt_id, head_sha="e" * 40, checkpoint=CK_PUSHED)
    _ingest(hooks, "check_run",
            {"action": "completed", "repository": {"full_name": "foo/bar"},
             "check_run": {"name": "pytest", "conclusion": "failure", "head_sha": "e" * 40},
             "pull_request": {"number": 12,
                              "body": f"EasyChat-Superagent-Task: {claimed_task.task_id}",
                              "head": {"sha": "e" * 40}},
             "sender": {"login": "maintainer", "type": "User"}},
            delivery_id="d-ci")
    results = _drain_with(hooks, queue)
    assert "ci_failure_reported" in results
    reports = service.repo.reports_for_task(claimed_task.task_id)
    assert any("CI 失败" in r.summary for r in reports)


def _drain_with(hooks: WebhookService, queue: JobQueue) -> list[str]:
    results = []
    while True:
        lease = queue.claim("test-worker", kinds=(WEBHOOK_JOB_KIND,))
        if lease is None:
            break
        event_id = str(lease.payload_json()["event_id"])
        results.append(hooks.process_event(event_id))
        queue.complete(lease)
    return results


async def test_auto_fix_requeues_terminal_task_when_enabled(rig) -> None:
    """P7：开关开启，CI 失败把已发布成功任务重新入队（轮次+1、修复输入注入、原任务分支复用）。"""
    from backend.modules.delivery.contracts import DeliveryTarget

    ready, service, hooks, queue, admin, user, delivery = await _env(rig)
    service.update_settings(admin, auto_fix_enabled=True, auto_fix_max_rounds=2)
    task = service.create_task(
        user, title="t", requirement="r", idempotency_key="af-1",
        source="wechat",
        source_target=DeliveryTarget(kind="wechat", ref="wx-af", channel_account_id="chn_1"),
    )
    claimed = service.repo.claim_next_task()
    assert claimed is not None
    _t, attempt = claimed
    from backend.modules.superagent.contracts import CK_PUSHED

    service.repo.update_attempt(attempt.attempt_id, head_sha="f" * 40, checkpoint=CK_PUSHED)
    service.repo.transition_task(task.task_id, from_statuses={"running"}, to_status="succeeded")
    _ingest(hooks, "check_run",
            {"action": "completed", "repository": {"full_name": "foo/bar"},
             "check_run": {"name": "pytest", "conclusion": "failure", "head_sha": "f" * 40},
             "pull_request": {"number": 13,
                              "body": f"EasyChat-Superagent-Task: {task.task_id}",
                              "head": {"sha": "f" * 40}},
             "sender": {"login": "maintainer", "type": "User"}},
            delivery_id="d-af1")
    results = _drain_with(hooks, queue)
    assert "auto_fix_queued" in results
    fresh = service.task(task.task_id)
    assert fresh.status == "queued" and fresh.auto_fix_rounds == 1
    inputs = service.repo.unconsumed_inputs(task.task_id)
    assert any("[自动修复]" in str(i.text) for i in inputs)
    # 同一事件内的两条通知（❌CI 失败 + 🔁自动入队）必须各自成行：
    # 时间戳键同秒碰撞会被 enqueue 合并为既有行。
    conn = ready.db.connect()
    try:
        notes = conn.execute(
            "SELECT content_text FROM deliveries WHERE source='superagent'"
        ).fetchall()
    finally:
        conn.close()
    assert len(notes) == 2
    assert any("🔁" in str(r["content_text"]) for r in notes)


async def test_auto_fix_budget_exhausted_blocks(rig) -> None:
    """P7：预算耗尽→blocked 等人工，不再入队；CAS 保证只迁移一次。"""
    ready, service, hooks, queue, admin, user, _ = await _env(rig)
    service.update_settings(admin, auto_fix_enabled=True, auto_fix_max_rounds=1)
    service.create_task(user, title="t", requirement="r", idempotency_key="af-2")
    claimed = service.repo.claim_next_task()
    task, attempt = claimed  # type: ignore[misc]
    from backend.modules.superagent.contracts import CK_PUSHED

    service.repo.update_attempt(attempt.attempt_id, head_sha="g" * 40, checkpoint=CK_PUSHED)
    service.repo.transition_task(task.task_id, from_statuses={"running"}, to_status="succeeded")
    # 预支一轮：模拟预算已用完
    service.repo.auto_fix_requeue(task.task_id, max_rounds=1, detail="第 1 轮")
    service.repo.transition_task(task.task_id, from_statuses={"queued"}, to_status="succeeded")
    _ingest(hooks, "check_run",
            {"action": "completed", "repository": {"full_name": "foo/bar"},
             "check_run": {"name": "pytest", "conclusion": "failure", "head_sha": "g" * 40},
             "pull_request": {"number": 14,
                              "body": f"EasyChat-Superagent-Task: {task.task_id}",
                              "head": {"sha": "g" * 40}},
             "sender": {"login": "maintainer", "type": "User"}},
            delivery_id="d-af2")
    results = _drain_with(hooks, queue)
    assert "auto_fix_budget_exhausted" in results
    fresh = service.task(task.task_id)
    assert fresh.status == "blocked" and fresh.auto_fix_rounds == 1


async def test_auto_fix_skips_human_paused(rig) -> None:
    """P7：人工暂停态（cancel_requested）不被自动修复触活——只有人类指令能解除暂停。"""
    ready, service, hooks, queue, admin, user, _ = await _env(rig)
    service.update_settings(admin, auto_fix_enabled=True, auto_fix_max_rounds=2)
    service.create_task(user, title="t", requirement="r", idempotency_key="af-3")
    claimed = service.repo.claim_next_task()
    task, attempt = claimed  # type: ignore[misc]
    from backend.modules.superagent.contracts import CK_PUSHED

    service.repo.update_attempt(attempt.attempt_id, head_sha="h" * 40, checkpoint=CK_PUSHED)
    service.repo.transition_task(task.task_id, from_statuses={"running"},
                                 to_status="cancel_requested")
    _ingest(hooks, "check_run",
            {"action": "completed", "repository": {"full_name": "foo/bar"},
             "check_run": {"name": "pytest", "conclusion": "failure", "head_sha": "h" * 40},
             "pull_request": {"number": 15,
                              "body": f"EasyChat-Superagent-Task: {task.task_id}",
                              "head": {"sha": "h" * 40}},
             "sender": {"login": "maintainer", "type": "User"}},
            delivery_id="d-af3")
    results = _drain_with(hooks, queue)
    assert "ci_failure_reported" in results and "auto_fix_queued" not in results
    assert service.task(task.task_id).auto_fix_rounds == 0
