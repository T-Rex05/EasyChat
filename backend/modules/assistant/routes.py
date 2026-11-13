"""Web 兼容路由：旧 /chat/stream SSE 契约 → 统一 Assistant（A09）。

帧格式 id:{seq} + data:{json}；事件名 start/token/thinking_step/stream_reset/
chat_complete/error；busy→409；Last-Event-ID 续传；缓存失效发 resync+持久终态，
不重新执行。薄适配层：不选模型、不写 SQL、不创建 Agent。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.modules.assistant.api import AssistantService
from backend.modules.files.contracts import DEFAULT_MAX_ATTACHMENTS
from backend.modules.assistant.repository import (
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_INTERRUPTED,
)
from backend.shared.errors import AppError, BusyError, InvalidInputError, NotFoundError, UnauthenticatedError

_LEGACY_THREAD_RE = re.compile(r"^\d+_\d+$")
_SSE_RETRY_AFTER_DONE = "retry: 86400000\n\n"


class StreamPostBody(BaseModel):
    message: str
    thread_id: str
    client_msg_id: str = ""
    mode: str = "normal"
    scene: str = ""
    model_id: int | None = None
    images: list[dict[str, str]] = []
    files: list[dict[str, str]] = []
    attachment_ids: list[str] = []


def _sse_frame(seq: int | None, payload: dict[str, Any]) -> str:
    prefix = f"id: {seq}\n" if seq is not None and seq >= 0 else ""
    return prefix + f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_web_chat_router(
    assistant: AssistantService,
    authenticate: Any,
    authenticate_ticket: Any = None,
) -> APIRouter:
    """authenticate: Callable[[str], Principal]（bootstrap 注入 access.authenticate_token）。

    authenticate_ticket: Callable[[str], Principal]（注入 access.consume_sse_ticket）。
    审计 #3：EventSource 无法带 Header，但 30 天期 JWT 不得进 URL——GET /chat/stream
    只接受秒级一次性 ticket 或 Authorization header；长效 token 查询参数已移除。
    """

    def _principal_from_token(token: str | None):
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    def _principal_from_request(ticket: str | None, authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if token:
            return _principal_from_token(token)
        if ticket:
            if authenticate_ticket is None:
                raise UnauthenticatedError("请先登录")
            return authenticate_ticket(ticket)
        raise UnauthenticatedError("请先登录")

    async def _resolve_session(principal, thread_id: str) -> str:
        if not thread_id:
            raise InvalidInputError("缺少 thread_id")
        if thread_id.startswith("wx_"):
            raise InvalidInputError("微信会话请走渠道入口")
        if thread_id.startswith("sess_"):
            assistant.repo.get_session(thread_id, owner_id=principal.user_id)  # 归属校验
            return thread_id
        if _LEGACY_THREAD_RE.match(thread_id):
            return await assistant.get_or_create_session(
                principal, external_chat_id=thread_id, source="web"
            )
        raise InvalidInputError(f"无法识别的 thread_id 格式: {thread_id[:40]}")

    async def _final_frame_for(principal, run_id: str, thread_id: str) -> tuple[str | None, str]:
        """从持久状态构造最终帧（resync 场景），不重新执行。"""
        status = await assistant.run_status(principal, run_id)
        state = status["status"]
        if state == RUN_COMPLETED:
            content = _final_content(principal, run_id)
            return None, _sse_frame(None, {"type": "chat_complete", "thread_id": thread_id,
                                           "final_content": content, "timestamp": "", "todos": []})
        if state == RUN_FAILED:
            return _sse_frame(None, {"type": "error", "message": status["error"] or "执行失败"}), ""
        if state == RUN_CANCELLED:
            return _sse_frame(None, {"type": "error", "message": "已取消"}), ""
        if state == RUN_INTERRUPTED:
            return _sse_frame(None, {"type": "error", "message": "执行被中断，请稍后查看结果"}), ""
        return None, ""

    def _final_content(principal, run_id: str) -> str:
        conn = assistant.db.connect()
        try:
            row = conn.execute(
                "SELECT content FROM conversations WHERE run_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return str(row["content"]) if row else ""
        finally:
            conn.close()

    async def _stream_events(principal, run_id: str, thread_id: str, after_seq: int) -> AsyncIterator[str]:
        yield _sse_frame(None, {"type": "start", "thread_id": thread_id, "conversation_id": run_id})
        try:
            iterator = assistant.iter_events(principal, run_id, after_seq=after_seq)
        except NotFoundError:
            # 环形缓存失效：resync + 持久最终状态，不重新执行
            yield _sse_frame(None, {"type": "stream_reset"})
            reset_frame, done_frame = await _final_frame_for(principal, run_id, thread_id)
            if reset_frame:
                yield reset_frame
            if done_frame:
                yield done_frame
            yield _SSE_RETRY_AFTER_DONE
            return
        try:
            while True:
                event = await iterator.__anext__()
                seq = event.seq
                kind = event.kind
                if kind == "token":
                    yield _sse_frame(seq, {"type": "token", "content": str(event.payload.get("text", ""))})
                elif kind == "thinking":
                    yield _sse_frame(seq, {"type": "thinking_step", "content": str(event.payload.get("text", ""))})
                elif kind == "stream_reset":
                    yield _sse_frame(seq, {"type": "stream_reset"})
                elif kind == "tool_started":
                    # 内部工具事件不直接暴露敏感内容；前端兼容层不消费此帧
                    continue
                elif kind == "completed":
                    assistant.events.flush_token(run_id)
                    yield _sse_frame(None, {"type": "chat_complete", "thread_id": thread_id,
                                            "final_content": str(event.payload.get("final_content", "")),
                                            "timestamp": "", "todos": []})
                    yield _SSE_RETRY_AFTER_DONE
                    return
                elif kind in ("failed", "cancelled", "interrupted"):
                    message = {
                        "failed": str(event.payload.get("error") or "执行失败"),
                        "cancelled": "已取消",
                        "interrupted": "执行被中断，请稍后查看结果",
                    }[kind]
                    yield _sse_frame(None, {"type": "error", "message": message})
                    yield _SSE_RETRY_AFTER_DONE
                    return
        except (StopAsyncIteration, asyncio.CancelledError):
            return

    router = APIRouter()

    @router.get("/chat/stream")
    async def stream_get(
        request: Request,
        message: str = Query(...),
        thread_id: str = Query(...),
        client_msg_id: str = Query(default=""),
        ticket: str = Query(default=""),
        authorization: Annotated[str | None, Header()] = None,
        mode: str = Query(default="normal"),
        scene: str = Query(default=""),
        last_seq: int = Query(default=0, ge=0),
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ):
        # URL 上只允许秒级一次性 ticket 或 Authorization header（审计 #3）
        principal = _principal_from_request(ticket or None, authorization)
        session_id = await _resolve_session(principal, thread_id)
        client_msg_id = client_msg_id or f"auto-{session_id[:8]}-{message[:12]}"
        try:
            receipt = await assistant.submit(_make_command(principal, session_id, client_msg_id, message))
        except BusyError as busy:
            return JSONResponse(status_code=409, content={"error": str(busy)})
        except AppError as exc:
            return JSONResponse(status_code=exc.http_status, content=exc.to_payload())
        # 浏览器自动重连会带 Last-Event-ID header；前端受控重连（新 ticket）
        # 无法设置 header，以 last_seq 查询参数传"最后已收 seq"，语义相同：
        # 从 N+1 续传，不重复回放。取两者较大值。
        from_seq = max(
            _resume_from(last_event_id),
            _resume_from(str(last_seq) if last_seq else None),
        )
        return StreamingResponse(
            _stream_events(principal, receipt.run_id, thread_id, from_seq),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/chat/stream")
    async def stream_post(request: Request, body: StreamPostBody,
                          authorization: Annotated[str | None, Header()] = None,
                          last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None):
        principal = _principal_from_token((authorization or "").replace("Bearer ", "").strip() or None)
        session_id = await _resolve_session(principal, body.thread_id)
        client_msg_id = body.client_msg_id or f"auto-{session_id[:8]}-{body.message[:12]}"
        if len(body.attachment_ids) > DEFAULT_MAX_ATTACHMENTS:
            raise InvalidInputError("附件数量超过上限")
        for attachment_id in body.attachment_ids:
            await assistant.get_attachment(principal, attachment_id)
        try:
            receipt = await assistant.submit(_make_command(
                principal, session_id, client_msg_id, body.message, tuple(body.attachment_ids),
            ))
        except BusyError as busy:
            return JSONResponse(status_code=409, content={"error": str(busy)})
        except AppError as exc:
            return JSONResponse(status_code=exc.http_status, content=exc.to_payload())
        from_seq = _resume_from(last_event_id)
        return StreamingResponse(
            _stream_events(principal, receipt.run_id, body.thread_id, from_seq),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/chat/cancel")
    @router.post("/chat/cancel")
    async def cancel_chat(
        request: Request,
        thread_id: str = Query(default=""),
        client_msg_id: str = Query(default=""),
        run_id: str = Query(default=""),
        ticket: str = Query(default=""),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal_from_request(ticket or None, authorization)
        target = run_id
        if not target:
            session_id = await _resolve_session(principal, thread_id)
            run = _latest_run_for_session(session_id, client_msg_id)
            target = run
        if not target:
            return JSONResponse(status_code=404, content={"error": "not_found", "message": "未找到进行中的请求"})
        cancelled = await assistant.cancel(principal, target)
        return {"ok": True, "cancelled": bool(cancelled), "run_id": target}

    @router.get("/api/history")
    async def history_list(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal_from_token((authorization or "").replace("Bearer ", "").strip())
        sessions = await assistant.list_sessions(principal, limit=limit, offset=offset)
        return {
            "sessions": [
                {
                    "session_id": s["id"],
                    "title": s["title"],
                    "source": s["source"],
                    "created_at": s["created_at"],
                    "updated_at": s["updated_at"],
                }
                for s in sessions
                if s["active"]
            ],
            "offset": offset,
            "limit": limit,
        }

    @router.get("/api/history/{session_id}")
    async def history_messages(session_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal_from_token((authorization or "").replace("Bearer ", "").strip())
        messages = await assistant.session_messages(principal, session_id)
        return {
            "session_id": session_id,
            "messages": [
                {"role": m["role"], "content": m["content"], "created_at": m["created_at"]}
                for m in messages
                if m["status"] == 1
            ],
        }

    @router.put("/api/history/{session_id}")
    async def history_rename(session_id: str, body: dict, authorization: Annotated[str | None, Header()] = None):
        principal = _principal_from_token((authorization or "").replace("Bearer ", "").strip())
        await assistant.rename_session(principal, session_id, str(body.get("title", "")))
        return {"ok": True}

    @router.delete("/api/history/{session_id}")
    async def history_delete(session_id: str, authorization: Annotated[str | None, Header()] = None):
        principal = _principal_from_token((authorization or "").replace("Bearer ", "").strip())
        await assistant.delete_session(principal, session_id)
        return {"ok": True}

    def _latest_run_for_session(session_id: str, client_msg_id: str) -> str:
        conn = assistant.db.connect()
        try:
            row = conn.execute(
                "SELECT id FROM runs WHERE session_id=? AND client_message_id=? ORDER BY created_at DESC LIMIT 1",
                (session_id, client_msg_id),
            ).fetchone() if client_msg_id else None
            if row is None:
                row = conn.execute(
                    "SELECT id FROM runs WHERE session_id=? AND status IN ('queued','running','cancel_requested') "
                    "ORDER BY created_at DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
            return str(row["id"]) if row else ""
        finally:
            conn.close()

    return router


def _make_command(principal, session_id: str, client_msg_id: str, message: str,
                  attachment_ids: tuple[str, ...] = ()):
    from backend.modules.assistant.contracts import RunCommand

    return RunCommand(
        principal=principal,
        session_id=session_id,
        source="web",
        client_message_id=client_msg_id,
        text=message,
        attachment_ids=attachment_ids,
    )


def _resume_from(last_event_id: str | None) -> int:
    """EventSource Last-Event-ID → from_seq（N+1，排除已看到的 N）。"""
    if not last_event_id:
        return 0
    try:
        seq = int(str(last_event_id).strip())
    except ValueError:
        return 0
    return seq + 1 if seq >= 0 else 0
