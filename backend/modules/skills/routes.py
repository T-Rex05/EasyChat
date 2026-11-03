"""skills HTTP 路由：薄适配层，权限/版本规则全部在 SkillService。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel

from backend.modules.skills.api import SkillService
from backend.modules.skills.contracts import SkillVersionView, SkillView
from backend.shared.errors import InvalidInputError, UnauthenticatedError


class ProposeBody(BaseModel):
    content: str
    source: str = "web"
    parent_version_id: str | None = None


class ActivateBody(BaseModel):
    version_id: str
    expected_active_version_id: str | None = None


class RollbackBody(BaseModel):
    version_id: str


class PatchBody(BaseModel):
    pinned: bool | None = None
    archived: bool | None = None


def _version_payload(version: SkillVersionView) -> dict[str, Any]:
    return {
        "version_id": version.version_id,
        "skill_id": version.skill_id,
        "version_seq": version.version_seq,
        "content_hash": version.content_hash,
        "parent_version_id": version.parent_version_id,
        "source": version.source,
        "status": version.status,
        "created_at": version.created_at,
    }


def _skill_payload(skill: SkillView) -> dict[str, Any]:
    return {
        "skill_id": skill.skill_id,
        "owner_id": skill.owner_id,
        "name": skill.name,
        "description": skill.description,
        "origin": skill.origin,
        "pinned": skill.pinned,
        "archived": skill.archived,
        "active_version_id": skill.active_version_id,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
    }


def build_skills_router(service: SkillService, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/skills", tags=["skills"])

    @router.get("")
    async def list_skills(
        include_archived: bool = Query(default=False),
        all_owners: bool = Query(default=False),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        skills = service.list(
            principal, include_archived=include_archived, all_owners=all_owners,
        )
        return {"skills": [_skill_payload(s) for s in skills]}

    @router.get("/{skill_id}")
    async def get_skill(
        skill_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        skill = service.get(principal, skill_id)
        versions = service.list_versions(principal, skill_id)
        content = (
            service.read_active_content(principal, skill_id)
            if skill.active_version_id else None
        )
        return {
            "skill": _skill_payload(skill),
            "versions": [_version_payload(v) for v in versions],
            "content": content,
        }

    @router.post("/{name}/versions")
    async def propose_version(
        name: str,
        body: ProposeBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        version = service.propose(
            principal, name, body.content,
            source=body.source, parent_version_id=body.parent_version_id,
        )
        return {"version": _version_payload(version)}

    @router.post("/{skill_id}/activate")
    async def activate_version(
        skill_id: str,
        body: ActivateBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        skill = service.activate(
            principal, skill_id, body.version_id, body.expected_active_version_id,
        )
        return {"skill": _skill_payload(skill)}

    @router.post("/{skill_id}/rollback")
    async def rollback_version(
        skill_id: str,
        body: RollbackBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        skill = service.rollback(principal, skill_id, body.version_id)
        return {"skill": _skill_payload(skill)}

    @router.patch("/{skill_id}")
    async def patch_skill(
        skill_id: str,
        body: PatchBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        if body.pinned is None and body.archived is None:
            raise InvalidInputError("至少要提供 pinned 或 archived 之一")
        skill = service.get(principal, skill_id)
        if body.pinned is not None:
            skill = service.set_pinned(principal, skill_id, body.pinned)
        if body.archived is not None:
            skill = service.set_archived(principal, skill_id, body.archived)
        return {"skill": _skill_payload(skill)}

    return router
