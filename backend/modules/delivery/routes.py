"""投递状态 HTTP 路由（只读；发送由 worker 完成）。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header

from backend.modules.delivery.api import DeliveryService
from backend.shared.errors import UnauthenticatedError


def build_delivery_router(service: DeliveryService, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    def _view(view) -> dict[str, Any]:
        return {
            "delivery_id": view.delivery_id, "run_id": view.run_id,
            "source": view.source, "status": view.status, "attempts": view.attempts,
            "error": view.error, "created_at": view.created_at, "sent_at": view.sent_at,
            "target": {"kind": view.target.kind, "ref": view.target.ref},
        }

    router = APIRouter(prefix="/api/deliveries", tags=["delivery"])

    @router.get("")
    async def list_deliveries(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"deliveries": [_view(v) for v in service.list_for_owner(principal.user_id)]}

    @router.get("/{delivery_id}")
    async def get_delivery(delivery_id: str,
                           authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"delivery": _view(service.status(principal.user_id, delivery_id))}

    return router
