"""
Adaptive RAG Router — 参考 Adaptive-RAG (Jeong et al., NAACL 2024)。

核心思想：路由器只决定"检索多少"，不管"怎么检索"。
- No Retrieval → LLM 直接回答，跳过整个检索管线
- Single-Step → 标准 RAG，单次检索
- Multi-Step  → 迭代检索 + 查询改写 + 多路召回

检索细节（mode / rerank / weights 等）由已有机制控制：
- 置信度门控 → 控制是否跳过昂贵操作
- CRAG 质量评估 → 控制是否补充/纠正
- classify_query_for_weights → 控制 RRF 权重

设计原则：
- 零 LLM 调用：纯规则分类，延迟 < 1ms
- 3 种策略，不过度细分
- 安全降级：不确定时回退到 SINGLE_STEP
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# 查询复杂度（参考 Adaptive-RAG 论文的三级分类）
# ════════════════════════════════════════════════════════════

class QueryComplexity(str, Enum):
    """查询复杂度 — 决定检索深度。"""
    NO_RETRIEVAL = "no_retrieval"     # LLM 参数记忆即可回答
    SINGLE_STEP = "single_step"       # 单次检索足够
    MULTI_STEP = "multi_step"         # 需要多轮检索 + 推理


# ════════════════════════════════════════════════════════════
# 路由结果
# ════════════════════════════════════════════════════════════

@dataclass
class RoutingResult:
    """路由结果 — 路由器输出，dual_path_retrieve 消费。"""
    complexity: QueryComplexity
    skip_retrieval: bool = False          # True = 跳过检索，LLM 直答
    enable_rewrite: bool = False          # 是否启用查询改写
    enable_sub_queries: bool = False      # 是否分解子查询
    enable_web_fallback: bool = False     # 是否启用 Web 兜底
    top_k_multiplier: float = 1.0         # top_k 放大系数
    reason: str = ""


# ════════════════════════════════════════════════════════════
# 复杂度信号检测
# ════════════════════════════════════════════════════════════

# 多跳/多步推理信号（表明需要多轮检索）
_MULTI_HOP_SIGNALS = [
    "区别", "对比", "比较", "异同", "差异", "vs", "VS",
    "以及", "并且", "同时", "另外",
    "第一步", "第二步", "然后", "接着",
]

# SQL/代码特征（需要检索，但不需要多轮）
_SQL_PATTERNS = [
    "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE",
    "JOIN", "GROUP BY", "ORDER BY", "HAVING",
    "CREATE TABLE", "ALTER TABLE",
    "select ", "from ", "where ",
]


def _detect_complexity(query: str) -> QueryComplexity:
    """
    检测查询复杂度（纯规则，零 LLM 调用）。

    分类逻辑（从高到低优先级）：
    1. 极短 + 无检索信号 → NO_RETRIEVAL
    2. 多跳信号 / 长查询多问题 → MULTI_STEP
    3. 其余 → SINGLE_STEP（默认）
    """
    q = query.strip()
    length = len(q)

    # 空查询 → 不需要检索
    if not q:
        return QueryComplexity.NO_RETRIEVAL

    # 预检测：是否有检索信号（SQL / 技术术语 / 多跳词）
    has_retrieval = _has_retrieval_signals(q)

    # ── NO_RETRIEVAL 检测 ──
    # 极短 + 无检索信号 → LLM 参数记忆可覆盖
    if length <= 8 and not has_retrieval:
        return QueryComplexity.NO_RETRIEVAL

    # ── MULTI_STEP 检测 ──
    # 1. 多跳信号词（对比、并列、分步）
    for signal in _MULTI_HOP_SIGNALS:
        if signal in q:
            return QueryComplexity.MULTI_STEP

    # 2. 长查询 + 多个疑问词（暗示需要多个子查询）
    question_words = ["怎么", "如何", "什么", "哪些", "为什么", "多少", "哪", "谁"]
    question_count = sum(1 for w in question_words if w in q)
    if length >= 15 and question_count >= 2:
        return QueryComplexity.MULTI_STEP

    # 3. SQL 长查询（需要检索 schema + 生成 + 可能涉及多表）
    has_sql = any(p in q for p in _SQL_PATTERNS) or bool(
        re.search(r'(?<![a-zA-Z])sql(?![a-zA-Z])', q, re.IGNORECASE)
    )
    if has_sql and length >= 15:
        return QueryComplexity.MULTI_STEP

    # 4. 长查询 + 并列结构（逗号/顿号/并列连词分隔的多个子话题）
    if length >= 20:
        separators = q.count("，") + q.count(",") + q.count("、") + q.count("；")
        conjunctions = sum(1 for c in ["包括", "以及", "并且", "同时"] if c in q)
        if separators >= 2 or (separators >= 1 and conjunctions >= 1):
            return QueryComplexity.MULTI_STEP

    # ── SINGLE_STEP（默认）──
    return QueryComplexity.SINGLE_STEP


def _has_retrieval_signals(q: str) -> bool:
    """检测是否有明确的检索需求信号。"""
    q_lower = q.lower()
    # SQL
    if any(p in q for p in _SQL_PATTERNS):
        return True
    if re.search(r'(?<![a-zA-Z])sql(?![a-zA-Z])', q, re.IGNORECASE):
        return True
    # 技术术语
    tech_terms = [
        "redis", "mysql", "docker", "kubernetes", "api",
        "http", "json", "rag", "llm", "embedding",
        "python", "java", "golang", "bm25", "milvus", "neo4j",
    ]
    if any(t in q_lower for t in tech_terms):
        return True
    # 多跳信号
    if any(s in q for s in _MULTI_HOP_SIGNALS):
        return True
    # 疑问词（"怎么"/"如何"等表明用户不知道答案，需要检索）
    question_words = ["怎么", "如何", "什么是", "是什么", "为什么", "哪些"]
    if any(w in q for w in question_words):
        return True
    return False


# ════════════════════════════════════════════════════════════
# AdaptiveRAGRouter
# ════════════════════════════════════════════════════════════

class AdaptiveRAGRouter:
    """
    自适应 RAG 路由器（参考 Adaptive-RAG, NAACL 2024）。

    只决定"检索多少"：
    - NO_RETRIEVAL → 跳过检索，LLM 直接回答
    - SINGLE_STEP  → 标准单次检索
    - MULTI_STEP   → 迭代检索 + 查询改写 + 多路召回

    检索细节由已有机制控制，路由器不越权。
    """

    def route(self, query: str, user_id: int = 0) -> RoutingResult:
        """
        路由查询到合适的检索深度。

        Args:
            query: 用户查询
            user_id: 用户 ID（预留，未来可接入用户画像）

        Returns:
            RoutingResult: 路由结果
        """
        complexity = _detect_complexity(query)
        result = self._build_result(complexity, query)

        logger.info(
            f"[AdaptiveRAG] '{query[:40]}' → "
            f"{complexity.value} | {result.reason}"
        )

        return result

    def _build_result(
        self, complexity: QueryComplexity, query: str
    ) -> RoutingResult:
        """根据复杂度构建路由结果。"""

        if complexity == QueryComplexity.NO_RETRIEVAL:
            return RoutingResult(
                complexity=complexity,
                skip_retrieval=True,
                enable_rewrite=False,
                enable_sub_queries=False,
                enable_web_fallback=False,
                top_k_multiplier=0,
                reason=f"短查询(len={len(query)})，LLM 直答",
            )

        if complexity == QueryComplexity.MULTI_STEP:
            return RoutingResult(
                complexity=complexity,
                skip_retrieval=False,
                enable_rewrite=True,
                enable_sub_queries=True,
                enable_web_fallback=True,
                top_k_multiplier=1.5,
                reason="复杂查询，启用改写 + 子查询 + Web 兜底",
            )

        # SINGLE_STEP — 标准路径
        return RoutingResult(
            complexity=complexity,
            skip_retrieval=False,
            enable_rewrite=False,
            enable_sub_queries=False,
            enable_web_fallback=False,
            top_k_multiplier=1.0,
            reason="标准查询，单次检索",
        )


# ════════════════════════════════════════════════════════════
# 便捷函数
# ════════════════════════════════════════════════════════════

_router_instance: Optional[AdaptiveRAGRouter] = None


def get_adaptive_router() -> AdaptiveRAGRouter:
    """获取全局路由器实例（单例）。"""
    global _router_instance
    if _router_instance is None:
        _router_instance = AdaptiveRAGRouter()
    return _router_instance


def route_query(query: str, user_id: int = 0) -> RoutingResult:
    """便捷函数：查询 → 路由结果。"""
    return get_adaptive_router().route(query, user_id)
