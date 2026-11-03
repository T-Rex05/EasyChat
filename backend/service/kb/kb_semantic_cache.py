"""
语义缓存（Query-level Semantic Cache）

对用户 query 做 embedding，在 Redis 中缓存检索结果。
相似 query 命中缓存时直接返回，跳过整个检索管线（向量检索 + BM25 + RRF + Rerank + GraphRAG）。

与 Embedding 缓存的区别：
- Embedding 缓存（embeddings.py）：文本级，同一段文字不重复调 embedding API
- 语义缓存（本模块）：查询级，相似 query 命中直接跳过整个检索流程

缓存结构（Redis Hash，按 user_id 分片）：
  key: agentforge:kb:semantic_cache:{user_id}
  field: query_hash → {"embedding": [...], "result": {...}, "query": "...", "hits": int}
  TTL: 1 小时（可配置）

匹配逻辑：
  1. 对新 query 做 embedding
  2. 加载该用户缓存条目的 embedding
  3. 计算余弦相似度
  4. 最高分 >= threshold → 命中，返回缓存结果
  5. 否则 → 未命中，执行正常检索后写入缓存

租户隔离：缓存键包含 user_id，不同用户的缓存互不可见。
"""
import hashlib
import json
import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 3600          # 1 小时
_DEFAULT_THRESHOLD = 0.95    # 余弦相似度阈值
_MAX_CACHE_ENTRIES = 200     # 最大缓存条目数


def _cache_key(user_id: int) -> str:
    """按 user_id 分片的缓存键。"""
    return f"agentforge:kb:semantic_cache:{user_id}"


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """余弦相似度。"""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticCache:
    """
    语义缓存 — 相似 query 命中直接返回检索结果。

    用法：
        cache = SemanticCache()

        # 查缓存（user_id 必填，按用户分片）
        cached = cache.get(query_embedding, query_text, user_id)
        if cached:
            return cached

        # 写缓存
        cache.set(query_embedding, query_text, result_dict, user_id)
    """

    def __init__(
        self,
        ttl: int = _DEFAULT_TTL,
        threshold: float = _DEFAULT_THRESHOLD,
        max_entries: int = _MAX_CACHE_ENTRIES,
    ):
        self.ttl = ttl
        self.threshold = threshold
        self.max_entries = max_entries

    def _get_cache(self):
        from backend.infrastructure import get_cache
        return get_cache()

    def _query_hash(self, query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]

    def get(self, query_embedding: List[float], query_text: str, user_id: int) -> Optional[Dict[str, Any]]:
        """
        查缓存 — 返回最相似且超过阈值的结果，未命中返回 None。

        Args:
            query_embedding: query 的 embedding 向量
            query_text: 原始 query 文本
            user_id: 用户ID（用于租户隔离，必填 —— **不给默认值**，
                     漏传时应报错而不是静默共享一个全局桶）
        """
        try:
            cache = self._get_cache()
            cache_key = _cache_key(user_id)
            raw = cache.get(cache_key)
            if not raw:
                return None

            entries = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(entries, dict):
                return None

            best_sim = 0.0
            best_entry = None

            for qhash, entry in entries.items():
                emb = entry.get("embedding")
                if not emb:
                    continue
                sim = _cosine_sim(query_embedding, emb)
                if sim > best_sim:
                    best_sim = sim
                    best_entry = entry

            if best_entry and best_sim >= self.threshold:
                # ⚠️ 命中时**不回写**缓存：回写要调 cache.set(..., ttl=...)，
                # 而 Redis 的 setex 会**重置 TTL** → 形成滑动过期、条目可永不过期。
                # 命中计数因此不再持久化累积（它只用于 set() 时的淘汰排序），
                # 过期语义的正确性优先于淘汰质量。
                logger.info(
                    f"[SemanticCache] HIT sim={best_sim:.4f} "
                    f"user={user_id} query='{best_entry.get('query', '')[:50]}'"
                )
                return best_entry.get("result")

            return None
        except Exception as e:
            logger.debug(f"[SemanticCache] get 失败（不影响正常流程）: {e}")
            return None

    def set(
        self,
        query_embedding: List[float],
        query_text: str,
        result: Dict[str, Any],
        user_id: int,
    ) -> None:
        """
        写缓存 — 存储 query embedding + 检索结果。

        Args:
            query_embedding: query 的 embedding 向量
            query_text: 原始 query 文本
            result: 检索结果
            user_id: 用户ID（用于租户隔离，必填）
        """
        try:
            cache = self._get_cache()
            cache_key = _cache_key(user_id)
            raw = cache.get(cache_key)
            entries = {}
            if raw:
                entries = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(entries, dict):
                    entries = {}

            qhash = self._query_hash(query_text)
            entries[qhash] = {
                "embedding": query_embedding,
                "query": query_text[:200],
                "query_hash": qhash,
                "result": result,
                "hits": 0,
            }

            # 超限时淘汰命中最少的
            if len(entries) > self.max_entries:
                min_key = min(entries, key=lambda k: entries[k].get("hits", 0))
                del entries[min_key]

            cache.set(cache_key, json.dumps(entries, ensure_ascii=False), ttl=self.ttl)
            logger.debug(f"[SemanticCache] SET query='{query_text[:50]}'")
        except Exception as e:
            logger.debug(f"[SemanticCache] set 失败（不影响正常流程）: {e}")


def _embed_query(query: str) -> Optional[List[float]]:
    """对 query 做 embedding，失败返回 None。"""
    try:
        from backend.rag.embeddings import get_embeddings
        embeddings = get_embeddings()
        return embeddings.embed_query(query)
    except Exception as e:
        logger.debug(f"[SemanticCache] query embedding 失败: {e}")
        return None


def check_semantic_cache(query: str, user_id: int) -> Optional[Dict[str, Any]]:
    """
    检查语义缓存 — 返回缓存的检索结果或 None。

    在 dual_path_retrieve 入口处调用。

    Args:
        query: 用户查询文本
        user_id: 用户ID（必填，用于租户隔离）
    """
    emb = _embed_query(query)
    if emb is None:
        return None
    cache = SemanticCache()
    return cache.get(emb, query, user_id=user_id)


def write_semantic_cache(query: str, result: Dict[str, Any], user_id: int) -> None:
    """
    写入语义缓存 — 在 dual_path_retrieve 返回前调用。

    Args:
        query: 用户查询文本
        result: 检索结果
        user_id: 用户ID（必填，用于租户隔离）
    """
    emb = _embed_query(query)
    if emb is None:
        return
    cache = SemanticCache()
    cache.set(emb, query, result, user_id=user_id)
