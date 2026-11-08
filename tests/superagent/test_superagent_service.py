"""superagent：受理 gate、权限、生命周期、worker 执行全流程（假 git/PR/运行时）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.modules.superagent.api import SuperagentService
from backend.modules.superagent.contracts import (
    EVENT_NO_CHANGES,
    EVENT_PR_CREATED,
    EVENT_STARTED,
    TASK_CANCELLED,
    TASK_QUEUED,
    TASK_SUCCEEDED,
)
from backend.modules.superagent.github import PullRequest
from backend.modules.superagent.worker import SuperagentWorker
from backend.runtime.contracts import RuntimeEvent
from backend.shared.errors import ForbiddenError, InvalidInputError
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig

REPO_URL = "https://github.com/foo/bar.git"


def _service(rig) -> tuple[SuperagentService, object, object]:
    ready = rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)
    rig.db, rig.access = ready.db, ready.access
    service = SuperagentService(ready.db, access=ready.access)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    admin = ready.seed_user(role="admin")
    user = ready.seed_user(role="user")
    return service, admin, user


def _enable(service: SuperagentService, admin, *, token: str = "gh_token_1234567890") -> None:
    service.update_settings(
        admin, enabled=True, repo_url=REPO_URL, base_branch="main", github_token=token,
    )


def _worker(
    rig, service: SuperagentService, runtime, *,
    git_runner=None, pr_client=None, workspace_root: Path | None = None,
) -> SuperagentWorker:
    return SuperagentWorker(
        service,
        runtime=runtime,
        delivery=None,
        channels_provider=lambda: None,
        workspace_root=workspace_root or (rig.tmp_path / "ws"),
        encryption_secret=TEST_ENCRYPTION_SECRET,
        pr_client=pr_client,
        git_runner=git_runner or _fake_git(clean=False),
        timezone="Asia/Shanghai",
    )


def _fake_git(*, clean: bool, calls: list | None = None):
    """假 git runner：status 按 clean 意愿返回；其余命令成功并记录。"""
    seen = calls if calls is not None else []

    async def run(cwd, *args):
        seen.append((cwd, args))
        if args[:1] == ("status",):
            return 0, ("" if clean else " M app.py\n"), ""
        return 0, "", ""

    return run


class _FakePRClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_pull_request(self, *, repo_url, title, head, base, body):
        self.calls.append(
            {"repo_url": repo_url, "title": title, "head": head, "base": base, "body": body}
        )
        return PullRequest(number=7, api_url="https://api/pulls/7", html_url="https://github.com/foo/bar/pull/7")


def _completed(final_response: str) -> list[RuntimeEvent]:
    return [RuntimeEvent(kind="completed", payload={"result": {"final_response": final_response, "completed": True}})]


def _setup_workspace(root: Path) -> None:
    """预置 .git 目录，跳过 clone 路径（clone 需要真实网络）。"""
    (root / "foo__bar" / ".git").mkdir(parents=True, exist_ok=True)


# ---- 受理与权限 ------------------------------------------------------------------

async def test_create_task_requires_enabled_gate(rig) -> None:
    service, admin, _ = _service(rig)
    with pytest.raises(InvalidInputError):
        service.create_task(
            admin, title="t", requirement="r", source="web",
        )  # 未启用


async def test_create_task_and_queue(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    task = service.create_task(
        user, title="修复登录", requirement="登录页 500，修复它", source="web",
    )
    assert task.status == TASK_QUEUED
    assert task.branch.startswith("superagent/sag_")
    assert task.owner_id == user.user_id
    kinds = [e.kind for e in service.list_events(user, task.task_id)]
    assert kinds[0] == "created"


async def test_user_cannot_manage_settings_or_others_tasks(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    task = service.create_task(admin, title="a", requirement="b", source="web")
    with pytest.raises(ForbiddenError):
        service.get_settings(user)
    with pytest.raises(ForbiddenError):
        service.get_task(user, task.task_id)


async def test_token_is_encrypted_and_masked(rig) -> None:
    service, admin, _ = _service(rig)
    _enable(service, admin)
    settings = service.get_settings(admin)
    assert settings.has_github_token
    assert "gh_token" not in settings.github_token_mask
    raw = service.repo.get_token_encrypted()
    assert raw.startswith("enc:v1:")


# ---- worker 执行 ------------------------------------------------------------------


async def test_worker_runs_task_and_creates_pr(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    task = service.create_task(user, title="修复登录", requirement="修复登录 500", source="wechat")
    rig.runtime.script_events(_completed("修复了 login.py 的空指针。"))
    workspace_root = rig.tmp_path / "ws"
    _setup_workspace(workspace_root)
    pr_client = _FakePRClient()
    worker = _worker(rig, service, rig.runtime, pr_client=pr_client,
                     workspace_root=workspace_root)

    executed = await worker.tick()
    assert executed == 1
    final = service.task(task.task_id)
    assert final.status == TASK_SUCCEEDED
    assert final.pr_url.endswith("/pull/7")
    assert final.pr_number == 7
    assert final.result_summary == "修复了 login.py 的空指针。"
    assert pr_client.calls[0]["head"] == final.branch
    assert pr_client.calls[0]["base"] == "main"
    kinds = [e.kind for e in service.list_events(user, task.task_id)]
    assert EVENT_STARTED in kinds and EVENT_PR_CREATED in kinds
    # 运行时请求：独立 source、编码工具集、需求文本
    request = rig.runtime.requests[-1]
    assert request.context.source == "superagent"
    assert request.allowed_tools == frozenset({"terminal", "file", "web"})
    assert "修复登录 500" in request.text


async def test_worker_no_changes_succeeds_without_pr(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    task = service.create_task(user, title="体检", requirement="检查代码", source="web")
    rig.runtime.script_events(_completed("没有需要改动的地方。"))
    workspace_root = rig.tmp_path / "ws"
    _setup_workspace(workspace_root)
    worker = _worker(rig, service, rig.runtime, pr_client=_FakePRClient(),
                     workspace_root=workspace_root,
                     git_runner=_fake_git(clean=True))

    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_SUCCEEDED
    assert final.pr_url == ""
    kinds = [e.kind for e in service.list_events(user, task.task_id)]
    assert EVENT_NO_CHANGES in kinds and EVENT_PR_CREATED not in kinds


async def test_worker_runtime_failure_marks_task_failed(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    task = service.create_task(user, title="t", requirement="r", source="web")
    rig.runtime.script_events([RuntimeEvent(kind="failed", payload={"error": "模型超时"})])
    workspace_root = rig.tmp_path / "ws"
    _setup_workspace(workspace_root)
    worker = _worker(rig, service, rig.runtime, pr_client=_FakePRClient(),
                     workspace_root=workspace_root)

    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == "failed"
    assert "模型超时" in final.error


async def test_cancelled_task_is_not_overwritten(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    task = service.create_task(user, title="t", requirement="r", source="web")
    # 执行中取消：runtime 事件流期间把任务置为 cancelled
    scripted = rig.runtime

    async def execute(request):
        service.cancel_task(user, task.task_id)
        for event in _completed("晚到的结果"):
            yield event

    scripted.execute = execute  # type: ignore[method-assign]
    workspace_root = rig.tmp_path / "ws"
    _setup_workspace(workspace_root)
    worker = _worker(rig, service, scripted, pr_client=_FakePRClient(),
                     workspace_root=workspace_root)

    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == TASK_CANCELLED
    assert final.pr_url == ""


async def test_queued_task_can_be_cancelled_before_execution(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    task = service.create_task(user, title="t", requirement="r", source="web")
    cancelled = service.cancel_task(user, task.task_id)
    assert cancelled.status == TASK_CANCELLED
    assert await _worker(rig, service, rig.runtime).tick() == 0


async def test_retry_requeues_failed_task(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    task = service.create_task(user, title="t", requirement="r", source="web")
    service.repo.update_fields(task.task_id, status="failed", error="x", finished_at="now")
    retried = service.retry_task(user, task.task_id)
    assert retried.status == TASK_QUEUED
    assert retried.error == ""
    with pytest.raises(InvalidInputError):
        service.repo.update_fields(task.task_id, status="succeeded")
        service.retry_task(user, task.task_id)


async def test_disabled_gate_stops_worker_claiming(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin)
    service.create_task(user, title="t", requirement="r", source="web")
    service.update_settings(admin, enabled=False)
    assert await _worker(rig, service, rig.runtime).tick() == 0


async def test_worker_requires_token_before_push(rig) -> None:
    service, admin, user = _service(rig)
    _enable(service, admin, token="")
    task = service.create_task(user, title="t", requirement="r", source="web")
    rig.runtime.script_events(_completed("done"))
    workspace_root = rig.tmp_path / "ws"
    _setup_workspace(workspace_root)
    worker = _worker(rig, service, rig.runtime, pr_client=_FakePRClient(),
                     workspace_root=workspace_root)
    await worker.tick()
    final = service.task(task.task_id)
    assert final.status == "failed"
    assert "token" in final.error
