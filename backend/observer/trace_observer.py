"""
LLM 链路可观测性 — TraceObserver

注册到 Hermes 全局 PluginManager 的生命周期钩子，
采集每次 LLM API 调用和工具调用的数据写入 MySQL。
不修改 Hermes 代码，完全在 AgentForge 层实现。

注册方式:
    register_trace_hooks(user_id)
    → 将 TraceObserver 的 4 个方法追加到全局 _hooks 字典

改进：
    - pending 字典添加过期清理，防止长时间运行内存泄漏
"""
import time as _time
import threading
from typing import Any, Dict
from backend.utils.log_utils import log
from backend.utils.llm_usage import note_api_request, trace_usage

logger = log

# ── pending 记录过期时间 ──
_PENDING_TTL = 300  # 5 分钟后自动清理未完成的 pending 记录


def _detect_source_override() -> str:
    """区分父/子 Agent 的 LLM 调用来源（C1）。

    子 Agent 的 LLM 调用走同一套全局钩子（conversation_loop 的 pre/post_api_request），
    此前 trace 里父子混在一起、无法归因。Hermes 的 delegation_context 在子 Agent 的
    执行线程里为 True（由 delegate_tool 的 delegated_child_context() 设置，随
    ContextVar 传播下去），用它打标。
    取不到时返回空串 = 走原有会话来源判定，行为不变。
    """
    try:
        from agent.delegation_context import is_delegated_child_context

        if is_delegated_child_context():
            return "subagent"
    except Exception:
        pass
    return ""


