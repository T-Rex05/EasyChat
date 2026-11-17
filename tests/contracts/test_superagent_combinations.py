"""WP-D：superagent view/create/manage 八组合——capabilities.read 以真实 view 计算，
菜单语义（read）与任务列表入口、创建/配置动作一致；不自动扩大授权。"""
from __future__ import annotations

import itertools

import httpx
import pytest
from fastapi import FastAPI

from backend.modules.superagent.api import SuperagentService
from backend.modules.superagent.routes import build_superagent_router
from backend.shared.errors import AppError
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig

ALL_KEYS = ("superagent.view", "superagent.create", "superagent.manage")


def _client(rig, service) -> httpx.AsyncClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle(_: object, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(build_superagent_router(service, rig.access.authenticate_token))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                             base_url="http://test")


async def _run(rig, mask) -> None:
    from tests.support.rig import make_rig as _make_rig

    ready = _make_rig(rig.tmp_path, seed_access=True)
    rig = ready  # 全局 rig 未 seed access；本地重建
    service = SuperagentService(rig.db, access=rig.access)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    service.runner_ready = True
    import uuid

    user = rig.seed_user(username=f"combo_{uuid.uuid4().hex[:8]}")
    for key, on in zip(ALL_KEYS, mask):
        # 显式授予/撤销三键（manage 不在 user 模板，必须显式授）
        rig.access.repo.set_user_permission(user.user_id, key, bool(on))
    rig.access.invalidate_all()
    principal = rig.access.snapshot_principal(user.user_id)

    caps = rig.access.capabilities(principal)
    module = caps["modules"]["superagent"]
    has_view, has_create, has_manage = (bool(m) for m in mask)
    # 菜单语义 read 必须等于真实查看权限（此前 create/manage 被折算成 read）
    assert module["read"] == has_view, f"mask={mask} read={module['read']}"
    assert module["manage"] == has_manage

    async with _client(rig, service) as client:
        token = rig.access.create_token(user.user_id, "combo", "user")
        headers = {"Authorization": f"Bearer {token}"}
        listed = await client.get("/api/superagent/tasks", headers=headers)
        if has_view:
            assert listed.status_code == 200
        else:
            assert listed.status_code == 403, f"mask={mask} 无 view 不得查看任务列表"
    await ready.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("mask", list(itertools.product([0, 1], repeat=3)),
                         ids=["none", "manage", "create", "create+manage",
                              "view", "view+manage", "view+create", "all"])
async def test_eight_combinations_match_real_gates(rig, mask) -> None:
    await _run(rig, mask)
