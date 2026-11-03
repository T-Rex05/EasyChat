"""
fact_anchor 策略 —— 压缩前先抽关键事实作为只读片段注入

解决 Hermes 原配摘要压缩的一个固有问题：
"语义摘要压得越顺，任务跑得越歪"——订单号、参数值、已做决策等"无语言特征的执行事实"
在摘要中最先被牺牲，导致长任务里模型从自己压出来的历史里拼不出当前状态。

机制：
  1. 压缩触发时，先用全局模型把当前消息里的"关键事实"提取成结构化清单
  2. 把事实清单作为 memory_context 传给 Hermes 的 ContextCompressor，
     让摘要 prompt 优先保留这些信息
  3. 把事实清单作为【只读系统消息】注入到压缩后消息列表的头部，
     确保即使摘要过程有损，模型在下一轮也能直接看到关键事实

设计原则：
  - 继承 ContextCompressor：复用 Hermes 全部压缩逻辑（阈值/保护首尾/裁剪/ orphan 清理）
  - 仅重写 compress()：压缩前的"事实提取" + 压缩后的"事实注入"
  - 优雅降级：事实提取失败 → 退化为 Hermes 默认压缩，不阻塞对话
  - 成本可控：只在真正触发压缩时才调 LLM 抽事实（低频操作）
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from backend.context.config import (
    get_fact_anchor_enabled,
    get_fact_anchor_max_facts,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 事实提取 prompt
# ──────────────────────────────────────────────────────────────

_FACT_EXTRACTION_PROMPT = """你是一个"会话事实提取器"。从下面的对话历史中提取【关键事实清单】。

关键事实的定义：后续任何决策都可能依赖的、一旦丢失就会让任务"跑歪"的信息。
包括但不限于：
  - 已确定的参数、配置、阈值（具体数值，不要概括）
  - 关键 ID：订单号、文件路径、数据库名、URL、标识符（原样保留）
  - 已做的决策 + 简要理由
  - 已修改的状态（改了哪个文件/哪条记录/哪个系统，从什么改成什么）
  - 当前进度：完成了哪几步，下一步是什么
  - 用户明确提出的硬性约束（"必须 X"、"不能 Y"、"优先 Z"）

【不要提取】
  - 寒暄、重复信息、已经被新信息覆盖的旧信息
  - 推理过程、中间尝试（除非它导出了最终决策）

输出严格 JSON，不要任何 Markdown 标记或解释：
{
  "facts": [
    {"category": "param|id|decision|state|progress|constraint", "content": "具体事实（一句话，保留数值和标识符）"},
    ...
  ],
  "next_action": "当前应该做的下一步（一句话，没有则为空字符串）"
}

最多输出 {max_facts} 条事实，按重要性排序。没有值得保留的事实就返回 {{"facts": [], "next_action": ""}}。

