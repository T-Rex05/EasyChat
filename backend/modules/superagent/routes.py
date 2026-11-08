"""superagent HTTP 路由：配置、任务受理与生命周期。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel

from backend.shared.errors import UnauthenticatedError


class SettingsBody(BaseModel):
    enabled: bool | None = None
    repo_url: str | None = None
    base_branch: str | None = None
    github_token: str | None = None
    pr_labels: str | None = None
    max_concurrent: int | None = None


class TaskCreateBody(BaseModel):
    title: str
    requirement: str
    context_extra: str = ""


def _task_dict(task) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "owner_id": task.owner_id,
        "title": task.title,
        "requirement": task.requirement,
        "context_extra": task.context_extra,
        "source": task.source,
        "status": task.status,
        "branch": task.branch,
        "pr_url": task.pr_url,
        "pr_number": task.pr_number,
        "result_summary": task.result_summary,
        "error": task.error,
        "attempts": task.attempts,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }


def _settings_dict(settings) -> dict[str, Any]:
    return {
        "enabled": settings.enabled,
        "repo_url": settings.repo_url,
        "base_branch": settings.base_branch,
        "github_token_mask": settings.github_token_mask,
        "has_github_token": settings.has_github_token,
        "pr_labels": settings.pr_labels,
        "max_concurrent": settings.max_concurrent,
        "updated_at": settings.updated_at,
    }


def build_superagent_router(service: Any, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/superagent", tags=["superagent"])

    @router.get("/settings")
    async def get_settings(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"settings": _settings_dict(service.get_settings(principal))}

    @router.put("/settings")
    async def update_settings(body: SettingsBody,
                              authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        settings = service.update_settings(
            principal,
            enabled=body.enabled,
            repo_url=body.repo_url,
            base_branch=body.base_branch,
            github_token=body.github_token,
            pr_labels=body.pr_labels,
            max_concurrent=body.max_concurrent,
        )
        return {"settings": _settings_dict(settings)}

    @router.get("/tasks")
    async def list_tasks(authorization: Annotated[str | None, Header()] = None,
                         limit: int = 50):
        principal = _principal(authorization)
        tasks = service.list_tasks(principal, limit=max(1, min(limit, 200)))
        return {"tasks": [_task_dict(t) for t in tasks]}

    @router.post("/tasks")
    async def create_task(body: TaskCreateBody,
                          authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        task = service.create_task(
            principal, title=body.title, requirement=body.requirement,
            context_extra=body.context_extra, source="web",
        )
        return {"task": _task_dict(task)}

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"task": _task_dict(service.get_task(principal, task_id))}

    @router.get("/tasks/{task_id}/events")
    async def list_events(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"events": [
            {"event_id": e.event_id, "kind": e.kind, "detail": e.detail,
             "created_at": e.created_at}
            for e in service.list_events(principal, task_id)
        ]}

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"task": _task_dict(service.cancel_task(principal, task_id))}

    @router.post("/tasks/{task_id}/retry")
    async def retry_task(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"task": _task_dict(service.retry_task(principal, task_id))}

    return router
