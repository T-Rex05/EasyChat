"""Hermes 工具策略：安全项目工具注册与 toolset 解析。

安全边界（架构 §9）：
- schema 面（get_tool_definitions 的 enabled/disabled）+ conversation_loop 的
  valid_tool_names 闸门共同决定可调用性；绕过 run_conversation 直接
  registry.dispatch 没有任何 toolset 隔离，禁止。
- KB/KG/SQL/论文/CodeMode 工具已从 get_project_tools 移除（惰性导入）。
- 禁用工具在实际 dispatcher 也不可调用：由 valid_tool_names 保证。
"""
from __future__ import annotations

import inspect
import json
import logging
import types
from collections.abc import Mapping
from typing import Any, Iterable, Union, get_args, get_origin

logger = logging.getLogger(__name__)

# Hermes 内建 toolset（terminal/file/web 等）+ 项目安全 toolset
BUILTIN_TOOLSETS = frozenset({"terminal", "file", "web"})
PROJECT_TOOLSETS = frozenset({"schedule", "notification"})
KNOWN_TOOLSETS = BUILTIN_TOOLSETS | PROJECT_TOOLSETS

# 已废弃 toolset（沿用旧 checker 过滤清单并追加 R14 移除项）
DEPRECATED_TOOLSETS = frozenset(
    {"vision", "session_search", "memory", "utility", "data", "email", "paper_repro"}
)

_registered_tools: set[str] = set()


def resolve_enabled_toolsets(role_toolsets: Iterable[str]) -> tuple[list[str], list[str]]:
    """角色 toolsets → (enabled_toolsets, disabled_toolsets)。

    无效/废弃 toolset 不授予（fail-closed）；terminal/file/web 等内建
    toolset 直接透传给 AIAgent。
    """
    enabled: list[str] = []
    for t in role_toolsets:
        if t in DEPRECATED_TOOLSETS:
            continue
        if t in KNOWN_TOOLSETS and t not in enabled:
            enabled.append(t)
    # __always_available__（时间/待办等基础工具）由 Hermes 自动包含
    return enabled, []


def register_safe_project_tools(
    thread_context_provider: Any, *, extra_tools: Iterable[Any] = ()
) -> int:
    """注册项目工具（基础工具 + 可选业务工具）到 Hermes registry。

    幂等；已在 registry 的同名同 toolset 工具跳过。handler 用 LangChain 官方
    invoke()/ainvoke() 入口，thread_id 与 ToolContext 经 RunnableConfig 注入。
    """
    ensure = _ensure_hermes_loaded
    ensure()
    from tools.registry import registry  # noqa: PLC0415  (Hermes 顶层模块)
    from backend.tools.tools_decorator import get_project_tools

    registered = 0
    tools = [*get_project_tools(), *extra_tools]
    for tool in tools:
        name = getattr(tool, "name", getattr(tool, "__name__", "unknown"))
        if name in _registered_tools:
            continue
        toolset = getattr(tool, "_toolset", "agentforge_project")
        schema = _tool_schema(tool)
        registry.register(
            name,
            toolset=toolset,
            schema=schema,
            handler=_make_handler(tool, thread_context_provider),
            description=schema.get("description", ""),
            is_async=_is_async_tool(tool),
            override=True,
        )
        _registered_tools.add(name)
        registered += 1
    return registered


def _tool_schema(tool: Any) -> dict[str, Any]:
    """从 LangChain 工具提取 Hermes registry 需要的 schema。"""
    try:
        args_schema = tool.args_schema
        properties = {}
        required = []
        for name, field in getattr(args_schema, "model_fields", {}).items():
            properties[name] = {
                "type": _json_type(field.annotation),
                "description": field.description or "",
            }
            if field.is_required():
                required.append(name)
        return {
            "description": (tool.description or "").strip(),
            "parameters": {"type": "object", "properties": properties, "required": required},
        }
    except Exception:
        return {"description": getattr(tool, "description", ""), "parameters": {"type": "object", "properties": {}}}


def _json_type(annotation: Any) -> str:
    """Pydantic 注解 → JSON Schema 基础类型；未知类型保守按 string。"""
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [item for item in get_args(annotation) if item is not type(None)]
        return _json_type(args[0]) if len(args) == 1 else "string"
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if origin in (list, tuple, set, frozenset):
        return "array"
    if origin is dict or annotation is dict or origin is Mapping:
        return "object"
    return "string"


def _is_async_tool(tool: Any) -> bool:
    for candidate in (getattr(tool, "coroutine", None), getattr(tool, "func", None)):
        if candidate is not None and inspect.iscoroutinefunction(candidate):
            return True
    return False


def _make_handler(tool: Any, thread_context_provider: Any):
    """同步工具走 invoke；异步工具走 ainvoke，避免把 coroutine 当字符串。"""

    def _config(provided: Any = None) -> dict[str, Any] | None:
        from backend.shared.tool_context import config_with, current, from_config

        thread_id = None
        try:
            thread_id = thread_context_provider()
        except Exception:  # noqa: BLE001
            pass
        context = from_config(provided) or current()
        if context is not None:
            # Todo 等旧工具用 thread_id 做隔离；没有 Hermes 线程时退回 session，
            # 绝不落到所有会话共享的 "default"。
            tid = thread_id or context.session_id or context.run_id
            return config_with(context, thread_id=str(tid) if tid else None)
        return {"configurable": {"thread_id": thread_id}} if thread_id else None

    if _is_async_tool(tool):
        def _async_handler(args, **kwargs):
            # 必须先同步解析 config，再返回协程：Hermes 可能只把协程移到新线程，
            # 届时 contextvar 已不可见，不能在协程内部才读 current()。
            config = _config(kwargs.get("config"))

            async def _invoke():
                result = await tool.ainvoke(args or {}, config=config)
                if not isinstance(result, str):
                    result = json.dumps(result, ensure_ascii=False, default=str)
                return result

            return _invoke()

        return _async_handler

    def _handler(args, **kwargs):
        result = tool.invoke(args or {}, config=_config(kwargs.get("config")))
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False, default=str)
        return result

    return _handler


def _ensure_hermes_loaded() -> None:
    import os
    from pathlib import Path

    from backend.config.paths import get_hermes_dir
    from backend.runtime.hermes.paths import ensure_hermes_environment

    home = os.environ.get("HERMES_HOME") or str(get_hermes_dir())
    ensure_hermes_environment(Path(home))
