"""assistant 旧 HTTP 兼容（Task 15）：上传/反馈/执行审批在新架构未实现或已移除。

明确 503/空结果，避免前端得到 404 或误以为成功；全部要求登录。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header

from backend.shared.errors import CapabilityUnavailableError, UnauthenticatedError


def build_assistant_compat_router(authenticate: Any) -> APIRouter:
    def _require(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(tags=["assistant-compat"])

    @router.post("/api/chat/upload-images")
    async def upload_images(authorization: Annotated[str | None, Header()] = None):
        _require(authorization)
        raise CapabilityUnavailableError("新架构暂不支持图片上传附件")

    @router.post("/api/chat/upload-files")
    async def upload_files(authorization: Annotated[str | None, Header()] = None):
        _require(authorization)
        raise CapabilityUnavailableError("新架构暂不支持文件上传附件")

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
