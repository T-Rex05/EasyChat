"""渠道 HTTP 路由：账号/扫码/绑定/监听状态。

薄适配层：只做认证、参数校验与值对象序列化；权限、去重、会话归属都在
ChannelService/Assistant，不在这里写 SQL 或直接调用 iLink。
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from backend.modules.channels.api import ChannelService
from backend.shared.errors import UnauthenticatedError


class AccountCreateBody(BaseModel):
    platform: str = "wechat"
    account_id: str = Field(min_length=1)
    token: str = Field(min_length=1)
    base_url: str = ""
    bot_user_id: str = ""
    display_name: str = ""


class StatusBody(BaseModel):
    status: str


class BindingCreateBody(BaseModel):
    platform: str = "wechat"
    account_id: str = ""
    account_pk: str = ""
    external_user_id: str = Field(min_length=1)
    user_id: int | None = None


def build_channels_router(service: ChannelService, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/channels", tags=["channels"])

    @router.get("/accounts")
    async def list_accounts(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"accounts": [asdict(a) for a in service.list_accounts(principal)]}

    @router.post("/accounts")
    async def create_account(body: AccountCreateBody,
                             authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        view = service.register_account(
            principal,
            platform=body.platform,
            account_id=body.account_id,
            token=body.token,
            base_url=body.base_url,
            bot_user_id=body.bot_user_id,
            display_name=body.display_name,
        )
        return {"account": asdict(view)}

    @router.patch("/accounts/{account_pk}")
    async def set_account_status(account_pk: str, body: StatusBody,
                                 authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"account": asdict(await service.set_account_status(principal, account_pk, body.status))}

    @router.post("/accounts/{account_pk}/start")
    async def start_account(account_pk: str,
                            authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"listener": asdict(await service.start_account(principal, account_pk))}

    @router.post("/accounts/{account_pk}/stop")
    async def stop_account(account_pk: str,
                           authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"listener": asdict(await service.stop_account(principal, account_pk))}

    @router.get("/listeners")
    async def list_listeners(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"listeners": [asdict(s) for s in service.list_listener_states(principal)]}

    @router.post("/wechat/qr/start")
    async def start_qr(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"qr": asdict(await service.start_qr_login(principal))}

    @router.get("/wechat/qr/{session_id}")
    async def qr_status(session_id: str,
                        authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"qr": asdict(await service.poll_qr_login(principal, session_id))}

    @router.post("/wechat/qr/{session_id}/bind")
    async def bind_after_qr(session_id: str,
                            authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return await service.bind_after_qr(principal, session_id)

    @router.get("/bindings")
    async def list_bindings(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"bindings": service.list_bindings(principal)}

    @router.post("/bindings")
    async def create_binding(body: BindingCreateBody,
                             authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        binding = service.bind_user(
            principal,
            platform=body.platform,
            account_id=body.account_id,
            external_user_id=body.external_user_id,
            user_id=body.user_id,
            account_pk=body.account_pk,
        )
        return {"binding": {
            "id": binding.id, "platform": binding.platform, "account_id": binding.account_id,
            "external_user_id": binding.external_user_id, "user_id": binding.user_id,
            "status": binding.status,
        }}

    @router.patch("/bindings/{binding_id}")
    async def set_binding_status(binding_id: str, body: StatusBody,
                                 authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        binding = service.set_binding_status(principal, binding_id, body.status)
        return {"binding": {
            "id": binding.id, "status": binding.status, "user_id": binding.user_id,
        }}

    @router.delete("/bindings/{binding_id}")
    async def delete_binding(binding_id: str,
                             authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        binding = service.unbind(principal, binding_id)
        return {"ok": True, "binding_id": binding.id, "status": binding.status}

    return router
