"""usage 模块 HTTP 路由：排行与明细（保留 trace.view / trace.manage 语义）。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query

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

    @router.get("/api/usage/calls/{call_id}")
    async def get_call(
        call_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        principal = _principal(authorization)
        return usage.get_call(principal, call_id)

    @router.get("/api/usage/me/daily")
    async def my_daily(
        days: int = Query(default=30, ge=1, le=365),
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, Any]]:
        principal = _principal(authorization)
        return usage.my_daily_usage(principal, days=days)

    return router
