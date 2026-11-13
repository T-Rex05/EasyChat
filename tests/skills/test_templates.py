"""P3 技能模板目录与导入回归：固定来源版本、元数据完整、导入经真实服务、
激活后运行请求使用模板快照、owner 隔离与"已存在相同内容"幂等。"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.modules.skills.api import SkillService
from backend.modules.skills.templates import (
    TEMPLATE_KEYS,
    load_template_content,
    templates_catalog,
)
from backend.shared.context import Principal
from tests.support.rig import make_rig


def _user(rig, username: str) -> Principal:
    result = rig.access.register(username, "password6")
    principal = rig.access.snapshot_principal(result["user_id"])
    rig.access.repo.set_user_permission(result["user_id"], "skill.create", True)
    rig.access.invalidate_all()
    return principal


def _skills(rig) -> SkillService:
    return SkillService(rig.db, access=rig.access, content_root=rig.tmp_path / "skills")


def test_catalog_lists_three_pinned_templates_with_full_metadata() -> None:
    catalog = templates_catalog()
    keys = {item["key"] for item in catalog}
    assert keys == TEMPLATE_KEYS == {"pdf", "xlsx", "skill-creator"}
    for item in catalog:
        assert item["origin"] == "anthropics/skills"
        assert item["commit"] == "2c5958ecac7c"
        assert item["license"]
        assert item["purpose"]
        assert isinstance(item["dependencies"], list)
        assert item["resources"]


def test_template_contents_are_self_contained_adapted_versions() -> None:
    for key in sorted(TEMPLATE_KEYS):
        content = load_template_content(key)
        assert "anthropics/skills" in content, key
        assert "2c5958ecac7c" in content, key
        # 适配声明：EasyChat 支持范围必须写明（资源目录扩展另设计）
        assert "EasyChat" in content, key
        assert len(content) > 3000, key


def test_unknown_template_key_rejected() -> None:
    from backend.shared.errors import InvalidInputError

    with pytest.raises(InvalidInputError):
        load_template_content("not-a-template")


@pytest.mark.asyncio
async def test_import_creates_validated_version_and_activate_enters_runtime(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    ready.attach_assistant()
    skills = _skills(ready)
    ready.assistant.dispatcher.skills = skills
    alice = _user(ready, f"alice_{uuid.uuid4().hex[:6]}")

    version = skills.import_template(alice, "pdf")
    assert version.status == "validated"
    skill = skills.get(alice, version.skill_id)
    assert skill.name == "pdf"
    assert skill.active_version_id is None  # 导入≠批量启用

    skills.activate(alice, version.skill_id, version.version_id, None)
    session_id = await ready.assistant.create_session(alice, source="wechat")
    receipt = await ready.assistant.submit(RunCommand(
        principal=alice, session_id=session_id, source="wechat",
        client_message_id=f"msg-{uuid.uuid4().hex[:6]}", text="你好",
    ))
    request = ready.assistant.dispatcher._build_request(
        ready.assistant.repo.get_run(receipt.run_id)
    )
    assert ("pdf", "1") in request.skill_versions
    assert "2c5958ecac7c" in request.system_context  # 来源与固定版本实际进入请求


@pytest.mark.asyncio
async def test_import_same_active_content_is_idempotent(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    skills = _skills(ready)
    bob = _user(ready, f"bob_{uuid.uuid4().hex[:6]}")

    first = skills.import_template(bob, "xlsx")
    skills.activate(bob, first.skill_id, first.version_id, None)
    second = skills.import_template(bob, "xlsx")
    assert second.version_id == first.version_id, (
        "当前激活内容与模板一致时不得重复追加版本"
    )


@pytest.mark.asyncio
async def test_template_import_is_owner_scoped(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    skills = _skills(ready)
    carol = _user(ready, f"carol_{uuid.uuid4().hex[:6]}")
    dave = _user(ready, f"dave_{uuid.uuid4().hex[:6]}")

    version = skills.import_template(carol, "skill-creator")
    assert [s.name for s in skills.list(dave)] == []
    assert [s.name for s in skills.list(carol)] == ["skill-creator"]
    from backend.shared.errors import ForbiddenError

    with pytest.raises(ForbiddenError):
        skills.get(dave, version.skill_id)


@pytest.mark.asyncio
async def test_templates_http_endpoints_registered(rig) -> None:
    """真实 HTTP 入口：目录可读、导入经服务、无 token 401。"""
    import httpx

    from backend.modules.skills.routes import build_skills_router
    from fastapi import FastAPI

    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    skills = _skills(ready)
    app = FastAPI()

    from backend.shared.errors import AppError

    @app.exception_handler(AppError)
    async def _handle(_: object, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    token_user = _user(ready, f"http_{uuid.uuid4().hex[:6]}")
    token = ready.access.create_token(token_user.user_id, "http", "user")
    app.include_router(
        build_skills_router(skills, ready.access.authenticate_token)
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        anon = await client.get("/api/skills/templates")
        assert anon.status_code == 401
        listing = await client.get(
            "/api/skills/templates", headers={"Authorization": f"Bearer {token}"}
        )
        assert listing.status_code == 200
        items = listing.json()["templates"]
        assert {i["key"] for i in items} == TEMPLATE_KEYS
        assert all(i["commit"] == "2c5958ecac7c" for i in items)

        imp = await client.post(
            "/api/skills/templates/pdf/import",
            json={"activate": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert imp.status_code == 200
        payload = imp.json()
        assert payload["version"]["status"] == "validated"
        assert payload["activated"] is not None
        # /templates 不得被 /{skill_id} 参数路由吞掉：非法 skill_id 查询仍 404/403 而非命中模板
        other = await client.get(
            "/api/skills/skl_nope", headers={"Authorization": f"Bearer {token}"}
        )
        assert other.status_code in (404, 403)
