"""子 Agent 上下文富化 -- 自动注入 Supervisor 的 TaskState + 记忆快照 + 输出契约

每次委派从持久化源实时读取，不缓存。只读快照，降级友好。
数据流：
    Supervisor LLM 生成 tool_call(goal, context)
        -> enrich_context() 在 context 前追加 TaskState + 记忆 + 输出契约
        -> _build_child_system_prompt() 照常拼接
        -> 子 Agent 拿到富化后的系统提示
"""
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 子 Agent 输出契约（B3）──
# 现状：子 Agent 的产出是自由文本，父侧按字符预算截断（Hermes 的 _apply_summary_budget），
# 关键结论可能被砍掉。给子 Agent 一个最小结构，截断时就能"保结论、砍证据"。
# 可用 AGENTFORGE_DELEGATION_CONTRACT=0 关闭（回到原生行为）。
_OUTPUT_CONTRACT = """<output_contract>
最终回复末尾必须附一个结构化结论块（其余正文照常），字段缺失写 "none"：
<result>
task: <一句话说明你做了什么>
status: success | partial | failed
conclusion: <核心结论，1-3 句，必须可独立阅读>
evidence: <支撑结论的关键数据/文件路径/命令输出，可多行>
files: <创建或修改的文件绝对路径，逗号分隔；无则 none>
errors: <遇到的问题；无则 none>
</result>
</output_contract>"""


def _contract_enabled() -> bool:
    """输出契约开关（默认开启）。"""
    return os.environ.get("AGENTFORGE_DELEGATION_CONTRACT", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def enrich_context(context: Optional[str], goal: str = "") -> str:  # noqa: ARG001
    """富化子 Agent 的 context，在 LLM 原始输入前追加 TaskState + 记忆

    Args:
        context: LLM 填的原始 context
        goal: 任务目标（预留，未来可用于过滤记忆）

    Returns:
        富化后的 context 字符串
    """
    parts = []

    # 1. TaskState -- 从 TaskStateMaintainer 内存缓存读（源头是 state.db）
    try:
        ts = _load_task_state()
    except Exception:
        ts = None
    if ts:
        formatted = _format_task_state(ts)
        if formatted:
            parts.append(formatted)

    # 2. 记忆快照 -- 从 _MEMORY_REFS_CTX 读（本轮 prefetch 缓存）
    try:
        refs = _load_memory_refs()
    except Exception:
        refs = None
    if refs:
        formatted = _format_memories(refs)
        if formatted:
            parts.append(formatted)

    # 3. 输出契约 -- 约束子 Agent 的产出结构（可关）
    try:
        if _contract_enabled():
            parts.append(_OUTPUT_CONTRACT)
    except Exception:
        pass

    # 4. LLM 原始 context
    #    有富化内容时用 <supervisor_notes> 包裹，否则直接返回原始 context
    has_enrichment = bool(parts)
    if context and context.strip():
        if has_enrichment:
            parts.append(f"<supervisor_notes>\n{context.strip()}\n</supervisor_notes>")
        else:
            return context.strip()

    if not parts:
        return (context or "").strip()

    return "\n\n".join(parts)


def _load_task_state() -> Optional[dict]:
    """从 TaskStateMaintainer 加载当前任务状态"""
    try:
        thread_id = _get_thread_id()
        if not thread_id:
            return None
        from backend.context.task_state import get_task_state_maintainer

        maintainer = get_task_state_maintainer()
        state = maintainer.get_state(thread_id)
        return state if state else None
    except Exception:
        logger.debug("TaskState 加载失败，跳过", exc_info=True)
        return None


def _load_memory_refs() -> Optional[dict]:
    """读取本轮 prefetch 缓存的记忆引用"""
    try:
        from backend.memory.agentforge_provider import _MEMORY_REFS_CTX

        refs = _MEMORY_REFS_CTX.get(None)
        return refs if refs else None
    except Exception:
        logger.debug("记忆引用加载失败，跳过", exc_info=True)
        return None


def _get_thread_id() -> Optional[str]:
    """从 ContextVar 获取当前 thread_id"""
    try:
        from backend.hermes_adapter import _THREAD_ID_CTX

        return _THREAD_ID_CTX.get(None)
    except Exception:
        return None


def _format_task_state(ts: dict) -> Optional[str]:
    """格式化 TaskState 为 XML 标签包裹的文本"""
    if not ts:
        return None

    field_map = {
        "current_goal": "当前目标",
        "completed_steps": "已完成步骤",
        "next_action": "下一步",
        "key_params": "关键参数",
        "constraints": "约束条件",
        "decisions": "已做决策",
    }

    lines = []
    for key, label in field_map.items():
        val = ts.get(key)
        if val and isinstance(val, dict):
            v = val.get("v")
            if v is not None:
                lines.append(f"{label}: {_format_value(v)}")

    if not lines:
        return None

    return "<inherited_task_state>\n" + "\n".join(lines) + "\n</inherited_task_state>"


def _format_value(v: Any) -> str:
    """将 TaskState 值格式化为人类友好的字符串"""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ", ".join(str(item) for item in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}={val}" for k, val in v.items())
    return json.dumps(v, ensure_ascii=False)


def _format_memories(refs: dict) -> Optional[str]:
    """格式化记忆引用为 XML 标签包裹的文本

    注意字段名：生产方（agentforge_provider.prefetch）写入的键是
    ``memory_type``（不是 ``category``）——早期这里读错字段名，导致真实环境
    恒输出 [unknown]。这里以 memory_type 为主、category 兜底，两边都兼容。
    """
    if not refs:
        return None

    lines = []
    for tag, mem in refs.items():
        if isinstance(mem, dict):
            category = (
                mem.get("memory_type")
                or mem.get("category")
                or mem.get("type")
                or "unknown"
            )
            content = mem.get("content", "")
            if content:
                lines.append(f"[{tag}] [{category}] {content}")

    if not lines:
        return None

    return "<inherited_memories>\n" + "\n".join(lines) + "\n</inherited_memories>"
