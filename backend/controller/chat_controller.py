"""
聊天控制器 - 主路由注册

提供 SSE 流式聊天端点，核心逻辑已拆分到：
- chat_persistence.py: 对话持久化辅助函数
- chat_stream.py: SSE 流式处理逻辑
"""
import asyncio
import base64
import json
from pathlib import Path
from typing import AsyncGenerator, List, Dict, Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, JSONResponse
from backend.service.auth.auth_middleware import get_current_user

from backend.controller.chat import persistence
from backend.controller.chat.persistence import (
    set_conversation_mapper,
    _mark_conversation_cancelled,
)
from backend.controller.chat.stream import (
    token_stream_events,
    completed_threads,
    MAX_HISTORY_MESSAGES,
)
from backend.controller.conversation_controller import (
    save_message, limit_chat_history, chat_histories, clear_thread_history,
)
from backend.controller.utils_controller import sanitize_for_json, safe_json_dumps
from backend.hooks import ChatHookContext, get_hooks, has_hooks
from backend.utils.log_utils import log
from backend.utils.time_utils import now_local_iso
from backend.utils.todo_parser import parse_todos_from_tool_output
from backend.utils.rate_limit import limiter

logger = log

# ── 会话归属校验 ──

def _parse_thread_user(thread_id: str):
    """从 thread_id 解析 user_id（web: {user_id}_{timestamp}；微信: wx_{user_id}_{wxid}）。
    
    格式验证：
    - Web: 必须为 {整数}_{时间戳或任意字符串} 格式
    - 微信: 必须为 wx_{整数}_{wxid} 格式
    """
    if not thread_id:
        return None
    if thread_id.startswith("wx_"):
        # 微信格式: wx_{user_id}_{wxid}
        parts = thread_id.split("_", 2)
        if len(parts) >= 3:
            try:
                user_id = int(parts[1])
                # 验证 wxid 非空
                if not parts[2]:
                    return None
                return user_id
            except ValueError:
                return None
        return None
    # Web 格式: {user_id}_{timestamp} 或 {user_id}_{任意标识}
    if "_" not in thread_id:
        return None
    try:
        first_part = thread_id.split("_")[0]
        user_id = int(first_part)
        # 验证 user_id 为正整数
        if user_id <= 0:
            return None
        return user_id
    except ValueError:
        return None


def _thread_belongs_to(thread_id: str, user_id: int) -> bool:
    """校验会话归属：优先解析 thread_id 前缀；解析不出时查 conversations 表兜底。"""
    parsed = _parse_thread_user(thread_id)
    if parsed is not None:
        return parsed == int(user_id)
    try:
        mapper = persistence.conversation_mapper
        if mapper is None:
            return False
        conn = mapper._get()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM conversations WHERE session_id = %s LIMIT 1", (thread_id,))
            row = cur.fetchone()
            return bool(row) and int(row.get("user_id") or 0) == int(user_id)
        finally:
            conn.close()
    except Exception:
        return False


# ── 常量 ──
# 历史消息窗口（兜底软上限）。本地有 session 时 Hermes 从 state.db 恢复完整历史，
# 不受此值限制；仅无 session（首次/换机）时回退用前端注入的最近 N 条。

# ============================================================
# 通用辅助函数
# ============================================================

async def _with_sse_keepalive(
    gen: AsyncGenerator[str, None], interval: float = 8.0
) -> AsyncGenerator[str, None]:
    """
    SSE 心跳包装器：内层生成器静默超过 interval 秒时补发空 data 事件，
    防止代理/浏览器在长工具调用期间掐断连接。

    必须用 data: 事件行而非注释行（: xxx），因为浏览器 EventSource
    默认忽略注释行，不会重置前端超时计时器。
    """
    it = gen.__aiter__()
    task = None
    try:
        while True:
            if task is None:
                task = asyncio.ensure_future(anext(it))
            done, _ = await asyncio.wait({task}, timeout=interval)
            if not done:
                yield "data: {}\n\n"  # 空 data 事件（心跳）
                continue
            finished, task = task, None
            try:
                yield finished.result()
            except StopAsyncIteration:
                return
    finally:
        if task is not None:
            task.cancel()