class TraceObserver:
    """LLM 链路可观测性采集器 — 全局单例，按 session_id 反查 user_id"""

    def __init__(self):
        # 不再绑定单一 user_id，改为按 session_id 动态反查
        # api_request_id → {"trace_id": int, "session_id": str, "created_at": float}
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._completed: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _lookup_user_id(self, session_id: str) -> int:
        """按 session_id 反查真实 user_id。
        
        对于 aux_* 开头的辅助 session（如 aux_rag、aux_graphrag），
        尝试从 ContextVar 获取当前用户，否则返回 0。
        """
        if not session_id:
            return 0
        
        # 辅助 session：尝试从上下文获取 user_id
        if session_id.startswith("aux_"):
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                ctx_uid = _CURRENT_USER_ID_CTX.get()
                if ctx_uid:
                    return int(ctx_uid)
            except Exception:
                pass
            return 0  # 辅助 session 且无上下文 → 返回 0（这些是系统级调用）
        
        # 正常会话：查 conversations 表
        try:
            from backend.db.connection_pool import get_pool_connection
            conn = get_pool_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT user_id FROM conversations WHERE session_id = %s LIMIT 1",
                    (session_id,),
                )
                row = cur.fetchone()
                if row:
                    return row.get("user_id", 0) or 0
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[TraceObserver] 反查 user_id 失败 (session_id={session_id}): {e}")
        return 0  # 查不到时返回 0

    def _cleanup_expired_pending(self) -> None:
        """清理过期的 pending 记录（防止 API 请求异常终止时残留）。"""
        now = _time.time()
        with self._lock:
            expired = [request_id for request_id, data in self._pending.items()
                       if now - data.get("created_at", 0) > _PENDING_TTL]
            for request_id in expired:
                self._pending.pop(request_id, None)
            self._completed = {key: value for key, value in self._completed.items()
                               if now - value.get("completed_at", 0) <= _PENDING_TTL}
        if expired:
            logger.info(
                f"[TraceObserver] 清理 {len(expired)} 条过期 pending 记录"
            )

    def on_pre_api_request(self, **kwargs) -> None:
        """LLM API 调用前 → 创建 trace 记录"""
        try:
            # 清理过期记录
            self._cleanup_expired_pending()

            from backend.service.trace.trace_service import record_trace, is_detail_enabled

            session_id = kwargs.get("session_id", "")
            api_request_id = kwargs.get("api_request_id", "")
            model = kwargs.get("model", "")
            provider = kwargs.get("provider", "") or ""
            note_api_request(session_id, api_request_id)
            approx_input = kwargs.get("approx_input_tokens", 0) or 0

            # 全量模式下提取 prompt 文本
            prompt_text = ""
            if is_detail_enabled():
                msgs = kwargs.get("request_messages") or []
                if msgs:
                    import json
                    prompt_text = json.dumps(msgs, ensure_ascii=False)

            # 按 session_id 反查真实 user_id（租户隔离）
            user_id = self._lookup_user_id(session_id)

            trace_id = record_trace(
                session_id=session_id,
                user_id=user_id,
                api_request_id=api_request_id,
                model=model,
                provider=provider,
                approx_input_tokens=approx_input,
                prompt_text=prompt_text,
                source_override=_detect_source_override(),
            )

            if trace_id and api_request_id:
                with self._lock:
                    self._pending[api_request_id] = {
                        "trace_id": trace_id, "session_id": session_id,
                        "model": model, "created_at": _time.time(),
                    }

            logger.debug(
                f"[TraceObserver] pre_api_request: {api_request_id} → trace_id={trace_id}"
            )
        except Exception as e:
            logger.warning(f"[TraceObserver] on_pre_api_request 异常: {e}")

    def on_post_api_request(self, **kwargs) -> None:
        """LLM API 调用后 → 更新 trace（token/延迟/费用）"""
        try:
            from backend.service.trace.trace_service import update_trace, is_detail_enabled

            api_request_id = kwargs.get("api_request_id", "")
            if not api_request_id:
                return

            # Hermes 传入的是「单次 API 响应的 usage」（_usage_summary_for_api_request_hook
            # 基于 response.usage 归一化），不是会话累计值——直接落库，不做差值。
            # 每条 trace 记录该次 API 调用的完整 token 分解，累计统计由 update_trace
            # 内部的 user_token_stats / daily_user_stats 累加完成。
            usage = trace_usage(kwargs.get("usage"))
            api_duration = kwargs.get("api_duration", 0) or 0

            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            cache_read_tokens = usage["cache_read_tokens"]
            cache_write_tokens = usage["cache_write_tokens"]
            reasoning_tokens = usage["reasoning_tokens"]
            total_tokens = usage["total_tokens"]

            # 费用估算（如果 Hermes 已计算）
            cost = kwargs.get("estimated_cost_usd")
            if kwargs.get("cost_status") in {"unknown", "unavailable", "not_available"}:
                cost = None

            # completion 文本（全量模式）
            completion_text = ""
            if is_detail_enabled():
                resp = kwargs.get("response") or {}
                choices = resp.get("choices") or []
                if choices:
                    msg = choices[0].get("message") or {}
                    completion_text = msg.get("content", "") or ""

            update_trace(
                api_request_id=api_request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
                reasoning_tokens=reasoning_tokens,
                total_tokens=total_tokens,
                latency_ms=int(api_duration * 1000),
                estimated_cost_usd=float(cost) if cost is not None else None,
                finish_reason=kwargs.get("finish_reason", "") or "",
                api_call_count=kwargs.get("api_call_count", 0) or 0,
                completion_text=completion_text,
            )

            # 清理 pending（并向 LLM 网关上报告成功，用于熔断器恢复）
            with self._lock:
                pending = self._pending.pop(api_request_id, None)
                if pending:
                    self._completed[api_request_id] = {**pending, "completed_at": _time.time()}
                    while len(self._completed) > 10000:
                        self._completed.pop(next(iter(self._completed)))
            model = (kwargs.get("model") or "").strip() or ((pending or {}).get("model") or "")
            if model:
                try:
                    from backend.service.llm_gateway import gateway
                    gateway.report_success(model)
                except Exception:
                    pass

            logger.debug(
                f"[TraceObserver] post_api_request: {api_request_id} "
                f"latency={api_duration:.1f}s tokens={total_tokens}"
            )
        except Exception as e:
            logger.warning(f"[TraceObserver] on_post_api_request 异常: {e}")

    def on_api_request_error(self, **kwargs) -> None:
        """API 调用失败 → 标记 trace 失败"""
        try:
            from backend.service.trace.trace_service import mark_trace_error

            api_request_id = kwargs.get("api_request_id", "")
            if not api_request_id:
                return

            error = kwargs.get("error", "")
            error_msg = str(error)[:500] if error else "unknown error"
            mark_trace_error(api_request_id, error_msg)

            with self._lock:
                pending = self._pending.pop(api_request_id, None)
            model = (kwargs.get("model") or "").strip() or ((pending or {}).get("model") or "")
            if model:
                try:
                    from backend.service.llm_gateway import gateway
                    gateway.report_failure(model)
                except Exception:
                    pass
            logger.warning(
                f"[TraceObserver] api_request_error: {api_request_id} → {error_msg}"
            )
        except Exception as e:
            logger.warning(f"[TraceObserver] on_api_request_error 异常: {e}")

    def on_post_tool_call(self, **kwargs) -> None:
        """工具调用完成 → 创建 trace_span + 写入操作审计日志"""
        try:
            from backend.service.trace import trace_service

            tool_name = (
                kwargs.get("tool_name", "")
                or kwargs.get("name", "")
                or "unknown"
            )
            duration_ms = kwargs.get("duration_ms", 0) or 0
            success = kwargs.get("success", True)
            error = kwargs.get("error", "") or ""

            # 定位本次工具调用所属的 trace。
            # ⚠️ 本 observer 是**全局单例**，`_pending` 跨所有用户共享，所以
            # 不能只取"最后一个 pending" —— 那会把 A 的工具 span 挂到 B 正在飞的
            # trace 上（跨租户观测污染）。按优先级三级定位：
            #   1) Hermes 传来的 api_request_id → 精确匹配，最可靠
            #   2) session_id → 把搜索范围收窄到本会话
            #   3) 归属缺失或不唯一 → 不记录，禁止全局最近一次兜底。
            api_request_id = kwargs.get("api_request_id", "") or ""
            trace_id = 0
            if api_request_id:
                with self._lock:
                    pending = self._pending.get(api_request_id) or self._completed.get(api_request_id)
                if pending:
                    trace_id = pending.get("trace_id", 0)
            elif kwargs.get("session_id"):
                trace_id = self._find_current_trace(session_id=kwargs.get("session_id", "") or "")
            if not trace_id:
                return

            trace_service.record_span(
                trace_id=trace_id,
                tool_name=tool_name,
                duration_ms=int(duration_ms),
                status=1 if success else 0,
                error_message=str(error)[:500] if error else "",
            )

            logger.debug(
                f"[TraceObserver] post_tool_call: {tool_name} {duration_ms}ms"
            )
        except Exception as e:
            logger.warning(f"[TraceObserver] on_post_tool_call 异常: {e}")

    def _find_current_trace(self, session_id: str = "") -> int:
        """获取当前 pending 中最新的 trace_id。

        ⚠️ 全局单例下 `_pending` 跨所有用户共享，本方法只是**兜底**：
        只取"最后一个 pending"会让 A 的工具 span 挂到 B 的 trace 上。
        调用方应优先用 Hermes 传入的 `api_request_id` 精确定位；
        退而求其次也要传 `session_id` 收窄范围。传了 `session_id` 但一条都没
        匹配上时返回 0（**fail-closed，不外溢到别人的 trace**）。
        """
        if not session_id:
            return 0
        with self._lock:
            items = list(self._pending.values()) + list(self._completed.values())
        scoped = [value for value in items if value.get("session_id") == session_id]
        return scoped[0].get("trace_id", 0) if len(scoped) == 1 else 0

    def _find_current_session_id(self) -> str:
        """获取当前 pending 中最新的 session_id"""
        return ""  # A global newest session is not a safe ownership signal.


