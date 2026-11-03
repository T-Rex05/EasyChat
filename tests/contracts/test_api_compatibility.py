"""API 兼容测试（Task 15）：新工厂显式路由、旧前缀不再暴露、未就绪明确 503。"""
from __future__ import annotations

import httpx
import pytest

from backend.app import create_app
from backend.bootstrap import AppSettings


def _settings(tmp_path):
    return AppSettings(
        data_db_path=tmp_path / "app.db",
        state_db_path=tmp_path / "state.db",
        artifacts_dir=tmp_path / "artifacts",
    )


@pytest.fixture
async def client(tmp_path):
    app = create_app(_settings(tmp_path))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, app


async def test_explicit_routes_and_health(client):
    c, app = client
    assert (await c.get("/healthz")).status_code == 200
    assert (await c.get("/readyz")).status_code == 200
    paths = set(app.openapi()["paths"])
    assert {"/api/auth/login", "/api/memory", "/api/skills", "/api/channels/accounts",
            "/api/usage/ranking", "/chat/stream", "/api/schedules",
            "/api/email/config", "/api/deliveries",
            "/api/model-configs", "/api/model-routes/fallback-chain",
            "/api/email-configs", "/api/personal-emails"}.issubset(paths)


async def test_removed_module_prefixes_not_mounted(client):
    _, app = client
    paths = set(app.openapi()["paths"])
    for removed in ("/api/kb", "/api/graph", "/api/paper", "/api/community", "/api/data-layers"):
        assert not any(path.startswith(removed) for path in paths), removed


async def test_register_login_and_memory_ownership(client):
    c, _ = client
    assert (await c.get("/api/auth/me")).status_code == 401
    registered = await c.post("/api/auth/register", json={
        "username": "compat_user", "password": "password6",
    })
    assert registered.status_code == 200
    token = registered.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await c.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["username"] == "compat_user"

    assert (await c.get("/api/memory", headers=headers)).status_code == 200
    assert (await c.get("/api/skills", headers=headers)).status_code == 200
    assert (await c.get("/api/usage/ranking", headers=headers)).status_code == 200
    assert (await c.get("/api/deliveries", headers=headers)).status_code == 200
    # 未配置部署密钥/渠道时，邮件模块明确 503；配置后普通用户 403
    assert (await c.get("/api/email/config", headers=headers)).status_code == 503
    assert (await c.get("/api/schedules", headers=headers)).status_code == 200
    no_target = await c.post("/api/schedules", headers=headers, json={
        "text": "喝水", "every_seconds": 60,
    })
    assert no_target.status_code == 503
    created = await c.post("/api/schedules", headers=headers, json={
        "title": "日报", "text": "读一遍日报", "daily_at": "09:00",
        "target_kind": "email", "target_ref": "nobody@example.com",
    })
    assert created.status_code == 200
    schedule_id = created.json()["schedule"]["schedule_id"]
    assert (await c.delete(f"/api/schedules/{schedule_id}", headers=headers)).status_code == 200
    remaining = await c.get("/api/schedules", headers=headers)
    assert all(s["schedule_id"] != schedule_id for s in remaining.json()["schedules"])


async def test_assistant_route_reports_unavailable_without_runtime(client):
    c, _ = client
    registered = await c.post("/api/auth/register", json={
        "username": "no_runtime", "password": "password6",
    })
    token = registered.json()["token"]
    response = await c.get("/chat/stream", params={
        "message": "hi", "thread_id": "1_1", "token": token,
    })
    assert response.status_code == 503
    assert response.json()["error"] == "capability_unavailable"


async def test_email_compat_paths_use_new_service(tmp_path):
    app = create_app(AppSettings(
        data_db_path=tmp_path / "app.db",
        state_db_path=tmp_path / "state.db",
        artifacts_dir=tmp_path / "artifacts",
        encryption_secret="e" * 64,
    ))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            reg = await c.post("/api/auth/register", json={
                "username": "mail_admin", "password": "password6",
            })
            token = reg.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            me = await c.get("/api/auth/me", headers=headers)
            registry = app.state.registry
            registry.access.repo.set_user_role(me.json()["id"], "super_admin")
            registry.access.invalidate_all()

            assert (await c.get("/api/email-configs", headers=headers)).status_code == 200
            saved = await c.post("/api/email-configs", headers=headers, json={
                "config_name": "测试", "host": "smtp.example.com", "port": "587",
                "sender_email": "bot@example.com", "sender_name": "EasyChat",
                "password": "secret",
            })
            assert saved.status_code == 200
            listed = await c.get("/api/email-configs", headers=headers)
            assert listed.json()["configs"][0]["host"] == "smtp.example.com"
            assert listed.json()["configs"][0]["password"] != "secret"
            added = await c.post("/api/personal-emails", headers=headers,
                                 json={"email": "me@example.com"})
            assert added.status_code == 200
            assert (await c.get("/api/personal-emails", headers=headers)).status_code == 200
