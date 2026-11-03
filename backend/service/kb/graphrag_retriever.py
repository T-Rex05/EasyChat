"""
GraphRAG 检索器：Global 和 DRIFT 搜索

支持三种搜索模式：
1. Local Search: 从实体扩展邻居（已有 HybridRetriever）
2. Global Search: 汇总所有社区报告（Map-Reduce）
3. DRIFT Search: 社区上下文 + 迭代扩展（混合）
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from backend.utils.log_utils import log, rag

logger = log


# ════════════════════════════════════════════════════════════
# 查询分类器
# ════════════════════════════════════════════════════════════

class QueryType:
    """查询类型常量"""
    LOCAL = "local"      # 具体实体问题
    GLOBAL = "global"    # 全局主题问题
    DRIFT = "drift"      # 混合问题


# 用于判断查询类型的关键词模式
_GLOBAL_PATTERNS = [
"总结", "概括", "核心", "主题", "主要", "整体", "全面",
"所有", "全部", "每个", "哪些", "什么关系",
"分析", "比较", "对比", "异同", "发展历程",
"为什么", "原因", "意义", "影响",
"有哪些", "包括什么",
"有什么", "哪几", "几个", "故事背景", "背景"  # 新增：更全面的全局信号
]

_LOCAL_PATTERNS = [
"是谁", "是什么", "什么是", "多少", "在哪里", "什么时候",
"多大", "几岁", "何年", "何处",
"具体", "详细", "描述", "介绍",
"哪一", "哪一个"  # 新增：单数形式才是真正的局部查询
]


class QueryClassifier:
    """
    查询分类器

    判断用户问题属于 Local、Global 还是 DRIFT 类型
    """

    def classify(self, query: str, use_llm: bool = False) -> str:
        """
        分类查询

        Args:
            query: 用户查询
            use_llm: 是否使用 LLM 分类（更准确但更慢）

        Returns:
            QueryType.LOCAL / GLOBAL / DRIFT
        """
        query_lower = query.lower().strip()

        if use_llm:
            return self._classify_with_llm(query)

        # 基于规则的分类
        return self._classify_with_rules(query_lower)

    def _classify_with_rules(self, query: str) -> str:
        """基于规则的分类"""
        # 检查匹配
        global_matches = [p for p in _GLOBAL_PATTERNS if p in query]
        local_matches = [p for p in _LOCAL_PATTERNS if p in query]
        global_score = len(global_matches)
        local_score = len(local_matches)

        # 决策逻辑：
        # 1. 强 GLOBAL 信号（≥2 个全局关键词）→ GLOBAL
        # 2. 1 global + 1 local（"原因是什么" 类型）→ GLOBAL（分析性提问）
        # 3. 纯 LOCAL（有 local 无 global）→ LOCAL
        # 4. 1 global 无 local → DRIFT
        # 5. 都无信号 → LOCAL（短小无关键词的查询通常是事实性问题）
        if global_score >= 2:
            return QueryType.GLOBAL
        elif global_score == 1 and local_score >= 1:
            return QueryType.GLOBAL  # "X的原因是什么" → 分析性
        elif local_score > 0 and global_score == 0:
            return QueryType.LOCAL
        elif global_score == 1 and local_score == 0:
            return QueryType.DRIFT
        else:
            # 无匹配信号：短查询多为事实性（LOCAL），长查询为 DRIFT
            return QueryType.LOCAL if len(query) < 20 else QueryType.DRIFT

    def _classify_with_llm(self, query: str) -> str:
        """使用 LLM 分类"""
        try:
            from backend.utils.traced_llm import traced_llm

            prompt = f"""请判断以下问题属于哪种类型：

问题: {query}

类型说明：
- LOCAL: 具体实体的事实性问题（如"关羽的武器是什么？"）
- GLOBAL: 需要全局视角的总结性问题（如"三国演义的核心主题？"）
- DRIFT: 需要一定背景但最终指向具体的问题（如"曹操的用人策略？"）

