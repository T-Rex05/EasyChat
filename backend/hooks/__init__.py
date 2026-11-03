"""
AgentForge 聊天钩子系统 — 可插拔的业务逻辑扩展点

使用方式：
    from backend.hooks import ChatHooks, ChatHookContext, register_hooks

    def my_pre_process(ctx: ChatHookContext) -> ChatHookContext:
        # 消息预处理（如业务域守卫、RAG 增强等）
        return ctx

    def my_post_process(ctx: ChatHookContext, response: str) -> str:
        # 响应后处理（如报告渲染、格式化等）
        return response

    register_hooks(ChatHooks(
        pre_process=my_pre_process,
        post_process=my_post_process,
    ))

钩子函数均为可选，传 None 则跳过。所有钩子支持同步和异步（async def）。
"""
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Dict, Any


@dataclass
class ChatHookContext:
    """
    传递给钩子函数的上下文对象。

    属性:
        thread_id: 会话线程 ID
        user_id: 用户 ID（从 thread_id 解析）
        user_message: 用户原始消息
        mode: 会话模式（如 "normal"、自定义模式等）
        history: 对话历史（最近 N 条）
        model_config: 当前模型配置
        system_prompt: 系统提示词
        metadata: 可扩展元数据字典（钩子间传递自定义数据）
        sse_events: 自定义 SSE 事件列表（钩子可追加额外事件推送给前端）
        conversation_id: 数据库对话 ID（入口即落库后赋值）
    """
    thread_id: str
    user_id: int = 0
    user_message: str = ""
    mode: str = "normal"
    history: List[dict] = field(default_factory=list)
    model_config: Dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    sse_events: List[dict] = field(default_factory=list)
    conversation_id: Optional[int] = None


@dataclass
class ChatHooks:
    """
    可插拔的聊天钩子集合。

    所有字段均为可选（None = 不执行该钩子）。

    钩子执行顺序：
        1. on_session_start  — 请求开始（可选，用于初始化上下文）
        2. pre_process       — 消息预处理（修改消息/注入上下文）
        3. on_stream_chunk   — 每个流式 token 经过时触发
        4. post_process      — LLM 响应完成后处理
        5. on_complete       — 对话完成回调（持久化、通知等）
        6. on_error          — 异常时触发
        7. register_routes   — 注册额外 API 路由（在 create_controller 时调用）
    """
    # 会话生命周期
    on_session_start: Optional[Callable[[ChatHookContext], Any]] = None
    on_complete: Optional[Callable[[ChatHookContext, str], Any]] = None
    on_error: Optional[Callable[[Exception, ChatHookContext], Any]] = None

    # 消息处理
    pre_process: Optional[Callable[[ChatHookContext], ChatHookContext]] = None
    post_process: Optional[Callable[[ChatHookContext, str], str]] = None

    # 流式处理
    on_stream_chunk: Optional[Callable[[str, ChatHookContext], None]] = None

    # 路由扩展
    register_routes: Optional[Callable[[Any], None]] = None  # Callable[[FastAPI], None]


# ── 全局钩子注册表 ──
_active_hooks: Optional[ChatHooks] = None


def register_hooks(hooks: ChatHooks) -> None:
    """
    注册业务钩子。

    在应用启动时调用（通常在 main.py 或用户入口脚本中）。
    多次调用会覆盖之前的注册。传 None 清除所有钩子。
    """
    global _active_hooks
    _active_hooks = hooks


def get_hooks() -> Optional[ChatHooks]:
    """获取当前注册的钩子集合（无钩子时返回 None）。"""
    return _active_hooks


def has_hooks() -> bool:
    """是否有钩子已注册。"""
    return _active_hooks is not None
