"""memory HTTP 路由：薄适配层，权限/规则在 MemoryService。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, Field

from backend.modules.memory.api import MemoryService
from backend.modules.memory.contracts import MemoryRecord, SourceRef
from backend.shared.errors import UnauthenticatedError


class RecallBody(BaseModel):
    query: str
    top_k: int = 5
    budget: int = 2000


class SourceRefBody(BaseModel):
    kind: str = "message"
    ref: str
    quote: str = ""


class RememberBody(BaseModel):
    kind: str
    content: str
    source_refs: list[SourceRefBody]
    scope: str = "user"
    event_at: str | None = None
    confidence: float = 0.5
    source_type: str = "model_inferred"
    tags: list[str] = []
    supersedes: str | None = None
    pinned: bool = False


class ReviseBody(BaseModel):
    expected_version: int = Field(ge=1)
    content: str
    reason: str = ""
    source_refs: list[SourceRefBody] = []


class FeedbackBody(BaseModel):
    source_event_id: str
    signal: str = "used"
    note: str = ""


class ForgetBody(BaseModel):
    memory_id: str = ""
    source_ref: str = ""
    query: str = ""
    reason: str = ""


def _record(record: MemoryRecord) -> dict[str, Any]:
    return {
        "memory_id": record.memory_id,
        "kind": record.kind,
        "content": record.content,
        "source_refs": [{"kind": r.kind, "ref": r.ref, "quote": r.quote}
                        for r in record.source_refs],
        "scope": record.scope,
        "event_at": record.event_at,
        "recorded_at": record.recorded_at,
        "version": record.version,
        "status": record.status,
        "pinned": record.pinned,
        "confidence": record.confidence,
        "source_type": record.source_type,
        "tags": list(record.tags),
    }


def _refs(items: list[SourceRefBody]) -> tuple[SourceRef, ...]:
    return tuple(SourceRef(kind=i.kind, ref=i.ref, quote=i.quote) for i in items if i.ref)


def build_memory_router(service: MemoryService, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/memory", tags=["memory"])

    @router.get("")
    async def list_memories(
        include_archived: bool = Query(default=False),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return {"memories": [_record(m) for m in service.list(principal, include_archived=include_archived)]}

    @router.post("/recall")
    async def recall(body: RecallBody, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        result = service.recall(
            principal, body.query, top_k=body.top_k, token_budget=body.budget,
        )
        return {
            "items": [
                {"score": item.score, "matched_terms": list(item.matched_terms),
                 "memory": _record(item.memory)}
                for item in result.items
            ],
            "candidate_count": result.candidate_count,
            "estimated_tokens": result.estimated_tokens,
            "include_archived": result.include_archived,
            "no_result": result.no_result,
            "reason": result.reason,
        }

    @router.post("/remember")
    async def remember(body: RememberBody, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        from backend.modules.memory.contracts import MemoryCandidate

        record = service.remember(principal, MemoryCandidate(
            kind=body.kind, content=body.content, source_refs=_refs(body.source_refs),
            scope=body.scope, event_at=body.event_at, confidence=body.confidence,
            source_type=body.source_type, tags=tuple(body.tags),
            supersedes=body.supersedes, pinned=body.pinned,
        ))
        return {"memory": _record(record)}

    @router.put("/{memory_id}")
    async def revise(memory_id: str, body: ReviseBody,
                     authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        record = service.revise(
            principal, memory_id, body.expected_version, content=body.content,
            reason=body.reason, source_refs=_refs(body.source_refs),
        )
        return {"memory": _record(record)}

    @router.post("/{memory_id}/feedback")
    async def feedback(memory_id: str, body: FeedbackBody,
                       authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        created = service.record_feedback(
            principal, memory_id, body.source_event_id, body.signal, body.note,
        )
        return {"ok": True, "created": created}

    @router.post("/forget")
    async def forget(body: ForgetBody, authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        result = service.forget(
            principal, memory_id=body.memory_id, source_ref=body.source_ref,
            query=body.query, reason=body.reason,
        )
        return {
            "forgotten": result.forgotten, "rule_recorded": result.rule_recorded,
            "affected_ids": list(result.affected_ids),
        }

    @router.delete("/{memory_id}")
    async def delete_memory(memory_id: str, reason: str = Query(default=""),
                            authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        result = service.forget(principal, memory_id=memory_id, reason=reason)
        return {"forgotten": result.forgotten}

    return router