--- 对话历史 ---
{transcript}
"""


# ──────────────────────────────────────────────────────────────
# 关键事实注入时使用的系统消息模板
# ──────────────────────────────────────────────────────────────

_FACT_ANCHOR_SYSTEM_TEMPLATE = (
    "<fact_anchor>以下是从本轮对话历史中提取的关键事实，由系统自动维护，"
    "请勿修改或质疑其真实性，仅作为后续决策的参考依据：\n"
    "{facts_text}\n"
    "当前下一步建议：{next_action}\n"
    "</fact_anchor>"
)


# ──────────────────────────────────────────────────────────────
# 策略实现
# ──────────────────────────────────────────────────────────────

def build(**kwargs: Any) -> "FactAnchorCompressor":
    """fact_anchor 策略工厂。

    kwargs 对齐 ContextCompressor 的构造参数（由 hermes_adapter 从 agent 属性组装）。
    """
    return FactAnchorCompressor(**kwargs)


class FactAnchorCompressor:
    """fact_anchor 策略引擎。

    通过 duck-typing 兼容 Hermes 的 context_compressor 插槽：
    Hermes 只调用 should_compress / compress / update_from_response /
    update_model / get_status 等方法，本类把这些调用代理给内部持有的
    ContextCompressor 实例，仅在 compress() 前后插入事实提取/注入逻辑。

    为什么用代理而不是继承：
    ContextCompressor 构造参数极多（20+ 个）且内部实现频繁变化，
    代理模式只需要从 hermes_adapter 拿到 Hermes 已经创建好的
    ContextCompressor 实例就能工作，避免重复构造和版本耦合。
    """

    def __init__(self, inner: Any):
        """
        Args:
            inner: Hermes 已经构造好的 ContextCompressor 实例。
                   所有非 compress 的调用都代理给它。
        """
        self._inner = inner
        self._last_facts: List[Dict[str, str]] = []
        self._last_next_action: str = ""

    # ── 透传属性 / 方法（Hermes 主循环依赖的接口）─────────────

    def __getattr__(self, name: str) -> Any:
        """所有未在本类定义的方法/属性，全部代理给内部 ContextCompressor。

        这样 Hermes 调用 update_from_response / should_compress / update_model /
        get_status / prune_tool_results_only / should_compress_preflight /
        on_session_start / on_session_end / on_session_reset / get_tool_schemas
        等等都能无感穿透。
        """
        return getattr(self._inner, name)

    # ── 核心：重写 compress ──────────────────────────────────

    def compress(
        self,
        messages: List[Dict[str, Any]],
        current_tokens: Optional[int] = None,
        focus_topic: Optional[str] = None,
        force: bool = False,
        memory_context: str = "",
    ) -> List[Dict[str, Any]]:
        """压缩前抽事实 + 压缩后注入事实。

        流程：
          1. 检查 fact_anchor 总开关（FACT_ANCHOR_ENABLED），关闭则直接透传
          2. 调用 LLM 从当前消息中提取关键事实（失败则降级为透传）
          3. 把事实作为 memory_context 传给内部 ContextCompressor.compress()
          4. 把事实作为系统消息注入到返回的消息列表头部
        """
        # 1. 开关检查
        if not get_fact_anchor_enabled():
            return self._inner.compress(
                messages,
                current_tokens=current_tokens,
                focus_topic=focus_topic,
                force=force,
                memory_context=memory_context,
            )

        # 2. 提取关键事实
        facts_json = self._extract_facts(messages)
        facts = facts_json.get("facts") if isinstance(facts_json, dict) else []
        next_action = (facts_json.get("next_action") or "").strip() if isinstance(facts_json, dict) else ""

        if not isinstance(facts, list):
            facts = []

        # 截断到配置的最大条数
        max_facts = get_fact_anchor_max_facts()
        facts = facts[:max_facts]

        self._last_facts = facts
        self._last_next_action = next_action

        # 3. 组装 memory_context（和原有 memory_context 拼接，不覆盖）
        if facts:
            facts_text = self._format_facts(facts)
            anchor_block = f"<fact_anchor>\n{facts_text}\n下一步: {next_action or '(未指定)'}\n</fact_anchor>"
            combined_memory_context = (
                f"{memory_context}\n\n{anchor_block}".strip()
                if memory_context else anchor_block
            )
        else:
            facts_text = ""
            combined_memory_context = memory_context

        # 4. 调用内部 ContextCompressor 做真正的压缩
        compressed = self._inner.compress(
            messages,
            current_tokens=current_tokens,
            focus_topic=focus_topic,
            force=force,
            memory_context=combined_memory_context,
        )

        # 5. 注入到压缩后列表的【末尾】（KV Cache 友好）
        # ── KV Cache 优化 ──
        # 旧实现：把 fact_anchor 作为 system 消息插到系统 prompt 之后（idx=1），
        # 导致从该位置开始的所有后续消息（对话历史、工具结果）前缀全部失效，
        # 缓存命中率从 99% 骤降到 ~50%。
        #
        # 新实现：追加为末尾 user 消息。根据 KV Cache 前缀匹配原理：
        #   - 系统 prompt（~8K tokens）+ 对话历史 位置不变 → 前缀稳定
        #   - 动态内容放在最后 → 只影响尾部，不破坏已有缓存
        # 参见：docs/Agent 上下文管理：五种常见错误为什么会让 KV Cache 失效.md
        #
        # ── 压缩无进展判定修复 ──
        # 只有在压缩确实产出了新列表时才追加，避免就地改写调用方的 live list。
        # Hermes 用 `compressed == messages_before_compression` 判定"无进展"，
        # 多 append 一行会破坏这个判定并触发无谓的会话轮换。
        if facts and compressed and compressed is not messages:
            anchor_msg = {
                "role": "user",
                "content": _FACT_ANCHOR_SYSTEM_TEMPLATE.format(
                    facts_text=facts_text,
                    next_action=next_action or "(未指定)",
                ),
            }
            compressed.append(anchor_msg)
            logger.info(
                f"📌 [fact_anchor] 注入 {len(facts)} 条关键事实"
                f"（末尾追加，KV Cache 友好）"
            )

        return compressed

    # ── 内部方法 ─────────────────────────────────────────────

    def _extract_facts(self, messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """调用全局模型提取关键事实。失败返回 None（调用方降级处理）。"""
        # 过滤空消息 / 过短的对话（少于 4 条不抽）
        meaningful = [m for m in messages if (m.get("content") or "")]
        if len(meaningful) < 4:
            return {"facts": [], "next_action": ""}

        # 序列化对话为可读文本（截断过长的单条，避免 prompt 爆炸）
        transcript_parts = []
        for m in meaningful:
            role = m.get("role", "?")
            content = m.get("content") or ""
            # 工具调用/结果也带上，它们经常包含关键 ID 和参数
            if role == "tool":
                name = m.get("name") or "tool"
                content = f"[tool:{name}] {content}"
            # 单条截断 2000 字符，足以保留事实又不让 prompt 爆炸
            if len(content) > 2000:
                content = content[:2000] + "...(已截断)"
            transcript_parts.append(f"[{role}] {content}")

        transcript = "\n".join(transcript_parts)
        # 整个 transcript 也截断，防止超长会话
        if len(transcript) > 12000:
            transcript = transcript[:12000] + "\n...(历史已截断)"

        prompt = _FACT_EXTRACTION_PROMPT.format(
            max_facts=get_fact_anchor_max_facts(),
            transcript=transcript,
        )

        try:
            from backend.utils.traced_llm import traced_llm

            # 尝试从上下文获取 user_id
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                uid = int(_CURRENT_USER_ID_CTX.get() or 0)
            except Exception:
                uid = 0

            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="context_fact_extract",
                user_id=uid,
                source="context",
                temperature=0,
                max_tokens=1024,
            )
            content = (resp.content or "").strip()

            # 解析 JSON：先尝试直接解析，失败则提取 ```json ``` 块或第一个 {...}
            parsed = self._parse_json(content)
            if parsed is None:
                logger.warning(
                    f"⚠️ [fact_anchor] LLM 返回无法解析的 JSON: {content[:200]}"
                )
                return None
            return parsed

        except Exception as e:
            logger.warning(f"[fact_anchor] 事实提取失败，降级为普通压缩: {e}")
            return None

    @staticmethod
    def _parse_json(content: str) -> Optional[Dict[str, Any]]:
        """从 LLM 输出中解析 JSON，多种回退策略。"""
        if not content:
            return None
        # 1. 直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # 2. 提取 ```json ``` 代码块
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content, re.IGNORECASE)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass
        # 3. 提取第一个 {...} 块
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _format_facts(facts: List[Dict[str, Any]]) -> str:
        """把事实列表渲染成可读文本。"""
        lines = []
        idx = 0
        for f in facts:
            if not isinstance(f, dict):
                continue
            content = (f.get("content") or "").strip()
            if not content:
                continue
            idx += 1
            cat = (f.get("category") or "").strip()
            prefix = f"[{cat}] " if cat else ""
            lines.append(f"{idx}. {prefix}{content}")
        return "\n".join(lines)
