"""files HTTP 路由：薄适配层，授权/保存/引用规则全部在 FileService。

- 上传：Web multipart，流式消费，不在内存保留整文件；owner 只来自 Principal；
- 下载：鉴权接口，不映射到公开 static，不暴露 storage_key/绝对路径；
- 文件名安全编码（RFC 5987），响应禁止 MIME 嗅探。
"""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Header, Query, UploadFile
from fastapi.responses import StreamingResponse

from backend.modules.files.api import FileService
from backend.modules.files.contracts import (
    DELETE_SCOPES,
    FileRecord,
    SaveMetadata,
)
from backend.shared.errors import InvalidInputError, UnauthenticatedError

_CHUNK_SIZE = 1024 * 1024


def file_payload(record: FileRecord) -> dict[str, Any]:
    """对外 JSON：不含 storage_key/绝对路径。"""
    return {
        "file_id": record.file_id,
        "original_name": record.original_name,
        "mime": record.verified_mime,
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
        "status": record.status,
        "kind": record.kind,
        "source": record.source,
        "retention_policy": record.retention_policy,
        "created_at": record.created_at,
        "deleted_at": record.deleted_at,
        "error": record.error,
    }


def build_files_router(service: FileService, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/files", tags=["files"])

    @router.post("")
    async def upload_file(
        file: Annotated[UploadFile, File()],
        request_id: Annotated[str, Form()] = "",
        session_id: Annotated[str, Form()] = "",
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)

        async def _chunks():
            while True:
                block = await file.read(_CHUNK_SIZE)
                if not block:
                    break
                yield block

        metadata = SaveMetadata(
            original_name=file.filename or "未命名文件",
            declared_mime=file.content_type or "",
            source="web",
            session_id=session_id,
        )
        result = await service.save_stream(
            principal, _chunks(), metadata, request_id=request_id,
        )
        return {
            "file": file_payload(result.file),
            "receipt_id": result.receipt_id,
            "duplicate": result.duplicate,
            "reused_content": result.reused_content,
        }

    @router.get("")
    async def list_files(
        kind: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        all_owners: bool = Query(default=False),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        records = service.list(
            principal, limit=limit, offset=offset, kind=kind, all_owners=all_owners,
        )
        return {"files": [file_payload(r) for r in records]}

    @router.get("/{file_id}")
    async def get_file(
        file_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        record = service.get(principal, file_id)
        return {
            "file": file_payload(record),
            "references": service.reference_counts(principal, file_id),
        }

    @router.get("/{file_id}/content")
    async def download_file(
        file_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        record = service.get(principal, file_id)
        handle = service.open_read(principal, file_id)
        safe_name = quote(record.original_name or "download.bin", safe="")

        def _stream():
            try:
                while True:
                    block = handle.read(_CHUNK_SIZE)
                    if not block:
                        break
                    yield block
            finally:
                handle.close()

        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}",
            "Content-Length": str(record.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        }
        return StreamingResponse(
            _stream(), media_type=record.verified_mime or "application/octet-stream",
            headers=headers,
        )

    @router.delete("/{file_id}")
    async def delete_file(
        file_id: str,
        scope: str = Query(default="unlink"),
        ref_kind: str = Query(default=""),
        ref_id: str = Query(default=""),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        if scope not in DELETE_SCOPES:
            raise InvalidInputError(f"未知删除范围: {scope}")
        if scope == "unlink" and bool(ref_kind) != bool(ref_id):
            raise InvalidInputError("撤回引用需要同时提供 ref_kind 与 ref_id")
        impact = service.request_delete(
            principal, file_id, scope, ref_kind=ref_kind, ref_id=ref_id,
        )
        return {
            "file_id": impact.file_id,
            "scope": impact.scope,
            "allowed": impact.allowed,
            "reason": impact.reason,
            "reference_counts": dict(impact.reference_counts),
        }

    return router
