"""
TracedLLMClient — 带 trace 的轻量 LLM 客户端

替代 LangChain ChatOpenAI 直连调用，自动记录 token 用量、延迟、模型名到 traces 表。

使用方式：
    from backend.utils.traced_llm import traced_llm

    resp = traced_llm.invoke(
        messages=[{"role": "user", "content": prompt}],
        scene="memory_extract",
        user_id=1,
        source="memory",
    )
    print(resp.content)
    print(resp.usage)  # {"input_tokens": ..., "output_tokens": ..., "total_tokens": ...}
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.utils.log_utils import log
from backend.utils.token_counter import count_messages_tokens
from backend.utils.llm_usage import current_trace_context, trace_usage

logger = log


@dataclass
class TracedResponse:
    """LLM 调用结果 + trace 信息。"""
    content: str = ""
    usage: Dict[str, Any] = field(default_factory=lambda: trace_usage(None))
    model: str = ""
    latency_ms: int = 0
    trace_id: int = 0
    finish_reason: str = ""
    is_error: bool = False  # True 表示 LLM API 调用失败（如 429/500），content 为空不代表失败
    correlation: Dict[str, str] = field(default_factory=dict)

    # 兼容 LangChain 的 .content 属性
    @property
    def text(self) -> str:
        return self.content


class TracedLLMClient:
    """带 trace 的轻量 LLM 客户端。

    直接用 openai SDK 调用 API，前后用 trace_service 记录。
    通过 ModelRouter 做场景路由 + api_key 解密。
    """

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        *,
        scene: str = "",
        user_id: int = 0,
        source: str = "",
        temperature: float = 0,
        max_tokens: int = 1024,
        response_format: Optional[Dict] = None,
        timeout: float = 60,
        model_override: Optional[Dict[str, str]] = None,
    ) -> TracedResponse:
        """发送 LLM 请求并自动记录 trace。

        Args:
            messages: OpenAI 格式消息列表
            scene: 场景路由 key（如 memory_extract, rag_rewrite）
            user_id: 用户 ID（传 0 时尝试从 ContextVar 获取）
            source: 来源标识（显示在 trace 面板）
            temperature: 采样温度
            max_tokens: 最大输出 token
            response_format: 响应格式（如 {"type": "json_object"}）
            timeout: 超时秒数
            model_override: 绕过 ModelRouter，直接使用指定的模型配置。
                格式: {"api_url": ..., "api_key": ..., "model_name": ..., "provider": ...}
                用于评测服务等需要测试特定模型配置的场景。

        Returns:
            TracedResponse(content, usage, model, latency_ms, trace_id, is_error)
            is_error=True 表示 LLM API 调用失败（429/500/配置缺失等），content 为空。
            is_error=False 表示调用成功，content 为模型返回的文本（可能为空字符串）。
        """
        from backend.service.trace.write import record_trace, update_trace, mark_trace_error

        # ── 0. 尝试从 ContextVar 获取 user_id ──
        # 如果调用方传了 user_id=0，尝试从当前上下文获取真实 user_id
        # 这对于辅助 LLM 调用（RAG、GraphRAG、Memory）很重要
        if user_id == 0:
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                ctx_uid = _CURRENT_USER_ID_CTX.get()
                if ctx_uid:
                    user_id = int(ctx_uid)
            except Exception:
                pass  # ContextVar 不可用时保持 user_id=0

        # ── 1. 场景路由选模型（或使用覆盖配置）──
        # 必须把 user_id 传给 select_model：否则会走"系统默认配置"分支，
        # 享受不到按用户过滤（用户自己的模型配置不生效）。
        if model_override:
            config = dict(model_override)
        else:
            from backend.service.model_router import router as model_router
            config = model_router.select_model(scene=scene, user_id=user_id) if scene else model_router.select_model(user_id=user_id)
        if not config:
            logger.warning(f"[TracedLLM] 无可用模型配置 (scene={scene}, user_id={user_id})")
            return TracedResponse(content="", model="", latency_ms=0, is_error=True)

        api_url = (config.get("api_url") or "").rstrip("/")
        api_key = config.get("api_key") or ""
        model_name = (config.get("model_name") or "").strip()
        # 清理模型名中可能的 extra 信息
        if "[" in model_name:
            model_name = model_name.split("[")[0].strip()

        if not api_url or not api_key:
            logger.warning(f"[TracedLLM] 模型配置不完整: url={bool(api_url)}, key={bool(api_key)}")
            return TracedResponse(content="", model=model_name, latency_ms=0, is_error=True)

        # ── 2. 生成唯一请求 ID + 估算输入 token ──
        correlation = current_trace_context() or {}
        run_id = correlation.get("run_id", uuid.uuid4().hex)
        api_request_id = f"traced_{run_id}_{uuid.uuid4().hex[:12]}"
        approx_input = count_messages_tokens(messages)

        # 构造 session_id（用 source 标识，便于区分）
        session_id = correlation.get("session_id") or f"aux_{source or 'unknown'}_{run_id}"

        # ── 3. 记录 trace（pre）──
        trace_id = 0
        try:
            trace_id = record_trace(
                session_id=session_id,
                user_id=user_id,
                api_request_id=api_request_id,
                model=model_name,
                provider=config.get("provider", ""),
                approx_input_tokens=approx_input,
                source_override=source,
            )
        except Exception as e:
            logger.debug(f"[TracedLLM] record_trace 失败（不影响调用）: {e}")

        # ── 4. 调用 LLM API ──
        start = time.time()
        client = None
        try:
            from openai import OpenAI

            client = OpenAI(base_url=api_url, api_key=api_key, timeout=timeout, max_retries=0)

            kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = client.chat.completions.create(**kwargs)
            latency_ms = int((time.time() - start) * 1000)

            # ── 5. 提取结果 ──
            content = ""
            finish_reason = ""
            if response.choices:
                content = response.choices[0].message.content or ""
                finish_reason = response.choices[0].finish_reason or ""

            usage_data = trace_usage(response.usage)

            actual_model = response.model or model_name

            # ── 6. 更新 trace（post）──
            if trace_id:
                try:
                    update_trace(
                        api_request_id=api_request_id,
                        input_tokens=usage_data["input_tokens"],
                        output_tokens=usage_data["output_tokens"],
                        cache_read_tokens=usage_data["cache_read_tokens"],
                        cache_write_tokens=usage_data["cache_write_tokens"],
                        reasoning_tokens=usage_data["reasoning_tokens"],
                        total_tokens=usage_data["total_tokens"],
                        estimated_cost_usd=None,
                        latency_ms=latency_ms,
                        finish_reason=finish_reason,
                        api_call_count=1,
                    )
                except Exception as e:
                    logger.debug(f"[TracedLLM] update_trace 失败: {e}")

            # 上报熔断器成功
            try:
                from backend.service.llm_gateway import gateway
                gateway.report_success(model_name)
            except Exception as e:
                logger.debug(f"[TracedLLM] 熔断器上报失败: {e}")

            # 获取场景中文名
            scene_label = source
            try:
                from backend.service.scene_registry import scenes
                if scene:
                    scene_def = scenes.get(scene)
                    if scene_def:
                        scene_label = f"{source}({scene_def.name})"
            except Exception:
                pass

            logger.info(
                f"[TracedLLM] {scene_label} | model={actual_model} | "
                f"tokens={usage_data.get('total_tokens', '?')} | "
                f"latency={latency_ms}ms"
            )

            return TracedResponse(
                content=content,
                usage=usage_data,
                model=actual_model,
                latency_ms=latency_ms,
                trace_id=trace_id,
                finish_reason=finish_reason,
                correlation={**correlation, "run_id": run_id, "api_request_id": api_request_id},
            )

        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            error_msg = str(e)[:500]

            # 记录错误 trace
            if trace_id:
                try:
                    mark_trace_error(api_request_id, error_msg)
                except Exception as te:
                    logger.debug(f"[TracedLLM] mark_trace_error 失败: {te}")

            # 上报熔断器
            try:
                from backend.service.llm_gateway import gateway
                gateway.report_failure(model_name)
            except Exception as ge:
                logger.debug(f"[TracedLLM] 熔断器上报失败: {ge}")

            # 获取场景中文名
            scene_label = source
            try:
                from backend.service.scene_registry import scenes
                if scene:
                    scene_def = scenes.get(scene)
                    if scene_def:
                        scene_label = f"{source}({scene_def.name})"
            except Exception:
                pass

            logger.warning(
                f"[TracedLLM] {scene_label} 调用失败 | model={model_name} | "
                f"latency={latency_ms}ms | error={error_msg}"
            )
            return TracedResponse(
                content="",
                model=model_name,
                latency_ms=latency_ms,
                trace_id=trace_id,
                is_error=True,
                correlation={**correlation, "run_id": run_id, "api_request_id": api_request_id},
            )
        finally:
            if client is not None:
                close = getattr(client, "close", None)
                if close is not None:
                    try:
                        close()
                    except Exception:
                        logger.debug("[TracedLLM] client close failed")


# 全局单例，供各模块直接 import 使用
traced_llm = TracedLLMClient()
