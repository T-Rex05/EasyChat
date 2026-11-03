"""聊天控制器 - SSE 流式处理"""
import asyncio
import json
import re
import base64
from typing import AsyncGenerator, List, Dict, Any, Optional
from pathlib import Path
from fastapi import HTTPException
from backend.utils.log_utils import log
from backend.utils.time_utils import now_local_iso
from backend.utils.multimodal_detect import check_model_multimodal
from backend.utils.image_safety import process_image_safe
from backend.controller.chat.persistence import (
    conversation_mapper,
    _insert_running_conversation,
    _persist_conversation_answer,
    _mark_conversation_failed,
)
from backend.controller.conversation_controller import (
    save_message, limit_chat_history, chat_histories, clear_thread_history,
)
from backend.controller.utils_controller import safe_json_dumps
from backend.controller.chat_cleanup import mark_completed_time
from backend.hooks import ChatHookContext, get_hooks

logger = log

# 历史消息窗口（兜底软上限）
MAX_HISTORY_MESSAGES = 7

# 全局集合：追踪已完成的对话（防止重复发送 chat_complete）
completed_threads: set = set()


# ──────────────────────────────────────────────────────────────
# 同步 DB 辅助函数（供 asyncio.to_thread 调用）
# ──────────────────────────────────────────────────────────────

