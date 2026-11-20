"""提醒 HTTP 路由：薄适配；目标默认取用户有效微信绑定，也可显式邮箱。"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header
from pydantic import BaseModel

from backend.modules.delivery.contracts import DeliveryTarget, target_from_channel
from backend.modules.scheduling.api import SchedulingService
from backend.shared.errors import InvalidInputError, UnauthenticatedError


class ScheduleCreateBody(BaseModel):
    title: str = ""
    text: str = ""
    at: str = ""
    every_seconds: int = 0
    daily_at: str = ""
    weekly_at: str = ""
    weekday: int | None = None
    timezone: str = ""
    content_kind: str = "text"
    briefing_kind: str = ""
    target_kind: str = ""
    target_ref: str = ""


class ScheduleUpdateBody(BaseModel):
    title: str | None = None
    text: str | None = None
    at: str | None = None
    every_seconds: int | None = None
    daily_at: str | None = None
    weekly_at: str | None = None
    weekday: int | None = None
    timezone: str | None = None
    enabled: bool | None = None
    target_kind: Literal["wechat", "email"] | None = None
    target_ref: str | None = None


def _schedule_dict(schedule) -> dict[str, Any]:
    return {
        "schedule_id": schedule.schedule_id,
        "title": schedule.title,
        "text": schedule.text,
        "kind": schedule.kind,
        "interval_seconds": schedule.interval_seconds,
        "at_time": schedule.at_time,
        "timezone": schedule.timezone,
        "next_run_at": schedule.next_run_at,
        "enabled": schedule.enabled,
        "last_run_at": schedule.last_run_at,
        "weekday": schedule.weekday,
        "content_kind": schedule.content_kind,
        "briefing_kind": schedule.briefing_kind,
        "target": {
            "kind": schedule.target.kind, "ref": schedule.target.ref,
            "channel_account_id": schedule.target.channel_account_id,
        },
    }


def build_scheduling_router(service: SchedulingService, channels: Any, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    def _target(owner_id: int, kind: str, ref: str) -> DeliveryTarget:
        if kind and ref:
            return DeliveryTarget(kind=kind, ref=ref)
        if kind == "email" or ref:
            raise InvalidInputError("邮箱目标需要同时提供 target_kind=email 与 target_ref")
        resolved = (
            channels.delivery_target_for_owner(owner_id)
            if channels is not None else None
        )
        if not resolved:
            raise InvalidInputError("没有可用的微信绑定，请先绑定渠道或提供邮箱目标")
        return target_from_channel(resolved)

    router = APIRouter(prefix="/api/schedules", tags=["scheduling"])

    @router.get("")
    async def list_schedules(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"schedules": [_schedule_dict(s) for s in service.list(principal)]}

    @router.post("")
    async def create_schedule(body: ScheduleCreateBody,
                              authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        schedule = service.create(
            principal, title=body.title, text=body.text,
            target=_target(principal.user_id, body.target_kind, body.target_ref),
            at=body.at, every_seconds=body.every_seconds, daily_at=body.daily_at,
            weekly_at=body.weekly_at, weekday=body.weekday, timezone=body.timezone,
            content_kind=body.content_kind, briefing_kind=body.briefing_kind,
        )
        return {"schedule": _schedule_dict(schedule)}

    @router.patch("/{schedule_id}")
    async def update_schedule(schedule_id: str, body: ScheduleUpdateBody,
                              authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        changes = body.model_dump(exclude_none=True, exclude={"target_kind", "target_ref"})
        if body.target_kind is not None or body.target_ref is not None:
            schedule = service.get(principal, schedule_id)
            if body.target_kind == "wechat" and body.target_ref:
                raise InvalidInputError("微信目标需要使用用户已绑定的账号")
            changes["target"] = _target(schedule.owner_id, body.target_kind or "", (body.target_ref or "").strip())
        if not changes:
            raise InvalidInputError("请提供要更新的提醒设置")
        return {"schedule": _schedule_dict(service.update(principal, schedule_id, **changes))}

    @router.delete("/{schedule_id}")
    async def cancel_schedule(schedule_id: str,
                              authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        service.remove(principal, schedule_id)
        return {"ok": True, "deleted": schedule_id}

    @router.get("/{schedule_id}/occurrences")
    async def occurrences(schedule_id: str,
                          authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"occurrences": [
            {"occurrence_id": o.occurrence_id, "scheduled_at": o.scheduled_at,
             "state": o.state, "delivery_id": o.delivery_id, "job_id": o.job_id,
             "missed": o.missed}
            for o in service.occurrences(principal, schedule_id)
        ]}

    return router
