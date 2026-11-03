"""Hermes 工具策略：安全项目工具注册与 toolset 解析。

安全边界（架构 §9）：
- schema 面（get_tool_definitions 的 enabled/disabled）+ conversation_loop 的
  valid_tool_names 闸门共同决定可调用性；绕过 run_conversation 直接
  registry.dispatch 没有任何 toolset 隔离，禁止。
- KB/KG/SQL/论文/CodeMode 工具已从 get_project_tools 移除（惰性导入）。
- 禁用工具在实际 dispatcher 也不可调用：由 valid_tool_names 保证。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable

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


def register_safe_project_tools(thread_context_provider: Any) -> int:
    """注册安全项目工具（时间/待办/提醒/时间解析）到 Hermes registry。

    幂等；必须在 AIAgent 构造之前调用。handler 用 LangChain 官方 invoke()
    入口（工具签名可能要求 config），thread_id 经 provider 注入。
    返回本次实际新注册数量。
    """
    ensure = _ensure_hermes_loaded
    ensure()
    from tools.registry import registry  # noqa: PLC0415  (Hermes 顶层模块)
    from backend.tools.tools_decorator import get_project_tools

    registered = 0
    for tool in get_project_tools():
        name = getattr(tool, "name", getattr(tool, "__name__", "unknown"))
        if name in _registered_tools:
            continue
        toolset = getattr(tool, "_toolset", "agentforge_project")
        schema = _tool_schema(tool)
        registry.register(
            name,
            description=schema.get("description", ""),
            parameters=schema.get("parameters", {"type": "object", "properties": {}}),
            handler=_make_handler(tool, thread_context_provider),
            toolset=toolset,
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
            properties[name] = {"type": "string", "description": field.description or ""}
            if field.is_required():
                required.append(name)
        return {
            "description": (tool.description or "").strip(),
            "parameters": {"type": "object", "properties": properties, "required": required},
        }
    except Exception:
        return {"description": getattr(tool, "description", ""), "parameters": {"type": "object", "properties": {}}}


def _make_handler(tool: Any, thread_context_provider: Any):
    def _handler(args, **_kwargs):
        thread_id = None
        try:
            thread_id = thread_context_provider()
        except Exception:
            pass
        run_config = {"configurable": {"thread_id": thread_id}} if thread_id else None
        result = tool.invoke(args or {}, config=run_config)
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
