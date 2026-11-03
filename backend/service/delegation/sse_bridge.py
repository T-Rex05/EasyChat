"""子 Agent 桥接 -- 独立模块（无 Hermes 依赖）

将 ContextVar 桥接放在独立模块，方便测试和复用。
包含：
  - SSE 帧构造/推送（子 Agent 可视化）
  - 系统模型配置桥接（子 Agent 凭证继承，delegate_tool.py 从这里导入）

可视化路径（2026-02 起）：宿主在父 Agent 上挂 ``tool_progress_callback``，Hermes 会把
子 Agent 的生命周期事件（``subagent.start/text/tool/complete``，带 subagent_id/depth/
model/tokens 等身份字段）转发过来，宿主自己拼帧入队 —— 不再需要在 delegate_tool 里埋点。
`_push_subagent_sse`（ContextVar 版）保留作为兼容/兜底工具。
"""
import contextvars
import json
import logging
import queue
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Hermes 的子 Agent 事件名 → 前端 SSE 帧类型（单一映射，改这里即可）
SUBAGENT_EVENT_TO_FRAME: Dict[str, str] = {
    "subagent.start": "subagent_start",
    "subagent.text": "subagent_token",
    "subagent.tool": "subagent_tool",
    "subagent.complete": "subagent_complete",
}


def build_frame(frame_type: str, payload: Dict[str, Any]) -> str:
    """构造一个已格式化的 SSE 帧（含 type 字段，不依赖任何全局状态）。"""
    body = dict(payload or {})
    body["type"] = frame_type
    return f"data: {json.dumps(body, ensure_ascii=False, default=str)}\n\n"


def push_frame(queue_obj: Optional[queue.Queue], frame_type: str, payload: Dict[str, Any]) -> bool:
    """把帧推到指定队列（best-effort，永不抛）。返回是否推送成功。

    显式传队列而不是读 ContextVar：回调可能在 ThreadPoolExecutor 的工作线程里执行，
    ContextVar 不一定带得过去，闭包捕获的队列引用才是可靠的。
    """
    if queue_obj is None:
        return False
    try:
        queue_obj.put(build_frame(frame_type, payload))
        return True
    except Exception:
        return False  # best-effort: SSE loss must never break delegation


# ── SSE 队列桥接 ──
# ContextVar holding the SSE thread_queue. When set by hermes_adapter, the
# progress callback pushes subagent SSE frames directly to the queue so the
# frontend can render subagent execution in real time.
_DELEGATION_SSE_QUEUE_CTX: contextvars.ContextVar[Optional[queue.Queue]] = contextvars.ContextVar(
    "_delegation_sse_queue_ctx", default=None
)


def _push_subagent_sse(frame_type: str, payload: dict) -> None:
    """Push a subagent SSE frame to the thread_queue (best-effort, never raises).

    兼容路径：队列从 ContextVar 取。生产热路径已改为显式传队列的
    :func:`push_frame`（见 hermes_adapter 的 tool_progress 回调）。
    """
    push_frame(_DELEGATION_SSE_QUEUE_CTX.get(None), frame_type, payload)


# ── 系统模型配置桥接 ──
# 主 Agent 的 model_config 来自 model_configs 表（前端场景路由配置），
# 但子 Agent 默认走 Hermes credential_pool，可能拿到不同的（甚至过期的）凭证。
# 通过此 ContextVar 把系统 model_config 桥接到 delegate_tool，
# 让子 Agent 直接使用父 Agent 的显式凭证，不走 credential_pool。
_DELEGATION_MODEL_CONFIG_CTX: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "_delegation_model_config_ctx", default=None
)
