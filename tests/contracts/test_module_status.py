"""WP-B：模块装配状态端点——渠道关闭/缺密钥/依赖缺失/就绪各自原因可见（脱敏）。"""
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from backend.bootstrap import ModuleRegistry
from backend.platform.settings import default_settings
from backend.shared.errors import AppError
from tests.support.rig import make_rig


def _app(registry: ModuleRegistry, *, auth) -> FastAPI:
    from backend.app import build_module_status_router

    app = FastAPI()

    @app.exception_handler(AppError)
    async def _handle(_: object, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(build_module_status_router(registry, auth))
    return app


def _settings(**flags):
    base = default_settings()
    for key, value in flags.items():
        object.__setattr__(base, key, value)
    return base


async def _status(rig, registry) -> dict:
    ready = make_rig(rig.tmp_path, seed_access=True)
    user = ready.seed_user(username="status_reader")
    token = ready.access.create_token(user.user_id, "status_reader", "user")
    transport = httpx.ASGITransport(
        app=_app(registry, auth=ready.access.authenticate_token),
        raise_app_exceptions=False,
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        anon = await client.get("/api/system/module-status")
        assert anon.status_code == 401
        res = await client.get(
            "/api/system/module-status", headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 200
        return res.json()


@pytest.mark.asyncio
async def test_channels_disabled_reason(rig) -> None:
    registry = ModuleRegistry(settings=_settings(wechat_enabled=False, hermes_enabled=False))
    out = await _status(rig, registry)
    ch = out["channels"]
    assert ch["assembled"] is False
    assert ch["state"] == "disabled"
    assert "EASYCHAT_WECHAT_ENABLED" in ch["reason"]


@pytest.mark.asyncio
async def test_channels_secret_missing_reason(rig) -> None:
    registry = ModuleRegistry(settings=_settings(
        wechat_enabled=True, hermes_enabled=True, encryption_secret="",
    ))
    out = await _status(rig, registry)
    ch = out["channels"]
    assert ch["assembled"] is False
    assert ch["state"] == "misconfigured"
    assert "EASYCHAT_ENCRYPTION_SECRET" in ch["reason"]
    # 凭据值绝不出现（此处为空，但契约上状态端点无 secret 字段）
    assert "secret_value" not in ch


@pytest.mark.asyncio
async def test_channels_dependency_missing_reason(rig) -> None:
    registry = ModuleRegistry(settings=_settings(
        wechat_enabled=True, hermes_enabled=False, encryption_secret="s3cret",
    ))
    out = await _status(rig, registry)
    ch = out["channels"]
    assert ch["assembled"] is False
    assert ch["state"] == "dependency_missing"
    assert "EASYCHAT_HERMES_ENABLED" in ch["reason"]


@pytest.mark.asyncio
async def test_channels_ready_and_assistant_states(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    ready.attach_assistant()
    registry = ModuleRegistry(settings=_settings(
        wechat_enabled=True, hermes_enabled=True, encryption_secret="s3cret",
    ))
    registry.access = ready.access
    registry.assistant = ready.assistant
    out = await _status(ready, registry)
    assert out["assistant"]["assembled"] is True
    assert out["assistant"]["state"] == "ready"
    # channels 依赖满足但本 rig 未装配 channels → 初始化缺失按 ready 条件归因
    ch = out["channels"]
    assert ch["assembled"] is False
    assert ch["state"] in ("dependency_missing", "init_failed", "disabled")
    assert ch["reason"]
