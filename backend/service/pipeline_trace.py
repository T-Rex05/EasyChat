"""
Pipeline Trace — RAG 全链路追踪

在 PIPELINE_TRACE=true 时，记录每次请求从「用户提问 → 记忆检索 → KB 检索 → 图谱扩展 → 工具调用 → 最终响应」的完整数据流。

输出目标：
  - 控制台（通过 loguru stdout handler）
  - audit.log（loguru INFO 级别文件 handler）

设计：
  - 使用 contextvars 实现请求级隔离（与 _MEMORY_REFS_CTX 同模式）
  - PipelineTrace 实例在 stream.py 入口创建，结束时 flush
  - 各阶段（agentforge_provider / tools_decorator / hermes dispatch）通过 record() 写入
  - 零开销：PIPELINE_TRACE != true 时 is_enabled() 返回 False，各注入点短路跳过
"""

import json
import os
import time
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

# 必须用 log_utils 的 logger（经过 patch(_patch_shanghai_time)），
# 不能直接 from loguru import logger，否则缺少 extra["shanghai_time"]
from backend.utils.log_utils import logger

# ── 环境变量 ──────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """检查 PIPELINE_TRACE 是否开启（支持 true/1/yes/on，不区分大小写）"""
    return os.getenv("PIPELINE_TRACE", "false").strip().lower() in ("1", "true", "yes", "on")


# ── contextvar（请求级隔离）──────────────────────────────────────────────

_PIPELINE_TRACE_CTX: ContextVar[Optional["PipelineTrace"]] = ContextVar(
    "_pipeline_trace_ctx", default=None
)


