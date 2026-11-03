"""
自适应检索器 —— 知识库检索的统一链路（对应 docs/adaptive_retrieval_design.md §10）

```
query ──► classify_retrieval_kind()
            ├─ summary  → 社区报告检索（Global Search / Map-Reduce）
            │              └─ 无报告或无答案 → 自动降级到 adaptive 链路
            └─ adaptive → ① 实体向量检索命中 → Local Search（实体 → 图扩展 → 文本块）
                          ② 实体检索失败     → Basic Search（文本块向量 + BM25 RRF）
```

设计要点：
- **实体优先**：实体描述向量库（entity_vectorstore）替代了旧图检索里"LLM 从 query 抽实体"
  这一步（旧路径每次检索都要一次 LLM 调用，且抽取失败即整条图路径失效）。
- **兜底必须存在**：实体库为空/未命中/不可用时，必须退化成文本块检索，不能返回空结果。
- **阈值有绝对语义**：实体库用 COSINE，`RAG_ENTITY_THRESHOLD`（默认 0.5）。
- **可见性**：文档实体按部门层级过滤（`_filter_by_scope_layer`），记忆实体按 `user_id`。

日志规范（使用 `rag` logger）：
- rag.info()：正常流程（检索开始、完成、门控放行）
- rag.retrieval_fallback()：降级（实体未命中 → 文本块兜底）
- rag.warning()：异常但可恢复（图扩展失败）
- rag.error()：严重错误（检索完全失败）
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Sequence

from backend.db.schema import get_conn
from backend.utils.log_utils import log, rag

logger = log

# ════════════════════════════════════════════════════════════
# 链路类型
# ════════════════════════════════════════════════════════════

KIND_SUMMARY = "summary"     # 总结型 → 社区报告
KIND_ADAPTIVE = "adaptive"   # 其他 → 实体 local → 文本块兜底

METHOD_GLOBAL = "global"           # 社区报告（Map-Reduce）
METHOD_ENTITY_LOCAL = "entity_local"  # 实体 local 检索
METHOD_BASIC = "basic"             # 文本块检索（Basic Search）

# 强总结信号：出现 1 个即可判为总结型
_SUMMARY_CORE = (
    "总结", "概括", "综述", "概述", "归纳", "梳理", "主旨", "大意",
    "讲了什么", "说了什么", "主要讲", "讲了啥", "脉络", "来龙去脉",
    "整体", "全局", "全面", "全景", "框架",
)

# 弱总结信号：需叠加（≥2 个）或长查询（>20 字）才判为总结型
# 注意：移除了 "哪些"、"全部" 等过于宽泛的词，避免把实体型问题误判为总结型
# 示例误判案例：
#   - "五虎上将是哪五将" → 原命中 "哪些" → 误判为总结型
#   - "关羽的武器是什么" → 原命中 "全部" → 误判为总结型
_SUMMARY_ANALYTIC = (
    "核心", "主题", "主要", "所有", "每个", "什么关系",
    "分析", "比较", "对比", "异同", "发展历程", "为什么", "原因", "意义",
    "影响", "趋势",
)


def classify_retrieval_kind(query: str) -> str:
    """
    判断检索链路：总结型（社区报告）还是自适应（实体 → 文本块）。

    纯规则、零 LLM 调用（延迟 < 1ms）。

    为什么不用 `graphrag_retriever.QueryClassifier`：
    它的 `_GLOBAL_PATTERNS` 含 "哪些/背景/有什么" 等宽泛词，`global_score >= 2` 即判 GLOBAL，
    会把 "五虎上将是哪五将，有什么故事背景" 这类**实体型问题**误判为全局问题
    （设计文档 §8.1 明确要求它走 Local Search）。这里只认强总结信号。
    """
    q = (query or "").strip().lower()
    if not q:
        return KIND_ADAPTIVE

    core_hits = [p for p in _SUMMARY_CORE if p in q]
    if core_hits:
        return KIND_SUMMARY

    analytic_hits = [p for p in _SUMMARY_ANALYTIC if p in q]
    if len(analytic_hits) >= 2:
        return KIND_SUMMARY
    if len(analytic_hits) == 1 and len(q) > 20:
        return KIND_SUMMARY

    return KIND_ADAPTIVE


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ════════════════════════════════════════════════════════════
# 实体门控：什么算"实体这次够用"
# ════════════════════════════════════════════════════════════

# 强命中阈值：单独一个 0.5~0.6 的实体往往是"擦边命中"，它的来源块够不到答案
# （实测："缓存雪崩怎么解决" 只有 1 个实体 ≥0.6 → 判不够，去补检才对）
ENTITY_STRONG_THRESHOLD_DEFAULT = 0.6
ENTITY_MIN_STRONG_DEFAULT = 2


def get_strong_threshold() -> float:
    return _env_float("RAG_ENTITY_STRONG_THRESHOLD", ENTITY_STRONG_THRESHOLD_DEFAULT)


def get_min_strong_entities() -> int:
    return max(1, _env_int("RAG_ENTITY_MIN_STRONG", ENTITY_MIN_STRONG_DEFAULT))


# ── 关系卡片触发信号（三档）──
_RELATION_STRONG = (
    "关系", "什么关系", "谁隶属", "隶属", "归属", "上级", "下属", "部下",
    "和谁", "与谁", "之间", "关联", "牵扯", "参与", "合作", "敌对", "对立",
    "谁负责", "谁管", "从属", "依附", "盟友", "仇敌", "师从", "手下",
)
_RELATION_WEAK = ("与", "和", "跟", "同", "对比", "区别", "相似")


def classify_relation_signal(query: str, seed_names: Optional[Sequence[str]] = None) -> str:
    """
    判定关系卡片档位：strong / weak / none。

    - strong：明确的关系型问法 → 注入"实体卡片 + 关系三元组"
    - weak：查询里同时出现 2 个以上已命中实体（如"A 和 B 怎么样"）→ 只注入实体卡片
    - none：默认不注入（省 token，也避免把抽取错误的关系塞给模型）
    """
    q = (query or "").strip()
    if not q:
        return "none"
    if any(p in q for p in _RELATION_STRONG):
        return "strong"
    if seed_names:
        hits = sum(1 for n in seed_names if n and n in q)
        if hits >= 2:
            return "weak"
        if hits >= 1 and any(p in q for p in _RELATION_WEAK):
            return "weak"
    return "none"


# 关系类型 → 中文（渲染关系卡片用；与 entity_vectorstore._REL_TEXT 同源语义）
_REL_CARD_TEXT = {
    "KNOWS": "认识", "KNOWS_ABOUT": "了解", "WORKS_WITH": "共事", "WORKS_AT": "就职于",
    "WORKS_ON": "参与", "MEMBER_OF": "隶属于", "REPORTS_TO": "汇报给", "OWNS": "负责",
    "USES": "使用", "PART_OF": "属于", "RELATED_TO": "相关", "CAUSED": "导致",
    "DEPENDS_ON": "依赖", "LEARNED": "学过", "FOUNDED": "创立", "PREFERS": "偏好",
    "DISLIKES": "不喜欢", "EXPERT_IN": "擅长", "HAPPENED_BEFORE": "早于",
    "HAPPENED_AFTER": "晚于", "INVOLVES": "涉及",
}


def build_relation_card(
    query: str,
    entities: Sequence[Dict[str, Any]],
    relationships: Sequence[Dict[str, Any]],
    max_edges: int = 10,
    max_entities: int = 5,
) -> Dict[str, Any]:
    """
    构建"知识图谱关系"卡片（按信号分档，不注入时返回 tier=none + 空 lines）。

    目的：关系型问题（"谁隶属于曹操""关羽和张飞什么关系"）用原文块答不好 ——
    关系散在多个块里；而图谱里本来就有 A --[REL]--> B。这里把它渲染成几行文本，
    作为**线索**附在资料头部（明确标注"冲突时以原文为准"，防止抽取错误带偏）。
    """
    tier = classify_relation_signal(query, [e.get("entity_name") for e in entities])
    if tier == "none":
        return {"tier": "none", "lines": []}

    lines: List[str] = []

    # 1) 实体卡片：名字（类型）+ 一句话描述 —— 让模型知道这是人/组织/表/字段
    for ent in list(entities)[:max_entities]:
        name = ent.get("entity_name")
        if not name:
            continue
        etype = ent.get("entity_type") or "other"
        desc = (ent.get("description") or "").strip()
        lines.append(f"- {name}（{etype}）{desc[:60]}".rstrip())

    # 2) 关系三元组：只有强信号才注入（避免普通查询被噪声关系干扰）
    if tier == "strong":
        seen = set()
        count = 0
        for rel in relationships:
            src = rel.get("source_entity_name")
            tgt = rel.get("target_entity_name")
            rtype = rel.get("relation_type") or ""
            if not src or not tgt:
                continue
            key = (src, rtype, tgt)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {src} --[{_REL_CARD_TEXT.get(rtype, rtype)}]--> {tgt}")
            count += 1
            if count >= max_edges:
                break

    return {"tier": tier, "lines": lines}


# ════════════════════════════════════════════════════════════
# 自适应检索器
# ════════════════════════════════════════════════════════════

class AdaptiveRetriever:
    """
    知识库自适应检索器。

    使用方式：
        retriever = AdaptiveRetriever(user_id)
        result = retriever.retrieve(query, top_k=10, kb_id=None, _user_layers=layers)
        # result = {"kind", "method", "results", "entities", "relationships", "seed_entities", ...}
    """

    def __init__(self, user_id: int):
        self.user_id = int(user_id)

    # ── 主入口 ──────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        kb_id: Optional[int] = None,
        mode: str = "hybrid",
        _user_layers: Optional[set] = None,
        enable_graph_expansion: bool = True,
        enable_entity: bool = True,
        entity_hits: Optional[List[Dict[str, Any]]] = None,
        require_confident: bool = False,
    ) -> Dict[str, Any]:
        """
        自适应检索：实体优先，文本块兜底。

        Args:
            query: 查询文本
            top_k: 返回文本块数量
            kb_id: 知识库 ID（None = 全部）
            mode: 兜底路径的检索模式（hybrid/bm25/vector）
            _user_layers: 预取的用户层级（避免重复查库）
            enable_graph_expansion: 是否做实体图扩展（**只有主查询该开**：换措辞不改变邻居集合）
            enable_entity: 是否做实体检索（False = 只走文本块）
            entity_hits: 复用上层已算好的实体命中（避免同一查询重复 embedding + Milvus）
            require_confident: True 时"不够"也返回（由上层决定融合），False 时"够"直接返回

        Returns:
            {
                "kind": "adaptive",
                "method": "entity_local" | "basic" | "entity_local+basic",
                "confident": bool,            # 实体门控是否放行（= 可以直接返回实体块）
                "results": [...],             # 本方法内部的最终列表
                "routes": {"entity_local": [...], "basic": [...]},  # 各路原始有序列表
                "entities": [...], "relationships": [...], "relation_card": {...},
                "seed_entities": [...], "entity_hits": n, "strong_entity_count": n,
                "top1_entity_score": float, "fallback_reason": str | None,
                "elapsed_ms": int,
            }
        """
        started = time.monotonic()

        entity_hits = list(entity_hits) if entity_hits is not None else (
            self.search_entities(query) if enable_entity else []
        )
        top1 = float(entity_hits[0]["score"]) if entity_hits else 0.0
        strong_count = self.count_strong(entity_hits)
        threshold = self._entity_threshold()
        min_strong = get_min_strong_entities()
        fallback_reason: Optional[str] = None

        local: Dict[str, Any] = {"results": [], "entities": [], "relationships": []}
        if entity_hits and top1 >= threshold:
            local = self._entity_local_search(
                query, entity_hits, top_k, kb_id=kb_id,
                _user_layers=_user_layers, expand=enable_graph_expansion,
            )

        # ── 实体门控：够 → 直接返回实体关联的原文块（不改写、不跑分片检索）──
        confident = bool(local["results"]) and top1 >= get_strong_threshold() and strong_count >= min_strong
        if confident:
            rag.info(
                f"✅ [Adaptive] Entity Local Search（门控放行）: {len(entity_hits)} 实体, "
                f"strong={strong_count}, top1={top1:.3f} ≥ {get_strong_threshold()} "
                f"→ {len(local['results'])} 文本块，跳过改写/分片检索"
            )
            return self._pack(
                query, method=METHOD_ENTITY_LOCAL, confident=True,
                routes={"entity_local": local["results"]},
                results=local["results"], local=local,
                entity_hits=entity_hits, strong_count=strong_count, top1=top1,
                fallback_reason=None, started=started,
            )

        # ── 不够 → 实体块（可能为空）与文本块兜底都留下，交给上层统一 RRF 融合 ──
        if not entity_hits:
            fallback_reason = "实体未命中"
        elif top1 < threshold:
            fallback_reason = f"实体分数不足 top1={top1:.3f} < {threshold}"
        elif strong_count < min_strong:
            fallback_reason = (
                f"强实体不足 strong={strong_count} < {min_strong}"
                f"（top1={top1:.3f} 属于单点擦边命中，来源块很可能够不到答案）"
            )
        else:
            fallback_reason = "实体命中但未取到文本块（来源文本块已删除或不属于该知识库）"

        basic = self._basic_search(query, top_k, kb_id=kb_id, mode=mode, _user_layers=_user_layers)
        routes = {"entity_local": local["results"], "basic": basic["results"]}
        merged = self._fuse_routes(routes, top_k)
        rag.info(
            f"📊 [Adaptive] Entity+Basic（{fallback_reason}）: "
            f"实体块={len(local['results'])}, 文本块={len(basic['results'])}, 融合后={len(merged)}"
        )
        return self._pack(
            query, method=f"{METHOD_ENTITY_LOCAL}+{METHOD_BASIC}", confident=False,
            routes=routes, results=merged, local=local,
            entity_hits=entity_hits, strong_count=strong_count, top1=top1,
            fallback_reason=fallback_reason, started=started,
        )

    # ── 组装返回体 ──────────────────────────────────────────

    def _pack(
        self,
        query: str,
        method: str,
        confident: bool,
        routes: Dict[str, List[dict]],
        results: List[dict],
        local: Dict[str, Any],
        entity_hits: List[Dict[str, Any]],
        strong_count: int,
        top1: float,
        fallback_reason: Optional[str],
        started: float,
    ) -> Dict[str, Any]:
        seed_names = [e.get("entity_name") for e in local.get("entities", []) if e.get("entity_name")]
        card = build_relation_card(
            query=query,
            entities=local.get("entities", []),
            relationships=local.get("relationships", []),
        )
        return {
            "kind": KIND_ADAPTIVE,
            "method": method,
            "confident": confident,
            "results": results,
            "routes": routes,
            "entities": local.get("entities", []),
            "relationships": local.get("relationships", []),
            "claims": local.get("claims", []),  # 新增：Claim 列表
            "relation_card": card,
            "seed_entities": seed_names,
            "entity_hits": len(entity_hits),
            "strong_entity_count": strong_count,
            "top1_entity_score": round(top1, 6),
            "fallback_reason": fallback_reason,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    @staticmethod
    def _fuse_routes(routes: Dict[str, List[dict]], top_k: int) -> List[dict]:
        """把各路（实体 / 文本块）按 RRF 融合：**同 chunk 去重成一条**，被多路命中则分数叠加。"""
        lists = [(name, items) for name, items in routes.items() if items]
        if not lists:
            return []
        if len(lists) == 1:
            return list(lists[0][1])[:top_k]
        try:
            from backend.service.kb.kb_retriever import _rrf_fuse_multi_query

            return _rrf_fuse_multi_query(lists, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Adaptive] 路由融合失败，退化为拼接去重: {e}")
            seen, out = set(), []
            for _name, items in lists:
                for r in items:
                    cid = r.get("chunk_id")
                    if cid is not None and cid in seen:
                        continue
                    if cid is not None:
                        seen.add(cid)
                    out.append(r)
            return out[:top_k]

    # ── 总结型：社区报告检索 ─────────────────────────────────

    def community_report_search(self, query: str, max_reports: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        社区报告检索（总结型查询专用）。

        Args:
            query: 查询文本
            max_reports: Map 阶段最多用多少份报告（默认 RAG_GLOBAL_MAX_REPORTS=15；
                每份报告一次 LLM 调用，Map 已并发执行，但仍需限制总量控制延迟）

        Returns:
            {"query_type": "global", "answer": str, "sources": [...],
              "reports_used": n, "method": "global"} 或 None（无报告/无答案 → 调用方降级）
        """
        if not self._has_community_reports():
            logger.debug("[Adaptive] 无社区报告，跳过社区报告检索")
            return None

        if max_reports is None:
            # 默认 5 份：实测 Map 阶段（并发 5）单波 ~12s，且 5 份相关报告的 Reduce
            # 已能产出结构完整的总结（更多报告只增加尾部延迟，不显著提升答案质量）
            max_reports = _env_int("RAG_GLOBAL_MAX_REPORTS", 5)
        workers = _env_int("RAG_GLOBAL_MAP_WORKERS", 5)

        started = time.monotonic()
        try:
            from backend.service.kb.graphrag_retriever import GlobalRetriever

            retriever = GlobalRetriever(self.user_id, map_workers=workers)

            # ★ 社区报告检索（而不是"把所有报告都 Map 一遍"）：
            #   按 query 与报告摘要的语义相似度先选最相关的 N 份，再对它们做 Map-Reduce。
            #   收益：① 相关性更高（无关报告本来会被 Map 判成"无关"）② LLM 调用量可控。
            reports = retriever._get_all_reports()  # noqa: SLF001 —— 与 retrieve 同源
            selected = self._select_reports(query, reports, max_reports)

            result = retriever.retrieve(query, max_reports=max_reports, reports=selected)
            answer = (result.get("answer") or "").strip()
            reports_used = int(result.get("reports_used") or 0)

            # ⚠️ GlobalRetriever 在"没有报告"或"所有报告都判为无关"时会返回**非空但无信息量**
            # 的兜底文案（"无法从社区报告中提取相关信息"），只判 answer 非空会把这种
            # "假成功"当成真结果，导致总结型查询拿到一句废话且不再降级。
            # reports_used 才是有没有真正 Map 出片段的可靠信号。
            if not answer or reports_used <= 0:
                logger.info(
                    f"[Adaptive] 社区报告未产出有效片段（reports_used={reports_used}），降级自适应链路"
                )
                return None

            rag.info(
                f"🌐 [Adaptive] Global Search（社区报告）: {reports_used} 份报告, "
                f"{len(answer)} 字, {int((time.monotonic() - started) * 1000)}ms"
            )
            return {
                "query_type": "global",
                "method": METHOD_GLOBAL,
                "answer": answer,
                "sources": result.get("sources", []),
                "reports_used": reports_used,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Adaptive] 社区报告检索失败，降级自适应检索: {e}")
            return None

    def _select_reports(
        self,
        query: str,
        reports: List[Dict[str, Any]],
        top_n: int,
    ) -> List[Dict[str, Any]]:
        """
        社区报告检索：按 query 与报告（标题+摘要）的语义相似度选最相关的 top_n 份。

        失败（embedding 不可用等）→ 退回"原顺序取前 top_n"（保证一定可用）。
        """
        if not reports or len(reports) <= top_n:
            return list(reports)

        try:
            from backend.rag.embeddings import get_embeddings

            embeddings = get_embeddings()
            query_vec = embeddings.embed_query(query)
            texts = [
                f"{r.get('title') or ''}。{r.get('summary') or ''}"
                for r in reports
            ]
            doc_vecs = embeddings.embed_documents(texts)

            scored = []
            for report, vec in zip(reports, doc_vecs):
                scored.append((self._cosine(query_vec, vec), report))
            scored.sort(key=lambda item: item[0], reverse=True)

            selected = [report for _, report in scored[:top_n]]
            logger.info(
                f"📚 [Adaptive] 社区报告检索: {len(reports)} 份 → 选取 {len(selected)} 份 "
                f"(top1 相似度={scored[0][0]:.3f}, 标题={selected[0].get('title')!r})"
            )
            return selected
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Adaptive] 报告相关性预筛失败，按原顺序取前 {top_n} 份: {e}")
            return list(reports[:top_n])

    @staticmethod
    def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
        """余弦相似度（长度不一致或空向量返回 0）。"""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _has_community_reports(self) -> bool:
        """该用户是否有已生成的社区报告（粗粒度判断，避免无谓的 LLM 开销）。"""
        try:
            conn = get_conn()
            try:
                cur = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM kg_community_reports r "
                    "JOIN kg_communities c ON r.community_id = c.id "
                    "WHERE c.user_id = %s AND r.status = 'completed'",
                    (self.user_id,),
                )
                rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                return bool(rows and rows[0].get("cnt"))
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            return False

    # ── 实体检索 ────────────────────────────────────────────

    def _entity_threshold(self) -> float:
        from backend.service.kb.entity_vectorstore import get_entity_threshold

        return get_entity_threshold()

    def search_entities(self, query: str) -> List[Dict[str, Any]]:
        """实体描述向量检索（失败/不可用时返回空 → 自动走文本块兜底）。"""
        try:
            from backend.service.kb.entity_vectorstore import search_entities

            return search_entities(self.user_id, query, scope="all")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Adaptive] 实体检索失败（降级文本块）: {e}")
            return []

    @staticmethod
    def count_strong(entity_hits: Sequence[Dict[str, Any]]) -> int:
        """统计"强命中"实体数（≥ RAG_ENTITY_STRONG_THRESHOLD，默认 0.6）。"""
        strong = get_strong_threshold()
        return sum(1 for h in entity_hits if float(h.get("score") or 0) >= strong)

    def is_confident(self, entity_hits: Sequence[Dict[str, Any]]) -> bool:
        """
        实体门控判定：实体这条路"够不够用"。

        够 = 至少 `RAG_ENTITY_MIN_STRONG`（默认 2）个强命中实体。
        为什么不是"top1 过阈值就够"：单个擦边命中（0.5~0.6）说明 query 只蹭到了一个实体的
        描述，而该实体只能提供它自己 source_chunk_id 那一块 —— 答案若在同文档其他块就够不到，
        所以单点命中要判"不够"，去走补检。
        """
        return self.count_strong(entity_hits) >= get_min_strong_entities()

    @property
    def _with_relations(self) -> bool:
        """关系卡片是否可用（Neo4j 不可用时不必白跑扩展）。"""
        try:
            from backend.graphrag.kg_store import get_kg_store

            return get_kg_store().is_available()
        except Exception:  # noqa: BLE001
            return False

    def _entity_local_search(
        self,
        query: str,
        entity_hits: List[Dict[str, Any]],
        top_k: int,
        kb_id: Optional[int],
        _user_layers: Optional[set],
        expand: bool = True,
    ) -> Dict[str, Any]:
        """
        Local Search：实体 → 图扩展 → 文本块 + Claim。

        1. 种子实体（向量命中的实体）→ 自身 `source_chunk_id`
        2. 图扩展（1 跳）→ 邻居实体的 `source_chunk_id`
        3. 回捞文本块 → 数据层级过滤 → 按实体相似度排序
        4. **Claim 检索**：基于种子实体名称检索相关 Claim
        """
        seed_entities = [h for h in entity_hits if h.get("entity_name")]
        entities_out = [self._entity_brief(h) for h in seed_entities]
        relationships: List[Dict[str, Any]] = []

        chunk_scores: Dict[int, float] = {}
        for rank, hit in enumerate(seed_entities):
            chunk_id = int(hit.get("source_chunk_id") or 0)
            # 命中实体本身附带的来源文本块：分数 = 实体相似度 × 排名衰减（下限 0.1，防负数）
            if chunk_id:
                score = float(hit.get("score") or 0) * max(0.1, 1.0 - 0.02 * rank)
                chunk_scores[chunk_id] = max(chunk_scores.get(chunk_id, 0.0), score)

        if expand:
            expanded = self._expand_from_entities([h["entity_id"] for h in seed_entities if h.get("entity_id")])
            for item in expanded["entities"]:
                entities_out.append(item)
            relationships = expanded["relationships"]
            for chunk_id, score in expanded["chunk_scores"].items():
                chunk_scores[chunk_id] = max(chunk_scores.get(chunk_id, 0.0), score)

        if not chunk_scores:
            return {
                "method": METHOD_ENTITY_LOCAL,
                "results": [],
                "entities": entities_out,
                "relationships": relationships,
                "seed_entities": [h["entity_name"] for h in seed_entities],
                "entity_hits": len(entity_hits),
                "top1_entity_score": round(float(seed_entities[0]["score"]), 6) if seed_entities else 0.0,
            }

        max_chunks = max(top_k * 3, _env_int("RAG_ENTITY_MAX_CHUNKS", 30))
        ranked = sorted(chunk_scores.items(), key=lambda kv: kv[1], reverse=True)[:max_chunks]
        chunk_ids = [cid for cid, _ in ranked]

        chunks = self._load_chunks(chunk_ids)
        if kb_id is not None:
            chunks = self._filter_chunks_by_kb(chunks, int(kb_id))

        results: List[dict] = []
        for chunk_id, score in ranked:
            chunk = chunks.get(chunk_id)
            if not chunk:
                continue
            results.append({
                "chunk_id": int(chunk_id),
                "document_id": chunk.get("document_id"),
                "content": chunk.get("content") or "",
                # score 会被后续多查询 RRF 融合覆盖（融合分只有 0.0x 量级），
                # 因此额外保留实体余弦分 entity_score 供质量评估与展示使用
                "score": round(float(score), 6),
                "entity_score": round(float(score), 6),
                "kind": chunk.get("kind") or "base",
                "retrieval_source": METHOD_ENTITY_LOCAL,
            })

        # ★ child→parent 归一化：实体链路的 source_chunk_id 通常是父片，但历史/异常数据里
        #   可能是子片 id；统一归一化到父片，才能与"分片检索"落在同一个 id 空间，
        #   否则同一段文本会以两个 id 出现，去重直接失效（重复资料进 prompt）。
        results = self._normalize_to_parent(results)

        # 数据层级过滤（安全边界：只返回用户可见层级的数据）
        results = self._filter_by_scope_layer(results, _user_layers)

        # ════════════════════════════════════════════════════════════
        # Claim 检索：基于种子实体名称批量检索相关 Claim（避免 N+1 查询）
        # ════════════════════════════════════════════════════════════
        claims = []
        try:
            from backend.graphrag.kg_store import get_kg_store
            kg_store = get_kg_store()

            # 收集所有种子实体名称
            entity_names = []
            for h in seed_entities:
                name = h.get("entity_name")
                if name:
                    entity_names.append(name)

            # 批量检索 Claim（一次查询，避免 N+1）
            if entity_names:
                entity_claims = kg_store.get_claims_by_entities(
                    entity_names,
                    user_id=self.user_id,
                    limit=10
                )
                for claim in entity_claims:
                    claims.append({
                        "id": claim.id,
                        "claim_text": claim.claim_text,
                        "claim_type": claim.claim_type.value,
                        "subject": claim.subject,
                        "object": claim.object,
                        "claim_value": claim.claim_value,
                        "time": claim.time,
                        "confidence": claim.confidence,
                    })

                if claims:
                    # 按置信度排序，限制数量
                    claims = sorted(claims, key=lambda c: c["confidence"], reverse=True)[:10]
                    rag.info(f"[Claim] Retrieved {len(claims)} claims for {len(entity_names)} entities")

        except Exception as e:
            rag.warning(f"Failed to retrieve claims: {e}")

        return {
            "method": METHOD_ENTITY_LOCAL,
            "results": results[:top_k],
            "entities": entities_out,
            "relationships": relationships,
            "claims": claims,  # 新增：Claim 列表
            "seed_entities": [h["entity_name"] for h in seed_entities],
            "entity_hits": len(entity_hits),
            "top1_entity_score": round(float(seed_entities[0]["score"]), 6) if seed_entities else 0.0,
        }

    @staticmethod
    def _normalize_to_parent(results: List[dict]) -> List[dict]:
        """子片 → 父片（chunk_id/content 都换成父片），再按父片去重。"""
        if not results:
            return results
        try:
            from backend.service.kb.kb_retriever import (
                _dedup_by_parent,
                _enrich_with_parent_content,
            )

            return _dedup_by_parent(_enrich_with_parent_content(results))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Adaptive] 父片归一化失败（保持原样）: {e}")
            return results

    def _expand_from_entities(self, entity_ids: Sequence[str]) -> Dict[str, Any]:
        """
        从种子实体做 1 跳图扩展，收集邻居实体与其来源文本块。

        直接用 Cypher 批量查询（避免逐实体 N+1），并复用 kg_store 的可见性谓词。
        """
        out: Dict[str, Any] = {"entities": [], "relationships": [], "chunk_scores": {}}
        if not entity_ids:
            return out

        try:
            from backend.graphrag.kg_store import get_kg_store

            kg_store = get_kg_store()
            if not kg_store.is_available():
                return out
            client = kg_store._get_graph_client()  # noqa: SLF001

            hops = max(1, min(_env_int("RAG_ENTITY_GRAPH_HOPS", 1), 2))
            vis = kg_store._vis_pred("m")  # noqa: SLF001 —— 与图谱检索同源的可见性谓词
            params = {"ids": list(entity_ids), **kg_store._vis_params(self.user_id)}  # noqa: SLF001

            query = (
                "MATCH (n)-[r]-(m) "
                "WHERE n.id IN $ids AND m.id IS NOT NULL AND NOT m:Memory "
                f"AND {vis} "
                "RETURN n.id AS source_id, n.name AS source_name, "
                "m.id AS id, m.name AS name, m.entity_type AS entity_type, "
                "m.description AS description, m.source_chunk_id AS source_chunk_id, "
                "type(r) AS relation_type, coalesce(r.weight, 1.0) AS weight "
                f"LIMIT {_env_int('RAG_GRAPH_EXPAND_LIMIT', 500)}"
            )
            rows = client.run_query(query, params) or []

            seed_names = {str(i): "" for i in entity_ids}
            seen_entity = {str(i) for i in entity_ids}
            for row in rows:
                eid = row.get("id")
                if not eid:
                    continue
                eid = str(eid)
                src_id = row.get("source_id")
                if src_id is not None:
                    seed_names[str(src_id)] = row.get("source_name") or ""
                chunk_id = row.get("source_chunk_id")
                if eid not in seen_entity:
                    seen_entity.add(eid)
                    out["entities"].append({
                        "entity_id": eid,
                        "entity_name": row.get("name"),
                        "entity_type": row.get("entity_type"),
                        "description": (row.get("description") or "")[:200],
                        "source_chunk_id": int(chunk_id) if chunk_id is not None else 0,
                    })
                # 完整三元组：A --[REL]--> B（旧实现丢了 source 端，关系卡片没法渲染）
                out["relationships"].append({
                    "source_entity_id": str(src_id) if src_id is not None else None,
                    "source_entity_name": row.get("source_name"),
                    "target_entity_id": eid,
                    "target_entity_name": row.get("name"),
                    "relation_type": row.get("relation_type"),
                    "weight": float(row.get("weight") or 1.0),
                })
                if chunk_id:
                    # 邻居实体的文本块：给一个略低于种子实体的固定分（0.45），保证排序稳定
                    out["chunk_scores"][int(chunk_id)] = max(
                        out["chunk_scores"].get(int(chunk_id), 0.0), 0.45
                    )

            logger.debug(
                f"[Adaptive] 实体图扩展（hops={hops}）: {len(out['entities'])} 邻居实体, "
                f"{len(out['chunk_scores'])} 文本块"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Adaptive] 实体图扩展失败（仅用种子实体的文本块）: {e}")
        return out

    @staticmethod
    def _entity_brief(hit: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "entity_id": hit.get("entity_id"),
            "entity_name": hit.get("entity_name"),
            "entity_type": hit.get("entity_type"),
            "description": (hit.get("description") or "")[:200],
            "score": hit.get("score"),
            "source_chunk_id": hit.get("source_chunk_id") or 0,
        }

    # ── 文本块兜底（Basic Search）───────────────────────────

    def _basic_search(
        self,
        query: str,
        top_k: int,
        kb_id: Optional[int],
        mode: str = "hybrid",
        _user_layers: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        文本块检索兜底：向量 + BM25（RRF 融合）。

        说明：hybrid 模式走 `HybridRetriever(skip_graph=True)` —— 只融合文本块两路，
        不触发 LLM 实体抽取的图检索（那正是 entity_local 要替代的昂贵路径）。
        """
        from backend.service.kb.kb_retriever import BM25Retriever, VectorRetriever

        def _bm25():
            return BM25Retriever(self.user_id, kb_id=kb_id).retrieve(
                query, top_k, _user_layers=_user_layers
            )

        try:
            if mode == "bm25":
                results = _bm25()
                source = "bm25"
            elif mode == "vector":
                results = VectorRetriever(self.user_id, kb_id=kb_id).retrieve(
                    query, top_k, _user_layers=_user_layers
                )
                source = "vector"
                if not results:
                    # 向量路空结果（无向量/embedding 不可用）→ 词法路兜底
                    results = _bm25()
                    source = "bm25"
            else:
                from backend.service.kb.kb_retriever import HybridRetriever

                results = HybridRetriever(self.user_id, kb_id=kb_id).retrieve(
                    query, top_k, skip_graph=True, _user_layers=_user_layers
                )
                source = "hybrid"
                if not results:
                    results = _bm25()
                    source = "bm25"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Adaptive] 文本块检索失败（{mode}），降级 BM25: {e}")
            results = []
            source = mode
            try:
                results = _bm25()
                source = "bm25"
            except Exception as e2:  # noqa: BLE001
                logger.warning(f"[Adaptive] BM25 兜底也失败: {e2}")

        for r in results:
            r.setdefault("retrieval_source", source)

        return {"method": METHOD_BASIC, "results": results, "basic_source": source}

    # ── 数据加载与过滤 ──────────────────────────────────────

    @staticmethod
    def _load_chunks(chunk_ids: Sequence[int]) -> Dict[int, dict]:
        """批量回捞文本块（id → {id, document_id, content, kind}）。"""
        if not chunk_ids:
            return {}
        conn = get_conn()
        try:
            placeholders = ",".join(["%s"] * len(chunk_ids))
            cur = conn.execute(
                f"SELECT id, document_id, content, kind FROM kb_chunks WHERE id IN ({placeholders})",
                tuple(int(c) for c in chunk_ids),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return {int(r["id"]): dict(r) for r in rows}
        finally:
            conn.close()

    @staticmethod
    def _filter_chunks_by_kb(chunks: Dict[int, dict], kb_id: int) -> Dict[int, dict]:
        """
        按知识库过滤文本块（兼容 kb_chunks.kb_id 为空、靠文档兜底的历史数据）。

        ★ 默认知识库特例：`kb_documents.kb_id IS NULL` 的文档语义上属于默认知识库，
        查该库时要一并纳入（否则那些文档在 chat 路径里永远检索不到）。
        """
        if not chunks:
            return {}
        from backend.service.kb.kb_retriever import is_default_kb

        allow_null = is_default_kb(kb_id)
        conn = get_conn()
        try:
            placeholders = ",".join(["%s"] * len(chunks))
            cur = conn.execute(
                f"SELECT c.id, COALESCE(c.kb_id, d.kb_id) AS kb_id FROM kb_chunks c "
                f"LEFT JOIN kb_documents d ON d.id = c.document_id "
                f"WHERE c.id IN ({placeholders})",
                tuple(chunks.keys()),
            )
            allowed = set()
            for r in (cur.fetchall() if hasattr(cur, "fetchall") else []):
                eff = r.get("kb_id")
                if eff is None:
                    if allow_null:
                        allowed.add(int(r["id"]))
                elif int(eff) == int(kb_id):
                    allowed.add(int(r["id"]))
            return {cid: chunk for cid, chunk in chunks.items() if cid in allowed}
        finally:
            conn.close()

    def _filter_by_scope_layer(
        self, results: List[dict], _user_layers: Optional[set]
    ) -> List[dict]:
        """数据层级过滤（复用 kb_retriever 的安全边界实现）。"""
        if not results:
            return results
        try:
            from backend.service.kb.kb_retriever import _filter_by_scope_layer

            return _filter_by_scope_layer(results, self.user_id, _user_layers=_user_layers)
        except Exception as e:  # noqa: BLE001
            # fail-closed：层级过滤不可用时宁可丢结果，也不让不可见数据进 LLM
            logger.warning(f"[Adaptive] 层级过滤异常 → 丢弃本批结果（fail-closed）: {e}")
            return []


# ════════════════════════════════════════════════════════════
# 便捷函数
# ════════════════════════════════════════════════════════════

def adaptive_retrieve(
    user_id: int,
    query: str,
    top_k: int = 10,
    kb_id: Optional[int] = None,
    mode: str = "hybrid",
) -> Dict[str, Any]:
    """自适应检索便捷函数（不走 dual_path 的轻量入口，主要用于测试/工具）。"""
    return AdaptiveRetriever(user_id).retrieve(query, top_k=top_k, kb_id=kb_id, mode=mode)
