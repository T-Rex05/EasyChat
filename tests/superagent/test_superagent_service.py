"""superagent 服务与 worker 回归（T1–T4）。

覆盖：快照与幂等受理、CAS 状态机、attempt 生命周期、权限撤销、
变更识别（代理自行 commit）、completed 门禁、验证门禁、Draft PR、
通知幂等、取消竞态、publish 恢复。git/runner/PR 全部注入假件。
"""
from __future__ import annotations

import pytest

from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.wechat import DisabledDeliverySender
from backend.modules.superagent.api import SuperagentService
from backend.modules.superagent.contracts import (
    TASK_BLOCKED,
    TASK_CANCELLED,
    TASK_QUEUED,
    TASK_RUNNING,
    TASK_SUCCEEDED,
    TASK_WAITING_INPUT,
)
from backend.modules.superagent.github import PullRequest
from backend.modules.superagent.runner import RunnerOutcome
from backend.modules.superagent.worker import SuperagentWorker
from backend.shared.errors import ForbiddenError, InvalidInputError
from tests.superagent.fakes import (
    CancelMidRunRunner,
    FakeCanceller,
    FakeGit,
    FakePRClient,
    FakeRunner,
    make_outcome,
)
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig

REPO_URL = "https://github.com/foo/bar.git"
HEAD1 = "a" * 40
HEAD2 = "c" * 40


async def _rig_with_worker(rig, *, status="", diff="", existing_pr=None):
    """装配 service + delivery(真实账本) + worker。返回 (service, admin, user, worker, delivery)。"""
    ready = rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)
    rig.db, rig.access = ready.db, ready.access
    delivery = DeliveryService(ready.db, sender=DisabledDeliverySender())
    service = SuperagentService(ready.db, access=ready.access, delivery=delivery)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    service.runner_ready = True
    admin = ready.seed_user(role="admin")
    user = ready.seed_user(role="user")
    service.update_settings(admin, enabled=True, repo_url=REPO_URL, base_branch="main",
                            github_token="ghp_test_token_1234567890")
    worker = SuperagentWorker(
        service,
        runner=FakeRunner(make_outcome()),
        delivery=delivery,
        channels_provider=lambda: None,
        workspace_root=rig.tmp_path / "ws",
        artifacts_root=rig.tmp_path / "verify",
        pr_client_factory=lambda token: FakePRClient(existing=existing_pr),
        git_runner=FakeGit(status=status, diff=diff),
        timezone="Asia/Shanghai",
    )
    return service, admin, user, worker, delivery


def _wire(worker: SuperagentWorker, *, git: FakeGit | None = None, runner=None, pr=None) -> None:
    worker._git_runner = git or FakeGit()
    if runner is not None:
        worker.runner = runner
    worker._pr_client_factory = lambda token: pr or FakePRClient()
    worker._helper_path = lambda: str(worker.workspace_root.parent / "helper.py")


# ---- 受理 / 快照 / 幂等 ------------------------------------------------------------

async def test_create_task_snapshots_repo_and_is_idempotent(rig) -> None:
    service, admin, user, _, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="修复登录", requirement="登录 500", source="web",
                               idempotency_key="evt-1")
    assert task.status == TASK_QUEUED
    assert task.repo_url_snapshot == "https://github.com/foo/bar.git"
    assert task.base_branch_snapshot == "main"
    assert task.branch.startswith("superagent/sag_")
    # 幂等：同 key 返回同一任务
    again = service.create_task(user, title="修复登录", requirement="登录 500",
                                idempotency_key="evt-1")
    assert again.task_id == task.task_id
    # 不同 key 新任务
    other = service.create_task(user, title="x", requirement="y", idempotency_key="evt-2")
    assert other.task_id != task.task_id