只回复一个词: LOCAL / GLOBAL / DRIFT"""

            # 尝试从上下文获取 user_id
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                uid = int(_CURRENT_USER_ID_CTX.get() or 0)
            except Exception:
                uid = 0

            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="graph_global_search",
                user_id=uid,
                source="graphrag",
                temperature=0,
                max_tokens=10,
            )
            content = (resp.content or "").strip().upper()

            if "LOCAL" in content:
                return QueryType.LOCAL
            elif "GLOBAL" in content:
                return QueryType.GLOBAL
            else:
                return QueryType.DRIFT

        except Exception as e:
            logger.debug(f"[Classifier] LLM 分类失败: {e}")
            return self._classify_with_rules(query.lower())


# ════════════════════════════════════════════════════════════
# Global 检索器
# ════════════════════════════════════════════════════════════

class GlobalRetriever:
    """
    全局检索器

    基于社区报告的 Map-Reduce 搜索：
    1. 读取所有社区报告
    2. Map: 每个报告生成答案片段（**并发**，每个报告一次独立 LLM 调用）
    3. Reduce: 汇总片段生成最终答案

    性能：Map 阶段天然可并行（报告之间无依赖）。串行跑 30 份报告实测 ~35s+，
    并发（默认 5 路）可压到几秒级；单份报告失败只丢那一片段，不影响整体。
    """

    def __init__(self, user_id: int, map_workers: int = 5):
        self.user_id = user_id
        self.map_workers = max(1, min(int(map_workers), 10))

    def _get_all_reports(self) -> List[Dict[str, Any]]:
        """获取所有社区报告"""
        from backend.graphrag.community_reporter import get_community_reports
        return get_community_reports(self.user_id, limit=100)

    def retrieve(
        self,
        query: str,
        max_reports: int = 50,
        reports: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        全局检索

        Args:
            query: 用户查询
            max_reports: 最大使用报告数
            reports: 预筛选好的报告列表（由调用方做相关性预筛，如
                `AdaptiveRetriever.community_report_search`）；None 时自行拉取全部

        Returns:
            {
                "answer": "最终答案",
                "reports_used": int,
                "answer_fragments": [...],
                "sources": [...]
            }
        """
        # 1. 获取社区报告（调用方预筛优先）
        if reports is None:
            reports = self._get_all_reports()
        if not reports:
            return {
                "answer": "没有社区报告，请先运行社区检测和报告生成",
                "reports_used": 0,
                "answer_fragments": [],
                "sources": []
            }

        # 限制报告数量
        reports = reports[:max_reports]

        # 2. Map 阶段：每个报告生成答案片段（并发）
        answer_fragments = self._map_phase(query, reports)

        if not answer_fragments:
            return {
                "answer": "无法从社区报告中提取相关信息",
                "reports_used": 0,
                "answer_fragments": [],
                "sources": []
            }

        # 3. Reduce 阶段：汇总片段
        final_answer = self._reduce_fragments(query, answer_fragments)

        return {
            "answer": final_answer,
            "reports_used": len(answer_fragments),
            "answer_fragments": answer_fragments,
            "sources": [f["title"] for f in answer_fragments]
        }

    def _map_phase(self, query: str, reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map 阶段：并发为每份报告生成答案片段（保留原报告顺序）"""
        from concurrent.futures import ThreadPoolExecutor

        def _safe_map(report: Dict[str, Any]) -> Optional[str]:
            """单个报告失败只丢这一片，绝不让整个 Map 阶段崩掉"""
            try:
                return self._map_report(query, report)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"[Global] Map 单份报告失败（已跳过）community={report.get('community_id')}: {e}"
                )
                return None

        fragments: List[Dict[str, Any]] = []
        workers = min(self.map_workers, len(reports)) or 1

        if workers == 1:
            for report in reports:
                fragment = _safe_map(report)
                if fragment:
                    fragments.append({
                        "community_id": report["community_id"],
                        "title": report["title"],
                        "fragment": fragment,
                    })
            return fragments

        # 线程池按调用创建、用 with 确定性回收：
        # GlobalRetriever 是"一次查询一个实例"的短命对象，把它做成实例属性反而
        # 会因为没有 shutdown 时机而泄漏线程；每次新建的开销远小于一次 LLM 调用。
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="global-map") as pool:
            results = list(pool.map(_safe_map, reports))

        for report, fragment in zip(reports, results):
            if fragment:
                fragments.append({
                    "community_id": report["community_id"],
                    "title": report["title"],
                    "fragment": fragment,
                })
        return fragments

    def _map_report(self, query: str, report: Dict[str, Any]) -> Optional[str]:
        """Map 阶段：从单个报告提取答案片段"""
        prompt = f"""根据以下社区报告回答问题。

问题: {query}

社区标题: {report['title']}
社区摘要: {report['summary']}
关键发现: {', '.join(report.get('findings', []))}

请从这份报告中提取与问题相关的信息，生成一个简短的答案片段（50-100字）。
如果报告与问题无关，回复"无关"。
只回复答案片段，不要其他文字。"""

        try:
            from backend.utils.traced_llm import traced_llm
            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="graph_global_search",
                user_id=self.user_id,
                source="graphrag",
                temperature=0,
                max_tokens=200,
            )
            content = (resp.content or "").strip()

            if "无关" in content or len(content) < 10:
                return None

            return content

        except Exception as e:
            logger.debug(f"[Global] Map 失败: {e}")
            return None

    def _reduce_fragments(self, query: str, fragments: List[Dict]) -> str:
        """Reduce 阶段：汇总所有片段"""
        combined = "\n\n".join([
            f"【{f['title']}】\n{f['fragment']}"
            for f in fragments
        ])

        prompt = f"""请综合以下多个信息片段，回答用户的问题。

用户问题: {query}

信息片段:
{combined}

请生成一个完整、连贯的答案。答案应该：
1. 综合所有相关信息
2. 结构清晰，条理分明
3. 不要遗漏重要信息"""

        try:
            from backend.utils.traced_llm import traced_llm
            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="graph_global_search",
                user_id=self.user_id,
                source="graphrag",
                temperature=0.3,
                max_tokens=1024,
            )
            return (resp.content or "").strip()

        except Exception as e:
            rag.error(f"[Global] Reduce 失败: {e}")
            return "生成答案失败"


# ════════════════════════════════════════════════════════════
# DRIFT 检索器
# ════════════════════════════════════════════════════════════

class DRIFTRetriever:
    """
    DRIFT 检索器

    结合社区上下文和实体扩展的混合搜索：
    1. 向量匹配找到相关社区
    2. 读取社区报告作为上下文
    3. 可选：扩展相关实体
    """

    def __init__(self, user_id: int):
        self.user_id = user_id

    def _find_relevant_communities(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """找到与查询最相关的社区（优先向量相似度，回退关键词匹配）"""
        from backend.graphrag.community_reporter import get_community_reports

        # 获取社区报告（包含 embedding 用于向量搜索）
        reports = get_community_reports(self.user_id, limit=100, include_embedding=True)

        if not reports:
            return []

        # 1. 尝试向量相似度搜索
        try:
            from backend.rag.embeddings import get_embeddings
            embeddings = get_embeddings()

            if embeddings:
                # 生成查询向量
                query_vector = embeddings.embed_query(query)

                # 获取社区报告的 embedding
                scored = []
                for report in reports:
                    report_embedding = report.get("summary_embedding")

                    if report_embedding:
                        # 计算余弦相似度
                        similarity = np.dot(query_vector, report_embedding) / (
                            np.linalg.norm(query_vector) * np.linalg.norm(report_embedding)
                        )
                        scored.append((similarity, report))

                if scored:
                    # 按相似度排序
                    scored.sort(key=lambda x: -x[0])
                    logger.debug(f"[DRIFT] Vector search found {len(scored)} communities")
                    return [r for _, r in scored[:top_k]]

        except Exception as e:
            logger.debug(f"[DRIFT] Vector search failed, fallback to keyword: {e}")

        # 2. 回退关键词匹配
        scored = []
        query_lower = query.lower()

        for report in reports:
            score = 0
            title = report.get('title', '').lower()
            summary = report.get('summary', '').lower()
            findings = ' '.join(report.get('findings', [])).lower()

            # 关键词匹配
            for word in query_lower.split():
                if len(word) > 1:
                    if word in title:
                        score += 3
                    if word in summary:
                        score += 2
                    if word in findings:
                        score += 1

            if score > 0:
                scored.append((score, report))

        # 排序取 top_k
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:top_k]]

    def retrieve(self, query: str, top_k: int = 5, enable_iteration: bool = True) -> Dict[str, Any]:
        """
        DRIFT 检索

        Args:
            query: 用户查询
            top_k: 返回的相关社区数
            enable_iteration: 是否启用迭代扩展

        Returns:
            {
                "context": "社区上下文",
                "communities_used": [...],
                "claims": [...],
                "iterations": [...],
                "answer": "LLM 生成的答案"
            }
        """
        # 1. 找到相关社区
        relevant = self._find_relevant_communities(query, top_k)

        if not relevant:
            return {
                "context": "",
                "communities_used": [],
                "claims": [],
                "iterations": [],
                "answer": "没有找到相关社区"
            }

        # 2. 使用增强器
        from backend.service.kb.drift_enhancer import enhance_drift_search

        result = enhance_drift_search(
            query=query,
            community_reports=relevant,
            user_id=self.user_id,
            retriever=self._get_adaptive() if enable_iteration else None,
            enable_iteration=enable_iteration,
        )

        result["communities_used"] = [r['title'] for r in relevant]
        return result

    def _get_adaptive(self):
        """获取 AdaptiveRetriever 实例"""
        if not hasattr(self, '_adaptive'):
            from backend.service.kb.adaptive_retriever import AdaptiveRetriever
            self._adaptive = AdaptiveRetriever(self.user_id)
        return self._adaptive


# ════════════════════════════════════════════════════════════
# Smart 检索器（统一入口）
# ════════════════════════════════════════════════════════════

class SmartRetriever:
    """
    智能检索器

    自动路由到合适的检索路径：
    - 总结型（GLOBAL）→ GlobalRetriever（社区报告 Map-Reduce）
    - 其他           → AdaptiveRetriever（实体向量 → 实体 local → 文本块兜底）
    - DRIFT          → DRIFTRetriever（社区 + 实体混合），仅在调用方显式指定 query_type 时使用

    ⚠️ 2026-09-23：分类规则已与 chat 主链路统一 —— 用
    `adaptive_retriever.classify_retrieval_kind()` 取代本地 `QueryClassifier`。
    原因：`QueryClassifier._GLOBAL_PATTERNS` 含"哪些/背景/有什么"等宽泛词，
    `global_score >= 2` 即判 GLOBAL，会把"五虎上将是哪五将，有什么故事背景"
    这类**实体型问题**误判成全局问题（设计文档 §8.1 要求它走 Local Search）。
    不统一的话，`/api/graphrag/smart-search` 调试端点看到的链路与线上不一致。
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.classifier = QueryClassifier()
        self._adaptive = None
        self._global = None
        self._drift = None

    def _get_adaptive(self):
        """获取 AdaptiveRetriever（实体优先，文本块兜底）"""
        if self._adaptive is None:
            from backend.service.kb.adaptive_retriever import AdaptiveRetriever
            self._adaptive = AdaptiveRetriever(self.user_id)
        return self._adaptive

    def _get_global(self):
        """获取 GlobalRetriever"""
        if self._global is None:
            self._global = GlobalRetriever(self.user_id)
        return self._global

    def _get_drift(self):
        """获取 DRIFTRetriever"""
        if self._drift is None:
            self._drift = DRIFTRetriever(self.user_id)
        return self._drift

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        query_type: Optional[str] = None,
        use_llm_classifier: bool = False
    ) -> Dict[str, Any]:
        """
        智能检索

        Args:
            query: 用户查询
            top_k: 返回数量
            query_type: 强制指定查询类型 (local/global/drift)；None 时自动判定
            use_llm_classifier: 仅在 query_type 强制为 local/global/drift 的旧路径下无效；
                自动判定已改为纯规则的总结型判定（零 LLM）

        Returns:
            {
                "query_type": "local/global/drift",
                "results": [...],  # local 为结果列表；global/drift 为 answer
                "answer": "...",   # global/drift
                "sources": [...],
                "retrieval_method": "entity_local"/"basic"/"global"/"drift"
            }
        """
        # 1. 分类查询（显式指定优先；否则用与主链路一致的纯规则分类）
        if query_type is None:
            from backend.service.kb.adaptive_retriever import (
                KIND_SUMMARY,
                classify_retrieval_kind,
            )

            query_type = (
                QueryType.GLOBAL
                if classify_retrieval_kind(query) == KIND_SUMMARY
                else QueryType.LOCAL
            )
            if use_llm_classifier:
                # 兼容参数：不再走 LLM 分类，保留入参只为不破坏既有调用
                logger.debug("[Smart] use_llm_classifier 已废弃，改用纯规则总结型判定")

        rag.info(f"[Smart] 查询分类: {query_type}")

        # 2. 路由到合适的检索器
        if query_type == QueryType.LOCAL:
            return self._retrieve_local(query, top_k)
        elif query_type == QueryType.GLOBAL:
            return self._retrieve_global(query)
        else:  # DRIFT
            return self._retrieve_drift(query)

    def _retrieve_local(self, query: str, top_k: int) -> Dict[str, Any]:
        """Local 检索：实体向量优先，文本块兜底（内部已完成数据层级过滤）"""
        adaptive = self._get_adaptive()
        out = adaptive.retrieve(query, top_k=top_k)

        return {
            "query_type": QueryType.LOCAL,
            "results": out.get("results", []),
            "sources": [
                r.get("document_title", "") for r in out.get("results", []) if r.get("document_title")
            ],
            "retrieval_method": out.get("method"),
            "seed_entities": out.get("seed_entities", []),
            "top1_entity_score": out.get("top1_entity_score"),
        }

    def _retrieve_global(self, query: str) -> Dict[str, Any]:
        """Global 检索"""
        global_ret = self._get_global()
        result = global_ret.retrieve(query)

        return {
            "query_type": QueryType.GLOBAL,
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "reports_used": result.get("reports_used", 0)
        }

    def _retrieve_drift(self, query: str) -> Dict[str, Any]:
        """DRIFT 检索"""
        drift = self._get_drift()
        result = drift.retrieve(query)

        return {
            "query_type": QueryType.DRIFT,
            "answer": result.get("answer", ""),
            "context": result.get("context", ""),
            "sources": result.get("communities_used", [])
        }


# ════════════════════════════════════════════════════════════
# 便捷函数
# ════════════════════════════════════════════════════════════

def smart_retrieve(
    user_id: int,
    query: str,
    top_k: int = 5,
    query_type: Optional[str] = None
) -> Dict[str, Any]:
    """智能检索便捷函数"""
    retriever = SmartRetriever(user_id)
    return retriever.retrieve(query, top_k, query_type)


def global_search(user_id: int, query: str) -> Dict[str, Any]:
    """全局搜索便捷函数"""
    retriever = GlobalRetriever(user_id)
    return retriever.retrieve(query)


def drift_search(user_id: int, query: str, top_k: int = 5) -> Dict[str, Any]:
    """DRIFT 搜索便捷函数"""
    retriever = DRIFTRetriever(user_id)
    return retriever.retrieve(query, top_k)
