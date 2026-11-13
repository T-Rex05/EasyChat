"""MCP 配置 API 路由（P4）。全部要求 system.config（写读同闸，能力默认隐藏）。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header

from backend.modules.mcp.api import McpService
from backend.shared.errors import UnauthenticatedError


def _payload(body: Any) -> dict[str, Any]:
    if hasattr(body, "model_dump"):
        return dict(body.model_dump())
    return dict(body or {})


def build_mcp_router(service: McpService, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/mcp", tags=["mcp"])

    @router.get("/servers")
    async def list_servers(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        servers = service.list(principal)
        return {"servers": [
            {
                "id": s.id, "name": s.name, "url": s.url,
                "credential_set": s.credential_set,
                "allowed_tools": list(s.allowed_tools),
                "excluded_tools": list(s.excluded_tools),
                "connect_timeout_s": s.connect_timeout_s,
                "call_timeout_s": s.call_timeout_s,
                "audience": s.audience, "enabled": s.enabled,
                "last_check_state": s.last_check_state,
                "last_check_error": s.last_check_error,
                "last_check_tools": list(s.last_check_tools),
                "last_checked_at": s.last_checked_at,
            } for s in servers
        ]}

    @router.post("/servers")
    async def create_server(body: dict, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        data = _payload(body)
        view = service.create(
            principal,
            name=str(data.get("name") or ""),
            url=str(data.get("url") or ""),
            credential=str(data.get("credential") or ""),
            allowed_tools=data.get("allowed_tools") or [],
            excluded_tools=data.get("excluded_tools") or [],
            connect_timeout_s=data.get("connect_timeout_s", 60),
            call_timeout_s=data.get("call_timeout_s", 300),
            audience=str(data.get("audience") or "config_admin"),
            enabled=bool(data.get("enabled")),
        )
        return {"server": _server_dict(view)}

    @router.put("/servers/{server_id}")
    async def update_server(server_id: str, body: dict,
                            authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        allowed = {"name", "url", "credential", "clear_credential", "allowed_tools",
                   "excluded_tools", "connect_timeout_s", "call_timeout_s", "audience"}
        fields = {k: v for k, v in _payload(body).items() if k in allowed}
        view = service.update(principal, server_id, **fields)
        return {"server": _server_dict(view)}

    @router.delete("/servers/{server_id}")
    async def delete_server(server_id: str,
                            authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        service.delete(principal, server_id)
        return {"ok": True}

    @router.post("/servers/{server_id}/enable")
    async def enable_server(server_id: str, body: dict,
                            authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        enabled = bool(_payload(body).get("enabled"))
        view = service.set_enabled(principal, server_id, enabled)
        return {"server": _server_dict(view)}

    @router.post("/servers/{server_id}/test")
    async def test_server(server_id: str, body: dict | None = None,
                          authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        credential = None
        data = _payload(body)
        if isinstance(data.get("credential"), str):
            credential = data["credential"]
        return service.test(principal, server_id, credential=credential)

    @router.get("/health")
    async def health(authorization: Annotated[str | None, Header()] = None):
        _principal(authorization)
        if service.adapter is None:
            return {"servers": {}}
        return {"servers": service.adapter.health()}

    return router


def _server_dict(view) -> dict[str, Any]:
    return {
        "id": view.id, "name": view.name, "url": view.url,
        "credential_set": view.credential_set,
        "allowed_tools": list(view.allowed_tools),
        "excluded_tools": list(view.excluded_tools),
        "connect_timeout_s": view.connect_timeout_s,
        "call_timeout_s": view.call_timeout_s,
        "audience": view.audience, "enabled": view.enabled,
        "last_check_state": view.last_check_state,
        "last_check_error": view.last_check_error,
        "last_check_tools": list(view.last_check_tools),
        "last_checked_at": view.last_checked_at,
    }
