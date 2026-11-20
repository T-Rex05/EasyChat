"""usage 模块 HTTP 路由：排行与明细（保留 trace.view / trace.manage 语义）。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Response

from backend.modules.usage.api import UsageService
from backend.shared.errors import UnauthenticatedError


def build_usage_router(
    usage: UsageService,
    authenticate: Any,
) -> APIRouter:
    """authenticate: Callable[[str], Principal] —— bootstrap 注入 access.authenticate_token。"""

    def _principal(authorization: str | None):
        if not authorization:
            raise UnauthenticatedError("请先登录")
        return authenticate(authorization.replace("Bearer ", "").strip())

    router = APIRouter()

    @router.get("/api/usage/ranking")
    async def ranking(
        days: int = Query(default=7, ge=1, le=365),
        limit: int = Query(default=20, ge=1, le=100),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        principal = _principal(authorization)
        return usage.ranking(principal, days=days, limit=limit)

    @router.get("/api/usage/calls")
    async def list_calls(
        owner_id: int | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, Any]]:
        principal = _principal(authorization)
        return usage.list_calls(principal, owner_id=owner_id, limit=limit, offset=offset)

    @router.get("/api/usage/users")
    async def usage_users(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        principal = _principal(authorization)
        return usage.user_options(principal, limit=limit, offset=offset)

    @router.get("/api/usage/calls/{call_id}")
    async def get_call(
        call_id: str,
        response: Response,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        principal = _principal(authorization)
        response.headers["Cache-Control"] = "no-store"
        return usage.get_call(principal, call_id)

    @router.get("/api/usage/me/call-groups")
    async def my_call_groups(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        return usage.my_call_groups(_principal(authorization), limit=limit, offset=offset)

    @router.get("/api/usage/me/group-calls")
    async def my_group_calls(
        session_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, Any]]:
        return usage.my_group_calls(_principal(authorization), session_id=session_id, limit=limit, offset=offset)

    @router.get("/api/usage/call-groups")
    async def global_call_groups(
        response: Response,
        owner_id: int | None = Query(default=None, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return usage.global_call_groups(_principal(authorization), owner_id=owner_id, limit=limit, offset=offset)

    @router.get("/api/usage/group-calls")
    async def global_group_calls(
        response: Response,
        owner_id: int = Query(ge=0),
        session_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, Any]]:
        response.headers["Cache-Control"] = "no-store"
        return usage.global_group_calls(
            _principal(authorization), owner_id=owner_id, session_id=session_id, limit=limit, offset=offset,
        )

    @router.get("/api/usage/me/daily")
    async def my_daily(
        days: int = Query(default=30, ge=1, le=365),
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, Any]]:
        principal = _principal(authorization)
        return usage.my_daily_usage(principal, days=days)

    return router
