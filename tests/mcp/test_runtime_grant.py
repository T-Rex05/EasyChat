"""P4c 运行打通：MCP 工具组逐 run 注入、跨 owner 不扩权、缓存键隔离、HTTP 闸。"""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI

from backend.modules.assistant.contracts import RunCommand
from backend.modules.mcp.api import McpService
from backend.modules.mcp.contracts import McpCheckResult
from backend.modules.mcp.routes import build_mcp_router
from backend.shared.errors import AppError
from backend.shared.identifiers import new_run_id, new_session_id
from tests.support.rig import make_rig

SECRET = "unit-test-secret"


class _Adapter:
    def __init__(self):
        self.registered: list = []

    def register(self, configs):
        self.registered.append([c.name for c in configs])

    def health(self):
        return {"everyone": {"registered": True, "tools": 1, "error": None}}


def _service(rig) -> McpService:
    return McpService(
        rig.db, access=rig.access, encryption_secret=SECRET,
        adapter=_Adapter(), probe=lambda config: McpCheckResult(ok=True, tools=("t",)),
    )


def _build_request(ready, principal, *, grantor):
    """直接走 dispatcher._build_request 真实代码路径。"""
    run = {
        "id": new_run_id(), "owner_id": principal.user_id, "source": "web",
        "session_id": new_session_id(), "channel_account_scope": "",
        "attachment_ids": "[]", "input_summary": "你好",
    }
    ready.assistant.dispatcher.mcp_grantor = grantor
    return ready.assistant.dispatcher._build_request(run)


@pytest.mark.asyncio
async def test_mcp_toolset_in_request_per_audience(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    ready.attach_assistant()
    admin = ready.seed_user(role="super_admin", username=f"adm_{uuid.uuid4().hex[:6]}")
    plain = ready.seed_user(grants=("chat.use",), username=f"pl_{uuid.uuid4().hex[:6]}")
    service = _service(ready)
    v1 = service.create(admin, name="cfgonly", url="https://a.test/x")
    v2 = service.create(admin, name="everyone", url="https://b.test/y", audience="all")
    service.set_enabled(admin, v1.id, True)
    service.set_enabled(admin, v2.id, True)

    req_admin = _build_request(ready, admin, grantor=service.granted_toolsets)
    assert "mcp-cfgonly" in req_admin.allowed_tools
    assert "mcp-everyone" in req_admin.allowed_tools

    req_plain = _build_request(ready, plain, grantor=service.granted_toolsets)
    assert "mcp-everyone" in req_plain.allowed_tools
    assert "mcp-cfgonly" not in req_plain.allowed_tools, (
        "config_admin audience 不得扩权到普通 owner"
    )

    # Agent 缓存键隔离：同 session 模型下 admin/plain 的 allowed_tools 不同
    from backend.runtime.hermes.adapter import HermesRuntimeAdapter  # noqa: F401 仅确认可导入

    # 禁用后即刻从请求消失（enabled 门控，无需重启）
    service.set_enabled(admin, v2.id, False)
    req_plain2 = _build_request(ready, plain, grantor=service.granted_toolsets)
    assert "mcp-everyone" not in req_plain2.allowed_tools


@pytest.mark.asyncio
async def test_grantor_failure_degrades_to_no_grant(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    ready.attach_assistant()
    plain = ready.seed_user(grants=("chat.use",), username=f"pl_{uuid.uuid4().hex[:6]}")

    def boom(principal):
        raise RuntimeError("mcp 服务不可用")

    request = _build_request(ready, plain, grantor=boom)
    assert not any(str(t).startswith("mcp-") for t in request.allowed_tools)


@pytest.mark.asyncio
async def test_mcp_http_routes_gating(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    admin = ready.seed_user(role="super_admin", username=f"adm_{uuid.uuid4().hex[:6]}")
    plain = ready.seed_user(grants=("chat.use",), username=f"pl_{uuid.uuid4().hex[:6]}")
    service = _service(ready)

    app = FastAPI()

    @app.exception_handler(AppError)
    async def _handle(_: object, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(build_mcp_router(service, ready.access.authenticate_token))
    admin_token = ready.access.create_token(admin.user_id, "adm", "super_admin")
    plain_token = ready.access.create_token(plain.user_id, "pl", "user")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://t",
    ) as client:
        anon = await client.get("/api/mcp/servers")
        assert anon.status_code == 401
        denied = await client.get(
            "/api/mcp/servers", headers={"Authorization": f"Bearer {plain_token}"}
        )
        assert denied.status_code == 403

        created = await client.post(
            "/api/mcp/servers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "knora", "url": "https://k.test/mcp", "credential": "sk-x-1"},
        )
        assert created.status_code == 200
        server = created.json()["server"]
        assert server["credential_set"] is True
        assert "sk-x-1" not in created.text
        assert server["enabled"] is False, "能力默认关闭"

        tested = await client.post(
            f"/api/mcp/servers/{server['id']}/test",
            headers={"Authorization": f"Bearer {admin_token}"}, json={},
        )
        assert tested.status_code == 200
        assert tested.json()["tools"] == ["t"]

        enabled = await client.post(
            f"/api/mcp/servers/{server['id']}/enable",
            headers={"Authorization": f"Bearer {admin_token}"}, json={"enabled": True},
        )
        assert enabled.json()["server"]["enabled"] is True
        assert service.adapter.registered[-1] == ["knora"]

        health = await client.get(
            "/api/mcp/health", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert health.status_code == 200
