"""进化路由：经验查看与显式回滚；验证/采用在服务层由证据驱动。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel

from backend.modules.evolution.adoption import AdoptionService
from backend.modules.evolution.api import EvolutionService
from backend.shared.errors import UnauthenticatedError


class RollbackBody(BaseModel):
    skill_id: str
    version_id: str
    reason: str = ""


def build_evolution_router(
    evolution: EvolutionService, adoption: AdoptionService, authenticate: Any
) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/evolution", tags=["evolution"])

    @router.get("/experiences")
    async def list_experiences(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {
            "experiences": [
                {
                    "experience_id": e.experience_id, "task_id": e.task_id,
                    "content": e.content, "conditions": e.conditions,
                    "counterexample": e.counterexample, "confidence": e.confidence,
                    "source_type": e.source_type, "created_at": e.created_at,
                }
                for e in evolution.experiences(principal)
            ]
        }

    @router.post("/rollback")
    async def rollback(body: RollbackBody,
                       authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        skill = adoption.rollback(
            principal, skill_id=body.skill_id, target_version_id=body.version_id,
            reason=body.reason,
        )
        return {"skill_id": skill.skill_id, "active_version_id": skill.active_version_id}

    return router
