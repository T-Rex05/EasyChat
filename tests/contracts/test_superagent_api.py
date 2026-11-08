"""superagent HTTP 契约：capabilities、配置、幂等受理、inputs、增量事件、权限。"""
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from backend.modules.superagent.api import SuperagentService
from backend.modules.superagent.routes import build_superagent_router
from backend.shared.errors import AppError
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig


@pytest.fixture
async def rig(tmp_path):
    r = make_rig(tmp_path, seed_access=True)
    yield r
    await r.aclose()


def _service(rig) -> tuple[SuperagentService, object, object]:
    service = SuperagentService(rig.db, access=rig.access)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    service.runner_ready = True
    admin = rig.seed_user(role="admin")
    user = rig.seed_user(role="user")
    return service, admin, user


def _client(rig, service) -> httpx.AsyncClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle(_: object, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(build_superagent_router(service, rig.access.authenticate_token))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                             base_url="http://test")


def _headers(rig, user) -> dict:
    token = rig.access.create_token(user.user_id, f"user{user.user_id}", user.role)
    return {"Authorization": f"Bearer {token}"}


async def test_capabilities_reports_gate_and_hides_repo_from_user(rig) -> None:
    service, admin, user = _service(rig)
    client = _client(rig, service)
    # 未配置时：enabled=False
    caps = (await client.get("/api/superagent/capabilities", headers=_headers(rig, user))).json()["capabilities"]
    assert caps["view"] is True and caps["create"] is True and caps["manage"] is False
    assert caps["enabled"] is False and caps["configured"] is False
    assert caps["reasons"], "未配置时必须给出原因"
    # 配置后：普通用户看得到状态但看不到 repo_url
    service.update_settings(admin, enabled=True, repo_url="https://github.com/foo/bar.git",
                            github_token="ghp_x")
    caps_user = (await client.get("/api/superagent/capabilities", headers=_headers(rig, user))).json()["capabilities"]
    assert caps_user["configured"] is True
    assert caps_user["credentials_ready"] is True
    assert caps_user["runner_ready"] is True
    assert caps_user["reasons"] == []
    assert caps_user["repo_url"] == ""  # 敏感值不外露
    caps_admin = (await client.get("/api/superagent/capabilities", headers=_headers(rig, admin))).json()["capabilities"]
    assert caps_admin["repo_url"] == "https://github.com/foo/bar.git"


async def test_settings_roundtrip_verify_profile_and_strict_url(rig) -> None:
    service, admin, _ = _service(rig)
    client = _client(rig, service)
    headers = _headers(rig, admin)
    # 非法 URL 被拒（严格 parser）
    bad = await client.put("/api/superagent/settings", headers=headers,
                           json={"repo_url": "git@github.com:foo/bar.git"})
    assert bad.status_code == 422
    # 合法 URL 规范化存储 + 验证策略
    response = await client.put(
        "/api/superagent/settings", headers=headers,
        json={"enabled": True, "repo_url": "https://github.com/foo/bar.git",
              "base_branch": "main", "github_token": "ghp_secret_value",
              "verify_profile": '[{"name":"pytest","command":"python -m pytest -q"}]',
              "allow_unverified_draft": False},
    )
    settings = response.json()["settings"]
    assert settings["repo_url"] == "https://github.com/foo/bar.git"
    assert settings["has_github_token"] is True
    assert settings["allow_unverified_draft"] is False
    assert settings["verify_profile"].startswith("[")
    assert "ghp_secret" not in settings["github_token_mask"]


async def test_task_create_idempotency_header_and_isolation(rig) -> None:
    service, admin, user = _service(rig)
    service.update_settings(admin, enabled=True, repo_url="https://github.com/foo/bar.git")
    client = _client(rig, service)
    other = rig.seed_user(role="user")
    headers = {**_headers(rig, user), "Idempotency-Key": "evt-42"}

    created = await client.post("/api/superagent/tasks", headers=headers,
                                json={"title": "修复登录", "requirement": "登录 500"})
    assert created.status_code == 200
    task = created.json()["task"]
    assert task["status"] == "queued"
    assert task["repo_url"] == "https://github.com/foo/bar.git"  # 快照回显
    # 幂等重放：同 header 返回同一任务
    replay = await client.post("/api/superagent/tasks", headers=headers,
                               json={"title": "修复登录", "requirement": "登录 500"})
    assert replay.json()["task"]["task_id"] == task["task_id"]
    # 隔离：其他用户 403
    forbidden = await client.get(f"/api/superagent/tasks/{task['task_id']}",
                                 headers=_headers(rig, other))
    assert forbidden.status_code == 403
    # admin 跨用户可见
    all_tasks = await client.get("/api/superagent/tasks", headers=_headers(rig, admin))
    assert len(all_tasks.json()["tasks"]) == 1


