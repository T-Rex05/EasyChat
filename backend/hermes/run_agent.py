#!/usr/bin/env python3
"""
Hermes AI Agent 运行器

提供工具调用能力的 AI Agent 核心，负责对话循环、工具执行和响应管理。

使用示例:
    from run_agent import AIAgent
    agent = AIAgent(base_url="http://localhost:30000/v1", model="claude-opus-4-20250514")
    response = agent.run_conversation("你好，介绍一下 Python 最新特性")
"""

# 重要：hermes_bootstrap 必须是最先导入的模块 —— 修复 Windows UTF-8 标准 I/O 编码。
# POSIX 上为空操作。详见 hermes_bootstrap.py 中的说明。
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    # 优雅降级：部分更新导致 hermes_bootstrap 未注册时跳过。
    # 缺少 bootstrap 意味着 Windows 上 UTF-8 标准 I/O 设置被跳过，POSIX 不受影响。
    pass

import asyncio
import base64
import copy
import hashlib
import json
import logging
logger = logging.getLogger(__name__)
import os
import re
import sys
import tempfile
import time
import threading
import uuid
from typing import List, Dict, Any, Optional, Callable
# 注意：`from openai import OpenAI` 有意不在模块顶层导入 —— SDK 导入耗时约 240ms。
# OpenAI 作为轻量代理对象暴露，在首次调用/类型检查时才真正加载 SDK，同时保持：
#   (a) _create_openai_client 中的 `OpenAI(**client_kwargs)` 调用点不变
#   (b) ~28 个测试文件使用的 `patch("run_agent.OpenAI", ...)` 模式不受影响
#
# 注意：`fire` 仅在 `__main__` 块中用于 CLI 模式，不作为库依赖放在模块顶层导入。
# 这样在守护线程中 import run_agent 时，即使 fire 未安装也不会报错。
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from hermes_constants import get_hermes_home


def _launch_cwd_for_session(source: str) -> Optional[str]:
    """获取新会话记录的工作目录，不可用时返回 None。

    仅本地 CLI 会话会记录 cwd：`hermes -c`/`--resume` 需要恢复启动目录。
    Gateway/cron/远程后端会话没有稳定的宿主机 cwd 可恢复，故不记录。

    TERMINAL_ENV 由 CLI 配置桥（load_cli_config）设置；非 "local" 后端
    （docker/ssh/modal 等）意味着宿主机 cwd 对 Agent 工具无意义，同样跳过。
    """
    if source != "cli":
        return None
    backend = (os.environ.get("TERMINAL_ENV") or "local").strip().lower()
    if backend and backend != "local":
        return None
    try:
        return os.getcwd()
    except OSError:
        # cwd 已被删除 —— 无有效信息可记录
        return None


def _session_source_for_agent(platform: Optional[str]) -> str:
    try:
        from gateway.session_context import get_session_env

        source = get_session_env("HERMES_SESSION_SOURCE", "")
    except Exception:
        source = os.environ.get("HERMES_SESSION_SOURCE", "")
    source = str(source or "").strip()
    if source:
        return source
    return platform or "cli"


# OpenAI 懒惰代理 + 安全标准 I/O + 代理 URL 辅助函数（见 agent/process_bootstrap.py）
# OpenAI 在此重导出以使 `patch("run_agent.OpenAI", ...)` 测试模式正常工作。
# 以下 `# noqa: F401` 重导出覆盖了通过 mock.patch、`from run_agent import <X>`
# 或 agent/system_prompt.py 的 `_ra().<X>` 间接访问的符号 —— 这些使用方式 ruff 无法检测到。
from agent.process_bootstrap import (
    OpenAI,  # noqa: F401  # 重导出供测试用
    _SafeWriter,  # noqa: F401  # 重导出供测试用
    _get_proxy_for_base_url,
)
from agent.iteration_budget import IterationBudget


from hermes_cli.env_loader import load_hermes_dotenv
from hermes_cli.timeouts import (
    get_provider_request_timeout,
    get_provider_stale_timeout,
)

_hermes_home = get_hermes_home()
_project_env = Path(__file__).parent / '.env'
_loaded_env_paths = load_hermes_dotenv(hermes_home=_hermes_home, project_env=_project_env)
if _loaded_env_paths:
    for _env_path in _loaded_env_paths:
        logger.info("Loaded environment variables from %s", _env_path)
else:
    logger.info("No .env file found. Using system environment variables.")


from model_tools import (
    get_tool_definitions,  # noqa: F401  # 重导出供测试用
    get_toolset_for_tool,
    handle_function_call,  # noqa: F401  # 重导出供测试用
    check_toolset_requirements,  # noqa: F401  # 重导出供测试用
)
from tools.terminal_tool import cleanup_vm, get_active_env
from tools.interrupt import set_interrupt as _set_interrupt
from tools.browser_tool import cleanup_browser


# Agent 内部模块（已抽取到 agent/ 包以提高模块化）
from agent.memory_manager import sanitize_context
from agent.error_classifier import FailoverReason
from agent.redact import redact_sensitive_text
from agent.message_content import flatten_message_text
from agent.model_metadata import (
    estimate_request_tokens_rough,  # noqa: F401  # 重导出供测试用
    is_local_endpoint,
)
from agent.usage_pricing import normalize_usage
from agent.context_compressor import (  # noqa: F401  # 重导出供测试用
    COMPRESSED_SUMMARY_METADATA_KEY,
    ContextCompressor,
)
from agent.retry_utils import jittered_backoff  # noqa: F401  # 重导出供测试用
from agent.prompt_builder import (  # noqa: F401  # 重导出供测试用
    DEFAULT_AGENT_IDENTITY,
    build_skills_system_prompt,
    build_context_files_prompt,
    build_environment_hints,
    build_nous_subscription_prompt,
    load_soul_md,
)
from agent.process_bootstrap import _get_proxy_from_env  # noqa: F401  # 重导出供测试用
from agent.message_sanitization import (  # noqa: F401  # 重导出供测试用
    _SURROGATE_RE,
    _sanitize_surrogates,
    _sanitize_structure_surrogates,
    _sanitize_messages_surrogates,
    _escape_invalid_chars_in_json_strings,
    _repair_tool_call_arguments,
    _strip_non_ascii,
    _sanitize_messages_non_ascii,
    _sanitize_tools_non_ascii,
    _strip_images_from_messages,
    _sanitize_structure_non_ascii,
)
from agent.codex_responses_adapter import (
    _derive_responses_function_call_id as _codex_derive_responses_function_call_id,
    _deterministic_call_id as _codex_deterministic_call_id,
    _split_responses_tool_id as _codex_split_responses_tool_id,
    _summarize_user_message_for_log,  # 也被 _sync_external_memory_for_turn 使用（记忆边界）
)
from agent.tool_guardrails import (
    ToolGuardrailDecision,
    append_toolguard_guidance,
    toolguard_synthetic_result,
)
from agent.tool_result_classification import (
    FILE_MUTATING_TOOL_NAMES as _FILE_MUTATING_TOOLS,
    file_mutation_result_landed,
)
from agent.trajectory import (
    convert_scratchpad_to_think,
    save_trajectory as _save_trajectory_to_file,
)
from agent.tool_dispatch_helpers import (
    _should_parallelize_tool_batch,  # noqa: F401  # 重导出供测试用
    _is_destructive_command,  # noqa: F401  # 重导出供测试用
    _extract_parallel_scope_path,  # noqa: F401  # 重导出供测试用
    _paths_overlap,  # noqa: F401  # 重导出供测试用
    _is_multimodal_tool_result,
    _multimodal_text_summary,
    _append_subdir_hint_to_multimodal,  # noqa: F401  # 重导出供测试用
    _extract_file_mutation_targets,
    _extract_landed_file_mutation_paths,
    _extract_error_preview,
    _trajectory_normalize_msg,  # noqa: F401  # 重导出供测试用
)
from utils import atomic_json_write, base_url_host_matches, base_url_hostname, env_float, is_truthy_value, model_forces_max_completion_tokens


# 标记消息为临时恢复脚手架的标志位集合。这些合成消息（如空回复后的 "(empty)" 占位、
# thinking-only 预填充等）仅用于驱动下一次 API 重试，内存循环在附加真实回复前会弹出它们。
# 持久化层必须同步处理，否则追加式刷盘会将这些临时消息写入会话存储，
# 导致恢复会话时重放这些合成消息，污染上下文。
_EPHEMERAL_SCAFFOLDING_FLAGS = (
    "_empty_recovery_synthetic",
    "_empty_terminal_sentinel",
    "_thinking_prefill",
    # verify-on-stop 和 pre_verify 的合成用户催促消息，用于在 Agent 声明完成前
    # 再推一轮验证循环。持久化它们会污染恢复的转录并破坏 prompt-prefix 缓存复用。
    # assistant 候选消息不是合成的 —— 它会被持久化并作为中间消息发送 (#65919)。
    "_verification_stop_synthetic",
    "_pre_verify_synthetic",
    # kanban worker 停止守卫：无 kanban_complete/block 时的叙述性退出
    "_kanban_stop_synthetic",
    # 丢弃的 tool-call 重新提示对（finish_reason=tool_calls 但 tool_calls 数组为空）：
    # 中间的叙述性 assistant 消息和"请发出实际工具调用"的用户催促仅用于驱动有界重试。
    # 持久化它们会在恢复时将内部重试指令作为用户消息重放。
    "_dropped_toolcall_nudge",
)


def _is_ephemeral_scaffolding(msg: Any) -> bool:
    """判断消息是否为内部恢复脚手架 —— 这些消息绝不能持久化到 SQLite 会话存储或 JSON 日志。"""
    return isinstance(msg, dict) and any(
        msg.get(flag) for flag in _EPHEMERAL_SCAFFOLDING_FLAGS
    )


_MAX_TOOL_WORKERS = 8

# 消息已写入 SQLite 会话存储后的内在标记，供 _flush_messages_to_session_db 判断哪些已持久化。
# 不能用 id(msg) 做去重集合：一旦已刷盘的消息被丢弃并被垃圾回收（如脚手架回退或原地压缩），
# CPython 可能将其地址分配给新消息，导致 id() 碰撞，使真实对话轮次被静默丢失。
# 绑定在 dict 自身上的标记不会被别名化。`_` 前缀是必需的：线路清理器会在请求离开进程前
# 剥离所有 `_` 前缀的顶层 key，确保不会到达严格的 OpenAI 兼容网关。
_DB_PERSISTED_MARKER = "_db_persisted"


# 确保 OpenRouter 元数据预热线程在每个进程中只启动一次，而非每个 AIAgent 实例一次。
# 否则长运行网关进程会因每个消息泄漏一个线程，最终耗尽系统线程上限。
_openrouter_prewarm_done = threading.Event()

# =========================================================================
# 大型工具结果处理器 —— 将超大输出保存到临时文件
# =========================================================================


# =========================================================================
# Qwen Portal 请求头 —— 模拟 QwenCode CLI 以兼容 portal.qwen.ai。
# 提取为模块级辅助函数，供 __init__ 和 _apply_client_headers_for_base_url 共享。
# =========================================================================
_QWEN_CODE_VERSION = "0.14.1"


def _routermint_headers() -> dict:
    """返回 RouteMint 所需的 User-Agent 请求头，避免 Cloudflare 1010 拦截。"""
    from hermes_cli import __version__ as _HERMES_VERSION

    return {
        "User-Agent": f"HermesAgent/{_HERMES_VERSION}",
    }


def _pool_may_recover_from_rate_limit(pool) -> bool:
    """判断凭证池是否可能从速率限制中恢复。

    仅当池存在且包含多个条目时，凭证旋转才有意义。只有一个凭证的池（如 Vertex
    服务账号、个人 API key 配置）触发 429 后没有备用凭证可切换，等待冷却只是
    对同一已耗尽配额的重试。此时应直接使用 fallback_model 降级。

    参见 issues #11314 和 #13636。
    """
    if pool is None:
        return False
    if not pool.has_available():
        return False
    return len(pool.entries()) > 1


def _qwen_portal_headers() -> dict:
    """返回 Qwen Portal API 所需的默认 HTTP 请求头。"""
    import platform as _plat

    _ua = f"QwenCode/{_QWEN_CODE_VERSION} ({_plat.system().lower()}; {_plat.machine()})"
    return {
        "User-Agent": _ua,
        "X-DashScope-CacheControl": "enable",
        "X-DashScope-UserAgent": _ua,
        "X-DashScope-AuthType": "qwen-oauth",
    }


def _safe_session_filename_component(session_id: str) -> str:
    """将会话 ID 转换为安全的文件名组件。

    会话 ID 可能来自不可信输入（如 X-Hermes-Session-Id API 头），会被直接
    拼接到 ~/.hermes/sessions/ 下的文件路径中。未净化时，类似
    ../../../../etc/pwned 的路径穿越 ID 可将会话快照写出到会话目录之外。

    此函数将所有非 [A-Za-z0-9_-] 字符折叠为 _（消除路径分隔符和 .），
    限制长度，并在净化改变了原始字符串时追加短哈希以避免碰撞。
    结果始终是单个、无路径穿越的安全路径段。
    """
    raw = str(session_id or "").strip()
    sanitized = re.sub(r"[^\w-]", "_", raw).strip("._")
    sanitized = sanitized[:96] or "session"
    if raw and sanitized == raw:
        return sanitized
    digest = hashlib.sha256(
        raw.encode("utf-8", errors="surrogatepass")
    ).hexdigest()[:12]
    return f"{sanitized}_{digest}"


