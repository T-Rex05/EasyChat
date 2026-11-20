"""profiles HTTP 路由：人格/安静时段/情绪设置与查看。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from backend.modules.profiles.api import ProfilesService, mood_as_dict, profile_as_dict
from backend.shared.errors import UnauthenticatedError


class ProfilePatch(BaseModel):
    persona_preset: str | None = None
    address_form: str | None = None
    max_chars: int | None = None
    emoji_level: str | None = None
    proactivity: str | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None
    timezone: str | None = None
    custom_instruction: str | None = None
    mood_opt_in: bool | None = None
    mood_retention_days: int | None = None


class PersonaCreate(BaseModel):
    name: str
    instruction: str


class PersonaPatch(BaseModel):
    name: str | None = None
    instruction: str | None = None
    active: bool | None = None


class MoodDeleteBody(BaseModel):
    confirm: bool = Field(default=False)


def build_profiles_router(service: ProfilesService, authenticate: Any) -> APIRouter:
    router = APIRouter(prefix="/api/profile", tags=["profile"])

    def principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    @router.get("")
    async def get_profile(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        profile = service.get(actor)
        return {
            "profile": profile_as_dict(profile),
            "quiet": {
                "active": service.in_quiet_hours(profile.owner_id),
                "start": profile.quiet_start,
                "end": profile.quiet_end,
            },
            "persona": service.render_persona(profile.owner_id, "web"),
        }

    @router.patch("")
    async def patch_profile(
        body: ProfilePatch,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        fields = body.model_dump(exclude_none=True)
        profile = service.update(actor, **fields)
        return {"profile": profile_as_dict(profile)}

    @router.get("/personas")
    async def list_personas(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return {"personas": service.list_personas(principal(authorization))}

    @router.post("/personas")
    async def create_persona(
        body: PersonaCreate, authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        return service.create_persona(principal(authorization), name=body.name, instruction=body.instruction)

    @router.patch("/personas/{persona_id}")
    async def update_persona(
        persona_id: str, body: PersonaPatch, authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        return service.update_persona(principal(authorization), persona_id, **body.model_dump(exclude_none=True))

    @router.get("/mood")
    async def list_mood(
        authorization: Annotated[str | None, Header()] = None,
        days: int = 7,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        entries = service.list_mood(actor, days=min(max(days, 1), 90))
        return {"entries": [mood_as_dict(item) for item in entries]}

    @router.delete("/mood")
    async def delete_mood(
        body: MoodDeleteBody,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        if not body.confirm:
            from backend.shared.errors import InvalidInputError

            raise InvalidInputError("删除情绪记录需要 confirm=true")
        result = service.delete_mood(actor)
        return {"deleted": result.deleted}

    return router
