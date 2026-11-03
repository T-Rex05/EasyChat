"""models 兼容路由（Task 15）：保留旧 Config 页使用的 HTTP 契约。

只迁移聊天模型配置与 fallback 链；embedding/场景路由属于已删能力，明确 503。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel

from backend.modules.models.api import ModelsService
from backend.shared.errors import CapabilityUnavailableError, UnauthenticatedError


class ModelConfigBody(BaseModel):
    config_name: str = ""
    config_type: str = "openai"
    api_url: str = ""
    api_key: str = ""
    model_name: str = ""
    provider: str = ""
    category: str = "chat"
    is_multimodal: bool | int = False
    reasoning_effort: str = ""


class MultimodalBody(BaseModel):
    is_multimodal: bool | int


class ReasoningBody(BaseModel):
    reasoning_effort: str


class FallbackBody(BaseModel):
    config_ids: list[int]


def _legacy(profile) -> dict[str, Any]:
    return {
        "id": profile.config_id,
        "config_name": profile.name,
        "config_type": profile.provider,
        "api_url": profile.base_url,
        "api_key": profile.api_key_masked,
        "model_name": profile.model,
        "provider": profile.provider,
        "category": "chat",
        "is_multimodal": 1 if profile.is_multimodal else 0,
        "is_current": 1 if profile.is_active else 0,
        "enabled": 1,
        "reasoning_effort": profile.reasoning_effort,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def build_models_router(service: ModelsService, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(tags=["models"])

    @router.get("/api/model-configs")
    async def list_configs(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {
            "configs": [_legacy(p) for p in service.list_configs(principal)],
            "env_configured": False,
            "categories": {"chat": "聊天模型"},
        }

    @router.post("/api/model-configs")
    async def create_config(body: ModelConfigBody,
                            authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        if body.category != "chat":
            raise CapabilityUnavailableError("只保留聊天模型；embedding 已移除")
        config_id = service.create_config(
            principal, name=body.config_name or body.model_name,
            provider=body.provider or body.config_type or "openai",
            model=body.model_name, api_key=body.api_key, base_url=body.api_url,
            is_multimodal=bool(body.is_multimodal),
            reasoning_effort=body.reasoning_effort,
        )
        return {"ok": True, "id": config_id}

    @router.put("/api/model-configs/{config_id}")
    async def update_config(config_id: int, body: ModelConfigBody,
                            authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        service.update_config(
            principal, config_id, name=body.config_name or None,
            model=body.model_name or None, base_url=body.api_url or None,
            api_key=body.api_key or None, is_multimodal=bool(body.is_multimodal),
            reasoning_effort=body.reasoning_effort or None,
        )
        return {"ok": True}

    @router.put("/api/model-configs/{config_id}/active")
    async def set_active(config_id: int,
                         authorization: Annotated[str | None, Header()] = None):
        service.set_active(_principal(authorization), config_id)
        return {"ok": True}

    @router.delete("/api/model-configs/{config_id}")
    async def delete_config(config_id: int,
                            authorization: Annotated[str | None, Header()] = None):
        service.delete_config(_principal(authorization), config_id)
        return {"ok": True}

    @router.put("/api/model-configs/{config_id}/multimodal")
    async def set_multimodal(config_id: int, body: MultimodalBody,
                             authorization: Annotated[str | None, Header()] = None):
        service.update_config(
            _principal(authorization), config_id, is_multimodal=bool(body.is_multimodal),
        )
        return {"ok": True}

    @router.put("/api/model-configs/reasoning-effort")
    async def set_reasoning(body: ReasoningBody,
                            authorization: Annotated[str | None, Header()] = None):
        raise CapabilityUnavailableError("按配置修改 reasoning_effort 请走 PUT /api/model-configs/{id}")

    @router.post("/api/model-configs/{config_id}/test")
    async def test_config(config_id: int,
                          authorization: Annotated[str | None, Header()] = None):
        _principal(authorization)
        raise CapabilityUnavailableError("真实模型连通性测试需要外部网络，离线环境不启用")

    @router.get("/api/model-routes/fallback-chain")
    async def get_fallback(authorization: Annotated[str | None, Header()] = None):
        return {"chain": service.get_fallback_chain(_principal(authorization))}

    @router.put("/api/model-routes/fallback-chain")
    async def save_fallback(body: FallbackBody,
                            authorization: Annotated[str | None, Header()] = None):
        service.save_fallback_chain(_principal(authorization), body.config_ids)
        return {"ok": True}

    @router.get("/api/model-routes/scenes")
    async def scenes(authorization: Annotated[str | None, Header()] = None):
        raise CapabilityUnavailableError("场景路由/embedding 能力已移除")

    return router