# ============================================================
# 子 Agent 委派留痕 → 历史消息回填
# ============================================================

def _to_dt(value):
    """把 'YYYY-MM-DD HH:MM:SS' / ISO 字符串 / datetime 统一成 datetime；失败返回 None。"""
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value
    text = str(value).strip().replace("T", " ")
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            from datetime import datetime as _dt

            return _dt.strptime(text[:26], fmt)
        except Exception:
            continue
    return None


def _load_delegations_for_history(chat_id: str) -> List[Dict[str, Any]]:
    """读取该会话的委派留痕（失败返回空列表，历史接口不能因为留痕不可用而挂掉）。"""
    try:
        from backend.service.delegation.store import list_by_thread

        return list_by_thread(chat_id, limit=100)
    except Exception as e:
        logger.debug(f"委派留痕查询失败（忽略）: {e}")
        return []


def _delegations_for_window(rows: List[Dict[str, Any]], start, end) -> List[Dict[str, Any]]:
    """挑出时间窗内发起的委派（同一轮对话的 assistant 消息上展示）。

    没有可用时间戳时退化为"全部挂在最后一轮"，宁可位置不准也不要丢信息。
    """
    if not rows:
        return []
    t0, t1 = _to_dt(start), _to_dt(end)
    if t0 is None and t1 is None:
        return rows
    hit = []
    for row in rows:
        ts = _to_dt(row.get("started_at"))
        if ts is None:
            continue
        if (t0 is None or ts >= t0) and (t1 is None or ts <= t1):
            hit.append(row)
    return hit