class _StreamErrorEvent(Exception):
    """从 Responses SSE ``error`` 帧合成的提供商错误。

    某些 Codex 风格的 Responses 后端（如 xAI 的订阅/配额失败、格式错误工具调用
    下的自定义中继）会发送独立的 ``type=error`` 帧，而非通过 ``response.failed``
    或返回 HTTP 4xx。回退流路径抛出此异常，使 ``_summarize_api_error`` 和
    ``_extract_api_error_context`` 能识别熟悉的 .body/.status_code 结构，
    授权检测器也能匹配底层提供商消息（如"没有活跃的 Grok 订阅"等）。
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        param: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.param = param
        self.status_code = status_code
        # 构造 OpenAI SDK 风格 body，使 _extract_api_error_context /
        # _summarize_api_error / classify_api_error 能统一处理。
        self.body: Dict[str, Any] = {
            "error": {
                "message": message,
                "code": code,
                "param": param,
                "type": "error",
            }
        }


class AIAgent:
    """
    具有工具调用能力的 AI Agent。

    管理对话流程、工具执行和响应处理，支持多种 LLM 提供商。
    """

    _TOOL_CALL_ARGUMENTS_CORRUPTION_MARKER = (
        "[hermes-agent: 工具调用 arguments were corrupted in this session and "
        "have been dropped to keep the conversation alive. See issue #15236.]"
    )

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        self._base_url = value
        self._base_url_lower = value.lower() if value else ""
        self._base_url_hostname = base_url_hostname(value)

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        provider: str = None,
        api_mode: str = None,
        acp_command: str = None,
        acp_args: list[str] | None = None,
        command: str = None,
        args: list[str] | None = None,
        model: str = "",
        max_iterations: int = 500,  # Default tool-calling iterations (shared with subagents)
        tool_delay: float = 1.0,
        enabled_toolsets: List[str] = None,
        disabled_toolsets: List[str] = None,
        save_trajectories: bool = False,
        verbose_logging: bool = False,
        quiet_mode: bool = False,
        tool_progress_mode: str = "all",
        ephemeral_system_prompt: str = None,
        log_prefix_chars: int = 100,
        log_prefix: str = "",
        providers_allowed: List[str] = None,
        providers_ignored: List[str] = None,
        providers_order: List[str] = None,
        provider_sort: str = None,
        provider_require_parameters: bool = False,
        provider_data_collection: str = None,
        openrouter_min_coding_score: Optional[float] = None,
        session_id: str = None,
        tool_progress_callback: callable = None,
        tool_start_callback: callable = None,
        tool_complete_callback: callable = None,
        thinking_callback: callable = None,
        reasoning_callback: callable = None,
        clarify_callback: callable = None,
        read_terminal_callback: callable = None,
        step_callback: callable = None,
        stream_delta_callback: callable = None,
        interim_assistant_callback: callable = None,
        tool_gen_callback: callable = None,
        status_callback: callable = None,
        notice_callback: callable = None,
        notice_clear_callback: callable = None,
        event_callback: Optional[Callable[[str, dict], None]] = None,
        reaction_callback: Optional[Callable[[str], None]] = None,
        max_tokens: int = None,
        reasoning_config: Dict[str, Any] = None,
        service_tier: str = None,
        request_overrides: Dict[str, Any] = None,
        prefill_messages: List[Dict[str, Any]] = None,
        platform: str = None,
        user_id: str = None,
        user_id_alt: str = None,
        user_name: str = None,
        chat_id: str = None,
        chat_name: str = None,
        chat_type: str = None,
        thread_id: str = None,
        gateway_session_key: str = None,
        skip_context_files: bool = False,
        load_soul_identity: bool = False,
        skip_memory: bool = False,
        session_db=None,
        parent_session_id: str = None,
        iteration_budget: "IterationBudget" = None,
        fallback_model: Dict[str, Any] = None,
        credential_pool=None,
        checkpoints_enabled: bool = False,
        checkpoint_max_snapshots: int = 20,
        checkpoint_max_total_size_mb: int = 500,
        checkpoint_max_file_size_mb: int = 10,
        pass_session_id: bool = False,
        requested_provider: str = None,
        skills_scope: "set[str] | None" = None,  # AgentForge-PATCH: 每用户可见技能名集合；None=全量（原生行为）
    ):
        """转发器 → agent/agent_init/init_agent.py"""
        from agent.agent_init import init_agent
        init_agent(
            self,
            base_url=base_url,
            api_key=api_key,
            provider=provider,
            requested_provider=requested_provider,
            api_mode=api_mode,
            acp_command=acp_command,
            acp_args=acp_args,
            command=command,
            args=args,
            model=model,
            max_iterations=max_iterations,
            tool_delay=tool_delay,
            enabled_toolsets=enabled_toolsets,
            disabled_toolsets=disabled_toolsets,
            save_trajectories=save_trajectories,
            verbose_logging=verbose_logging,
            quiet_mode=quiet_mode,
            tool_progress_mode=tool_progress_mode,
            ephemeral_system_prompt=ephemeral_system_prompt,
            log_prefix_chars=log_prefix_chars,
            log_prefix=log_prefix,
            providers_allowed=providers_allowed,
            providers_ignored=providers_ignored,
            providers_order=providers_order,
            provider_sort=provider_sort,
            provider_require_parameters=provider_require_parameters,
            provider_data_collection=provider_data_collection,
            openrouter_min_coding_score=openrouter_min_coding_score,
            session_id=session_id,
            tool_progress_callback=tool_progress_callback,
            tool_start_callback=tool_start_callback,
            tool_complete_callback=tool_complete_callback,
            thinking_callback=thinking_callback,
            reasoning_callback=reasoning_callback,
            clarify_callback=clarify_callback,
            read_terminal_callback=read_terminal_callback,
            step_callback=step_callback,
            stream_delta_callback=stream_delta_callback,
            interim_assistant_callback=interim_assistant_callback,
            tool_gen_callback=tool_gen_callback,
            status_callback=status_callback,
            notice_callback=notice_callback,
            notice_clear_callback=notice_clear_callback,
            event_callback=event_callback,
            reaction_callback=reaction_callback,
            max_tokens=max_tokens,
            reasoning_config=reasoning_config,
            service_tier=service_tier,
            request_overrides=request_overrides,
            prefill_messages=prefill_messages,
            platform=platform,
            user_id=user_id,
            user_id_alt=user_id_alt,
            user_name=user_name,
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type=chat_type,
            thread_id=thread_id,
            gateway_session_key=gateway_session_key,
            skip_context_files=skip_context_files,
            load_soul_identity=load_soul_identity,
            skip_memory=skip_memory,
            session_db=session_db,
            parent_session_id=parent_session_id,
            iteration_budget=iteration_budget,
            fallback_model=fallback_model,
            credential_pool=credential_pool,
            checkpoints_enabled=checkpoints_enabled,
            checkpoint_max_snapshots=checkpoint_max_snapshots,
            checkpoint_max_total_size_mb=checkpoint_max_total_size_mb,
            checkpoint_max_file_size_mb=checkpoint_max_file_size_mb,
            pass_session_id=pass_session_id,
            skills_scope=skills_scope,  # AgentForge-PATCH
        )

    def _get_session_db_for_recall(self):
        """返回用于 recall 的 SessionDB，如果入口点忘记则懒创建。

        Most frontends pass ``session_db`` into ``AIAgent`` explicitly, but recall
        is important enough that a missing constructor argument should degrade by
        opening the default state DB instead of making the advertised
        ``session_search`` tool unusable.
        """
        # 持久化隔离的分支（后台审查）不能懒加载标准状态数据库：否则会重新激活
        # _flush_messages_to_session_db，将分支的 harness 轮次写入用户真实会话。
        # 分支不需要 recall，降级为 None（它们不使用 session_search）。
        if getattr(self, "_persist_disabled", False):
            return None
        if self._session_db is not None:
            return self._session_db
        try:
            from hermes_state import SessionDB

            self._session_db = SessionDB()
            return self._session_db
        except Exception as exc:
            logger.debug("SessionDB unavailable for recall", exc_info=True)
            return None

    def _ensure_db_session(self) -> None:
        """首次使用时创建会话数据库行，失败时禁用 _session_db。"""
        if getattr(self, "_persist_disabled", False):
            return
        if self._session_db_created or not self._session_db:
            return
        source = _session_source_for_agent(self.platform)
        try:
            try:
                from hermes_cli.profiles import get_active_profile_name
                _profile_for_session = get_active_profile_name()
                if _profile_for_session == "default":
                    _profile_for_session = None
            except Exception:
                _profile_for_session = None
            self._session_db.create_session(
                session_id=self.session_id,
                source=source,
                model=self.model,
                model_config=self._session_init_model_config,
                system_prompt=self._cached_system_prompt,
                user_id=None,
                parent_session_id=self._parent_session_id,
                cwd=_launch_cwd_for_session(source),
                profile_name=_profile_for_session,
            )
            self._session_db_created = True
        except Exception as e:
            # 临时故障（如 SQLite 锁）。保持 _session_db 存活 ——
            # _session_db_created 保持 False，下次 run_conversation() 会重试。
            logger.warning(
                "Session DB creation failed (will retry next turn): %s", e
            )

    def _transition_context_engine_session(
        self,
        *,
        old_session_id: Optional[str] = None,
        new_session_id: Optional[str] = None,
        previous_messages: Optional[list] = None,
        carry_over_context: bool = False,
        reset_engine: bool = True,
        **extra_context,
    ) -> None:
        """通知活动上下文引擎有关主机会话转换。

        Generic host-side lifecycle helper. The built-in compressor keeps its
        existing reset behavior; plugin engines that implement richer hooks
        (``on_session_end``, ``on_session_reset``, ``on_session_start``,
        ``carry_over_new_session_context``) can flush old-session state,
        reset runtime counters, bind to the new session, and optionally
        carry retained context forward.
        """
        engine = getattr(self, "context_compressor", None)
        if not engine:
            return

        if old_session_id and previous_messages is not None and hasattr(engine, "on_session_end"):
            try:
                engine.on_session_end(old_session_id, previous_messages)
            except Exception as exc:
                logger.debug("context engine on_session_end during transition: %s", exc)

        if reset_engine and hasattr(engine, "on_session_reset"):
            try:
                engine.on_session_reset()
            except Exception as exc:
                logger.debug("context engine on_session_reset during transition: %s", exc)

        should_start = bool(
            old_session_id
            or previous_messages is not None
            or carry_over_context
            or extra_context
        )
        target_session_id = new_session_id or getattr(self, "session_id", "") or ""
        if should_start and target_session_id and hasattr(engine, "on_session_start"):
            start_context = {
                "old_session_id": old_session_id,
                "carry_over_context": carry_over_context,
                "platform": _session_source_for_agent(getattr(self, "platform", None)),
                "model": getattr(self, "model", ""),
                "context_length": getattr(engine, "context_length", None),
                "conversation_id": getattr(self, "_gateway_session_key", None),
            }
            start_context.update(extra_context)
            start_context = {k: v for k, v in start_context.items() if v not in (None, "")}
            try:
                engine.on_session_start(target_session_id, **start_context)
            except Exception as exc:
                logger.debug("context engine on_session_start during transition: %s", exc)

        if (
            carry_over_context
            and old_session_id
            and target_session_id
            and hasattr(engine, "carry_over_new_session_context")
        ):
            try:
                engine.carry_over_new_session_context(old_session_id, target_session_id)
            except Exception as exc:
                logger.debug("context engine carry_over_new_session_context during transition: %s", exc)

    def reset_session_state(
        self,
        previous_messages: Optional[list] = None,
        old_session_id: Optional[str] = None,
        carry_over_context: bool = False,
    ):
        """为新会话将所有会话范围的 token 计数器重置为 0。
        
        This method encapsulates the reset logic for all session-level metrics
        including:
        - Token usage counters (input, output, total, prompt, completion)
        - Cache read/write tokens
        - API call count
        - Reasoning tokens
        - Estimated cost tracking
        - Context compressor internal counters
        
        The method safely handles optional attributes (e.g., context compressor)
        using ``hasattr`` checks.

        When ``previous_messages`` / ``old_session_id`` / ``carry_over_context``
        are provided, the active context engine is notified through the
        full transition lifecycle (``_transition_context_engine_session``)
        instead of a bare reset. Default callers pass nothing and keep the
        existing reset-only behavior.
        """
        self.session_total_tokens = 0
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.session_cache_read_tokens = 0
        self.session_cache_write_tokens = 0
        self.session_reasoning_tokens = 0
        self.session_api_calls = 0
        self.session_estimated_cost_usd = 0.0
        self.session_cost_status = "unknown"
        self.session_cost_source = "none"
        
        self._user_turn_count = 0

        self._is_user_initiated_turn = False

        self._transition_context_engine_session(
            old_session_id=old_session_id,
            new_session_id=getattr(self, "session_id", None),
            previous_messages=previous_messages,
            carry_over_context=carry_over_context,
            reset_engine=True,
        )

        engine = getattr(self, "context_compressor", None)
        target_session_id = getattr(self, "session_id", "") or ""
        bound_session_id = getattr(engine, "_session_id", "") if engine is not None else ""
        if (
            engine is not None
            and hasattr(engine, "bind_session_state")
            and target_session_id
            and target_session_id != bound_session_id
        ):
            try:
                engine.bind_session_state(getattr(self, "_session_db", None), target_session_id)
            except Exception as exc:
                logger.debug("context engine bind_session_state during reset: %s", exc)

    @staticmethod
    def _effective_lmstudio_context_length(
        config_context_length: Optional[int],
        runtime_context_length: Any,
    ) -> Optional[int]:
        """从显式意图和已验证运行时返回安全的上下文预算。"""
        explicit = (
            config_context_length
            if isinstance(config_context_length, int)
            and not isinstance(config_context_length, bool)
            and config_context_length > 0
            else None
        )
        runtime_value = getattr(runtime_context_length, "context_length", runtime_context_length)
        runtime = (
            runtime_value
            if isinstance(runtime_value, int)
            and not isinstance(runtime_value, bool)
            and runtime_value > 0
            else None
        )
        if bool(getattr(runtime_context_length, "rejected", False)) or (
            bool(getattr(runtime_context_length, "load_attempted", False))
            and runtime is None
        ):
            return None
        if runtime is not None and explicit is not None:
            return min(runtime, explicit)
        return runtime if runtime is not None else explicit

    @staticmethod
    def _lmstudio_load_was_unverified(load_result: Any) -> bool:
        """判断管理加载是否被拒绝或无法验证。"""
        return bool(getattr(load_result, "rejected", False)) or (
            bool(getattr(load_result, "load_attempted", False))
            and getattr(load_result, "context_length", None) is None
        )

    def _ensure_lmstudio_runtime_loaded(
        self,
        config_context_length: Optional[int] = None,
    ) -> Any:
        """预加载 LM Studio，除非配置为依赖 JIT 加载。"""
        if (self.provider or "").strip().lower() != "lmstudio":
            return None
        if (getattr(self, "lmstudio_load_mode", "explicit") or "explicit").strip().lower() == "jit":
            logger.debug("LM Studio explicit preload skipped: lmstudio_load_mode=jit")
            return None

        from hermes_cli.models import ensure_lmstudio_model_loaded

        if config_context_length is None:
            config_context_length = getattr(self, "_config_context_length", None)
        return ensure_lmstudio_model_loaded(
            self.model,
            self.base_url,
            getattr(self, "api_key", ""),
            config_context_length,
            return_load_result=True,
        )

    def switch_model(self, new_model, new_provider, api_key='', base_url='', api_mode=''):
        """转发器 → agent/agent_runtime_helpers/switch_model.py"""
        from agent.agent_runtime_helpers import switch_model
        return switch_model(self, new_model, new_provider, api_key, base_url, api_mode)

    def _safe_print(self, *args, **kwargs):
        """安全打印，静默处理管道破裂/标准输出关闭。

        在无头环境中（systemd、Docker、nohup），stdout 可能在会话中变得不可用。
        原始 ``print()`` 会抛出 ``OSError``，可能使 cron 任务崩溃并丢失已完成的工作。

        内部通过 ``self._print_fn``（默认：内建 ``print``）路由，这样 CLI 等调用者
        可以注入正确处理 ANSI 转义序列的渲染器（例如 prompt_toolkit 的
        ``print_formatted_text(ANSI(...))``），而无需修改此方法。
        """
        try:
            fn = self._print_fn or print
            fn(*args, **kwargs)
        except (OSError, ValueError):
            pass

    def _vprint(self, *args, force: bool = False, **kwargs):
        """详细打印 —— streaming token 时抑制。

        传递 ``force=True`` 用于即使在streaming播放期间（TTS 或显示）也应始终显示的错误/警告消息。

        在工具执行期间（``_executing_tools`` 为 True），即使注册了流消费者也允许打印，
        因为此时没有 token 被streaming。

        在主响应已交付且剩余的工具调用是响应后内务处理（``_mute_post_response``）后，
        所有非强制输出都被抑制。

        ``suppress_status_output`` 是更严格的 CLI 自动化模式，用于 ``hermes chat -q`` 等
        可解析的单查询流程。在该模式下，通过 ``_vprint`` 路由的所有状态/诊断打印都被抑制，
        以便 stdout 保持机器可读。
        """
        if getattr(self, "suppress_status_output", False):
            return
        if not force and getattr(self, "_mute_post_response", False):
            return
        if not force and self._has_stream_consumers() and not self._executing_tools:
            return
        self._safe_print(*args, **kwargs)

    def _should_start_quiet_spinner(self) -> bool:
        """判断静默模式旋转器输出是否有安全的接收端。

        In headless/stdio-protocol environments, a raw spinner with no custom
        ``_print_fn`` falls back to ``sys.stdout`` and can corrupt protocol
        streams such as ACP JSON-RPC. Allow quiet spinners only when either:
        - output is explicitly rerouted via ``_print_fn``; or
        - stdout is a real TTY.
        """
        if self._print_fn is not None:
            return True
        stream = getattr(sys, "stdout", None)
        if stream is None:
            return False
        try:
            return bool(stream.isatty())
        except (AttributeError, ValueError, OSError):
            return False

    def _should_emit_quiet_tool_messages(self) -> bool:
        """判断静默模式工具摘要是否应直接打印。

        Quiet mode is used by both the interactive CLI and embedded/library
        callers. The CLI may still want compact progress hints when no callback
        owns rendering. Embedded/library callers, on the other hand, expect
        quiet mode to be truly silent.
        """
        return (
            self.quiet_mode
            and not self.tool_progress_callback
            and getattr(self, "platform", "") == "cli"
        )

    def _emit_status(self, message: str) -> None:
        """Emit a lifecycle status message to both CLI and gateway channels.

        CLI users see the message via ``_vprint(force=True)`` so it is always
        visible regardless of verbose/quiet mode.  Gateway consumers receive
        it through ``status_callback("lifecycle", ...)``.

        This helper never raises — exceptions are swallowed so it cannot
        interrupt the retry/fallback logic.
        """
        try:
            self._vprint(f"{self.log_prefix}{message}", force=True)
        except Exception:
            pass
        if self.status_callback:
            try:
                self.status_callback("lifecycle", message)
            except Exception:
                logger.debug("status_callback error in _emit_status", exc_info=True)

    def _emit_warning(self, message: str) -> None:
        """通过相同的状态管道发送用户可见的警告。

        Unlike debug logs, these warnings are meant for degraded side paths
        such as auxiliary compression or memory flushes where the main turn can
        continue but the user needs to know something important failed.
        """
        try:
            self._vprint(f"{self.log_prefix}{message}", force=True)
        except Exception:
            pass
        if self.status_callback:
            try:
                self.status_callback("warn", message)
            except Exception:
                logger.debug("status_callback error in _emit_warning", exc_info=True)

    def _warn_context_overflow_blocked(
        self, reason: str, preflight_tokens: int, threshold_tokens: int
    ) -> None:
        """当上下文超过压缩阈值但压缩被阻止时，显示去重警告
        （摘要 LLM 冷却或防抖动）。

        没有此信号，会话会持续增长，直到模型静默停止回答 —— 对话到达
        硬提供商 token 限制而没有解释。集中在此处，以便每个检查
        ``should_compress_info`` 的调用者（turn 上下文预检、对话循环守卫）
        共享相同的去重/重置逻辑。

        去重基于阻止的*类型*（``cooldown`` / ``ineffective``），而不是精确的
        倒计数字符串，所以冷却从 30→29→… 递减不会每 turn 重新触发警告。
        当阻止清除时，去重键会被清除（见 ``_clear_context_overflow_warn``），
        所以警告可以在下一个被阻止的超阈值 turn 上再次触发。
        """
        _warn_kind = (reason or "unknown").split(":", 1)[0]
        _warn_key = ("ctx_overflow_blocked", _warn_kind)
        if getattr(self, "_last_ctx_overflow_warn", None) != _warn_key:
            self._last_ctx_overflow_warn = _warn_key
            from agent.conversation_compression import (
                CONTEXT_OVERFLOW_BLOCKED_WARNING_TEMPLATE,
            )
            self._emit_warning(
                CONTEXT_OVERFLOW_BLOCKED_WARNING_TEMPLATE.format(
                    tokens=preflight_tokens,
                    threshold=threshold_tokens,
                    reason=reason,
                )
            )

    def _clear_context_overflow_warn(self) -> None:
        """重置被阻止溢出警告的去重状态。

        Call this whenever compression is no longer blocked while the context
        is over threshold (e.g. the cooldown elapsed, or compression ran
        successfully), so the warning can re-fire on the next blocked turn.
        """
        self._last_ctx_overflow_warn = None

    def _emit_notice(self, notice) -> None:
        """向活动驱动（TUI / CLI）发送结构化 ``AgentNotice``。

        驱动无关：绑定的 ``notice_callback`` 按该驱动的方式渲染它（TUI 状态栏覆盖、CLI 控制台行）。
        吞掉所有回调错误 —— 通知绝不能破坏 Agent 循环（D-D 失败开放）。
        """
        if self.notice_callback:
            try:
                self.notice_callback(notice)
            except Exception:
                logger.debug("notice_callback error in _emit_notice", exc_info=True)

    def _emit_notice_clear(self, key: str) -> None:
        """通过 key 清除先前触发的粘性通知（如恢复时）。"""
        if self.notice_clear_callback:
            try:
                self.notice_clear_callback(key)
            except Exception:
                logger.debug("notice_clear_callback error in _emit_notice_clear", exc_info=True)

    def _emit_wait_notice(self, text: str) -> None:
        """在每个驱动上显示实时等待状态说明。

        长时间的提供商等待（慢/过载的后端、无首字节、reasoning_model思考数分钟）曾经让用户
        盯着通用的 "cogitating..." 旋转器，没有任何关于 Agent 在等待什么的提示。
        此助手用说明重写实时状态行：

        - CLI：``thinking_callback`` 更新 prompt_toolkit 旋转器文本。
        - TUI / Desktop：相同的回调桥接到 ``thinking.delta`` 事件，两者都渲染为
          实时旋转器/状态行。
        - Gateway：``_touch_activity`` 将文本存储为活动描述，"⏳ Working — N min"
          心跳包含它。

        绝不抛出 —— 等待通知不能破坏 API 调用等待循环。
        """
        self._touch_activity(text)
        _thinking_cb = getattr(self, "thinking_callback", None)
        if _thinking_cb:
            try:
                _thinking_cb(text)
            except Exception:
                logger.debug("thinking_callback error in _emit_wait_notice", exc_info=True)

    # ── 缓冲重试/降级状态 ────────────────────────────────────────────
    # 重试和降级链会向 CLI/网关输出大量状态噪音，用户觉得困惑：一次短暂的 429 可能在请求
    # 最终成功前产生 10+ 行 "Provider/Endpoint/Retrying in 5s..." 消息。下面的缓冲辅助函数
    # 捕获这些状态消息而不是立即输出。它们仅在每次重试和降级都耗尽时才刷新（显示给用户）；
    # 成功时会被静默丢弃。后端日志（agent.log）不受影响 —— 每个单独的输出处仍然写入
    # ``logger.warning`` / ``logger.info`` 用于诊断。

    def _buffer_status(self, message: str) -> None:
        """Buffer a retry/fallback status message.

        Stored as a (kind, text) tuple where ``kind`` is one of:
        - ``"status"``  -> replays via ``_emit_status``
        - ``"vprint"``  -> replays via ``_vprint(force=True)``
        - ``"warn"``    -> replays via ``_emit_warning``
        Used to defer noisy retry chatter until we know whether the
        turn ultimately recovered or failed.
        """
        try:
            buf = getattr(self, "_retry_status_buffer", None)
            if buf is None:
                buf = []
                self._retry_status_buffer = buf
            buf.append(("status", message))
        except Exception:
                    pass

    def _buffer_vprint(self, message: str) -> None:
        """缓冲一条 vprint(force=True) 重试/降级日志行。"""
        try:
            buf = getattr(self, "_retry_status_buffer", None)
            if buf is None:
                buf = []
                self._retry_status_buffer = buf
            buf.append(("vprint", message))
        except Exception:
            pass

    def _clear_status_buffer(self) -> None:
        """丢弃缓冲的重试消息 —— 成功恢复时调用。"""
        try:
            buf = getattr(self, "_retry_status_buffer", None)
            if buf:
                buf.clear()
        except Exception:
            pass

    def _emit_pending_fallback_notice(self) -> None:
        """成功恢复时显示一次性降级切换通知。

        A provider/model switch is a durable state change operators must see,
        unlike transient retry chatter that ``_clear_status_buffer`` drops.
        ``try_activate_fallback`` records the switch in
        ``self._pending_fallback_notice``; this emits it exactly once via
        ``_emit_status`` and then clears it, so a successful fallback still
        produces one visible notice.  On terminal failure the buffered switch
        line is flushed instead (and this notice discarded) — see
        ``_flush_status_buffer`` — so the user always sees the switch once.
        """
        try:
            notice = getattr(self, "_pending_fallback_notice", None)
            if notice:
                # 在发射前清除，这样（被吞掉的）回调错误就不会在后续轮次中
                # 留下过时的通知用于重复发射。
                self._pending_fallback_notice = None
                self._emit_status(notice)
        except Exception:
            pass

    def _flush_status_buffer(self) -> None:
        """发送缓冲的重试消息 —— 在终末失败时调用。

        Surfaces the full retry/fallback trace so the user can see what
        was tried before the turn gave up.
        """
        try:
            # 缓冲追踪已经携带了降级切换行，所以丢弃任何一次性降级通知以避免
            # 过时副本泄漏到后续成功的轮次中。
            self._pending_fallback_notice = None
            buf = getattr(self, "_retry_status_buffer", None)
            if not buf:
                return
            # 先排空，防止回调异常导致重复输出。
            messages = list(buf)
            buf.clear()
            for kind, msg in messages:
                try:
                    if kind == "status":
                        self._emit_status(msg)
                    elif kind == "warn":
                        self._emit_warning(msg)
                    else:
                        self._vprint(f"{self.log_prefix}{msg}", force=True)
                except Exception:
                    pass
        except Exception:
            pass

    def _disable_codex_reasoning_replay(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        """Disable Responses encrypted reasoning replay and strip cached state.

        Called from the conversation_loop retry path when the provider
        rejects a replayed ``codex_reasoning_items`` blob with HTTP 400
        ``invalid_encrypted_content``.  Sets ``self._codex_reasoning_replay_enabled``
        to ``False`` (consumed by ``codex_responses_adapter._chat_messages_to_responses_input``
        and ``transports/codex.py`` to drop ``reasoning.encrypted_content``
        from subsequent requests) and pops ``codex_reasoning_items`` from
        every assistant message in ``messages`` so they cannot be replayed
        again later in the session.

        Returns a small stats dict ``{"messages": int, "items": int}``
        counting what was stripped — purely for diagnostic logging.
        """
        stripped_messages = 0
        stripped_items = 0
        target_messages = messages if isinstance(messages, list) else []

        for msg in target_messages:
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            items = msg.pop("codex_reasoning_items", None)
            if isinstance(items, list) and items:
                stripped_messages += 1
                stripped_items += len(items)

        self._codex_reasoning_replay_enabled = False
        return {"messages": stripped_messages, "items": stripped_items}

    # 流诊断类头保留用于向后兼容 —— 实际列表在
    # agent.stream_diag.STREAM_DIAG_HEADERS 中。
    from agent.stream_diag import STREAM_DIAG_HEADERS as _STREAM_DIAG_HEADERS  # noqa: E402

    @staticmethod
    def _stream_diag_init() -> Dict[str, Any]:
        """转发器 → agent/stream_diag/stream_diag_init.py"""
        from agent.stream_diag import stream_diag_init
        return stream_diag_init()

    def _stream_diag_capture_response(
        self, diag: Dict[str, Any], http_response: Any
    ) -> None:
        """转发器 → agent/stream_diag/stream_diag_capture_response.py"""
        from agent.stream_diag import stream_diag_capture_response
        stream_diag_capture_response(self, diag, http_response)

    @staticmethod
    def _flatten_exception_chain(error: BaseException) -> str:
        """转发器 → agent/stream_diag/flatten_exception_chain.py"""
        from agent.stream_diag import flatten_exception_chain
        return flatten_exception_chain(error)

    def _is_provider_stream_parse_error(self, error: BaseException) -> bool:
        """Return True for malformed provider streaming data from SDK parsers.

        Some Anthropic-compatible streaming providers can send a malformed
        event-stream frame.  The Anthropic SDK surfaces that as a plain
        ``ValueError`` such as ``expected ident at line 1 column 149``.  That
        is provider wire-format trouble, not local request validation, so it
        should follow the same retry path as a truncated JSON body.
        """
        if getattr(self, "api_mode", None) != "anthropic_messages":
            return False
        if not isinstance(error, ValueError):
            return False
        if isinstance(error, (UnicodeEncodeError, json.JSONDecodeError)):
            return False
        message = str(error).strip().lower()
        return "expected ident at line" in message

    def _log_stream_retry(
        self,
        *,
        kind: str,
        error: BaseException,
        attempt: int,
        max_attempts: int,
        mid_tool_call: bool,
        diag: Optional[Dict[str, Any]] = None,
    ) -> None:
        """转发器 → agent/stream_diag/log_stream_retry.py"""
        from agent.stream_diag import log_stream_retry
        log_stream_retry(
            self, kind=kind, error=error, attempt=attempt,
            max_attempts=max_attempts, mid_tool_call=mid_tool_call, diag=diag,
        )

    def _emit_stream_drop(
        self,
        *,
        error: BaseException,
        attempt: int,
        max_attempts: int,
        mid_tool_call: bool,
        diag: Optional[Dict[str, Any]] = None,
    ) -> None:
        """转发器 → agent/stream_diag/emit_stream_drop.py"""
        from agent.stream_diag import emit_stream_drop
        emit_stream_drop(
            self, error=error, attempt=attempt, max_attempts=max_attempts,
            mid_tool_call=mid_tool_call, diag=diag,
        )

    def _emit_auxiliary_failure(self, task: str, exc: BaseException) -> None:
        """为失败的辅助工作输出紧凑警告。"""
        try:
            detail = self._summarize_api_error(exc)
        except Exception:
            detail = str(exc)
        detail = (detail or exc.__class__.__name__).strip()
        if len(detail) > 220:
            detail = detail[:217].rstrip() + "..."
        self._emit_warning(f"⚠ Auxiliary {task} failed: {detail}")

    def _current_main_runtime(self) -> Dict[str, str]:
        """返回会话范围内辅助路由的实时主运行时信息。"""
        return {
            "model": getattr(self, "model", "") or "",
            "provider": getattr(self, "provider", "") or "",
            "base_url": getattr(self, "base_url", "") or "",
            "api_key": getattr(self, "api_key", "") or "",
            "api_mode": getattr(self, "api_mode", "") or "",
            "auth_mode": getattr(self, "auth_mode", "") or "",
        }

    def _check_compression_model_feasibility(self) -> None:
        """转发器 → agent/conversation_compression/check_compression_model_feasibility.py"""
        from agent.conversation_compression import check_compression_model_feasibility
        check_compression_model_feasibility(self)

    def _replay_compression_warning(self) -> None:
        """转发器 → agent/conversation_compression/replay_compression_warning.py"""
        from agent.conversation_compression import replay_compression_warning
        replay_compression_warning(self)

    def _is_direct_openai_url(self, base_url: str = None) -> bool:
        """判断 base URL 是否指向 OpenAI 原生 API。"""
        if base_url is not None:
            hostname = base_url_hostname(base_url)
        else:
            hostname = getattr(self, "_base_url_hostname", "") or base_url_hostname(
                getattr(self, "_base_url_lower", "")
            )
        return hostname == "api.openai.com"

    def _is_azure_openai_url(self, base_url: str = None) -> bool:
        """判断 base URL 是否指向 Azure OpenAI。

        Azure OpenAI exposes an OpenAI-compatible endpoint at
        ``{resource}.openai.azure.com/openai/v1`` that accepts the
        standard ``openai`` Python client.  Unlike api.openai.com it
        does NOT support the Responses API — gpt-5.x models are served
        on the regular ``/chat/completions`` path — so routing decisions
        must treat Azure separately from direct OpenAI.
        """
        if base_url is not None:
            url = str(base_url).lower()
        else:
            url = getattr(self, "_base_url_lower", "") or ""
        return "openai.azure.com" in url

    def _is_github_copilot_url(self, base_url: str = None) -> bool:
        """判断 base URL 是否指向 GitHub Copilot 的 OpenAI 兼容 API。"""
        if base_url is not None:
            hostname = base_url_hostname(base_url)
        else:
            hostname = getattr(self, "_base_url_hostname", "") or base_url_hostname(
                getattr(self, "_base_url_lower", "")
            )
        if not hostname:
            return False
        return hostname == "api.githubcopilot.com" or hostname.endswith(".githubcopilot.com")

    def _resolved_api_call_timeout(self) -> float:
        """解析每次调用的有效请求超时时间（秒）。

        Priority:
          1. ``providers.<id>.models.<model>.timeout_seconds`` (per-model override)
          2. ``providers.<id>.request_timeout_seconds`` (provider-wide)
          3. ``HERMES_API_TIMEOUT`` env var (legacy escape hatch)
          4. 1800.0s default

        Used by OpenAI-wire chat completions (streaming and non-streaming) so
        the per-provider config knob wins over the 1800s default.  Without this
        helper, the hardcoded ``HERMES_API_TIMEOUT`` fallback would always be
        passed as a per-call ``timeout=`` kwarg, overriding the client-level
        timeout the AIAgent.__init__ path configured.
        """
        cfg = get_provider_request_timeout(self.provider, self.model)
        if cfg is not None:
            return cfg
        return env_float("HERMES_API_TIMEOUT", 1800.0)

    def _resolved_api_call_stale_timeout_base(self) -> tuple[float, bool]:
        """Resolve the base non-stream stale timeout and whether it is implicit.

        Priority:
          1. ``providers.<id>.models.<model>.stale_timeout_seconds``
          2. ``providers.<id>.stale_timeout_seconds``
          3. ``HERMES_API_CALL_STALE_TIMEOUT`` env var
          4. 90.0s default (time-to-first-byte for non-streaming / Codex
             internal-streaming requests; lowered from 300s in May 2026 so
             fallback providers kick in faster when upstream providers
             stall).  The detector still scales up for large contexts in
             ``_compute_non_stream_stale_timeout``.

        Returns ``(timeout_seconds, uses_implicit_default)`` so the caller can
        preserve legacy behaviors that only apply when the user has *not*
        explicitly configured a stale timeout, such as auto-disabling the
        detector for local endpoints.
        """
        cfg = get_provider_stale_timeout(self.provider, self.model)
        if cfg is not None:
            return cfg, False

        env_timeout = os.getenv("HERMES_API_CALL_STALE_TIMEOUT")
        if env_timeout is not None:
            return float(env_timeout), False

        # reasoning_model下限：对已知reasoning_model的自动缓解
        # （Nemotron 3 Ultra、OpenAI o1/o3、Anthropic Opus 4.x thinking、
        # DeepSeek R1、Qwen QwQ、xAI Grok reasoning等），其云端
        # 在模型的reasoning阶段结束前，gateway 会空闲杀死。
        # uses_implicit_default 在此为 False，以便 _compute_non_stream_stale_timeout
        # 中的本地端点短路不会
        # 为在本地 NIM 端点上运行reasoning_model的用户禁用过期检测。
        from agent.reasoning_timeouts import get_reasoning_stale_timeout_floor
        reasoning_floor = get_reasoning_stale_timeout_floor(self.model)
        if reasoning_floor is not None:
            return reasoning_floor, False

        return 90.0, True

    def _compute_non_stream_stale_timeout(self, api_payload: Any) -> float:
        """计算此请求的有效非流过期超时。

        接受完整的 ``api_kwargs`` 字典（Chat Completions 或
        Responses API）或遗留的 ``messages`` 列表。上下文大小缩放
        对两种形状都通过
        :func:`agent.chat_completion_helpers.estimate_request_context_tokens` 应用相同方式。
        """
        stale_base, uses_implicit_default = self._resolved_api_call_stale_timeout_base()
        base_url = getattr(self, "_base_url", None) or self.base_url or ""
        if uses_implicit_default and base_url and is_local_endpoint(base_url):
            return float("inf")

        from agent.chat_completion_helpers import estimate_request_context_tokens
        est_tokens = estimate_request_context_tokens(api_payload)
        if est_tokens > 100_000:
            return max(stale_base, 240.0)
        if est_tokens > 50_000:
            return max(stale_base, 150.0)
        return stale_base

    def _codex_silent_hang_hint(self, model: Optional[str] = None) -> Optional[str]:
        """当此请求匹配已知的 Codex 静默拒绝配置时返回可操作的提示，
        否则返回 ``None``。

        ChatGPT Codex 后端（``chatgpt.com/backend-api/codex``）历史上
        静默丢弃某些模型请求：连接被接受但没有流事件发出，也没有错误抛出。
        过期调用检测器结束挂起，但通用的"超时"消息没有给用户前进的路径。

        此助手将可操作的提示替换到过期超时
        warning when the request matches a known silent-reject pattern.
        Currently flagged: ``gpt-5.5`` family on the Codex backend.  See
        hermes-agent #21444 for the symptom history.  The upstream backend
        behavior has historically come and gone with ChatGPT entitlement
        changes — the heuristic stays in place as future-proofing even when
        the symptom is dormant.

        Does NOT fix the backend issue.  Only converts an opaque stale-timeout
        into actionable text so users learn the workaround in seconds rather
        than digging through logs.
        """
        if self.api_mode != "codex_responses":
            return None
        is_codex_backend = (
            self.provider == "openai-codex"
            or (
                getattr(self, "_base_url_hostname", "") == "chatgpt.com"
                and "/backend-api/codex" in (getattr(self, "_base_url_lower", "") or "")
            )
        )
        if not is_codex_backend:
            return None
        eff_model = (model if model is not None else self.model) or ""
        model_lower = eff_model.lower()
        # 匹配 gpt-5.5 系列 —— 裸名 ``gpt-5.5``、``gpt-5.5-codex``、供应商前缀变体如
        # ``openai/gpt-5.5``，以及任何未来的 ``gpt-5.5-*`` SKU。在任一侧用单词边界锚定，
        # 这样无关的 token 如 ``gpt-5.50`` 不会匹配。
        if not re.search(r"(?:^|[/\-_])gpt-5\.5(?:$|[\-_])", model_lower):
            return None
        return (
            f"Codex backend appears to be silently rejecting {eff_model!r} "
            "on chatgpt.com/backend-api/codex (no stream events, no error). "
            "This is a known backend-side pattern that has affected ChatGPT "
            "Plus accounts intermittently. "
            "Workaround: try `gpt-5.4` on the same OAuth profile, or `gpt-5.3-codex`, "
            "or switch to a different model/provider in your fallback chain. "
            "Some ChatGPT Codex accounts do not support `gpt-5.4-codex`. "
            "See hermes-agent#21444 for symptom history."
        )

    def _is_openrouter_url(self) -> bool:
        """判断 base URL 是否指向 OpenRouter。"""
        return base_url_host_matches(self._base_url_lower, "openrouter.ai")

    def _is_copilot_url(self) -> bool:
        """判断 base URL 是否指向 GitHub Copilot 或 GitHub Models。"""
        return (
            "api.githubcopilot.com" in self._base_url_lower
            or "models.github.ai" in self._base_url_lower
        )

    def _anthropic_prompt_cache_policy(
        self,
        *,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        api_mode: Optional[str] = None,
        model: Optional[str] = None,
    ) -> tuple[bool, bool]:
        """转发器 → agent/agent_runtime_helpers/anthropic_prompt_cache_policy.py"""
        from agent.agent_runtime_helpers import anthropic_prompt_cache_policy
        return anthropic_prompt_cache_policy(self, provider=provider, base_url=base_url, api_mode=api_mode, model=model)

    @staticmethod
    def _model_requires_responses_api(model: str) -> bool:
        """对需要 Responses API 路径的模型返回 True。

        GPT-5.x models are rejected on /v1/chat/completions by both
        OpenAI and OpenRouter (error: ``unsupported_api_for_model``).
        Detect these so the correct api_mode is set regardless of
        which provider is serving the model.
        """
        m = model.lower()
        # 去除供应商前缀（例如 "openai/gpt-5.4" → "gpt-5.4"）
        if "/" in m:
            m = m.rsplit("/", 1)[-1]
        return m.startswith("gpt-5")

    @staticmethod
    def _provider_model_requires_responses_api(
        model: str,
        *,
        provider: Optional[str] = None,
    ) -> bool:
        """判断此提供商/模型对是否应使用 Responses API。"""
        normalized_provider = (provider or "").strip().lower()
        # Nous 通过其 OpenAI 兼容的 chat completions 端点提供 GPT-5.x 模型；
        # 其 /v1/responses 端点返回 404。
        if normalized_provider == "nous":
            return False
        if normalized_provider == "custom":
            # 通用自定义端点默认保守。它们可能中继 GPT-5 模型但没有完整的
            # Responses 语义，所以只有
            # 直接 OpenAI/xAI URL 检测应自动升级它们。
            return False
        if normalized_provider == "copilot":
            try:
                from hermes_cli.models import _should_use_copilot_responses_api
                return _should_use_copilot_responses_api(model)
            except Exception:
                # 如果由于任何原因 Copilot 特定逻辑不可用，则回退到通用的
                # GPT-5 规则。
                pass
        return AIAgent._model_requires_responses_api(model)

    def _max_tokens_param(self, value: int) -> dict:
        """为当前提供商返回正确的 max tokens kwarg。

        OpenAI 的较新模型（gpt-4o、gpt-4.1、gpt-5+、o 系列）需要
        'max_completion_tokens'。Azure OpenAI 和 GitHub Copilot 通过其
        OpenAI 兼容端点提供的那些系列也需要 'max_completion_tokens'。
        OpenRouter、本地模型和较旧的 OpenAI 模型使用 'max_tokens'。

        检查优先 URL（api.openai.com / Azure / Copilot 都使用新 kwarg），
        然后回退到模型名称检查，以便代理那些模型的第三方 OpenAI 兼容端点
        被识别 —— 仅 URL 检测会漏掉这种情况并静默发送错误的 kwarg，
        上游模型会以 400 拒绝。
        """
        if (
            self._is_direct_openai_url()
            or self._is_azure_openai_url()
            or self._is_github_copilot_url()
            or model_forces_max_completion_tokens(self.model)
        ):
            return {"max_completion_tokens": value}
        return {"max_tokens": value}

    @staticmethod
    def _requested_output_cap_from_api_kwargs(api_kwargs: Any) -> Optional[int]:
        """从准备好的请求中提取输出响应 token 上限。"""
        if not isinstance(api_kwargs, dict):
            return None
        for key in ("max_output_tokens", "max_completion_tokens", "max_tokens"):
            raw = api_kwargs.get(key)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    def _has_content_after_think_block(self, content: str) -> bool:
        """
        检查内容在任何 reasoning/thinking 块后是否有实际文本。

        这检测模型只输出 reasoning但没有实际响应的情况，这表示应重试的不完整生成。
        必须与 _strip_think_blocks() 标签变体保持同步。

        Args:
            content: 要检查的助手消息内容

        Returns:
            如果 think 块后有有意义的内容则为 True，否则为 False
        """
        if not content:
            return False

        # Remove all reasoning tag variants (must match _strip_think_blocks)
        cleaned = self._strip_think_blocks(content)

        # 检查是否还有非空白内容剩余
        return bool(cleaned.strip())

    def _strip_think_blocks(self, content: str) -> str:
        """转发器 → agent/agent_runtime_helpers/strip_think_blocks.py"""
        from agent.agent_runtime_helpers import strip_think_blocks
        return strip_think_blocks(self, content)

    @staticmethod
    def _has_natural_response_ending(content: str) -> bool:
        """启发式判断：可见的 assistant 文本是否看起来是有意结束的？"""
        if not content:
            return False
        stripped = content.rstrip()
        if not stripped:
            return False
        if stripped.endswith("```"):
            return True
        if stripped.endswith('^'):
            return True
        last = stripped[-1]
        if last in '.!?:)"\']}。！？：）】」』》^':
            return True
        # Emoji 范围（杂项符号、丁贝符、表情符号、补充符号等）
        if ord(last) >= 0x1F300:
            return True
        return False

    def _is_ollama_glm_backend(self) -> bool:
        """检测受 stop 误报影响的 Ollama 托管 GLM 模型。

        Ollama 可能将截断的输出误报为 finish_reason='stop'。
        检测依赖显式的 Ollama 签名：
        - 端口 11434（Ollama 默认）
        - base URL 中的 "ollama"（例如 ollama.local、/ollama/ 路径）
        - provider 显式设置为 "ollama"

        关键是它不匹配任意本地/私有端点（LiteLLM/sglang/vLLM/LM Studio 代理、
        Tailscale 盒子），它们正确报告 finish_reason，并且是 #13971 误报
        截断继续的来源。
        """
        model_lower = (self.model or "").lower()
        provider_lower = (self.provider or "").lower()
        if "glm" not in model_lower and provider_lower != "zai":
            return False
        if "ollama" in self._base_url_lower or ":11434" in self._base_url_lower:
            return True
        return provider_lower == "ollama"

    def _should_treat_stop_as_truncated(
        self,
        finish_reason: str,
        assistant_message,
        messages: Optional[list] = None,
    ) -> bool:
        """检测 Ollama 托管 GLM 模型的保守 stop→length 误报。"""
        if finish_reason != "stop" or self.api_mode != "chat_completions":
            return False
        if not self._is_ollama_glm_backend():
            return False
        if not any(
            isinstance(msg, dict) and msg.get("role") == "tool"
            for msg in (messages or [])
        ):
            return False
        if assistant_message is None or getattr(assistant_message, "tool_calls", None):
            return False

        content = getattr(assistant_message, "content", None)
        if not isinstance(content, str):
            return False

        visible_text = self._strip_think_blocks(content).strip()
        if not visible_text:
            return False
        if len(visible_text) < 20 or not re.search(r"\s", visible_text):
            return False

        return not self._has_natural_response_ending(visible_text)

    def _looks_like_codex_intermediate_ack(
        self,
        user_message: str,
        assistant_content: str,
        messages: List[Dict[str, Any]],
        require_workspace: bool = True,
    ) -> bool:
        """转发器 → agent/agent_runtime_helpers/looks_like_codex_intermediate_ack.py"""
        from agent.agent_runtime_helpers import looks_like_codex_intermediate_ack
        return looks_like_codex_intermediate_ack(
            self, user_message, assistant_content, messages, require_workspace
        )

    def _extract_reasoning(self, assistant_message) -> Optional[str]:
        """转发器 → agent/agent_runtime_helpers/extract_reasoning.py"""
        from agent.agent_runtime_helpers import extract_reasoning
        return extract_reasoning(self, assistant_message)

    def _cleanup_task_resources(self, task_id: str) -> None:
        """转发器 → agent/chat_completion_helpers/cleanup_task_resources.py"""
        from agent.chat_completion_helpers import cleanup_task_resources
        return cleanup_task_resources(self, task_id)

    # ------------------------------------------------------------------
    # 后台 memory/skill 审查 —— 提示词位于 agent.background_review
    # ------------------------------------------------------------------
    from agent.background_review import (
        _MEMORY_REVIEW_PROMPT,
        _SKILL_REVIEW_PROMPT,
        _COMBINED_REVIEW_PROMPT,
    )

    @staticmethod
    def _summarize_background_review_actions(
        review_messages: List[Dict],
        prior_snapshot: List[Dict],
        notification_mode: str = "on",
    ) -> List[str]:
        """转发器 → agent/background_review/summarize_background_review_actions.py"""
        from agent.background_review import summarize_background_review_actions
        return summarize_background_review_actions(
            review_messages,
            prior_snapshot,
            notification_mode=notification_mode,
        )

    def _spawn_background_review(
        self,
        messages_snapshot: List[Dict],
        review_memory: bool = False,
        review_skills: bool = False,
    ) -> None:
        """生成后台 memory/skill 审查线程。

        Thin wrapper — the heavy lifting lives in
        ``agent.background_review.spawn_background_review_thread`` which
        returns the thread target.  ``threading.Thread`` is constructed
        here so existing tests that patch ``run_agent.threading.Thread``
        keep working.
        """
        from agent.background_review import spawn_background_review_thread
        from tools.thread_context import propagate_context_to_thread
        target, _prompt = spawn_background_review_thread(
            self,
            messages_snapshot,
            review_memory=review_memory,
            review_skills=review_skills,
        )
        # 将活动配置文件携带到审查线程，以便 MEMORY.md / skill 审查写入
        # 落在正确的配置文件中（#54937）。
        t = threading.Thread(
            target=propagate_context_to_thread(target), daemon=True, name="bg-review"
        )
        t.start()

    def _build_memory_write_metadata(
        self,
        *,
        write_origin: Optional[str] = None,
        execution_context: Optional[str] = None,
        task_id: Optional[str] = None,
        tool_call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """转发器 → agent/background_review/build_memory_write_metadata.py"""
        from agent.background_review import build_memory_write_metadata
        return build_memory_write_metadata(
            self,
            write_origin=write_origin,
            execution_context=execution_context,
            task_id=task_id,
            tool_call_id=tool_call_id,
        )

    def _apply_persist_user_message_override(self, messages: List[Dict]) -> None:
        """在持久化/返回前重写当前 turn 的用户消息。

        Some call paths need an API-only user-message variant without letting
        that synthetic text leak into persisted transcripts or resumed session
        history. When an override is configured for the active turn, mutate the
        in-memory messages list in place so both persistence and returned
        history stay clean.  A paired timestamp override preserves the platform
        event time as message metadata, rather than embedding it in content.
        """
        idx = getattr(self, "_persist_user_message_idx", None)
        override = getattr(self, "_persist_user_message_override", None)
        timestamp = getattr(self, "_persist_user_message_timestamp", None)
        if idx is None or (override is None and timestamp is None):
            return
        if 0 <= idx < len(messages):
            msg = messages[idx]
            if isinstance(msg, dict) and msg.get("role") == "user":
                # 纯文本调用路径可能分别传递合成的面向 API 的提示词和更清晰的
                # 转录字符串。在 API 调用前，纯文本覆盖不能替换本地图像/音频
                # 块。然而，列表覆盖是原始干净的多模态负载（例如在排队的 /model
                # 注释前）
                # and 必须 replace the API-local list once the turn is final。
                # 预检压缩可以将此索引重新锚定到其内容与压缩摘要合并的消息（merge-summary-into-tail）。这不是意外：``reanchor_current_turn_user_idx`` 正是回退到最后一条用户行，因为合并重写了内容并
                # 精确匹配查找遗漏。用干净文本覆盖会从延续历史中丢弃摘要，而
                # 下一个 turn 从 —— 构建，下面的 DB 写入孪生已经拒绝的危险（见中的同级守卫
                # ``_flush_messages_to_session_db_unlocked``）。
                if (
                    override is not None
                    and not msg.get(COMPRESSED_SUMMARY_METADATA_KEY)
                    and (
                        not isinstance(msg.get("content"), list)
                        or isinstance(override, list)
                    )
                ):
                    msg["content"] = override
                if timestamp is not None:
                    msg["timestamp"] = timestamp

    def _persist_session(self, messages: List[Dict], conversation_history: List[Dict] = None):
        """在任何退出路径上将会话状态保存到 JSON 日志和 SQLite。

        Ensures conversations are never lost, even on errors or early returns.

        Trailing empty-response scaffolding is dropped from the live list in
        place (it is ephemeral junk the real transcript should shed). The
        persist user-message *override* is NOT applied here — it is resolved
        inside ``_flush_messages_to_session_db`` and written only to the DB row,
        never mutating the live message list used by the API call (#48677 is
        thus closed for every persist caller, not just this one).
        """
        # 脚手架移除会改变 live 列表（符合预期 —— 临时的
        # retry/failure sentinels 必须 not survive into the real transcript)。
        # Close 和 turn-start 持久化可以在不同的 CLI 线程上运行；下面的标记
        # 测试并追加必须是一个临界区，否则两者都可能观察到同一个未标记的 dict 并
        # 写入重复的持久化行。
        from agent.agent_runtime_helpers import note_turn_persisted

        persist_lock = getattr(self, "_session_persist_lock", None)

        def _persist_and_drain() -> None:
            self._drop_trailing_empty_response_scaffolding(messages)
            self._session_messages = messages
            self._save_session_log(messages)
            self._flush_messages_to_session_db(messages, conversation_history)
            # 在每个持久化点（turn 完成 + 错误退出）排空异步 token 计数增量，
            # 这样此行后的崩溃最多丢失飞行中 API 调用的增量。当没有排队时是廉价的
            # 空操作。
            if self._session_db is not None:
                self._session_db.flush_token_counts()
            note_turn_persisted(self)

        if persist_lock is None:
            _persist_and_drain()
            return

        with persist_lock:
            _persist_and_drain()

    def _drop_trailing_empty_response_scaffolding(self, messages: List[Dict]) -> None:
        """从转录尾部移除私有的空响应重试/失败脚手架。

        Also rewinds past any trailing tool-result / assistant(tool_calls) pair
        that the failed iteration left hanging. Without this, the tail ends at
        a raw ``tool`` message and the next user turn lands as
        ``...tool, user, user`` — a protocol-invalid sequence that most
        providers silently reject (returns empty content), causing the
        empty-retry loop to fire forever. (issue number to be backfilled once filed)
        """
        # 第 1 遍：strip the flagged scaffolding messages themselves.
        dropped_scaffolding = False
        while (
            messages
            and isinstance(messages[-1], dict)
            and (
                messages[-1].get("_empty_recovery_synthetic")
                or messages[-1].get("_empty_terminal_sentinel")
            )
        ):
            messages.pop()
            dropped_scaffolding = True

        # 第 2 遍：if we stripped scaffolding, rewind through any trailing
        # 工具结果消息加上产生它们的助手（tool_calls）消息。这保持了角色交替，
        # 以便下一个用户消息跟在用户或助手消息之后，而不是孤立工具
        # 结果。仅在实际存在脚手架时运行 —— 正常的对话尾部（进行中的真实工具循环）
        # 不会被触及。
        if not dropped_scaffolding:
            return

        # 丢弃任何尾随的工具结果消息
        while (
            messages
            and isinstance(messages[-1], dict)
            and messages[-1].get("role") == "tool"
        ):
            messages.pop()

        # Drop the assistant message that issued the 工具调用s, if the tail
        # 现在以 assistant-with-tool_calls 结尾（拥有工具结果的那个对）
        # just-popped 工具结果s). Without this, the tail is
        # ``assistant(tool_calls=...)`` 没有工具回答，某些提供商也会拒绝。
        if (
            messages
            and isinstance(messages[-1], dict)
            and messages[-1].get("role") == "assistant"
            and messages[-1].get("tool_calls")
        ):
            messages.pop()

    def _repair_message_sequence(self, messages: List[Dict]) -> int:
        """转发器 → agent/agent_runtime_helpers/repair_message_sequence.py"""
        from agent.agent_runtime_helpers import repair_message_sequence
        return repair_message_sequence(self, messages)

    def _flush_messages_to_session_db(
        self,
        messages: List[Dict],
        conversation_history: Optional[List[Dict]] = None,
    ):
        """序列化每个 Agent 的直接和轮次边界会话刷新。"""
        persist_lock = getattr(self, "_session_persist_lock", None)
        if persist_lock is None:
            return self._flush_messages_to_session_db_unlocked(messages, conversation_history)
        with persist_lock:
            return self._flush_messages_to_session_db_unlocked(messages, conversation_history)

    def _flush_messages_to_session_db_unlocked(
        self,
        messages: List[Dict],
        conversation_history: Optional[List[Dict]] = None,
    ):
        """Persist any un-flushed messages to the SQLite 会话存储.

        Deduplicates via an intrinsic ``_DB_PERSISTED_MARKER`` stamped on each
        written message dict, so repeated calls (from multiple exit paths) only
        write truly new messages — preventing the duplicate-write bug (#860)
        without relying on positional slices that can drift after
        message-sequence repair, and without a retained ``id(msg)`` set that
        CPython could alias onto a freed-then-reused address (#50372). The
        ``_flushed_db_message_ids`` attribute is now only a one-shot seed
        (translated to markers, then cleared each flush), not a persisted set.

        Note: the marker is stamped on the live/shared conversation dict, which
        correctly makes re-persistence idempotent across turns. No code path
        edits a persisted message's content/role in place expecting a re-write
        (in-place compaction resets the seed and re-diffs by identity).
        """
        # 持久化隔离的 Agent（例如后台 skill/memory 审查分支）绝不能写入标准会话存储。
        # 分支共享父级的 session_id 以利用 prompt 缓存，所以此处的任何写入都会将它的
        # harness turn（"Review the conversation above and update the skill library…"）
        # 放在用户的真实会话历史中，下一个 live turn 会将其作为指令重读，Agent
        # 在任何 DB 触碰之前就会"变成"curator。硬停止。
        if getattr(self, "_persist_disabled", False):
            return None
        if not self._session_db:
            return None
        # 持久化用户消息覆盖（#48677 关键点）：历史上这会原地改变 live `messages` 列表，
        # 在崩溃恢复持久化（在 API 调用构建之前运行）中，会从 live 用户消息中剥离观察到的
        # 群聊上下文并静默丢弃。相反，在此处解析覆盖并仅将其应用到写入 DB 的值（见下方
        # 写入循环）；live dict 永远不会被改变，所以每个调用者（早期持久化、循环中刷新、
        # /resume、/branch）都被统一保护。时间戳覆盖是元数据，同样只应用到写入的行。
        _ov_idx = getattr(self, "_persist_user_message_idx", None)
        _ov_content = getattr(self, "_persist_user_message_override", None)
        _ov_timestamp = getattr(self, "_persist_user_message_timestamp", None)
        try:
            # 如果之前的尝试临时失败，重试创建行。
            if not self._session_db_created:
                self._ensure_db_session()
            # 位置刷新曾用于在 max(len(conversation_history), _last_flushed_db_idx) 处切片。
            # 那假设 live `messages` 列表是原始历史加上新的尾部。repair_message_sequence
            # 可以在最终刷新前收缩/合并历史副本，使 len(conversation_history) 大于
            # len(messages)；切片就变成空的，交付的助手回答永远到不了 state.db（#46053）。
            #
            # 使用内在的每消息标记而非 id(msg) 追踪持久化。`messages` 是 `conversation_history`
            # 的浅拷贝，所以历史 dict 通过身份被跳过，这个 turn 中追加的新 dict 只写入一次，
            # 即使 repair 在它们周围压缩列表也是如此。与 id() 键控的 set 不同，绑定到 dict 的
            # 标记不能别名到释放后重用的地址，所以真实的 turn 永远不会被静默跳过（见 _DB_PERSISTED_MARKER）。
            #
            # `self._flushed_db_message_ids` 仍被当作*一次性*种子尊重：外部调用者（网关关闭、
            # 测试）在刷新前立即用 {id(m) for m in already_persisted} 填充它，此时那些对象
            # 还活着 —— 所以 id 在那个瞬间是有效的。我们将种子转换为持久标记然后清除该 set，
            # 所以过时的 id 永远不会跨 turn 累积并别名到未来的消息。
            current_session_id = getattr(self, "session_id", None)
            flushed_session_id = getattr(self, "_flushed_db_message_session_id", None)
            if flushed_session_id != current_session_id or self._last_flushed_db_idx == 0:
                seed_ids = set()
            else:
                seed_ids = getattr(self, "_flushed_db_message_ids", None)
                if not isinstance(seed_ids, set):
                    seed_ids = set()
            self._flushed_db_message_session_id = current_session_id
            history_ids = {
                id(item) for item in (conversation_history or [])
                if isinstance(item, dict)
            }

            for _msg_idx, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    continue
                # 绝不将临时恢复脚手架写入会话存储。刷新是仅追加的（它只通过身份追踪
                # 推进 _last_flushed_db_idx），所以由 turn 中期持久化提交的合成消息在 turn
                # 结束时从内存列表中删除时不能被撤销 —— 恢复的转录会将合成的
                # "(empty)"/nudge/thinking-prefill turn 当作真实上下文重放。无论位置如何都跳过：
                # 已回答的 nudge 将合成对埋在列表中间，而不仅仅是在尾部。
                if _is_ephemeral_scaffolding(msg):
                    continue
                if msg.get(_DB_PERSISTED_MARKER):
                    continue
                # 已经持久化的消息：要么来自加载的历史副本，要么由调用者播种。标记它们
                # 以便未来的刷新跳过它们，不用再查询任何 id() set。
                if id(msg) in history_ids or id(msg) in seed_ids:
                    msg[_DB_PERSISTED_MARKER] = True
                    continue
                role = msg.get("role", "unknown")
                content = msg.get("content")
                # api_content 侧车：当发送的字节与干净内容不同时（由 turn 前言为预取/插件
                # 注入盖章）。逐字写入，以便重放可以逐字节重现发送的前缀。
                _row_api_content = msg.get("api_content")
                if not isinstance(_row_api_content, str):
                    _row_api_content = None
                _row_timestamp = msg.get("timestamp")
                # 仅将持久化覆盖应用到 THIS 行的写入值（从不到 live dict）。多模态覆盖是
                # 对 API 本地记录负载的完整干净替换。但对于列表负载，保留历史的纯文本守卫：
                # 纯文本覆盖不能擦除其图像/音频转录摘要。
                # close 安全网可能在 turn 设置仍拥有其暂存的 CLI dict 时刷新缩短的快照。
                # 在这种情况下，正常的 turn 索引指向完整历史，而不是这个列表；通过识别同一个
                # dict 来保留 API 本地覆盖。
                pending_cli_message = getattr(self, "_pending_cli_user_message", None)
                is_current_turn_user = (
                    _ov_idx == _msg_idx or msg is pending_cli_message
                )
                if is_current_turn_user and msg.get("role") == "user":
                    # 预检压缩可以将覆盖索引重新锚定到其内容与压缩摘要合并的消息
                    # （merge-summary-into-tail）。用干净网关文本覆盖会静默丢弃持久化转录
                    # 中的摘要。线路已经一致 —— 合并弹出了侧车，合并的内容就是要发送的 ——
                    # 所以保留它。
                    if (
                        _ov_content is not None
                        and (not isinstance(content, list) or isinstance(_ov_content, list))
                        and not msg.get(COMPRESSED_SUMMARY_METADATA_KEY)
                    ):
                        # live 内容是 API 调用发送的内容；覆盖是清理后的转录值。如果它们不同
                        # 且没有注入已经盖章侧车，将发送的字节保留在 api_content 中，以便重放
                        # 匹配线路（#48677 分歧，缓存前缀也已关闭）。
                        if (
                            _row_api_content is None
                            and isinstance(content, str)
                            and content != _ov_content
                        ):
                            _row_api_content = content
                        content = _ov_content
                    if _ov_timestamp is not None:
                        _row_timestamp = _ov_timestamp
                # Store the sidecar 仅 when it actually differs。
                if _row_api_content == content:
                    _row_api_content = None
                # 加载时的清理分歧：get_messages_as_conversation 通过 ``sanitize_context(content).strip()``
                # 重放 user/assistant 行，所以清理会重写的的内容（回显/粘贴的 <memory-context>
                # 围栏或系统注释）在会话重载后会重放不同的字节，即使 THIS turn 逐字发送了它。
                # 在侧车中捕获发送的字节，以便重载的会话重放线路上实际的内容。以线路形式比较
                # （两边都 .strip()-ed —— api_messages 构建会剥离每个传出的内容字符串），
                # 所以单纯的周围空白不会增长多余的侧车。
                if (
                    _row_api_content is None
                    and role in ("user", "assistant")
                    and isinstance(content, str)
                    and content
                    and sanitize_context(content).strip() != content.strip()
                ):
                    _row_api_content = content
                # 持久化多模态工具结果仅为文本摘要 —— base64 图像会使会话 DB 膨胀，
                # 且对跨会话重放无用。
                if _is_multimodal_tool_result(content):
                    content = _multimodal_text_summary(content)
                elif isinstance(content, list):
                    # OpenAI 风格内容部分列表：剥离图像，保留文本。
                    _txt = []
                    for p in content:
                        if isinstance(p, dict) and p.get("type") == "text":
                            _txt.append(str(p.get("text", "")))
                        elif isinstance(p, dict) and p.get("type") in {"image", "image_url", "input_image"}:
                            _txt.append("[screenshot]")
                    content = "\n".join(_txt) if _txt else None
                tool_calls_data = None
                if hasattr(msg, "tool_calls") and isinstance(msg.tool_calls, list) and msg.tool_calls:
                    tool_calls_data = [
                        {"name": tc.function.name, "arguments": tc.function.arguments}
                        for tc in msg.tool_calls
                    ]
                elif isinstance(msg.get("tool_calls"), list):
                    tool_calls_data = msg["tool_calls"]
                self._session_db.append_message(
                    session_id=self.session_id,
                    role=role,
                    content=content,
                    tool_name=msg.get("tool_name"),
                    tool_calls=tool_calls_data,
                    tool_call_id=msg.get("tool_call_id"),
                    finish_reason=msg.get("finish_reason"),
                    reasoning=msg.get("reasoning") if role == "assistant" else None,
                    reasoning_content=msg.get("reasoning_content") if role == "assistant" else None,
                    reasoning_details=msg.get("reasoning_details") if role == "assistant" else None,
                    codex_reasoning_items=msg.get("codex_reasoning_items") if role == "assistant" else None,
                    codex_message_items=msg.get("codex_message_items") if role == "assistant" else None,
                    timestamp=_row_timestamp,
                    api_content=_row_api_content,
                    display_kind=(
                        "hidden"
                        if msg.get(COMPRESSED_SUMMARY_METADATA_KEY)
                        and not msg.get("_compressed_summary_has_user_turn")
                        else msg.get("display_kind")
                    ),
                    display_metadata=msg.get("display_metadata"),
                    compression_lock_holder=getattr(
                        self, "_active_compression_lock_holder", None
                    ),
                )
                msg[_DB_PERSISTED_MARKER] = True
            # 内在标记现在是唯一的事实来源。重置一次性种子，以便没有 id() 比这次刷新
            # 活得更久，从而别名到下一 turn 在回收地址分配的消息。
            self._flushed_db_message_ids = set()
            self._last_flushed_db_idx = len(messages)
            return True
        except Exception as e:
            logger.warning("Session DB append_message failed: %s", e)
            return False

    def _get_messages_up_to_last_assistant(self, messages: List[Dict]) -> List[Dict]:
        """
        Get messages up to (but not including) the last assistant turn.
        
        This is used when we need to "roll back" to the last successful point
        in the conversation, typically when the final assistant message is
        incomplete or malformed.
        
        Args:
            messages: Full message list
            
        Returns:
            Messages up to the last complete assistant turn (ending with user/tool message)
        """
        if not messages:
            return []
        
        # 查找最后一条助手消息的索引
        last_assistant_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                last_assistant_idx = i
                break
        
        if last_assistant_idx is None:
            # 未找到助手消息，返回所有消息
            return messages.copy()
        
        # 返回到最后一条助手消息之前（不包括它）的所有内容
        return messages[:last_assistant_idx]

    def _format_tools_for_system_message(self) -> str:
        """转发器 → agent/system_prompt/format_tools_for_system_message.py"""
        from agent.system_prompt import format_tools_for_system_message
        return format_tools_for_system_message(self)

    def _convert_to_trajectory_format(self, messages: List[Dict[str, Any]], user_query: str, completed: bool) -> List[Dict[str, Any]]:
        """转发器 → agent/agent_runtime_helpers/convert_to_trajectory_format.py"""
        from agent.agent_runtime_helpers import convert_to_trajectory_format
        return convert_to_trajectory_format(self, messages, user_query, completed)

    def _save_trajectory(self, messages: List[Dict[str, Any]], user_query: str, completed: bool):
        """
        Save conversation trajectory to JSONL file.
        
        Args:
            messages (List[Dict]): Complete message history
            user_query (str): Original user query
            completed (bool): Whether the conversation completed successfully
        """
        if not self.save_trajectories:
            return
        
        trajectory = self._convert_to_trajectory_format(messages, user_query, completed)
        _save_trajectory_to_file(trajectory, self.model, completed)

    @staticmethod
    def _is_entitlement_failure(
        error_context: Optional[Dict[str, Any]],
        status_code: Optional[int],
    ) -> bool:
        """Detect subscription/entitlement 403s that masquerade as auth failures.

        Returned True only when the body text matches a known entitlement
        shape AND the status is 401/403.  Refreshing an OAuth token cannot
        fix an unsubscribed account, so callers should surface the error
        instead of looping the credential pool.

        Current matches:
          * xAI OAuth: "do not have an active Grok subscription" /
            "out of available resources" / "does not have permission" + "grok"

        Disambiguator for xAI (#29344): the same ``code`` text ("The caller
        does not have permission to execute the specified operation") is
        returned for BOTH an unsubscribed account AND a stale OAuth access
        token.  xAI ships an explicit signal in the ``error`` field that
        tells the two apart: a ``[WKE=unauthenticated:...]`` suffix (and/or
        the ``OAuth2 access token could not be validated`` phrasing) means
        the credentials failed validation — that's recoverable by refreshing
        the token, NOT by surfacing an entitlement message.  When either
        signal is present we return False eagerly so the credential-pool
        refresh path runs, letting long-running TUI sessions recover from
        stale tokens without an exit/reopen cycle.

        Extend here for new providers as we discover them (Anthropic's
        Claude Max OAuth entitlement errors look distinct enough today that
        the existing 1M-context-beta branch handles them; revisit if other
        subscription tiers start producing the same loop signature).
        """
        if status_code not in {401, 403, None}:
            return False
        if not isinstance(error_context, dict):
            return False
        # 构建一个单一的小写干草堆，覆盖 body 可能落入的每种字段形状。
        # ``_extract_api_error_context`` 标准化到 ``message``/``reason``，但调用者
        # （和测试套件）也可能用 ``code``/``error`` 键给我们原始 body；两者都覆盖，
        # 这样下面的 WKE 消歧器无论入口点如何都会触发。
        message = str(error_context.get("message") or "").lower()
        reason = str(error_context.get("reason") or "").lower()
        code = str(error_context.get("code") or "").lower()
        err = str(error_context.get("error") or "").lower()
        haystack = f"{message} {reason} {code} {err}"
        if not haystack.strip():
            return False
        # xAI 对"过期 token"与"未订阅账户"的权威消歧器。两种条件共享相同的
        # permission-denied ``code`` text; 仅 one carries this suffix。
        # 在权限关键字检查前退出，这样过期的 OAuth token 通过凭证刷新路径路由，
        # 而不是 surface-error-as-entitlement 路径。见 #29344 了解此修复关闭的
        # 长时间运行的 TUI 失败模式。
        if "[wke=unauthenticated:" in haystack:
            return False
        if "oauth2 access token could not be validated" in haystack:
            return False
        if "do not have an active grok subscription" in haystack:
            return True
        if "out of available resources" in haystack and "grok" in haystack:
            return True
        if "does not have permission" in haystack and "grok" in haystack:
            return True
        return False

    @staticmethod
    def _decorate_xai_entitlement_error(detail: str) -> str:
        """Append a neutral hint when xAI's OAuth surface returns the
        permission-denied 403.

        xAI's ``/v1/responses`` endpoint replies to several distinct failure
        modes with the SAME body::

            {"code": "The caller does not have permission to execute the
             specified operation", "error": "You have either run out of
             available resources or do not have an active Grok subscription.
             Manage subscriptions at https://grok.com/?_s=usage or subscribe
             at https://grok.com/supergrok"}

        That body covers several real causes we cannot distinguish without
        more info from xAI.  The most common (and least obvious) one is
        that **X Premium+ does NOT include API access** — only standalone
        SuperGrok subscribers can use Hermes against xai-oauth.  Lots of
        users see Grok in their X app, assume it works here too, and hit
        this 403 with no idea why.  Lead the hint with that.

        Other possible causes:
          * No Grok subscription at all
          * SuperGrok tier doesn't include the requested model (e.g.
            grok-4.3 may need a higher tier)
          * Monthly quota exhausted (the ``?_s=usage`` URL hints at this)

        Surface the raw xAI text verbatim and point at
        https://grok.com/?_s=usage where the user can see WHICH applies.

        Matched once per detail string — won't double-decorate if the
        upstream already concatenated the same text.
        """
        if not detail:
            return detail
        lower = detail.lower()
        is_entitlement = (
            "do not have an active grok subscription" in lower
            or ("out of available resources" in lower and "grok" in lower)
            or ("does not have permission" in lower and "grok" in lower)
        )
        if not is_entitlement:
            return detail
        hint = (
            " — xAI rejected this OAuth account. NOTE: X Premium+ does NOT "
            "include xAI API access — only standalone SuperGrok subscribers "
            "can use this provider. Other possible causes: no Grok "
            "subscription, your tier doesn't include this model, or your "
            "quota is exhausted. Check https://grok.com/?_s=usage to see "
            "which, or run `/model` to switch providers."
        )
        # 幂等性：通过提示独有的子串检测先前的装饰（不存在于 xAI 自己的 body 文本中）。
        if "X Premium+ does NOT include" in detail:
            return detail
        return f"{detail}{hint}"

    @staticmethod
    def _coerce_api_error_detail(value: Any) -> str:
        """为结构化提供商错误字段返回显示安全的字符串。"""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("message", "detail", "error", "code", "type"):
                nested = value.get(key)
                if isinstance(nested, str) and nested.strip():
                    return nested
            for key in ("message", "detail", "error", "code", "type"):
                if key in value:
                    nested_detail = AIAgent._coerce_api_error_detail(value[key])
                    if nested_detail:
                        return nested_detail
            try:
                return json.dumps(value, ensure_ascii=False, sort_keys=True)
            except TypeError:
                return str(value)
        if isinstance(value, (list, tuple)):
            parts = [
                AIAgent._coerce_api_error_detail(item)
                for item in value
            ]
            return "; ".join(part for part in parts if part)
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _summarize_api_error(error: Exception) -> str:
        """从 API 错误中提取人类可读的单行消息。

        Handles Cloudflare HTML error pages (502, 503, etc.) by pulling the
        <title> tag instead of dumping raw HTML.  Falls back to a truncated
        str(error) for everything else.
        """
        raw = str(error)

        if (
            isinstance(error, ValueError)
            and "expected ident at line" in raw.lower()
        ):
            return f"Malformed provider streaming response: {raw[:300]}"

        # Cloudflare / 代理 HTML 页面：抓取 <title> 作为干净摘要
        if "<!DOCTYPE" in raw or "<html" in raw:
            m = re.search(r"<title[^>]*>([^<]+)</title>", raw, re.IGNORECASE)
            title = m.group(1).strip() if m else "HTML error page (title not found)"
            # 同时捕获 Cloudflare Ray ID（如果存在）
            ray = re.search(r"Cloudflare Ray ID:\s*<strong[^>]*>([^<]+)</strong>", raw)
            ray_id = ray.group(1).strip() if ray else None
            status_code = getattr(error, "status_code", None)
            parts = []
            if status_code:
                parts.append(f"HTTP {status_code}")
            parts.append(title)
            if ray_id:
                parts.append(f"Ray {ray_id}")
            return " — ".join(parts)

        # GeminiAPIError (agent/gemini_native_adapter.py) 已经组合了一个干净的单行消息，
        # 并可能附加了可操作的指导（免费层 429、遗留 Standard-key 401）。优先使用它的消息
        # 而不是下面重新提取原始响应体，那样会剥离该指导。
        if type(error).__name__ == "GeminiAPIError":
            return redact_sensitive_text(raw[:1000])

        # 来自 OpenAI/Anthropic SDK 的 JSON body 错误
        body = getattr(error, "body", None)
        if isinstance(body, dict):
            msg = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("message")
            if msg:
                status_code = getattr(error, "status_code", None)
                prefix = f"HTTP {status_code}: " if status_code else ""
                msg = AIAgent._coerce_api_error_detail(msg)
                return AIAgent._decorate_xai_entitlement_error(f"{prefix}{msg[:300]}")

        # SDK 可能在 httpx 仍有负载时留下空 body（#36109）。
        # 返回前脱敏：原始提供商/代理错误 body 受攻击者影响，可能回显
        # Authorization / x-api-key / request JSON，否则会泄漏到 final_response +
        # 日志（此路径相比旧的空 body "HTTP 400" 字符串扩大了暴露面）。
        response = getattr(error, "response", None)
        if response is not None:
            try:
                snippet = (getattr(response, "text", None) or "").strip()
            except Exception:
                snippet = ""
            if snippet:
                status_code = getattr(error, "status_code", None)
                prefix = f"HTTP {status_code}: " if status_code else ""
                try:
                    payload = json.loads(snippet)
                except (json.JSONDecodeError, TypeError):
                    payload = None
                if isinstance(payload, dict):
                    err = payload.get("error")
                    if isinstance(err, dict) and err.get("message"):
                        return redact_sensitive_text(f"{prefix}{str(err['message'])[:300]}")
                    if payload.get("message"):
                        return redact_sensitive_text(f"{prefix}{str(payload['message'])[:300]}")
                return redact_sensitive_text(f"{prefix}{snippet[:300]}")

        # 回退：截断原始字符串，但比 200 字符给更多空间
        status_code = getattr(error, "status_code", None)
        prefix = f"HTTP {status_code}: " if status_code else ""
        return AIAgent._decorate_xai_entitlement_error(f"{prefix}{raw[:500]}")

    def _mask_api_key_for_logs(self, key: Any) -> Optional[str]:
        # Azure Foundry Entra ID bearer 提供者是 callable —— 绝不在日志路径中调用它们；
        # 识别认证表面即可。
        if callable(key) and not isinstance(key, str):
            return "<entra-id-bearer>"
        if not key:
            return None
        if len(key) <= 12:
            return "***"
        return f"{key[:8]}...{key[-4:]}"

    def _clean_error_message(self, error_msg: str) -> str:
        """
        Clean up error messages for user display, removing HTML content and truncating.
        
        Args:
            error_msg: Raw error message from API or exception
            
        Returns:
            Clean, user-friendly error message
        """
        if not error_msg:
            return "Unknown error"
            
        # 移除 HTML 内容（CloudFlare 和网关错误页面常见）
        if error_msg.strip().startswith('<!DOCTYPE html') or '<html' in error_msg:
            return "Service temporarily unavailable (HTML error page returned)"
            
        # 移除换行符和过多空白
        cleaned = ' '.join(error_msg.split())
        
        # 如果太长则截断
        if len(cleaned) > 150:
            cleaned = cleaned[:150] + "..."
            
        return cleaned

    @staticmethod
    def _extract_api_error_context(error: Exception) -> Dict[str, Any]:
        """转发器 → agent/agent_runtime_helpers/extract_api_error_context.py"""
        from agent.agent_runtime_helpers import extract_api_error_context
        return extract_api_error_context(error)

    def _usage_summary_for_api_request_hook(self, response: Any) -> Optional[Dict[str, Any]]:
        """为 post_api_request 插件提供的 token 桶（无原始 response 对象）。"""
        if response is None:
            return None
        raw_usage = getattr(response, "usage", None)
        if not raw_usage:
            return None
        from dataclasses import asdict

        cu = normalize_usage(raw_usage, provider=self.provider, api_mode=self.api_mode)
        summary = asdict(cu)
        summary.pop("raw_usage", None)
        summary["prompt_tokens"] = cu.prompt_tokens
        summary["total_tokens"] = cu.total_tokens
        return summary

    @staticmethod
    def _hook_payload_max_chars() -> int:
        raw = os.getenv("HERMES_PLUGIN_PAYLOAD_MAX_CHARS", "50000")
        try:
            return max(1000, int(raw))
        except (TypeError, ValueError):
            return 50000

    @staticmethod
    def _is_sensitive_hook_key(key: Any) -> bool:
        if not isinstance(key, str):
            return False
        lowered = key.lower().replace("-", "_")
        exact = {
            "api_key",
            "authorization",
            "proxy_authorization",
            "cookie",
            "set_cookie",
        }
        return lowered in exact or lowered.endswith("_api_key")

    @classmethod
    def _hook_jsonable(
        cls,
        value: Any,
        *,
        depth: int = 0,
        max_depth: int = 8,
        max_string: int = 8000,
        max_sequence: int = 200,
    ) -> Any:
        if depth > max_depth:
            return f"<{type(value).__name__} depth limit>"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            if len(value) > max_string:
                return value[:max_string] + f"...[truncated {len(value) - max_string} chars]"
            return value
        if isinstance(value, (bytes, bytearray)):
            return f"<{len(value)} bytes>"
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            for idx, (key, item) in enumerate(value.items()):
                if idx >= max_sequence:
                    out["_truncated_items"] = len(value) - max_sequence
                    break
                str_key = str(key)
                if cls._is_sensitive_hook_key(str_key):
                    out[str_key] = "<redacted>"
                else:
                    out[str_key] = cls._hook_jsonable(
                        item,
                        depth=depth + 1,
                        max_depth=max_depth,
                        max_string=max_string,
                        max_sequence=max_sequence,
                    )
            return out
        if isinstance(value, (list, tuple, set)):
            seq = list(value)
            out = [
                cls._hook_jsonable(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_string=max_string,
                    max_sequence=max_sequence,
                )
                for item in seq[:max_sequence]
            ]
            if len(seq) > max_sequence:
                out.append({"_truncated_items": len(seq) - max_sequence})
            return out
        try:
            if hasattr(value, "model_dump"):
                try:
                    dumped = value.model_dump(mode="json")
                except TypeError:
                    dumped = value.model_dump()
                return cls._hook_jsonable(
                    dumped,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_string=max_string,
                    max_sequence=max_sequence,
                )
        except Exception:
            pass
        try:
            from dataclasses import asdict, is_dataclass
            if is_dataclass(value):
                return cls._hook_jsonable(
                    asdict(value),
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_string=max_string,
                    max_sequence=max_sequence,
                )
        except Exception:
            pass
        if isinstance(value, SimpleNamespace):
            return cls._hook_jsonable(
                vars(value),
                depth=depth + 1,
                max_depth=max_depth,
                max_string=max_string,
                max_sequence=max_sequence,
            )
        if hasattr(value, "__dict__"):
            try:
                public_attrs = {
                    k: v
                    for k, v in vars(value).items()
                    if not str(k).startswith("_")
                }
                return cls._hook_jsonable(
                    public_attrs,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_string=max_string,
                    max_sequence=max_sequence,
                )
            except Exception:
                pass
        return str(value)[:max_string]

    @classmethod
    def _sanitize_hook_payload(cls, value: Any) -> Any:
        payload = cls._hook_jsonable(value)
        limit = cls._hook_payload_max_chars()
        try:
            encoded = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            return str(payload)[:limit]
        if len(encoded) <= limit:
            return payload
        payload = cls._hook_jsonable(value, max_string=1000, max_sequence=50)
        try:
            encoded = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            return str(payload)[:limit]
        if len(encoded) <= limit:
            return payload
        return {
            "_truncated": True,
            "original_type": type(value).__name__,
            "preview": encoded[:limit],
        }

    def _api_request_payload_for_hook(self, api_kwargs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        body = {
            key: value
            for key, value in (api_kwargs or {}).items()
            if key not in {"timeout", "http_client"}
        }
        return self._sanitize_hook_payload(
            {
                "method": "POST",
                "body": body,
            }
        )

    def _api_response_payload_for_hook(
        self,
        response: Any,
        assistant_message: Any,
        *,
        finish_reason: Optional[str],
    ) -> Dict[str, Any]:
        # ``tool_calls`` 是提供商 SDK 对象的原始列表（例如 OpenAI
        # ``ChatCompletionMessageToolCall``）。我们故意将原始对象交给
        # ``_sanitize_hook_payload`` 并依赖 ``_hook_jsonable`` 通过
        # ``model_dump`` / ``__dict__`` / dataclass 内省进行规范化 ——
        # 清理器的未来重构必须保留该能力，否则钩子订阅者将收到不透明的
        # ``str(obj)`` 块。
        tool_calls = getattr(assistant_message, "tool_calls", None) or []
        return self._sanitize_hook_payload(
            {
                "model": getattr(response, "model", None),
                "finish_reason": finish_reason,
                "assistant_message": {
                    "role": getattr(assistant_message, "role", "assistant"),
                    "content": getattr(assistant_message, "content", None),
                    "tool_calls": tool_calls,
                },
                "usage": self._usage_summary_for_api_request_hook(response),
            }
        )

    def _invoke_api_request_error_hook(
        self,
        *,
        task_id: str,
        turn_id: str,
        api_request_id: str,
        api_call_count: int,
        api_start_time: float,
        api_kwargs: Optional[Dict[str, Any]],
        error_type: str,
        error_message: str,
        status_code: Optional[int] = None,
        retry_count: Optional[int] = None,
        max_retries: Optional[int] = None,
        retryable: Optional[bool] = None,
        reason: Optional[str] = None,
    ) -> None:
        # 延迟模块导入（非 from-import），以便测试可以在此调用站点替换生命周期
        # 调度。首次调用后，导入就是 ``sys.modules`` 字典查找，所以重试不会付出任何
        # 实际成本。
        try:
            from hermes_cli import lifecycle as _lifecycle

            if not _lifecycle.has_hook("api_request_error"):
                return
            ended_at = time.time()
            _lifecycle.invoke_hook(
                "api_request_error",
                task_id=task_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                session_id=self.session_id or "",
                platform=self.platform or "",
                model=self.model,
                provider=self.provider,
                base_url=self.base_url,
                api_mode=self.api_mode,
                api_call_count=api_call_count,
                api_duration=ended_at - api_start_time,
                started_at=api_start_time,
                ended_at=ended_at,
                status_code=status_code,
                retry_count=retry_count,
                max_retries=max_retries,
                retryable=retryable,
                reason=reason,
                error={
                    "type": error_type,
                    "message": error_message,
                },
                request=self._api_request_payload_for_hook(api_kwargs),
            )
        except Exception:
            pass

    def _dump_api_request_debug(
        self,
        api_kwargs: Dict[str, Any],
        *,
        reason: str,
        error: Optional[Exception] = None,
    ) -> Optional[Path]:
        """转发器 → agent/agent_runtime_helpers/dump_api_request_debug.py"""
        from agent.agent_runtime_helpers import dump_api_request_debug
        return dump_api_request_debug(self, api_kwargs, reason=reason, error=error)

    @staticmethod
    def _clean_session_content(content: str) -> str:
        """将 REASONING_SCRATCHPAD 转换为 think 标签并清理空白。"""
        if not content:
            return content
        content = convert_scratchpad_to_think(content)
        content = re.sub(r'\n+(<think>)', r'\n\1', content)
        content = re.sub(r'(</think>)\n+', r'\1\n', content)
        return content.strip()

    @staticmethod
    def _redact_message_content(content):
        """Apply secret redaction to message content (str or list-of-parts).

        Handles both plain-string content and the OpenAI/Anthropic multimodal
        shape where ``content`` is a list of ``{"type": "text", "text": ...}``
        / ``{"type": "image_url", ...}`` / ``{"type": "input_text", "content": ...}``
        parts. Image / binary parts are left untouched; only text fields are
        passed through ``redact_sensitive_text``.

        Respects ``HERMES_REDACT_SECRETS`` via ``redact_sensitive_text`` —
        when disabled the helper is effectively a no-op.
        """
        if content is None:
            return content
        if isinstance(content, str):
            return redact_sensitive_text(content)
        if isinstance(content, list):
            redacted = []
            for part in content:
                if isinstance(part, dict):
                    part = dict(part)
                    if isinstance(part.get("text"), str):
                        part["text"] = redact_sensitive_text(part["text"])
                    if isinstance(part.get("content"), str):
                        part["content"] = redact_sensitive_text(part["content"])
                redacted.append(part)
            return redacted
        return content

    def _save_session_log(self, messages: List[Dict[str, Any]] = None):
        """Optional per-session JSON snapshot writer.

        Gated by ``sessions.write_json_snapshots`` (default False).  state.db
        is the canonical message store; this writer exists only for users
        whose external tooling consumes ``~/.hermes/sessions/session_{sid}.json``
        directly.  When the flag is off this is a fast no-op.

        When enabled, rewrites the snapshot after every persistence point with
        the full message list (assistant content normalized via
        ``_clean_session_content`` to convert REASONING_SCRATCHPAD to think
        tags).  The truncation guard ("don't overwrite a larger log with
        fewer messages") is preserved so resume + branch don't clobber a
        fuller existing snapshot.
        """
        if not getattr(self, "_session_json_enabled", False):
            return
        messages = messages or self._session_messages
        if not messages:
            return

        # 每次调用都重新派生目标路径，以便 /branch 和 /compress 的会话 ID 变更
        # 落在正确的文件中，无需在调用站点重新指向。将会话 ID 清理为单个无路径穿越
        # 的路径段 —— 会话 ID 可能来自不可信输入（X-Hermes-Session-Id 头），不能逃逸
        # sessions 目录。
        try:
            safe_sid = _safe_session_filename_component(self.session_id)
            log_file = self.logs_dir / f"session_{safe_sid}.json"
        except Exception:
            return

        try:
            cleaned = []
            for msg in messages:
                # 镜像 SQLite 刷新：临时恢复脚手架是
                # internal retry state, 绝不 durable transcript content。
                if _is_ephemeral_scaffolding(msg):
                    continue
                if msg.get("role") == "assistant" and msg.get("content"):
                    msg = dict(msg)
                    msg["content"] = self._clean_session_content(msg["content"])
                # 纵深防御：持久化前从每个消息内容中脱敏凭证。捕获可能泄漏到助手响应、
                # 工具输出或用户粘贴中的 PAT / API key / Bearer token。通过
                # redact_sensitive_text 尊重 HERMES_REDACT_SECRETS —— 禁用时为空操作。
                #（#19798, #19845）
                if "content" in msg:
                    msg = dict(msg)
                    msg["content"] = self._redact_message_content(msg.get("content"))
                cleaned.append(msg)

            # Guard: 绝不 overwrite a larger session log with fewer messages。
            # 防止恢复的 Agent 以部分历史开始时丢失数据，否则会覆盖完整的 JSON 日志。
            if log_file.exists():
                try:
                    existing = json.loads(log_file.read_text(encoding="utf-8"))
                    existing_count = existing.get("message_count", len(existing.get("messages", [])))
                    if existing_count > len(cleaned):
                        logging.debug(
                            "Skipping session log overwrite: existing has %d messages, current has %d",
                            existing_count, len(cleaned),
                        )
                        return
                except Exception:
                    pass  # corrupted existing file — allow the overwrite

            entry = {
                "session_id": self.session_id,
                "model": self.model,
                "base_url": self.base_url,
                "platform": self.platform,
                "session_start": self.session_start.isoformat(),
                "last_updated": datetime.now().isoformat(),
                "system_prompt": redact_sensitive_text(self._cached_system_prompt or ""),
                "tools": self.tools or [],
                "message_count": len(cleaned),
                "messages": cleaned,
            }

            atomic_json_write(
                log_file,
                entry,
                indent=2,
                default=str,
            )

        except Exception as e:
            if self.verbose_logging:
                logging.warning(f"Failed to save session log: {e}")


    def interrupt(self, message: str = None) -> None:
        """
        Request the agent to interrupt its current tool-calling loop.
        
        Call this from another thread (e.g., input handler, message receiver)
        to gracefully stop the agent and process a new message.
        
        Also signals long-running tool executions (e.g. terminal commands)
        to terminate early, so the agent can respond immediately.
        
        Args:
            message: Optional new message that triggered the interrupt.
                     If provided, the agent will include this in its response context.
        
        Example (CLI):
            # 在单独的输入线程中：
            if user_typed_something:
                agent.interrupt(user_input)
        
        Example (Messaging):
            # 当新消息到达活动会话时：
            if session_has_running_agent:
                running_agent.interrupt(new_message.text)
        """
        # 硬停止和重定向共享一个锁，以便 /stop 不能与已接受的纠正竞争并意外变成重试。
        _redirect_lock = getattr(self, "_pending_redirect_lock", None)
        if _redirect_lock is not None:
            with _redirect_lock:
                self._interrupt_requested = True
                self._interrupt_message = message
                self._pending_redirect = None
        else:
            self._interrupt_requested = True
            self._interrupt_message = message
            self._pending_redirect = None

        # Codex app-server 拥有其模型/工具循环并监视私有
        # interrupt event，而不是 Hermes' per-thread flag。
        if getattr(self, "api_mode", None) == "codex_app_server":
            _codex_session = getattr(self, "_codex_session", None)
            _request_interrupt = getattr(_codex_session, "request_interrupt", None)
            if callable(_request_interrupt):
                try:
                    _request_interrupt()
                except Exception:
                    logger.debug(
                        "Failed to interrupt Codex app-server turn",
                        exc_info=True,
                    )

        # cron turn 在对话线程上执行其 API 请求到
        # avoid the nested interrupt-worker 死锁.  Unlike the normal worker
        # 路径，其客户端在此注册，所以这个跨线程中断仍然可以立即关闭活动 socket。
        _abort_active_request = getattr(self, "_active_request_abort", None)
        if callable(_abort_active_request):
            try:
                _abort_active_request("interrupt_abort")
            except Exception:
                logger.debug("Failed to abort active inline request", exc_info=True)
        # 通知所有工具立即中止任何飞行中操作。将中断限定在此 Agent 的执行线程内，
        # 这样在同一进程（gateway）中运行的其他 Agent 不受影响。
        if self._execution_thread_id is not None:
            _set_interrupt(True, self._execution_thread_id)
            self._interrupt_thread_signal_pending = False
        else:
            # 中断在 run_conversation() 完成将 Agent 绑定到其执行线程之前到达。
            # 延迟工具级中断信号直到启动完成，而不是错误地目标调用者线程。
            self._interrupt_thread_signal_pending = True
        # 扇出到并发工具工作线程。这些工作线程在自己的 tid 上运行工具
        #（ThreadPoolExecutor 工作线程），所以工具内的 `is_interrupted()` 只有当
        # 其特定 tid 在 `_interrupted_threads` 集合中时才看到中断。没有这个传播，
        # 已经运行的并发工具（例如挂在网络 I/O 上的终端命令）永远注意不到中断，必须运行到自己的
        # 超时。见 `_run_tool` 了解匹配的入口/出口簿记。
        # `getattr` 回退覆盖通过 object.__new__ 构建 AIAgent 并跳过 __init__ 的测试桩。
        _tracker = getattr(self, "_tool_worker_threads", None)
        _tracker_lock = getattr(self, "_tool_worker_threads_lock", None)
        if _tracker is not None and _tracker_lock is not None:
            with _tracker_lock:
                _worker_tids = list(_tracker)
            for _wtid in _worker_tids:
                try:
                    _set_interrupt(True, _wtid)
                except Exception:
                    pass
        # 将中断传播到任何运行的子 Agent（子 Agent 委托）
        with self._active_children_lock:
            children_copy = list(self._active_children)
        for child in children_copy:
            try:
                child.interrupt(message)
            except Exception as e:
                logger.debug("Failed to propagate interrupt to child agent: %s", e)
        if not self.quiet_mode:
            print("\n⚡ Interrupt requested" + (f": '{message[:40]}...'" if message and len(message) > 40 else f": '{message}'" if message else ""))

    def clear_interrupt(self, *, preserve_redirect: bool = False) -> bool:
        """清除中断请求和每线程工具信号。

        ``preserve_redirect`` is used only by the conversation loop after it
        intentionally cancels a model request to rebuild that same logical
        turn. Public hard-stop paths keep the default and clear everything.
        """
        _redirect_lock = getattr(self, "_pending_redirect_lock", None)
        if _redirect_lock is not None:
            with _redirect_lock:
                if preserve_redirect and not self._pending_redirect:
                    return False
                self._interrupt_requested = False
                self._interrupt_message = None
                if not preserve_redirect:
                    self._pending_redirect = None
        else:
            if preserve_redirect and not getattr(self, "_pending_redirect", None):
                return False
            self._interrupt_requested = False
            self._interrupt_message = None
            if not preserve_redirect:
                self._pending_redirect = None
        self._interrupt_thread_signal_pending = False
        if self._execution_thread_id is not None:
            _set_interrupt(False, self._execution_thread_id)
        # 同时清除任何并发工具工作线程位。被追踪的工作线程通常在退出时清除自己的位，
        # 但此处的显式清除保证没有过时的中断能在 turn 中幸存，如果该线程恰好被调度到
        # 同一个回收的工作线程 tid 上。`getattr` 回退覆盖通过 object.__new__ 构建
        # AIAgent 并跳过 __init__ 的测试桩。
        # boundary and fire on a subsequent, unrelated 工具调用 that
        # 恰好被调度到同一个回收的工作线程 tid 上。
        # `getattr` 回退覆盖通过 object.__new__ 构建 AIAgent 并跳过 __init__ 的测试桩。
        _tracker = getattr(self, "_tool_worker_threads", None)
        _tracker_lock = getattr(self, "_tool_worker_threads_lock", None)
        if _tracker is not None and _tracker_lock is not None:
            with _tracker_lock:
                _worker_tids = list(_tracker)
            for _wtid in _worker_tids:
                try:
                    _set_interrupt(False, _wtid)
                except Exception:
                    pass
        # 硬中断取代任何待处理的 /steer —— steer 是为 Agent 的下一个工具调用迭代准备的，
        # 这不会再发生。丢弃它，而不是在 post-interrupt turn 上用延迟注入惊吓用户。
        _steer_lock = getattr(self, "_pending_steer_lock", None)
        if _steer_lock is not None:
            with _steer_lock:
                self._pending_steer = None
        return True

    def steer(self, text: str) -> bool:
        """
        Inject a user message into the next 工具结果 without interrupting.

        Unlike interrupt(), this does NOT stop the current 工具调用. The
        text is stashed and the agent loop appends it to the LAST tool
        result's content once the current tool batch finishes. The model
        sees the steer as part of the tool output on its next iteration.

        Thread-safe: callable from gateway/CLI/TUI threads. Multiple calls
        before the drain point concatenate with newlines.

        Args:
            text: The user text to inject. Empty strings are ignored.

        Returns:
            True if the steer was accepted, False if the text was empty.
        """
        if not text or not text.strip():
            return False
        cleaned = text.strip()
        _lock = getattr(self, "_pending_steer_lock", None)
        if _lock is None:
            # 通过 object.__new__ 构建 AIAgent 的测试桩跳过 __init__。
            # 回退到直接属性设置；这些桩中不应有并发调用者。
            existing = getattr(self, "_pending_steer", None)
            self._pending_steer = (existing + "\n" + cleaned) if existing else cleaned
            return True
        with _lock:
            if self._pending_steer:
                self._pending_steer = self._pending_steer + "\n" + cleaned
            else:
                self._pending_steer = cleaned
        return True

    def redirect(self, text: str) -> bool:
        """Redirect the active turn without converting it into a new task.

        During a normal Hermes model request this cancels only that request;
        the conversation loop retains completed messages/工具结果s, records
        the displayed partial reasoning as plain assistant context, appends the
        correction as a real user message, and retries. During tool execution
        it degrades to ``steer()`` so the tool can finish at a safe boundary.
        Codex app-server has a native ``turn/steer`` operation and uses it
        directly instead of cancelling.

        Returns ``False`` when there is no live turn or the text is empty, so
        surfaces can fall back to their existing next-turn queue.
        """
        if not text or not text.strip():
            return False
        cleaned = text.strip()

        # Codex owns its internal reasoning/tool loop, so use its first-class
        # active-turn steering protocol，而不是 interrupting the subprocess。
        if getattr(self, "api_mode", None) == "codex_app_server":
            _codex_session = getattr(self, "_codex_session", None)
            _native_steer = getattr(_codex_session, "request_steer", None)
            if callable(_native_steer):
                _redirect_lock = getattr(self, "_pending_redirect_lock", None)
                if _redirect_lock is not None:
                    with _redirect_lock:
                        if self._interrupt_requested:
                            return False
                elif self._interrupt_requested:
                    return False
                try:
                    return bool(_native_steer(cleaned))
                except Exception:
                    logger.debug("Codex app-server turn/steer failed", exc_info=True)
                    return False

        # 绝不仅仅为了传递对话指导而杀死工具。这是
        # existing steer drain puts it on the final 工具结果 before the next
        # 模型决策，包括 delegate_task 子 Agent。
        if getattr(self, "_executing_tools", False):
            return self.steer(cleaned)

        _model_active = getattr(self, "_model_request_active", None)
        _redirect_lock = getattr(self, "_pending_redirect_lock", None)
        if _redirect_lock is None:
            if _model_active is None or not _model_active.is_set():
                return False
            existing = getattr(self, "_pending_redirect", None)
            if self._interrupt_requested and not existing:
                return False
            self._pending_redirect = (
                f"{existing}\n\n[Additional user correction]\n{cleaned}"
                if existing
                else cleaned
            )
            self._interrupt_requested = True
            self._interrupt_message = None
        else:
            with _redirect_lock:
                if _model_active is None or not _model_active.is_set():
                    # 在 we acquired the state lock 之前，The response completed。
                    # 拒绝以便表面排队一个新 turn。
                    return False
                if self._interrupt_requested and not self._pending_redirect:
                    return False
                if self._pending_redirect:
                    self._pending_redirect = (
                        f"{self._pending_redirect}\n\n"
                        f"[Additional user correction]\n{cleaned}"
                    )
                else:
                    self._pending_redirect = cleaned
                self._interrupt_requested = True
                self._interrupt_message = None

        # 仅中断模型请求。不要像 interrupt() 那样扇出到工具工作线程或子 Agent。
        _execution_thread_id = getattr(self, "_execution_thread_id", None)
        if _execution_thread_id is not None:
            _set_interrupt(True, _execution_thread_id)
            self._interrupt_thread_signal_pending = False
        else:
            self._interrupt_thread_signal_pending = True
        _abort_active_request = getattr(self, "_active_request_abort", None)
        if callable(_abort_active_request):
            try:
                _abort_active_request("redirect_abort")
            except Exception:
                logger.debug("Failed to abort request for redirect", exc_info=True)
        return True

    def _has_pending_redirect(self) -> bool:
        """判断是否有活动轮次重定向等待应用。"""
        _redirect_lock = getattr(self, "_pending_redirect_lock", None)
        if _redirect_lock is None:
            return bool(getattr(self, "_pending_redirect", None))
        with _redirect_lock:
            return bool(self._pending_redirect)

    def _drain_pending_redirect(self) -> Optional[str]:
        """返回并清除待处理的活动轮次纠正文本。"""
        _redirect_lock = getattr(self, "_pending_redirect_lock", None)
        if _redirect_lock is None:
            text = getattr(self, "_pending_redirect", None)
            self._pending_redirect = None
            return text
        with _redirect_lock:
            text = self._pending_redirect
            self._pending_redirect = None
        return text

    def _drain_pending_steer(self) -> Optional[str]:
        """返回待处理的 steer 文本（如果有）并清除槽位。

        Safe to call from the agent execution thread after appending tool
        results. Returns None when no steer is pending.
        """
        _lock = getattr(self, "_pending_steer_lock", None)
        if _lock is None:
            text = getattr(self, "_pending_steer", None)
            self._pending_steer = None
            return text
        with _lock:
            text = self._pending_steer
            self._pending_steer = None
        return text

    def _record_file_mutation_result(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        is_error: bool,
    ) -> None:
        """记录 ``write_file`` / ``patch`` 结果用于 turn 结束验证器。

        On failure, store ``{path: {error_preview, tool}}`` entries.  On
        success, remove any prior failure entries for the same paths (the
        model recovered within the turn).  Silently no-ops if the per-turn
        state dict hasn't been initialised yet (e.g. a tool dispatched
        outside ``run_conversation``).
        """
        if tool_name not in _FILE_MUTATING_TOOLS:
            return
        state = getattr(self, "_turn_failed_file_mutations", None)
        if state is None:
            return
        targets = _extract_file_mutation_targets(tool_name, args)
        if not targets:
            return
        landed = file_mutation_result_landed(tool_name, result)
        if landed:
            changed = getattr(self, "_turn_file_mutation_paths", None)
            if changed is not None:
                changed.update(_extract_landed_file_mutation_paths(tool_name, args, result))
        if is_error and not landed:
            preview = _extract_error_preview(result)
            for path in targets:
                # 为给定路径保留我们看到的第一个错误，除非我们后来看到成功。
                # 带有不同消息的重复失败不应静默覆盖原始错误。
                if path not in state:
                    state[path] = {
                        "tool": tool_name,
                        "error_preview": preview,
                    }
        else:
            for path in targets:
                state.pop(path, None)

    def _file_mutation_verifier_enabled(self) -> bool:
        """检查每 turn 文件变异验证器页脚是否开启。

        Config path: ``display.file_mutation_verifier`` (bool, default True).
        ``HERMES_FILE_MUTATION_VERIFIER`` env var overrides config.  Exposed
        as a method so tests can patch a single seam without reaching into
        the private ``_turn_failed_file_mutations`` state dict.
        """
        try:
            import os as _os
            env = _os.environ.get("HERMES_FILE_MUTATION_VERIFIER")
            if env is not None:
                return env.strip().lower() not in {"0", "false", "no", "off"}
            # 从持久化的 config.yaml 读取，以便 gateway 和 CLI 共享同一设置。延迟导入以避免启动时循环。
            try:
                from hermes_cli.config import load_config as _load_config
                _cfg = _load_config() or {}
            except Exception:
                _cfg = {}
            _display = _cfg.get("display") if isinstance(_cfg, dict) else None
            if isinstance(_display, dict) and "file_mutation_verifier" in _display:
                return bool(_display.get("file_mutation_verifier"))
        except Exception:
            pass
        return True  # safe default: verifier on

    # 页脚行中的裸绝对 / home / Windows 驱动器文件路径。锚点镜像 gateway 的 ``extract_local_files`` 裸路径
    # 检测器，以便 gateway 会自动附加的任何内容首先在此处用内联代码反引号包装（提取器跳过内部的路径
    # `code` 跨度）。纵深防御：即使未来的错误消息将凭证路径（config.yaml、.env、auth.json）回显到用户面向的页脚，它也永远不会被匹配为可交付的裸路径并静默上传到消息通道（#35584）。
    _FOOTER_PATH_RE = re.compile(
        r"(?<![/:\w.`])(?:~/|/|[A-Za-z]:[/\\])(?:[\w.\-]+[/\\])*[\w.\-]+\.[\w]+",
    )

    @classmethod
    def _neutralize_footer_paths(cls, text: str) -> str:
        """将裸文件路径用反引号包装，以便它们不会被自动传递。

        The gateway's ``extract_local_files`` scans response text for bare
        absolute/home paths ending in a deliverable extension and uploads
        any that exist on disk as native attachments — but it explicitly
        skips paths inside inline-code (`` `...` ``) spans.  Backticking
        every path the footer renders defeats that auto-detection while
        keeping the path fully human-readable.  Paths already wrapped in a
        backtick (the negative lookbehind excludes a preceding `` ` ``) are
        left untouched so we never double-wrap.
        """
        if not text:
            return text
        return cls._FOOTER_PATH_RE.sub(lambda m: f"`{m.group(0)}`", text)

    @classmethod
    def _format_file_mutation_failure_footer(cls, failed: Dict[str, Dict[str, Any]]) -> str:
        """将每 turn 的失败变异字典渲染为用户面向的页脚。

        Displays up to 10 paths with their first error preview, then a
        count of any additional failures.  Returns an empty string when
        the dict is empty so callers can concatenate unconditionally.

        Every file path that reaches the user-facing text — both the bullet
        path and any path echoed inside the tool's error preview — is
        backtick-wrapped via ``_neutralize_footer_paths`` so the gateway's
        bare-path media extractor can never auto-attach a protected file
        (e.g. ``~/.hermes/config.yaml``) to a messaging channel (#35584).
        """
        if not failed:
            return ""
        lines = [
            "⚠️ File-mutation verifier: "
            f"{len(failed)} file(s) were NOT modified this turn despite any "
            "wording above that may suggest otherwise. Run `git status` or "
            "`read_file` to confirm."
        ]
        shown = 0
        for path, info in failed.items():
            if shown >= 10:
                break
            preview = (info.get("error_preview") or "").strip()
            tool = info.get("tool") or "patch"
            if preview:
                lines.append(f"  • `{path}` — [{tool}] {preview}")
            else:
                lines.append(f"  • `{path}` — [{tool}] failed")
            shown += 1
        remaining = len(failed) - shown
        if remaining > 0:
            lines.append(f"  • … and {remaining} more")
        # 中和预览文本回显的任何路径（项目符号路径已在上方用反引号标记；后视保持它不被
        # 双重包装）。
        return cls._neutralize_footer_paths("\n".join(lines))

    def _turn_completion_explainer_enabled(self) -> bool:
        """检查 turn 结束完成解释器页脚是否开启。

        Config path: ``display.turn_completion_explainer`` (bool, default
        True).  ``HERMES_TURN_COMPLETION_EXPLAINER`` env var overrides
        config.  Exposed as a method so tests can patch a single seam,
        mirroring ``_file_mutation_verifier_enabled``.
        """
        try:
            import os as _os
            env = _os.environ.get("HERMES_TURN_COMPLETION_EXPLAINER")
            if env is not None:
                return env.strip().lower() not in {"0", "false", "no", "off"}
            # 从持久化的 config.yaml 读取，以便 gateway 和 CLI 共享同一设置。延迟导入以避免启动时循环。
            try:
                from hermes_cli.config import load_config as _load_config
                _cfg = _load_config() or {}
            except Exception:
                _cfg = {}
            _display = _cfg.get("display") if isinstance(_cfg, dict) else None
            if isinstance(_display, dict) and "turn_completion_explainer" in _display:
                return bool(_display.get("turn_completion_explainer"))
        except Exception:
            pass
        return True  # safe default: explainer on

    @staticmethod
    def _format_turn_completion_explanation(turn_exit_reason: str) -> str:
        """Render a user-facing explanation for an abnormal turn ending.

        Maps the internal ``turn_exit_reason`` to a short, actionable
        message so a turn that produced no usable assistant reply (empty
        content after retries, a partial/truncated stream, a still-pending
        工具结果, or an iteration/budget limit) is never silent from
        the UI's perspective — the symptom users report in #34452.

        Returns an empty string for reasons that are NOT abnormal (e.g.
        a normal ``text_response(...)`` exit), so callers can concatenate
        or substitute unconditionally without warning on healthy turns
        like a terse ``Done.``.
        """
        if not turn_exit_reason:
            return ""
        reason = str(turn_exit_reason)

        # 正常完成 —— 保持安静。``text_response(...)`` 是健康终端；任何产生真实回复的都可以。
        if reason.startswith("text_response"):
            return ""

        prefix = "⚠️ No reply: "
        if reason == "empty_response_exhausted":
            return (
                prefix
                + "the model returned empty content after retries and any "
                "fallback providers. Try `continue`, switch model/provider, "
                "or inspect the tool output above."
            )
        if reason == "all_retries_exhausted_no_response":
            return (
                prefix
                + "all API retries were exhausted before a response was "
                "produced (provider errors / 速率限制s). Try `continue` "
                "or switch provider."
            )
        if reason == "partial_stream_recovery":
            return (
                prefix
                + "streaming stopped early and only a partial response was "
                "recovered. Send `continue` to resume from where it stopped."
            )
        if reason == "fallback_prior_turn_content":
            return (
                prefix
                + "no new content was produced this turn; showing recovered "
                "prior context. Send `continue` to retry."
            )
        if reason == "interrupted_during_api_call":
            return (
                prefix
                + "the request was interrupted mid-call before a reply was "
                "received. Send `continue` to retry."
            )
        if reason == "budget_exhausted":
            return (
                prefix
                + "the per-turn iteration/cost budget was exhausted before a "
                "final answer. Send `continue` to keep going."
            )
        if reason == "ollama_runtime_context_too_small":
            return (
                prefix
                + "the local model's 上下文窗口 was too small to finish. "
                "Increase the context size or use a larger model."
            )
        if reason.startswith("max_iterations_reached"):
            return (
                prefix
                + "the maximum tool-iteration limit was reached before a "
                "final answer. Send `continue` to keep going, or raise "
                "`max_iterations`."
            )
        if reason.startswith("error_near_max_iterations"):
            return (
                prefix
                + "an error occurred near the iteration limit before a final "
                "answer. Check the tool output above, then send `continue`."
            )
        if reason == "pending_tool_result":
            return (
                prefix
                + "the turn stopped while a 工具结果 was still pending and "
                "the model produced no follow-up text. Send `continue` to "
                "let it summarize."
            )
        if reason == "session_persistence_failed":
            return (
                prefix
                + "the turn was stopped because session storage could not be "
                "written (the transcript would have been lost on restart). "
                "Check disk space / permissions for the state DB, then send "
                "your message again."
            )
        # 未知/仅诊断原因（例如 "unknown"、guardrail_halt 已经显示自己的消息）—— 不要二次猜测。
        return ""

    def _apply_pending_steer_to_tool_results(self, messages: list, num_tool_msgs: int) -> None:
        """转发器 → agent/agent_runtime_helpers/apply_pending_steer_to_tool_results.py"""
        from agent.agent_runtime_helpers import apply_pending_steer_to_tool_results
        return apply_pending_steer_to_tool_results(self, messages, num_tool_msgs)

    def _touch_activity(self, desc: str) -> None:
        """更新最后活动时间戳和描述（线程安全）。

        Also bridges to the kanban board's heartbeat fields when this
        process is a dispatcher-spawned worker (HERMES_KANBAN_TASK set),
        so the dispatcher watchdog doesn't reclaim an actively-running
        worker as stale (#31752). Bridge is rate-limited (60s) and
        best-effort — it never raises into the agent loop.
        """
        self._last_activity_ts = time.time()
        self._last_activity_desc = desc
        if os.environ.get("HERMES_KANBAN_TASK"):
            try:
                from tools.kanban_tools import heartbeat_current_worker_from_env
                heartbeat_current_worker_from_env()
            except Exception:
                # 绝不让桥接破坏 Agent 循环。函数内部已经吞掉异常；这个外部守卫
                # 覆盖导入时失败（kanban_tools 不可用等）在小众部署表面上。
                pass

    def _capture_rate_limits(self, http_response: Any) -> None:
        """Parse x-ratelimit-* headers from an HTTP response and cache the state.

        Called after each streaming API call.  The httpx Response object is
        available on the OpenAI SDK Stream via ``stream.response``.
        """
        if http_response is None:
            return
        headers = getattr(http_response, "headers", None)
        if not headers:
            return
        try:
            from agent.rate_limit_tracker import parse_rate_limit_headers
            state = parse_rate_limit_headers(headers, provider=self.provider)
            if state is not None:
                self._rate_limit_state = state
        except Exception:
            pass  # Never let header parsing break the agent loop

    def get_rate_limit_state(self):
        """返回最后捕获的 RateLimitState，或 None。"""
        return self._rate_limit_state

    def _capture_anthropic_response_headers(self, http_response: Any) -> None:
        """Capture out-of-band state from Anthropic Messages response headers.

        The Anthropic SDK's aggregated ``Message`` drops HTTP headers. Portal
        (and other providers) put rate-limit and credits state there — the same
        families the OpenAI-wire streaming path captures via
        ``stream.response``. Fail-open: each capture swallows its own errors.
        """
        self._capture_rate_limits(http_response)
        self._capture_credits(http_response)

    def _capture_credits(self, http_response: Any) -> None:
        """解析 x-nous-credits-* 头，缓存 CreditsState，触发阈值通知。

        Fail-open throughout — header issues never break the agent loop. The PARSE is
        swallowed (any error → treated as a miss → keep last-known). The notice
        EVALUATION/EMIT is a SEPARATE block that WARNS on failure (R1-M2): a bug in the
        depletion-notice path must not vanish silently under the parse swallow.
        """
        # 开发测试 fixture（HERMES_DEV_CREDITS_FIXTURE）：每 turn 注入选择的通知状态以进行可重复测试，绕过真实头。一次性脚手架。
        try:
            from agent.credits_tracker import dev_fixture_credits_state
            _fixture = dev_fixture_credits_state()
        except Exception:
            _fixture = None
        if _fixture is not None:
            self._credits_state = _fixture
            if self._credits_session_start_micros is None:
                self._credits_session_start_micros = _fixture.remaining_micros
            _latch = getattr(self, "_credits_latch", None)
            if isinstance(_latch, dict):
                # 仅 seen_below_90 —— 不 seen_grant_unspent（初始化它会在 fixture 的首次
                # 观察时触发 grant_spent，这正是该门禁要防止的每会话骚扰）。
                _latch["seen_below_90"] = True  # let warn90 fire without a real crossing
            _used = _fixture.used_fraction
            logger.info(
                "credits ▸ [FIXTURE] remaining=%d (%s) · paid=%s · denom=%s · used=%s "
                "(real headers bypassed — `echo clear` / unset HERMES_DEV_CREDITS_FIXTURE to restore)",
                _fixture.remaining_micros,
                _fixture.remaining_usd or "?",
                _fixture.paid_access,
                _fixture.denominator_kind,
                ("%.0f%%" % (_used * 100)) if _used is not None else "n/a",
            )
            self._emit_credits_notices()
            return
        if http_response is None:
            return
        headers = getattr(http_response, "headers", None)
        if not headers:
            return
        _dev = is_truthy_value(os.environ.get("HERMES_DEV_CREDITS"))

        # ── 解析（失败开放 → 缺失；绝不用 None 覆盖良好状态）──
        try:
            from agent.credits_tracker import parse_credits_headers
            state = parse_credits_headers(headers, provider=self.provider)
        except Exception:
            return  # parse error → treat as a miss, keep last-known
        if state is None:
            if _dev:
                logger.info(
                    "credits ▸ response had no valid x-nous-credits-* headers "
                    "(miss — producer off / non-Nous path / >TTL stale)"
                )
            return

        # 保留最后已知值：仅在新解析有效时覆盖
        self._credits_state = state
        # 首次看到头时锁存会话起始剩余
        if self._credits_session_start_micros is None:
            self._credits_session_start_micros = state.remaining_micros
        if _dev:
            # HERMES_DEV_CREDITS：将每次捕获streaming到 agent.log —— 用 `hermes logs -f`
            # 实时查看（grep 'credits ▸'）。仅开发模式；普通用户静默。
            spent = self.get_credits_spent_micros()
            used = state.used_fraction
            logger.info(
                "credits ▸ remaining=%d (%s) · paid=%s · denom=%s · used=%s "
                "· Δspent=%s · age=%s%s",
                state.remaining_micros,
                state.remaining_usd or "?",
                state.paid_access,
                state.denominator_kind,
                ("%.0f%%" % (used * 100)) if used is not None else "n/a",
                ("%.1f¢" % (spent / 10000)) if spent is not None else "n/a",
                ("%.0fs" % state.age_seconds) if state.age_seconds != float("inf") else "n/a",
                (" · disabled=%s" % state.disabled_reason) if state.disabled_reason else "",
            )

        # 阈值通知 —— 与冷启动种子共享（见 _emit_credits_notices）。
        self._emit_credits_notices()

    def _emit_credits_notices(self) -> None:
        """在当前 credits 状态上运行阈值策略并发出通知。

        由热路径（_capture_credits）和 L3 冷启动种子共享，所以在已耗尽状态下打开的
        会话会立即警告 —— 而不仅仅是在第一个reasoning头之后。仅当通知消费者绑定时运行
        （消息不绑定任何消费者 → 状态仍为 /usage 缓存，无策略）。失败时 WARN 而非吞掉
        （R1-M2）：耗尽路径的 bug 绝不能静默消失。先发出清除，再显示（所以耗尽在
        latest-wins 槽中最后落地）。
        """
        if getattr(self, "notice_callback", None) is None and getattr(self, "notice_clear_callback", None) is None:
            return
        if not self._credits_notices_enabled():
            return
        state = getattr(self, "_credits_state", None)
        if state is None:
            return
        try:
            from agent.credits_tracker import evaluate_credits_notices, is_free_tier_model, new_credits_latch
            latch = getattr(self, "_credits_latch", None)
            if latch is None:
                latch = self._credits_latch = new_credits_latch()
            # 免费模型门禁：免费模型上耗尽的账户仍然可以reasoning，所以耗尽错误横幅被抑制。本地数据
            # only (":free" suffix + pricing-cache peek) — 绝不 a network call。
            model_is_free = is_free_tier_model(
                getattr(self, "model", "") or "",
                getattr(self, "base_url", "") or "",
            )
            to_show, to_clear = evaluate_credits_notices(state, latch, model_is_free=model_is_free)
            for key in to_clear:        # clears FIRST …
                self._emit_notice_clear(key)
            for notice in to_show:      # … then shows (depleted lands last in a latest-wins slot)
                self._emit_notice(notice)
        except Exception:
            logger.warning("credits notice evaluation/emit failed", exc_info=True)

    def _credits_notices_enabled(self) -> bool:
        """credits 通知是否启用（配置 display.credits_notices）。

        Read once per agent and cached — the policy runs after every API
        response, and the setting governs UI noise, not correctness, so a
        config flip applying on the next session is fine.  Fail-open True
        (preserve current behaviour) on any config error.
        """
        cached = getattr(self, "_credits_notices_enabled_cache", None)
        if cached is not None:
            return cached
        enabled = True
        try:
            from hermes_cli.config import load_config as _load_config
            _cfg = _load_config() or {}
            _display = _cfg.get("display") if isinstance(_cfg, dict) else None
            if isinstance(_display, dict) and "credits_notices" in _display:
                enabled = bool(_display.get("credits_notices"))
        except Exception:
            enabled = True
        self._credits_notices_enabled_cache = enabled
        return enabled

    def get_credits_state(self):
        """返回最后捕获的 CreditsState，或 None。"""
        return self._credits_state

    def get_credits_spent_micros(self):
        """会话累计花费微秒 = 首次看到的剩余 - 当前剩余。无数据时为 None。"""
        if self._credits_session_start_micros is None or self._credits_state is None:
            return None
        return self._credits_session_start_micros - self._credits_state.remaining_micros

    def _check_openrouter_cache_status(self, http_response: Any) -> None:
        """从响应头读取 X-OpenRouter-Cache-Status 并记录日志。

        Increments ``_or_cache_hits`` on HIT so callers can report savings.
        """
        if http_response is None:
            return
        headers = getattr(http_response, "headers", None)
        if not headers:
            return
        try:
            status = headers.get("x-openrouter-cache-status")
            if not status:
                return
            if status.upper() == "HIT":
                self._or_cache_hits += 1
                logger.info("OpenRouter response cache HIT (total: %d)", self._or_cache_hits)
            else:
                logger.debug("OpenRouter response cache %s", status.upper())
        except Exception:
            pass  # Never let header parsing break the agent loop

    def get_activity_summary(self) -> dict:
        """Return a snapshot of the agent's current activity for diagnostics.

        Called by the gateway timeout handler to report what the agent was doing
        when it was killed, and by the periodic "still working" notifications.
        """
        elapsed = time.time() - self._last_activity_ts
        return {
            "last_activity_ts": self._last_activity_ts,
            "last_activity_desc": self._last_activity_desc,
            "seconds_since_activity": round(elapsed, 1),
            "current_tool": self._current_tool,
            "api_call_count": self._api_call_count,
            "max_iterations": self.max_iterations,
            "budget_used": self.iteration_budget.used,
            "budget_max": self.iteration_budget.max_total,
        }

    def shutdown_memory_provider(self, messages: list = None) -> None:
        """关闭内存提供者和上下文引擎 —— 在实际会话边界调用。

        This calls on_session_end() then shutdown_all() on the memory
        manager, and on_session_end() on the context engine.
        NOT called per-turn — only at CLI exit, /reset, gateway
        session expiry, etc.
        """
        if self._memory_manager:
            try:
                self._memory_manager.on_session_end(messages or [])
            except Exception as e:
                logger.warning("Memory provider on_session_end failed during shutdown: %s", e, exc_info=True)
            try:
                self._memory_manager.shutdown_all()
            except Exception:
                pass
        # 通知上下文引擎会话结束（刷新 DAG、关闭数据库等）
        if hasattr(self, "context_compressor") and self.context_compressor:
            try:
                self.context_compressor.on_session_end(
                    self.session_id or "",
                    messages or [],
                )
            except Exception:
                pass

    def commit_memory_session(self, messages: list = None) -> None:
        """触发会话结束提取而不拆除提供商。
        Called when session_id rotates (e.g. /new, context compression);
        providers keep their state and continue running under the old
        session_id — they just flush pending extraction now."""
        if self._memory_manager:
            try:
                self._memory_manager.on_session_end(messages or [])
            except Exception:
                pass
        # 同时通知上下文引擎会话结束 —— 与内存管理器的 on_session_end 相同的生命周期时刻。没有这个，引擎会
        # 累积每会话状态（DAG、摘要）从轮换出的会话泄漏该状态到同一
        # 压缩器实例。镜像 shutdown_memory_provider() 中的调用。
        # 参见 issue #22394.
        if hasattr(self, "context_compressor") and self.context_compressor:
            try:
                self.context_compressor.on_session_end(
                    self.session_id or "",
                    messages or [],
                )
            except Exception:
                pass

    def _sync_external_memory_for_turn(
        self,
        *,
        original_user_message: Any,
        final_response: Any,
        interrupted: bool,
        messages: list | None = None,
    ) -> None:
        """Mirror a completed turn into external memory providers.

        Called at the end of ``run_conversation`` with the cleaned user
        message (``original_user_message``) and the finalised assistant
        response.  The external memory backend gets both ``sync_all`` (to
        persist the exchange) and ``queue_prefetch_all`` (to start
        warming context for the next turn) in one shot.

        Uses ``original_user_message`` rather than ``user_message``
        because the latter may carry injected skill content that bloats
        or breaks provider queries.

        Interrupted turns are skipped entirely (#15218).  A partial
        assistant output, an aborted tool chain, or a mid-stream reset
        is not durable conversational truth — mirroring it into an
        external memory backend pollutes future recall with state the
        user never saw completed.  The prefetch is gated on the same
        flag: the user's next message is almost certainly a retry of
        the same intent, and a prefetch keyed on the interrupted turn
        would fire against stale context.

        Normal completed turns still sync as before.  The whole body is
        wrapped in ``try/except Exception`` because external memory
        providers are strictly best-effort — a misconfigured or offline
        backend must not block the user from seeing their response.
        """
        if interrupted:
            return
        if not (self._memory_manager and final_response and original_user_message):
            return
        # 多模态 turn 将内容作为类型部分列表携带；提供商期望纯字符串，所以先扁平化为文本（换行连接以便
        # 内存，与日志/轨迹预览使用的默认空格连接相对）。
        user_text = _summarize_user_message_for_log(original_user_message, sep="\n")
        response_text = _summarize_user_message_for_log(final_response, sep="\n")
        if not (user_text and response_text):
            return
        try:
            sync_kwargs = {"session_id": self.session_id or ""}
            if messages is not None:
                sync_kwargs["messages"] = messages
            self._memory_manager.sync_all(
                user_text,
                response_text,
                **sync_kwargs,
            )
            self._memory_manager.queue_prefetch_all(
                user_text,
                session_id=self.session_id or "",
            )
        except Exception:
            pass

    def release_clients(self) -> None:
        """Release LLM client resources WITHOUT tearing down session tool state.

        Used by the gateway when evicting this agent from _agent_cache for
        memory-management reasons (LRU cap or idle TTL) — the session may
        resume at any time with a freshly-built AIAgent that reuses the
        same task_id / session_id, so we must NOT kill:
          - process_registry entries for task_id (user's bg shells)
          - terminal sandbox for task_id (cwd, env, shell state)
          - browser daemon for task_id (open tabs, cookies)
          - memory provider (has its own lifecycle; keeps running)

        We DO close:
          - OpenAI/httpx client pool (big chunk of held memory + sockets;
            the rebuilt agent gets a fresh client anyway)
          - Active child subagents (per-turn artefacts; safe to drop)

        Safe to call multiple times.  Distinct from close() — which is the
        hard teardown for actual session boundaries (/new, /reset, session
        expiry).
        """
        # 关闭 active child agents (per-turn; no cross-turn persistence)。
        try:
            with self._active_children_lock:
                children = list(self._active_children)
                self._active_children.clear()
            for child in children:
                try:
                    child.release_clients()
                except Exception:
                    # 回退到对子进程的完整关闭；它们是每 turn 的。
                    try:
                        child.close()
                    except Exception:
                        pass
        except Exception:
            pass

        # 退役 OpenAI/httpx 客户端以立即释放 socket。#70773：驱逐运行在 gateway 的
        # memory-manager 线程上 —— 一个
        # cross-thread hard close of the 共享客户端 can release TLS FDs
        # 仍在展开的工作线程下（FD 回收 → SQLite 损坏）。退役会关闭池化的 socket
        #（我们获得的内存/socket 收益）——
        # 一旦 no thread holds them，want here) and lets GC release the FDs。
        try:
            client = getattr(self, "client", None)
            if client is not None:
                self._retire_shared_openai_client(client, reason="cache_evict")
                self.client = None
        except Exception:
            pass

        # 同时丢弃缓存的每请求线路客户端（在连续 LLM 调用间重用）—— 与上面相同的
        # socket/内存原理。
        try:
            self._close_cached_request_openai_client(reason="cache_evict")
        except Exception:
            pass

    def close(self) -> None:
        """释放此 Agent 实例持有的所有资源。

        Cleans up subprocess resources that would otherwise become orphans:
        - Background processes tracked in ProcessRegistry
        - Terminal sandbox environments
        - Browser daemon sessions
        - Active child agents (subagent delegation)
        - OpenAI/httpx client connections

        Safe to call multiple times (idempotent).  Each cleanup step is
        independently guarded so a failure in one does not prevent the rest.
        """
        task_id = getattr(self, "session_id", None) or ""

        # 1. 杀死此任务的后台进程
        try:
            from tools.process_registry import process_registry
            process_registry.kill_all(task_id=task_id)
        except Exception:
            pass

        # 2. 清理终端沙箱环境
        try:
            cleanup_vm(task_id)
        except Exception:
            pass

        # 3. 清理浏览器守护进程会话
        try:
            cleanup_browser(task_id)
        except Exception:
            pass

        # 4. 关闭活动子 Agent
        try:
            with self._active_children_lock:
                children = list(self._active_children)
                self._active_children.clear()
            for child in children:
                try:
                    child.close()
                except Exception:
                    pass
        except Exception:
            pass

        # 5. 关闭 OpenAI/httpx 客户端
        try:
            client = getattr(self, "client", None)
            if client is not None:
                self._close_openai_client(client, reason="agent_close", shared=True)
                self.client = None
        except Exception:
            pass

        # 5b. 关闭缓存的每请求线路客户端（在连续 LLM 调用间重用；见 _create_request_openai_client）。
        try:
            self._close_cached_request_openai_client(reason="agent_close")
        except Exception:
            pass

        # 6. 释放对话历史。镜像 _release_evicted_agent_soft 的软驱逐清除 ——
        # close() 是真正会话边界（/new、/reset、会话过期）的硬拆除，所以消息列表不会
        # 被重用。主动丢弃引用而不是等待 Agent 对象本身被收集，这在调用者
        # 仍持有已关闭的 Agent（例如正在排空的后台任务）。
        try:
            self._session_messages = []
        except Exception:
            pass

        # 7. 完成拥有的 SQLite 会话行，除非此 Agent 只是一个临时助手，故意将
        # 会话所有权向前移交（手动压缩助手旋转到续会话 ID，
        # 或共享活动父级 session_id 的后台审查分支，必须保持打开）。end_session() 是首次原因获胜，在
        # 已经结束的行，所以这永远不会覆盖由早期终端路径设置的 'compression' / 'cron_complete' / 'cli_close' 原因。
        try:
            if getattr(self, "_end_session_on_close", True):
                session_db = getattr(self, "_session_db", None)
                session_id = getattr(self, "session_id", None)
                if session_db and session_id:
                    session_db.end_session(session_id, "agent_close")
        except Exception:
            pass

    def _hydrate_todo_store(self, history: List[Dict[str, Any]]) -> None:
        """
        Recover todo state from conversation history.
        
        The gateway creates a fresh AIAgent per message, so the in-memory
        TodoStore is empty. We scan the history for the most recent todo
        tool response and replay it to reconstruct the state.

        Hydration is restricted to 工具结果s that are paired with an
        earlier assistant ``todo`` 工具调用. The gateway/API server accepts
        caller-supplied ``conversation_history``, so a forged bare
        ``role: tool`` message carrying a ``todos`` array must not be able to
        seed the store without a matching canonical 工具调用
        (GHSA-5g4g-6jrg-mw3g).
        """
        from tools.todo_tool import MAX_TODO_RESULT_CHARS

        # 向后遍历历史以找到最近的 todo 工具响应
        last_todo_response = None
        for idx in range(len(history) - 1, -1, -1):
            msg = history[idx]
            if msg.get("role") != "tool":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            # Only accept 工具结果s paired with a prior assistant todo call.
            if not self._tool_response_matches_todo_call(history, idx):
                continue
            if len(content) > MAX_TODO_RESULT_CHARS:
                logger.warning(
                    "Skipping oversized todo tool response during hydration: "
                    "session=%s chars=%d",
                    self.session_id or "none",
                    len(content),
                )
                continue
            # 快速检查：todo 响应包含 "todos" 键
            if '"todos"' not in content:
                continue
            try:
                data = json.loads(content)
                if "todos" in data and isinstance(data["todos"], list):
                    last_todo_response = data["todos"]
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        if last_todo_response:
            # 将项目重放到存储中（替换模式）
            self._todo_store.write(last_todo_response, merge=False)
            if not self.quiet_mode:
                self._vprint(f"{self.log_prefix}📋 Restored {len(last_todo_response)} todo item(s) from history")
        _set_interrupt(False)

    @classmethod
    def _tool_response_matches_todo_call(
        cls,
        history: List[Dict[str, Any]],
        tool_index: int,
    ) -> bool:
        """Return True when a 工具结果 belongs to a prior assistant todo call.

        Scans backwards from the 工具结果 to the nearest assistant message
        and confirms it issued a ``todo`` 工具调用 whose id matches this
        result's ``tool_call_id``. A ``user``/``system`` boundary (or a missing
        id) means the result is unpaired and must not hydrate the store.
        """
        if tool_index < 0 or tool_index >= len(history):
            return False
        tool_msg = history[tool_index]
        tool_call_id = tool_msg.get("tool_call_id")
        if not tool_call_id:
            return False

        for prior_idx in range(tool_index - 1, -1, -1):
            prior = history[prior_idx]
            role = prior.get("role")
            if role == "assistant":
                return cls._assistant_has_todo_tool_call(prior, tool_call_id)
            if role in {"user", "system"}:
                return False
        return False

    @classmethod
    def _assistant_has_todo_tool_call(
        cls,
        assistant_msg: Dict[str, Any],
        tool_call_id: str,
    ) -> bool:
        """当 assistant 消息发出了具有此 id 的 todo 调用时为 True。"""
        tool_calls = assistant_msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            return False

        for tool_call in tool_calls:
            if cls._get_tool_call_id_static(tool_call) != tool_call_id:
                continue
            if cls._get_tool_call_name_static(tool_call) == "todo":
                return True
        return False

    @property
    def is_interrupted(self) -> bool:
        """检查是否已请求中断。"""
        return self._interrupt_requested










    def _build_system_prompt_parts(self, system_message: str = None) -> Dict[str, str]:
        """转发器 → agent/system_prompt/build_system_prompt_parts.py"""
        from agent.system_prompt import build_system_prompt_parts
        return build_system_prompt_parts(self, system_message=system_message)

    def _build_system_prompt(self, system_message: str = None) -> str:
        """转发器 → agent/system_prompt/build_system_prompt.py"""
        from agent.system_prompt import build_system_prompt
        return build_system_prompt(self, system_message=system_message)

    @staticmethod
    def _get_tool_call_id_static(tc) -> str:
        """从 tool_call 条目（字典或对象）中提取调用 ID。"""
        if isinstance(tc, dict):
            return (tc.get("call_id", "") or tc.get("id", "") or "").strip()
        return (getattr(tc, "call_id", "") or getattr(tc, "id", "") or "").strip()

    @staticmethod
    def _get_tool_call_name_static(tc) -> str:
        """Extract function name from a tool_call entry (dict or object).

        Gemini's OpenAI-compatibility endpoint requires every `role: tool`
        message to carry the matching function name. OpenAI/Anthropic/ollama
        tolerate its absence, so the field is best-effort: callers fall back
        to "" and the message still works elsewhere.
        """
        if isinstance(tc, dict):
            fn = tc.get("function")
            if isinstance(fn, dict):
                return fn.get("name", "") or ""
            return ""
        fn = getattr(tc, "function", None)
        return getattr(fn, "name", "") or ""

    _VALID_API_ROLES = frozenset({"system", "user", "assistant", "tool", "function", "developer"})

    @staticmethod
    def _sanitize_api_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转发器 → agent/agent_runtime_helpers/sanitize_api_messages.py"""
        from agent.agent_runtime_helpers import sanitize_api_messages
        return sanitize_api_messages(messages)

    @staticmethod
    def _is_thinking_only_assistant(
        msg: Dict[str, Any],
        *,
        drop_codex_reasoning_items: bool = True,
    ) -> bool:
        """Return True if ``msg`` is an assistant turn whose only payload is reasoning.

        "Thinking-only" means the model emitted reasoning (``reasoning`` or
        ``reasoning_content``) but no visible text and no tool_calls. When sent
        back to providers that convert reasoning into thinking blocks (native
        Anthropic, OpenRouter Anthropic, third-party Anthropic-compatible
        gateways), the resulting message has only thinking blocks — which
        Anthropic rejects with HTTP 400 "The final block in an assistant
        message cannot be `thinking`."

        Symmetric with Claude Code's ``filterOrphanedThinkingOnlyMessages``
        (src/utils/messages.ts). We drop the whole turn from the API copy
        rather than fabricating stub text — the message log (UI transcript)
        keeps the reasoning block; only the wire copy is cleaned.
        """
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            return False
        if msg.get("tool_calls"):
            return False
        # 它有实际输出吗？
        content = msg.get("content")
        if isinstance(content, str):
            if content.strip():
                return False
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    if block:  # non-empty non-dict string etc.
                        return False
                    continue
                btype = block.get("type")
                if btype in {"thinking", "redacted_thinking"}:
                    continue
                if btype == "text":
                    text = block.get("text", "")
                    if isinstance(text, str) and text.strip():
                        return False
                    continue
                # tool_use、image、document 等 —— 真实负载
                return False
        elif content is not None and content != "":
            return False
        # Content is empty-ish. Is there reasoning to make it thinking-only?
        reasoning = msg.get("reasoning_content") or msg.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return True
        # reasoning_details list form
        rd = msg.get("reasoning_details")
        if isinstance(rd, list) and rd:
            return True
        # Codex Responses stores encrypted reasoning state under a separate
        # assistant-message key. Treat only real reasoning items as
        # 仅 thinking；空/垃圾列表应该落到通用
        # empty-turn handling，而非 being dropped here。
        codex_items = msg.get("codex_reasoning_items")
        if drop_codex_reasoning_items and isinstance(codex_items, list):
            return any(
                isinstance(item, dict) and item.get("type") == "reasoning"
                for item in codex_items
            )
        return False

    @staticmethod
    def _drop_thinking_only_and_merge_users(
        messages: List[Dict[str, Any]],
        *,
        drop_codex_reasoning_items: bool = True,
    ) -> List[Dict[str, Any]]:
        """转发器 → agent/agent_runtime_helpers/drop_thinking_only_and_merge_users.py"""
        from agent.agent_runtime_helpers import drop_thinking_only_and_merge_users
        return drop_thinking_only_and_merge_users(
            messages,
            drop_codex_reasoning_items=drop_codex_reasoning_items,
        )

    @staticmethod
    def _cap_delegate_task_calls(tool_calls: list) -> list:
        """将过多的 delegate_task 调用截断到 max_concurrent_children。

        The delegate_tool caps the task list inside a single call, but the
        model can emit multiple separate delegate_task tool_calls in one
        turn.  This truncates the excess, preserving all non-delegate calls.

        Returns the original list if no truncation was needed.
        """
        from tools.delegate_tool import _get_max_concurrent_children
        max_children = _get_max_concurrent_children()
        delegate_count = sum(1 for tc in tool_calls if tc.function.name == "delegate_task")
        if delegate_count <= max_children:
            return tool_calls
        kept_delegates = 0
        truncated = []
        for tc in tool_calls:
            if tc.function.name == "delegate_task":
                if kept_delegates < max_children:
                    truncated.append(tc)
                    kept_delegates += 1
            else:
                truncated.append(tc)
        logger.warning(
            "Truncated %d excess delegate_task call(s) to enforce "
            "max_concurrent_children=%d limit",
            delegate_count - max_children, max_children,
        )
        return truncated

    @staticmethod
    def _deduplicate_tool_calls(tool_calls: list) -> list:
        """在单个 turn 内移除重复的 (tool_name, arguments) 对。

        Only the first occurrence of each unique pair is kept.
        Returns the original list if no duplicates were found.
        """
        seen: set = set()
        unique: list = []
        for tc in tool_calls:
            key = (tc.function.name, tc.function.arguments)
            if key not in seen:
                seen.add(key)
                unique.append(tc)
            else:
                logger.warning("Removed duplicate 工具调用: %s", tc.function.name)
        return unique if len(unique) < len(tool_calls) else tool_calls

    @staticmethod
    def _uniquify_tool_call_ids(tool_calls: list) -> list:
        """Ensure every 工具调用 in a single assistant turn has a distinct id.

        Some models/providers reuse one call id across different calls in a
        single batch (observed with native Kimi Responses replays, Ollama-
        compatible endpoints, and degraded models at long context; same bug
        class as openclaw/openclaw#110518 / #110956). Duplicate ids are lossy
        downstream: the pre-API sanitizer keeps only the first call/result
        pair per id (#58327), so the later call's result silently vanishes
        from every replayed payload, and strict providers (Anthropic
        tool_use, DeepSeek) reject duplicate ids outright.

        The first occurrence keeps its id; later collisions get a
        deterministic ``<id>_d<n>`` suffix — never a random UUID, which would
        break prompt-cache prefix stability across replays. Mutates the
        entries in place (SDK models / SimpleNamespace / dicts) and returns
        the same list. Blank/missing ids are left for the deterministic
        fallback in ``build_assistant_message``.
        """
        seen: set = set()
        for tc in tool_calls or []:
            if isinstance(tc, dict):
                raw = tc.get("call_id") or tc.get("id") or ""
            else:
                raw = getattr(tc, "call_id", None) or getattr(tc, "id", None) or ""
            raw = raw.strip() if isinstance(raw, str) else ""
            if not raw:
                continue
            # 复合 Responses id（"call_x|fc_y"）在调用
            # 每个 turn half — that's the pairing key providers enforce。
            cid = raw.split("|", 1)[0]
            if not cid:
                continue
            if cid not in seen:
                seen.add(cid)
                continue
            n = 2
            new_id = f"{cid}_d{n}"
            while new_id in seen:
                n += 1
                new_id = f"{cid}_d{n}"
            seen.add(new_id)

            def _renamed(value):
                # 保留复合 id 的 response-item 一半，以便提供商的真实 fc_/item id
                # 在重命名后幸存。
                if isinstance(value, str) and "|" in value:
                    return f"{new_id}|{value.split('|', 1)[1]}"
                return new_id

            try:
                if isinstance(tc, dict):
                    if tc.get("id"):
                        tc["id"] = _renamed(tc["id"])
                    else:
                        tc["id"] = new_id
                    if tc.get("call_id"):
                        tc["call_id"] = new_id
                else:
                    tc.id = _renamed(getattr(tc, "id", None))
                    if getattr(tc, "call_id", None):
                        tc.call_id = new_id
            except Exception:
                logger.warning(
                    "Could not uniquify duplicate 工具调用 id %s", cid
                )
                continue
            _fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
            _fn_name = (_fn.get("name") if isinstance(_fn, dict) else getattr(_fn, "name", None)) or "?"
            logger.warning(
                "Model reused 工具调用 id %s within one turn; renamed the "
                "duplicate to %s (tool=%s) to keep call/result pairing "
                "lossless.", cid, new_id, _fn_name,
            )
        return tool_calls

    def _repair_tool_call(self, tool_name: str) -> str | None:
        """转发器 → agent/agent_runtime_helpers/repair_tool_call.py"""
        from agent.agent_runtime_helpers import repair_tool_call
        return repair_tool_call(self, tool_name)

    def _invalidate_system_prompt(self):
        """转发器 → agent/system_prompt/invalidate_system_prompt.py"""
        from agent.system_prompt import invalidate_system_prompt
        invalidate_system_prompt(self)

    @staticmethod
    def _deterministic_call_id(fn_name: str, arguments: str, index: int = 0) -> str:
        """Generate a deterministic call_id from 工具调用 content.

        Used as a fallback when the API doesn't provide a call_id.
        Deterministic IDs prevent cache invalidation — random UUIDs would
        make every API call's prefix unique, breaking OpenAI's prompt cache.
        """
        return _codex_deterministic_call_id(fn_name, arguments, index)

    @staticmethod
    def _split_responses_tool_id(raw_id: Any) -> tuple[Optional[str], Optional[str]]:
        """将存储的工具 ID 拆分为 (call_id, response_item_id)。"""
        return _codex_split_responses_tool_id(raw_id)

    def _derive_responses_function_call_id(
        self,
        call_id: str,
        response_item_id: Optional[str] = None,
    ) -> str:
        """构建有效的 Responses `function_call.id`（必须以 `fc_` 开头）。"""
        return _codex_derive_responses_function_call_id(call_id, response_item_id)

    def _thread_identity(self) -> str:
        thread = threading.current_thread()
        return f"{thread.name}:{thread.ident}"

    def _client_log_context(self) -> str:
        provider = getattr(self, "provider", "unknown")
        base_url = getattr(self, "base_url", "unknown")
        model = getattr(self, "model", "unknown")
        return (
            f"thread={self._thread_identity()} provider={provider} "
            f"base_url={base_url} model={model}"
        )

    def _openai_client_lock(self) -> threading.RLock:
        lock = getattr(self, "_client_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._client_lock = lock
        return lock

    @staticmethod
    def _is_openai_client_closed(client: Any) -> bool:
        """Check if an OpenAI client is closed.

        Handles both property and method forms of is_closed:
        - httpx.Client.is_closed is a bool property
        - openai.OpenAI.is_closed is a method returning bool

        Prior bug: getattr(client, "is_closed", False) returned the bound method,
        which is always truthy, causing unnecessary client recreation on every call.
        """
        from unittest.mock import Mock

        if isinstance(client, Mock):
            return False

        is_closed_attr = getattr(client, "is_closed", None)
        if is_closed_attr is not None:
            # 处理方法（openai SDK）vs 属性（httpx）
            if callable(is_closed_attr):
                if is_closed_attr():
                    return True
            elif bool(is_closed_attr):
                return True

        http_client = getattr(client, "_client", None)
        if http_client is not None:
            return bool(getattr(http_client, "is_closed", False))
        return False

    @staticmethod
    def _build_keepalive_http_client(base_url: str = "", *, verify: Any = True) -> Any:
        """Build an httpx.Client with proactive idle-connection reaping.

        Previously this method injected a custom ``httpx.HTTPTransport``
        with ``socket_options`` (``SO_KEEPALIVE``, ``TCP_KEEPIDLE``, …) to
        prevent CLOSE-WAIT accumulation on long-lived connections (#10324).

        That approach broke streaming for providers behind reverse proxies
        (OpenResty, Cloudflare, etc.) because the custom socket options
        conflict with the proxy's chunked-transfer handling (#54049,
        #12952）。它还剥离了 ``TCP_NODELAY``，导致 TLS 握手停滞
        and SSE encoding.

        The fix moves connection lifecycle management from the socket layer
        to the HTTP pool layer: ``keepalive_expiry=20.0`` tells httpx to
        close idle pooled connections *before* a reverse proxy's typical
        30–60 s timeout drops them, preventing CLOSE-WAIT accumulation
        without modifying socket options.  The default httpx transport
        preserves OS TCP defaults (including ``TCP_NODELAY``).

        ``verify`` carries per-provider ``ssl_ca_cert`` / ``ssl_verify`` and
        ``HERMES_CA_BUNDLE`` settings.  It is passed on the client AND on
        the plain no-proxy mounts (a mounted transport owns the SSL context
        for its scheme).
        """
        try:
            import httpx as _httpx

            # 显式读取代理设置，以便请求正确路由通过 HTTP_PROXY / HTTPS_PROXY / NO_PROXY。
            _proxy = _get_proxy_for_base_url(base_url)

            # 主动池收割：在 20 秒关闭空闲连接，
            # 在反向代理（通常 30-60 秒）发送 FIN 并导致 CLOSE-WAIT 累积之前。
            _limits = _httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=20.0,
            )

            # Timeouts: generous read=None for SSE streaming endpoints.
            _timeout = _httpx.Timeout(
                connect=15.0,
                read=None,
                write=15.0,
                pool=10.0,
            )

            # 当 _proxy 为 None（NO_PROXY 绕过或未配置代理）时，挂载普通传输以防止 httpx 读取环境代理
            # 变量并创建会绕过我们 NO_PROXY 解析的 HTTPProxy 挂载。
            _mounts = {}
            if _proxy is None:
                _mounts = {
                    "http://": _httpx.HTTPTransport(verify=verify),
                    "https://": _httpx.HTTPTransport(verify=verify),
                }
            return _httpx.Client(
                limits=_limits,
                timeout=_timeout,
                proxy=_proxy,
                mounts=_mounts or None,
                verify=verify,
            )
        except Exception:
            return None

    def _create_openai_client(self, client_kwargs: dict, *, reason: str, shared: bool) -> Any:
        """转发器 → agent/agent_runtime_helpers/create_openai_client.py"""
        from agent.agent_runtime_helpers import create_openai_client
        return create_openai_client(self, client_kwargs, reason=reason, shared=shared)

    @staticmethod
    def _force_close_tcp_sockets(client: Any) -> int:
        """转发器 → agent/agent_runtime_helpers/force_close_tcp_sockets.py"""
        from agent.agent_runtime_helpers import force_close_tcp_sockets
        return force_close_tcp_sockets(client)

    def _close_openai_client(self, client: Any, *, reason: str, shared: bool) -> None:
        if client is None:
            return
        # 首先强制关闭 TCP socket 以防止 CLOSE-WAIT 累积，然后进行优雅的 SDK 级别关闭。
        force_closed = self._force_close_tcp_sockets(client)
        try:
            client.close()
            logger.info(
                "OpenAI client closed (%s, shared=%s, tcp_force_closed=%d) %s",
                reason,
                shared,
                force_closed,
                self._client_log_context(),
            )
        except Exception as exc:
            logger.debug(
                "OpenAI client close failed (%s, shared=%s) %s error=%s",
                reason,
                shared,
                self._client_log_context(),
                exc,
            )

    def _retire_shared_openai_client(self, client: Any, *, reason: str) -> None:
        """Ownership-safe retirement of a replaced shared OpenAI client.

        #70773 / #67142 / #29507：``client.close()`` 释放池的原始
        FDs from the *calling* thread. The shared primary client has no single
        owning thread — worker threads from stale-killed attempts may still be
        unwinding their SSL BIOs, and the codex-direct / MoA paths stream on
        the 共享客户端 itself. If we release an FD while another thread's
        SSL layer still caches the raw integer fd, the kernel can recycle it
        into an unrelated ``open()`` (e.g. ``kanban.db``) and the unwinding
        TLS flush then writes an application-data record into that file — the
        SQLite-header corruption documented in #29507/#70773.

        Only an owner may release FDs, and a replaced 共享客户端 has none.
        So nobody calls ``close()``: we ``shutdown()`` the pooled sockets
        (FD-safe from any thread; unblocks in-flight readers with EOF/EPIPE)
        and defer the actual FD release to garbage collection. Refcounting
        guarantees the underlying sockets are only collected once every
        thread that borrowed the client has unwound — GC *is* the ownership
        handshake. In the common case (no borrower) the refcount hits zero on
        this line and the FDs are released immediately anyway.
        """
        if client is None:
            return
        try:
            shutdown_count = self._force_close_tcp_sockets(client)
            logger.info(
                "Shared OpenAI client retired (%s, tcp_shutdown=%d, "
                "fd_release=deferred_to_gc) %s",
                reason,
                shutdown_count,
                self._client_log_context(),
            )
        except Exception as exc:
            logger.debug(
                "Shared OpenAI client retire failed (%s) %s error=%s",
                reason,
                self._client_log_context(),
                exc,
            )

    def _replace_primary_openai_client(self, *, reason: str) -> bool:
        with self._openai_client_lock():
            old_client = getattr(self, "client", None)
            try:
                new_client = self._create_openai_client(self._client_kwargs, reason=reason, shared=True)
            except Exception as exc:
                logger.warning(
                    "Failed to rebuild shared OpenAI client (%s) %s error=%s",
                    reason,
                    self._client_log_context(),
                    exc,
                )
                return False
            self.client = new_client
        # #70773: never hard-close the replaced 共享客户端 from here — the
        # 调用者可能不是其请求仍在
        # old pool (凭证旋转 and dead-connection cleanup run on the
        # turn 线程，而过期被杀的工作线程展开；codex-direct 路径
        # streams on the 共享客户端 itself). Retire it instead: sockets are
        # 关闭（FD 安全），FD 释放延迟到 GC。
        self._retire_shared_openai_client(old_client, reason=f"replace:{reason}")
        return True

    def _ensure_primary_openai_client(self, *, reason: str) -> Any:
        with self._openai_client_lock():
            client = getattr(self, "client", None)
            if client is not None and not self._is_openai_client_closed(client):
                return client
            old_client = client
            try:
                new_client = self._create_openai_client(
                    self._client_kwargs, reason=reason, shared=True
                )
            except Exception as exc:
                logger.warning(
                    "Failed to recreate closed OpenAI client (%s) %s error=%s",
                    reason,
                    self._client_log_context(),
                    exc,
                )
                raise RuntimeError("Failed to recreate closed OpenAI client") from exc
            self.client = new_client

        logger.warning(
            "Detected closed shared OpenAI client; recreated before use (%s) %s",
            reason,
            self._client_log_context(),
        )
        self._close_openai_client(old_client, reason=f"replace:{reason}", shared=True)
        return new_client

    def _cleanup_dead_connections(self) -> bool:
        """转发器 → agent/agent_runtime_helpers/cleanup_dead_connections.py"""
        from agent.agent_runtime_helpers import cleanup_dead_connections
        return cleanup_dead_connections(self)

    @staticmethod
    def _api_kwargs_have_image_parts(api_kwargs: dict) -> bool:
        """当出站请求仍包含本地图像部分时返回 True。"""
        if not isinstance(api_kwargs, dict):
            return False
        candidates = []
        messages = api_kwargs.get("messages")
        if isinstance(messages, list):
            candidates.extend(messages)
        # Responses API 负载使用 `input`；转换后，图像部分可以
        # still be present there，而非 in `messages`。
        response_input = api_kwargs.get("input")
        if isinstance(response_input, list):
            candidates.extend(response_input)

        def _contains_image(value: Any) -> bool:
            if isinstance(value, dict):
                ptype = value.get("type")
                if ptype in {"image_url", "input_image"}:
                    return True
                return any(_contains_image(v) for v in value.values())
            if isinstance(value, list):
                return any(_contains_image(v) for v in value)
            return False

        return any(_contains_image(item) for item in candidates)

    def _copilot_headers_for_request(self, *, is_vision: bool) -> dict:
        from hermes_cli.copilot_auth import copilot_request_headers

        return copilot_request_headers(is_agent_turn=True, is_vision=is_vision)

    # 请求工作线程自己的 ``finally`` 展开报告的关闭原因，针对产生响应的请求 ——
    # 这是唯一同时来自拥有池 FD 的线程 AND 证明池健康的关闭。
    # 只有这些可以为下一次调用保留线路客户端，毒化仍然获胜：跨线程中止（#29507）标记槽，所以即使
    # worker-finally 关闭丢弃它。每个其他原因（错误清理、过期/中断杀死、重试清理）都得到真实关闭，所以重试
    # after a request error 始终 builds a fresh pool。
    _REQUEST_CLIENT_REUSE_REASONS = frozenset({
        "request_complete",
        "stream_request_complete",
    })

    def _request_client_cache_ref(self) -> dict:
        # Lazy init — tests build agents via AIAgent.__new__ 不用 __init__。
        cache = getattr(self, "_request_client_cache", None)
        if cache is None:
            cache = {"client": None, "kwargs": None, "poisoned": False, "in_use": False}
            self._request_client_cache = cache
        return cache

    def _create_request_openai_client(self, *, reason: str, api_kwargs: Optional[dict] = None) -> Any:
        from unittest.mock import Mock

        primary_client = self._ensure_primary_openai_client(reason=reason)
        if self.provider == "moa":
            return primary_client
        if isinstance(primary_client, Mock):
            return primary_client
        with self._openai_client_lock():
            request_kwargs = dict(self._client_kwargs)
        # Per-request OpenAI-wire clients (used by both the non-streaming
        # chat-completions path and the streaming chat-completions path
        # `_interruptible_api_call` 中）不应运行 SDK 的内置重试循环：Agent 的外层循环
        # 拥有带凭证轮换、提供商降级和退避的重试，SDK 无法
        # 见。保留 SDK 重试（默认 2）与我们外层的重试复合，让单个挂起的提供商请求延伸到约 3 倍
        # 在 our stale detector reports it 之前，the per-call timeout。
        # 共享/主客户端和 Anthropic / Bedrock 路径不受影响（它们不经过这里）。
        request_kwargs["max_retries"] = 0
        if (
            base_url_host_matches(str(request_kwargs.get("base_url", "")), "githubcopilot.com")
            and self._api_kwargs_have_image_parts(api_kwargs or {})
        ):
            request_kwargs["default_headers"] = self._copilot_headers_for_request(is_vision=True)
        # 当有效 kwargs 不变时重用缓存的线路客户端：构建 openai.OpenAI + 其 httpx 池成本为
        # 每个 LLM call (fresh TCP+TLS handshake), ~5x per turn ~19-35ms。
        # 缓存是一个单一检出槽：`in_use` 防止两个并发调用共享一个池的 close/abort
        # 生命周期（第二个并发调用得到一个新鲜的未追踪客户端，
        # 旧的每请求构建行为）。
        stale = None
        with self._openai_client_lock():
            cache = self._request_client_cache_ref()
            cached = cache["client"]
            if cached is not None and not cache["in_use"]:
                if (
                    not cache["poisoned"]
                    and cache["kwargs"] == request_kwargs
                    and not self._is_openai_client_closed(cached)
                ):
                    cache["in_use"] = True
                    return cached
                # kwargs changed (凭证旋转, provider 故障转移),
                # 被跨线程中止毒化（#29507），或外部
                # closed — 绝不 reuse; discard and rebuild below。
                stale = cached
                cache["client"] = None
                cache["kwargs"] = None
                cache["poisoned"] = False
        if stale is not None:
            # 可以安全地从此线程关闭：in_use 为 False，所以没有工作线程拥有池的 FD
            #（#29507 关注在另一个线程上有飞行中请求的客户端）。
            self._close_openai_client(stale, reason=f"reuse_evict:{reason}", shared=False)
        client = self._create_openai_client(request_kwargs, reason=reason, shared=False)
        with self._openai_client_lock():
            cache = self._request_client_cache_ref()
            if cache["client"] is None:
                cache["client"] = client
                # 快照嵌套字典（default_headers）：轮换站点今天分配新鲜内部字典，
                # 但别名的内部
                # 在 in-place mutation 之后，object would compare equal even。
                cache["kwargs"] = {
                    k: dict(v) if isinstance(v, dict) else v
                    for k, v in request_kwargs.items()
                }
                cache["poisoned"] = False
                cache["in_use"] = True
            # else：并发调用持有槽 —— 将此客户端未追踪地交出；
            # _close_request_openai_client 完全关闭未追踪客户端，保留每请求生命周期。
        return client

    def _close_request_openai_client(self, client: Any, *, reason: str) -> None:
        with self._openai_client_lock():
            cache = self._request_client_cache_ref()
            if cache["client"] is client:
                if reason in self._REQUEST_CLIENT_REUSE_REASONS and not cache["poisoned"]:
                    # 在拥有线程上正常完成 —— 保留线路客户端（及其温暖的 httpx 池）
                    # 供下一个顺序调用使用。
                    cache["in_use"] = False
                    return
                # 失败/杀死/中止结果：丢弃槽并落到真实关闭。这在拥有工作线程上运行，
                # FD 释放属于这里（#29507）。
                cache["client"] = None
                cache["kwargs"] = None
                cache["poisoned"] = False
                cache["in_use"] = False
        self._close_openai_client(client, reason=reason, shared=False)

    def _close_cached_request_openai_client(self, *, reason: str) -> None:
        """拆卸钩子：真正关闭缓存的每请求线路客户端。"""
        with self._openai_client_lock():
            cache = getattr(self, "_request_client_cache", None)
            client = cache["client"] if cache else None
            in_use = bool(cache["in_use"]) if cache else False
            if cache is not None:
                cache["client"] = None
                cache["kwargs"] = None
                cache["poisoned"] = False
                cache["in_use"] = False
        if client is None:
            return
        if in_use:
            # 一个工作线程为此客户端检出用于飞行中请求（工作线程可以比 turn 活得长 ——
            # 见 interruptible_api_call）。此处的 client.close() 会从陌生线程释放其 FD，
            # #29507 竞态拆卸绝不能重新引入。改为中止 socket
            # 替代；槽已被清除，所以工作线程自己的 finally看到未追踪的客户端并在其线程上执行真实关闭。
            self._abort_request_openai_client(client, reason=f"{reason}_in_flight")
            return
        self._close_openai_client(client, reason=reason, shared=False)

    def _abort_request_openai_client(self, client: Any, *, reason: str) -> None:
        """跨线程中止：关闭 socket 而不释放 FD。

        Companion to :meth:`_close_request_openai_client` for stranger-thread
        callers (interrupt-check loop, stale-call detector). Calling
        ``client.close()`` from a thread that does not own the active httpx
        connection raced the still-live SSL BIO and corrupted unrelated file
        descriptors when the kernel recycled the just-freed TCP FD (#29507).

        Here we only ``shutdown(SHUT_RDWR)`` the pool's sockets. That unblocks
        the owning worker thread's pending ``recv``/``send`` with an EOF or
        ``EPIPE`` so it can unwind and close ``client`` from its own context
        — which is where the FD release belongs.
        """
        if client is None:
            return
        # 从陌生线程关闭了 socket 的池绝不能重用：毒化缓存槽，以便拥有者线程关闭
        # 丢弃它，下一次 create 构建新鲜客户端。
        with self._openai_client_lock():
            cache = self._request_client_cache_ref()
            if cache["client"] is client:
                cache["poisoned"] = True
        try:
            shutdown_count = self._force_close_tcp_sockets(client)
            # tcp_force_closed=0 意味着陌生线程中止没有找到要关闭的 socket ——
            # 工作线程仍然阻塞在 recv 中，提供商保留槽（#72975）。将其作为 WARNING
            # 呈现，以便
            # 在日志中不会被误认为成功中止。
            _log = logger.warning if shutdown_count == 0 else logger.info
            _log(
                "OpenAI client aborted (%s, shared=False, tcp_force_closed=%d, "
                "deferred_close=stranger_thread) %s%s",
                reason,
                shutdown_count,
                self._client_log_context(),
                (
                    " — no sockets found; in-flight request may keep running "
                    "until the provider finishes"
                    if shutdown_count == 0
                    else ""
                ),
            )
        except Exception as exc:
            logger.debug(
                "OpenAI client abort failed (%s, shared=False) %s error=%s",
                reason,
                self._client_log_context(),
                exc,
            )

    def _create_request_anthropic_client(self, *, reason: str) -> Any:
        """Build a request-local Anthropic client for one in-flight call.

        The shared ``_anthropic_client`` stays the long-lived primary, but the
        stale/interrupt watchdog runs on the poll thread and must never call
        ``close()`` on the client whose TLS socket a worker thread is still
        reading: releasing that FD from a stranger thread lets the kernel
        recycle it under a still-live SSL BIO, which then writes a TLS record
        into an unrelated SQLite header (#29507 / #67142). A per-请求客户端
        lets the stranger thread ``shutdown()`` the socket while the owning
        worker performs the SDK-level close from its own context — the same
        ownership contract the OpenAI-wire path already uses.

        Mirrors ``_rebuild_anthropic_client`` construction (direct + Bedrock,
        1M-beta drop) but returns a fresh client instead of swapping the shared
        one.
        """
        if self.api_mode == "anthropic_messages":
            self._try_refresh_anthropic_client_credentials()
        _drop_1m = bool(getattr(self, "_oauth_1m_beta_disabled", False))
        if getattr(self, "provider", None) == "bedrock":
            from agent.anthropic_adapter import build_anthropic_bedrock_client
            region = getattr(self, "_bedrock_region", "us-east-1") or "us-east-1"
            client = build_anthropic_bedrock_client(region)
        else:
            from agent.anthropic_adapter import build_anthropic_client
            client = build_anthropic_client(
                self._anthropic_api_key,
                getattr(self, "_anthropic_base_url", None),
                timeout=get_provider_request_timeout(self.provider, self.model),
                drop_context_1m_beta=_drop_1m,
            )
        logger.debug(
            "Anthropic 请求客户端 created (%s, shared=False) provider=%s model=%s",
            reason,
            getattr(self, "provider", None),
            getattr(self, "model", None),
        )
        return client

    def _close_request_anthropic_client(self, client: Any, *, reason: str) -> None:
        """拥有者线程完全关闭请求本地 Anthropic 客户端。

        Force-closes the pool's TCP sockets first (CLOSE-WAIT hygiene, parity
        with ``_close_openai_client``), then does the graceful SDK close. Safe
        because the caller owns the connection.
        """
        if client is None:
            return
        try:
            self._force_close_tcp_sockets(client)
            client.close()
            logger.info(
                "Anthropic client closed (%s, shared=False) provider=%s model=%s",
                reason,
                getattr(self, "provider", None),
                getattr(self, "model", None),
            )
        except Exception as exc:
            logger.debug(
                "Anthropic client close failed (%s, shared=False) provider=%s model=%s error=%s",
                reason,
                getattr(self, "provider", None),
                getattr(self, "model", None),
                exc,
            )

    def _abort_request_anthropic_client(self, client: Any, *, reason: str) -> None:
        """Cross-thread abort for request-local Anthropic clients.

        Stranger threads (the interrupt-check / stale-stream detector loop)
        must not call the SDK ``close()`` — that races the owning worker's live
        SSL BIO and can recycle a TLS FD into a SQLite header (#29507 /
        #67142）。仅 ``shutdown(SHUT_RDWR)`` 池的 socket，以便工作线程
        unblocks and releases the FD from its own thread.
        """
        if client is None:
            return
        try:
            shutdown_count = self._force_close_tcp_sockets(client)
            # 与 OpenAI 中止路径相同的可见性合约（#72975）：零 socket 关闭意味着中止没有解除阻塞
            # worker —— 记录 WARNING，而不是成功形状的 INFO。
            _log = logger.warning if shutdown_count == 0 else logger.info
            _log(
                "Anthropic client aborted (%s, shared=False, tcp_force_closed=%d, "
                "deferred_close=stranger_thread) provider=%s model=%s%s",
                reason,
                shutdown_count,
                getattr(self, "provider", None),
                getattr(self, "model", None),
                (
                    " — no sockets found; in-flight request may keep running "
                    "until the provider finishes"
                    if shutdown_count == 0
                    else ""
                ),
            )
        except Exception as exc:
            logger.debug(
                "Anthropic client abort failed (%s, shared=False) provider=%s model=%s error=%s",
                reason,
                getattr(self, "provider", None),
                getattr(self, "model", None),
                exc,
            )

    def _run_codex_stream(self, api_kwargs: dict, client: Any = None, on_first_delta: callable = None):
        """转发器 → agent/codex_runtime/run_codex_stream.py"""
        from agent.codex_runtime import run_codex_stream
        return run_codex_stream(self, api_kwargs, client, on_first_delta)

    def _run_codex_create_stream_fallback(self, api_kwargs: dict, client: Any = None):
        """转发器 → agent/codex_runtime/run_codex_create_stream_fallback.py"""
        from agent.codex_runtime import run_codex_create_stream_fallback
        return run_codex_create_stream_fallback(self, api_kwargs, client)

    def _try_refresh_codex_client_credentials(self, *, force: bool = True) -> bool:
        if self.api_mode != "codex_responses" or self.provider not in {"openai-codex", "xai-oauth"}:
            return False

        # 防止静默账户交换。
        #
        # 当 Agent 使用非单例凭证时 —— 例如手动池条目（``hermes auth add xai-oauth``），其 token 属于
        # 与 device_code 单例不同的账户，或用显式 ``api_key=`` 参数构建的 Agent —— 强制刷新
        # 此处的单例并采用其 token 会静默将对话的其余部分重新路由到单例的账户。
        # 凭证池的反应性恢复（``_recover_with_credential_pool``）是这种情况的正确通道；此路径是池无法恢复时使用的仅单例回退，并且
        # MUST 仅 fire when the agent really is on singleton tokens。
        try:
            if self.provider == "openai-codex":
                from hermes_cli.auth import resolve_codex_runtime_credentials

                singleton_now = resolve_codex_runtime_credentials(
                    refresh_if_expiring=False,
                )
            else:
                from hermes_cli.auth import resolve_xai_oauth_runtime_credentials

                singleton_now = resolve_xai_oauth_runtime_credentials(
                    refresh_if_expiring=False,
                )
        except Exception as exc:
            logger.debug("%s singleton read failed: %s", self.provider, exc)
            return False

        singleton_key = str(singleton_now.get("api_key") or "").strip()
        active_key = str(self.api_key or "").strip()
        if singleton_key and active_key and singleton_key != active_key:
            logger.debug(
                "%s singleton tokens differ from the active api_key; "
                "skipping singleton force-refresh to avoid silent account swap. "
                "Reactive 凭证旋转 should go through the pool.",
                self.provider,
            )
            return False

        try:
            if self.provider == "openai-codex":
                from hermes_cli.auth import resolve_codex_runtime_credentials

                creds = resolve_codex_runtime_credentials(force_refresh=force)
            else:
                from hermes_cli.auth import resolve_xai_oauth_runtime_credentials

                creds = resolve_xai_oauth_runtime_credentials(force_refresh=force)
        except Exception as exc:
            logger.debug("%s credential refresh failed: %s", self.provider, exc)
            return False

        api_key = creds.get("api_key")
        base_url = creds.get("base_url")
        if not isinstance(api_key, str) or not api_key.strip():
            return False
        if not isinstance(base_url, str) or not base_url.strip():
            return False

        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/")
        self._client_kwargs["api_key"] = self.api_key
        self._client_kwargs["base_url"] = self.base_url

        if not self._replace_primary_openai_client(reason=f"{self.provider}_credential_refresh"):
            return False

        return True

    def _try_refresh_nous_client_credentials(
        self,
        *,
        force: bool = True,
    ) -> bool:
        if self.provider != "nous":
            return False
        # Portal 在原生 Messages 路由上提供 anthropic/*，所以会话在短暂调用 JWT 时可以持有任一客户端类型
        # 过期。两者都需要刷新，否则 turn 会在 401 上死亡。
        if self.api_mode not in ("chat_completions", "anthropic_messages"):
            return False

        try:
            from hermes_cli.auth import resolve_nous_runtime_credentials

            creds = resolve_nous_runtime_credentials(
                timeout_seconds=env_float("HERMES_NOUS_TIMEOUT_SECONDS", 15),
                force_refresh=force,
            )
        except Exception as exc:
            logger.debug("Nous credential refresh failed: %s", exc)
            return False

        api_key = creds.get("api_key")
        base_url = creds.get("base_url")
        if not isinstance(api_key, str) or not api_key.strip():
            return False
        if not isinstance(base_url, str) or not base_url.strip():
            return False

        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/")

        if self.api_mode == "anthropic_messages":
            self._anthropic_api_key = self.api_key
            self._anthropic_base_url = self.base_url
            self._rebuild_anthropic_client()
            return True

        self._client_kwargs["api_key"] = self.api_key
        self._client_kwargs["base_url"] = self.base_url
        # Nous requests 应 not inherit OpenRouter-only attribution headers。
        self._client_kwargs.pop("default_headers", None)

        if not self._replace_primary_openai_client(reason="nous_credential_refresh"):
            return False

        return True

    def _try_refresh_vertex_client_credentials(self) -> bool:
        """重新铸造 Vertex OAuth2 访问令牌并重建 OpenAI 客户端。

        Vertex tokens live ~1 hour. On a long-lived agent (gateway session) a
        cached client's bearer token will expire mid-session, producing a 401.
        This re-resolves credentials via the adapter (which refreshes the
        underlying google-auth Credentials object when near expiry), swaps the
        new token into the client kwargs, and rebuilds the primary OpenAI
        client. Returns True when a usable token+base_url were obtained.
        """
        if self.api_mode != "chat_completions" or self.provider != "vertex":
            return False

        try:
            from agent.vertex_adapter import get_vertex_config

            token, base_url = get_vertex_config()
        except Exception as exc:
            logger.debug("Vertex credential refresh failed: %s", exc)
            return False

        if not isinstance(token, str) or not token.strip():
            return False
        if not isinstance(base_url, str) or not base_url.strip():
            return False

        self.api_key = token.strip()
        self.base_url = base_url.strip().rstrip("/")
        self._client_kwargs["api_key"] = self.api_key
        self._client_kwargs["base_url"] = self.base_url

        if not self._replace_primary_openai_client(reason="vertex_credential_refresh"):
            return False

        logger.info("Vertex AI OAuth token refreshed")
        return True

    def _try_refresh_copilot_client_credentials(self) -> bool:
        """刷新 Copilot 凭证并重建共享 OpenAI 客户端。

        Copilot tokens may remain the same string across refreshes (`gh auth token`
        returns a stable OAuth token in many setups). We still rebuild the client
        on 401 so retries recover from stale auth/client state without requiring
        a session restart.
        """
        if self.provider != "copilot":
            return False

        try:
            from hermes_cli.copilot_auth import resolve_copilot_token

            new_token, token_source = resolve_copilot_token()
        except Exception as exc:
            logger.debug("Copilot credential refresh failed: %s", exc)
            return False

        if not isinstance(new_token, str) or not new_token.strip():
            return False

        new_token = new_token.strip()

        self.api_key = new_token
        self._client_kwargs["api_key"] = self.api_key
        self._client_kwargs["base_url"] = self.base_url
        self._apply_client_headers_for_base_url(str(self.base_url or ""))

        if not self._replace_primary_openai_client(reason="copilot_credential_refresh"):
            return False

        logger.info("Copilot credentials refreshed from %s", token_source)
        return True

    def _try_refresh_anthropic_client_credentials(self) -> bool:
        if self.api_mode != "anthropic_messages" or not hasattr(self, "_anthropic_api_key"):
            return False
        # 仅为原生 Anthropic 提供商刷新凭证。其他 anthropic_messages 提供商（MiniMax、阿里巴巴等）使用自己的 key。
        if self.provider != "anthropic":
            return False
        # Azure 端点使用静态 API key —— OAuth token 轮换不适用。
        # 刷新会拾取 ~/.claude/.credentials.json OAuth token 并破坏认证。
        _base = getattr(self, "_anthropic_base_url", "") or ""
        if "azure.com" in _base:
            return False

        try:
            from agent.anthropic_adapter import resolve_anthropic_token, build_anthropic_client

            new_token = resolve_anthropic_token()
        except Exception as exc:
            logger.debug("Anthropic credential refresh failed: %s", exc)
            return False

        if not isinstance(new_token, str) or not new_token.strip():
            return False
        new_token = new_token.strip()
        if new_token == self._anthropic_api_key:
            return False

        try:
            self._anthropic_client.close()
        except Exception:
            pass

        try:
            self._anthropic_client = build_anthropic_client(
                new_token,
                getattr(self, "_anthropic_base_url", None),
                timeout=get_provider_request_timeout(self.provider, self.model),
            )
        except Exception as exc:
            logger.warning("Failed to rebuild Anthropic client after credential refresh: %s", exc)
            return False

        self._anthropic_api_key = new_token
        # 更新 OAuth flag — token type may have changed (API key ↔ OAuth)。
        # 仅在原生 Anthropic 上视为 OAuth；使用 Anthropic 协议的第三方端点绝不能
        # 触发 OAuth 路径（#1739 和第三方身份注入守卫）。
        from agent.anthropic_adapter import _is_oauth_token
        self._is_anthropic_oauth = _is_oauth_token(new_token) if self.provider == "anthropic" else False
        return True

    def _apply_client_headers_for_base_url(
        self,
        base_url: str,
        *,
        apply_user_headers: bool = True,
    ) -> None:
        from agent.auxiliary_client import (
            build_nvidia_nim_headers,
            build_or_headers,
        )

        if base_url_host_matches(base_url, "openrouter.ai"):
            self._client_kwargs["default_headers"] = build_or_headers()
        elif base_url_host_matches(base_url, "integrate.api.nvidia.com"):
            self._client_kwargs["default_headers"] = build_nvidia_nim_headers(base_url)
        elif base_url_host_matches(base_url, "api.routermint.com"):
            self._client_kwargs["default_headers"] = _routermint_headers()
        elif base_url_host_matches(base_url, "githubcopilot.com"):
            from hermes_cli.models import copilot_default_headers

            self._client_kwargs["default_headers"] = copilot_default_headers()
        elif base_url_host_matches(base_url, "api.kimi.com"):
            self._client_kwargs["default_headers"] = {"User-Agent": "claude-code/0.1.0"}
        elif base_url_host_matches(base_url, "portal.qwen.ai"):
            self._client_kwargs["default_headers"] = _qwen_portal_headers()
        elif base_url_host_matches(base_url, "chatgpt.com"):
            from agent.auxiliary_client import _codex_cloudflare_headers
            self._client_kwargs["default_headers"] = _codex_cloudflare_headers(
                self._client_kwargs.get("api_key", "")
            )
        elif base_url_host_matches(base_url, "x.ai"):
            # 同时覆盖 provider=xai 和 provider=xai-oauth（api.x.ai）。
            from tools.xai_http import hermes_xai_default_headers

            self._client_kwargs["default_headers"] = hermes_xai_default_headers()
        else:
            # 在 clearing 之前，No URL-specific headers — check profile.default_headers。
            _ph_headers = None
            try:
                from providers import get_provider_profile as _gpf2
                _ph2 = _gpf2(self.provider)
                if _ph2 and _ph2.default_headers:
                    _ph_headers = dict(_ph2.default_headers)
            except Exception:
                pass
            if _ph_headers:
                self._client_kwargs["default_headers"] = _ph_headers
            else:
                self._client_kwargs.pop("default_headers", None)

        # 用户配置的覆盖优先于同一提供商的 URL/配置文件默认值
        # route. A credential swap to another endpoint 必须 not inherit them。
        if apply_user_headers:
            self._apply_user_default_headers()

        # 每提供商额外的 HTTP 头（providers.<name>.extra_headers /
        # custom_providers[].extra_headers）—— 最后应用，以便最具体的配置级别
        # 在凭证交换和重建中也能幸存。
        # 安全：values may carry credentials — 绝不 log them。
        if self.api_mode not in ("anthropic_messages", "bedrock_converse"):
            try:
                from hermes_cli.config import (
                    apply_custom_provider_extra_headers_to_client_kwargs,
                )

                apply_custom_provider_extra_headers_to_client_kwargs(
                    self._client_kwargs, base_url,
                )
            except Exception:
                logger.debug("custom-provider extra_headers skipped", exc_info=True)

    def _apply_user_default_headers(self) -> None:
        """Merge user-configured request headers onto the OpenAI client.

        Reads ``model.default_headers`` from config.yaml and merges it onto
        ``self._client_kwargs["default_headers"]``, with user values taking
        precedence over provider- and SDK-supplied defaults.

        This exists for ``custom`` OpenAI-compatible endpoints sitting behind
        a gateway/WAF that rejects the OpenAI Python SDK's identifying headers
        (``User-Agent: OpenAI/Python ...``, ``X-Stainless-*``). Setting e.g.
        ``model.default_headers: {User-Agent: curl/8.7.1}`` lets the request
        reach such an upstream instead of failing with an opaque 4xx/502 even
        though the same body works under ``curl``. (#40033)

        Delegates the config read + merge to
        ``agent.auxiliary_client._apply_user_default_headers`` so the main and
        auxiliary clients can never drift on precedence or value handling.

        No-op for Anthropic/Bedrock modes, which don't use the OpenAI client,
        and when no overrides are configured.
        """
        if self.api_mode in ("anthropic_messages", "bedrock_converse"):
            return
        from agent.auxiliary_client import (
            _apply_user_default_headers as _merge_user_headers,
        )
        merged = _merge_user_headers(self._client_kwargs.get("default_headers"))
        if merged:
            self._client_kwargs["default_headers"] = merged

    def _swap_credential(self, entry) -> None:
        runtime_key = getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", "")
        runtime_base = getattr(entry, "runtime_base_url", None) or getattr(entry, "base_url", None) or self.base_url
        self._credential_pool_entry_id = getattr(entry, "id", None)
        from hermes_cli.route_identity import normalize_route_base_url

        route_changed = normalize_route_base_url(self.base_url) != normalize_route_base_url(
            runtime_base
        )

        if self.api_mode == "anthropic_messages":
            from agent.anthropic_adapter import build_anthropic_client, _is_oauth_token

            try:
                self._anthropic_client.close()
            except Exception:
                pass

            self._anthropic_api_key = runtime_key
            self._anthropic_base_url = runtime_base.rstrip("/") if isinstance(runtime_base, str) else runtime_base
            self._anthropic_client = build_anthropic_client(
                runtime_key, self._anthropic_base_url,
                timeout=get_provider_request_timeout(self.provider, self.model),
            )
            self._is_anthropic_oauth = _is_oauth_token(runtime_key) if self.provider == "anthropic" else False
            self.api_key = runtime_key
            self.base_url = runtime_base.rstrip("/") if isinstance(runtime_base, str) else runtime_base
            return

        self.api_key = runtime_key
        self.base_url = runtime_base.rstrip("/") if isinstance(runtime_base, str) else runtime_base
        self._client_kwargs["api_key"] = self.api_key
        self._client_kwargs["base_url"] = self.base_url
        self._client_kwargs.pop("ssl_verify", None)
        self._client_kwargs.pop("ssl_ca_cert", None)
        try:
            from hermes_cli.config import (
                apply_custom_provider_tls_to_client_kwargs,
                get_compatible_custom_providers,
                load_config_readonly,
            )

            apply_custom_provider_tls_to_client_kwargs(
                self._client_kwargs,
                str(self.base_url or ""),
                get_compatible_custom_providers(load_config_readonly()),
            )
        except Exception:
            logger.debug(
                "custom-provider TLS resolution skipped on 凭证旋转",
                exc_info=True,
            )
        self._apply_client_headers_for_base_url(
            self.base_url,
            apply_user_headers=not route_changed,
        )
        self._replace_primary_openai_client(reason="credential_rotation")

    def _recover_with_credential_pool(
        self,
        *,
        status_code: Optional[int],
        has_retried_429: bool,
        classified_reason: Optional[FailoverReason] = None,
        error_context: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, bool]:
        """转发器 → agent/agent_runtime_helpers/recover_with_credential_pool.py"""
        from agent.agent_runtime_helpers import recover_with_credential_pool
        return recover_with_credential_pool(self, status_code=status_code, has_retried_429=has_retried_429, classified_reason=classified_reason, error_context=error_context)

    def _credential_pool_may_recover_rate_limit(self) -> bool:
        """速率限制重试是否应等待相同提供商的凭证。"""
        pool = self._credential_pool
        if pool is None:
            return False
        return pool.has_available()

    def _anthropic_messages_create(self, api_kwargs: dict, *, client: Any = None):
        # 当提供了请求本地客户端时，它已经在 ``_create_request_anthropic_client`` 中
        # 刷新了凭证；只有共享回退路径在此处刷新。
        if client is None and self.api_mode == "anthropic_messages":
            self._try_refresh_anthropic_client_credentials()
        # 防御性：剥离可能在 api_mode 翻转竞争中泄漏的 Responses 专属 kwargs
        #（Anthropic SDK 对它们抛出不可重试的 TypeError）。见 #31673。
        from agent.anthropic_adapter import create_anthropic_message
        return create_anthropic_message(
            client or self._anthropic_client,
            api_kwargs,
            log_prefix=getattr(self, "log_prefix", ""),
            prefer_stream=not bool(getattr(self, "_disable_streaming", False)),
            # 速率限制 + credits 状态存在于响应头中，解析的 Message 丢弃了它们。
            # 对不发送匹配头族（x-ratelimit-* / x-nous-credits-*）的提供商为空操作。
            on_response=self._capture_anthropic_response_headers,
        )

    def _rebuild_anthropic_client(self) -> None:
        """在中断或过期调用后重建 Anthropic 客户端。

        Handles both direct Anthropic and Bedrock-hosted Anthropic models
        correctly — rebuilding with the Bedrock SDK when provider is bedrock,
        rather than always falling back to build_anthropic_client() which
        requires a direct Anthropic API key.

        Honors ``self._oauth_1m_beta_disabled`` (set by the reactive recovery
        path when an OAuth subscription rejects the 1M-context beta) so the
        rebuilt client carries the reduced beta set.
        """
        _drop_1m = bool(getattr(self, "_oauth_1m_beta_disabled", False))
        if getattr(self, "provider", None) == "bedrock":
            from agent.anthropic_adapter import build_anthropic_bedrock_client
            region = getattr(self, "_bedrock_region", "us-east-1") or "us-east-1"
            self._anthropic_client = build_anthropic_bedrock_client(region)
        else:
            from agent.anthropic_adapter import build_anthropic_client
            self._anthropic_client = build_anthropic_client(
                self._anthropic_api_key,
                getattr(self, "_anthropic_base_url", None),
                timeout=get_provider_request_timeout(self.provider, self.model),
                drop_context_1m_beta=_drop_1m,
            )

    def _interruptible_api_call(self, api_kwargs: dict):
        """转发器 → agent/chat_completion_helpers/interruptible_api_call.py"""
        from agent.chat_completion_helpers import interruptible_api_call
        return interruptible_api_call(self, api_kwargs)

    # ── Unified streaming API call ─────────────────────────────────────────

    def _reset_stream_delivery_tracking(self) -> None:
        """重置当前模型响应期间传递的文本追踪。"""
        # 首先刷新 think 清理器持有的任何良性部分标签尾部（#17924）：流末尾无辜的
        # '<' 如果最终不是标签前缀，应该到达 UI。然后
        # 刷新上下文清理器。顺序很重要 —— think 清理器的输出馈入上下文清理器的状态。
        think_scrubber = getattr(self, "_stream_think_scrubber", None)
        if think_scrubber is not None:
            think_tail = think_scrubber.flush()
            if think_tail:
                # 也将尾部通过上下文清理器路由，以便跨越最终边界的
                # memory-context 跨度仍被捕获。
                ctx_scrubber = getattr(self, "_stream_context_scrubber", None)
                if ctx_scrubber is not None:
                    think_tail = ctx_scrubber.feed(think_tail)
                if think_tail:
                    callbacks = [cb for cb in (self.stream_delta_callback, self._stream_callback) if cb is not None]
                    for cb in callbacks:
                        try:
                            cb(think_tail)
                        except Exception:
                            pass
                    self._record_streamed_assistant_text(think_tail)
        # 刷新上下文清理器持有的任何良性部分标签尾部，以便它在清除下一次模型调用的
        # 状态前到达 UI。如果清理器在跨度中间，flush() 丢弃孤儿内容。
        scrubber = getattr(self, "_stream_context_scrubber", None)
        if scrubber is not None:
            tail = scrubber.flush()
            if tail:
                callbacks = [cb for cb in (self.stream_delta_callback, self._stream_callback) if cb is not None]
                for cb in callbacks:
                    try:
                        cb(tail)
                    except Exception:
                        pass
                self._record_streamed_assistant_text(tail)
        self._current_streamed_assistant_text = ""

    def _record_streamed_assistant_text(self, text: str) -> None:
        """累积通过流回调发出的可见助手文本。"""
        # 单写入者守卫（#65991）：被取代的流绝不能污染 turn 累积的文本
        #（它也供给中间可见文本去重比较），即使调用者直接到达这里（
        # tool-suppressed content path)，而不是 through _fire_stream_delta。
        if self._stream_writer_superseded():
            return
        if isinstance(text, str) and text:
            self._current_streamed_assistant_text = (
                getattr(self, "_current_streamed_assistant_text", "") + text
            )

    @staticmethod
    def _normalize_interim_visible_text(text: str) -> str:
        if not isinstance(text, str):
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def _interim_content_was_streamed(self, content: str) -> bool:
        visible_content = self._normalize_interim_visible_text(
            self._strip_think_blocks(content or "")
        )
        if not visible_content:
            return False
        streamed = self._normalize_interim_visible_text(
            self._strip_think_blocks(getattr(self, "_current_streamed_assistant_text", "") or "")
        )
        # 前缀匹配（非精确相等）：最终响应可能是stream文本加尾部增量，或者当验证
        # 催促触发时流可能是部分的。在这两种情况下，stream
        # 内容是最终的子串 —— 这足以标记它
        # previewed (fails safe to a benign duplicate, 绝不 loses text)。
        # 反向方向（stream比最终长）不匹配：那可能抑制网关路径中需要的重发，
        # 其中 already_streamed=True 调用 on_segment_break() 而不是
        # on_commentary()（#65919 审查）。
        return bool(streamed) and visible_content.startswith(streamed)

    def _extract_codex_interim_visible_parts(
        self,
        assistant_msg: Dict[str, Any],
    ) -> List[str]:
        """Extract visible Codex commentary as one string per message item.

        Codex Responses can keep user-facing mid-turn narration as structured
        ``phase=commentary`` message items while final answer text remains in
        assistant ``content``.  Non-streaming gateway surfaces need that
        commentary through the interim assistant callback before 工具调用s run.
        ``phase=analysis`` remains hidden because it is provider scratchpad.
        """
        if not getattr(self, "show_commentary", True):
            # display.show_commentary=false —— commentary 留在
            # reasoning channel (pre-commentary-channel behavior).
            return []
        items = assistant_msg.get("codex_message_items")
        if not isinstance(items, list):
            return []

        messages: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            phase = item.get("phase")
            if not isinstance(phase, str) or phase.strip().lower() != "commentary":
                continue
            content_parts = item.get("content")
            if not isinstance(content_parts, list):
                continue
            item_parts: List[str] = []
            for part in content_parts:
                if not isinstance(part, dict):
                    continue
                if part.get("type") != "output_text":
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    item_parts.append(text)
            visible = "".join(item_parts).strip()
            if visible:
                visible = self._strip_think_blocks(visible).strip()
                visible = redact_sensitive_text(visible)
            if visible:
                messages.append(visible)
        return messages

    def _extract_codex_interim_visible_text(self, assistant_msg: Dict[str, Any]) -> str:
        """提取所有可见的 Codex 评论以进行比较/回退。"""
        return "\n\n".join(
            self._extract_codex_interim_visible_parts(assistant_msg)
        ).strip()

    def _interim_assistant_visible_text(self, assistant_msg: Dict[str, Any]) -> str:
        """Return the exact assistant text eligible for interim delivery.

        Prefer structured Codex commentary over top-level content. A Codex
        response can contain both commentary and a partial/final-answer message
        while tools are still pending; treating top-level content as progress
        in that shape leaks the answer before the 工具调用 runs.

        Content may be a string or a structured parts list (e.g. after vision
        turns or context compaction), so flatten it before stripping reasoning.
        """
        visible = self._extract_codex_interim_visible_text(assistant_msg)
        if visible:
            return visible
        content = assistant_msg.get("content")
        return self._strip_think_blocks(flatten_message_text(content)).strip()

    def _interim_text_was_delivered(self, text: str) -> bool:
        normalized = self._normalize_interim_visible_text(text)
        if not normalized:
            return False
        return normalized in getattr(self, "_delivered_interim_texts", set())

    def _record_delivered_interim_text(self, text: str) -> None:
        normalized = self._normalize_interim_visible_text(text)
        if normalized:
            delivered = getattr(self, "_delivered_interim_texts", None)
            if not isinstance(delivered, set):
                delivered = set()
                self._delivered_interim_texts = delivered
            delivered.add(normalized)

    def _fire_streamed_codex_commentary(self, text: str) -> None:
        """立即传递已完成的实时 Codex 评论消息。"""
        cb = getattr(self, "interim_assistant_callback", None)
        if cb is None or not isinstance(text, str):
            return
        visible = self._strip_think_blocks(text).strip()
        if visible:
            visible = redact_sensitive_text(visible)
        if not visible or visible == "(empty)" or self._interim_text_was_delivered(visible):
            return
        try:
            cb(visible, already_streamed=False)
            self._record_delivered_interim_text(visible)
        except Exception:
            logger.debug("interim_assistant_callback error", exc_info=True)

    def _emit_interim_assistant_message(
        self, assistant_msg: Dict[str, Any]
    ) -> None:
        """Surface a real mid-turn assistant commentary message to the UI layer.

        Does NOT set ``_response_was_previewed`` — that flag means "the final
        response was already shown to the user," but this helper is called for
        ordinary tool-call narration, intermediate acknowledgements, and
        verification candidates alike. Setting it here would cause the CLI to
        suppress a *different* final summary (e.g. from ``_handle_max_iterations``)
        when the only streamed text was unrelated mid-turn commentary. (#65919
        review: response-loss blocker)
        """
        cb = getattr(self, "interim_assistant_callback", None)
        if cb is None or not isinstance(assistant_msg, dict):
            return
        commentary_parts = self._extract_codex_interim_visible_parts(assistant_msg)
        undelivered_parts: List[str] = []
        pending_keys: set[str] = set()
        for part in commentary_parts:
            key = self._normalize_interim_visible_text(part)
            if (
                not key
                or key in pending_keys
                or self._interim_text_was_delivered(part)
            ):
                continue
            pending_keys.add(key)
            undelivered_parts.append(part)
        visible = (
            "\n\n".join(undelivered_parts).strip()
            if commentary_parts
            else self._interim_assistant_visible_text(assistant_msg)
        )
        if (
            not visible
            or visible == "(empty)"
            or self._interim_text_was_delivered(visible)
        ):
            return
        already_streamed = self._interim_content_was_streamed(visible)
        try:
            cb(visible, already_streamed=already_streamed)
            if undelivered_parts:
                for part in undelivered_parts:
                    self._record_delivered_interim_text(part)
            else:
                self._record_delivered_interim_text(visible)
        except Exception:
            logger.debug("interim_assistant_callback error", exc_info=True)

    def _ensure_stream_writer_state(self) -> None:
        """懒创建单写入者守卫字段（#65991）。

        The fields are normally set in ``agent_init``, but agents constructed
        via ``AIAgent.__new__`` (test doubles, legacy/partially-initialized
        instances) skip that path. Claiming/checking the writer must not crash
        those agents, so initialize the fields on first use.
        """
        if getattr(self, "_stream_writer_lock", None) is None:
            self._stream_writer_lock = threading.Lock()
        if not hasattr(self, "_stream_writer_token"):
            self._stream_writer_token = 0
        if getattr(self, "_stream_writer_tls", None) is None:
            self._stream_writer_tls = threading.local()
        if not hasattr(self, "_stream_writer_dropped"):
            self._stream_writer_dropped = 0

    def _claim_stream_writer(self) -> int:
        """Claim exclusive ownership of the streaming delta sink for the calling
        stream attempt and return its monotonic writer token (#65991).

        Every streaming attempt (each provider path, each retry) calls this
        right before it begins consuming its stream. Claiming bumps the shared
        token, so any earlier attempt still alive on another thread is
        immediately superseded: its cached token no longer matches and the sink
        fences its late chunks out. The token is stored per-thread, so a thread
        that never claimed (a non-streaming caller) is never treated as a
        writer and can never be fenced.
        """
        self._ensure_stream_writer_state()
        with self._stream_writer_lock:
            self._stream_writer_token += 1
            token = self._stream_writer_token
        self._stream_writer_tls.token = token
        return token

    def _stream_writer_is_current(self, token: int) -> bool:
        """当 ``token``（来自先前的 _claim_stream_writer）仍是活动写入者时为 True — i.e. no newer stream attempt has claimed the sink since
        (#65991). Lets a stream loop bail out the instant it is superseded."""
        return token == getattr(self, "_stream_writer_token", token)

    def _stream_writer_superseded(self) -> bool:
        """True when the calling thread claimed the delta sink but a newer
        stream attempt has since claimed it — i.e. this thread is a stale
        writer whose chunks must be dropped (#65991).

        A thread that never claimed (``token is None``) is not a writer and is
        never reported as superseded, so non-streaming delta callers are
        unaffected.
        """
        tls = getattr(self, "_stream_writer_tls", None)
        token = getattr(tls, "token", None) if tls is not None else None
        if token is None:
            return False
        return token != getattr(self, "_stream_writer_token", token)

    def _note_dropped_stream_writer(self, where: str) -> None:
        """记录并记录被取代流的增量已被丢弃。"""
        try:
            self._stream_writer_dropped = int(getattr(self, "_stream_writer_dropped", 0)) + 1
        except Exception:
            self._stream_writer_dropped = 1
        # 稀疏日志（首次丢弃，然后按 2 的幂次），使嘈杂的被取代流不会淹没日志，
        # 但真正的提供商问题仍然可见。静默丢弃会隐藏真实故障。
        _n = self._stream_writer_dropped
        if _n == 1 or (_n & (_n - 1)) == 0:
            logger.warning(
                "Dropped delta from a superseded stream writer at %s "
                "(discarded=%d this turn) — a stale stream tried to write into "
                "the turn after a retry superseded it.",
                where, _n,
            )

    def _fire_stream_delta(self, text: str) -> None:
        """触发所有注册的流增量回调（显示 + TTS）。"""
        # 单写入者守卫 (#65991)：被取代的流不能将其 token 交错写入
        # 替换它的重试所在的同一轮次中。
        if self._stream_writer_superseded():
            self._note_dropped_stream_writer("_fire_stream_delta")
            return
        # 如果工具迭代设置了中断标志，在第一个真实文本增量前前置单个段落中断。
        # 这防止了原始问题（跨工具边界的文本连接）而不会堆叠
        # 当多个工具迭代连续运行时的空行。
        if getattr(self, "_stream_needs_break", False) and text and text.strip():
            self._stream_needs_break = False
            text = "\n\n" + text
            prepended_break = True
        else:
            prepended_break = False
        if isinstance(text, str):
            # Suppress reasoning/thinking blocks via the stateful
            # 清理器（#17924）。早期版本在此处每增量运行 _strip_think_blocks，这破坏了下游状态机
            # 当标签跨增量拆分时（例如 MiniMax-M2.7 将 '<think>' 及其内容作为单独的增量发送 ——
            # 正则情况 2 擦除了第一个增量，所以 CLI/gateway 状态机从未看到开放标签并泄漏了
            # reasoning content as regular response text).
            think_scrubber = getattr(self, "_stream_think_scrubber", None)
            if think_scrubber is not None:
                text = think_scrubber.feed(text or "")
            else:
                # Defensive: legacy callers 不用 the scrubber attribute。
                text = self._strip_think_blocks(text or "")
            # 然后通过有状态的上下文清理器馈入，以便 memory-context
            # spans split across chunks 不能 leak to the UI (#5719)。
            scrubber = getattr(self, "_stream_context_scrubber", None)
            if scrubber is not None:
                text = scrubber.feed(text)
            else:
                # Defensive: legacy callers 不用 the scrubber attribute。
                text = sanitize_context(text)
            # 仅在第一个增量上剥离前导换行 —— 流中间的 "\n" 是合法的 markdownn.
            if not prepended_break and not getattr(
                self, "_current_streamed_assistant_text", ""
            ):
                text = text.lstrip("\n")
        if not text:
            return
        callbacks = [cb for cb in (self.stream_delta_callback, self._stream_callback) if cb is not None]
        delivered = False
        for cb in callbacks:
            try:
                cb(text)
                delivered = True
            except Exception:
                pass
        if delivered:
            self._record_streamed_assistant_text(text)

    def _fire_reasoning_delta(self, text: str) -> None:
        """Fire reasoning callback if registered."""
        # 单写入者守卫（#65991）：将取代流的
        # reasoning deltas the same way as content deltas.
        if self._stream_writer_superseded():
            self._note_dropped_stream_writer("_fire_reasoning_delta")
            return
        cb = self.reasoning_callback
        if cb is not None:
            try:
                cb(text)
            except Exception:
                pass

    def _fire_tool_gen_started(self, tool_name: str) -> None:
        """Notify display layer that the model is generating 工具调用 arguments.

        Fires once per tool name when the streaming response begins producing
        tool_call / tool_use tokens.  Gives the TUI a chance to show a spinner
        or status line so the user isn't staring at a frozen screen while a
        large tool payload (e.g. a 45 KB write_file) is being generated.
        """
        cb = self.tool_gen_callback
        if cb is not None:
            try:
                cb(tool_name)
            except Exception:
                pass

    def _has_stream_consumers(self) -> bool:
        """Return True if any streaming consumer is registered."""
        return (
            self.stream_delta_callback is not None
            or getattr(self, "_stream_callback", None) is not None
        )

    def _interruptible_streaming_api_call(
        self, api_kwargs: dict, *, on_first_delta: callable = None
    ):
        """转发器 → agent/chat_completion_helpers/interruptible_streaming_api_call.py"""
        from agent.chat_completion_helpers import interruptible_streaming_api_call
        return interruptible_streaming_api_call(self, api_kwargs, on_first_delta=on_first_delta)

    def _try_activate_fallback(self, reason: "FailoverReason | None" = None) -> bool:
        """转发器 → agent/chat_completion_helpers/try_activate_fallback.py"""
        from agent.chat_completion_helpers import try_activate_fallback
        return try_activate_fallback(self, reason)

    def _has_pending_fallback(self) -> bool:
        """Whether a fallback provider is actually available to switch to.

        Used to gate user-facing "trying fallback..." status so we don't
        announce a fallback that will never be attempted (the user has no
        fallback chain configured).  Mirrors the early-return guard in
        ``try_activate_fallback`` (#35314, #17446).
        """
        chain = getattr(self, "_fallback_chain", None) or []
        index = getattr(self, "_fallback_index", 0)
        return index < len(chain)

    # ── 每 turn 主恢复 ─────────────────────────────────────────────────

    def _restore_primary_runtime(self) -> bool:
        """转发器 → agent/agent_runtime_helpers/restore_primary_runtime.py"""
        from agent.agent_runtime_helpers import restore_primary_runtime
        return restore_primary_runtime(self)

    def _try_recover_primary_transport(
        self, api_error: Exception, *, retry_count: int, max_retries: int,
    ) -> bool:
        """转发器 → agent/agent_runtime_helpers/try_recover_primary_transport.py"""
        from agent.agent_runtime_helpers import try_recover_primary_transport
        return try_recover_primary_transport(self, api_error, retry_count=retry_count, max_retries=max_retries)

    @staticmethod
    def _content_has_image_parts(content: Any) -> bool:
        if not isinstance(content, list):
            return False
        for part in content:
            if isinstance(part, dict) and part.get("type") in {"image_url", "input_image"}:
                return True
        return False

    # 20 MB base64 ≈ 15 MB 解码图像 —— 慷慨但防止来自过大的 data: URL 的 OOM（100 MB+ 负载创建约 275 MB 内存压力，共享同一进程的 gateway 用户可以轻易使其 OOM）。
    _MAX_DATA_URL_BASE64_BYTES = 20 * 1024 * 1024

    @staticmethod
    def _materialize_data_url_for_vision(image_url: str) -> tuple[str, Optional[Path]]:
        header, _, data = str(image_url or "").partition(",")
        if len(data) > AIAgent._MAX_DATA_URL_BASE64_BYTES:
            logger.warning(
                "data-URL payload too large (%d bytes), skipping", len(data)
            )
            return "", None
        mime = "image/jpeg"
        if header.startswith("data:"):
            mime_part = header[len("data:"):].split(";", 1)[0].strip()
            if mime_part.startswith("image/"):
                mime = mime_part
        suffix = {
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
        }.get(mime, ".jpg")
        tmp = tempfile.NamedTemporaryFile(prefix="anthropic_image_", suffix=suffix, delete=False)
        try:
            with tmp:
                tmp.write(base64.b64decode(data))
        except Exception:
            # delete=False 意味着损坏/不支持的 data URL 会在每次物化失败时泄漏零字节临时文件。
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            raise
        path = Path(tmp.name)
        return str(path), path

    def _describe_image_for_anthropic_fallback(self, image_url: str, role: str) -> str:
        cache_key = hashlib.sha256(str(image_url or "").encode("utf-8")).hexdigest()
        cached = self._anthropic_image_fallback_cache.get(cache_key)
        if cached:
            return cached

        role_label = {
            "assistant": "assistant",
            "tool": "工具结果",
        }.get(role, "user")
        analysis_prompt = (
            "Describe everything visible in this image in thorough detail. "
            "Include any text, code, UI, data, objects, people, layout, colors, "
            "and any other notable visual information."
        )

        vision_source = str(image_url or "")
        cleanup_path: Optional[Path] = None
        if vision_source.startswith("data:"):
            vision_source, cleanup_path = self._materialize_data_url_for_vision(vision_source)

        description = ""
        try:
            from tools.vision_tools import vision_analyze_tool

            result_json = asyncio.run(
                vision_analyze_tool(image_url=vision_source, user_prompt=analysis_prompt)
            )
            result = json.loads(result_json) if isinstance(result_json, str) else {}
            description = (result.get("analysis") or "").strip()
        except Exception as e:
            description = f"Image analysis failed: {e}"
        finally:
            if cleanup_path and cleanup_path.exists():
                try:
                    cleanup_path.unlink()
                except OSError:
                    pass

        if not description:
            description = "Image analysis failed."

        note = f"[The {role_label} attached an image. Here's what it contains:\n{description}]"
        if vision_source and not str(image_url or "").startswith("data:"):
            note += (
                f"\n[If you need a closer look, use vision_analyze with image_url: {vision_source}]"
            )

        self._anthropic_image_fallback_cache[cache_key] = note
        return note

    def _model_supports_vision(self) -> bool:
        """Return True if the active provider+model reports native vision.

        Used to decide whether to strip image content parts from API-bound
        messages (for non-vision 模型s) or let the provider adapter handle
        them natively (for vision-capable models).

        Resolution order (see ``agent.image_routing._supports_vision_override``):
          1. ``model.supports_vision`` (top-level, single-model shortcut)
          2. ``providers.<provider>.models.<model>.supports_vision``
          3. models.dev capability lookup
        Custom/local models absent from models.dev would otherwise be
        misclassified as non-vision and have their images stripped.
        """
        try:
            from hermes_cli.config import load_config
            from agent.image_routing import _lookup_supports_vision
            cfg = load_config()
            provider = (getattr(self, "provider", "") or "").strip()
            model = (getattr(self, "model", "") or "").strip()
            return _lookup_supports_vision(provider, model, cfg) is True
        except Exception:
            return False

    def _provider_supports_vision_tool_messages(self) -> bool:
        """如果活动提供商接受列表类型工具内容则返回 True。

        Some providers (e.g. Xiaomi MiMo) support multimodal user messages
        but reject list-type tool message content with 400 errors.  This
        checks the provider profile's ``supports_vision_tool_messages`` field.
        """
        try:
            from providers import get_provider_profile
            provider = (getattr(self, "provider", "") or "").strip()
            profile = get_provider_profile(provider)
            if profile is not None:
                return getattr(profile, "supports_vision_tool_messages", True)
        except Exception:
            pass
        return True  # default: assume compatible

    def _preprocess_anthropic_content(self, content: Any, role: str) -> Any:
        if not self._content_has_image_parts(content):
            return content

        text_parts: List[str] = []
        image_notes: List[str] = []
        for part in content:
            if isinstance(part, str):
                if part.strip():
                    text_parts.append(part.strip())
                continue
            if not isinstance(part, dict):
                continue

            ptype = part.get("type")
            if ptype in {"text", "input_text"}:
                text = str(part.get("text", "") or "").strip()
                if text:
                    text_parts.append(text)
                continue

            if ptype in {"image_url", "input_image"}:
                image_data = part.get("image_url", {})
                image_url = image_data.get("url", "") if isinstance(image_data, dict) else str(image_data or "")
                if image_url:
                    image_notes.append(self._describe_image_for_anthropic_fallback(image_url, role))
                else:
                    image_notes.append("[An image was attached but no image source was available.]")
                continue

            text = str(part.get("text", "") or "").strip()
            if text:
                text_parts.append(text)

        prefix = "\n\n".join(note for note in image_notes if note).strip()
        suffix = "\n".join(text for text in text_parts if text).strip()
        if prefix and suffix:
            return f"{prefix}\n\n{suffix}"
        if prefix:
            return prefix
        if suffix:
            return suffix
        return "[A multimodal message was converted to text for Anthropic compatibility.]"

    def _get_transport(self, api_mode: str = None):
        """返回给定（或当前）api_mode 的缓存传输。

        Lazy-initializes on first call per api_mode. Returns None if no
        transport is registered for the mode.
        """
        mode = api_mode or self.api_mode
        cache = getattr(self, "_transport_cache", None)
        if cache is None:
            cache = {}
            self._transport_cache = cache
        t = cache.get(mode)
        if t is None:
            from agent.transports import get_transport
            t = get_transport(mode)
            cache[mode] = t
        return t

    def _prepare_anthropic_messages_for_api(self, api_messages: list) -> list:
        # 当没有消息携带图像内容时快速退出。
        if not any(
            isinstance(msg, dict) and self._content_has_image_parts(msg.get("content"))
            for msg in api_messages
        ):
            return api_messages

        # Anthropic 适配器（agent/anthropic_adapter.py:_convert_content_part_to_anthropic）
        # 已经将 OpenAI 风格的 image_url/input_image 部分转换为原生 Anthropic
        # ``{"type": "image", "source": ...}`` 块。当
        # 活动模型支持 vision，我们让适配器做它的工作并完全跳过这个遗留文本回退预处理器。
        if self._model_supports_vision():
            return api_messages

        # 非 vision Anthropic 模型（今天罕见，但保留回退以兼容）：用 vision_analyze
        # 文本注释替换每个图像部分。
        transformed = copy.deepcopy(api_messages)
        for msg in transformed:
            if not isinstance(msg, dict):
                continue
            msg["content"] = self._preprocess_anthropic_content(
                msg.get("content"),
                str(msg.get("role", "user") or "user"),
            )
        return transformed

    def _prepare_messages_for_non_vision_model(self, api_messages: list) -> list:
        """Strip native image parts when the active model lacks vision.

        Runs on the chat.completions / codex_responses paths. Vision-capable
        models pass through unchanged (provider and any downstream translator
        handle the image parts natively). Non-vision 模型s get each image
        replaced by a cached vision_analyze text description so the turn
        doesn't fail with "model does not support image input".
        """
        if not any(
            isinstance(msg, dict) and self._content_has_image_parts(msg.get("content"))
            for msg in api_messages
        ):
            return api_messages

        if self._model_supports_vision():
            return api_messages

        transformed = copy.deepcopy(api_messages)
        for msg in transformed:
            if not isinstance(msg, dict):
                continue
            # 重用 Anthropic 文本回退预处理器 —— 行为相同（遍历内容部分，
            # 用缓存描述替换图像，合并回单个文本或结构化
            # 内容）。命名是历史性的。
            msg["content"] = self._preprocess_anthropic_content(
                msg.get("content"),
                str(msg.get("role", "user") or "user"),
            )
        return transformed

    def _tool_result_content_for_active_model(self, tool_name: str, result: Any) -> Any:
        """Return the tool message content that is safe for the active model.

        Multimodal 工具结果s normally unwrap to OpenAI-style content parts so
        vision-capable models can inspect screenshots.  Text-only providers must
        not receive those image parts, because a rejected 工具结果 becomes
        part of the canonical history and can make the next user turn fail before
        the agent has a chance to recover.
        """
        if not _is_multimodal_tool_result(result):
            return result

        content = result.get("content") or []
        if not self._content_has_image_parts(content):
            return content

        if self._model_supports_vision():
            # 理论上支持 vision —— 但如果提供商拒绝列表类型工具内容
            #（例如小米 MiMo 的 400 "text is not set"），或者如果我们已经在会话中
            # 学到了这个教训，短路到
            # 文本摘要，这样我们不会浪费一个往返重新学习它。
            if not self._provider_supports_vision_tool_messages():
                logger.debug(
                    "Tool %s: provider %s does not accept list-type tool "
                    "content — sending text summary",
                    tool_name, getattr(self, "provider", ""),
                )
                return _multimodal_text_summary(result)
            key = (
                (getattr(self, "provider", "") or "").strip().lower(),
                (getattr(self, "model", "") or "").strip(),
            )
            no_list = getattr(self, "_no_list_tool_content_models", None)
            if no_list and key in no_list:
                logger.debug(
                    "Tool %s: model %s/%s known to reject list-type tool "
                    "content this session — sending text summary",
                    tool_name, key[0], key[1],
                )
                return _multimodal_text_summary(result)
            return content

        summary = _multimodal_text_summary(result)
        if tool_name == "computer_use":
            return json.dumps({
                "error": (
                    "computer_use returned screenshot/image content, but the active "
                    "model/provider does not support image input. Switch to a "
                    "vision-capable model for desktop computer use, or use browser "
                    "tools for browser tasks."
                ),
                "text_summary": summary,
            })

        logger.warning(
            "Tool %s returned image content for non-vision 模型 %s/%s; "
            "falling back to text summary",
            tool_name,
            self.provider,
            self.model,
        )
        return summary

    def _try_shrink_image_parts_in_messages(
        self,
        api_messages: list,
        *,
        max_dimension: int = 8000,
    ) -> bool:
        """转发器 → agent/conversation_compression/try_shrink_image_parts_in_messages.py"""
        from agent.conversation_compression import try_shrink_image_parts_in_messages
        return try_shrink_image_parts_in_messages(
            api_messages,
            max_dimension=max_dimension,
        )

    def _try_strip_image_parts_from_tool_messages(
        self,
        api_messages: list,
        *,
        remember_model: bool = True,
    ) -> bool:
        """Downgrade list-type tool messages to text summaries in-place.

        Recovery path for providers that reject list-type tool message content
        (e.g. Xiaomi MiMo's 400 "text is not set"; see issue #27344).  Walks
        ``api_messages`` for any ``role: "tool"`` message whose ``content`` is
        a list containing image parts, replaces the content with the existing
        text part(s) (or a minimal placeholder if none survive), and by default
        records the active (provider, model) in
        ``self._no_list_tool_content_models`` so subsequent
        ``_tool_result_content_for_active_model`` calls in this session
        preemptively downgrade screenshots without a round-trip.

        413 payload-size recovery passes ``remember_model=False`` because that
        error means this request body was too large, not that the provider/model
        rejects list-type tool content in general.

        Returns True when at least one tool message was downgraded — the
        caller (the 400 recovery branch in ``agent.conversation_loop``) uses
        this to decide whether to retry the API call with the modified
        history or surface the original error.
        """
        if not isinstance(api_messages, list):
            return False

        if remember_model:
            # 记录（provider, model），这样我们不会重复学习这个教训。
            key = (
                (getattr(self, "provider", "") or "").strip().lower(),
                (getattr(self, "model", "") or "").strip(),
            )
            if not hasattr(self, "_no_list_tool_content_models"):
                self._no_list_tool_content_models = set()
            if key[1]:  # only record when we actually have a model id
                self._no_list_tool_content_models.add(key)

        changed = False
        for msg in api_messages:
            if not isinstance(msg, dict) or msg.get("role") != "tool":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue

            # 抢救任何文本部分，以便模型仍能看到一些信号。
            text_parts: List[str] = []
            had_image = False
            for part in content:
                if not isinstance(part, dict):
                    if isinstance(part, str) and part.strip():
                        text_parts.append(part.strip())
                    continue
                ptype = part.get("type")
                if ptype == "image_url" or ptype == "input_image":
                    had_image = True
                    continue
                if ptype in {"text", "input_text"}:
                    text = str(part.get("text") or "").strip()
                    if text:
                        text_parts.append(text)

            if not had_image:
                # 列表类型内容但没有图像部分 —— 保持原样（某些提供商拒绝任何列表内容，
                # 但剥离纯文本列表不会减少歧义；让调用者
                # 如果事实证明是这种情况，则显示原始错误）。
                continue

            if text_parts:
                msg["content"] = "\n\n".join(text_parts)
            else:
                msg["content"] = (
                    "[image content removed — provider does not accept "
                    "list-type tool message content]"
                )
            changed = True

        return changed

    def _anthropic_preserve_dots(self) -> bool:
        """当使用保留模型名称中点的 anthropic 兼容端点时为 True。
        Alibaba/DashScope keeps dots (e.g. qwen3.5-plus).
        MiniMax keeps dots (e.g. MiniMax-M2.7).
        Xiaomi MiMo keeps dots (e.g. mimo-v2.5, mimo-v2.5-pro).
        OpenCode Go/Zen keeps dots for non-Claude models (e.g. minimax-m2.5-free).
        ZAI/Zhipu keeps dots (e.g. glm-4.7, glm-5.1).
        AWS Bedrock uses dotted inference-profile IDs
        (e.g. ``global.anthropic.claude-opus-4-7``,
        ``us.anthropic.claude-sonnet-4-5-20250929-v1:0``) and rejects
        the hyphenated form with
        ``HTTP 400 The provided model identifier is invalid``.
        Regression for #11976; mirrors the opencode-go fix for #5211
        (commit f77be22c), which extended this same allowlist."""
        if (getattr(self, "provider", "") or "").lower() in {
            "alibaba", "minimax", "minimax-cn",
            "opencode-go", "opencode-zen",
            "zai", "bedrock",
            "xiaomi", "vertex",
        }:
            return True
        base = (getattr(self, "base_url", "") or "").lower()
        return (
            "dashscope" in base
            or "aliyuncs" in base
            or "minimax" in base
            or "opencode.ai/zen/" in base
            or "bigmodel.cn" in base
            or "xiaomimimo.com" in base
            # Vertex AI OpenAI 兼容端点 —— Gemini 模型 ID 保留点
            #（例如 google/gemini-3.5-flash）；连字符形式是错误的。
            or "aiplatform.googleapis.com" in base
            # AWS Bedrock 运行时端点 —— 纵深防御，当 ``provider`` 未设置但
            # ``base_url`` 仍命名 Bedrock 时。
            or "bedrock-runtime." in base
        )

    def _is_qwen_portal(self) -> bool:
        """当 base URL 指向 Qwen Portal 时返回 True。"""
        return base_url_host_matches(self._base_url_lower, "portal.qwen.ai")

    def _qwen_prepare_chat_messages(self, api_messages: list) -> list:
        prepared = copy.deepcopy(api_messages)
        if not prepared:
            return prepared

        for msg in prepared:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                msg["content"] = [{"type": "text", "text": content}]
            elif isinstance(content, list):
                # 规范化：将裸字符串转换为文本字典，保持字典原样。
                # deepcopy 已经创建了独立副本，不需要 dict()。
                normalized_parts = []
                for part in content:
                    if isinstance(part, str):
                        normalized_parts.append({"type": "text", "text": part})
                    elif isinstance(part, dict):
                        normalized_parts.append(part)
                if normalized_parts:
                    msg["content"] = normalized_parts

        # 在系统消息的最后一部分注入 cache_control。
        for msg in prepared:
            if isinstance(msg, dict) and msg.get("role") == "system":
                content = msg.get("content")
                if isinstance(content, list) and content and isinstance(content[-1], dict):
                    content[-1]["cache_control"] = {"type": "ephemeral"}
                break

        return prepared

    def _qwen_prepare_chat_messages_inplace(self, messages: list) -> None:
        """原地变体 —— 改变已复制的消息列表。"""
        if not messages:
            return

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                msg["content"] = [{"type": "text", "text": content}]
            elif isinstance(content, list):
                normalized_parts = []
                for part in content:
                    if isinstance(part, str):
                        normalized_parts.append({"type": "text", "text": part})
                    elif isinstance(part, dict):
                        normalized_parts.append(part)
                if normalized_parts:
                    msg["content"] = normalized_parts

        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "system":
                content = msg.get("content")
                if isinstance(content, list) and content and isinstance(content[-1], dict):
                    content[-1]["cache_control"] = {"type": "ephemeral"}
                break

    def _build_api_kwargs(self, api_messages: list) -> dict:
        """转发器 → agent/chat_completion_helpers/build_api_kwargs.py"""
        from agent.chat_completion_helpers import build_api_kwargs
        return build_api_kwargs(self, api_messages)

    def _supports_reasoning_extra_body(self) -> bool:
        """Return True when reasoning extra_body is safe to send for this route/model.

        OpenRouter forwards unknown extra_body fields to upstream providers.
        Some providers/routes reject `reasoning` with 400s, so gate it to
        known reasoning-capable model families and direct Nous Portal.
        """
        if base_url_host_matches(self._base_url_lower, "nousresearch.com"):
            return True
        if (
            base_url_host_matches(self._base_url_lower, "models.github.ai")
            or base_url_host_matches(self._base_url_lower, "githubcopilot.com")
        ):
            try:
                from hermes_cli.models import github_model_reasoning_efforts

                return bool(github_model_reasoning_efforts(self.model))
            except Exception:
                return False
        if (self.provider or "").strip().lower() == "lmstudio":
            opts = self._lmstudio_reasoning_options_cached()
            # "off-only" (or absent) means no real reasoning capability.
            return any(opt and opt != "off" for opt in opts)
        # Ollama Cloud（和任何 Ollama 兼容服务器）：原生
        # /api/show capabilities list is authoritative — emit reasoning_effort
        # 仅用于声明 "thinking" 能力的模型。deepseek-v4
        # 每个 (model, base_url) has it; gemma3 / qwen3-coder don't. Cached。
        if base_url_host_matches(self._base_url_lower, "ollama.com"):
            return self._ollama_supports_thinking_cached()
        if "openrouter" not in self._base_url_lower:
            return False
        if "api.mistral.ai" in self._base_url_lower:
            return False

        model = (self.model or "").lower()
        reasoning_model_prefixes = (
            "deepseek/",
            "anthropic/",
            "openai/",
            "x-ai/",
            "google/gemini-2",
            "google/gemma-4",
            "qwen/qwen3",
            "tencent/hy3",
            "xiaomi/",
        )
        return any(model.startswith(prefix) for prefix in reasoning_model_prefixes)

    def _lmstudio_reasoning_options_cached(self) -> list[str]:
        """Probe LM Studio's published reasoning ``allowed_options`` once per
        (model, base_url). The list (e.g. ``["off","on"]`` or
        ``["off","minimal","low"]``) is needed both for the supports-reasoning
        gate and for clamping the emitted ``reasoning_effort`` so toggle-style
        models don't 400 on ``high``. Cache is keyed on (model, base_url) so
        ``/model`` swaps and base-URL changes don't reuse a stale list.
        Non-empty results are cached permanently (model capabilities don't
        change). Empty results (transient probe failure OR genuinely
        non-reasoning model) are cached with a 60-second TTL to avoid an
        HTTP round-trip on every turn while still retrying reasonably soon.
        """
        import time as _time

        cache = getattr(self, "_lm_reasoning_opts_cache", None)
        if cache is None:
            cache = self._lm_reasoning_opts_cache = {}
        key = (self.model, self.base_url)
        cached = cache.get(key)
        if cached is not None:
            opts, ts = cached
            # 非空 → 永久。空 → 60 秒 TTL。
            if opts or (_time.monotonic() - ts) < 60:
                return opts
        try:
            from hermes_cli.models import lmstudio_model_reasoning_options
            opts = lmstudio_model_reasoning_options(
                self.model, self.base_url, getattr(self, "api_key", ""),
            )
        except Exception:
            opts = []
        cache[key] = (opts, _time.monotonic())
        return opts

    def _ollama_supports_thinking_cached(self) -> bool:
        """Probe Ollama's ``/api/show`` capabilities once per (model, base_url).

        Returns True only when the model declares the ``thinking`` capability.
        Caching mirrors the LM Studio probe: a True/False result is permanent
        (capabilities don't change), while a probe failure (None) is cached
        with a 60-second TTL so a transient outage doesn't suppress reasoning
        for the rest of the session but also doesn't round-trip every turn.
        """
        import time as _time

        cache = getattr(self, "_ollama_thinking_cache", None)
        if cache is None:
            cache = self._ollama_thinking_cache = {}
        key = (self.model, self.base_url)
        cached = cache.get(key)
        if cached is not None:
            supported, ts = cached
            # 明确的 True/False → 永久。未知（None）→ 60 秒 TTL。
            if supported is not None or (_time.monotonic() - ts) < 60:
                return bool(supported)
        try:
            from hermes_cli.models import ollama_model_supports_thinking
            supported = ollama_model_supports_thinking(
                self.model, self.base_url, getattr(self, "api_key", "")
            )
        except Exception:
            supported = None
        cache[key] = (supported, _time.monotonic())
        return bool(supported)

    def _resolve_lmstudio_summary_reasoning_effort(self) -> Optional[str]:
        """Resolve a safe top-level ``reasoning_effort`` for LM Studio.

        The iteration-limit summary path calls ``chat.completions.create()``
        directly, bypassing the transport. Share the helper so the two paths
        can't drift on effort resolution and clamping.
        """
        from agent.lmstudio_reasoning import resolve_lmstudio_effort
        return resolve_lmstudio_effort(
            self.reasoning_config,
            self._lmstudio_reasoning_options_cached(),
        )

    def _github_models_reasoning_extra_body(self) -> dict | None:
        """Format reasoning payload for GitHub Models/OpenAI-compatible routes."""
        try:
            from hermes_cli.models import github_model_reasoning_efforts
        except Exception:
            return None

        supported_efforts = github_model_reasoning_efforts(self.model)
        if not supported_efforts:
            return None

        if self.reasoning_config and isinstance(self.reasoning_config, dict):
            if self.reasoning_config.get("enabled") is False:
                return None
            requested_effort = str(
                self.reasoning_config.get("effort", "medium")
            ).strip().lower()
        else:
            requested_effort = "medium"

        if requested_effort == "xhigh" and "xhigh" not in supported_efforts and "high" in supported_efforts:
            requested_effort = "high"
        elif requested_effort not in supported_efforts:
            if requested_effort == "minimal" and "low" in supported_efforts:
                requested_effort = "low"
            elif "medium" in supported_efforts:
                requested_effort = "medium"
            else:
                requested_effort = supported_efforts[0]

        return {"effort": requested_effort}

    def _build_assistant_message(self, assistant_message, finish_reason: str) -> dict:
        """转发器 → agent/chat_completion_helpers/build_assistant_message.py"""
        from agent.chat_completion_helpers import build_assistant_message
        return build_assistant_message(self, assistant_message, finish_reason)

    def _needs_thinking_reasoning_pad(self) -> bool:
        """Return True when the active provider enforces reasoning_content echo-back.

        DeepSeek v4 thinking and Kimi / Moonshot thinking both reject replays
        of assistant tool-call messages that omit ``reasoning_content`` (refs
        #15250, #17400). Xiaomi MiMo thinking 模式 has the same requirement.

        Result cached on the AIAgent instance keyed by (provider, model,
        base_url); invalidated whenever ``switch_model()`` /
        ``_try_activate_fallback()`` mutate any of those. This is hot — the
        agent loop hits ~16 invocations per turn, each of which would
        otherwise re-run ~5 ``base_url_host_matches`` (and therefore
        ``urlparse``) calls under it. Caching drops the per-turn cost from
        ~5us × 16 = ~80us to <1us.
        """
        key = (self.provider, self.model, getattr(self, "_base_url_lower", self.base_url))
        cached = getattr(self, "_thinking_pad_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        result = (
            self._needs_deepseek_tool_reasoning()
            or self._needs_kimi_tool_reasoning()
            or self._needs_mimo_tool_reasoning()
        )
        self._thinking_pad_cache = (key, result)
        return result

    def _needs_kimi_tool_reasoning(self) -> bool:
        """Return True when the current provider is Kimi / Moonshot thinking 模式.

        Kimi ``/coding`` and Moonshot thinking 模式 both require
        ``reasoning_content`` on every assistant tool-call message; omitting
        it causes the next replay to fail with HTTP 400.

        Detection is host-driven, not model-name-driven: aggregators like
        OpenRouter that re-export Kimi/Moonshot models speak their own
        protocol and reject ``reasoning_content`` echoes. We only enable the
        kimi-reasoning replay when the request actually targets a
        kimi/moonshot endpoint or the dedicated kimi-coding provider.
        """
        return (
            self.provider in {"kimi-coding", "kimi-coding-cn"}
            or base_url_host_matches(self.base_url, "api.kimi.com")
            or base_url_host_matches(self.base_url, "moonshot.ai")
            or base_url_host_matches(self.base_url, "moonshot.cn")
        )

    def _needs_deepseek_tool_reasoning(self) -> bool:
        """Return True when the current provider is DeepSeek thinking 模式.

        DeepSeek V4 thinking 模式 requires ``reasoning_content`` on every
        assistant tool-call turn; omitting it causes HTTP 400 when the
        message is replayed in a subsequent API request (#15250).
        """
        provider = (self.provider or "").lower()
        model = (self.model or "").lower()
        return (
            provider == "deepseek"
            or "deepseek" in model
            or base_url_host_matches(self.base_url, "api.deepseek.com")
        )

    def _needs_mimo_tool_reasoning(self) -> bool:
        """Return True when the current provider is Xiaomi MiMo thinking 模式.

        MiMo thinking 模式 requires ``reasoning_content`` on every assistant
        tool-call message when replaying history; omitting it causes HTTP 400.
        Refs: https://platform.xiaomimimo.com/docs/zh-CN/usage-guide/passing-back-reasoning_content
        """
        provider = (self.provider or "").lower()
        model = (self.model or "").lower()
        return (
            provider == "xiaomi"
            or "mimo" in model
            or base_url_host_matches(self.base_url, "api.xiaomimimo.com")
            or base_url_host_matches(self.base_url, "xiaomimimo.com")
        )

    def _copy_reasoning_content_for_api(self, source_msg: dict, api_msg: dict) -> None:
        """转发器 → agent/agent_runtime_helpers/copy_reasoning_content_for_api.py"""
        from agent.agent_runtime_helpers import copy_reasoning_content_for_api
        return copy_reasoning_content_for_api(self, source_msg, api_msg)

    def _reapply_reasoning_echo_for_provider(self, api_messages: list) -> int:
        """转发器 → agent/agent_runtime_helpers/reapply_reasoning_echo_for_provider.py"""
        from agent.agent_runtime_helpers import reapply_reasoning_echo_for_provider
        return reapply_reasoning_echo_for_provider(self, api_messages)

    @staticmethod
    def _sanitize_tool_calls_for_strict_api(api_msg: dict, model: "str | None" = None) -> dict:
        """Strip Codex Responses API fields from tool_calls for strict providers.

        Providers like Mistral, Fireworks, and other strict OpenAI-compatible APIs
        validate the Chat Completions schema and reject unknown fields (call_id,
        response_item_id) with 400 or 422 errors. These fields are preserved in
        the internal message history — this method only modifies the outgoing
        API copy.

        ``extra_content`` (Gemini thought_signature) is also stripped — strict
        providers reject it with "Extra inputs are not permitted" — UNLESS the
        outgoing ``model`` is itself Gemini-family, in which case it must be
        replayed (Gemini 3 thinking 模式ls 400 without it). Defaults to
        stripping when no model is supplied.

        Creates new tool_call dicts rather than mutating in-place, so the
        original messages list retains call_id/response_item_id for Codex
        Responses API compatibility (e.g. if the session falls back to a
        Codex provider later).

        Fields stripped: call_id, response_item_id, extra_content (model-gated)
        """
        tool_calls = api_msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            return api_msg
        from agent.transports.chat_completions import _model_consumes_thought_signature
        _STRIP_KEYS = {"call_id", "response_item_id"}
        if not _model_consumes_thought_signature(model):
            _STRIP_KEYS = _STRIP_KEYS | {"extra_content"}
        api_msg["tool_calls"] = [
            {k: v for k, v in tc.items() if k not in _STRIP_KEYS}
            if isinstance(tc, dict) else tc
            for tc in tool_calls
        ]
        return api_msg

    @staticmethod
    def _sanitize_tool_call_arguments(
        messages: list,
        *,
        logger=None,
        session_id: str = None,
    ) -> int:
        """转发器 → agent/agent_runtime_helpers/sanitize_tool_call_arguments.py"""
        from agent.agent_runtime_helpers import sanitize_tool_call_arguments
        return sanitize_tool_call_arguments(messages, logger=logger, session_id=session_id)

    def _should_sanitize_tool_calls(self) -> bool:
        """判断 tool_calls 是否需要为严格 API 进行清理。

        Codex Responses API uses fields like call_id and response_item_id
        that are not part of the standard Chat Completions schema. These
        fields must be stripped when calling any other API to avoid
        validation errors (400 Bad Request).

        Returns:
            bool: True if sanitization is needed (non-Codex API), False otherwise.
        """
        return self.api_mode != "codex_responses"

    def _compress_context(
        self,
        messages: list,
        system_message: str,
        *,
        approx_tokens: int = None,
        task_id: str = "default",
        focus_topic: str = None,
        force: bool = False,
        defer_context_engine_notification: bool = False,
        commit_fence=None,
    ) -> tuple:
        """转发器 → agent/conversation_compression/compress_context.py

        ``force=True`` 由手动 ``/compress`` 斜杠命令传递，允许用户在自动压缩
        中断后绕过摘要失败冷却。自动压缩调用方使用默认的 ``force=False``。
        """
        from agent.conversation_compression import compress_context
        from agent.portal_tags import (
            get_conversation_context,
            reset_conversation_context,
            set_conversation_context,
        )
        # 轮次外压缩入口 —— ``/compact``（cli.py）、gateway ``/compress`` 命令及其
        # 卫生清扫（两者都构建一次性 agent），以及部分头部压缩 —— 调用此
        # 直接在 ``run_conversation`` 的环境作用域外转发器。没有任何环境，摘要器的辅助调用不携带对话标签和 Portal 粘性键，所以它独立于所属对话路由。在此发布根作为回退；轮次内调用者已将其设置为相同值，所以对它们这是空操作。
        #
        # 注意这不保持压缩 turn 自己的提示缓存温暖：压缩用摘要替换历史并重建
        # 系统提示词, so that request is a cold write on any endpoint. What
        # 它获得的是压缩后读取它写入的缓存的 turn。
        token = None
        if get_conversation_context() is None:
            root = self._conversation_root_id()
            if root:
                token = set_conversation_context(root)
        try:
            return compress_context(
                self, messages, system_message,
                approx_tokens=approx_tokens, task_id=task_id, focus_topic=focus_topic,
                force=force,
                defer_context_engine_notification=defer_context_engine_notification,
                commit_fence=commit_fence,
            )
        finally:
            # 恢复调用者拥有的任何内容，这样压缩永远不会将其标签泄漏到周围作用域。
            if token is not None:
                reset_conversation_context(token)

    def _set_tool_guardrail_halt(self, decision: ToolGuardrailDecision) -> None:
        """记录应停止此 turn 的第一个护栏决策。"""
        if decision.should_halt and self._tool_guardrail_halt_decision is None:
            self._tool_guardrail_halt_decision = decision

    def _toolguard_controlled_halt_response(self, decision: ToolGuardrailDecision) -> str:
        tool = decision.tool_name or "a tool"
        return (
            f"I stopped retrying {tool} because it hit the tool-call guardrail "
            f"({decision.code}) after {decision.count} repeated non-progressing "
            "attempts. The last 工具结果 explains the blocker; the next step is "
            "to change strategy instead of repeating the same call."
        )

    def _append_guardrail_observation(
        self,
        tool_name: str,
        function_args: dict,
        function_result: str,
        *,
        failed: bool,
    ) -> str:
        decision = self._tool_guardrails.after_call(
            tool_name,
            function_args,
            function_result,
            failed=failed,
        )
        if decision.action in {"warn", "halt"}:
            function_result = append_toolguard_guidance(function_result, decision)
        if decision.should_halt:
            self._set_tool_guardrail_halt(decision)
        return function_result

    def _guardrail_block_result(self, decision: ToolGuardrailDecision) -> str:
        self._set_tool_guardrail_halt(decision)
        return toolguard_synthetic_result(decision)

    def _execute_tool_calls(self, assistant_message, messages: list, effective_task_id: str, api_call_count: int = 0) -> None:
        """Execute 工具调用s from the assistant message and append results to messages.

        The segment planner splits the batch into maximal contiguous runs of
        parallel-safe calls (read-only tools, non-overlapping file targets,
        opted-in MCP tools) separated by sequential barriers (interactive,
        unsafe, or unrecognized tools). Homogeneous batches keep their
        original single-path dispatch; mixed batches execute segment by
        segment in emission order so safe subsets still run concurrently
        while side-effect ordering is preserved.
        """
        tool_calls = assistant_message.tool_calls

        # 允许在工具执行期间使用 _vprint，即使有流消费者
        self._executing_tools = True
        try:
            if len(tool_calls) <= 1:
                return self._execute_tool_calls_sequential(
                    assistant_message, messages, effective_task_id, api_call_count
                )

            from agent.tool_dispatch_helpers import _plan_tool_batch_segments
            _active_env = get_active_env(effective_task_id)
            _exec_cwd = Path(_active_env.cwd) if _active_env is not None and _active_env.cwd else None
            segments = _plan_tool_batch_segments(tool_calls, execution_cwd=_exec_cwd)

            if len(segments) == 1:
                kind = segments[0][0]
                if kind == "parallel":
                    return self._execute_tool_calls_concurrent(
                        assistant_message, messages, effective_task_id, api_call_count
                    )
                return self._execute_tool_calls_sequential(
                    assistant_message, messages, effective_task_id, api_call_count
                )

            from agent.tool_executor import execute_tool_calls_segmented
            return execute_tool_calls_segmented(
                self, assistant_message, messages, effective_task_id, api_call_count,
                segments=segments,
            )
        finally:
            self._executing_tools = False

    def _dispatch_delegate_task(self, function_args: dict) -> str:
        """delegate_task 分发的单一调用站点。

        New DELEGATE_TASK_SCHEMA fields only need to be added here to reach all
        invocation paths (concurrent, sequential, inline).
        """
        from tools.delegate_tool import (
            _strip_model_hidden_task_fields,
            delegate_task as _delegate_task,
        )
        # 从顶层 MODEL 的委托总是在后台运行 —— 模型没有选择权。delegate_task
        # 立即返回一个句柄（每个任务一个），每个子 Agent 的结果在完成后作为新消息
        # 重新进入对话。这适用于单个任务和扇出批次（每个任务成为自己独立的后台
        # 子 Agent）。唯一的例外：
        #   - 来自 ORCHESTRATOR SUBAGENT（depth > 0）的委托保持同步：编排器需要在
        #     自己的 turn 内获得其工作线程的结果以组合摘要，而子 Agent 不拥有异步结果
        #     将路由回的 gateway 会话。
        # schema-level `background` param 是 intentionally ignored here。
        _is_subagent = getattr(self, "_delegate_depth", 0) > 0
        return _delegate_task(
            goal=function_args.get("goal"),
            context=function_args.get("context"),
            tasks=_strip_model_hidden_task_fields(function_args.get("tasks")),
            max_iterations=function_args.get("max_iterations"),
            role=function_args.get("role"),
            background=(not _is_subagent),
            parent_agent=self,
        )

    def _invoke_tool(self, function_name: str, function_args: dict, effective_task_id: str,
                     tool_call_id: Optional[str] = None, messages: list = None,
                     pre_tool_block_checked: bool = False,
                     skip_tool_request_middleware: bool = False,
                     tool_request_middleware_trace: Optional[list[dict[str, Any]]] = None,
                     skip_tool_execution_middleware: bool = False) -> str:
        """转发器 → agent/agent_runtime_helpers/invoke_tool.py"""
        from agent.agent_runtime_helpers import invoke_tool
        return invoke_tool(
            self,
            function_name,
            function_args,
            effective_task_id,
            tool_call_id,
            messages,
            pre_tool_block_checked,
            skip_tool_request_middleware,
            tool_request_middleware_trace,
            skip_tool_execution_middleware,
        )

    @staticmethod
    def _wrap_verbose(label: str, text: str, indent: str = "     ") -> str:
        """自动换行详细工具输出以适应终端宽度。

        Splits *text* on existing newlines and wraps each line individually,
        preserving intentional line breaks (e.g. pretty-printed JSON).
        Returns a ready-to-print string with *label* on the first line and
        continuation lines indented.
        """
        import shutil as _shutil
        import textwrap as _tw
        cols = _shutil.get_terminal_size((120, 24)).columns
        wrap_width = max(40, cols - len(indent))
        out_lines: list[str] = []
        for raw_line in text.split("\n"):
            if len(raw_line) <= wrap_width:
                out_lines.append(raw_line)
            else:
                wrapped = _tw.wrap(raw_line, width=wrap_width,
                                   break_long_words=True,
                                   break_on_hyphens=False)
                out_lines.extend(wrapped or [raw_line])
        body = ("\n" + indent).join(out_lines)
        return f"{indent}{label}{body}"

    def _execute_tool_calls_concurrent(self, assistant_message, messages: list, effective_task_id: str, api_call_count: int = 0) -> None:
        """转发器 → agent/tool_executor/execute_tool_calls_concurrent.py"""
        from agent.tool_executor import execute_tool_calls_concurrent
        return execute_tool_calls_concurrent(self, assistant_message, messages, effective_task_id, api_call_count)

    def _execute_tool_calls_sequential(self, assistant_message, messages: list, effective_task_id: str, api_call_count: int = 0) -> None:
        """转发器 → agent/tool_executor/execute_tool_calls_sequential.py"""
        from agent.tool_executor import execute_tool_calls_sequential
        return execute_tool_calls_sequential(self, assistant_message, messages, effective_task_id, api_call_count)

    def _handle_max_iterations(self, messages: list, api_call_count: int) -> str:
        """转发器 → agent/chat_completion_helpers/handle_max_iterations.py"""
        from agent.chat_completion_helpers import handle_max_iterations
        return handle_max_iterations(self, messages, api_call_count)

    def _conversation_root_id(self) -> Optional[str]:
        """解析稳定的对话 ID 用于 Portal 使用归因。

        返回会话谱系的 ROOT id 而不是当前片段 id，这样一个用户面向的对话
        在上下文压缩轮换中保持单个 ``conversation=`` 标签（`/new` 开始真正
        的新谱系）。委托子 Agent 通过其 ``_parent_session_id`` 解析，所以整个
        委托树标记为父对话。

        尽力而为：当会话数据库不可用或谱系回溯失败时，回退到原始会话 id。
        """
        sid = getattr(self, "session_id", None)
        if not sid:
            return None
        # 子 Agent 首次轮次可能还没有 DB 行；从父 id 回退仍能到达正确的根。
        start = getattr(self, "_parent_session_id", None) or sid
        db = getattr(self, "_session_db", None)
        if db is not None:
            try:
                root = db.get_conversation_root(start)
                if root:
                    return root
            except Exception:
                logger.debug("Conversation root lineage walk failed", exc_info=True)
        return start

    def run_conversation(
        self,
        user_message: Any,
        system_message: str = None,
        conversation_history: List[Dict[str, Any]] = None,
        task_id: str = None,
        stream_callback: Optional[callable] = None,
        persist_user_message: Optional[Any] = None,
        persist_user_timestamp: Optional[float] = None,
        persist_user_display_kind: Optional[str] = None,
        persist_user_display_metadata: Optional[Dict[str, Any]] = None,
        moa_config: Optional[dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """转发器 → agent/conversation_loop/run_conversation.py"""
        from agent.aux_accounting import (
            reset_accounting_context,
            set_accounting_context,
        )
        from agent import relay_runtime
        from agent.conversation_loop import run_conversation
        from agent.portal_tags import (
            reset_conversation_context,
            set_conversation_context,
        )
        from hermes_cli.observability.relay_shared_metrics import (
            finish_task_run,
            start_task_run,
        )
        from agent.subagent_lifecycle import bind_subagent_parent
        effective_task_id = task_id or str(uuid.uuid4())
        session_id = str(getattr(self, "session_id", None) or "")
        task_context = {
            "session_id": session_id,
            "task_id": effective_task_id,
            "platform": getattr(self, "platform", None) or "",
        }
        relay_turn_id = (
            f"{session_id or 'session'}:{effective_task_id}:{uuid.uuid4().hex[:8]}"
        )
        self._relay_pending_turn_id = relay_turn_id
        relay_parent_session_id = (
            str(getattr(self, "_parent_session_id", None) or "")
            if task_context["platform"] == "subagent"
            else ""
        )
        relay_lease = None
        relay_turn = None
        token = None
        acct_token = None
        task_started = False
        task_finished = False
        relay_outcome = "failed"
        try:
            relay_lease = relay_runtime.SESSION_COORDINATOR.acquire_conversation(
                profile_key=relay_runtime.current_profile_key(),
                session_id=task_context["session_id"],
                platform=task_context["platform"],
                parent_session_id=relay_parent_session_id,
                model=str(getattr(self, "model", None) or ""),
            )
            relay_turn = relay_runtime.SESSION_COORDINATOR.begin_turn(
                relay_lease,
                turn_id=relay_turn_id,
                task_id=effective_task_id,
            )
            start_task_run(
                **task_context,
                parent_session_id=getattr(self, "_parent_session_id", None) or "",
            )
            task_started = True
            # 发布会话 ID 用于 Nous Portal 环境标记。本轮内所有 LLM 调用 ——
            # 主循环、压缩、vision、web_extract、session_search、MoA 槽位、
            # 后台审查分支（将 Context 复制到其线程中）—— 零侵入继承
            # ``conversation=<root>`` 标记。
            token = set_conversation_context(self._conversation_root_id())
            # 同样方式发布会话计费句柄，使辅助调用能将 token 用量
            # 记录到 session_model_usage（任务维度）—— 修复辅助调用开销
            # 在分析中不可见的问题 (#23270)。
            acct_token = set_accounting_context(
                getattr(self, "_session_db", None),
                getattr(self, "session_id", None),
            )
            from agent.auxiliary_client import scoped_runtime_main

            # 外层 token 恢复调用方的 Context，即使 turn 设置会在故障转移
            # 恢复后将其替换为实时运行时值。将作用域保持局部而非将
            # ContextVar token 存储在 agent 上，因为 agent 可能被其他线程观察。
            with bind_subagent_parent(self), scoped_runtime_main({}):
                result = run_conversation(
                    self,
                    user_message,
                    system_message,
                    conversation_history,
                    effective_task_id,
                    stream_callback,
                    persist_user_message,
                    persist_user_timestamp=persist_user_timestamp,
                    persist_user_display_kind=persist_user_display_kind,
                    persist_user_display_metadata=persist_user_display_metadata,
                    moa_config=moa_config,
                )
            terminal = result if isinstance(result, dict) else {}
            if terminal.get("interrupted") is True:
                relay_outcome = "cancelled"
            elif terminal.get("failed") is True:
                relay_outcome = "failed"
            else:
                relay_outcome = "success"
            relay_runtime.SESSION_COORDINATOR.finish_logical_calls(
                relay_turn,
                outcome=relay_outcome,
            )
            task_finished = True
            finish_task_run(**task_context, result=result)
            return result
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, InterruptedError)) or (
                type(exc).__name__ == "CancelledError"
            ):
                relay_outcome = "cancelled"
            elif isinstance(exc, TimeoutError):
                relay_outcome = "timed_out"
            if relay_turn is not None:
                relay_runtime.SESSION_COORDINATOR.finish_logical_calls(
                    relay_turn,
                    outcome=relay_outcome,
                )
            if task_started and not task_finished:
                task_finished = True
                finish_task_run(**task_context, error=exc)
            raise
        finally:
            try:
                if relay_turn is not None:
                    relay_runtime.SESSION_COORDINATOR.end_turn(
                        relay_turn,
                        outcome=relay_outcome,
                    )
            finally:
                try:
                    if relay_lease is not None:
                        relay_runtime.SESSION_COORDINATOR.release_conversation(
                            relay_lease
                        )
                finally:
                    if getattr(self, "_relay_pending_turn_id", None) == relay_turn_id:
                        self._relay_pending_turn_id = None
                    if acct_token is not None:
                        reset_accounting_context(acct_token)
                    if token is not None:
                        reset_conversation_context(token)

    def chat(self, message: str, stream_callback: Optional[callable] = None) -> str:
        """
        Simple chat interface that returns just the final response.

        Args:
            message (str): User message
            stream_callback: Optional callback invoked with each text delta during streaming.

        Returns:
            str: Final assistant response
        """
        result = self.run_conversation(message, stream_callback=stream_callback)
        return result["final_response"]

    def _run_codex_app_server_turn(
        self,
        *,
        user_message: str,
        original_user_message: Any,
        messages: List[Dict[str, Any]],
        effective_task_id: str,
        should_review_memory: bool = False,
    ) -> Dict[str, Any]:
        """转发器 → agent/codex_runtime/run_codex_app_server_turn.py"""
        from agent.codex_runtime import run_codex_app_server_turn
        return run_codex_app_server_turn(self, user_message=user_message, original_user_message=original_user_message, messages=messages, effective_task_id=effective_task_id, should_review_memory=should_review_memory)

def main(
    query: str = None,
    model: str = "",
    api_key: str = None,
    base_url: str = "",
    max_turns: int = 10,
    enabled_toolsets: str = None,
    disabled_toolsets: str = None,
    list_tools: bool = False,
    save_trajectories: bool = False,
    save_sample: bool = False,
    verbose: bool = False,
    log_prefix_chars: int = 20
):
    """
    Agent 命令行入口函数。

    参数:
        query: 自然语言查询，默认为 Python 3.13 示例问题。
        model: 模型名称（OpenRouter 格式: provider/model）。
        api_key: API 认证密钥，未提供时使用 OPENROUTER_API_KEY 环境变量。
        base_url: 模型 API 基础 URL，默认 https://openrouter.ai/api/v1
        max_turns: API 调用最大迭代次数，默认 10。
        enabled_toolsets: 启用的工具集，逗号分隔（如 "research,web,vision"）。
        disabled_toolsets: 禁用的工具集，逗号分隔（如 "terminal"）。
        list_tools: 仅列出可用工具并退出。
        save_trajectories: 保存对话轨迹到 JSONL 文件。
        save_sample: 保存单条轨迹样本到 UUID 命名的 JSONL 文件。
        verbose: 启用详细日志用于调试。
        log_prefix_chars: 日志预览显示的字符数，默认 20。
    """
    print("🤖 AI Agent with Tool Calling")
    print("=" * 50)
    
    if list_tools:
        from model_tools import get_all_tool_names, get_available_toolsets
        from toolsets import get_all_toolsets, get_toolset_info
        
        print("📋 Available Tools & Toolsets:")
        print("-" * 50)
        
        print("\n🎯 Predefined Toolsets (New System):")
        print("-" * 40)
        all_toolsets = get_all_toolsets()

        # 按类别分组
        basic_toolsets = []
        composite_toolsets = []
        scenario_toolsets = []
        
        for name, toolset in all_toolsets.items():
            info = get_toolset_info(name)
            if info:
                entry = (name, info)
                if name in {"web", "terminal", "vision", "creative", "reasoning"}:
                    basic_toolsets.append(entry)
                elif name in {"research", "development", "analysis", "content_creation", "full_stack"}:
                    composite_toolsets.append(entry)
                else:
                    scenario_toolsets.append(entry)
        
        # 打印基础工具集
        print("\n📌 Basic Toolsets:")
        for name, info in basic_toolsets:
            tools_str = ', '.join(info['resolved_tools']) if info['resolved_tools'] else 'none'
            print(f"  • {name:15} - {info['description']}")
            print(f"    Tools: {tools_str}")
        
        # 打印复合工具集
        print("\n📂 Composite Toolsets (built from other toolsets):")
        for name, info in composite_toolsets:
            includes_str = ', '.join(info['includes']) if info['includes'] else 'none'
            print(f"  • {name:15} - {info['description']}")
            print(f"    Includes: {includes_str}")
            print(f"    Total tools: {info['tool_count']}")
        
        # 打印场景专用工具集
        print("\n🎭 Scenario-Specific Toolsets:")
        for name, info in scenario_toolsets:
            print(f"  • {name:20} - {info['description']}")
            print(f"    Total tools: {info['tool_count']}")
        
        
        # 显示旧版工具集兼容性
        print("\n📦 Legacy Toolsets (for backward compatibility):")
        legacy_toolsets = get_available_toolsets()
        for name, info in legacy_toolsets.items():
            status = "✅" if info["available"] else "❌"
            print(f"  {status} {name}: {info['description']}")
            if not info["available"]:
                print(f"    Requirements: {', '.join(info['requirements'])}")
        
        # 显示各个工具
        all_tools = get_all_tool_names()
        print(f"\n🔧 Individual Tools ({len(all_tools)} available):")
        for tool_name in sorted(all_tools):
            toolset = get_toolset_for_tool(tool_name)
            print(f"  📌 {tool_name} (from {toolset})")
        
        print("\n💡 Usage Examples:")
        print("  # Use predefined toolsets")
        print("  python run_agent.py --enabled_toolsets=research --query='search for Python news'")
        print("  python run_agent.py --enabled_toolsets=development --query='debug this code'")
        print("  python run_agent.py --enabled_toolsets=safe --query='analyze without terminal'")
        print("  ")
        print("  # Combine multiple toolsets")
        print("  python run_agent.py --enabled_toolsets=web,vision --query='analyze website'")
        print("  ")
        print("  # Disable toolsets")
        print("  python run_agent.py --disabled_toolsets=terminal --query='no command execution'")
        print("  ")
        print("  # Run with trajectory saving enabled")
        print("  python run_agent.py --save_trajectories --query='your question here'")
        return
    
    enabled_toolsets_list = None
    disabled_toolsets_list = None
    
    if enabled_toolsets:
        enabled_toolsets_list = [t.strip() for t in enabled_toolsets.split(",")]
        print(f"🎯 Enabled toolsets: {enabled_toolsets_list}")
    
    if disabled_toolsets:
        disabled_toolsets_list = [t.strip() for t in disabled_toolsets.split(",")]
        print(f"🚫 Disabled toolsets: {disabled_toolsets_list}")
    
    if save_trajectories:
        print("💾 Trajectory saving: ENABLED")
        print("   - Successful conversations → trajectory_samples.jsonl")
        print("   - Failed conversations → failed_trajectories.jsonl")
    
    # 使用提供参数初始化 Agent
    try:
        agent = AIAgent(
            base_url=base_url,
            model=model,
            api_key=api_key,
            max_iterations=max_turns,
            enabled_toolsets=enabled_toolsets_list,
            disabled_toolsets=disabled_toolsets_list,
            save_trajectories=save_trajectories,
            verbose_logging=verbose,
            log_prefix_chars=log_prefix_chars
        )
    except RuntimeError as e:
        print(f"❌ Failed to initialize agent: {e}")
        return
    
    if query is None:
        user_query = (
            "Tell me about the latest developments in Python 3.13 and what new features "
            "developers should know about. Please search for current information and try it out."
        )
    else:
        user_query = query
    
    print(f"\n📝 User Query: {user_query}")
    print("\n" + "=" * 50)
    
    result = agent.run_conversation(user_query)
    
    print("\n" + "=" * 50)
    print("📋 CONVERSATION SUMMARY")
    print("=" * 50)
    print(f"✅ Completed: {result['completed']}")
    print(f"📞 API Calls: {result['api_calls']}")
    print(f"💬 Messages: {len(result['messages'])}")
    
    if result['final_response']:
        print("\n🎯 FINAL RESPONSE:")
        print("-" * 30)
        print(result['final_response'])
    
    if save_sample:
        sample_id = str(uuid.uuid4())[:8]
        sample_filename = f"sample_{sample_id}.json"
        
        # 将消息转换为轨迹格式
        trajectory = agent._convert_to_trajectory_format(
            result['messages'], 
            user_query, 
            result['completed']
        )
        
        entry = {
            "conversations": trajectory,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "completed": result['completed'],
            "query": user_query
        }
        
        try:
            with open(sample_filename, "w", encoding="utf-8") as f:
                # 格式化 JSON 输出
                f.write(json.dumps(entry, ensure_ascii=False, indent=2))
            print(f"\n💾 Sample trajectory saved to: {sample_filename}")
        except Exception as e:
            print(f"\n⚠️ Failed to save sample: {e}")
    
    print("\n👋 Agent execution completed!")


if __name__ == "__main__":
    import fire
    fire.Fire(main)