def _fetch_username_sync(user_id: int) -> Optional[str]:
    """同步查询用户名（在线程池中执行）。"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row:
            return row.get("username") if isinstance(row, dict) else row[0]
        return None
    finally:
        conn.close()


def _load_conversations_sync(thread_id: str) -> List[Dict[str, Any]]:
    """同步加载会话历史（在线程池中执行）。"""
    if not conversation_mapper:
        return []
    return conversation_mapper.get_conversations_by_session(thread_id)


def _insert_running_conversation_sync(
    thread_id: str, user_id: int, message: str, chat_mode: str, metadata: Optional[Dict] = None
) -> Optional[int]:
    """同步入口落库（在线程池中执行）。"""
    return _insert_running_conversation(thread_id, user_id, message, chat_mode=chat_mode, metadata=metadata)


def _persist_conversation_answer_sync(
    conversation_id: Optional[int], thread_id: str, user_id: int, user_message: str, answer: str
) -> Optional[int]:
    """同步持久化答案（在线程池中执行）。"""
    return _persist_conversation_answer(conversation_id, thread_id, user_id, user_message, answer)


def _flush_audit_sync(
    thread_id: str, user_id: int, approvals: List[Dict[str, Any]]
) -> int:
    """同步审计落库（在线程池中执行）。"""
    from backend.db.schema import get_conn
    if not approvals:
        return 0
    conn = get_conn()
    try:
        count = 0
        for rec in approvals:
            conn.execute(
                "INSERT INTO exec_approval_logs "
                "(thread_id, user_id, command, decision, allow_permanent, confirmed_by_name, confirmed_by_user_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (thread_id, user_id, str(rec.get("command", ""))[:2000],
                 str(rec.get("decision", "")), 1 if rec.get("allow_permanent") else 0,
                 str(rec.get("confirmed_by_name") or ""),
                 rec.get("confirmed_by_user_id")),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def _stream_text_chunks(text: str, chunk_size: int = 900) -> List[str]:
    """将长文本按段落边界拆分为适合 SSE 流式推送的块。"""
    content = str(text or "")
    if len(content) <= chunk_size:
        return [content]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for block in re.split(r"(\n\n+)", content):
        if not block:
            continue
        if current and current_len + len(block) > chunk_size:
            chunks.append("".join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += len(block)
    if current:
        chunks.append("".join(current))
    return chunks or [content]


async def token_stream_events(
    message: str,
    thread_id: str,
    mode: str = "normal",
    images: Optional[List[Dict[str, str]]] = None,
    files: Optional[List[Dict[str, str]]] = None,
    scene: str = "",
    model_id: int = None,
) -> AsyncGenerator[str, None]:
    """
    通用 SSE 流式生成器 — Hermes AIAgent 决策 + 流式推送。

    参数:
        message: 用户消息
        thread_id: 会话线程 ID（格式: {user_id}_{timestamp}）
        mode: 会话模式（透传给钩子，通用脚手架不解析此字段）
        images: 可选图片列表 [{"data_url": "data:image/png;base64,...", "mime": "image/png"}, ...]
        files: 可选文件列表 [{"filename": "xxx.md", "url": "/static/uploads/xxx.md", "content": "..."}, ...]
        scene: 场景标识（code/summary/chat 等），用于场景路由
        model_id: 用户手动指定的 model_config ID

    流程:
        1. 解析 thread_id → user_id
        2. 检查多模态支持（如有图片）
        3. 创建 Hook 上下文
        4. 执行 pre_process 钩子
        5. 入口落库（status=4）
        6. 调用 Hermes Runtime
        7. 消费 thread_queue → 推送 SSE token 事件
        8. 执行 post_process 钩子
        9. 持久化答案
        10. 发送 chat_complete 事件
    """
    from backend.controller import stream_runner  # noqa: F401 — 确保模块已加载

    # ── 解析 user_id ──
    user_id = None
    if thread_id.startswith("wx_"):
        # 微信会话：wx_{user_id}_{wx_user_id[:12]}
        parts = thread_id.split("_", 2)  # ["wx", "1", "o9cq80-..."]
        if len(parts) >= 3:
            try:
                user_id = int(parts[1])
            except (ValueError, IndexError):
                pass
    if user_id is None:
        if not thread_id or '_' not in thread_id:
            raise HTTPException(status_code=400, detail="thread_id 格式错误，应为 user_id_timestamp 格式")
        try:
            user_id = int(thread_id.split('_')[0])
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail=f"无法从 thread_id 解析 user_id: {thread_id}")

    # ── Pipeline Trace（PIPELINE_TRACE=true 时启用全链路追踪） ──
    from backend.service.pipeline_trace import PipelineTrace, _PIPELINE_TRACE_CTX, is_enabled as _pt_enabled
    _pipeline_trace: Optional[PipelineTrace] = None
    if _pt_enabled():
        _pipeline_trace = PipelineTrace(user_id=user_id, thread_id=thread_id, message=message)
        _PIPELINE_TRACE_CTX.set(_pipeline_trace)

    # ── SQL 操作审计上下文（text2sql 工具记录用，经 copy_context 继承到工具线程） ──
    try:
        from backend.service.sql_recorder import set_context as _set_sql_ctx
        _set_sql_ctx(thread_id)
    except Exception:
        pass

    # ── 内存历史管理（兜底用） ──
    is_new_conversation = thread_id not in chat_histories or len(chat_histories[thread_id]) == 0
    if is_new_conversation:
        # 尝试从数据库恢复历史（异步线程池执行，避免阻塞事件循环）
        if conversation_mapper:
            try:
                conversations = await asyncio.to_thread(_load_conversations_sync, thread_id)
                if conversations:
                    if thread_id in chat_histories:
                        chat_histories[thread_id].clear()
                    for conv in conversations:
                        user_content = str(conv.get("user_question", "")).strip()
                        assistant_content = str(conv.get("agent_answer", "")).strip()
                        if user_content:
                            chat_histories[thread_id].append({
                                "role": "user", "content": user_content,
                                "timestamp": str(conv.get("create_time", "")),
                            })
                        if assistant_content:
                            chat_histories[thread_id].append({
                                "role": "assistant", "content": assistant_content,
                                "timestamp": str(conv.get("update_time", "")),
                            })
                    if chat_histories[thread_id]:
                        is_new_conversation = False
            except Exception:
                pass

    if is_new_conversation:
        logger.debug(f"新对话 - thread_id={thread_id}")
        clear_thread_history(thread_id)

    # ── 保存用户消息到内存 ──
    save_message(thread_id, "user", message)

    # ── 创建 Hook 上下文 ──
    ctx = ChatHookContext(
        thread_id=thread_id,
        user_id=user_id,
        user_message=message,
        mode=mode,
    )

    # ── 执行 on_session_start 钩子 ──
    hooks = get_hooks()
    if hooks and hooks.on_session_start:
        try:
            result = hooks.on_session_start(ctx)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning(f"on_session_start 钩子异常: {e}")

    # ── 执行 pre_process 钩子 ──
    effective_message = message
    text_message = message  # 跟踪文本消息（用于 DB 存储）
    if hooks and hooks.pre_process:
        try:
            result = hooks.pre_process(ctx)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, ChatHookContext):
                ctx = result
                effective_message = ctx.user_message
                text_message = ctx.user_message
        except Exception as e:
            logger.warning(f"pre_process 钩子异常，使用原始消息: {e}")

    # ── 入口即落库（status=4，异步线程池执行，避免阻塞事件循环） ──
    metadata = None
    if images:
        metadata = {"images": images}
    running_conversation_id = await asyncio.to_thread(
        _insert_running_conversation_sync, thread_id, user_id, effective_message, mode, metadata
    )
    ctx.conversation_id = running_conversation_id

    # ── 自动生成会话标题（仅新会话；后台异步、失败静默） ──
    if is_new_conversation:
        try:
            from backend.service.session_title import schedule_auto_title
            schedule_auto_title(thread_id, user_id, text_message)
        except Exception:
            pass

    # ── 发送 start 事件 ──
    start_data = {"type": "start", "thread_id": thread_id}
    if running_conversation_id:
        start_data["conversation_id"] = running_conversation_id
    yield f"data: {safe_json_dumps(start_data)}\n\n"

    # ── 发送钩子自定义 SSE 事件 ──
    for event in ctx.sse_events:
        yield f"data: {safe_json_dumps(event)}\n\n"

    # ── Hermes 决策 ──
    accumulated_tokens: List[str] = []
    chat_complete_sent = False
    runtime = None
    hermes_task = None
    # ⚠️ 必须在 try 之前初始化：finally 里会用到 username，
    # 而"未配置模型"/"模型不支持图片"等提前 return 的分支根本没走到赋值那一步，
    # 裸引用会 UnboundLocalError（被 finally 的 except 吞掉 → 审计日志静默不落库）。
    username: Optional[str] = None
    # 已经作为 thinking_step 推送过的文本（用于 process_log 补发时去重）
    _emitted_thinking: List[str] = []

    try:
        logger.debug(f"[用户 {user_id}] 开始 Hermes 决策 - 消息: {effective_message[:100]}{'...' if len(effective_message) > 100 else ''}")

        # 获取模型配置和系统提示词
        from backend.controller.agent_controller import get_current_model_config
        from backend.agents.prompts import get_decision_system_prompt
        from backend.hermes_adapter import get_runtime

        model_config = get_current_model_config(user_id, scene=scene, model_id=model_id)

        # ── 记录本次选中的模型（路由决策日志） ──
        if model_config:
            _route_hint = "手动指定" if model_id else ("场景:" + scene if scene else "默认/降级链")
            logger.info(
                f"[选模型] user={user_id}, model={model_config.get('model_name')}, "
                f"config={model_config.get('config_name')}, route={_route_hint}"
            )

        # ── 模型未配置：快速降级返回 ──
        if not model_config:
            fallback_msg = "⚠️ 未配置 LLM 模型。请在 .env 文件中设置 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL，或通过系统配置页面进行配置。"
            logger.warning(f"用户 {user_id} 未配置模型，返回降级提示")
            save_message(thread_id, "assistant", fallback_msg)
            _persist_conversation_answer(running_conversation_id, thread_id, user_id, effective_message, fallback_msg)
            for chunk in _stream_text_chunks(fallback_msg):
                yield f"data: {safe_json_dumps({'type': 'token', 'content': chunk})}\n\n"
            yield f"data: {safe_json_dumps({'type': 'chat_complete', 'thread_id': thread_id, 'final_content': fallback_msg, 'timestamp': now_local_iso(), 'todos': []})}\n\n"
            limit_chat_history(thread_id, max_messages=MAX_HISTORY_MESSAGES)
            return

        # ── 多模态检查 ──
        multimodal_message = None  # 初始化，避免后续 NameError
        has_images = bool(images and len(images) > 0)
        if has_images:
            if not check_model_multimodal(model_config):
                error_msg = "⚠️ 当前模型不支持图片解析，请切换到多模态模型（如 gpt-4o、claude-3、gemini-2 等）"
                logger.warning(f"用户 {user_id} 发送了图片但模型不支持多模态: {model_config.get('model_name')}")
                save_message(thread_id, "assistant", error_msg)
                _persist_conversation_answer(running_conversation_id, thread_id, user_id, effective_message, error_msg)
                for chunk in _stream_text_chunks(error_msg):
                    yield f"data: {safe_json_dumps({'type': 'token', 'content': chunk})}\n\n"
                yield f"data: {safe_json_dumps({'type': 'chat_complete', 'thread_id': thread_id, 'final_content': error_msg, 'timestamp': now_local_iso(), 'todos': []})}\n\n"
                limit_chat_history(thread_id, max_messages=MAX_HISTORY_MESSAGES)
                return
            # 构建多模态消息：文本 + 图片（经过安全处理）
            content_blocks = [{"type": "text", "text": effective_message}]
            valid_images = []
            for img in images:
                data_url = img.get("data_url", "")
                if not data_url:
                    continue
                # 如果已经是 data URL，解析出 raw bytes 做安全检查
                if data_url.startswith("data:"):
                    try:
                        header, b64_part = data_url.split(",", 1)
                        mime = header.split(":")[1].split(";")[0] if ":" in header else ""
                        raw = base64.b64decode(b64_part)
                        safe_url, err = process_image_safe(raw, mime)
                        if err:
                            logger.warning(f"图片安全检查不通过，跳过: {err}")
                            continue
                        data_url = safe_url
                    except Exception as e:
                        logger.warning(f"图片解析失败，跳过: {e}")
                        continue
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": data_url}
                })
                valid_images.append(img)
            images = valid_images  # 替换为通过安全检查的图片列表
            # 将多模态内容作为消息（Hermes runtime 会传给 LLM）
            # 多模态 content_blocks 保留为 list 传给 Hermes（含 text + image_url）
            # 仅当有图片时才替换为 list，否则保持原始文本
            multimodal_message = content_blocks if len(content_blocks) > 1 else None
            logger.debug(f"多模态消息: 文本长度={len(message)}, 图片数={len(images)}")

        # ── 文件附件：读取内容注入 effective_message（不修改原始 message）──
        if files and len(files) > 0:
            from backend.controller.wechat.file import _read_file_content as _read_file
            file_parts = []
            for f in files:
                fname = f.get("filename") or "unknown"
                f_url = f.get("url") or ""
                f_content = f.get("content")  # 前端已经读过一遍了
                # 如果前端传来的 content 为空，后端再读一次
                if not f_content and f_url:
                    from backend.config.paths import DATA_ROOT
                    # 兼容新旧路径
                    old_path = Path(__file__).resolve().parents[2] / "data" / "uploads" / Path(f_url).name
                    new_path = DATA_ROOT / "uploads" / Path(f_url).name
                    stored_path = new_path if new_path.exists() else old_path
                    if stored_path.exists():
                        f_content = _read_file(str(stored_path))
                if f_content:
                    file_parts.append(f"【用户上传文件: {fname}】\n{f_content}")
                else:
                    file_parts.append(f"【用户上传文件: {fname}】（无法读取内容）")
            if file_parts:
                file_prefix = "\n\n".join(file_parts)
                effective_message = f"{file_prefix}\n\n用户问题: {effective_message}"
                logger.debug(f"文件内容已注入: {len(files)} 个文件, total_len={len(str(effective_message))}")

        # 查询用户可用工具，动态生成系统提示词
        from backend.permission.checker import get_user_hermes_tools
        available_tools = get_user_hermes_tools(user_id)
        
        # 获取主机白名单信息（如果用户有权限）
        host_whitelist_text = None
        try:
            from backend.service.host_whitelist_service import (
                get_user_accessible_hosts,
                format_hosts_for_prompt,
                user_has_whitelist_perm
            )
            if user_has_whitelist_perm(user_id):
                hosts = get_user_accessible_hosts(user_id)
                if hosts:
                    host_whitelist_text = format_hosts_for_prompt(hosts)
                    logger.debug(f"用户 {user_id} 有 {len(hosts)} 台白名单主机已注入系统提示词")
        except Exception as e:
            logger.warning(f"获取主机白名单失败: {e}")
        
        decision_prompt = get_decision_system_prompt(
            user_id=user_id,
            available_tools=available_tools,
            host_whitelist_text=host_whitelist_text
        )

        # 查询当前用户的 username（异步线程池执行，避免阻塞事件循环）
        username = None
        try:
            username = await asyncio.to_thread(_fetch_username_sync, user_id)
        except Exception as e:
            logger.warning(f"查询 username 失败: {e}")
        
        # 确保 username 非空，避免 ContextVar 缓存污染
        if not username:
            username = f"user_{user_id}"
            logger.warning(f"username 为空，使用 fallback: {username}")
        
        runtime = get_runtime(user_id, model_config or {}, decision_prompt, thread_id=thread_id, username=username)

        # 准备兜底 history
        history = []
        if thread_id in chat_histories and chat_histories[thread_id]:
            cached = chat_histories[thread_id]
            if cached and cached[-1].get("role") == "user" and cached[-1].get("content") == text_message:
                cached = cached[:-1]
            history = cached[-(MAX_HISTORY_MESSAGES - 1):]

        ctx.history = history
        ctx.model_config = model_config or {}
        ctx.system_prompt = decision_prompt

        import queue as _queue
        thread_queue: _queue.Queue = _queue.Queue()

        async def _run_hermes():
            return await runtime.run(
                user_message=multimodal_message if multimodal_message is not None else effective_message,
                history=history,
                thread_queue=thread_queue,
                mode=mode,
            )

        hermes_task = asyncio.create_task(_run_hermes())

        # ── 消费 thread_queue → SSE ──
        from backend.hermes_adapter import HermesStreamReset
        _sse_reset_count = 0

        # ── exec 审批卡片推送（主机白名单远程命令审批；去重） ──
        _emitted_approvals: set = set()

        while not hermes_task.done() or not thread_queue.empty():
            # 轮询待审批命令 → 推 exec_approval_request 帧给前端渲染审批卡片
            try:
                from backend.hermes_adapter import get_pending_approval as _gap
                _pa = _gap(thread_id)
                if _pa and _pa.get("approval_id") not in _emitted_approvals:
                    _emitted_approvals.add(_pa["approval_id"])
                    yield f"data: {safe_json_dumps({'type': 'exec_approval_request', 'approval_id': _pa['approval_id'], 'command': _pa.get('command', ''), 'description': _pa.get('description', '')})}\n\n"
            except Exception:
                pass
            try:
                chunk = thread_queue.get_nowait()
                if isinstance(chunk, HermesStreamReset):
                    _sse_reset_count += 1
                    # 把重置前积累的内容作为思考过程发送给前端
                    reset_content = "".join(accumulated_tokens).strip()
                    logger.debug(f"stream_reset #{_sse_reset_count}: 积累内容长度={len(reset_content)} 内容预览={reset_content[:100] if reset_content else '(空)'}")
                    if reset_content:
                        # 过滤掉占位文案（不重要的中间状态）
                        from backend.hermes_adapter import _is_placeholder_text
                        if not _is_placeholder_text(reset_content):
                            logger.debug(f"发送思考过程: {reset_content[:50]}...")
                            _emitted_thinking.append(reset_content)
                            yield f"data: {safe_json_dumps({'type': 'thinking_step', 'content': reset_content})}\n\n"
                        else:
                            logger.debug(f"跳过占位文案: {reset_content[:50]}...")
                    accumulated_tokens = []
                    yield f"data: {safe_json_dumps({'type': 'stream_reset'})}\n\n"
                    continue
                # ── P0: 预格式化 SSE 帧透传（子 Agent 委派事件等） ──
                # _push_subagent_sse 推入的是已格式化的 "data: {...}\n\n"，
                # 直接 yield 不再二次包装为 token 帧
                if isinstance(chunk, str) and chunk.startswith("data: "):
                    yield chunk
                    continue
                accumulated_tokens.append(chunk)
                yield f"data: {safe_json_dumps({'type': 'token', 'content': chunk})}\n\n"

                # 执行流式钩子
                if hooks and hooks.on_stream_chunk:
                    try:
                        result = hooks.on_stream_chunk(chunk, ctx)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass
            except _queue.Empty:
                if hermes_task.done():
                    break
                await asyncio.sleep(0.05)

        logger.debug(
            f"SSE 消费完成: {len(accumulated_tokens)} tokens / "
            f"{_sse_reset_count} 次 stream_reset"
        )

        try:
            hermes_result = await hermes_task
        except RuntimeError as e:
            err_msg = str(e)
            if "No LLM provider configured for task=vision" in err_msg:
                friendly = (
                    "⚠️ 当前模型不支持图片识别，且未配置辅助视觉模型。"
                    "请切换到支持图片的多模态模型（如 qwen-vl-max、gpt-4o、claude-3+、gemini-2+ 等）。"
                )
                logger.warning(f"视觉模型降级失败: {err_msg[:200]}")
                save_message(thread_id, "assistant", friendly)
                _persist_conversation_answer(running_conversation_id, thread_id, user_id, effective_message, friendly)
                for chunk in _stream_text_chunks(friendly):
                    yield f"data: {safe_json_dumps({'type': 'token', 'content': chunk})}\n\n"
                yield f"data: {safe_json_dumps({'type': 'chat_complete', 'thread_id': thread_id, 'final_content': friendly, 'timestamp': now_local_iso(), 'todos': []})}\n\n"
                limit_chat_history(thread_id, max_messages=MAX_HISTORY_MESSAGES)
                return
            raise
        final_output = hermes_result.get("final_response", "")

        # 检查 Hermes 是否返回了错误（与正常空回复区分）
        hermes_error = hermes_result.get("error")
        if hermes_error:
            logger.error(f"Hermes 返回错误: {hermes_error}")
            yield f"data: {safe_json_dumps({'type': 'error', 'message': hermes_error})}\n\n"
            if running_conversation_id:
                try:
                    conversation_mapper.update_conversation_answer(
                        conversation_id=running_conversation_id,
                        agent_answer=hermes_error, status=2,
                    )
                except Exception:
                    pass
            return

        if not final_output and accumulated_tokens:
            final_output = "".join(accumulated_tokens)

        # ── 提取思考过程（process_log），供钩子上报/审计用 ──
        process_log = hermes_result.get("process_log", "[]")
        ctx.metadata["process_log"] = process_log
        # 输出思考过程步骤数（调试用）
        try:
            _pl = json.loads(process_log) if isinstance(process_log, str) else process_log
            _pl_steps = len(_pl) if isinstance(_pl, list) else 0
        except Exception:
            _pl_steps = 0

        # ── 如果有思考过程但前端还没收到，现在发送 ──
        # 当没有工具调用时（没有 stream_reset），思考过程不会通过 thinking_step 发送
        # 这里补发一次，确保用户能看到 AI 的推理过程。
        # ⚠️ 有工具调用时同一条旁白已经在上面的 stream_reset 分支发过一遍，
        #    process_log 又来自同一批 assistant content → 必须去重，否则前端重复显示。
        if _pl_steps > 0:
            try:
                def _norm_thinking(_s: str) -> str:
                    return "".join(_ch for _ch in _s if not _ch.isspace())

                for note in _pl:
                    if not isinstance(note, str) or not note.strip():
                        continue
                    _n = _norm_thinking(note)
                    if any(
                        _n in _norm_thinking(_prev) or _norm_thinking(_prev) in _n
                        for _prev in _emitted_thinking
                    ):
                        continue  # 已作为 thinking_step 推送过
                    _emitted_thinking.append(note)
                    yield f"data: {safe_json_dumps({'type': 'thinking_step', 'content': note.strip()})}\n\n"
            except Exception:
                pass

        logger.info(
            f"Hermes 决策完成 - 输出长度={len(final_output)}, "
            f"流式token数={len(accumulated_tokens)}, "
            f"process_log步骤={_pl_steps}"
        )

        # ── 执行 post_process 钩子 ──
        if hooks and hooks.post_process and final_output:
            try:
                result = hooks.post_process(ctx, final_output)
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, str):
                    final_output = result
            except Exception as e:
                logger.warning(f"post_process 钩子异常: {e}")

        # ── 保存到内存历史 ──
        if final_output:
            save_message(thread_id, "assistant", final_output)

        # ── 执行 on_complete 钩子 ──
        if hooks and hooks.on_complete and final_output:
            try:
                result = hooks.on_complete(ctx, final_output)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"on_complete 钩子异常: {e}")

        # ── 持久化答案（异步线程池执行，避免阻塞事件循环） ──
        if final_output:
            conversation_id = await asyncio.to_thread(
                _persist_conversation_answer_sync,
                running_conversation_id, thread_id, user_id, text_message, final_output,
            )

            # ── 同步用户问题和 AI 回复到 trace 记录 ──
            try:
                from backend.service.trace.trace_service import sync_trace_texts
                sync_trace_texts(thread_id, text_message, final_output)
            except Exception:
                pass

            # ── 解析 LLM 回答中的记忆引用 ──
            memory_citations = []
            try:
                refs_map = (hermes_result or {}).get("_memory_refs", {})
                if refs_map:
                    # 提取回答中的 [M1]、[M2] 等引用标签（去重保序）
                    cited_tags = re.findall(r'\[M(\d+)\]', final_output)
                    for tag_num in dict.fromkeys(cited_tags):
                        tag = f"M{tag_num}"
                        if tag in refs_map:
                            memory_citations.append(refs_map[tag])
            except Exception:
                pass

            # ── 发送 chat_complete ──
            completion_data = {
                "type": "chat_complete",
                "thread_id": thread_id,
                "final_content": final_output,
                "timestamp": now_local_iso(),
                "todos": [],
                "has_attachments": False,
                "process_log": process_log,
                "memory_citations": memory_citations,
            }
            if conversation_id:
                completion_data["conversation_id"] = conversation_id

            chat_complete_sent = True
            completed_threads.add(thread_id)
            if len(completed_threads) > 10000:
                # 保留最近的一半，清除较早的条目
                to_remove = list(completed_threads)[:5000]
                for item in to_remove:
                    completed_threads.discard(item)
            mark_completed_time(thread_id)
            yield f"data: {safe_json_dumps(completion_data)}\n\n"
            yield "retry: 86400000\n\n"  # 压制浏览器 EventSource EOF 自动重连

            limit_chat_history(thread_id, max_messages=MAX_HISTORY_MESSAGES)

        elif not final_output:
            logger.warning(f"Hermes 输出为空 - thread_id={thread_id}")

    except asyncio.CancelledError:
        logger.warning(f"流式请求被取消 - thread_id={thread_id}")
        if runtime is not None:
            try:
                runtime.cancel()
            except Exception as exc:
                logger.warning(f"取消时通知 Hermes 失败: {exc}")
        if hermes_task is not None and not hermes_task.done():
            hermes_task.cancel()
            try:
                await asyncio.sleep(0)  # 让事件循环处理取消请求
            except Exception:
                pass
        # 保存半截内容
        if running_conversation_id and accumulated_tokens and not chat_complete_sent:
            partial = "".join(accumulated_tokens)
            try:
                conversation_mapper.update_conversation_answer(
                    conversation_id=running_conversation_id,
                    agent_answer=partial, status=3,
                )
            except Exception:
                pass
        yield f"data: {safe_json_dumps({'type': 'error', 'message': '客户端断开连接'})}\n\n"

    except HTTPException:
        # FastAPI HTTP 异常向上传播，不做额外处理
        raise

    except ConnectionError as e:
        # 连接相关异常（数据库/网络）- 记录详细日志
        import traceback
        logger.error(f"流式处理连接错误: {e}\n{traceback.format_exc()}")
        _mark_conversation_failed(running_conversation_id)
        if hooks and hooks.on_error:
            try:
                result = hooks.on_error(e, ctx)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass
        yield f"data: {safe_json_dumps({'type': 'error', 'message': '连接错误，请稍后重试'})}\n\n"

    except MemoryError as e:
        # 内存不足 - 致命错误，记录并向上传播
        logger.critical(f"内存不足: {e}")
        _mark_conversation_failed(running_conversation_id)
        raise  # 致命错误向上传播

    except Exception as e:
        # 其他异常 - 记录详细日志
        import traceback
        error_type = type(e).__name__
        logger.error(f"流式处理错误 [{error_type}]: {e}\n{traceback.format_exc()}")
        _mark_conversation_failed(running_conversation_id)
        # 执行错误钩子
        if hooks and hooks.on_error:
            try:
                result = hooks.on_error(e, ctx)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass
        # 返回用户友好的错误消息
        yield f"data: {safe_json_dumps({'type': 'error', 'message': f'处理出错: {error_type}'})}\n\n"

    finally:
        # ── exec 审批记录落库（审计，异步线程池执行，避免阻塞事件循环） ──
        # 使用 asyncio.shield 保护 await 操作，防止 CancelledError 导致数据丢失
        # CancelledError 在 Python 3.8+ 继承 BaseException，except Exception 拦不住
        try:
            from backend.utils.exec_approval_recorder import drain as _drain_approvals
            _approvals = _drain_approvals(thread_id)
            if _approvals:
                try:
                    count = await asyncio.shield(
                        asyncio.to_thread(_flush_audit_sync, thread_id, user_id, _approvals)
                    )
                    logger.info(f"exec 审批记录已落库: {count} 条 (thread={thread_id})")
                except asyncio.CancelledError:
                    # shield 内部完成后再取消，忽略
                    pass
        except Exception:
            pass
        # ── AI 操作审计日志落库：drain 内存缓冲 → agent_operation_logs ──
        try:
            from backend.service.agent_operation_log_service import flush_to_db as _flush_ops
            _flush_ops(thread_id, user_id=user_id, username=username or "")
        except Exception:
            pass
        # ── SQL 操作审计落库：drain 内存缓冲 → sql_operation_logs ──
        try:
            from backend.service.sql_recorder import flush_to_db as _flush_sql
            _flush_sql(thread_id, user_id=user_id, username=username or "")
        except Exception:
            pass
        from backend.tools.tools_decorator import _clear_todo_list
        try:
            _clear_todo_list(thread_id)
        except Exception:
            pass
        # ── Pipeline Trace 输出（无论成功/取消/异常，都 flush 已收集的链路数据） ──
        try:
            if _pipeline_trace is not None:
                _pipeline_trace.flush()
        except Exception:
            pass
