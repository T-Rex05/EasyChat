"""收件箱 HTTP 路由：列表/搜索/保存/归档/删除。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from backend.modules.inbox.api import InboxService
from backend.shared.errors import UnauthenticatedError


class SaveBody(BaseModel):
    url: str = ""
    file_id: str = ""
    note: str = ""
    title: str = ""
    tags: list[str] = Field(default_factory=list)


def item_as_dict(item) -> dict[str, Any]:
    return {
        "id": item.item_id,
        "kind": item.kind,
        "title": item.title,
        "url": item.url,
        "file_id": item.file_id,
        "note": item.note,
        "summary": item.summary,
        "tags": list(item.tags),
        "status": item.status,
        "enrich_state": item.enrich_state,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def build_inbox_router(service: InboxService, authenticate: Any) -> APIRouter:
    router = APIRouter(prefix="/api/inbox", tags=["inbox"])

    def principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    @router.get("")
    async def list_items(
        authorization: Annotated[str | None, Header()] = None,
        status: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        items = service.list(actor, status=status, limit=min(max(limit, 1), 100))
        return {"items": [item_as_dict(item) for item in items]}

    @router.get("/search")
    async def search_items(
        q: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        return {"items": [item_as_dict(item) for item in service.search(actor, q)]}

    @router.post("")
    async def save_item(
        body: SaveBody,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        item = service.save(
            actor, url=body.url, file_id=body.file_id, note=body.note,
            title=body.title, tags=body.tags, source="web",
        )
        return {"item": item_as_dict(item)}

    @router.post("/{item_id}/archive")
    async def archive_item(
        item_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        return {"item": item_as_dict(service.archive(actor, item_id))}

    @router.post("/{item_id}/read")
    async def read_item(
        item_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        return {"item": item_as_dict(service.mark_read(actor, item_id))}

    @router.delete("/{item_id}")
    async def delete_item(
        item_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = principal(authorization)
        service.delete(actor, item_id)
        return {"deleted": True}

    return router
