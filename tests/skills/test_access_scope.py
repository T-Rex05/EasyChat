"""技能资产访问范围与授权撤销回归。"""
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.modules.skills.routes import build_skills_router
from backend.shared.errors import AppError, InvalidInputError
from tests.skills.helpers import make_skill_rig, make_user


@pytest.mark.asyncio
async def test_revocation_blocks_private_reads_writes_and_runtime_but_keeps_catalog(tmp_path):
    rig, service, _ = make_skill_rig(tmp_path)
    try:
        owner = make_user(rig, tag="owner")
        version = service.import_template(owner, "pdf")
        service.activate(owner, version.skill_id, version.version_id, None)
        assert len(service.list_for_runtime(owner)) == 1
        token = rig.access.create_token(owner.user_id, "owner", "user")
        rig.access.repo.set_user_permission(owner.user_id, "skill.create", False)
        rig.access.invalidate_all()

        app = FastAPI()
        app.include_router(build_skills_router(service, rig.access.authenticate_token))

        @app.exception_handler(AppError)
        async def handle_error(_, exc):
            return JSONResponse(exc.to_payload(), status_code=exc.http_status)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            root = f"/api/skills/{version.skill_id}"
            reads = [
                await client.get("/api/skills"),
                await client.get(root),
                await client.get(f"{root}/versions/{version.version_id}"),
            ]
            writes = [
                await client.patch(root, json={"pinned": True}),
                await client.patch(root, json={"archived": True}),
                await client.post("/api/skills/pdf/versions", json={"content": "新的内容"}),
                await client.post("/api/skills/templates/pdf/import"),
            ]
            assert [response.status_code for response in reads + writes] == [403] * 7
            assert (await client.get("/api/skills/templates")).status_code == 200
            assert (await client.get("/api/skills/templates/pdf")).status_code == 200
        assert service.list_for_runtime(owner) == ()
    finally:
        rig.db.close()


def test_effective_manager_can_browse_other_owners_but_runtime_stays_personal(tmp_path):
    rig, service, _ = make_skill_rig(tmp_path)
    try:
        owner = make_user(rig, tag="owner")
        outsider = make_user(rig, tag="outsider")
        manager = make_user(rig, grants=("skill.manage",), revokes=("skill.create",))
        version = service.propose(owner, "private", "# Private version")
        service.activate(owner, version.skill_id, version.version_id, None)
        assert service.list(outsider) == ()
        assert service.list(manager) == ()
        assert [item.owner_id for item in service.list(manager, all_owners=True)] == [owner.user_id]
        assert service.read_version_content(manager, version.version_id) == "# Private version"
        assert service.list_for_runtime(manager) == ()
        assert service.set_pinned(manager, version.skill_id, True).pinned
    finally:
        rig.db.close()


def test_proposal_with_another_owners_parent_leaves_no_personal_skill(tmp_path):
    rig, service, _ = make_skill_rig(tmp_path)
    try:
        owner = make_user(rig, tag="owner")
        manager = make_user(rig, grants=("skill.manage",))
        version = service.propose(owner, "shared-name", "# Owner content")

        with pytest.raises(InvalidInputError):
            service.propose(
                manager, "shared-name", "# Manager content", parent_version_id=version.version_id,
            )
        assert service.list(manager) == ()
        assert [item.version_id for item in service.list_versions(owner, version.skill_id)] == [version.version_id]
    finally:
        rig.db.close()