# ════════════════════════════════════════════════════════════
# 注册入口
# ════════════════════════════════════════════════════════════

_global_observer: TraceObserver = None
_global_registered: bool = False


def register_trace_hooks(user_id: int = None) -> TraceObserver:
    """注册全局单例 TraceObserver 到 Hermes 全局钩子。

    参数 user_id 已废弃（保留向后兼容），实际 user_id 按 session_id 动态反查。
    幂等：只注册一次，多次调用返回同一实例。
    返回 TraceObserver 实例。
    """
    global _global_observer, _global_registered

    if _global_registered and _global_observer:
        return _global_observer

    observer = TraceObserver()

    try:
        from hermes_cli.plugins import get_plugin_manager
        pm = get_plugin_manager()

        pm._hooks.setdefault("pre_api_request", []).append(observer.on_pre_api_request)
        pm._hooks.setdefault("post_api_request", []).append(observer.on_post_api_request)
        pm._hooks.setdefault("api_request_error", []).append(observer.on_api_request_error)
        pm._hooks.setdefault("post_tool_call", []).append(observer.on_post_tool_call)

        _global_observer = observer
        _global_registered = True
        logger.info("✅ [TraceObserver] 全局单例已注册")
    except Exception as e:
        logger.warning(f"⚠️ [TraceObserver] 注册失败: {e}")

    return observer
