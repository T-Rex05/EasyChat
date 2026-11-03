"""
记忆系统自适应检索器 —— 实体优先，记忆向量兜底（对应 docs/memory_adaptive_retrieval_design.md §12）

```
query ──► 意图分类（memory_type 过滤）
            │
            ├─ ① 记忆实体向量检索命中（余弦 ≥ RAG_ENTITY_STRONG_THRESHOLD）
            │      → Memory Local Search
            │         ├─ 种子实体 → source_memory_id（或 EXTRACTED_ENTITY 跨层边）
            │         ├─ KG 1 跳扩展 → 邻居实体及其来源记忆
            │         └─ 回捞记忆正文（解密 + user_id 归属校验）→ 多维 Rerank
            │
            └─ ② 未命中 → Memory Basic Search（现有记忆向量检索）
```

**记忆侧没有社区报告**（设计文档 §12.1）：社区检测跑在整张知识图谱上、产物是"知识主题"
而非"用户画像"，且记忆是用户私有的短片段，社区报告要跨文档的稳定结构才成立。
记忆的"主题"由 GraphMemory 的 SIMILAR_TO/FOLLOWS 边 + Rerank 精排承担。

与知识库侧的差异：
- 无 summary 分支（记忆没有社区报告）
- 内容是 `ENC:` 密文，回捞后必须解密（`decrypt_memory_content`）
- 可见性是 `user_id` 强隔离（不是部门层级）

日志规范（使用 `rag` logger）：
- rag.info()：正常流程（检索开始、完成、门控放行）
- rag.retrieval_fallback()：降级（实体未命中 → 记忆向量兜底）
- rag.warning()：异常但可恢复（图扩展失败）
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

from backend.db.schema import get_conn
from backend.utils.crypto_utils import decrypt_memory_content
from backend.utils.log_utils import log, rag

logger = log

METHOD_MEMORY_LOCAL = "memory_local"
METHOD_MEMORY_BASIC = "memory_basic"

# 邻居实体带来的记忆固定分（低于种子实体，保证排序稳定）
_NEIGHBOR_MEMORY_SCORE = 0.45
# 邻居实体图扩展跳数上限
_MAX_HOPS = 2


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ════════════════════════════════════════════════════════════
# 实体门控阈值（与知识库检索统一命名，但默认值不同）
# ════════════════════════════════════════════════════════════

# 记忆检索的特点：用户私有的短片段，单个实体关联的记忆可能就足够
# 因此使用更宽松的门控条件（min_strong=1，而不是知识库的 2）
ENTITY_STRONG_THRESHOLD_DEFAULT = 0.6  # 强命中阈值（与知识库一致）
ENTITY_MIN_STRONG_DEFAULT = 1          # 最少强实体数（记忆检索用更宽松的默认值）


def get_strong_threshold() -> float:
    """获取强命中阈值（统一环境变量：RAG_ENTITY_STRONG_THRESHOLD）"""
    return _env_float("RAG_ENTITY_STRONG_THRESHOLD", ENTITY_STRONG_THRESHOLD_DEFAULT)


def get_min_strong_entities() -> int:
    """获取最少强实体数（统一环境变量：RAG_ENTITY_MIN_STRONG）

    默认值为 1（记忆检索），知识库检索可以通过环境变量设置为 2。
    """
    return max(1, _env_int("RAG_ENTITY_MIN_STRONG", ENTITY_MIN_STRONG_DEFAULT))


def count_strong(entity_hits: Sequence[Dict[str, Any]]) -> int:
    """统计强命中实体数（≥ RAG_ENTITY_STRONG_THRESHOLD）"""
    threshold = get_strong_threshold()
    return sum(1 for h in entity_hits if float(h.get("score") or 0) >= threshold)


class AdaptiveMemoryRetriever:
    """
    记忆自适应检索器。

    使用方式：
        retriever = AdaptiveMemoryRetriever(memory_service)
        out = retriever.retrieve(user_id, query, top_k=8, memory_type="preference")
        # out = {"method", "results": [{memory, score, final_score, source}], "entities", "seed_entities"}
    """

    def __init__(self, memory_service: Any):
        self._service = memory_service

    # ── 主入口 ──────────────────────────────────────────────

    def retrieve(
        self,
        user_id: int,
        query: str,
        top_k: int = 8,
        memory_type: Optional[str] = None,
        candidate_k: int = 30,
    ) -> Dict[str, Any]:
        """
        自适应记忆检索：实体 local 优先，记忆向量兜底。

        Args:
            user_id: 用户 ID
            query: 查询文本
            top_k: 最终返回条数（Rerank 后）
            memory_type: 记忆类型过滤（preference/fact/event/skill）
            candidate_k: 兜底向量检索的候选池大小

        Returns:
            {"method": "memory_local"|"memory_basic", "results": [...],
             "entities": [...], "seed_entities": [...], "entity_hits": n,
             "top1_entity_score": float, "fallback_reason": str|None}
        """
        entity_hits = self._search_entities(user_id, query, memory_type)
        top1 = float(entity_hits[0]["score"]) if entity_hits else 0.0
        strong_count = count_strong(entity_hits)
        threshold = get_strong_threshold()
        min_strong = get_min_strong_entities()
        fallback_reason: Optional[str] = None

        # 门控判断：够用 → Memory Local Search
        confident = entity_hits and top1 >= threshold and strong_count >= min_strong
        if confident:
            local = self._memory_local_search(user_id, entity_hits, top_k)
            if local["results"]:
                rag.info(
                    f"✅ [Memory] Local Search（门控放行）: {len(entity_hits)} 实体 "
                    f"(strong={strong_count}, top1={top1:.3f} ≥ {threshold}) → {len(local['results'])} 条记忆"
                )
                local["top1_entity_score"] = round(top1, 6)
                local["entity_hits"] = len(entity_hits)
                return local
            rag.retrieval_fallback("memory_local", "memory_basic", "实体命中但未取到记忆")
            fallback_reason = "实体命中但未取到记忆（来源记忆已删除或不属于该用户）"
        elif not entity_hits:
            fallback_reason = "实体未命中"
        elif top1 < threshold:
            fallback_reason = f"实体分数不足 top1={top1:.3f} < {threshold}"
        elif strong_count < min_strong:
            fallback_reason = (
                f"强实体不足 strong={strong_count} < {min_strong} "
                f"（top1={top1:.3f} 属于单点擦边命中，来源记忆很可能不够答案）"
            )

        # 不够用 → Memory Basic Search（记忆向量检索兜底）
        basic = self._memory_basic_search(user_id, query, top_k, memory_type, candidate_k)
        rag.info(f"📊 [Memory] Basic Search（{fallback_reason}）: {len(basic['results'])} 条记忆")
        basic.update({
            "entities": [],
            "seed_entities": [],
            "entity_hits": len(entity_hits),
            "top1_entity_score": round(top1, 6),
            "fallback_reason": fallback_reason,
        })
        return basic

    # ── 实体检索 ────────────────────────────────────────────

    def _search_entities(
        self, user_id: int, query: str, memory_type: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        记忆实体向量检索（失败/不可用 → 空 → 走记忆向量兜底）。

        刻意**不按实体类型过滤**：记忆实体最典型的是 `用户(person)`、项目/技能等，
        按记忆意图（preference/skill/...）映射实体类型会把"用户"这类核心实体筛掉，
        反而降低召回。意图过滤留给兜底路径的 `memory_type`。
        """
        try:
            from backend.service.kb.entity_vectorstore import search_entities

            return search_entities(
                user_id,
                query,
                top_k=_env_int("MEMORY_TOP_K_ENTITIES", 10),
                scope="memory",
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Memory] 实体检索失败（降级记忆向量检索）: {e}")
            return []

    # ── Local Search ────────────────────────────────────────

    def _memory_local_search(
        self,
        user_id: int,
        entity_hits: List[Dict[str, Any]],
        top_k: int,
    ) -> Dict[str, Any]:
        """
        实体 → 记忆：种子实体直接带回来源记忆，邻居实体补充关联记忆，最后多维 Rerank。
        """
        seeds = [h for h in entity_hits if h.get("entity_id")]
        seed_entities = [h.get("entity_name") for h in seeds if h.get("entity_name")]

        memory_scores: Dict[int, float] = {}
        for rank, hit in enumerate(seeds):
            memory_id = int(hit.get("source_memory_id") or 0)
            if memory_id:
                score = float(hit.get("score") or 0) * max(0.1, 1.0 - 0.02 * rank)
                memory_scores[memory_id] = max(memory_scores.get(memory_id, 0.0), score)

        neighbors = self._expand_from_entities(user_id, [h["entity_id"] for h in seeds])
        for memory_id in neighbors["memory_ids"]:
            memory_scores[memory_id] = max(
                memory_scores.get(memory_id, 0.0), _NEIGHBOR_MEMORY_SCORE
            )

        if not memory_scores:
            return {
                "method": METHOD_MEMORY_LOCAL,
                "results": [],
                "entities": neighbors["entities"],
                "seed_entities": seed_entities,
            }

        memories = self._load_memories(user_id, list(memory_scores.keys()))
        candidates: List[Dict[str, Any]] = []
        for memory_id, score in memory_scores.items():
            memory = memories.get(memory_id)
            if not memory:
                continue
            candidates.append({
                "memory": memory,
                "score": round(float(score), 6),
                "source": METHOD_MEMORY_LOCAL,
                "entities": seed_entities[:3],
            })

        if not candidates:
            return {
                "method": METHOD_MEMORY_LOCAL,
                "results": [],
                "entities": neighbors["entities"],
                "seed_entities": seed_entities,
            }

        # 多维 Rerank（向量/重要性/新鲜度/访问频率）—— 与 Basic Search 同一套精排
        try:
            reranked = self._service.rerank_memories(candidates, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Memory] Rerank 失败，按原始分排序: {e}")
            candidates.sort(key=lambda c: c["score"], reverse=True)
            reranked = candidates[:top_k]

        return {
            "method": METHOD_MEMORY_LOCAL,
            "results": reranked,
            "entities": neighbors["entities"],
            "seed_entities": seed_entities,
            "relationships": neighbors["relationships"],
            "candidate_count": len(candidates),
        }

    def _expand_from_entities(self, user_id: int, entity_ids: Sequence[str]) -> Dict[str, Any]:
        """
        从记忆实体出发做图扩展：拿邻居实体，并收集"这些实体挂在哪条记忆上"。

        ⚠️ 记忆实体会被实体对齐合并进文档实体，合并后 `source_memory_id` 可能为空，
        因此必须同时读 `(m:Memory)-[:EXTRACTED_ENTITY]->(e)` 跨层边。
        """
        out: Dict[str, Any] = {"entities": [], "relationships": [], "memory_ids": []}
        if not entity_ids:
            return out

        try:
            from backend.graphrag.kg_store import get_kg_store

            kg_store = get_kg_store()
            if not kg_store.is_available():
                return out
            client = kg_store._get_graph_client()  # noqa: SLF001

            hops = max(1, min(int(_env_int("MEMORY_ENTITY_GRAPH_HOPS", 1)), _MAX_HOPS))
            limit = _env_int("RAG_GRAPH_EXPAND_LIMIT", 500)
            query = (
                f"MATCH (n)-[r*1..{hops}]-(m) "
                "WHERE n.id IN $ids AND m.id IS NOT NULL AND NOT m:Memory "
                "AND (m.source_document_id IS NULL AND m.user_id = $user_id) "
                "RETURN DISTINCT m.id AS id, m.name AS name, m.entity_type AS entity_type, "
                "m.description AS description, m.source_memory_id AS source_memory_id, "
                f"m.source_document_id AS source_document_id LIMIT {limit}"
            )
            rows = client.run_query(query, {"ids": list(entity_ids), "user_id": int(user_id)}) or []

            seen = {str(i) for i in entity_ids}
            memory_ids = set()
            for row in rows:
                eid = row.get("id")
                if not eid:
                    continue
                eid = str(eid)
                memory_id = int(row.get("source_memory_id") or 0)
                if memory_id:
                    memory_ids.add(memory_id)
                if eid in seen:
                    continue
                seen.add(eid)
                out["entities"].append({
                    "entity_id": eid,
                    "entity_name": row.get("name"),
                    "entity_type": row.get("entity_type"),
                    "description": (row.get("description") or "")[:200],
                })

            # 跨层边：邻居实体挂在哪条记忆上（含被对齐合并、source_memory_id 丢失的实体）
            if seen:
                edge_query = (
                    "MATCH (mem:Memory)-[:EXTRACTED_ENTITY]->(e) "
                    "WHERE e.id IN $ids AND mem.user_id = $user_id "
                    "RETURN DISTINCT mem.mem_id AS mem_id"
                )
                for row in client.run_query(edge_query, {"ids": list(seen), "user_id": int(user_id)}) or []:
                    mem_id = row.get("mem_id")
                    if mem_id:
                        memory_ids.add(int(mem_id))

            out["memory_ids"] = sorted(memory_ids)
            logger.debug(
                f"[Memory] 实体图扩展（hops={hops}）: {len(out['entities'])} 邻居实体, "
                f"{len(out['memory_ids'])} 条关联记忆"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Memory] 实体图扩展失败（仅用种子实体的来源记忆）: {e}")
        return out

    @staticmethod
    def _load_memories(user_id: int, memory_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
        """
        批量加载记忆正文（episodic + semantic）。

        ⚠️ 两道安全与正确性保障：
        1. 必须带 `user_id` 条件：两张表的 id 独立自增，只按 id 查会取到别的用户的记忆正文
        2. 内容在库里是 `ENC:` 密文，必须解密后再注入 prompt
        """
        if not memory_ids:
            return {}

        ids = [int(i) for i in memory_ids]
        result: Dict[int, Dict[str, Any]] = {}

        conn = get_conn()
        try:
            for layer, table in (("episodic", "memory_episodic"), ("semantic", "memory_semantic")):
                missing = [i for i in ids if i not in result]
                if not missing:
                    break
                marks = ",".join(["%s"] * len(missing))
                try:
                    cur = conn.execute(
                        f"SELECT id, user_id, memory_type, content, importance_score, access_count, "
                        f"created_at FROM {table} "
                        f"WHERE id IN ({marks}) AND deleted_at IS NULL AND user_id = %s",
                        tuple(missing) + (int(user_id),),
                    )
                    rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[Memory] 加载 {table} 失败: {e}")
                    continue
                for row in rows:
                    item = dict(row)
                    item["content"] = decrypt_memory_content(item.get("content") or "")
                    item["memory_layer"] = layer
                    result[int(item["id"])] = item
        finally:
            conn.close()
        return result

    # ── Basic Search（记忆向量检索兜底）─────────────────────

    def _memory_basic_search(
        self,
        user_id: int,
        query: str,
        top_k: int,
        memory_type: Optional[str],
        candidate_k: int,
    ) -> Dict[str, Any]:
        """记忆向量检索 + 多维 Rerank（现有实现，作为兜底路径）。"""
        results: List[Dict[str, Any]] = []
        try:
            results = self._service.hybrid_search(
                user_id=user_id,
                query=query,
                top_k=candidate_k,
                memory_type=memory_type,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Memory] 记忆向量检索失败: {e}")

        # 意图过滤后为空 → 回退到通用检索（不过滤类型）：宁可多召回，也不要空
        if not results and memory_type:
            try:
                results = self._service.hybrid_search(
                    user_id=user_id,
                    query=query,
                    top_k=candidate_k,
                    memory_type=None,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[Memory] 通用记忆检索失败: {e}")

        for item in results:
            item.setdefault("source", "vector")

        try:
            reranked = self._service.rerank_memories(results, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Memory] Rerank 失败，按原始分排序: {e}")
            reranked = sorted(results, key=lambda r: r.get("score", 0), reverse=True)[:top_k]

        return {"method": METHOD_MEMORY_BASIC, "results": reranked, "candidate_count": len(results)}
