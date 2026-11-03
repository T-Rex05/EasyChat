"""
Claim 向量存储

为 Claim 提供向量相似度搜索能力，类似于 entity_vectorstore。

索引内容：
- Claim 文本 (claim_text) 的向量表示
- 支持语义相似度搜索

向量库：
- Milvus collection `claim_user_{user_id}`，COSINE 度量
- Milvus 不可用时降级 Chroma

写入路径：
1. 文档图谱抽取完成 → vectorize_document_claims()
2. 存量补齐 → python -m backend.service.kb.claim_vectorstore --user-id N
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.utils.log_utils import log

logger = log

# ════════════════════════════════════════════════════════════
# 常量与配置
# ════════════════════════════════════════════════════════════

CLAIM_COLLECTION_PREFIX = "claim_user_"

# Claim 命中阈值（余弦相似度）
DEFAULT_CLAIM_THRESHOLD = 0.5
# 召回数量
DEFAULT_TOP_K_CLAIMS = 10
# 批大小
DEFAULT_EMBED_BATCH = 64

# 缓存
_store_cache: Dict[Tuple[int, str], Tuple[Any, str]] = {}
_store_lock = threading.Lock()
_store_locks: Dict[Tuple[int, str], threading.Lock] = {}
_STORE_CACHE_MAX = 32


class ClaimVectorStoreError(Exception):
    """Claim 向量库不可用"""


def get_claim_collection_name(user_id: int) -> str:
    """Claim 向量库的 collection 名"""
    return f"{CLAIM_COLLECTION_PREFIX}{int(user_id)}"


def _get_store(user_id: int) -> Tuple[Any, str]:
    """
    获取用户 Claim 向量库实例（Milvus 优先，Chroma 回退）

    Returns:
        (store_instance, store_type: "milvus" | "chroma")
    """
    from backend.infrastructure.milvus_client import get_milvus_client

    key = (user_id, "claim")

    with _store_lock:
        if key in _store_cache:
            return _store_cache[key]

        # 缓存清理：超过上限时移除最早的条目
        if len(_store_cache) >= _STORE_CACHE_MAX:
            oldest_key = next(iter(_store_cache))
            del _store_cache[oldest_key]
            logger.debug(f"[ClaimVector] Cache evicted: {oldest_key}")

        # Milvus 优先
        milvus = get_milvus_client()
        if milvus and milvus.is_available():
            collection_name = get_claim_collection_name(user_id)
            try:
                # 确保 collection 存在
                from pymilvus import Collection, DataType, FieldSchema, CollectionSchema

                # 动态获取向量维度
                from backend.rag.embeddings import get_embeddings
                embeddings = get_embeddings()
                if not embeddings:
                    raise ClaimVectorStoreError("Embeddings not configured")

                # 通过嵌入单个测试文本获取维度
                test_vector = embeddings.embed_query("test")
                vector_dim = len(test_vector)

                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                    FieldSchema(name="claim_text", dtype=DataType.VARCHAR, max_length=2048),
                    FieldSchema(name="subject", dtype=DataType.VARCHAR, max_length=256),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=vector_dim),
                ]
                schema = CollectionSchema(fields, description=f"Claim vectors for user {user_id}")

                if not milvus.has_collection(collection_name):
                    collection = milvus.create_collection(collection_name, schema)
                    # 创建向量索引
                    index_params = {
                        "metric_type": "COSINE",
                        "index_type": "IVF_FLAT",
                        "params": {"nlist": 128}
                    }
                    collection.create_index("embedding", index_params)
                else:
                    collection = Collection(collection_name)

                result = (collection, "milvus")
                _store_cache[key] = result
                return result

            except Exception as e:
                logger.warning(f"[ClaimVector] Milvus setup failed: {e}, fallback to Chroma")

        # 回退 Chroma
        try:
            from chromadb import Client as ChromaClient
            from backend.rag.config import get_rag_config

            config = get_rag_config()
            persist_dir = config.vector_persist_dir / f"claims_{user_id}"

            client = ChromaClient(persist_directory=str(persist_dir))
            collection = client.get_or_create_collection(
                name=f"claims_{user_id}",
                metadata={"hnsw:space": "cosine"}
            )
            result = (collection, "chroma")
            _store_cache[key] = result
            return result

        except Exception as e:
            logger.error(f"[ClaimVector] Chroma setup failed: {e}")
            raise ClaimVectorStoreError(f"Claim vector store unavailable: {e}")


def vectorize_claims(
    user_id: int,
    claims: Sequence[Dict[str, Any]],
    batch_size: int = DEFAULT_EMBED_BATCH,
) -> int:
    """
    向量化 Claim 列表

    Args:
        user_id: 用户 ID
        claims: Claim 数据列表，每项需包含 id, claim_text, subject
        batch_size: 批大小

    Returns:
        成功向量化的数量
    """
    if not claims:
        return 0

    try:
        from backend.rag.embeddings import get_embeddings
        embeddings = get_embeddings()
        if not embeddings:
            raise ClaimVectorStoreError("Embeddings not configured")

        store, store_type = _get_store(user_id)

        # 批量生成嵌入
        texts = [c.get("claim_text", "") for c in claims]
        vectors = embeddings.embed_documents(texts)

        if len(vectors) != len(claims):
            raise ClaimVectorStoreError("Embedding count mismatch")

        # 写入向量库
        ids = [c.get("id", "") for c in claims]
        subjects = [c.get("subject", "") for c in claims]

        if store_type == "milvus":
            from pymilvus import Collection
            collection = store
            data = [
                ids,
                [t[:2048] for t in texts],  # 截断
                [s[:256] for s in subjects],
                vectors
            ]
            collection.insert(data)
            collection.flush()

        else:  # chroma
            store.upsert(
                ids=ids,
                embeddings=vectors,
                documents=texts,
                metadatas=[{"subject": s, "user_id": user_id} for s in subjects]
            )

        logger.info(f"[ClaimVector] Vectorized {len(claims)} claims for user {user_id}")
        return len(claims)

    except ClaimVectorStoreError:
        raise
    except Exception as e:
        logger.error(f"[ClaimVector] Vectorization failed: {e}")
        return 0


def search_claims_by_vector(
    query: str,
    user_id: int,
    top_k: int = DEFAULT_TOP_K_CLAIMS,
    threshold: float = DEFAULT_CLAIM_THRESHOLD,
) -> List[Dict[str, Any]]:
    """
    向量相似度搜索 Claim

    Args:
        query: 查询文本
        user_id: 用户 ID
        top_k: 返回数量
        threshold: 相似度阈值

    Returns:
        [{id, claim_text, subject, score}, ...]
    """
    try:
        from backend.rag.embeddings import get_embeddings
        embeddings = get_embeddings()
        if not embeddings:
            # 回退到文本匹配
            return []

        store, store_type = _get_store(user_id)
        query_vector = embeddings.embed_query(query)

        results = []

        if store_type == "milvus":
            from pymilvus import Collection
            collection = store
            collection.load()

            search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
            hits = collection.search(
                data=[query_vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["id", "claim_text", "subject"]
            )

            for hit in hits[0]:
                if hit.distance >= threshold:
                    results.append({
                        "id": hit.entity.get("id"),
                        "claim_text": hit.entity.get("claim_text"),
                        "subject": hit.entity.get("subject"),
                        "score": hit.distance
                    })

        else:  # chroma
            query_result = store.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where={"user_id": user_id} if user_id else None
            )

            if query_result and query_result.get("ids"):
                for i, claim_id in enumerate(query_result["ids"][0]):
                    distance = query_result.get("distances", [[]])[0][i]
                    # Chroma 返回的是距离，需要转换为相似度
                    score = 1.0 - distance
                    if score >= threshold:
                        results.append({
                            "id": claim_id,
                            "claim_text": query_result.get("documents", [[]])[0][i],
                            "subject": query_result.get("metadatas", [[]])[0][i].get("subject", ""),
                            "score": score
                        })

        return results

    except ClaimVectorStoreError:
        return []
    except Exception as e:
        logger.warning(f"[ClaimVector] Vector search failed: {e}")
        return []


def delete_claim_vectors(
    user_id: int,
    claim_ids: Optional[List[str]] = None,
    document_id: Optional[int] = None,
) -> bool:
    """
    删除 Claim 向量

    Args:
        user_id: 用户 ID
        claim_ids: 要删除的 Claim ID 列表
        document_id: 文档 ID（删除该文档的所有 Claim）

    Returns:
        成功返回 True
    """
    try:
        store, store_type = _get_store(user_id)

        # 如果指定了 document_id，需要先查询相关 Claim
        if document_id and not claim_ids:
            from backend.graphrag.kg_store import get_kg_store
            kg_store = get_kg_store()
            # 查询文档的 Claim（使用专用方法，避免空字符串查询性能问题）
            claims = kg_store.get_claims_by_document(document_id, user_id=user_id)
            claim_ids = [c.id for c in claims]

        if not claim_ids:
            return True

        if store_type == "milvus":
            from pymilvus import Collection
            collection = store
            expr = f'id in {claim_ids}'
            collection.delete(expr)
            collection.flush()

        else:  # chroma
            store.delete(ids=claim_ids)

        logger.info(f"[ClaimVector] Deleted {len(claim_ids)} claim vectors for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"[ClaimVector] Delete failed: {e}")
        return False


def vectorize_document_claims(document_id: int, user_id: int) -> int:
    """
    向量化文档的所有 Claim

    Args:
        document_id: 文档 ID
        user_id: 用户 ID

    Returns:
        成功向量化的数量
    """
    try:
        from backend.graphrag.kg_store import get_kg_store
        kg_store = get_kg_store()

        # 查询文档的 Claim（使用专用方法）
        claims = kg_store.get_claims_by_document(document_id, user_id=user_id)

        if not claims:
            return 0

        claim_data = [
            {"id": c.id, "claim_text": c.claim_text, "subject": c.subject}
            for c in claims
        ]

        return vectorize_claims(user_id, claim_data)

    except Exception as e:
        logger.error(f"[ClaimVector] Failed to vectorize document claims: {e}")
        return 0


# ════════════════════════════════════════════════════════════
# CLI 入口（存量补齐）
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Claim Vector Store CLI")
    parser.add_argument("--user-id", type=int, required=True, help="User ID")
    parser.add_argument("--action", choices=["vectorize", "search"], default="vectorize")
    parser.add_argument("--query", type=str, help="Search query")
    args = parser.parse_args()

    if args.action == "search" and args.query:
        results = search_claims_by_vector(args.query, args.user_id)
        for r in results:
            print(f"- [{r['score']:.3f}] {r['claim_text'][:100]}")
    else:
        # 向量化该用户所有 Claim
        from backend.graphrag.kg_store import get_kg_store
        kg_store = get_kg_store()
        claims = kg_store.search_claims("", user_id=args.user_id, limit=10000)

        if claims:
            claim_data = [
                {"id": c.id, "claim_text": c.claim_text, "subject": c.subject}
                for c in claims
            ]
            count = vectorize_claims(args.user_id, claim_data)
            print(f"Vectorized {count} claims for user {args.user_id}")
        else:
            print(f"No claims found for user {args.user_id}")