# ============================================================
# 路由注册
# ============================================================
def create_controller(app: FastAPI):
    """创建并注册所有通用路由。"""

    # ── SSE 流式聊天 ──
    @app.get("/chat/stream")
    @limiter.limit("60/minute")
    async def stream_chat(
        request: Request,
        message: str,
        thread_id: str = "default",
        client_msg_id: str = None,
        mode: str = "normal",
        token: str = None,
        scene: str = "",
        model_id: int = None,
    ):
        """
        GET 版 SSE 流式端点，前端使用 EventSource 连接。
        支持 Last-Event-ID 断线续传、client_msg_id 幂等去重。
        EventSource 无法携带 Header，登录态通过 token 查询参数传递。
        """
        from backend.service.auth.auth_service import verify_token as _verify_token, check_token_renewal as _check_renew, renew_token as _renew_token

        # ── 鉴权（token 查询参数） ──
        if not token:
            return JSONResponse(status_code=401, content={"error": "未登录"})
        _user = _verify_token(token)
        # 宽限期刷新：token 已过期但仍在 grace period 内，自动续期
        if not _user:
            _refreshed = _renew_token(token)
            if _refreshed:
                _user = _verify_token(_refreshed)
                token = _refreshed  # 后续用新 token 推送刷新事件
            else:
                return JSONResponse(status_code=401, content={"error": "Token 无效或已过期"})
        if not _thread_belongs_to(thread_id, _user.get("user_id")):
            return JSONResponse(status_code=403, content={"error": "无权访问该会话"})

        # ── 滑动窗口续期 ──
        _new_token = _check_renew(token)

        from backend.service.run_registry import ThreadBusyError

        logger.debug(f"/chat/stream - thread_id={thread_id!r}, msg_len={len(message)}")

        try:
            if not message:
                raise HTTPException(status_code=400, detail="message 参数必填")

            from backend.controller import stream_runner

            # 如果 token 已续期，通过 SSE 事件推送新 token（EventSource 无法读取响应头）
            async def _inject_token_event(gen):
                if _new_token:
                    import json as _json
                    yield f"data: {_json.dumps({'type': 'token_refresh', 'token': _new_token})}\n\n"
                async for chunk in gen:
                    yield chunk

            stream_body = stream_runner.open_request_stream(
                thread_id, message, client_msg_id,
                request.headers.get("last-event-id"),
                lambda: token_stream_events(message, thread_id, mode=mode, scene=scene, model_id=model_id),
            )
            return StreamingResponse(
                _with_sse_keepalive(_inject_token_event(stream_body)),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Cache-Control",
                    "Access-Control-Expose-Headers": "X-New-Token",
                },
            )
        except ThreadBusyError as busy:
            logger.warning(f"thread busy - thread_id={thread_id}: {busy}")
            return JSONResponse(status_code=409, content={"error": str(busy)})
        except Exception as e:
            logger.error(f"创建 StreamingResponse 失败: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})

    # ── POST SSE 流式聊天（支持图片） ──
    @app.post("/chat/stream")
    @limiter.limit("60/minute")
    async def stream_chat_post(request: Request, user: dict = Depends(get_current_user)):
        """POST 版 SSE 流式端点，支持图片附件。前端使用 fetch + ReadableStream 连接。"""
        from backend.service.run_registry import ThreadBusyError
        from backend.service.auth.auth_service import check_token_renewal as _check_renew

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="请求体需为 JSON")

        message = str(body.get("message", "")).strip()
        thread_id = str(body.get("thread_id", "default")).strip()
        client_msg_id = body.get("client_msg_id")
        mode = str(body.get("mode", "normal")).strip()
        images = body.get("images")
        files = body.get("files")
        scene = str(body.get("scene", "")).strip()
        _raw_model_id = body.get("model_id")
        model_id = int(_raw_model_id) if _raw_model_id else None

        # ── 鉴权：thread_id 必须属于当前登录用户 ──
        if not _thread_belongs_to(thread_id, user.get("user_id")):
            raise HTTPException(status_code=403, detail="无权访问该会话")

        # ── 滑动窗口续期（从 Authorization 头提取 token） ──
        _new_token = None
        try:
            _auth_header = request.headers.get("authorization", "")
            _raw_token = _auth_header.removeprefix("Bearer ").strip() if _auth_header else ""
            if _raw_token:
                _new_token = _check_renew(_raw_token)
        except Exception as e:
            logger.warning(f"Token 续期失败: {e}")

        logger.debug(f"POST /chat/stream - thread_id={thread_id!r}, msg_len={len(message)}, images={len(images) if images else 0}, files={len(files) if files else 0}")

        try:
            if not message and not images and not files:
                raise HTTPException(status_code=400, detail="message / images / files 至少需要一项")

            from backend.controller import stream_runner

            # 如果 token 已续期，通过 SSE 事件推送新 token
            async def _inject_token_event_post(gen):
                if _new_token:
                    yield f"data: {json.dumps({'type': 'token_refresh', 'token': _new_token})}\n\n"
                async for chunk in gen:
                    yield chunk

            stream_body = stream_runner.open_request_stream(
                thread_id, message, client_msg_id,
                request.headers.get("last-event-id"),
                lambda: token_stream_events(message, thread_id, mode=mode, images=images, files=files, scene=scene, model_id=model_id),
            )
            return StreamingResponse(
                _with_sse_keepalive(_inject_token_event_post(stream_body)),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Cache-Control, Content-Type",
                    "Access-Control-Expose-Headers": "X-New-Token",
                },
            )
        except ThreadBusyError as busy:
            logger.warning(f"thread busy - thread_id={thread_id}: {busy}")
            return JSONResponse(status_code=409, content={"error": str(busy)})
        except Exception as e:
            logger.error(f"创建 StreamingResponse 失败: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})

    # ── 图片上传 ──
    @app.post("/api/chat/upload-images")
    async def upload_chat_images(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
        """上传聊天图片，返回 data_url 数组供前端直接使用。"""
        if not files:
            raise HTTPException(status_code=400, detail="请选择至少一张图片")

        uploaded = []

        for f in files:
            if not f.content_type or not f.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail=f"不支持的文件类型: {f.content_type}")

            content = await f.read()
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"图片 {f.filename} 超过 20MB 限制")

            b64 = base64.b64encode(content).decode("ascii")
            data_url = f"data:{f.content_type};base64,{b64}"

            uploaded.append({
                "mime": f.content_type,
                "data_url": data_url,
                "filename": f.filename,
            })

        logger.info(f"图片上传: count={len(uploaded)}")
        return {
            "ok": True,
            "images": uploaded,
            "count": len(uploaded),
        }

    @app.post("/api/chat/upload-files")
    async def upload_chat_files(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
        """上传文件（md/pdf/txt/pptx/docx/xlsx 等），存盘并读取内容。"""
        if not files:
            raise HTTPException(status_code=400, detail="请选择至少一个文件")

        from backend.controller.wechat.file import _read_file_content as _read_file
        import uuid as _uuid, os as _os

        uploaded = []
        for f in files:
            content_type = f.content_type or "application/octet-stream"
            content = await f.read()
            size = len(content)

            if size > 50 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"文件 {f.filename} 超过 50MB 限制")

            # 存储到 uploads 目录，返回静态文件 URL（用户隔离）
            from backend.config.paths import get_uploads_dir
            user_id = user.get("user_id")
            upload_dir = get_uploads_dir(user_id)
            ext = Path(f.filename or "file").suffix or ".bin"
            stored_name = f"{_uuid.uuid4().hex[:12]}{ext}"
            stored_path = upload_dir / stored_name
            stored_path.write_bytes(content)

            # 读取文本内容
            text = _read_file(str(stored_path))

            uploaded.append({
                "filename": f.filename or "unnamed",
                "size": size,
                "content_type": content_type,
                "content": text or "",
                "readable": text is not None,
                "url": f"/static/uploads/{stored_name}",
            })

        logger.info(f"文件上传: count={len(uploaded)} files={[u['filename'] for u in uploaded]}")
        return {"ok": True, "files": uploaded, "count": len(uploaded)}

    # ── 用户取消 ──
    @app.get("/chat/cancel")
    @app.post("/chat/cancel")
    async def cancel_chat(request: Request, user: dict = Depends(get_current_user)):
        """
        用户主动暂停/停止 AI 回复。
        取消 Registry 后台 Task + DB 标记 status=3。
        """
        if request.method == "GET":
            thread_id = (request.query_params.get("thread_id") or "").strip()
            client_msg_id = (request.query_params.get("client_msg_id") or "").strip()
            conversation_id = request.query_params.get("conversation_id")
        else:
            try:
                body = await request.json()
            except Exception:
                body = {}
            thread_id = (body.get("thread_id") or "").strip()
            client_msg_id = (body.get("client_msg_id") or "").strip()
            conversation_id = body.get("conversation_id")

        if not thread_id or not client_msg_id:
            raise HTTPException(status_code=400, detail="thread_id 和 client_msg_id 必填")

        if not _thread_belongs_to(thread_id, user.get("user_id")):
            raise HTTPException(status_code=403, detail="无权操作该会话")

        from backend.controller import stream_runner
        from backend.controller.stream_runner import resolve_client_msg_id

        run_key = resolve_client_msg_id(client_msg_id, thread_id, "")
        cancelled = stream_runner.cancel_run(thread_id, run_key)

        if conversation_id:
            try:
                _cid = int(conversation_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="conversation_id 必须为数字")
            _mark_conversation_cancelled(_cid, user_id=user.get("user_id"))

        # 清理内存
        try:
            from backend.tools.tools_decorator import _clear_todo_list
            _clear_todo_list(thread_id)
        except Exception:
            pass
        try:
            from backend.controller.conversation_controller import clear_thread_history, mark_thread_cancelled
            clear_thread_history(thread_id)
            mark_thread_cancelled(thread_id)
        except Exception:
            pass

        logger.info(f"取消 - thread_id={thread_id}, cancelled={cancelled}")
        return {"status": "ok", "run_cancelled": cancelled}

    # ── 聊天历史 API ──
    @app.get("/api/history")
    async def get_chat_history_list(user: dict = Depends(get_current_user)):
        """获取当前用户的聊天会话列表（包含标题和时间）。"""
        user_id = user.get("user_id")
        sessions = []
        # 从数据库获取会话列表（仅当前用户）
        if persistence.conversation_mapper:
            try:
                conn = persistence.conversation_mapper._get()
                try:
                    cur = conn.cursor()
                    # 获取每个会话的 ID、最后更新时间和第一条对话 ID
                    cur.execute("""
                        SELECT
                            c.session_id,
                            MAX(c.updated_at) as last_update,
                            MIN(c.id) as first_conv_id
                        FROM conversations c
                        WHERE c.status != 0 AND c.user_id = %s
                        GROUP BY c.session_id
                        ORDER BY last_update DESC
                        LIMIT 100
                    """, (user_id,))
                    session_map = {}
                    for r in cur.fetchall():
                        session_map[r["session_id"]] = {
                            "id": r["session_id"],
                            "last_update": r["last_update"],
                            "title": "",
                            "first_conv_id": r["first_conv_id"]
                        }

                    # 获取每个会话的第一条对话作为标题
                    if session_map:
                        session_ids = list(session_map.keys())
                        placeholders = ','.join(['%s'] * len(session_ids))
                        cur.execute(f"""
                            SELECT session_id, user_question
                            FROM conversations
                            WHERE session_id IN ({placeholders})
                              AND user_question != ''
                            ORDER BY created_at ASC
                        """, session_ids)

                        for r in cur.fetchall():
                            if r["session_id"] in session_map and not session_map[r["session_id"]]["title"]:
                                session_map[r["session_id"]]["title"] = r["user_question"][:50]

                    sessions = list(session_map.values())
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"数据库查询失败：{e}")

        # 添加内存中的会话（仅当前用户）
        memory_ids = set(chat_histories.keys()) - {s["id"] for s in sessions}
        for mid in memory_ids:
            if _thread_belongs_to(mid, user_id):
                sessions.append({
                    "id": mid,
                    "last_update": None,
                    "title": "",
                    "first_conv_id": None
                })

        # 按最后更新时间排序（统一转为字符串，兼容 datetime / str / None）
        def _sort_key(s):
            v = s.get("last_update")
            if v is None:
                return ""
            if hasattr(v, "isoformat"):
                return v.isoformat()
            return str(v)
        sessions.sort(key=_sort_key, reverse=True)

        return {"sessions": sessions[:100]}

    @app.put("/api/history/{chat_id}")
    async def rename_chat_session(chat_id: str, request: Request, user: dict = Depends(get_current_user)):
        """重命名会话。

        在 conversations 表的 session_title 字段保存标题（一个会话可有多条记录，
        重命名时同步更新该 session_id 的所有行），刷新后历史列表优先读取该字段。
        """
        try:
            body = await request.json()
            new_title = str(body.get("title", "")).strip()
            if not new_title:
                raise HTTPException(status_code=400, detail="标题不能为空")
            if len(new_title) > 255:
                new_title = new_title[:255]

            if not _thread_belongs_to(chat_id, user.get("user_id")):
                raise HTTPException(status_code=403, detail="无权操作该会话")

            if persistence.conversation_mapper:
                try:
                    conn = persistence.conversation_mapper._get()
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE conversations
                        SET session_title = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE session_id = %s AND user_id = %s
                    """, (new_title, chat_id, user.get("user_id")))
                    conn.commit()
                    updated = cur.rowcount
                    if updated == 0:
                        logger.warning(f"重命名会话无匹配记录 - session_id={chat_id}")
                except Exception as e:
                    logger.error(f"重命名失败：{e}")
                    raise HTTPException(status_code=500, detail="重命名失败")

            return {"ok": True}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/history/{chat_id}")
    async def delete_chat_session(chat_id: str, user: dict = Depends(get_current_user)):
        """删除会话（软删除，设置 status=0）并联动删除 Hermes state.db 记录。"""
        if not _thread_belongs_to(chat_id, user.get("user_id")):
            raise HTTPException(status_code=403, detail="无权操作该会话")

        if persistence.conversation_mapper:
            try:
                conn = persistence.conversation_mapper._get()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE conversations
                    SET status = 0
                    WHERE session_id = %s AND user_id = %s
                """, (chat_id, user.get("user_id")))
                conn.commit()
            except Exception as e:
                logger.error(f"删除失败：{e}")
                raise HTTPException(status_code=500, detail="删除失败")

        # 清理内存缓存
        if chat_id in chat_histories:
            del chat_histories[chat_id]

        # 联动删除 Hermes 侧 state.db 会话记录（避免孤儿 session）
        try:
            from backend.hermes_adapter import delete_hermes_session_history
            delete_hermes_session_history(chat_id)
        except Exception:
            pass

        return {"ok": True}


    @app.get("/api/history/{chat_id}")
    async def get_chat_messages(chat_id: str, user: dict = Depends(get_current_user)):
        """获取特定对话的消息历史（优先从数据库加载）。"""
        if not _thread_belongs_to(chat_id, user.get("user_id")):
            raise HTTPException(status_code=403, detail="无权访问该会话")
        messages = []

        if persistence.conversation_mapper:
            try:
                conversations = persistence.conversation_mapper.get_conversations_by_session(chat_id)
                logger.info(f"历史查询 chat_id={chat_id!r} mapper={type(persistence.conversation_mapper).__name__} 结果={len(conversations) if conversations else 0} 条")
                # 子 Agent 委派留痕：按时间窗回填到对应那一轮 assistant 消息上，
                # 否则刷新/切会话后子 Agent 面板就消失了（帧只活在内存里）。
                _delegations = _load_delegations_for_history(chat_id)
                _attached_delegations = 0
                if conversations:
                    for conv in conversations:
                        user_content = str(conv.get("user_question", "")).strip()
                        assistant_content = str(conv.get("agent_answer", "")).strip()
                        conv_id = conv.get("id")
                        source = str(conv.get("source", "web"))
                        # 解析 metadata 中的图片数据
                        metadata = conv.get("metadata")
                        images = None
                        if metadata:
                            try:
                                if isinstance(metadata, str):
                                    metadata = json.loads(metadata)
                                if isinstance(metadata, dict) and "images" in metadata:
                                    images = metadata["images"]
                            except (json.JSONDecodeError, TypeError):
                                pass
                        
                        # 注意：get_conversations_by_session 返回 created_at/updated_at 列，
                        # 而非 create_time/update_time，二者字段名不一致会导致时间戳为空。
                        t_user = str(conv.get("created_at") or conv.get("create_time") or "").replace(" ", "T")
                        t_assistant = str(conv.get("updated_at") or conv.get("update_time") or conv.get("created_at") or "").replace(" ", "T")
                        if user_content:
                            msg = {
                                "id": f"user-{conv_id}",
                                "role": "user", "content": user_content,
                                "timestamp": t_user,
                                "conversation_id": conv_id,
                                "source": source,
                            }
                            if images:
                                msg["images"] = images
                            messages.append(msg)
                        if assistant_content:
                            _msg = {
                                "id": f"assistant-{conv_id}",
                                "role": "assistant", "content": assistant_content,
                                "timestamp": t_assistant,
                                "conversation_id": conv_id,
                                "source": source,
                            }
                            _tasks = _delegations_for_window(
                                _delegations, conv.get("created_at") or conv.get("create_time"),
                                conv.get("updated_at") or conv.get("update_time") or conv.get("created_at"),
                            )
                            if _tasks:
                                _msg["subagent_tasks"] = _tasks
                                _attached_delegations += len(_tasks)
                            messages.append(_msg)
                    # 时间窗一个都没命中（时区/时间戳缺失）时，全部挂到最后一轮，
                    # 宁可位置不精确也不要让委派记录凭空消失。
                    if _delegations and _attached_delegations == 0:
                        for _m in reversed(messages):
                            if _m.get("role") == "assistant":
                                _m["subagent_tasks"] = _delegations
                                break
                    chat_histories[chat_id] = messages
            except Exception as e:
                logger.error(f"加载对话历史失败: {e}")

        return {"messages": messages}

    # ── 任务列表 API ──
    @app.get("/api/todos")
    async def get_thread_todos(thread_id: str = "default", user: dict = Depends(get_current_user)):
        """获取指定会话的任务清单。"""
        if not _thread_belongs_to(thread_id, user.get("user_id")):
            raise HTTPException(status_code=403, detail="无权访问该会话")
        try:
            from backend.tools.tools_decorator import _get_todo_list
            data = _get_todo_list(thread_id)
            return {"todos": data.get("tasks", [])}
        except Exception as e:
            logger.warning(f"获取任务列表失败: {e}")
            return {"todos": []}

    # ── 聊天反馈（RAG 评测闭环入口：点赞/点踩 → 归因检索 chunk → 生成优化建议） ──
    @app.post("/api/chat/feedback")
    async def chat_feedback(request: Request, user: dict = Depends(get_current_user)):
        """提交聊天反馈。body: {conversation_id?, thread_id?, rating: 1|-1, comment?}"""
        try:
            body = await request.json()
        except Exception:
            body = {}
        conversation_id = body.get("conversation_id")
        thread_id = str(body.get("thread_id") or "").strip()
        try:
            rating = int(body.get("rating", 0))
        except (TypeError, ValueError):
            rating = 0
        comment = str(body.get("comment") or "").strip()

        if rating not in (1, -1):
            raise HTTPException(status_code=400, detail="rating 仅支持 1（赞）或 -1（踩）")

        from backend.service.kb.kb_feedback import (
            FeedbackInvalid, FeedbackNotFound, create_feedback,
        )
        try:
            return create_feedback(
                user["user_id"],
                int(conversation_id) if conversation_id is not None else None,
                thread_id, rating, comment,
            )
        except FeedbackInvalid as e:
            raise HTTPException(status_code=400, detail=str(e))
        except FeedbackNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── exec 审批：查询待审批（页面恢复用） ──
    @app.get("/chat/exec-approval/pending")
    async def get_pending_exec_approval(thread_id: str = Query(...), user: dict = Depends(get_current_user)):
        """查询指定会话当前是否有待审批命令（用于前端页面切换后恢复审批卡片）。"""
        if not _thread_belongs_to(thread_id, user.get("user_id")):
            raise HTTPException(status_code=403, detail="无权查看该会话的审批")
        from backend.hermes_adapter import get_pending_approval as _get_pending
        pa = _get_pending(thread_id)
        if pa:
            return {"pending": True, **pa}
        return {"pending": False}

    # ── exec 审批决议（主机白名单远程命令 / Hermes 危险命令共用） ──
    @app.post("/chat/exec-approval")
    async def resolve_exec_approval(request: Request, user: dict = Depends(get_current_user)):
        """前端审批卡片点击后调用：decision = allow-once / allow-session / deny。"""
        try:
            body = await request.json()
        except Exception:
            body = {}
        approval_id = str(body.get("approval_id") or "").strip()
        decision = str(body.get("decision") or "").strip()
        thread_id = str(body.get("thread_id") or "").strip()
        if not approval_id or decision not in ("allow-once", "allow-session", "deny"):
            raise HTTPException(status_code=400, detail="approval_id 与 decision（allow-once/allow-session/deny）必填")
        if thread_id and not _thread_belongs_to(thread_id, user.get("user_id")):
            raise HTTPException(status_code=403, detail="无权操作该会话的审批")
        from backend.hermes_adapter import resolve_pending_approval as _resolve_approval
        # 传入审核人信息（留痕）
        approver_user_id = user.get("user_id")
        approver_name = user.get("username") or ""
        ok = _resolve_approval(approval_id, decision,
                               confirmed_by_user_id=approver_user_id,
                               confirmed_by_name=approver_name)
        return {"ok": ok, "approval_id": approval_id, "decision": decision}

    # ── Favicon ──
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        from fastapi.responses import Response
        return Response(status_code=204)

    # ── 注册钩子自定义路由 ──
    hooks = get_hooks()
    if hooks and hooks.register_routes:
        try:
            hooks.register_routes(app)
            logger.info("钩子自定义路由已注册")
        except Exception as e:
            logger.warning(f"注册钩子自定义路由失败: {e}")