# ── 截断工具 ──────────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int = 150) -> str:
    """截断文本用于展示：去除换行，保留开头 max_len 字符"""
    text = (text or "").replace("\n", " ").replace("\r", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


# ── PipelineTrace 核心类 ──────────────────────────────────────────────────

class PipelineTrace:
    """请求级 RAG 全链路追踪。

    生命周期：
      stream.py 入口 → __init__() + _PIPELINE_TRACE_CTX.set(trace)
        → agentforge_provider.prefetch() → record("memory_...", ...)
        → knowledge_search() 工具 → record("kb_...", ...)
        → 其他工具调用 → record_tool(...)
      stream.py 结束 → flush() + _PIPELINE_TRACE_CTX.set(None)
    """

    def __init__(self, user_id: int, thread_id: str, message: str):
        self.user_id = user_id
        self.thread_id = thread_id
        self.message = _truncate(message, 200)
        self.start_time = time.monotonic()
        self.stages: List[Dict[str, Any]] = []   # 各阶段数据
        self.tool_calls: List[Dict[str, Any]] = []  # 工具调用记录

    @staticmethod
    def current() -> Optional["PipelineTrace"]:
        """获取当前请求的 PipelineTrace 实例（None 表示未启用）"""
        return _PIPELINE_TRACE_CTX.get()

    def record(self, stage: str, **kwargs) -> None:
        """记录一个阶段的数据"""
        entry = {
            "stage": stage,
            "ts": round((time.monotonic() - self.start_time) * 1000),  # 毫秒偏移
            **kwargs,
        }
        self.stages.append(entry)

    def record_tool(self, name: str, args: Any, result: str, duration_ms: int) -> None:
        """记录工具调用"""
        # args 可能是 dict 或 JSON string
        try:
            if isinstance(args, str):
                args_preview = _truncate(args, 120)
            else:
                args_preview = _truncate(json.dumps(args, ensure_ascii=False), 120)
        except Exception:
            args_preview = _truncate(str(args), 120)

        self.tool_calls.append({
            "name": name,
            "args_preview": args_preview,
            "result_preview": _truncate(result, 200),
            "duration_ms": duration_ms,
        })

    def flush(self) -> None:
        """输出完整链路到控制台 + 文件，然后清理 contextvar"""
        try:
            if self.stages or self.tool_calls:
                output = self._format()
                logger.info(output)
        except Exception as e:
            logger.warning(f"[PipelineTrace] _format 失败: {e}")
        finally:
            _PIPELINE_TRACE_CTX.set(None)

    # ── 格式化输出 ─────────────────────────────────────────────────────

    def _format(self) -> str:
        """格式化为可读链路报告"""
        total_ms = round((time.monotonic() - self.start_time) * 1000)
        sep = "─" * 52

        lines = [
            f"{'═' * 18} 🔍 RAG 链路追踪 {'═' * 17}",
            f"📥 请求 | user={self.user_id} thread={self.thread_id}",
            f"   「{self.message}」",
        ]

        # 按阶段分组输出
        memory_stages = [s for s in self.stages if s["stage"].startswith("memory_")]
        kb_stages = [s for s in self.stages if s["stage"].startswith("kb_")]
        other_stages = [s for s in self.stages if not s["stage"].startswith(("memory_", "kb_"))]

        # 预定义摘要用变量（防止 memory_stages 为空时 NameError）
        final = None

        # ── 记忆检索 ──
        if memory_stages:
            lines.append(sep)
            # 汇总信息
            final = next((s for s in memory_stages if s["stage"] == "memory_final"), None)
            hybrid = next((s for s in memory_stages if s["stage"] == "memory_hybrid_search"), None)
            total_hits = final["total"] if final else (hybrid["total_results"] if hybrid else 0)
            elapsed = memory_stages[-1]["ts"]
            lines.append(f"🧠 记忆检索 | 耗时={elapsed}ms | 命中={total_hits}条")

            # 展示 top 结果（从 hybrid_search 或 rerank 阶段取）
            top_results = []
            for s in memory_stages:
                if "top_results" in s and s["top_results"]:
                    top_results = s["top_results"]
            for item in top_results[:5]:
                content = _truncate(item.get("content", ""), 80)
                score = item.get("score", 0)
                source = item.get("source", "")
                mid = item.get("id", "?")
                lines.append(f"  [M{mid}] (score={score:.3f}, src={source}) {content}")

            # 图谱扩展信息
            graph = next((s for s in memory_stages if s["stage"] == "memory_graph_expansion"), None)
            if graph and graph.get("expanded_count", 0) > 0:
                lines.append(
                    f"  └ 图谱扩展: 种子={len(graph.get('seed_ids', []))} "
                    f"→ 关联={graph['expanded_count']}"
                )

            # 矛盾检测
            if final and final.get("conflict_count", 0) > 0:
                lines.append(f"  ⚠️ 矛盾检测: {final['conflict_count']}对")

        # ── KB 检索 ──
        if kb_stages:
            lines.append(sep)
            kb = kb_stages[0]  # 通常只有一次 KB 检索
            elapsed = kb["ts"]
            main_count = kb.get("main_count", 0)
            case_count = kb.get("case_count", 0)
            selected = kb.get("selected_kbs", [])
            adaptive_c = kb.get("adaptive_complexity")

            # 路由信息后缀
            routing_suffix = f" | 路由={adaptive_c}" if adaptive_c else ""
            lines.append(f"📚 KB 检索 | 耗时={elapsed}ms | 知识库={selected} | 命中={main_count + case_count}条{routing_suffix}")

            for chunk in kb.get("top_chunks", [])[:5]:
                content = _truncate(chunk.get("content", ""), 80)
                # 相关度展示：优先真实语义分（Rerank / 实体余弦），融合分只作参考 ——
                # 多查询 RRF 会把 score 压成 0.0x 量级，直接显示会让人误判"检索质量很差"
                score = chunk.get("rerank_score")
                if score is None:
                    score = chunk.get("entity_score")
                if score is None:
                    score = chunk.get("score", 0)
                source = chunk.get("source", "")
                doc_id = chunk.get("doc_id", "")
                method = kb.get("retrieval_method") or ""
                lines.append(f"  [K{doc_id}] (score={score:.3f}, src={source or method}) {content}")

            if kb.get("has_graphrag"):
                lines.append("  └ GraphRAG 增强: ✓")

            # Adaptive routing 决策详情
            adaptive_reason = kb.get("adaptive_reason")
            if adaptive_c and adaptive_reason:
                lines.append(f"  └ 🔀 路由: {adaptive_c} — {adaptive_reason}")

        # ── 工具调用 ──
        if self.tool_calls:
            lines.append(sep)
            lines.append(f"🔧 工具调用 | 共{len(self.tool_calls)}次")
            for i, tc in enumerate(self.tool_calls, 1):
                name = tc["name"]
                args_p = tc["args_preview"]
                result_p = tc["result_preview"]
                dur = tc["duration_ms"]
                lines.append(f"  {i}⃝ {name}({args_p})")
                lines.append(f"     → {_truncate(result_p, 100)}  [{dur}ms]")

        # ── 其他阶段 ──
        if other_stages:
            lines.append(sep)
            for s in other_stages:
                lines.append(f"📌 {s['stage']} | ts={s['ts']}ms")

        # ── 摘要 ──
        lines.append(sep)
        mem_count = final["total"] if final else 0
        kb_total = sum(s.get("main_count", 0) + s.get("case_count", 0) for s in kb_stages)
        tool_count = len(self.tool_calls)
        # 路由决策（从 KB 阶段提取）
        routing_info = next((s.get("adaptive_complexity") for s in kb_stages if s.get("adaptive_complexity")), None)
        routing_str = f" | 路由={routing_info}" if routing_info else ""
        lines.append(
            f"📊 摘要 | 总耗时={total_ms}ms{routing_str} | 记忆={mem_count}条 "
            f"| KB={kb_total}chunks | 工具={tool_count}次"
        )
        lines.append("═" * 52)

        return "\n".join(lines)
