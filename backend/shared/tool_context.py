"""工具执行身份：contextvar + RunnableConfig 双通道。

Hermes 的异步工具可能在新的线程/任务里执行，contextvar 不会自动跨线程继承；
因此业务工具必须优先读取 ``RunnableConfig.configurable["tool_context"]``，缺失时
再回退到当前 contextvar。工具不接受模型传入的 ``user_id``。
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

from backend.shared.context import Principal

TOOL_CONTEXT_CONFIG_KEY = "tool_context"

_CURRENT_TOOL_CONTEXT: ContextVar["ToolContext | None"] = ContextVar(
    "easychat_tool_context", default=None
)


@dataclass(frozen=True, slots=True)
class ToolContext:
    principal: Principal
    run_id: str = ""
    session_id: str = ""
    source: str = ""
    channel_account_id: str | None = None
    # 渠道来源标识（T5）：任务受理时固定回执目标用；非渠道来源为空
    source_ref: str = ""
    source_chat_id: str = ""


def current() -> ToolContext | None:
    return _CURRENT_TOOL_CONTEXT.get()


def set_current(context: ToolContext | None) -> Token:
    return _CURRENT_TOOL_CONTEXT.set(context)


def reset_current(token: Token) -> None:
    _CURRENT_TOOL_CONTEXT.reset(token)


@contextmanager
def bind(context: ToolContext | None) -> Iterator[ToolContext | None]:
    token = set_current(context)
    try:
        yield context
    finally:
        reset_current(token)


def from_config(config: Any) -> ToolContext | None:
    """从 LangChain RunnableConfig 读取；非法值返回 None，不抛异常。"""
    if config is None:
        return None
    configurable: Any = None
    if isinstance(config, Mapping):
        configurable = config.get("configurable", config)
    else:
        configurable = getattr(config, "configurable", None)
        if configurable is None:
            try:
                configurable = config["configurable"]
            except Exception:  # noqa: BLE001  config 结构由调用方决定
                return None
    if not isinstance(configurable, Mapping):
        return None
    value = configurable.get(TOOL_CONTEXT_CONFIG_KEY)
    return value if isinstance(value, ToolContext) else None


def resolve(config: Any = None) -> ToolContext | None:
    """配置通道优先，contextvar 兜底。"""
    return from_config(config) or current()


def config_with(context: ToolContext, *, thread_id: str | None = None) -> dict[str, Any]:
    """构造同时携带 thread_id 与 ToolContext 的 RunnableConfig。"""
    configurable: dict[str, Any] = {TOOL_CONTEXT_CONFIG_KEY: context}
    if thread_id:
        configurable["thread_id"] = thread_id
    return {"configurable": configurable}
