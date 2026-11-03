"""access 模块 HTTP 路由：薄适配层，不执行 SQL、不持有全局状态。

响应结构沿用旧 /api/auth 与 /api/admin 契约（A09）；router 由 bootstrap
显式构造并注入 AccessService。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from backend.modules.access.api import AccessService
from backend.shared.errors import UnauthenticatedError


class RegisterRequest(BaseModel):
    username: str = Field(description="用户名（至少 2 字符）")
    password: str = Field(description="密码（至少 6 字符）")
    email: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class SetRoleRequest(BaseModel):
    role: str


class SetStatusRequest(BaseModel):
    status: int


class SetPermRequest(BaseModel):
    permission: str
    granted: bool


class CreateRoleRequest(BaseModel):
    name: str
    display_name: str
    description: str = ""
    permissions: list[str] = []
    hermes_tools: list[str] = []


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None
    hermes_tools: list[str] | None = None


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthenticatedError("缺少 Token，请先登录")
    return authorization.replace("Bearer ", "").strip()


def build_access_router(access: AccessService) -> APIRouter:
    router = APIRouter()

    # ---- /api/auth ----

    @router.post("/api/auth/register")
    async def register(req: RegisterRequest) -> dict[str, Any]:
        result = access.register(req.username, req.password, req.email)
        principal = access.snapshot_principal(result["user_id"])
        return {
            "ok": True,
            **result,
            "permissions": sorted(access.effective_permissions(principal.user_id)),
        }

    @router.post("/api/auth/login")
    async def login(req: LoginRequest, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        result = access.login(req.username, req.password)
        principal = access.snapshot_principal(result["user_id"])
        return {
            "ok": True,
            **result,
            "permissions": sorted(access.effective_permissions(principal.user_id)),
            "hermes_tools": list(access.hermes_toolsets(principal.user_id)),
        }

    @router.get("/api/auth/me")
    async def get_me(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        principal = access.authenticate_token(_bearer_token(authorization))
        user = access.get_user_detail(principal, principal.user_id)
        return {
            "id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "avatar": user.avatar,
            "status": user.status,
            "created_at": user.created_at,
            "permissions": sorted(access.effective_permissions(user.user_id)),
            "hermes_tools": list(access.hermes_toolsets(user.user_id)),
        }

    @router.post("/api/auth/refresh")
    async def refresh(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        token = _bearer_token(authorization)
        new_token = access.check_token_renewal(token) or access.renew_token(token)
        if not new_token:
            raise UnauthenticatedError("Token 已失效，请重新登录")
        principal = access.authenticate_token(new_token)
        token_user = access.verify_token(new_token) or {}
        return {
            "ok": True,
            "token": new_token,
            "user_id": principal.user_id,
            "username": token_user.get("username", ""),
            "role": principal.role,
            "permissions": sorted(access.effective_permissions(principal.user_id)),
            "hermes_tools": list(access.hermes_toolsets(principal.user_id)),
        }

    @router.get("/api/auth/users")
    async def list_users_auth(authorization: Annotated[str | None, Header()] = None) -> list[dict[str, Any]]:
        principal = access.authenticate_token(_bearer_token(authorization))
        return access.list_users(principal)

    # ---- /api/admin ----

    @router.get("/api/admin/users")
    async def admin_list_users(authorization: Annotated[str | None, Header()] = None) -> list[dict[str, Any]]:
        principal = access.authenticate_token(_bearer_token(authorization))
        return access.list_users(principal)

    @router.put("/api/admin/users/{user_id}/role")
    async def admin_set_role(user_id: int, req: SetRoleRequest, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        principal = access.authenticate_token(_bearer_token(authorization))
        access.set_user_role(principal, user_id, req.role)
        return {"ok": True}

    @router.get("/api/admin/users/{user_id}/perms")
    async def admin_get_perms(user_id: int, authorization: Annotated[str | None, Header()] = None) -> list[dict[str, Any]]:
        principal = access.authenticate_token(_bearer_token(authorization))
        return [{"permission": o.permission, "granted": o.granted} for o in access.get_user_perm_overrides(principal, user_id)]

    @router.put("/api/admin/users/{user_id}/perms")
    async def admin_set_perms(user_id: int, req: SetPermRequest, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        principal = access.authenticate_token(_bearer_token(authorization))
        access.set_user_permission(principal, user_id, req.permission, req.granted)
        return {"ok": True}

    @router.put("/api/admin/users/{user_id}/status")
    async def admin_set_status(user_id: int, req: SetStatusRequest, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        principal = access.authenticate_token(_bearer_token(authorization))
        access.set_user_status(principal, user_id, req.status)
        return {"ok": True}

    @router.get("/api/admin/permissions")
    async def admin_permissions(authorization: Annotated[str | None, Header()] = None) -> list[dict[str, Any]]:
        principal = access.authenticate_token(_bearer_token(authorization))
        return access.list_permissions(principal)

    @router.get("/api/admin/toolsets")
    async def admin_toolsets(authorization: Annotated[str | None, Header()] = None) -> list[dict[str, Any]]:
        principal = access.authenticate_token(_bearer_token(authorization))
        return access.list_toolsets(principal)

    @router.get("/api/admin/roles")
    async def admin_roles(authorization: Annotated[str | None, Header()] = None) -> list[dict[str, Any]]:
        principal = access.authenticate_token(_bearer_token(authorization))
        return [
            {
                "id": r.role_id,
                "name": r.name,
                "display_name": r.display_name,
                "description": r.description,
                "is_system": r.is_system,
                "permissions": list(r.permissions),
                "hermes_tools": list(r.toolsets),
            }
            for r in access.list_roles(principal)
        ]

    @router.post("/api/admin/roles", status_code=201)
    async def admin_create_role(req: CreateRoleRequest, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        principal = access.authenticate_token(_bearer_token(authorization))
        role_id = access.create_role(
            principal,
            name=req.name,
            display_name=req.display_name,
            description=req.description,
            permissions=req.permissions,
            toolsets=req.hermes_tools,
        )
        return {"ok": True, "id": role_id, "name": req.name, "display_name": req.display_name}

    @router.put("/api/admin/roles/{role_id}")
    async def admin_update_role(role_id: int, req: UpdateRoleRequest, authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
        principal = access.authenticate_token(_bearer_token(authorization))
        access.update_role(
            principal,
            role_id,
            name=req.name,
            display_name=req.display_name,
            description=req.description,
            permissions=req.permissions,
            toolsets=req.hermes_tools,
        )
        return {"ok": True}

    @router.delete("/api/admin/roles/{role_id}")
    async def admin_delete_role(role_id: int, authorization: Annotated[str | None, Header()] = None) -> dict[str, bool]:
        principal = access.authenticate_token(_bearer_token(authorization))
        access.delete_role(principal, role_id)
        return {"ok": True}

    return router