async def test_settings_change_after_creation_does_not_affect_accepted_task(rig) -> None:
    """验收矩阵 9：改仓库设置不改变已受理任务。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    service.create_task(user, title="t", requirement="r", idempotency_key="k9")
    service.update_settings(admin, repo_url="https://github.com/other/repo.git", base_branch="dev")
    git = FakeGit()
    runner = FakeRunner(make_outcome())
    pr_client = FakePRClient(existing=PullRequest(number=3, api_url="u",
                                                  html_url="https://github.com/foo/bar/pull/3"))
    _wire(worker, git=git, runner=runner, pr=pr_client)
    await worker.tick()
    # worker 用快照 clone；分支基线仍是快照的 main
    joined_calls = [" ".join(c) for c in git.calls]
    assert any("https://github.com/foo/bar.git" in c for c in joined_calls)
    assert not any("other/repo" in c for c in joined_calls)
    assert any("origin/main" in c for c in joined_calls)


# ---- CAS / attempt / 权限 ------------------------------------------------------------

async def test_claim_creates_attempt_and_late_result_is_rejected(rig) -> None:
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    claimed = service.repo.claim_next_task()
    assert claimed is not None
    claimed_task, attempt = claimed
    assert claimed_task.task_id == task.task_id
    assert claimed_task.status == TASK_RUNNING
    assert attempt.attempt_no == 1
    # CAS：终态迁移要求匹配 active_attempt_id；换一个假 attempt 必须失败
    from backend.modules.superagent.contracts import TaskAttempt

    fake_attempt = TaskAttempt(
        attempt_id="sat_" + "0" * 32, task_id=task.task_id, attempt_no=99, run_id="",
        session_id="", workspace_key="", state="running", checkpoint="", head_sha="",
        remote_head_sha="", pr_number=0, pr_url="", started_at="", heartbeat_at="",
        finished_at="", error_code="", error_summary="",
    )
    ok = worker._transition_terminal(
        claimed_task, fake_attempt, to_status=TASK_SUCCEEDED, task_fields={},
        report_kind=None,
    )
    assert ok is False
    assert service.task(task.task_id).status == TASK_RUNNING  # 未被迟到结果覆盖


async def test_permission_revoked_blocks_execution(rig) -> None:
    """验收矩阵 1/9：撤销权限后执行阶段重新检查。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    service.access.repo.set_user_permission(user.user_id, "superagent.create", False)
    service.access.invalidate_all()
    _wire(worker)
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_BLOCKED
    assert "权限" in final.error


async def test_legacy_task_without_snapshot_cannot_retry(rig) -> None:
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    # 模拟 0020 之前的旧任务：清空快照
    with service.repo.db.transaction() as conn:
        conn.execute(
            "UPDATE superagent_tasks SET repo_url_snapshot='', base_branch_snapshot='' WHERE id=?",
            (task.task_id,),
        )
    with pytest.raises(InvalidInputError, match="快照"):
        service.retry_task(user, task.task_id)


async def test_cross_user_access_rules(rig) -> None:
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    other = rig.seed_user(role="user")
    task = service.create_task(user, title="t", requirement="r")
    # 撤销 view 权限者不可见
    service.access.repo.set_user_permission(other.user_id, "superagent.view", False)
    service.access.invalidate_all()
    with pytest.raises(ForbiddenError):
        service.get_task(other, task.task_id)
    # 恢复 view 后：可见但跨用户取消需要 manage
    service.access.repo.set_user_permission(other.user_id, "superagent.view", True)
    service.access.invalidate_all()
    with pytest.raises(ForbiddenError):
        await service.cancel_task(other, task.task_id)
    # manage 可跨用户取消
    await service.cancel_task(admin, task.task_id)
    assert service.task(task.task_id).status == TASK_CANCELLED


# ---- worker 全流程 ------------------------------------------------------------------