async def test_cursor_pagination_stable_order(rig) -> None:
    service, admin, user = _service(rig)
    service.update_settings(admin, enabled=True, repo_url="https://github.com/foo/bar.git")
    client = _client(rig, service)
    headers = _headers(rig, user)
    for i in range(3):
        await client.post("/api/superagent/tasks", headers=headers,
                          json={"title": f"t{i}", "requirement": "r", "context_extra": ""})
    page1 = (await client.get("/api/superagent/tasks", headers=headers,
                              params={"limit": 2})).json()
    assert len(page1["tasks"]) == 2
    assert page1["next_cursor"]
    page2 = (await client.get("/api/superagent/tasks", headers=headers,
                              params={"limit": 2, "cursor": page1["next_cursor"]})).json()
    ids1 = {t["task_id"] for t in page1["tasks"]}
    ids2 = {t["task_id"] for t in page2["tasks"]}
    assert not ids1 & ids2  # 无重复
    assert len(ids2) == 1


async def test_inputs_endpoint_and_incremental_events(rig) -> None:
    service, admin, user = _service(rig)
    service.update_settings(admin, enabled=True, repo_url="https://github.com/foo/bar.git")
    client = _client(rig, service)
    headers = _headers(rig, user)
    task = (await client.post("/api/superagent/tasks", headers=headers,
                              json={"title": "t", "requirement": "r"})).json()["task"]
    # 受理事件 + 幂等输入
    events1 = (await client.get(f"/api/superagent/tasks/{task['task_id']}/events",
                                headers=headers)).json()
    assert events1["events"][0]["kind"] == "created"
    after_id = events1["next_after_id"]
    added = await client.post(f"/api/superagent/tasks/{task['task_id']}/inputs",
                              headers={**headers, "Idempotency-Key": "in-1"},
                              json={"text": "补充：兼容 Windows"})
    assert added.status_code == 200
    dup = await client.post(f"/api/superagent/tasks/{task['task_id']}/inputs",
                            headers={**headers, "Idempotency-Key": "in-1"},
                            json={"text": "补充：兼容 Windows"})
    assert dup.json()["input"]["input_id"] == added.json()["input"]["input_id"]
    # 增量事件：只返回 after_id 之后的新事件（input 事件）
    events2 = (await client.get(f"/api/superagent/tasks/{task['task_id']}/events",
                                headers=headers, params={"after_id": after_id})).json()
    kinds = [e["kind"] for e in events2["events"]]
    assert "input" in kinds
    assert "created" not in kinds
    # attempts / reports 端点可访问
    attempts = await client.get(f"/api/superagent/tasks/{task['task_id']}/attempts", headers=headers)
    assert attempts.status_code == 200
    reports = await client.get(f"/api/superagent/tasks/{task['task_id']}/reports", headers=headers)
    assert reports.status_code == 200


async def test_cancel_and_retry_flow_with_new_statuses(rig) -> None:
    service, admin, user = _service(rig)
    service.update_settings(admin, enabled=True, repo_url="https://github.com/foo/bar.git")
    client = _client(rig, service)
    headers = _headers(rig, user)
    task = (await client.post("/api/superagent/tasks", headers=headers,
                              json={"title": "t", "requirement": "r"})).json()["task"]
    cancelled = await client.post(f"/api/superagent/tasks/{task['task_id']}/cancel", headers=headers)
    assert cancelled.json()["task"]["status"] == "cancelled"
    retried = await client.post(f"/api/superagent/tasks/{task['task_id']}/retry", headers=headers)
    assert retried.json()["task"]["status"] == "queued"
    # gate：未配置时受理 422
    fresh_rig_service, _, fresh_user = _service(rig)
    # （同一 service 已配置，跳过 gate 用例——由 tests/superagent 覆盖）


async def test_ops_metrics_manage_only(rig) -> None:
    service, admin, user = _service(rig)
    client = _client(rig, service)
    denied = await client.get("/api/superagent/ops/metrics", headers=_headers(rig, user))
    assert denied.status_code == 403
    metrics = (await client.get("/api/superagent/ops/metrics", headers=_headers(rig, admin))).json()["metrics"]
    assert "tasks_by_status" in metrics and "attempts" in metrics
    assert metrics["runner_ready"] is True


async def test_unauthenticated_rejected(rig) -> None:
    service, _, _ = _service(rig)
    client = _client(rig, service)
    response = await client.get("/api/superagent/tasks")
    assert response.status_code == 401
