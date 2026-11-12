"""superagent HTTP 路由：capabilities、配置、任务受理（幂等）、inputs、增量事件。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel


class AcceptanceCheckBody(BaseModel):
    item_id: str
    title: str
    category: str = ""
    status: str
    required_evidence: list[str] = []
    observation: str = ""
    evidence: list[dict] = []


class AcceptanceRoundBody(BaseModel):
    requirement: str = ""
    attempt_id: str = ""
    provenance: dict = {}
    checks: list[AcceptanceCheckBody]


class AcceptanceDecisionBody(BaseModel):
    decision: str  # accepted | rejected
    note: str = ""

from backend.shared.errors import UnauthenticatedError


class SettingsBody(BaseModel):
    enabled: bool | None = None
    repo_url: str | None = None
    base_branch: str | None = None
    github_token: str | None = None
    pr_labels: str | None = None
    max_concurrent: int | None = None
    verify_profile: str | None = None
    allow_unverified_draft: bool | None = None
    auto_fix_enabled: bool | None = None
    auto_fix_max_rounds: int | None = None


class TaskCreateBody(BaseModel):
    title: str
    requirement: str
    context_extra: str = ""


class TaskInputBody(BaseModel):
    text: str


def _task_dict(task) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "owner_id": task.owner_id,
        "title": task.title,
        "requirement": task.requirement,
        "context_extra": task.context_extra,
        "source": task.source,
        "status": task.status,
        "phase": task.phase,
        "branch": task.branch,
        "repo_url": task.repo_url_snapshot,
        "base_branch": task.base_branch_snapshot,
        "pr_url": task.pr_url,
        "pr_number": task.pr_number,
        "pr_state": task.pr_state,
        "outcome": task.outcome,
        "result_summary": task.result_summary,
        "error": task.error,
        "attempts": task.attempts,
        "auto_fix_rounds": task.auto_fix_rounds,
        "active_attempt_id": task.active_attempt_id,
        "cancel_requested": bool(task.cancel_requested_at),
        "legacy_config_unknown": task.legacy_config_unknown,
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
        "verify_profile": settings.verify_profile,
        "allow_unverified_draft": settings.allow_unverified_draft,
        "auto_fix_enabled": settings.auto_fix_enabled,
        "auto_fix_max_rounds": settings.auto_fix_max_rounds,
        "updated_at": settings.updated_at,
    }


def build_superagent_router(service: Any, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/superagent", tags=["superagent"])

    @router.get("/capabilities")
    async def get_capabilities(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"capabilities": service.capabilities(principal)}

    @router.get("/ops/metrics")
    async def ops_metrics(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"metrics": service.ops_metrics(principal)}

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
            verify_profile=body.verify_profile,
            allow_unverified_draft=body.allow_unverified_draft,
            auto_fix_enabled=body.auto_fix_enabled,
            auto_fix_max_rounds=body.auto_fix_max_rounds,
        )
        return {"settings": _settings_dict(settings)}

    @router.get("/tasks")
    async def list_tasks(authorization: Annotated[str | None, Header()] = None,
                         limit: int = 50, cursor: str = "", status: str = ""):
        principal = _principal(authorization)
        page_limit = max(1, min(limit, 100))
        cursor_created_at, _, cursor_id = cursor.partition("|")
        tasks = service.list_tasks(
            principal,
            limit=page_limit,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
            status=status.strip(),
        )
        next_cursor = ""
        if len(tasks) == page_limit and tasks:
            last = tasks[-1]
            next_cursor = f"{last.created_at}|{last.task_id}"
        return {"tasks": [_task_dict(t) for t in tasks], "next_cursor": next_cursor}

    @router.post("/tasks")
    async def create_task(body: TaskCreateBody,
                          authorization: Annotated[str | None, Header()] = None,
                          idempotency_key: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        task = service.create_task(
            principal, title=body.title, requirement=body.requirement,
            context_extra=body.context_extra, source="web",
            idempotency_key=(idempotency_key or "").strip(),
        )
        return {"task": _task_dict(task)}

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"task": _task_dict(service.get_task(principal, task_id))}

    @router.get("/tasks/{task_id}/events")
    async def list_events(task_id: str, authorization: Annotated[str | None, Header()] = None,
                          after_id: int = 0, limit: int = 200):
        principal = _principal(authorization)
        events = service.list_events(principal, task_id, after_id=after_id)
        return {
            "events": [
                {"event_id": e["id"], "kind": e["kind"], "detail": e["detail"],
                 "created_at": e["created_at"]}
                for e in events
            ],
            "next_after_id": max((int(e["id"]) for e in events), default=after_id),
        }

    @router.get("/tasks/{task_id}/attempts")
    async def list_attempts(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        attempts = service.list_attempts(principal, task_id)
        return {"attempts": [
            {"attempt_id": a.attempt_id, "attempt_no": a.attempt_no, "state": a.state,
             "checkpoint": a.checkpoint, "head_sha": a.head_sha, "pr_number": a.pr_number,
             "pr_url": a.pr_url, "started_at": a.started_at, "finished_at": a.finished_at,
             "error_code": a.error_code, "error_summary": a.error_summary}
            for a in attempts
        ]}

    @router.get("/tasks/{task_id}/reports")
    async def list_reports(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        reports = service.list_reports(principal, task_id)
        return {"reports": [
            {"report_id": r.report_id, "kind": r.kind, "summary": r.summary,
             "question": r.question, "head_sha": r.head_sha,
             "verification_ref": r.verification_ref, "created_at": r.created_at}
            for r in reports
        ]}

    @router.post("/tasks/{task_id}/inputs")
    async def append_input(task_id: str, body: TaskInputBody,
                           authorization: Annotated[str | None, Header()] = None,
                           idempotency_key: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        created = service.append_task_input(
            principal, task_id, text=body.text, source="web",
            external_event_id=(idempotency_key or "").strip(),
        )
        return {"input": {"input_id": created.input_id, "text": created.text,
                          "created_at": created.created_at}}

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        task = await service.cancel_task(principal, task_id)
        return {"task": _task_dict(task)}

    @router.post("/tasks/{task_id}/retry")
    async def retry_task(task_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"task": _task_dict(service.retry_task(principal, task_id))}

    # ---- 逐项验收（工作包四） ------------------------------------------------------

    @router.post("/tasks/{task_id}/acceptance/rounds")
    async def submit_acceptance_round(task_id: str, body: AcceptanceRoundBody,
                                      authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        result = service.submit_acceptance_round(
            principal, task_id, requirement=body.requirement, attempt_id=body.attempt_id,
            provenance=body.provenance,
            checks=[c.model_dump() for c in body.checks],
        )
        return {"round": result}

    @router.get("/tasks/{task_id}/acceptance")
    async def list_acceptance(task_id: str, authorization: Annotated[str | None, Header()] = None):
        import json as _json

        principal = _principal(authorization)
        rounds = service.acceptance_for_task(principal, task_id)
        for r in rounds:
            r["summary"] = _json.loads(r.pop("summary_json") or "{}")
            r["provenance"] = _json.loads(r.pop("provenance_json") or "{}")
            for c in r["checks"]:
                c["evidence"] = _json.loads(c.pop("evidence_json") or "[]")
                c["required_evidence"] = _json.loads(c.pop("required_evidence") or "[]")
        return {"rounds": rounds}

    @router.post("/acceptance/checks/{check_id}/decision")
    async def decide_acceptance_check(check_id: int, body: AcceptanceDecisionBody,
                                      authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        result = service.decide_acceptance_check(
            principal, check_id, decision=body.decision, note=body.note,
        )
        return {"decision": result}

    @router.get("/tasks/{task_id}/acceptance/rounds/{round_id}/evidence/{item_id}/{index}")
    async def read_acceptance_evidence(task_id: str, round_id: str, item_id: str, index: int,
                                       authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        path = service.acceptance_evidence_path(principal, task_id, round_id, item_id, index)
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

    return router