async def test_worker_runs_task_and_creates_draft_pr(rig) -> None:
    from backend.modules.delivery.contracts import DeliveryTarget

    service, admin, user, worker, delivery = await _rig_with_worker(rig)
    task = service.create_task(
        user, title="修复登录", requirement="修复登录 500", source="wechat",
        source_target=DeliveryTarget(kind="wechat", ref="wx-user-1", channel_account_id="chn_1"),
    )
    git = FakeGit(status=" M app.py\n", heads=[HEAD1, HEAD1, HEAD1, HEAD2])
    pr_client = FakePRClient()
    runner = FakeRunner(make_outcome("修复了 login.py 的空指针。"))
    _wire(worker, git=git, runner=runner, pr=pr_client)

    assert await worker.tick() == 1
    final = service.task(task.task_id)
    assert final.status == TASK_SUCCEEDED
    assert final.pr_state == "draft"
    assert final.pr_url.endswith("/pull/7")
    assert final.result_summary == "修复了 login.py 的空指针。"
    # PR 调用：draft、head=任务分支、base=快照基线
    assert pr_client.created[0]["head"] == final.branch
    assert pr_client.created[0]["base"] == "main"
    assert "EasyChat-Superagent-Task:" in pr_client.created[0]["body"]
    # git 调用：无凭证 URL；argv 与 helper 参数都不含 token
    joined_calls = [" ".join(c) for c in git.calls]
    assert any("https://github.com/foo/bar.git" in c for c in joined_calls)
    assert not any("ghp_test_token" in c for c in joined_calls)
    assert not any("ghp_test_token" in " ".join(git.git_args_seen) for _ in [0])
    # push 限时存在且 ≤ 300
    push_idx = next(i for i, c in enumerate(git.calls) if c[0] == "push")
    assert git.timeouts_seen[push_idx] <= 300
    # attempt checkpoint 推进到 pr_created；head 记录
    attempts = service.repo.attempts_for_task(task.task_id)
    assert attempts[0].checkpoint == "pr_created"
    assert attempts[0].head_sha == HEAD2
    # 同事务回执：真实 deliveries 行存在且 dedup 含 attempt/report/target
    conn = rig.db.connect()
    try:
        rows = conn.execute(
            "SELECT dedup_key FROM deliveries WHERE source='superagent'"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert f"a{attempts[0].attempt_no}:ready" in str(rows[0]["dedup_key"])


async def test_agent_self_commit_is_detected_via_base_diff(rig) -> None:
    """验收矩阵 5：代理自行 commit 后 porcelain 为空，base...HEAD 仍识别变更。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    git = FakeGit(status="", diff=" app.py | 3 +-\n", heads=[HEAD1, HEAD1, HEAD1, HEAD2])
    pr_client = FakePRClient()
    _wire(worker, git=git, pr=pr_client)
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_SUCCEEDED
    assert final.pr_url.endswith("/pull/7")
    assert any("diff" in " ".join(c) and "..." in " ".join(c) for c in git.calls)


async def test_stream_ended_without_completed_fails_task(rig) -> None:
    """P0 门禁：runtime 流意外结束 ≠ 完成。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    _wire(worker, runner=FakeRunner(RunnerOutcome(completed=False, error="连接中断")))
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == "failed"
    assert "未正常完成" in final.error


async def test_missing_credentials_blocks(rig) -> None:
    """缺凭证 → blocked（可重试），不再伪装 failed。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    service.update_settings(admin, github_token="")  # 清除凭证
    task = service.create_task(user, title="t", requirement="r")
    git = FakeGit(heads=[HEAD1, HEAD1, HEAD1])
    _wire(worker, git=git)
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_BLOCKED
    assert "凭证" in final.error
    reports = service.repo.reports_for_task(task.task_id)
    assert reports[0].kind == "blocked"


async def test_no_changes_succeeds_without_pr(rig) -> None:
    from backend.modules.delivery.contracts import DeliveryTarget

    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(
        user, title="体检", requirement="检查代码", source="wechat",
        source_target=DeliveryTarget(kind="wechat", ref="wx-user-1", channel_account_id="chn_1"),
    )
    git = FakeGit(status="", diff="", heads=[HEAD1, HEAD1, HEAD1, HEAD1])
    _wire(worker, git=git, pr=FakePRClient())
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_SUCCEEDED
    assert final.pr_url == ""
    kinds = [e["kind"] for e in service.repo.events_for_task(task.task_id)]
    assert "no_changes" in kinds
    conn = rig.db.connect()
    try:
        rows = conn.execute(
            "SELECT dedup_key FROM deliveries WHERE source='superagent'"
        ).fetchall()
    finally:
        conn.close()
    assert any("no_changes" in str(r["dedup_key"]) for r in rows)


async def test_question_protocol_enters_waiting_input_and_input_resumes(rig) -> None:
    """追问 → waiting_input → 补充 → 重新入队续跑（同一任务）。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    outcome = make_outcome("需要知道目标 Python 版本。\nQUESTION: 目标 Python 版本是多少？")
    _wire(worker, git=FakeGit(heads=[HEAD1, HEAD1]),
          runner=FakeRunner(outcome), pr=FakePRClient())
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_WAITING_INPUT
    reports = service.repo.reports_for_task(task.task_id)
    assert reports[0].kind == "question"
    assert "Python" in reports[0].question
    # 用户补充（幂等键防重）
    first = service.append_task_input(user, task.task_id, text="3.12", source="wechat",
                                      external_event_id="wx-1")
    dup = service.append_task_input(user, task.task_id, text="3.12", source="wechat",
                                    external_event_id="wx-1")
    assert dup.input_id == first.input_id
    assert service.task(task.task_id).status == TASK_QUEUED
    # 第二次执行：runner 收到补充输入
    runner = FakeRunner(make_outcome("改好了。"))
    _wire(worker, git=FakeGit(status=" M a.py\n", heads=[HEAD1, HEAD1, HEAD1, HEAD2]),
          runner=runner, pr=FakePRClient())
    await worker.tick()
    request = runner.requests[-1]
    assert any("3.12" in item for item in request.extra_inputs)
    assert service.task(task.task_id).status == TASK_SUCCEEDED


async def test_cancel_during_coding_lands_cancelled_without_pr(rig) -> None:
    """验收矩阵 6：运行中取消按真实状态显示，协作中断被 await。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    canceller = FakeCanceller()
    service.set_run_canceller(canceller)
    task = service.create_task(user, title="t", requirement="r")

    async def trigger_cancel():
        await service.cancel_task(user, task.task_id)

    _wire(worker, git=FakeGit(heads=[HEAD1, HEAD1]),
          runner=CancelMidRunRunner(make_outcome("晚到的结果"), trigger_cancel),
          pr=FakePRClient())
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_CANCELLED
    assert final.pr_url == ""
    # 协作取消被 await（异步 canceller 真正执行）
    assert len(canceller.cancelled) >= 1
    attempts = service.repo.attempts_for_task(task.task_id)
    assert attempts[0].state == "interrupted"


async def test_cancel_after_push_records_race_and_finishes(rig) -> None:
    """取消/发布竞态：push 已发出后取消 → cancelled_after_publication + 完成发布。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")

    async def cancel_during_push(args: str) -> None:
        if args.startswith("push"):
            await service.cancel_task(user, task.task_id)

    git = FakeGit(status=" M a.py\n", heads=[HEAD1, HEAD1, HEAD1, HEAD2],
                  hooks={"push": cancel_during_push})
    _wire(worker, git=git, pr=FakePRClient())
    await worker.tick()
    final = service.task(task.task_id)
    # 已推送的动作以远端实际结果为准：完成发布（非 cancelled）
    assert final.status == TASK_SUCCEEDED
    assert final.pr_url != ""
    kinds = [e["kind"] for e in service.repo.events_for_task(task.task_id)]
    assert "cancelled_after_publication" in kinds


async def test_push_failure_then_retry_reconciles_pr(rig) -> None:
    """push 后建 PR 失败（响应丢失）→ 重试按远端对账复用 PR，不重复创建。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    ghost_pr = PullRequest(number=11, api_url="u", html_url="https://github.com/foo/bar/pull/11",
                           state="open", draft=True, head_ref=task.branch)
    # 第一次：PR 创建"失败"但远端实际已创建（网络歧义）
    pr_client = FakePRClient(create_error=RuntimeError("connection reset"),
                             register_on_create_error=ghost_pr)
    _wire(worker, git=FakeGit(status=" M a.py\n", heads=[HEAD1, HEAD1, HEAD1, HEAD2]),
          pr=pr_client)

    await worker.tick()
    assert service.task(task.task_id).status == "failed"
    assert pr_client.created == []  # 响应丢失，本地无记录

    # 重试：新 attempt；diff base...HEAD 非空（提交已在分支上）；远端 PR 复用
    assert service.retry_task(user, task.task_id).status == TASK_QUEUED
    _wire(worker, git=FakeGit(status=" M a.py\n", heads=[HEAD1, HEAD1, HEAD1, HEAD2]),
          runner=FakeRunner(make_outcome("重试完成。")), pr=pr_client)
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_SUCCEEDED
    assert final.pr_url.endswith("/pull/11")
    assert pr_client.created == []  # 未重复创建
    kinds = [e["kind"] for e in service.repo.events_for_task(task.task_id)]
    assert "reconciled" in kinds
    attempts = service.repo.attempts_for_task(task.task_id)
    assert len(attempts) == 2
    assert attempts[1].attempt_no == 2


async def test_notification_dedup_across_attempts(rig) -> None:
    """验收矩阵 8：失败通知与重试成功通知是两条独立回执。"""
    from backend.modules.delivery.contracts import DeliveryTarget

    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(
        user, title="t", requirement="r", source="wechat",
        source_target=DeliveryTarget(kind="wechat", ref="wx-user-1", channel_account_id="chn_1"),
    )
    _wire(worker, runner=FakeRunner(RunnerOutcome(completed=False, error="模型超时")),
          pr=FakePRClient())
    await worker.tick()
    assert service.task(task.task_id).status == "failed"

    service.retry_task(user, task.task_id)
    _wire(worker, git=FakeGit(status=" M a.py\n", heads=[HEAD1, HEAD1, HEAD1, HEAD2]),
          runner=FakeRunner(make_outcome()), pr=FakePRClient())
    await worker.tick()
    conn = rig.db.connect()
    try:
        rows = conn.execute(
            "SELECT dedup_key FROM deliveries WHERE source='superagent'"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 2
    keys = {str(r["dedup_key"]) for r in rows}
    assert any("a1:failed" in k for k in keys)
    assert any("a2:ready" in k for k in keys)


async def test_git_error_messages_are_sanitized(rig) -> None:
    """验收矩阵 10：git 错误里的 token 被脱敏。"""
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    git = FakeGit(fail_on=(("clone", "remote: Invalid credentials for ghp_test_token_1234567890"),))
    _wire(worker, git=git)
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == "failed"
    assert "ghp_test_token" not in final.error
    assert "***" in final.error


async def test_worker_disabled_gate_and_queued_cancel(rig) -> None:
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    service.update_settings(admin, enabled=False)
    assert await worker.tick() == 0
    cancelled = await service.cancel_task(user, task.task_id)
    assert cancelled.status == TASK_CANCELLED
    service.update_settings(admin, enabled=True)
    assert await worker.tick() == 0  # 取消后的任务不再执行


async def test_startup_recovery_marks_interrupted(rig) -> None:
    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    service.repo.claim_next_task()
    assert service.task(task.task_id).status == TASK_RUNNING
    assert service.recover_interrupted() == 1
    final = service.task(task.task_id)
    assert final.status == "interrupted"
    attempts = service.repo.attempts_for_task(task.task_id)
    assert attempts[0].state == "interrupted"
    # interrupted 可重试
    assert service.retry_task(user, task.task_id).status == TASK_QUEUED


async def test_worker_sanitizes_legacy_workspace_remotes(rig) -> None:
    """T2：旧工作区 origin 携带 userinfo → 启动清理。"""
    import subprocess as sp

    service, admin, user, worker, _ = await _rig_with_worker(rig)
    legacy = rig.tmp_path / "ws" / "legacy" / "repo"
    legacy.mkdir(parents=True)
    sp.run(["git", "init", "-q", str(legacy)], check=True)
    sp.run(["git", "remote", "add", "origin",
            "https://ghp_leaked_token@github.com/foo/bar.git"], cwd=str(legacy), check=True)
    worker._sanitize_legacy_remotes()
    url = sp.run(["git", "remote", "get-url", "origin"], cwd=str(legacy),
                 capture_output=True, text=True).stdout.strip()
    assert url == "https://github.com/foo/bar.git"


async def test_concurrent_claim_single_owner_and_retry_session_monotonic(rig) -> None:
    """P5 矩阵:双认领只有一个主人(queued→running 同事务 CAS);失败重认领换新 attempt
    与新 session(旧 session 不复用),晚到结果无法与新运行互相覆盖。"""
    from backend.modules.superagent.contracts import TASK_FAILED

    service, admin, user, worker, _ = await _rig_with_worker(rig)
    task = service.create_task(user, title="t", requirement="r")
    first = service.repo.claim_next_task()
    assert first is not None
    claimed_task, attempt1 = first
    # 第二次认领必须空转:任务已 running
    assert service.repo.claim_next_task() is None
    # 模拟执行失败回终态
    ok = worker._transition_terminal(
        claimed_task, attempt1, to_status=TASK_FAILED, task_fields={}, report_kind=None,
    )
    assert ok is True
    # 重新受理后再次认领:attempt #2,session 换新
    service.retry_task(user, task.task_id)
    second = service.repo.claim_next_task()
    assert second is not None
    _t2, attempt2 = second
    assert attempt2.attempt_no == 2
    assert attempt2.session_id != attempt1.session_id
    fresh = service.task(task.task_id)
    attempts = service.repo.attempts_for_task(task.task_id)
    assert [a.attempt_no for a in attempts] == [1, 2]
    assert fresh.active_attempt_id == attempt2.attempt_id
