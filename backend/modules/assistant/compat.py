"""assistant 旧 HTTP 兼容：上传复用 files；反馈和执行审批返回明确能力状态。"""
from __future__ import annotations

import base64
from typing import Annotated, Any

from fastapi import APIRouter, File, Header, UploadFile

from backend.modules.files.contracts import DEFAULT_MAX_ATTACHMENTS, REF_ATTACHMENT, SaveMetadata
from backend.shared.errors import CapabilityUnavailableError, InvalidInputError, UnauthenticatedError


def build_assistant_compat_router(authenticate: Any, assistant: Any = None, file_service: Any = None) -> APIRouter:
    def _require(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(tags=["assistant-compat"])

    async def _upload(principal, uploads: list[UploadFile], *, images: bool):
        if assistant is None or file_service is None:
            raise CapabilityUnavailableError("附件服务未就绪")
        if not uploads or len(uploads) > DEFAULT_MAX_ATTACHMENTS:
            raise InvalidInputError(f"每次请上传 1 至 {DEFAULT_MAX_ATTACHMENTS} 个附件")
        assistant.access.require_permission(principal, "chat.use")
        results = []
        for upload in uploads:
            head = await upload.read(4096)
            if images and file_service.detect_upload_mime(head, upload.filename or "") not in {
                "image/png", "image/jpeg", "image/gif", "image/webp",
            }:
                raise InvalidInputError("图片内容必须为 PNG、JPEG、GIF 或 WebP")

            async def chunks():
                yield head
                while block := await upload.read(1024 * 1024):
                    yield block

            saved = await file_service.save_stream(principal, chunks(), SaveMetadata(
                original_name=upload.filename or "附件", declared_mime=upload.content_type or "",
                source="web",
            ))
            record = saved.file
            attachment_id = await assistant.register_attachment(
                principal, file_name=record.original_name, file_path="",
                mime=record.verified_mime, file_size=record.size_bytes,
                sha256=record.sha256, stored_file_id=record.file_id,
            )
            file_service.link(principal, record.file_id, REF_ATTACHMENT, attachment_id)
            item = {"attachment_id": attachment_id, "file_id": record.file_id,
                    "filename": record.original_name}
            if images:
                with file_service.open_read(principal, record.file_id) as handle:
                    encoded = base64.b64encode(handle.read()).decode("ascii")
                item.update(mime=record.verified_mime,
                            data_url=f"data:{record.verified_mime};base64,{encoded}")
            else:
                item.update(size=record.size_bytes, content_type=record.verified_mime,
                            content=None, readable=False, url=f"/api/files/{record.file_id}/content")
            results.append(item)
        return {"images" if images else "files": results}

    @router.post("/api/chat/upload-images")
    async def upload_images(files: Annotated[list[UploadFile], File()] = [],
                            authorization: Annotated[str | None, Header()] = None):
        return await _upload(_require(authorization), files, images=True)

    @router.post("/api/chat/upload-files")
    async def upload_files(files: Annotated[list[UploadFile], File()] = [],
                           authorization: Annotated[str | None, Header()] = None):
        return await _upload(_require(authorization), files, images=False)

    @router.post("/api/chat/feedback")
    async def feedback(authorization: Annotated[str | None, Header()] = None):
        _require(authorization)
        raise CapabilityUnavailableError("对话反馈接口已移除")

    @router.get("/chat/exec-approval/pending")
    async def pending_approval(thread_id: str = "",
                               authorization: Annotated[str | None, Header()] = None):
        _require(authorization)
        return {"pending": False, "thread_id": thread_id}

    @router.post("/chat/exec-approval")
    async def resolve_approval(authorization: Annotated[str | None, Header()] = None):
        _require(authorization)
        raise CapabilityUnavailableError("新架构不在 Web 进程执行宿主机命令")

    return router
