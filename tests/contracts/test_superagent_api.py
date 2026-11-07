"""superagent HTTP 契约：配置读写、任务受理/列表/取消/重试、权限与隔离（httpx ASGI）。"""
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


async def test_settings_roundtrip_and_token_mask(rig) -> None:
    service, admin, _ = _service(rig)
    client = _client(rig, service)
    headers = _headers(rig, admin)

    response = await client.put(
        "/api/superagent/settings", headers=headers,
        json={"enabled": True, "repo_url": "https://github.com/foo/bar.git",
              "base_branch": "main", "github_token": "ghp_secret_value"},
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["enabled"] is True
    assert settings["has_github_token"] is True
    assert "ghp_secret" not in settings["github_token_mask"]

    got = await client.get("/api/superagent/settings", headers=headers)
    assert got.status_code == 200
    assert got.json()["settings"]["repo_url"] == "https://github.com/foo/bar.git"


async def test_settings_requires_manage_permission(rig) -> None:
    service, admin, user = _service(rig)
    client = _client(rig, service)
    response = await client.get("/api/superagent/settings", headers=_headers(rig, user))
    assert response.status_code == 403


async def test_task_create_list_and_isolation(rig) -> None:
    service, admin, user = _service(rig)
    service.update_settings(
        admin, enabled=True, repo_url="https://github.com/foo/bar.git",
    )
    client = _client(rig, service)
    other = rig.seed_user(role="user")

    created = await client.post(
        "/api/superagent/tasks", headers=_headers(rig, user),
        json={"title": "修复登录", "requirement": "登录 500"},
    )
    assert created.status_code == 200
    task = created.json()["task"]
    assert task["status"] == "queued"

    mine = await client.get("/api/superagent/tasks", headers=_headers(rig, user))
    assert [t["task_id"] for t in mine.json()["tasks"]] == [task["task_id"]]

    # 其他用户看不到，也取不到详情
    forbidden = await client.get(
        f"/api/superagent/tasks/{task['task_id']}", headers=_headers(rig, other),
    )
    assert forbidden.status_code == 403

    # admin 跨用户可见
    all_tasks = await client.get("/api/superagent/tasks", headers=_headers(rig, admin))
    assert len(all_tasks.json()["tasks"]) == 1


async def test_task_gate_rejects_when_disabled(rig) -> None:
    service, admin, user = _service(rig)
    client = _client(rig, service)
    response = await client.post(
        "/api/superagent/tasks", headers=_headers(rig, user),
        json={"title": "t", "requirement": "r"},
    )
    assert response.status_code == 422


async def test_cancel_and_retry_flow(rig) -> None:
    service, admin, user = _service(rig)
    service.update_settings(admin, enabled=True, repo_url="https://github.com/foo/bar.git")
    client = _client(rig, service)
    headers = _headers(rig, user)

    task = (await client.post(
        "/api/superagent/tasks", headers=headers,
        json={"title": "t", "requirement": "r"},
    )).json()["task"]

    cancelled = await client.post(f"/api/superagent/tasks/{task['task_id']}/cancel", headers=headers)
    assert cancelled.json()["task"]["status"] == "cancelled"

    retried = await client.post(f"/api/superagent/tasks/{task['task_id']}/retry", headers=headers)
    assert retried.json()["task"]["status"] == "queued"

    events = await client.get(f"/api/superagent/tasks/{task['task_id']}/events", headers=headers)
    kinds = [e["kind"] for e in events.json()["events"]]
    assert "created" in kinds and "cancelled" in kinds


async def test_unauthenticated_rejected(rig) -> None:
    service, _, _ = _service(rig)
    client = _client(rig, service)
    response = await client.get("/api/superagent/tasks")
    assert response.status_code == 401
