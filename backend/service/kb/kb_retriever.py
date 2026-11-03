"""
知识库检索器 — 向量检索（Milvus 每用户 collection，降级 Chroma）+ BM25 兜底 + Rerank 精排

设计：
- 向量化：kb_chunks → embedding → Milvus collection `kb_user_{uid}`（metadata: chunk_id/document_id/user_id/kb_id）
- 检索：auto 模式优先向量检索（要求 embedding 服务已配置且该用户有向量），否则 BM25（零外部依赖）
- BM25 索引懒构建 + 签名缓存（chunk 数量/最大 id 变化即重建）
- Rerank：可选的精排（从数据库 model_configs 表读取 category='rerank' 的激活配置）

**Redis 缓存**：
- Rerank 配置：10 分钟 TTL
- 用户向量存在性：1 分钟 TTL

配置（前端模型配置页面）：
- Embedding 模型：category='embedding'，用于知识库向量化与语义检索
- Rerank 模型：category='rerank'，用于 RAG 检索精排（如 DashScope gte-rerank-v2）
"""
import json
import os
import re
import threading
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from backend.db.schema import get_conn
from backend.service.kb.kb_service import KbNotFound
from backend.utils.log_utils import log, rag
from backend.infrastructure import get_cache, get_key_builder

logger = log

_KB_METADATA_KEYS = ("chunk_id", "document_id", "user_id")

# 向量库里的"无显式知识库"哨兵值。
# Milvus 没有 NULL，而 `kb_documents.kb_id IS NULL` 语义上属于"默认知识库"
# （建表注释 + 前端 `<option :value="null">默认知识库</option>`）→ 写入向量时统一落成 0。
NULL_KB_SENTINEL = 0


class RetrieverError(Exception):
    """检索器异常（配置缺失等，向用户呈现明确信息）"""


# ════════════════════════════════════════════════════════════
# Embedding / 向量库构建
# ════════════════════════════════════════════════════════════

def _build_embeddings():
    """构建 embedding 实例；未配置/失败时抛 RetrieverError（含提示）。"""
    try:
        from backend.rag.embeddings import get_embeddings
        return get_embeddings()
    except Exception as e:  # noqa: BLE001
        raise RetrieverError(
            f"Embedding 服务不可用: {e}。"
            "请配置 RAG_EMBEDDING_PROVIDER / RAG_EMBEDDING_MODEL / RAG_EMBEDDING_BASE_URL / RAG_EMBEDDING_API_KEY"
            "（如 DashScope text-embedding-v3 或本地 Ollama）；未配置时将自动使用 BM25 兜底检索。"
        ) from e


def _build_user_vectorstore(user_id: int):
    from backend.rag.vectorstore import get_user_collection_name, get_vectorstore
    embeddings = _build_embeddings()
    return get_vectorstore(embeddings, collection=get_user_collection_name(user_id))


# ════════════════════════════════════════════════════════════
# 向量化 / 清理
# ════════════════════════════════════════════════════════════

def _fetch_doc_chunks(user_id: int, doc_id: int) -> Tuple[dict, List[dict]]:
    """校验文档归属并读取其全部 chunk。"""
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_documents WHERE id = %s", (doc_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if not rows:
            raise KbNotFound(f"文档不存在: id={doc_id}")
        doc = rows[0]
        if doc["user_id"] != user_id:
            raise KbNotFound(f"文档不存在: id={doc_id}")
        cur = conn.execute(
            "SELECT id, content, kind, strategy FROM kb_chunks WHERE document_id = %s ORDER BY chunk_index ASC",
            (doc_id,),
        )
        chunks = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    return doc, chunks


def vectorize_document(user_id: int, doc_id: int) -> dict:
    """
    将文档 chunk 向量化写入用户 collection，标记 vectorized=1。

    父子分片策略：只向量化子片（child）和普通块（base），跳过父片（parent）。
    检索时命中子片会返回其父片内容。
    """
    doc, chunks = _fetch_doc_chunks(user_id, doc_id)
    if not chunks:
        raise RetrieverError("文档没有知识块，无法向量化（请先重新解析）")

    from langchain_core.documents import Document

    vectorstore = _build_user_vectorstore(user_id)

    # 过滤：只向量化 child 类型的 chunk，跳过 parent（父片用于 GraphRAG 提取）
    # 统一使用父子切分策略，不再有 base 类型
    vectorizable_chunks = [
        c for c in chunks
        if c.get("kind") == "child"
    ]

    if not vectorizable_chunks:
        raise RetrieverError("文档没有可向量化的知识块（可能全部是父片）")

    docs = [
        Document(
            page_content=c["content"],
            metadata={
                "chunk_id": int(c["id"]),
                "document_id": int(doc_id),
                # ⚠️ Milvus 没有 NULL：旧实现把 kb_id 为空的文档写成 `"kb_id": None`，
                #    而 langchain_milvus 建 collection 时会因 None 抛
                #    `ValueError: Unrecognized datatype for kb_id` → **整个文档向量化失败**。
                #    实测：库里 10 个 kb_id 为 NULL 的文档全是 vectorized=0（图谱抽了、向量没写）。
                #    统一落成哨兵值 0（= 默认知识库），检索该库时用 `kb_id in [1, 0]` 一并召回。
                "kb_id": int(doc["kb_id"]) if doc.get("kb_id") else NULL_KB_SENTINEL,
                "user_id": int(user_id),
                "kind": "child",
                "strategy": "parent_child",
            },
        )
        for c in vectorizable_chunks
    ]
    # ★ 显式传递 ids：用 chunk_id 作为向量主键，避免 "No ids provided" 警告
    chunk_ids = [str(c["id"]) for c in vectorizable_chunks]
    vectorstore.add_documents(docs, ids=chunk_ids)

    conn = get_conn()
    try:
        conn.execute("UPDATE kb_documents SET vectorized = 1 WHERE id = %s", (doc_id,))
        conn.commit()
    finally:
        conn.close()

    rag.kb_vectorize(doc_id, len(docs))
    return {"id": doc_id, "vectorized_chunks": len(docs), "vectorized": True}


def _milvus_client():
    """按 MILVUS_HOST 配置构造 pymilvus MilvusClient（未配置返回 None）。"""
    host = os.getenv("MILVUS_HOST", "")
    if not host:
        return None
    try:
        from pymilvus import MilvusClient

        return MilvusClient(uri=f"http://{host}:{os.getenv('MILVUS_PORT', '19530')}")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[KB] MilvusClient 构造失败: {e}")
        return None


def unvectorize_document(user_id: int, doc_id: int) -> None:
    """
    清理文档的向量（按 document_id 删除）+ 置 vectorized=0。

    安全策略（2026-09-23 加固）：
    - **删除不依赖 embedding 配置**：旧实现先 `_build_user_vectorstore()` 才能删，
      而该函数在 embedding 未配置/异常时抛 RetrieverError → 被当成"没有向量可删"直接跳过，
      却照样把 `vectorized` 置 0 → **旧向量全部变成幽灵块**（实测 kb_user_1 里 7494 个
      chunk_id 有 80% 已不在 kb_chunks 中，全是这种残留）。删除只需 Milvus 连接，不需要 embedding。
    - **向量删除失败必须向上暴露**（不吞异常）：若吞掉异常仍置 vectorized=0，
      后续 delete_document 会因 `if doc.get("vectorized")` 为假而再也不尝试清理。
      因此只在删除成功后（或确认无向量可删时）才置 vectorized = 0。
    """
    deleted_by_milvus = False

    # ── 路径 A（首选）：Milvus 直连按 document_id 删除，不需要 embedding ──
    client = _milvus_client()
    if client is not None:
        from backend.rag.vectorstore import get_user_collection_name

        collection = get_user_collection_name(user_id)
        try:
            # 先判存在，避免对不存在的 collection 发删除请求
            # （pymilvus 会先打一行 ERROR 级 RPC error 再抛，日志噪音很大）
            if not client.has_collection(collection):
                logger.debug(f"[KB] collection 不存在，无需清理 {collection}")
                deleted_by_milvus = True
            else:
                client.delete(collection_name=collection, filter=f"document_id == {int(doc_id)}")
                deleted_by_milvus = True
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=True).warning(
                f"[KB] 向量清理失败 doc_id={doc_id} user_id={user_id}: {e}"
            )
            raise RetrieverError(f"向量清理失败 doc_id={doc_id}: {e}") from e

    # ── 路径 B（降级）：没有 Milvus 配置（本地 Chroma 部署）时走向量库抽象 ──
    if not deleted_by_milvus:
        vectorstore = None
        try:
            vectorstore = _build_user_vectorstore(user_id)
        except RetrieverError:
            vectorstore = None

        if vectorstore is not None:
            try:
                if _is_chroma_store(vectorstore):
                    result = vectorstore.delete(where={"document_id": int(doc_id)})
                else:
                    result = vectorstore.delete(expr=f"document_id == {int(doc_id)}")
                if result is False:
                    raise RetrieverError(
                        f"向量删除返回失败 doc_id={doc_id} user_id={user_id}"
                    )
            except Exception as e:  # noqa: BLE001
                logger.opt(exception=True).warning(
                    f"[KB] 向量清理失败 doc_id={doc_id} user_id={user_id}: {e}"
                )
                raise

    conn = get_conn()
    try:
        conn.execute("UPDATE kb_documents SET vectorized = 0 WHERE id = %s", (doc_id,))
        conn.commit()
    finally:
        conn.close()


def purge_orphan_vectors(user_id: int, dry_run: bool = True, batch: int = 1000) -> Dict[str, Any]:
    """
    清理"幽灵向量"：Milvus 里 chunk_id 已不存在于 kb_chunks 的残留向量。

    为什么会有幽灵向量：重新解析/重新上传会换一批 chunk id，旧向量若没删干净就会留下
    （实测 kb_user_1：7494 个不同 chunk_id 里 5994 个已不存在，占 80%）。它们**还带着
    旧解析的正文**，会被向量检索召回并进入 prompt，同时因为 kb_chunks 查不到元数据，
    引用信息也拼不出来。

    Args:
        user_id: 用户 ID
        dry_run: True 只统计不删除
        batch: 每批处理条数

    Returns:
        {"total": n, "alive": n, "orphan": n, "deleted": n, "orphan_ids_sample": [...]}
    """
    client = _milvus_client()
    if client is None:
        raise RetrieverError("未配置 Milvus，无法清理幽灵向量（本地 Chroma 部署请删除整个 collection 重建）")

    from backend.rag.vectorstore import get_user_collection_name

    collection = get_user_collection_name(user_id)
    ids: List[int] = []
    offset = 0
    while True:
        try:
            rows = client.query(
                collection_name=collection,
                filter="chunk_id > 0",
                output_fields=["chunk_id"],
                limit=batch,
                offset=offset,
                consistency_level="Strong",
            )
        except Exception as e:  # noqa: BLE001
            if "collection not found" in str(e).lower():
                return {"total": 0, "alive": 0, "orphan": 0, "deleted": 0, "orphan_ids_sample": []}
            raise
        if not rows:
            break
        ids.extend(int(r["chunk_id"]) for r in rows)
        offset += batch

    uniq = sorted(set(ids))
    alive_ids = set()
    conn = get_conn()
    try:
        for start in range(0, len(uniq), batch):
            part = uniq[start:start + batch]
            ph = ",".join(["%s"] * len(part))
            cur = conn.execute(f"SELECT id FROM kb_chunks WHERE id IN ({ph})", tuple(part))
            alive_ids.update(int(r["id"]) for r in (cur.fetchall() if hasattr(cur, "fetchall") else []))
    finally:
        conn.close()

    orphan = [cid for cid in uniq if cid not in alive_ids]
    deleted = 0
    if orphan and not dry_run:
        for start in range(0, len(orphan), batch):
            part = orphan[start:start + batch]
            expr = f"chunk_id in [{', '.join(str(c) for c in part)}]"
            client.delete(collection_name=collection, filter=expr)
            deleted += len(part)

    return {
        "total": len(uniq),
        "alive": len(alive_ids),
        "orphan": len(orphan),
        "deleted": deleted,
        "orphan_ids_sample": orphan[:10],
    }


def _get_parent_content(child_chunk_id: int) -> Optional[dict]:
    """
    查询子片的父片内容（父子分片支持）。

    如果子片有 parent_chunk_id，返回父片的 id/content/metadata（含 table_refs）；
    否则返回 None。
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT c.parent_chunk_id, p.content, p.metadata FROM kb_chunks c "
            "LEFT JOIN kb_chunks p ON p.id = c.parent_chunk_id "
            "WHERE c.id = ?",
            (child_chunk_id,),
        )
        row = cur.fetchone() if hasattr(cur, "fetchone") else None
        if row and row.get("parent_chunk_id") and row.get("content"):
            import json as _json
            meta = {}
            raw_meta = row.get("metadata")
            if raw_meta:
                try:
                    meta = _json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta or {}
                except (TypeError, ValueError):
                    meta = {}
            return {
                "parent_chunk_id": int(row["parent_chunk_id"]),
                "content": row["content"],
                "metadata": meta,
            }
        return None
    finally:
        conn.close()


def _enrich_with_parent_content(results: List[dict]) -> List[dict]:
    """
    对检索结果进行父子分片增强：
    - 如果命中子片（kind=child），替换为父片内容，chunk_id 改为父片 ID
    - 在 metadata 中标记 is_child 和 original_chunk_id（子片 ID）
    - 父片 metadata 中的 table_refs（数据库表关联）透传到结果
    """
    enriched = []
    for r in results:
        chunk_id = r.get("chunk_id")
        kind = r.get("kind")

        if kind == "child" and chunk_id:
            parent = _get_parent_content(chunk_id)
            if parent:
                # 替换为父片内容，chunk_id 改为父片 ID（保证 GT/引用一致）
                table_refs = (parent.get("metadata") or {}).get("table_refs") or []
                enriched.append({
                    **r,
                    "chunk_id": parent["parent_chunk_id"],  # 改为父片 ID
                    "content": parent["content"],
                    "is_child": True,
                    "original_chunk_id": chunk_id,  # 保留子片 ID 溯源
                    "kind": "parent",  # 标记为父片（实际返回的内容）
                    "table_refs": table_refs,  # 数据库表关联（text2sql 召回用）
                })
                continue

        # 非子片或无父片，保持原样
        enriched.append({**r, "is_child": False})

    return enriched


def _result_dedup_key(r: dict):
    """结果去重键：chunk 与 memory 分属不同命名空间，且不能用 None 做 key。

    图检索产出的记忆结果结构是 {"memory_id": ..., "content": ...}，没有 chunk_id。
    若直接用 chunk_id 去重，第一条记忆结果会把 None 放进 seen 集合，
    后续所有记忆结果都被当成重复丢弃；多查询 RRF 路径则直接 continue 全部丢失。

    Returns:
        ("c", chunk_id) / ("m", memory_id) / None（无法归类 → 不去重，宁可重复也不要丢）
    """
    cid = r.get("chunk_id")
    if cid is not None:
        return ("c", cid)
    mid = r.get("memory_id")
    if mid is not None:
        return ("m", mid)
    return None


def _dedup_by_parent(results: List[dict]) -> List[dict]:
    """
    父片级去重 — enrich 后同一父片的多条子片会变成内容完全相同的结果。
    按 chunk_id（enrich 后已替换为父片 ID）去重，保留分数最高的那条。

    非 enrich 的结果（无 chunk_id 或非父子分片）保持原样。
    """
    seen_ids = set()
    deduped = []
    for r in results:
        cid = r.get("chunk_id")
        if cid is not None:
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
        deduped.append(r)
    return deduped


def _filter_by_scope_layer(
    results: List[dict],
    user_id: int,
    _user_layers: Optional[set] = None,
) -> List[dict]:
    """
    数据层级过滤 — 只返回用户可见层级的检索结果。

    过滤逻辑：
    - chunk.scope_layer_id IS NULL → 继承 KB 的层级（kb_data_layers）
    - chunk.scope_layer_id 非 NULL → 直接匹配用户层级
    - 用户层级与 chunk 有效层级有交集 → 可见
    - layer_id=0（全员）是特殊层级，表示"所有人可见"

    性能：批量查询 chunk 层级和 KB 层级，避免 N+1 查询。
    可选传入 _user_layers 避免重复查询 get_user_layers（调用方预取场景）。
    """
    if not results:
        return results

    # 获取用户可见的层级（支持调用方预取传入，避免重复 DB 查询）
    if _user_layers is not None:
        user_layers = _user_layers
    else:
        from backend.service.auth.data_layer_service import get_user_layers
        user_layers = set(get_user_layers(user_id))

    # 收集所有 chunk_id 和 kb_id
    chunk_ids = [r.get("chunk_id") for r in results if r.get("chunk_id")]
    kb_ids = set(r.get("kb_id") for r in results if r.get("kb_id"))

    if not chunk_ids and not kb_ids:
        # 整批都没有 chunk_id / kb_id（典型：全是图检索的记忆结果，或纯 web search）。
        # ⚠️ 不能在这里直接 `return results` —— 那会**整批绕过**下面的逐条归属校验，
        # 而记忆结果没有 chunk_id、层级过滤也兜不住 → 跨租户记忆会直接进 LLM prompt。
        # 改为落到下面的逐条分支处理（无 chunk_id 时按 user_id 归属校验，取不到就丢弃）。
        # 后续的层级查询会因为 chunk_ids/kb_ids 为空而自然跳过，没有额外开销。
        pass

    # 批量查询 chunk 的 scope_layer_id
    chunk_layer_map: Dict[int, Optional[int]] = {}  # chunk_id -> scope_layer_id
    chunk_kb_map: Dict[int, int] = {}  # chunk_id -> kb_id
    if chunk_ids:
        conn = None
        try:
            conn = get_conn()
            placeholders = ",".join(["%s"] * len(chunk_ids))
            cur = conn.execute(
                f"SELECT id, scope_layer_id, kb_id FROM kb_chunks WHERE id IN ({placeholders})",
                chunk_ids
            )
            for row in (cur.fetchall() if hasattr(cur, "fetchall") else []):
                chunk_layer_map[row["id"]] = row.get("scope_layer_id")
                chunk_kb_map[row["id"]] = row.get("kb_id")
        except Exception as e:
            # fail-closed：查不到 chunk 层级就**整批丢弃**（宁可少召回，也不让不可见数据进 LLM）
            logger.opt(exception=True).warning(
                f"[DataLayer] 查询 chunk 层级失败 → 丢弃本批 {len(results)} 条结果（fail-closed）"
            )
            return []
        finally:
            if conn is not None:
                conn.close()

    # 批量查询 KB 的层级（用于 scope_layer_id IS NULL 的情况）
    kb_layer_map: Dict[int, set] = {}  # kb_id -> set of layer_ids
    kb_layer_query_failed = False  # 标记 KB 层级查询是否失败
    if kb_ids:
        conn = None
        try:
            conn = get_conn()
            placeholders = ",".join(["%s"] * len(kb_ids))
            cur = conn.execute(
                f"SELECT kb_id, layer_id FROM kb_data_layers WHERE kb_id IN ({placeholders})",
                list(kb_ids)
            )
            for row in (cur.fetchall() if hasattr(cur, "fetchall") else []):
                kb_id = row["kb_id"]
                if kb_id not in kb_layer_map:
                    kb_layer_map[kb_id] = set()
                kb_layer_map[kb_id].add(row["layer_id"])
        except Exception as e:
            # fail-closed：KB 层级查询失败时，标记失败状态
            # 后续对于 scope_layer_id IS NULL 的 chunk 将被丢弃
            logger.opt(exception=True).warning(
                f"[DataLayer] 查询 KB 层级失败 → 无法判断 KB 层级的 chunk 将被丢弃（fail-closed）"
            )
            kb_layer_query_failed = True
        finally:
            if conn is not None:
                conn.close()

    # 过滤结果
    filtered = []
    for r in results:
        chunk_id = r.get("chunk_id")
        kb_id = r.get("kb_id")

        # 没有 chunk_id 的结果
        if not chunk_id:
            # 1) 网络搜索结果：不来自本系统数据面，无层级概念 → 保留
            if r.get("retriever") == "web_search":
                filtered.append(r)
                continue
            # 2) 其余（如只有 memory_id 的记忆结果）**必须按 user_id 归属校验**后保留。
            #    取不到归属信息 → fail-closed 丢弃（宁可少召回，也不能把别用户的数据
            #    送进 LLM —— 记忆结果没有 chunk_id，无法靠层级过滤兜住）。
            owner = r.get("user_id")
            if owner is not None and str(owner) == str(user_id):
                filtered.append(r)
            else:
                logger.warning(
                    f"[DataLayer] 丢弃无 chunk_id 且归属不明的检索结果（fail-closed）: "
                    f"owner={owner!r} user_id={user_id} keys={sorted(r.keys())[:6]}"
                )
            continue

        scope_layer_id = chunk_layer_map.get(chunk_id)

        if scope_layer_id is not None:
            # 直接匹配：chunk 指定了层级
            if scope_layer_id in user_layers:
                filtered.append(r)
        elif chunk_id not in chunk_layer_map and chunk_id not in chunk_kb_map:
            # ★ chunk 行已经不存在（典型：重新解析换了一批 chunk id，旧向量残留成"幽灵块"）。
            #   旧实现走到下面"继承 KB 层级"分支：kb 查不到 → kb_layers 取默认 {0} →
            #   用户带 layer 0 就被放行 —— 等于把**已删除的旧正文**喂进 prompt，
            #   而且没有元数据（引用只能显示文档名）。
            #   这里改为 fail-closed：查不到 = 不是可信数据，直接丢弃。
            logger.debug(
                f"[DataLayer] 丢弃 kb_chunks 中不存在的 chunk（幽灵向量）: chunk_id={chunk_id}"
            )
            continue
        else:
            # 继承 KB 层级
            effective_kb_id = chunk_kb_map.get(chunk_id) or kb_id
            # 如果 KB 层级查询失败，丢弃无法确定层级的 chunk（fail-closed）
            if kb_layer_query_failed:
                logger.warning(
                    f"[DataLayer] 丢弃 KB 层级未知的 chunk（fail-closed）: "
                    f"chunk_id={chunk_id} effective_kb_id={effective_kb_id}"
                )
                continue
            kb_layers = kb_layer_map.get(effective_kb_id, {0})  # 无记录时默认全员可见
            # KB 层级与用户层级有交集 → 可见
            if kb_layers & user_layers:
                filtered.append(r)

    if len(filtered) < len(results):
        logger.info(
            f"[DataLayer] 层级过滤: {len(results)} → {len(filtered)} "
            f"(user_layers={user_layers})"
        )

    return filtered


# ════════════════════════════════════════════════════════════
# 向量库类型判断与过滤器转换（T3.1）
# ════════════════════════════════════════════════════════════

def _is_chroma_store(store) -> bool:
    """判断向量库是否为 Chroma。"""
    return store.__class__.__module__.startswith("langchain_chroma")


def _milvus_expr_to_chroma_filter(filters: List[str]) -> Optional[Dict[str, Any]]:
    """
    把 Milvus expr 条件列表转换为 Chroma filter 字典。

    Args:
        filters: Milvus 表达式字符串列表，只有两种形式：
                 - 'kind == "xxx"'
                 - 'kb_id == N' / 'kb_id in [N, M]'（默认知识库会把哨兵值 0 一并纳入）

    Returns:
        Chroma filter 字典，或 None（无过滤条件时）

    Raises:
        ValueError: 遇到无法解析的条件（严格模式，不静默放过）
    
    Note:
        Chroma 要求 where filter 必须只有**一个顶级操作符**。
        多条件时必须包装成 {"$and": [{"kind": ...}, {"kb_id": ...}]} 格式。
        单条件时直接返回 {"kind": ...} 或 {"kb_id": ...} 即可。
    """
    if not filters:
        return None

    conditions = []
    for cond in filters:
        cond = cond.strip()

        # 解析 kind == "xxx"
        kind_match = re.match(r'kind\s*==\s*"([^"]+)"', cond)
        if kind_match:
            conditions.append({"kind": kind_match.group(1)})
            continue

        # 解析 kb_id in [N, M]
        kb_in_match = re.match(r"kb_id\s+in\s*\[([\d,\s]+)\]", cond)
        if kb_in_match:
            values = [int(v) for v in kb_in_match.group(1).split(",") if v.strip()]
            conditions.append({"kb_id": {"$in": values}})
            continue

        # 解析 kb_id == N
        kb_match = re.match(r'kb_id\s*==\s*(\d+)', cond)
        if kb_match:
            conditions.append({"kb_id": int(kb_match.group(1))})
            continue

        # 无法解析的条件 → 严格模式：抛错而不是静默放过
        raise ValueError(f"无法转换的过滤条件: {cond}")

    if not conditions:
        return None
    
    # 单条件：直接返回 {"key": value}
    if len(conditions) == 1:
        return conditions[0]
    
    # 多条件：包装成 {"$and": [{"key": value}, ...]}
    return {"$and": conditions}


# ════════════════════════════════════════════════════════════
# 检索器
# ════════════════════════════════════════════════════════════

class VectorRetriever:
    """Milvus 向量检索（每用户 collection，降级 Chroma）。"""

    name = "vector"

    def __init__(self, user_id: int, kind: str = "all", kb_id: Optional[int] = None):
        self.user_id = user_id
        # 支持 child 类型（父子分片）
        self.kind = kind if kind in ("base", "topic", "child") else "all"
        self.kb_id = kb_id
        self._store = _build_user_vectorstore(user_id)

    def retrieve(self, query: str, top_k: int = 5, _user_layers: Optional[set] = None) -> List[dict]:
        if not query.strip():
            return []
        # 空库快速返回：省一次 embedding + Milvus 调用，也避免触发
        # "零命中过滤 → pymilvus 结果解析报错"（见 get_kb_index_status 说明）
        if self.kb_id is not None and not get_kb_index_status(self.kb_id)["vectors"]:
            logger.debug(f"[Vector] 知识库无向量，跳过检索 kb_id={self.kb_id}")
            return []
        # 构建 Milvus filter 表达式（支持多条件组合）
        filters = []
        if self.kind != "all":
            filters.append(f'kind == "{self.kind}"')
        if self.kb_id is not None:
            # ★ 默认知识库：NULL-kb 文档的向量以 NULL_KB_SENTINEL 存入，需一并纳入
            if is_default_kb(self.kb_id):
                filters.append(f"kb_id in [{int(self.kb_id)}, {NULL_KB_SENTINEL}]")
            else:
                filters.append(f"kb_id == {self.kb_id}")
        kwargs = {}
        if filters:
            # Milvus 用 expr 表达式；Chroma 只认 filter=dict，传 expr 会抛 TypeError
            if _is_chroma_store(self._store):
                try:
                    chroma_filter = _milvus_expr_to_chroma_filter(filters)
                    if chroma_filter:
                        kwargs["filter"] = chroma_filter
                except ValueError as e:
                    # 严格模式：无法把 expr 转成 Chroma filter 时**返回空结果**，
                    # 绝不退回"无过滤检索"（那会返回其他知识库/其他 kind 的数据）。
                    logger.warning(
                        f"[Hybrid] Chroma 过滤器转换失败，本次向量检索返回空结果"
                        f"（严格模式，不做无过滤检索）: {e}"
                    )
                    return []
            else:
                kwargs["expr"] = " and ".join(filters)
        try:
            results = self._store.similarity_search_with_score(query, k=top_k, **kwargs)
        except Exception as e:  # noqa: BLE001
            # 过滤条件命中 0 行时 pymilvus 3.0.1 会在结果解析阶段抛
            # "Unsupported field type: 0" —— 语义就是"没有结果"，按空结果处理，
            # 不让它冒充"向量库故障"去触发降级告警与 BM25 空转。
            if _is_empty_result_milvus_error(e):
                logger.debug(f"[Vector] 过滤条件零命中（按空结果处理）: {kwargs.get('expr')}")
                return []
            raise
        out = []
        for doc, score in results:
            meta = doc.metadata or {}
            # Milvus 返回距离（越小越相似），转成 0-1 相似度便于展示
            sim = round(1.0 / (1.0 + float(score)), 6)
            out.append({
                "chunk_id": meta.get("chunk_id"),
                "document_id": meta.get("document_id"),
                "content": doc.page_content,
                "score": sim,
                "kind": meta.get("kind") or "base",
                "retrieval_source": "vector",
            })
        # 父子分片增强：子片替换为父片内容，然后按父片去重
        out = _dedup_by_parent(_enrich_with_parent_content(out))
        # ★ 数据层级过滤（安全边界：确保只返回用户可见的 chunk）
        return _filter_by_scope_layer(out, self.user_id, _user_layers=_user_layers)


class BM25Retriever:
    """
    BM25 关键词检索（Redis 缓存 + 降级到进程内存）

    改造点：
    1. 使用 Redis 共享缓存，支持多进程部署
    2. BM25Okapi 对象序列化为 JSON 存储
    3. Redis 不可用时降级到进程内存缓存
    4. 文档变更时显式失效缓存
    """

    name = "bm25"

    # 进程内存缓存（降级用）
    _fallback_cache: Dict[tuple, tuple] = {}
    _lock = threading.Lock()

    # Redis 缓存 TTL（24 小时）
    _CACHE_TTL = int(os.getenv("BM25_CACHE_TTL", "86400"))

    def __init__(self, user_id: int, kind: str = "all", kb_id: Optional[int] = None):
        self.user_id = user_id
        self.kb_id = kb_id  # 知识库ID，None表示所有知识库
        # 支持 child 类型（父子分片）
        self.kind = kind if kind in ("base", "topic", "child") else "all"
        self._redis = get_cache()  # Redis 客户端（支持降级）

    def retrieve(self, query: str, top_k: int = 5, _user_layers: Optional[set] = None) -> List[dict]:
        if not query.strip():
            return []
        # 空库快速返回：BM25 要全表扫 chunk 建索引（含 JOIN），空库上纯属白做
        if self.kb_id is not None and not get_kb_index_status(self.kb_id)["chunks"]:
            logger.debug(f"[BM25] 知识库无文本块，跳过检索 kb_id={self.kb_id}")
            return []
        bm25, id_list, content_list, kind_list, doc_id_list = self._get_index()
        if bm25 is None:  # 无 chunk 可检索
            return []
        scores = bm25.get_scores(_tokenize(query))
        # 注意：小语料库下 BM25 IDF 可能为负值，仅按分数排序取 top-K（不过滤 >0）
        ranked = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]
        out = []
        for i in ranked:
            if self.kind != "all" and kind_list[i] != self.kind:
                continue
            item = {
                "chunk_id": id_list[i],
                "document_id": doc_id_list[i],
                "content": content_list[i],
                "score": round(float(scores[i]), 6),
                "kind": kind_list[i],
                "retrieval_source": "bm25",
            }
            # topic 类型 chunk 携带数据库表关联（text2sql 召回用）
            if kind_list[i] in ("topic", "base"):
                table_refs = self._chunk_table_refs(id_list[i])
                if table_refs:
                    item["table_refs"] = table_refs
            out.append(item)
            if len(out) >= top_k:
                break
        # 父子分片增强：子片替换为父片内容，然后按父片去重
        out = _dedup_by_parent(_enrich_with_parent_content(out))
        # ★ 数据层级过滤（安全边界：确保只返回用户可见的 chunk）
        return _filter_by_scope_layer(out, self.user_id, _user_layers=_user_layers)

    def _get_index(self):
        """
        获取 BM25 索引（优先 Redis，降级到进程内存）

        Returns:
            (bm25, id_list, content_list, kind_list, doc_id_list)
        """
        from rank_bm25 import BM25Okapi

        signature = self._signature()
        cache_key = (self.user_id, self.kb_id) if self.kb_id is not None else (None, None)

        # 1. 尝试从 Redis 获取
        if self._redis.is_available:
            redis_key = self._bm25_cache_key()
            sig_key = self._bm25_signature_key()

            # 检查签名是否匹配
            cached_sig = self._redis.get(sig_key)
            if cached_sig:
                cached_sig = json.loads(cached_sig)
                if tuple(cached_sig) == signature:
                    # 签名匹配，获取索引
                    cached_data = self._redis.get(redis_key)
                    if cached_data:
                        data = json.loads(cached_data)
                        bm25 = self._deserialize_bm25(data["bm25"])
                        logger.debug(f"[BM25] Redis 缓存命中: {redis_key}")
                        return (
                            bm25,
                            data["id_list"],
                            data["content_list"],
                            data["kind_list"],
                            data["doc_id_list"],
                        )

        # 2. Redis 未命中或不可用，尝试进程内存缓存（降级）
        with self._lock:
            cached = self._fallback_cache.get(cache_key)
            if cached and cached[0] == signature:
                logger.debug(f"[BM25] 进程内存缓存命中: {cache_key}")
                return cached[1], cached[2], cached[3], cached[4], cached[5]

        # 3. 缓存完全未命中，从 MySQL 构建
        logger.info(f"[BM25] 构建索引: kb_id={self.kb_id}")
        bm25, id_list, content_list, kind_list, doc_id_list = self._build_index()

        # 4. 存入缓存
        # 存入 Redis
        if self._redis.is_available:
            redis_key = self._bm25_cache_key()
            sig_key = self._bm25_signature_key()

            # 序列化
            data = {
                "bm25": self._serialize_bm25(bm25),
                "id_list": id_list,
                "content_list": content_list,
                "kind_list": kind_list,
                "doc_id_list": doc_id_list,
            }

            # 存储索引
            self._redis.set(redis_key, json.dumps(data, ensure_ascii=False), ttl=self._CACHE_TTL)
            # 存储签名
            self._redis.set(sig_key, json.dumps(signature), ttl=self._CACHE_TTL)
            logger.info(f"[BM25] 已存入 Redis: {redis_key}, TTL={self._CACHE_TTL}s")

        # 同时存入进程内存缓存（降级用）
        with self._lock:
            self._fallback_cache[cache_key] = (
                signature,
                bm25,
                id_list,
                content_list,
                kind_list,
                doc_id_list,
            )

        return bm25, id_list, content_list, kind_list, doc_id_list

    def _signature(self) -> tuple:
        """
        计算索引签名，用于判断缓存是否过期

        Returns:
            (chunk_count, max_chunk_id)
        """
        conn = get_conn()
        try:
            if self.kb_id is not None:
                # 按知识库查询；默认知识库额外纳入 kb_id 为空的文档（见 is_default_kb）
                if is_default_kb(self.kb_id):
                    where = ("(c.kb_id = ? OR (c.kb_id IS NULL AND (d.kb_id = ? OR d.kb_id IS NULL))) "
                             "AND c.kind != 'parent'")
                else:
                    where = "(c.kb_id = ? OR (c.kb_id IS NULL AND d.kb_id = ?)) AND c.kind != 'parent'"
                cur = conn.execute(
                    "SELECT COUNT(*) as cnt, MAX(c.id) as max_id FROM kb_chunks c "
                    "JOIN kb_documents d ON d.id = c.document_id "
                    f"WHERE {where}",
                    (self.kb_id, self.kb_id),
                )
            else:
                # 全库查询
                cur = conn.execute(
                    "SELECT COUNT(*) as cnt, MAX(id) as max_id FROM kb_chunks WHERE kind != 'parent'"
                )
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            if row:
                return (row["cnt"] or 0, row["max_id"] or 0)
            return (0, 0)
        finally:
            conn.close()

    def _build_index(self):
        """从 MySQL 构建 BM25 索引"""
        conn = get_conn()
        try:
            # 排除父片（kind='parent'），只索引子片和普通块
            if self.kb_id is not None:
                # 按知识库过滤
                # 兼容 kb_chunks.kb_id IS NULL 的情况，通过 kb_documents 表关联；
                # 默认知识库额外纳入 kb_id 为空的文档
                if is_default_kb(self.kb_id):
                    where = ("(c.kb_id = ? OR (c.kb_id IS NULL AND (d.kb_id = ? OR d.kb_id IS NULL))) "
                             "AND c.kind != 'parent'")
                else:
                    where = "(c.kb_id = ? OR (c.kb_id IS NULL AND d.kb_id = ?)) AND c.kind != 'parent'"
                cur = conn.execute(
                    "SELECT c.id, c.document_id, c.content, c.kind FROM kb_chunks c "
                    "JOIN kb_documents d ON d.id = c.document_id "
                    f"WHERE {where} "
                    "ORDER BY c.id ASC",
                    (self.kb_id, self.kb_id),
                )
            else:
                # 所有知识库 —— **不按上传者过滤**。
                cur = conn.execute(
                    "SELECT c.id, c.document_id, c.content, c.kind FROM kb_chunks c "
                    "JOIN kb_documents d ON d.id = c.document_id "
                    "WHERE c.kind != 'parent' "
                    "ORDER BY c.id ASC",
                )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        finally:
            conn.close()

        from rank_bm25 import BM25Okapi

        id_list = [r["id"] for r in rows]
        doc_id_list = [r["document_id"] for r in rows]
        content_list = [r["content"] or "" for r in rows]
        kind_list = [r.get("kind") or "base" for r in rows]
        tokenized = [_tokenize(t) for t in content_list]
        bm25 = BM25Okapi(tokenized) if tokenized else None

        return bm25, id_list, content_list, kind_list, doc_id_list

    def _chunk_table_refs(self, chunk_id: int) -> List[str]:
        """读取 chunk metadata 中的 table_refs（数据库表关联）。"""
        import json as _json
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT metadata FROM kb_chunks WHERE id = ?",
                (chunk_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if not rows:
                return []
            meta = _json.loads(rows[0]["metadata"] or "{}")
            return meta.get("table_refs", [])
        finally:
            conn.close()

    def _bm25_cache_key(self) -> str:
        """生成 BM25 索引的 Redis 缓存 key"""
        if self.kb_id is not None:
            return f"agentforge:bm25:kb:{self.kb_id}"
        else:
            return "agentforge:bm25:all"

    def _bm25_signature_key(self) -> str:
        """生成 BM25 签名的 Redis 缓存 key"""
        if self.kb_id is not None:
            return f"agentforge:bm25:sig:{self.kb_id}"
        else:
            return "agentforge:bm25:sig:all"

    @staticmethod
    def _serialize_bm25(bm25) -> Optional[dict]:
        """序列化 BM25Okapi 对象为 JSON 兼容字典。

        ⚠️ 只序列化 BM25Okapi **真实存在**的属性：`corpus_size / avgdl / doc_freqs /
        doc_len / idf`（`get_scores()` 只用这几项）。
        历史实现多写了一个 `bm25.doc_term_freqs` —— 该属性在 rank_bm25 里并不存在，
        于是**只要语料非空就抛 AttributeError**，BM25 索引永远建不起来：
        表现为词法那一路静默失效（HybridRetriever 内部吞掉异常，退化成纯向量），
        CRAG 的 BM25 兜底也一起失效。空语料（bm25=None）反而"正常"，所以只在有数据的库上暴露。
        """
        if bm25 is None:
            return None

        return {
            "corpus_size": bm25.corpus_size,
            "avgdl": bm25.avgdl,
            "doc_freqs": bm25.doc_freqs,  # List[Dict[str, int]]：每个文档的词频表
            "doc_len": bm25.doc_len,  # List[int]
            "idf": bm25.idf,  # Dict[str, float]
        }

    @staticmethod
    def _deserialize_bm25(data: Optional[dict]):
        """反序列化字典为 BM25Okapi 对象（容忍历史缓存里多余的键）"""
        if data is None:
            return None

        from rank_bm25 import BM25Okapi

        # 创建空实例
        bm25 = BM25Okapi.__new__(BM25Okapi)

        # 恢复属性（只恢复存在的键，兼容旧版本写下的缓存条目）
        bm25.corpus_size = data["corpus_size"]
        bm25.avgdl = data["avgdl"]
        bm25.doc_freqs = data["doc_freqs"]
        bm25.doc_len = data["doc_len"]
        bm25.idf = data["idf"]

        # 恢复 k1 和 b 参数（默认值）
        bm25.k1 = 1.5
        bm25.b = 0.75
        bm25.epsilon = 0.25

        return bm25


def invalidate_bm25_cache(user_id: int, kb_id: Optional[int] = None) -> None:
    """
    文档删除/重解析后显式失效 BM25 缓存（Redis + 进程内存）

    Args:
        user_id: 用户 ID（保留参数，用于进程内存缓存失效）
        kb_id: 知识库 ID，None 表示失效全库索引
    """
    redis = get_cache()

    if redis.is_available:
        redis_key = f"agentforge:bm25:kb:{kb_id}" if kb_id is not None else "agentforge:bm25:all"
        sig_key = f"agentforge:bm25:sig:{kb_id}" if kb_id is not None else "agentforge:bm25:sig:all"

        redis.delete(redis_key)
        redis.delete(sig_key)
        logger.info(f"[BM25] 已失效 Redis 缓存: {redis_key}")

    # 同时失效进程内存缓存
    with BM25Retriever._lock:
        keys_to_remove = []
        for key in BM25Retriever._fallback_cache:
            if kb_id is None:
                # 失效所有
                keys_to_remove.append(key)
            elif key[1] == kb_id:
                # 失效指定知识库
                keys_to_remove.append(key)

        for key in keys_to_remove:
            BM25Retriever._fallback_cache.pop(key, None)


def invalidate_all_bm25_cache(reason: str = "") -> int:
    """
    清空所有 BM25 缓存（Redis + 进程内存）

    Returns:
        清除的条目数
    """
    redis = get_cache()
    count = 0

    if redis.is_available:
        # 使用 SCAN 遍历所有 BM25 缓存 key
        pattern = "agentforge:bm25:*"
        cursor = 0
        while True:
            cursor, keys = redis._client.scan(cursor, match=pattern, count=100)
            if keys:
                redis._client.delete(*keys)
                count += len(keys)
            if cursor == 0:
                break

        logger.info(f"[BM25] 已清空 Redis 缓存: {count} 条")

    # 清空进程内存缓存
    with BM25Retriever._lock:
        count += len(BM25Retriever._fallback_cache)
        BM25Retriever._fallback_cache.clear()

    return count


# ════════════════════════════════════════════════════════════
# 检索日志（RAG 评测闭环：聊天反馈归因的数据源）
# ════════════════════════════════════════════════════════════

def log_retrieval(
    user_id: int,
    thread_id: str,
    query: str,
    top_k: int,
    retriever_name: str,
    results: List[dict],
    elapsed_ms: int = 0,
) -> Optional[int]:
    """
    记录一次知识库检索调用（kb_retrieval_logs 表）。

    失败静默（不阻断聊天主链路）；成功返回 log id。

    Args:
        results: retriever.retrieve() 的输出（含 chunk_id 字段）
    """
    import json as _json

    try:
        chunk_ids = [int(r["chunk_id"]) for r in results if r.get("chunk_id") is not None]
        conn = get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO kb_retrieval_logs "
                "(user_id, thread_id, query, top_k, retriever, chunk_ids, hit_count, elapsed_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(user_id),
                    str(thread_id or "")[:128],
                    (query or "")[:2000],
                    int(top_k),
                    str(retriever_name or "")[:16],
                    _json.dumps(chunk_ids),
                    len(chunk_ids),
                    int(elapsed_ms),
                ),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 — 日志失败不影响对话
        logger.debug(f"[KB] 检索日志写入失败: {e}")
        return None


def latest_retrieval_chunk_ids(thread_id: str, user_id: Optional[int] = None, limit: int = 1) -> List[int]:
    """
    按 thread_id 取最近一次检索的 chunk_ids（反馈归因用）。
    
    Args:
        thread_id: 会话 ID
        user_id: 用户 ID（可选，传入时增加一层隔离校验）
        limit: 返回条数
    """
    import json as _json

    # 构建 SQL：优先用 user_id + thread_id 双重过滤
    if user_id is not None:
        sql = "SELECT chunk_ids FROM kb_retrieval_logs WHERE user_id = ? AND thread_id = ? ORDER BY id DESC LIMIT ?"
        params = (int(user_id), str(thread_id or ""), max(1, int(limit)))
    else:
        sql = "SELECT chunk_ids FROM kb_retrieval_logs WHERE thread_id = ? ORDER BY id DESC LIMIT ?"
        params = (str(thread_id or ""), max(1, int(limit)))

    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        return []
    try:
        raw = rows[0].get("chunk_ids")
        ids = _json.loads(raw) if isinstance(raw, str) else raw
        return [int(i) for i in (ids or [])]
    except (TypeError, ValueError):
        return []


def get_retriever(user_id: int, mode: str = "auto", kind: str = "all", kb_id: Optional[int] = None):
    """
    获取检索器。

    Args:
        user_id: 用户 ID
        mode: auto（有向量配置且该用户已有向量 → vector，否则 bm25）
              | vector | bm25 | hybrid（三路 RRF 融合：vector + bm25 + graph）
              | graph（仅图检索）
              | smart（智能路由：根据查询自动选择 local/global/drift）
              | global（GraphRAG Global Search：社区报告 Map-Reduce）
              | drift（GraphRAG DRIFT Search：社区上下文 + 实体扩展）
        kind: all（全部块）| base（仅基础块）| topic（仅主题节点块）
              | child（仅子片，父子分片策略）—— 策略对比用
        kb_id: 知识库ID，None表示所有知识库

    Returns:
        (retriever, warnings: List[str])
    """
    warnings: List[str] = []

    # GraphRAG 模式（Global / DRIFT / Smart）
    if mode in ("global", "drift", "smart"):
        from backend.service.kb.graphrag_retriever import (
            GlobalRetriever, DRIFTRetriever, SmartRetriever
        )
        if mode == "global":
            return GlobalRetriever(user_id), warnings
        elif mode == "drift":
            return DRIFTRetriever(user_id), warnings
        else:  # smart
            return SmartRetriever(user_id), warnings

    if mode == "bm25":
        return BM25Retriever(user_id, kind=kind, kb_id=kb_id), warnings

    if mode == "graph":
        return GraphRetriever(user_id), warnings

    if mode == "hybrid":
        return HybridRetriever(user_id, kind=kind, kb_id=kb_id), warnings

    if mode in ("vector", "auto"):
        try:
            retriever = VectorRetriever(user_id, kind=kind, kb_id=kb_id)
            if mode == "auto" and not _user_has_vectors(user_id):
                warnings.append("当前用户暂无向量数据，已降级 BM25 检索（先对文档执行「向量化」）")
                return BM25Retriever(user_id, kind=kind, kb_id=kb_id), warnings
            return retriever, warnings
        except RetrieverError as e:
            if mode == "vector":
                raise
            warnings.append(f"向量检索不可用，已降级 BM25: {e}")
            return BM25Retriever(user_id, kind=kind, kb_id=kb_id), warnings

    raise ValueError(f"未知检索模式: {mode}（可选 auto/vector/bm25/hybrid/graph/smart/global/drift）")


def classify_query_for_weights(query: str) -> dict:
    """
    根据查询特征判断 RRF 权重偏好（动态 RRF 权重）。

    通过分析查询中的关键词信号，判断该查询更适合语义检索、关键词检索还是图谱检索，
    返回对应的权重分配。

    Args:
        query: 用户查询文本

    Returns:
        {"semantic": float, "keyword": float, "kg": float} — 归一化权重
    """
    query_lower = query.lower()

    # 关键词密集型信号：SQL 语法、精确字段名、配置参数
    keyword_signals = [
        "表", "字段", "列", "sql", "insert", "select", "update",
        "delete", "create", "alter", "config", "参数", "配置项",
        "索引", "主键", "外键", "varchar", "int", "bigint",
    ]
    keyword_score = sum(1 for k in keyword_signals if k in query_lower)

    # 语义型信号：自然语言问题、描述性查询
    semantic_signals = [
        "怎么", "如何", "为什么", "什么", "描述", "解释", "分析",
        "区别", "对比", "原理", "机制", "流程", "优势", "劣势",
    ]
    semantic_score = sum(1 for s in semantic_signals if s in query)

    # 图关系型信号：实体关系、多跳推理
    kg_signals = ["关系", "关联", "依赖", "影响", "上下游", "链路", "调用"]
    kg_score = sum(1 for k in kg_signals if k in query)

    total = keyword_score + semantic_score + kg_score
    if total == 0:
        return {"semantic": 0.4, "keyword": 0.4, "kg": 0.2}  # 默认权重

    # 归一化信号比例
    raw_sem = semantic_score / total
    raw_kw = keyword_score / total
    raw_kg = kg_score / total

    # 混合策略：基础权重 + 分类偏移（最大 ±0.15）
    sem_w = 0.35 + (raw_sem - 0.33) * 0.45
    kw_w = 0.35 + (raw_kw - 0.33) * 0.45
    kg_w = 0.10 + (raw_kg - 0.33) * 0.45

    # 钳位 + 归一化
    sem_w = max(0.15, min(0.55, sem_w))
    kw_w = max(0.15, min(0.55, kw_w))
    kg_w = max(0.05, min(0.35, kg_w))
    total_w = sem_w + kw_w + kg_w

    return {
        "semantic": round(sem_w / total_w, 3),
        "keyword": round(kw_w / total_w, 3),
        "kg": round(kg_w / total_w, 3),
    }


def _rrf_fuse_multi_query(
    query_results: List[Tuple[str, List[dict]]],
    top_k: int,
    rrf_k: int = 60,
) -> List[dict]:
    """
    RRF 融合多路检索结果（P2 优化）。

    每个文档的 RRF 分 = Σ 1/(k + rank_in_route_i)：
    - **同一 chunk 被多路命中会被去重成一条**（key = chunk_id），不是出现两条；
    - 被多路命中的文档分数叠加 → 排更前（"多路投票"语义，正是我们要的共识奖励）。

    调用方约定：**每一路必须单独成 list**（一个 query×route 一个 list）。
    如果把"实体块"和"分片块"拼成一个 list 再传进来，两路的 rank 会互相穿插，
    RRF 的排名语义就被破坏了。

    Args:
        query_results: [(route_label, results_list), ...]
        top_k: 返回数量
        rrf_k: RRF 平滑常数（默认 60）

    Returns:
        融合后的结果列表，按 RRF 分降序排列
    """
    rrf_scores: Dict = {}   # dedup_key -> rrf_score（chunk 与 memory 分属不同命名空间）
    chunk_data: Dict = {}   # dedup_key -> first-seen result dict
    entity_scores: Dict = {}  # dedup_key -> 该块在各路里出现过的最大实体余弦分

    # 无法归类的结果（既无 chunk_id 也无 memory_id）单独保留，不参与 RRF 打分
    unclassified: List[dict] = []

    for _query, results in query_results:
        for rank, r in enumerate(results, start=1):
            key = _result_dedup_key(r)
            if key is None:
                # 无法归类 → 不去重也不打分，直接保留（宁可重复也不要丢）
                unclassified.append(r)
                continue
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
            if key not in chunk_data:
                chunk_data[key] = r
            # 实体余弦分要跨路保留（first-seen 那条可能来自分片路，没有 entity_score）：
            # 质量评估与"相关度"展示都优先用它，丢了就会退化成 0.0x 的融合分
            es = r.get("entity_score")
            if es is not None:
                entity_scores[key] = max(entity_scores.get(key, 0.0), float(es))

    # 按 RRF 分降序排列
    sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)[:top_k]

    out = []
    for key in sorted_keys:
        r = dict(chunk_data[key])
        r["score"] = round(rrf_scores[key], 6)
        r["rrf_fused"] = True  # 标记为 RRF 融合结果
        if key in entity_scores:
            r["entity_score"] = round(entity_scores[key], 6)
        out.append(r)

    # 追加无法归类的结果（放在融合结果之后）
    out.extend(dict(r) for r in unclassified)

    return out


def assess_retrieval_quality(results: List[dict], query: str) -> dict:
    """
    评估检索结果质量（CRAG 质量门控）。

    在 rerank 之后调用，基于 rerank_score 判断检索质量等级，
    指导下游（knowledge_search 工具）决定是否注入置信度提示。

    判断维度：
    1. rerank_score top-1 分数（核心指标）
    2. rerank_score 均值
    3. 结果数量

    Returns:
        {
            "quality": "high" | "medium" | "low" | "empty",
            "top1_score": float,
            "avg_score": float,
            "result_count": int,
            "action": "return" | "expand" | "warn" | "reject",
            "reason": str,
        }
    """
    if not results:
        return {
            "quality": "empty",
            "top1_score": 0.0,
            "avg_score": 0.0,
            "result_count": 0,
            "action": "reject",
            "reason": f"检索结果为空: {query[:50]}",
        }

    # 提取 rerank_score（优先）或 score 作为质量判断依据
    # ⚠️ entity_score 必须排在 score 之前：多查询 RRF 融合会把 score 覆盖成 0.0x 量级的
    # 融合分，直接用 score 判质量会把"实体余弦 0.8 的高相关结果"误判成 low。
    scores = []
    for r in results:
        s = r.get("rerank_score")
        if s is None:
            s = r.get("entity_score")
        if s is None:
            s = r.get("score", 0)
        scores.append(float(s or 0))

    top1 = scores[0] if scores else 0.0
    avg = sum(scores) / len(scores) if scores else 0.0

    # 质量分级
    if top1 < 0.3 or avg < 0.2:
        return {
            "quality": "low",
            "top1_score": round(top1, 4),
            "avg_score": round(avg, 4),
            "result_count": len(results),
            "action": "warn",
            "reason": f"检索质量低: top1={top1:.3f}, avg={avg:.3f}",
        }
    elif top1 < 0.5:
        return {
            "quality": "medium",
            "top1_score": round(top1, 4),
            "avg_score": round(avg, 4),
            "result_count": len(results),
            "action": "expand",
            "reason": f"检索质量中等: top1={top1:.3f}, avg={avg:.3f}",
        }
    else:
        return {
            "quality": "high",
            "top1_score": round(top1, 4),
            "avg_score": round(avg, 4),
            "result_count": len(results),
            "action": "return",
            "reason": f"检索质量高: top1={top1:.3f}, avg={avg:.3f}",
        }


def _web_search_fallback(query: str, top_k: int = 3) -> List[dict]:
    """
    联网搜索兜底 — 当知识库检索完全无结果时，用 web search 补充。
    复用系统已有的 web search 基础设施（DuckDuckGo/Tavily 等）。

    返回标准结果 dict 格式，方便下游统一处理。
    """
    try:
        from backend.hermes.tools.web_tools import web_search_tool
        import json

        raw = web_search_tool(query, limit=top_k)
        data = json.loads(raw)
        if not data.get("success"):
            return []

        results = []
        for item in data.get("data", {}).get("web", [])[:top_k]:
            results.append({
                "content": f"{item.get('title', '')}\n{item.get('description', '')}",
                "score": 0.0,
                "chunk_id": None,
                "document_id": None,
                "kb_name": "网络搜索",
                "kb_id": None,
                "retriever": "web_search",
                "path": "main",
                "web_url": item.get("url", ""),
                "web_title": item.get("title", ""),
            })
        return results
    except Exception as e:
        rag.crag_action("web_fallback", f"失败: {e}")
        return []


def dual_path_retrieve(
    user_id: int,
    query: str,
    main_kb_id: Optional[int] = None,
    case_kb_name: str = "历史正确案例",
    main_top_k: int = 5,
    case_top_k: int = 3,
    mode: str = "hybrid",
    enable_rerank: bool = True,
    enable_query_rewrite: bool = False,
    enable_sub_queries: bool = False,
    enable_synonyms: bool = False,
    auto_rewrite: bool = True,
    confidence_gate: bool = True,
    confidence_threshold: float = 0.70,
    enable_web_fallback: bool = True,
    enable_semantic_cache: bool = True,
    adaptive_routing: bool = False,
    force_retrieval: bool = False,
    enable_entity_search: bool = True,
) -> Dict[str, List[dict]]:
    """
    双路召回：LLM 选库 → 主路径召回 + 案例路径召回（与 Eyes 同构）。

    路径 A（产品手册主题）：解决"用哪张表"
    - 主链路 = 自适应检索：**实体向量检索优先**（实体 → 图扩展 → 原文块），
      实体不够用才查改写 + 分片检索（Vector + BM25）并统一 RRF 融合

    路径 B（历史正确案例检索）：解决"怎么写 SQL"
    - 召回 Top-3 SQL 示例注入 Prompt 作为 Few-shot 参照（保持文本匹配，不走实体）

    链路顺序（2026-09-23 定稿）：
    分类(总结→社区报告 / 其他→自适应) → 语义缓存 → 选库 → 剔除空库
      → **实体门控**：主查询实体检索，够（strong ≥ min_strong）→ 直接返回原文块
      → 不够：查询改写 → 主查询(实体+图扩展, 分片) + 每个改写(实体无扩展, 分片)
      → 全部 route 统一 RRF 融合（同块去重、多路命中加分）→ 案例路径 → Rerank → CRAG → 层级过滤

    Args:
        user_id: 用户 ID
        query: 检索查询
        main_kb_id: 主路径知识库ID，None 时由 LLM 自动选库
        case_kb_name: 案例知识库名称（默认"历史正确案例"）
        main_top_k: 主路径返回数量
        case_top_k: 案例路径返回数量
        mode: 检索模式（hybrid/auto/bm25/vector）
        enable_rerank: 是否启用 Rerank 精排（默认 True）
        enable_query_rewrite: 是否启用主查询改写（默认 False）
        enable_sub_queries: 是否启用子查询生成（默认 False）
        enable_synonyms: 是否启用同义改写（默认 False）
        auto_rewrite: 是否自动根据查询特征判断改写需求（默认 True，优先级低于显式参数）
        confidence_gate: 是否启用**实体门控**（默认 True）。命中即直返实体原文块，
            跳过查询改写与分片检索；置 False 则强制走完整链路（实体 + 分片两路补齐）。
        confidence_threshold: 兼容参数（旧的"分片基线门控"阈值，现已不参与决策，
            实体门控阈值见 RAG_ENTITY_STRONG_THRESHOLD / RAG_ENTITY_MIN_STRONG）
        adaptive_routing: 是否启用自适应 RAG 路由（默认 False）。
            启用后根据查询特征自动选择最优策略组合（检索模式/改写/top_k/权重等），
            其他策略参数将被路由器输出覆盖。
        force_retrieval: 强制检索（默认 False）。**显式检索入口必须置 True**
            （如 knowledge_search 工具）：路由器把 len ≤ 8 且无检索信号的查询判为
            NO_RETRIEVAL，而工具调用常是"关羽 武器"这类短查询 →
            会被整条跳过，表现为"知识库明明有数据却答没有相关信息"。
        enable_entity_search: 是否启用实体链路（默认 True）。关闭后退化为
            "改写 + 分片检索"，用于 A/B 对比。

    Returns:
        {
            "selected_kbs": [...],    # LLM 选中的知识库
            "main_results": [...],    # 主路径结果（不含案例库）
            "case_results": [...],    # 案例路径结果
            "merged_results": [...]   # 合并结果（主路径 + 案例路径）
            "query_rewrite": {...}    # 改写信息（可选）
            "confidence_gate": {...}  # 置信度门控信息（可选）
            "adaptive_routing": {...} # 自适应路由信息（可选）
        }
    """
    from backend.service.kb.knowledge_base_service import KnowledgeBaseService
    from backend.service.kb.adaptive_retriever import (
        AdaptiveRetriever,
        KIND_ADAPTIVE,
        KIND_SUMMARY,
        METHOD_GLOBAL,
        classify_retrieval_kind,
        get_min_strong_entities,
        get_strong_threshold,
    )

    # ── 统一检索链路分类（总结型 → 社区报告；其他 → 实体 local → 文本块兜底） ──
    # 纯规则零 LLM；必须在置信度门控之前，否则总结型查询会被"基线分够高"短路掉
    retrieval_kind = classify_retrieval_kind(query)
    rag.info(f"🧭 [Adaptive] 检索链路: {retrieval_kind} | query={query[:60]}")

    # ── Adaptive RAG 路由（参考 Adaptive-RAG, NAACL 2024） ──
    adaptive_result = None
    if adaptive_routing:
        from backend.service.kb.kb_adaptive_router import route_query
        adaptive_result = route_query(query, user_id)

        # NO_RETRIEVAL: 跳过整个检索管线，返回空结果让 LLM 直答
        # ⚠️ force_retrieval=True 时**不跳过**：显式检索入口（knowledge_search 工具）
        #    的短查询（如"关羽 武器"）会被路由器判成 NO_RETRIEVAL，
        #    若照跳，用户看到的是"知识库中未找到相关信息"（数据明明存在）。
        if adaptive_result.skip_retrieval and not force_retrieval:
            rag.adaptive(adaptive_result.complexity.value, adaptive_result.reason)
            return {
                "selected_kbs": [],
                "main_results": [],
                "case_results": [],
                "merged_results": [],
                "quality_assessment": {"quality": "empty", "reason": "no_retrieval"},
                "adaptive_routing": {
                    "complexity": adaptive_result.complexity.value,
                    "reason": adaptive_result.reason,
                },
            }

        if adaptive_result.skip_retrieval and force_retrieval:
            rag.info(
                f"⚡ [Adaptive] 显式检索请求 → 覆盖 NO_RETRIEVAL 路由（{adaptive_result.reason}）"
            )

        # 策略覆盖参数（路由器只管"检索多少"，不管"怎么检索"）
        enable_query_rewrite = adaptive_result.enable_rewrite
        enable_sub_queries = adaptive_result.enable_sub_queries
        enable_web_fallback = adaptive_result.enable_web_fallback
        if adaptive_result.top_k_multiplier > 0:
            main_top_k = int(main_top_k * adaptive_result.top_k_multiplier)
        rag.adaptive(
                adaptive_result.complexity.value,
                f"rewrite={enable_query_rewrite}, sub_q={enable_sub_queries}, top_k={main_top_k} | {adaptive_result.reason}"
            )

    # ── 语义缓存检查（相似 query 命中直接返回，跳过整个检索管线） ──
    if enable_semantic_cache:
        from backend.service.kb.kb_semantic_cache import check_semantic_cache
        cached_result = check_semantic_cache(query, user_id)
        if cached_result is not None:
            rag.cache_hit(query, cache_type="semantic")
            # ★ 缓存命中后仍需执行数据层级过滤
            # 缓存结果可能来自其他用户，包含当前用户不可见的部门数据
            # deepcopy 解除与缓存后端的引用绑定，防止原地修改污染缓存
            import copy
            cached_result = copy.deepcopy(cached_result)

            # 预取 user_layers，传递给 _filter_by_scope_layer 避免重复查询
            from backend.service.auth.data_layer_service import get_user_layers
            _user_layers = set(get_user_layers(user_id))

            cached_main = cached_result.get("main_results", [])
            cached_case = cached_result.get("case_results", [])
            cached_result["main_results"] = _filter_by_scope_layer(
                cached_main, user_id, _user_layers=_user_layers
            )
            cached_result["case_results"] = _filter_by_scope_layer(
                cached_case, user_id, _user_layers=_user_layers
            )
            cached_result["merged_results"] = (
                cached_result["main_results"] + cached_result["case_results"]
            )
            # 过滤 selected_kbs：移除当前用户不可见的知识库（防止 KB 名称泄露）
            cached_selected = cached_result.get("selected_kbs", [])
            if cached_selected and _user_layers != {0}:
                # 批量查询所有 KB 的层级（避免 N+1 逐条查询）
                cached_kb_ids = [kb.get("id", 0) for kb in cached_selected if kb.get("id")]
                kb_layer_map = {}
                if cached_kb_ids:
                    conn = None
                    try:
                        from backend.db.schema import get_conn
                        conn = get_conn()
                        placeholders = ",".join(["%s"] * len(cached_kb_ids))
                        cur = conn.execute(
                            f"SELECT kb_id, layer_id FROM kb_data_layers WHERE kb_id IN ({placeholders})",
                            cached_kb_ids,
                        )
                        for row in (cur.fetchall() if hasattr(cur, "fetchall") else []):
                            kb_layer_map.setdefault(row["kb_id"], set()).add(row["layer_id"])
                    finally:
                        if conn is not None:
                            conn.close()
                cached_result["selected_kbs"] = [
                    kb for kb in cached_selected
                    if kb_layer_map.get(kb.get("id", 0), {0}) & _user_layers
                ]
            # 丢弃 graphrag_context：它由社区报告合成、不属于任何 chunk 层级，
            # 层级过滤兜不住；缓存条目虽已按 user_id 分片，但历史/兼容写入仍可能带进来。
            cached_result.pop("graphrag_context", None)
            # 社区报告结果丢弃后就没有可用上下文了（main_results 本就为空）→
            # 视为缓存未命中，走完整链路重新生成，避免返回"空结果"。
            if (cached_result.get("retrieval_strategy") or {}).get("method") == METHOD_GLOBAL:
                logger.info("[SemanticCache] 社区报告结果不参与缓存复用，转完整检索")
            else:
                return cached_result

    kb_service = KnowledgeBaseService()

    # ── 预取用户层级（传递给所有检索器，避免重复 DB 查询） ──
    from backend.service.auth.data_layer_service import get_user_layers
    _user_layers = set(get_user_layers(user_id))

    # ── 0. 选库 → 实体门控 → （不够才）查询改写 ──
    #
    # 链路顺序（2026-09-23 定稿，B 方案）：
    #   分类(总结/其他) → 缓存 → 选库 → **实体门控（先 local）**
    #     ├─ 实体够用 → 直接返回实体关联的原文块（不改写、不跑分片检索）
    #     └─ 不够     → 查询改写（换措辞打宽召回）
    #                    → 主查询：实体 local（含图扩展）+ 分片检索
    #                    → 每个改写查询：实体 local（不做图扩展）+ 分片检索
    #                    → 所有路统一 RRF 融合（同块去重 + 多路命中加分）
    #
    # 旧实现是反过来的：先用"分片向量+BM25"基线做门控，分够高就直接返回 → 实体链路对
    # 高分查询完全失效。那个门控的历史理由是"跳过昂贵的图检索（LLM 抽实体）"，
    # 而现在的图检索是确定性 Cypher（零 LLM、几十毫秒），理由已不成立。
    gate_info = None

    # 1. 选库（明确 main_kb_id 则直接用，否则 LLM 自动选库）
    selected_kbs = []
    if main_kb_id is not None:
        kb = kb_service.get_knowledge_base(main_kb_id)
        if kb:
            selected_kbs = [kb]
    else:
        candidate_kbs = kb_service.candidate_kbs_for_route(user_id)
        selected_ids = kb_service.llm_select_kbs(query, user_id, candidate_kbs)
        kb_by_id = {int(kb["id"]): kb for kb in candidate_kbs}
        selected_kbs = [kb_by_id[rid] for rid in selected_ids if rid in kb_by_id]

    if not selected_kbs:
        return {
            "selected_kbs": [],
            "main_results": [],
            "case_results": [],
            "merged_results": [],
        }

    # 2. 分离"历史正确案例"库（硬编码判断）
    #
    # ★ 同时跳过"空知识库"：LLM 选库可能选中一个没有任何文档的库（如"默认知识库"——
    #   历史文档的 kb_id 为 NULL，不归属任何显式库）。对空库检索要付出
    #   embedding 调用 + Milvus 查询（必然零命中，还会触发 pymilvus 的空结果解析报错）
    #   + BM25 全表扫描，全是白做；这里直接跳过，日志里留一行说明。
    def _drop_empty_kbs(kbs: List[dict]) -> List[dict]:
        kept = []
        for kb in kbs:
            try:
                status = get_kb_index_status(int(kb["id"]))
            except Exception:  # noqa: BLE001 —— 状态查不出来就别拦，按有内容处理
                kept.append(kb)
                continue
            if status["vectors"] or status["chunks"]:
                kept.append(kb)
            else:
                logger.info(
                    f"[KB] 跳过空知识库（既无向量也无文本块）: id={kb['id']} name={kb.get('kb_name')}"
                )
        return kept

    case_kb = None
    main_kbs = []
    for kb in selected_kbs:
        if kb.get("kb_name") == case_kb_name:
            case_kb = kb
        else:
            main_kbs.append(kb)

    # 2.5 过滤掉空知识库（见 _drop_empty_kbs 说明）
    main_kbs = _drop_empty_kbs(main_kbs)
    if case_kb is not None:
        case_kb_kept = _drop_empty_kbs([case_kb])
        case_kb = case_kb_kept[0] if case_kb_kept else None

    # 3. 获取检索器（支持 hybrid/bm25/vector/auto 模式）
    # 用于按 kb_id 过滤检索结果的辅助函数
    def _filter_by_kb_id(results: List[dict], target_kb_id: Optional[int]) -> List[dict]:
        """按 kb_id 过滤检索结果（Vector/BM25 已通过 metadata 前置过滤，此处作为额外保障）"""
        if target_kb_id is None:
            return results
        # 通过 chunk_id 查询其所属的 kb_id
        chunk_ids = [r.get("chunk_id") for r in results if r.get("chunk_id")]
        if not chunk_ids:
            return results
        
        # 批量查询 chunk 所属的 kb_id
        kb_id_map = {}
        try:
            conn = get_conn()
            try:
                placeholders = ",".join(["%s"] * len(chunk_ids))
                cur = conn.execute(
                    f"SELECT c.id, COALESCE(c.kb_id, d.kb_id) AS kb_id FROM kb_chunks c "
                    f"LEFT JOIN kb_documents d ON d.id = c.document_id "
                    f"WHERE c.id IN ({placeholders})",
                    tuple(chunk_ids)
                )
                for row in cur.fetchall():
                    kb_id_map[row["id"]] = row["kb_id"]
            finally:
                conn.close()
        except Exception:
            return results  # 查询失败不过滤
        
        # 过滤并保留原有的分数和元数据
        # ★ 默认知识库：kb_id 为空的 chunk 也算属于它
        allow_null = is_default_kb(target_kb_id)
        filtered = []
        for r in results:
            chunk_id = r.get("chunk_id")
            if not chunk_id:
                continue
            eff = kb_id_map.get(chunk_id)
            if eff == target_kb_id or (eff is None and allow_null):
                filtered.append(r)
        return filtered

    def _get_retriever(kb_id: Optional[int] = None) -> tuple:
        """
        获取检索器：支持 hybrid（三路：Vector + BM25 + Graph）、bm25、vector 模式。

        仅服务于**案例路径**（见下方"有意不走自适应链路"的说明）与显式 mode 降级；
        主路径已改为 `AdaptiveRetriever`（实体优先 → 文本块兜底）。
        """
        if mode == "bm25":
            return BM25Retriever(user_id, kb_id=kb_id), "bm25", kb_id
        elif mode == "vector":
            try:
                return VectorRetriever(user_id, kb_id=kb_id), "vector", kb_id
            except Exception:
                return BM25Retriever(user_id, kb_id=kb_id), "bm25", kb_id
        else:  # hybrid / auto
            try:
                # 检查是否有向量数据或图数据可用
                has_vectors = _user_has_vectors(user_id)
                has_graph = False
                try:
                    from backend.infrastructure import get_infrastructure
                    infra = get_infrastructure()
                    has_graph = infra.is_graphrag_available()
                except Exception:
                    pass
                
                if has_vectors or has_graph:
                    # 使用 HybridRetriever（三路：Vector + BM25 + Graph）
                    # 动态权重：根据查询特征调整 Vector/BM25/Graph 权重
                    weights = classify_query_for_weights(query)
                    return HybridRetriever(user_id, kind="all", kb_id=kb_id, weights=weights), "hybrid", kb_id
                else:
                    # 降级为 BM25
                    return BM25Retriever(user_id, kb_id=kb_id), "bm25", kb_id
            except Exception:
                return BM25Retriever(user_id, kb_id=kb_id), "bm25", kb_id

    # 4. 主路径检索（在选中的主库内检索）
    # 多取一些给 Rerank 留余量，同时给 Hybrid 检索留更多余量（因为需要过滤）
    over_fetch = main_top_k * 2 if enable_rerank else main_top_k
    hybrid_multiplier = 3 if mode in ("hybrid", "auto") else 1  # Hybrid 需要多取一些再过滤
    over_fetch = over_fetch * hybrid_multiplier

    main_results = []  # 初始化（防止 main_kbs 为空时未定义）
    graphrag_context = None
    adaptive_retriever = AdaptiveRetriever(user_id)
    retrieval_strategy: Dict[str, Any] = {"kind": retrieval_kind, "method": None}
    rewrite_info = None
    effective_query = query
    all_queries = [query]
    relation_card: Dict[str, Any] = {"tier": "none", "lines": []}
    adaptive_probe: Dict[str, Any] = {"top1_entity_score": 0.0, "strong_entity_count": 0}
    probe_hits: List[dict] = []
    route_lists: List[Tuple[str, List[dict]]] = []  # ★ 提前初始化，供门控放行分支使用

    # ── 4.1 总结型查询 → 社区报告检索（Map-Reduce） ──
    # 命中则不再走文本块检索（社区报告本身就是"全局视角"的产物）
    if retrieval_kind == KIND_SUMMARY:
        summary_ctx = adaptive_retriever.community_report_search(query)
        if summary_ctx:
            graphrag_context = summary_ctx
            retrieval_strategy.update({
                "method": METHOD_GLOBAL,
                "reports_used": summary_ctx.get("reports_used", 0),
                "sources": summary_ctx.get("sources", [])[:5],
            })
        else:
            # 无社区报告 / 报告未生成答案 → 不能返回空，降级到自适应链路
            rag.retrieval_fallback("global", "adaptive", "无社区报告或未生成答案")
            retrieval_kind = KIND_ADAPTIVE
            retrieval_strategy["kind"] = KIND_ADAPTIVE
            retrieval_strategy["fallback_from"] = METHOD_GLOBAL

    if retrieval_strategy["method"] is None and main_kbs:
        # ── 4.2 实体门控：先做一次实体检索，判断"实体这条路够不够用" ──
        #     只检索一次（结果复用给下面的检索），不做图扩展 —— 门控只需知道命中分布。
        probe_hits = adaptive_retriever.search_entities(query) if confidence_gate else []
        adaptive_probe = {
            "top1_entity_score": round(float(probe_hits[0]["score"]), 6) if probe_hits else 0.0,
            "strong_entity_count": adaptive_retriever.count_strong(probe_hits),
        }
        local_confident = bool(probe_hits) and adaptive_retriever.is_confident(probe_hits)

        if local_confident:
            gate_info = {
                "triggered": True,
                "action": "entity_local_hit",
                "top1_entity_score": adaptive_probe["top1_entity_score"],
                "strong_entity_count": adaptive_probe["strong_entity_count"],
                "strong_threshold": get_strong_threshold(),
                "min_strong": get_min_strong_entities(),
            }
            rag.info(
                f"⚡ [Adaptive] 实体门控放行: strong={adaptive_probe['strong_entity_count']} "
                f"≥ {get_min_strong_entities()}, top1={adaptive_probe['top1_entity_score']:.3f} "
                f"→ 直接返回实体关联原文块（跳过改写与分片检索）"
            )
            # ★ 门控放行后直接用探针结果，不再调用 retrieve()
            #    retrieve() 会重新做实体检索 + 图扩展，浪费资源且可能触发 Milvus 错误
            gate_out = adaptive_retriever.retrieve(
                query,
                top_k=over_fetch,
                kb_id=main_kbs[0]["id"] if main_kbs else None,
                mode=mode,
                _user_layers=_user_layers,
                enable_graph_expansion=True,
                enable_entity=True,
                entity_hits=probe_hits,  # 复用探针结果，避免重复 embedding + Milvus
            )
            retrieval_strategy.update({
                "method": gate_out.get("method"),
                "confident": gate_out.get("confident"),
                "seed_entities": gate_out.get("seed_entities", []),
                "entity_hits": gate_out.get("entity_hits", 0),
                "strong_entity_count": gate_out.get("strong_entity_count", 0),
                "top1_entity_score": gate_out.get("top1_entity_score", 0.0),
                "fallback_reason": gate_out.get("fallback_reason"),
                "elapsed_ms": gate_out.get("elapsed_ms", 0),
            })
            card = gate_out.get("relation_card") or {}
            if card.get("tier", "none") != "none":
                relation_card = card
            # 直接使用门控结果，跳过多路检索
            for route_name, items in (gate_out.get("routes") or {}).items():
                if not items:
                    continue
                route_results = []
                for r in items:
                    r = dict(r)
                    r["path"] = "main"
                    r["kb_id"] = main_kbs[0]["id"] if main_kbs else None
                    r["kb_name"] = main_kbs[0].get("kb_name", "") if main_kbs else ""
                    r["retriever"] = route_name
                    r["query_source"] = "original"
                    route_results.append(r)
                route_lists.append((f"main:{main_kbs[0]['id'] if main_kbs else 0}:0:{route_name}", route_results))
            # 设置标记，跳过后面的多路检索
            retrieval_strategy["method"] = gate_out.get("method") or METHOD_ENTITY_LOCAL
        else:
            gate_info = {
                "triggered": False,
                "action": "full_retrieval",
                "top1_entity_score": adaptive_probe["top1_entity_score"],
                "strong_entity_count": adaptive_probe["strong_entity_count"],
                "strong_threshold": get_strong_threshold(),
                "min_strong": get_min_strong_entities(),
            }
            rag.info(
                f"🔍 [Adaptive] 实体门控未放行: strong={adaptive_probe['strong_entity_count']} "
                f"< {get_min_strong_entities()} 或 top1={adaptive_probe['top1_entity_score']:.3f} "
                f"→ 查询改写 + 实体/分片两路补检"
            )
            # ── 4.3 门控未放行 → 查询改写（换措辞打宽召回）──
            do_main = enable_query_rewrite
            do_sub = enable_sub_queries
            do_synonym = enable_synonyms
            if not do_main and auto_rewrite:
                from backend.service.kb.kb_query_rewriter import should_rewrite_query
                do_main, do_sub, do_synonym = should_rewrite_query(query)

            if do_main or do_sub or do_synonym:
                try:
                    from backend.service.kb.kb_query_rewriter import get_query_rewriter
                    rewriter = get_query_rewriter(user_id)
                    if rewriter:
                        result = rewriter.multi_rewrite(
                            query,
                            enable_main=do_main,
                            enable_sub=do_sub,
                            enable_synonym=do_synonym,
                        )
                        effective_query = result.main
                        rewrite_info = result.to_dict()
                        all_queries = result.all_queries()
                        if result.sub_queries or result.synonyms:
                            logger.info(
                                f"📝 查询改写: '{query}' → 主改写 '{result.main}'"
                                f"{', 子查询 ' + str(result.sub_queries) if result.sub_queries else ''}"
                                f"{', 同义 ' + str(result.synonyms) if result.synonyms else ''}"
                            )
                except Exception as e:
                    logger.warning(f"[QueryRewrite] 改写失败，使用原查询: {e}")

    if retrieval_strategy["method"] is None:
        # ── 4.4 多路检索（每条 route×query 一路有序列表）→ 统一 RRF 融合 ──
        per_query_fetch = (
            max(over_fetch // len(all_queries), 3) if len(all_queries) > 1 else over_fetch
        )
        # route_lists 已在上面初始化
        # 门控探针已算过一次实体检索 → 主查询直接复用，避免重复 embedding + Milvus
        reused_hits = probe_hits if gate_info is not None else None

        for kb in main_kbs:
            for i, q in enumerate(all_queries):
                is_main_query = (i == 0)
                out = adaptive_retriever.retrieve(
                    q,
                    top_k=per_query_fetch,
                    kb_id=kb["id"],
                    mode=mode,
                    _user_layers=_user_layers,
                    # 图扩展只给主查询：换措辞不改变"邻居集合"，重复遍历纯浪费
                    enable_graph_expansion=is_main_query,
                    enable_entity=enable_entity_search,
                    entity_hits=reused_hits if is_main_query else None,
                )
                label = f"{'main' if is_main_query else 'rewrite'}:{kb['id']}:{i}"

                # 记录主查询的链路信息（可观测性 + 测试断言）
                if is_main_query and retrieval_strategy["method"] is None:
                    retrieval_strategy.update({
                        "method": out.get("method"),
                        "confident": out.get("confident"),
                        "seed_entities": out.get("seed_entities", []),
                        "entity_hits": out.get("entity_hits", 0),
                        "strong_entity_count": out.get("strong_entity_count", 0),
                        "top1_entity_score": out.get("top1_entity_score", 0.0),
                        "fallback_reason": out.get("fallback_reason"),
                        "elapsed_ms": out.get("elapsed_ms", 0),
                    })
                    card = out.get("relation_card") or {}
                    if card.get("tier", "none") != "none":
                        relation_card = card

                # 每一路单独成 list 喂给 RRF：拼成一个 list 会让两路的 rank1 相互穿插，
                # RRF 的"排名"语义就被破坏了
                for route_name, items in (out.get("routes") or {}).items():
                    if not items:
                        continue
                    route_results = []
                    for r in items:
                        r = dict(r)
                        r["path"] = "main"
                        r["kb_id"] = kb["id"]
                        r["kb_name"] = kb.get("kb_name", "")
                        r["retriever"] = route_name
                        r["query_source"] = q if q != query else "original"
                        if not is_main_query:
                            r["skip_graph"] = True  # P1 标记
                        route_results.append(r)
                    route_lists.append((f"{label}:{route_name}", route_results))

        fused_top_k = main_top_k * 2 if enable_rerank else main_top_k
        if route_lists:
            if len(route_lists) == 1:
                main_results = route_lists[0][1][:fused_top_k]
            else:
                main_results = _rrf_fuse_multi_query(route_lists, top_k=fused_top_k)
                logger.info(
                    f"🔀 RRF 融合: {len(route_lists)} 路 → {len(main_results)} 条（同块已去重，"
                    f"多路命中叠加加分）"
                )
            for r in main_results:
                if "kb_id" not in r and main_kbs:
                    r["kb_id"] = main_kbs[0]["id"]
                    r["kb_name"] = main_kbs[0].get("kb_name", "")

    # 5. 案例路径检索（案例库单独召回，只用主改写结果）
    #
    # ⚠️ 有意不走自适应链路（实体 local）：案例库存的是 **SQL 示例文本**，
    #    "用哪条历史正确案例做 few-shot" 靠的是与 query 的文本相似度，
    #    而不是"命中了哪个实体"；走实体检索会把"命中了 `orders` 实体"的案例
    #    排在"与 query 最相似的案例"前面，反而降低 few-shot 质量。
    #    因此这里保持"文本块检索（Vector + BM25 + 动态 RRF 权重）+ 跳过图检索"。
    case_over_fetch = case_top_k * 2 if enable_rerank else case_top_k
    case_over_fetch = case_over_fetch * hybrid_multiplier  # Hybrid 需要多取
    case_results = []
    if case_kb:
        case_retriever, case_retriever_name, case_filter_kb_id = _get_retriever(case_kb["id"])

        # 案例路径始终跳过 Graph（案例库以文本匹配为主，图遍历收益低）
        # skip_graph 只有 HybridRetriever 支持，BM25/Vector 不支持（传了会 TypeError）
        if case_retriever_name == "hybrid":
            case_results = case_retriever.retrieve(
                effective_query, top_k=case_over_fetch, skip_graph=True, _user_layers=_user_layers
            )
        else:
            case_results = case_retriever.retrieve(
                effective_query, top_k=case_over_fetch, _user_layers=_user_layers
            )

        # HybridRetriever 结果需要按 kb_id 过滤
        if case_retriever_name == "hybrid" and case_filter_kb_id is not None:
            case_results = _filter_by_kb_id(case_results, case_filter_kb_id)

        for r in case_results:
            r["path"] = "case"
            r["kb_id"] = case_kb["id"]
            r["kb_name"] = case_kb.get("kb_name", "")
            r["retriever"] = case_retriever_name

    # 5.5 GraphRAG 社区上下文：
    # 已由 Step 4.1（总结型 → 社区报告检索）产出；此处不再做 DRIFT 兜底，
    # 其他查询统一走"实体 local → 文本块"自适应链路。

    # 6. Rerank 精排（可选，使用主改写结果）
    if enable_rerank and _rerank_enabled():
        if main_results:
            main_results = _rerank_items(effective_query, main_results, main_top_k)
        if case_results:
            case_results = _rerank_items(effective_query, case_results, case_top_k)
    else:
        # 无 Rerank 时直接截断
        main_results = main_results[:main_top_k]
        case_results = case_results[:case_top_k]

    # 7. CRAG 质量评估
    # 社区报告命中时 main_results 本就为空（答案在 graphrag_context 里），
    # 不能按"空结果"处理，否则会触发下面的 BM25/Web 纠正把社区答案稀释掉。
    community_hit = bool(
        graphrag_context and retrieval_strategy.get("method") == METHOD_GLOBAL
    )
    if community_hit:
        quality_assessment = {
            "quality": "high",
            "top1_score": 1.0,
            "avg_score": 1.0,
            "result_count": 0,
            "action": "return",
            "source": "community_report",
            "reason": f"社区报告检索: {retrieval_strategy.get('reports_used', 0)} 份报告",
        }
    else:
        quality_assessment = assess_retrieval_quality(main_results, effective_query)
        if quality_assessment["quality"] in ("low", "empty"):
            logger.info(f"[CRAG] {quality_assessment['reason']}")

    # 9. CRAG 纠正：Empty BM25 Fallback（去掉 kb_id 过滤，全库 BM25 重查）
    if not community_hit and quality_assessment["quality"] == "empty":
        rag.crag_action("bm25_fallback", "去掉 kb_id 过滤")
        try:
            fallback_bm25 = BM25Retriever(user_id, kind="all", kb_id=None)
            fallback_results = fallback_bm25.retrieve(effective_query, top_k=main_top_k, _user_layers=_user_layers)
            if fallback_results:
                for r in fallback_results:
                    r["path"] = "main"
                    r["retriever"] = "bm25_fallback_all"
                main_results = fallback_results
                merged_results = main_results + case_results
                quality_assessment = assess_retrieval_quality(main_results, effective_query)
                logger.info(
                    f"[CRAG] BM25 fallback 后: {len(main_results)} 条, "
                    f"quality={quality_assessment['quality']}"
                )
        except Exception as e:
            logger.warning(f"[CRAG] BM25 fallback 失败: {e}")

    # 10. CRAG 纠正：Web Search Fallback（知识库全无结果时联网搜索兜底）
    if not community_hit and enable_web_fallback and quality_assessment["quality"] == "empty":
        rag.crag_action("web_fallback", "知识库无结果")
        web_results = _web_search_fallback(effective_query, top_k=main_top_k)
        if web_results:
            main_results = web_results
            merged_results = main_results + case_results
            quality_assessment = assess_retrieval_quality(main_results, effective_query)
            quality_assessment["source"] = "web_search"
            rag.crag_action("web_fallback", f"成功: {len(main_results)} 条结果")

    # 11. 数据层级过滤 — 已由 VectorRetriever / BM25Retriever 内部自动完成
    # （检索器在返回前调用 _filter_by_scope_layer，确保 chunk 级安全边界）
    merged_results = main_results + case_results

    # 获取实际使用的检索器名称（用于日志）
    actual_retriever = "bm25"
    if main_results:
        actual_retriever = main_results[0].get("retriever", "bm25")
    elif case_results:
        actual_retriever = case_results[0].get("retriever", "bm25")

    # 构建优化摘要
    opt_flags = []
    if (gate_info or {}).get("triggered"):
        opt_flags.append("实体门控放行⚡")
    if rewrite_info:
        opt_flags.append("查询改写")
    if len(all_queries) > 1:
        opt_flags.append("RRF融合")
    if relation_card.get("tier", "none") != "none":
        opt_flags.append(f"关系卡片[{relation_card['tier']}]")

    logger.info(
        f"📊 双路召回完成: 选中 {len(selected_kbs)} 个库, "
        f"主路径 {len(main_results)} 条, 案例路径 {len(case_results)} 条"
        f", 链路={retrieval_strategy.get('kind')}/{retrieval_strategy.get('method')}"
        f"{', 社区报告 ' + str(retrieval_strategy.get('reports_used')) + ' 份' if community_hit else ''}"
        f"{', 种子实体 ' + str(retrieval_strategy.get('seed_entities')[:3]) if retrieval_strategy.get('seed_entities') else ''}"
        f", 检索模式={actual_retriever}"
        f"{', Rerank 已启用' if enable_rerank and _rerank_enabled() else ''}"
        f"{', ' + '+'.join(opt_flags) if opt_flags else ''}"
    )

    result = {
        "selected_kbs": selected_kbs,
        "main_results": main_results,
        "case_results": case_results,
        "merged_results": merged_results,
        "retrieval_strategy": retrieval_strategy,
    }
    if graphrag_context:
        result["graphrag_context"] = graphrag_context
    if rewrite_info:
        result["query_rewrite"] = rewrite_info
    if gate_info:
        result["confidence_gate"] = gate_info
    if relation_card.get("tier", "none") != "none":
        result["relation_card"] = relation_card
    result["quality_assessment"] = quality_assessment
    if adaptive_result:
        result["adaptive_routing"] = {
            "complexity": adaptive_result.complexity.value,
            "reason": adaptive_result.reason,
        }

    # 写入语义缓存（仅缓存非 fallback 的正常结果）
    # 社区报告结果不写缓存：它在命中分支会被丢弃 graphrag_context（层级过滤兜不住），
    # 写进去只会得到一条永远不能复用的条目。
    if enable_semantic_cache and not community_hit and quality_assessment.get("source") != "web_search":
        from backend.service.kb.kb_semantic_cache import write_semantic_cache
        try:
            write_semantic_cache(query, result, user_id)
        except Exception as e:
            logger.debug(f"[SemanticCache] 写缓存失败: {e}")

    return result


# ════════════════════════════════════════════════════════════
# Rerank 精排（DashScope gte-rerank）
# ════════════════════════════════════════════════════════════

def _get_rerank_config() -> Optional[dict]:
    """从数据库获取当前激活的 Rerank 模型配置（带 Redis 缓存，10min TTL）。

    Returns:
        {"api_url": str, "api_key": str, "model_name": str} 或 None（未配置/未激活）
    """
    # 尝试从缓存获取
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.build("kb", "rerank", "config")
    empty_key = kb.build("kb", "rerank", "config:empty")  # 空值标记

    # 检查是否是空值标记
    if cache.get(empty_key) is not None:
        return None

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 缓存 miss，查数据库
    try:
        from backend.db.connection_pool import get_pool_connection
        conn = get_pool_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT api_url, api_key, model_name FROM model_configs "
                "WHERE category = 'rerank' AND is_current = 1 AND enabled = 1 LIMIT 1"
            )
            row = cur.fetchone()
            if not row:
                # 缓存空结果标记（避免频繁查库）
                cache.set_with_jitter(empty_key, True, base_ttl=600, jitter_range=60)
                return None
            # 解密 api_key
            from backend.utils.crypto_utils import decrypt
            api_key = decrypt(row.get("api_key") or "") if row.get("api_key") else ""
            config = {
                "api_url": (row.get("api_url") or "").strip(),
                "api_key": api_key,
                "model_name": (row.get("model_name") or "").strip(),
            }
            # 写入缓存（10min TTL + 1min jitter）
            cache.set_with_jitter(cache_key, config, base_ttl=600, jitter_range=60)
            return config
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"获取 Rerank 配置失败: {exc}")
        return None


def _rerank_enabled() -> bool:
    """是否启用 Rerank 精排（检查数据库是否有激活的 Rerank 配置）。"""
    return _get_rerank_config() is not None


def _rerank_items(query: str, items: List[dict], top_k: int) -> List[dict]:
    """
    调用 Rerank API 对检索结果进行精排。

    Args:
        query: 原始查询
        items: 待精排的检索结果列表
        top_k: 返回数量

    Returns:
        精排后的结果列表（失败时返回原顺序）
    """
    if not items:
        return items[:top_k]

    rerank_config = _get_rerank_config()
    if not rerank_config:
        return items[:top_k]

    api_url = rerank_config["api_url"]
    api_key = rerank_config["api_key"]
    model = rerank_config["model_name"] or "gte-rerank-v2"

    if not api_url or not api_key:
        return items[:top_k]

    # 构造 Rerank API 端点（兼容 DashScope 格式）
    endpoint = api_url.rstrip("/")
    if not endpoint.endswith("/rerank"):
        endpoint = f"{endpoint}/rerank"

    timeout = float(os.getenv("RAG_RERANK_TIMEOUT", "20") or 20)

    # 构造 documents：每条 = 来源 + 标题 + 内容前 1800 字
    documents = []
    for item in items:
        content = (item.get("content") or "")[:1800]
        doc_name = item.get("doc_name") or item.get("document_name") or ""
        heading = item.get("heading") or ""
        doc_text = "\n".join(filter(None, [doc_name, heading, content]))
        documents.append(doc_text)

    payload = {
        "model": model,
        "input": {
            "query": query or "",
            "documents": documents,
        },
        "parameters": {
            "top_n": min(max(top_k, 1), len(items)),
            "return_documents": False,
        },
    }

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))

        results = (data.get("output") or {}).get("results") or data.get("results") or []
        ranked = []
        used_indexes = set()

        for result in results:
            index = result.get("index")
            if index is None:
                index = result.get("document_index")
            try:
                index = int(index)
            except Exception:
                continue
            if index < 0 or index >= len(items):
                continue

            item = dict(items[index])
            item["pre_rerank_rank"] = index + 1
            item["pre_rerank_score"] = item.get("score")
            rerank_score = result.get("relevance_score", result.get("score", 0))
            item["rerank_score"] = round(float(rerank_score or 0), 6)
            item["rerank_model"] = model
            ranked.append(item)
            used_indexes.add(index)

        if ranked:
            # 按 rerank_score 降序排列
            ranked.sort(
                key=lambda x: (
                    float(x.get("rerank_score") or 0),
                    -int(x.get("pre_rerank_rank") or 999999),
                ),
                reverse=True,
            )
            # 补充未被 rerank 选中的项（兜底）
            if len(ranked) < top_k:
                for index, item in enumerate(items):
                    if index in used_indexes:
                        continue
                    fallback = dict(item)
                    fallback["pre_rerank_rank"] = index + 1
                    fallback["pre_rerank_score"] = fallback.get("score")
                    fallback["rerank_model"] = model
                    fallback["rerank_fallback"] = True
                    ranked.append(fallback)
                    if len(ranked) >= top_k:
                        break
            rag.rerank(len(items), len(ranked), method="external", latency_ms=None)
            return ranked[:top_k]

    except Exception as exc:
        rag.retrieval_fallback("rerank", "llm_rerank", str(exc))
        # 尝试用 LLM 进行 Rerank
        return _llm_rerank_items(query, items, top_k)

    return items[:top_k]


def _llm_rerank_items(query: str, items: List[dict], top_k: int) -> List[dict]:
    """
    使用 Chat 模型进行 Rerank（当专业 Rerank API 不可用时的备选方案）。
    
    原理：
    - 将 query 和文档列表发送给 LLM
    - LLM 对每个文档的相关性打分（0-10）
    - 根据分数排序
    
    Args:
        query: 原始查询
        items: 待精排的检索结果列表
        top_k: 返回数量

    Returns:
        精排后的结果列表
    """
    if not items:
        return items[:top_k]
    
    # 获取 LLM 配置 — 改用 TracedLLMClient
    # （不再需要 get_llm_for_rerank，traced_llm 内部走场景路由）
    
    # 构造文档列表
    documents = []
    for i, item in enumerate(items):
        content = (item.get("content") or "")[:500]  # 限制长度
        documents.append(f"[{i}] {content}")
    
    # 构造 Prompt
    prompt = f"""你是一个搜索结果排序专家。请根据用户问题，对以下搜索结果进行相关性评分。

用户问题：{query}

搜索结果：
{chr(10).join(documents)}

请对每个搜索结果打分（0-10分，10分最相关），输出格式如下：
[0]: 分数
[1]: 分数
...

只输出打分结果，不要有其他内容。"""

    try:
        # 调用 LLM（通过 TracedLLMClient）
        from backend.utils.traced_llm import traced_llm
        
        # 尝试从上下文获取 user_id
        try:
            from backend.hermes_adapter import _CURRENT_USER_ID_CTX
            uid = int(_CURRENT_USER_ID_CTX.get() or 0)
        except Exception:
            uid = 0

        resp = traced_llm.invoke(
            messages=[{"role": "user", "content": prompt}],
            scene="rag_rerank",
            user_id=uid,
            source="rag",
            temperature=0,
            max_tokens=500,
        )
        response_text = resp.content or ""
        
        # 解析分数
        import re
        scores = {}
        for line in response_text.strip().split('\n'):
            match = re.match(r'\[(\d+)\][\s:]+(\d+(?:\.\d+)?)', line.strip())
            if match:
                idx = int(match.group(1))
                score = float(match.group(2))
                if 0 <= idx < len(items):
                    scores[idx] = score
        
        if not scores:
            logger.warning("LLM Rerank 未解析到有效分数")
            return items[:top_k]
        
        # 按分数排序
        ranked = []
        for idx, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            item = dict(items[idx])
            item["pre_rerank_rank"] = idx + 1
            item["pre_rerank_score"] = item.get("score")
            item["rerank_score"] = round(score / 10, 4)  # 归一化到 0-1
            item["rerank_model"] = "llm_rerank"
            ranked.append(item)
        
        # 补充未被打分的项
        scored_indexes = set(scores.keys())
        if len(ranked) < top_k:
            for idx, item in enumerate(items):
                if idx in scored_indexes:
                    continue
                fallback = dict(item)
                fallback["pre_rerank_rank"] = idx + 1
                fallback["pre_rerank_score"] = fallback.get("score")
                fallback["rerank_model"] = "llm_rerank"
                fallback["rerank_fallback"] = True
                ranked.append(fallback)
                if len(ranked) >= top_k:
                    break
        
        rag.rerank(len(items), len(ranked[:top_k]), method="llm", latency_ms=None)
        return ranked[:top_k]
        
    except Exception as e:
        logger.warning(f"LLM Rerank 失败: {e}")
        return items[:top_k]


# ════════════════════════════════════════════════════════════
# 混合检索（RRF 融合）
# ════════════════════════════════════════════════════════════

class GraphRetriever:
    """
    知识图谱检索器
    
    基于 Neo4j 图遍历检索：
    1. 从查询中提取实体
    2. 找到实体关联的 chunk（通过 source_chunk_id）
    3. 扩展 1-2 跳找到相关 chunk
    
    参考 AGI-saber 的 KGStore.search 实现
    """
    
    name = "graph"
    
    def __init__(self, user_id: int, max_hops: int = 2):
        self.user_id = user_id
        self.max_hops = max_hops
        self._kg_store = None
    
    def _get_kg_store(self):
        """获取 KGStore（延迟加载）"""
        if self._kg_store is None:
            from backend.graphrag.kg_store import get_kg_store
            self._kg_store = get_kg_store()
        return self._kg_store
    
    def retrieve(self, query: str, top_k: int = 5, _user_layers: Optional[set] = None) -> List[dict]:
        """
        图检索：从查询提取实体 → 遍历图谱 → 返回关联的 chunk 或 memory

        优化：使用 kg_store.retrieve_by_query() 复用图谱检索逻辑
        同时自动更新实体访问统计（用于冷热分离）

        支持两种来源：
        - source_chunk_id: 文档图谱实体 → 返回 chunk
        - source_memory_id: 记忆图谱实体 → 返回 memory

        降级策略：当图检索返回 0 结果时，自动降级到 hybrid 检索。

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            [{"chunk_id": int, "score": float, "entities": [...], "context": str, "retrieval_source": str}, ...]
            或
            [{"memory_id": int, "score": float, "entities": [...], "content": str, "retrieval_source": str}, ...]
        """
        if not query.strip():
            return []

        kg_store = self._get_kg_store()
        if not kg_store.is_available():
            logger.debug("[KG] Neo4j 不可用，跳过图检索")
            return self._fallback_to_hybrid(query, top_k)

        try:
            # 使用 kg_store 的新增方法（自动更新访问统计）
            graph_results = kg_store.retrieve_by_query(
                query=query,
                user_id=self.user_id,
                top_k=top_k * 2  # 多取一些，后面去重
            )

            if not graph_results:
                logger.debug("[KG] 图检索返回 0 结果，降级到 hybrid")
                return self._fallback_to_hybrid(query, top_k)

            # 转换为 HybridRetriever 期望的格式
            out = []
            seen_chunks = set()
            seen_memories = set()

            for r in graph_results:
                entity = r.get("entity")
                context = r.get("context", "")
                score = r.get("score", 0.5)
                chunk_id = r.get("source_chunk_id")
                memory_id = r.get("source_memory_id")  # 记忆来源

                # 情况 1：来自文档 chunk
                if chunk_id is not None:
                    if chunk_id in seen_chunks:
                        continue
                    seen_chunks.add(chunk_id)
                    out.append({
                        "chunk_id": int(chunk_id),
                        "score": round(score, 6),
                        "entities": [entity.name] if entity else [],
                        "context": context,
                        "retrieval_source": "graph"
                    })

                # 情况 2：来自永久记忆（source_memory_id 不为 None）
                elif memory_id is not None:
                    if memory_id in seen_memories:
                        continue
                    seen_memories.add(memory_id)
                    out.append({
                        "memory_id": int(memory_id),
                        "score": round(score, 6),
                        "entities": [entity.name] if entity else [],
                        "context": context,
                        "retrieval_source": "graph_memory"
                    })

                # 情况 3：两者都没有（理论上不应该出现，跳过）
                else:
                    continue

                if len(out) >= top_k:
                    break

            # 补充 chunk 内容（文档来源）
            chunk_results = [r for r in out if "chunk_id" in r]
            if chunk_results:
                chunk_ids = [r["chunk_id"] for r in chunk_results]
                chunks = self._load_chunks_by_ids(chunk_ids)
                chunk_map = {c["id"]: c for c in chunks}
                for r in chunk_results:
                    c = chunk_map.get(r["chunk_id"])
                    if c:
                        r["content"] = c.get("content", "")
                        r["document_id"] = c.get("document_id")
                        r["kind"] = c.get("kind", "base")

            # 补充 memory 内容（记忆来源）
            memory_results = [r for r in out if "memory_id" in r]
            if memory_results:
                memory_ids = [r["memory_id"] for r in memory_results]
                memories = self._load_memories_by_ids(memory_ids, self.user_id)
                memory_map = {m["id"]: m for m in memories}
                # 只保留**确实属于本用户**的记忆结果（取不到 = 非本用户或已删除 → 丢弃）
                memory_results = [r for r in memory_results if r["memory_id"] in memory_map]
                out = [r for r in out if "memory_id" not in r or r["memory_id"] in memory_map]
                for r in memory_results:
                    m = memory_map[r["memory_id"]]
                    r["content"] = m.get("content", "")
                    r["memory_type"] = m.get("memory_type", "semantic")
                    # 带出归属，供 _filter_by_scope_layer 做二次校验
                    r["user_id"] = m.get("user_id", self.user_id)

            logger.debug(f"[KG] 图检索完成: {len(chunk_results)} chunks, {len(memory_results)} memories")
            # ★ 数据层级过滤（安全边界：确保只返回用户可见的 chunk/memory）
            return _filter_by_scope_layer(out, self.user_id, _user_layers=_user_layers)

        except Exception as e:
            rag.retrieval_fallback("kg", "hybrid", str(e))
            return self._fallback_to_hybrid(query, top_k)

    def _fallback_to_hybrid(self, query: str, top_k: int) -> List[dict]:
        """降级到 Vector + BM25（不包含 Graph，避免循环依赖）"""
        results = []

        try:
            vector = VectorRetriever(user_id=self.user_id)
            results.extend(vector.retrieve(query, top_k))
        except Exception as e:
            logger.debug(f"[KG] Vector fallback failed: {e}")

        try:
            bm25 = BM25Retriever(user_id=self.user_id)
            results.extend(bm25.retrieve(query, top_k))
        except Exception as e:
            logger.debug(f"[KG] BM25 fallback failed: {e}")

        # 去重
        seen = set()
        deduped = []
        for r in results:
            cid = r.get("chunk_id")
            if cid and cid not in seen:
                seen.add(cid)
                deduped.append(r)
        return sorted(deduped, key=lambda x: x.get("score", 0), reverse=True)[:top_k]
    
    def _search_direct(self, entity_names: List[str], top_k: int) -> List[dict]:
        """APOC 不可用时的降级版本：直接匹配实体"""
        kg_store = self._get_kg_store()
        client = kg_store._get_graph_client()
        if not client:
            return []
        
        try:
            cypher = """
            MATCH (e:Entity)
            WHERE e.name IN $names AND e.source_chunk_id IS NOT NULL
            AND (e.user_id = $user_id OR e.user_id IS NULL)
            RETURN e.source_chunk_id AS cid, e.name AS name
            LIMIT $limit
            """
            results = client.run_query(cypher, {
                "names": entity_names,
                "user_id": self.user_id,
                "limit": top_k
            })
            
            out = []
            seen = set()
            for r in results or []:
                chunk_id = r.get("cid")
                if chunk_id is None or chunk_id in seen:
                    continue
                seen.add(chunk_id)
                out.append({
                    "chunk_id": int(chunk_id),
                    "score": 1.0,
                    "entities": [r.get("name", "")],
                    "retrieval_source": "graph"
                })
            return out
        except Exception:
            return []
    
    def _load_chunks_by_ids(self, chunk_ids: List[int]) -> List[dict]:
        """根据 chunk_id 列表加载 chunk 内容"""
        if not chunk_ids:
            return []
        conn = get_conn()
        try:
            placeholders = ",".join(["%s"] * len(chunk_ids))
            cur = conn.execute(
                f"SELECT id, document_id, content, kind FROM kb_chunks WHERE id IN ({placeholders})",
                tuple(chunk_ids)
            )
            return cur.fetchall() if hasattr(cur, "fetchall") else []
        finally:
            conn.close()

    def _load_memories_by_ids(self, memory_ids: List[int], user_id: int) -> List[dict]:
        """
        根据 memory_id 列表加载记忆内容（**按 user_id 归属过滤**）

        优先从 semantic 层加载（主要来源），
        如果 semantic 层找不到，再从 episodic 层找。

        ⚠️ 必须带 user_id 条件：memory_semantic / memory_episodic 的 id 是各自独立
        自增的，仅按 `id IN (...)` 查询会**取到别的用户的记忆正文**，而图检索的记忆
        结果没有 chunk_id，会被层级过滤当成"无 chunk_id → 保留"直接放进 LLM prompt
        → 跨租户记忆泄漏。这里在数据源处就过滤掉非本用户的记录（并把 user_id 带出来
        供下游 `_filter_by_scope_layer` 做二次归属校验）。
        """
        if not memory_ids:
            return []

        results = []
        conn = get_conn()
        try:
            placeholders = ",".join(["%s"] * len(memory_ids))

            # 1. 从 semantic 层查询（主要来源）
            cur = conn.execute(
                f"SELECT id, user_id, content, memory_type FROM memory_semantic "
                f"WHERE id IN ({placeholders}) AND deleted_at IS NULL AND user_id = %s",
                tuple(memory_ids) + (user_id,)
            )
            results.extend(cur.fetchall() if hasattr(cur, "fetchall") else [])

            # 2. 找出未命中的 ID，从 episodic 层查询
            found_ids = {r["id"] for r in results}
            missing_ids = [mid for mid in memory_ids if mid not in found_ids]

            if missing_ids:
                placeholders2 = ",".join(["%s"] * len(missing_ids))
                cur2 = conn.execute(
                    f"SELECT id, user_id, content, memory_type FROM memory_episodic "
                    f"WHERE id IN ({placeholders2}) AND deleted_at IS NULL AND user_id = %s",
                    tuple(missing_ids) + (user_id,)
                )
                results.extend(cur2.fetchall() if hasattr(cur2, "fetchall") else [])

            return results
        finally:
            conn.close()


class HybridRetriever:
    """
    三路混合检索：Vector + BM25 + Graph → RRF（Reciprocal Rank Fusion）融合。

    参考 AGI-saber 的 HybridStore 实现：
    - Milvus 语义检索
    - BM25 关键词检索
    - Neo4j 知识图谱检索
    - 三路 RRF 融合

    RRF 公式：score(d) = Σ weight_i / (k + rank_i(d))
    其中 k=60（经验常数），rank 从 1 开始。
    同 chunk_id 多路命中的分数会叠加，实现「多路投票」效果。

    权重配置：
    - semantic_weight: 语义检索权重（默认 0.4）
    - kg_weight: 图检索权重（默认 0.2）
    - keyword_weight: 关键词检索权重（自动计算 = 1 - semantic_weight - kg_weight）

    任一路不可用时自动跳过，剩余权重重新归一化。

    性能优化（P1）：
    - skip_graph=True 时跳过图检索（用于改写查询，避免重复 LLM 调用）
    """

    name = "hybrid"
    _RRF_K = 60  # RRF 平滑常数
    _SEMANTIC_WEIGHT = 0.4  # 语义检索权重
    _KG_WEIGHT = 0.2        # 图检索权重

    def __init__(self, user_id: int, kind: str = "all", kb_id: Optional[int] = None,
                 weights: Optional[dict] = None):
        self.user_id = user_id
        self.kind = kind
        self.kb_id = kb_id
        # 动态权重（改进 2）：根据查询类型调整 Vector/BM25/Graph 权重
        if weights:
            self._SEMANTIC_WEIGHT = weights.get("semantic", 0.4)
            self._KG_WEIGHT = weights.get("kg", 0.2)
        self._vector = VectorRetriever(user_id, kind=kind, kb_id=kb_id)
        self._bm25 = BM25Retriever(user_id, kind=kind, kb_id=kb_id)
        self._graph = GraphRetriever(user_id)

    def retrieve(self, query: str, top_k: int = 5, skip_graph: bool = False,
                 _user_layers: Optional[set] = None) -> List[dict]:
        """
        三路混合检索。

        Args:
            query: 检索查询
            top_k: 返回数量
            skip_graph: 是否跳过图检索（P1 优化：改写查询跳过，避免重复 LLM 实体提取）
            _user_layers: 预取的用户层级（由调用方传入避免重复 DB 查询）
        """
        if not query.strip():
            return []

        # 预取用户层级（传递给子检索器，避免各检索器重复查询 get_user_layers）
        if _user_layers is None:
            from backend.service.auth.data_layer_service import get_user_layers
            _user_layers = set(get_user_layers(self.user_id))

        # 各路独立检索（各取 top_k * 2 保证融合后有余量）
        over_fetch = min(top_k * 2, 20)

        # Vector 检索
        vector_results = []
        try:
            vector_results = self._vector.retrieve(query, over_fetch, _user_layers=_user_layers)
        except Exception as e:
            rag.retrieval_fallback("vector", "bm25", str(e))

        # BM25 检索
        bm25_results = []
        try:
            bm25_results = self._bm25.retrieve(query, over_fetch, _user_layers=_user_layers)
        except Exception as e:
            logger.debug(f"[Hybrid] BM25 检索失败: {e}")

        # Graph 检索（skip_graph=True 时跳过，用于改写查询避免重复 LLM 调用）
        graph_results = []
        if not skip_graph:
            try:
                graph_results = self._graph.retrieve(query, over_fetch, _user_layers=_user_layers)
            except Exception as e:
                logger.debug(f"[Hybrid] Graph 检索失败: {e}")
        else:
            logger.debug(f"[Hybrid] 跳过图检索 (skip_graph=True, query={query[:30]}...)")

        # 检查各路是否成功
        vector_ok = bool(vector_results)
        bm25_ok = bool(bm25_results)
        graph_ok = bool(graph_results)

        # 全失败
        if not vector_ok and not bm25_ok and not graph_ok:
            logger.warning("[Hybrid] 检索均失败")
            return []

        # 计算归一化权重
        weights = self._normalize_weights(vector_ok, bm25_ok, graph_ok)

        # RRF 融合（支持 chunk_id 和 memory_id 两种标识）
        rrf_scores: Dict[str, float] = {}   # result_key -> rrf_score
        chunk_data: Dict[str, dict] = {}     # result_key -> first-seen result dict

        def _result_key(r: dict):
            """优先用 chunk_id，降级用 memory_id"""
            cid = r.get("chunk_id")
            if cid is not None:
                return f"c:{cid}"
            mid = r.get("memory_id")
            if mid is not None:
                return f"m:{mid}"
            return None

        # Vector 路贡献
        if vector_ok:
            sem_w = weights["semantic"]
            for rank, r in enumerate(vector_results, start=1):
                key = _result_key(r)
                if key is None:
                    continue
                rrf_scores[key] = rrf_scores.get(key, 0.0) + sem_w / (self._RRF_K + rank)
                if key not in chunk_data:
                    chunk_data[key] = r

        # BM25 路贡献
        if bm25_ok:
            kw_w = weights["keyword"]
            for rank, r in enumerate(bm25_results, start=1):
                key = _result_key(r)
                if key is None:
                    continue
                rrf_scores[key] = rrf_scores.get(key, 0.0) + kw_w / (self._RRF_K + rank)
                if key not in chunk_data:
                    chunk_data[key] = r

        # Graph 路贡献
        if graph_ok:
            kg_w = weights["kg"]
            for rank, r in enumerate(graph_results, start=1):
                key = _result_key(r)
                if key is None:
                    continue
                rrf_scores[key] = rrf_scores.get(key, 0.0) + kg_w / (self._RRF_K + rank)
                if key not in chunk_data:
                    chunk_data[key] = r

        # 按 RRF 分降序排列，取 top_k
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)[:top_k]

        out = []
        for key in sorted_keys:
            r = dict(chunk_data[key])
            r["score"] = round(rrf_scores[key], 6)  # 用 RRF 分作为综合分数
            r["retrieval_source"] = "hybrid"
            out.append(r)
        return out
    
    def _normalize_weights(self, vector_ok: bool, bm25_ok: bool, graph_ok: bool) -> dict:
        """归一化权重（不可用的路跳过，剩余权重重新归一）"""
        sem_w = self._SEMANTIC_WEIGHT if vector_ok else 0.0
        kg_w = self._KG_WEIGHT if graph_ok else 0.0
        kw_w = 1.0 - sem_w - kg_w if bm25_ok else 0.0
        
        total = sem_w + kg_w + kw_w
        if total <= 0:
            return {"semantic": 0.33, "keyword": 0.33, "kg": 0.34}
        
        return {
            "semantic": sem_w / total,
            "keyword": kw_w / total,
            "kg": kg_w / total
        }


def _user_has_vectors(user_id: int) -> bool:
    """该用户是否有任何已向量化文档（带 Redis 缓存，1min TTL）。

    粗粒度判断，避免无谓的向量检索空转。
    """
    # 尝试从缓存获取
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.build("kb", "user", user_id, "has_vectors")

    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)

    # 缓存 miss，查数据库
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_documents WHERE user_id = ? AND vectorized = 1",
            (user_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        has_vec = bool(rows and rows[0].get("cnt"))
    finally:
        conn.close()

    # 写入缓存（1min TTL + 10s jitter）
    cache.set_with_jitter(cache_key, has_vec, base_ttl=60, jitter_range=10)

    return has_vec


# ════════════════════════════════════════════════════════════
# 知识库索引状态（Redis 缓存）
# ════════════════════════════════════════════════════════════

def get_kb_index_status(kb_id: int) -> Dict[str, bool]:
    """
    某个知识库是否有可检索内容（向量 / 文本块），带 Redis 缓存（60s TTL）。

    为什么要有这个判断：
    1. **避免 Milvus 空结果解析 Bug**：过滤条件命中 0 行时，pymilvus 3.0.1 会在
       结果解析阶段抛 `MilvusException: Unsupported field type: 0`（实测：
       `kb_id == 1` / `kb_id > 9999` 这类零命中过滤必现，`kb_id == 5` 正常）。
       对"整个库都没数据"的情况直接跳过检索，既不报错也不刷 traceback。
    2. **省一次空转**：向量检索要调 embedding API + Milvus，BM25 要全表扫 chunk 建索引；
       空库上这些工作全是白做（实测每次多花 ~1s 并产生 20+ 行 ERROR 日志）。

    ★ 默认知识库特例：`kb_documents.kb_id IS NULL` 的文档语义上属于"默认知识库"，
    所以查该库时要把它们一并算进来（否则"默认知识库"恒被判为空而被跳过）。
    """
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.build("kb", "kb", int(kb_id), "index_status", "v2")

    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return {"vectors": bool(cached.get("vectors")), "chunks": bool(cached.get("chunks"))}

    status = {"vectors": False, "chunks": False}
    is_default = is_default_kb(kb_id)
    try:
        conn = get_conn()
        try:
            # 向量：以文档上的 vectorized 标记为准（与 vectorize_document 写入的 metadata 一致）
            if is_default:
                cur = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM kb_documents "
                    "WHERE vectorized = 1 AND (kb_id = %s OR kb_id IS NULL)",
                    (int(kb_id),),
                )
            else:
                cur = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM kb_documents WHERE kb_id = %s AND vectorized = 1",
                    (int(kb_id),),
                )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            status["vectors"] = bool(rows and rows[0].get("cnt"))

            # 文本块：兼容 kb_chunks.kb_id 为空、靠文档兜底的历史数据
            if is_default:
                cur = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM kb_chunks c "
                    "JOIN kb_documents d ON d.id = c.document_id "
                    "WHERE (c.kb_id = %s OR (c.kb_id IS NULL AND (d.kb_id = %s OR d.kb_id IS NULL))) "
                    "AND c.kind != 'parent'",
                    (int(kb_id), int(kb_id)),
                )
            else:
                cur = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM kb_chunks c "
                    "JOIN kb_documents d ON d.id = c.document_id "
                    "WHERE (c.kb_id = %s OR (c.kb_id IS NULL AND d.kb_id = %s)) AND c.kind != 'parent'",
                    (int(kb_id), int(kb_id)),
                )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            status["chunks"] = bool(rows and rows[0].get("cnt"))
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 —— 查不出来就当"有内容"，走原路径，不改变既有行为
        logger.debug(f"[KB] 索引状态查询失败（按有内容处理）kb_id={kb_id}: {e}")
        return {"vectors": True, "chunks": True}

    cache.set_with_jitter(cache_key, status, base_ttl=60, jitter_range=10)
    return status


def get_default_kb_id() -> Optional[int]:
    """
    "默认知识库"的 id（带 Redis 缓存 300s）。

    约定来源：`kb_documents.kb_id IS NULL` 表示默认知识库（建表注释），
    前端知识库下拉也用 `null` 表示默认库；而默认库自身在 `kb_knowledge_base`
    里是一条名为「默认知识库」的记录（`get_or_create_default_kb` 创建）。
    取 id 最小的那条（历史数据里可能因多用户各建一条而存在多行）。
    """
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.build("kb", "default_kb_id")

    cached = cache.get(cache_key)
    if cached is not None:
        try:
            return int(cached) if str(cached) != "0" else None
        except (TypeError, ValueError):
            return None

    default_id: Optional[int] = None
    try:
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT id FROM kb_knowledge_base WHERE kb_name = %s ORDER BY id LIMIT 1",
                ("默认知识库",),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                default_id = int(rows[0]["id"])
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[KB] 默认知识库查询失败: {e}")
        return None

    cache.set_with_jitter(cache_key, default_id or 0, base_ttl=300, jitter_range=30)
    return default_id


def is_default_kb(kb_id: Optional[int]) -> bool:
    """该 kb_id 是否就是"默认知识库"（NULL-kb 文档归属它）。"""
    if kb_id is None:
        return False
    default_id = get_default_kb_id()
    return default_id is not None and int(kb_id) == default_id


def _is_empty_result_milvus_error(exc: Exception) -> bool:
    """
    判断异常是否为"Milvus 零命中结果解析失败"。

    仅这一种情况按"空结果"处理；连接类/服务端错误必须继续走降级与告警，
    不能把"向量库挂了"静默当成"没有相关内容"。
    """
    msg = str(exc)
    return "Unsupported field type" in msg and "MilvusException" in msg


# ════════════════════════════════════════════════════════════
# 分词
# ════════════════════════════════════════════════════════════

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    """中英混合分词：含中文走 jieba（搜索模式），纯英文按单词切。"""
    text = (text or "").lower()
    if not text:
        return []
    if _CJK_RE.search(text):
        try:
            import jieba
            return [t.strip() for t in jieba.cut_for_search(text) if t.strip()]
        except Exception:  # noqa: BLE001 — jieba 缺失时退化为按字符
            return list(text)
    return _WORD_RE.findall(text)


# ════════════════════════════════════════════════════════════
# CLI：幽灵向量体检 / 清理
# ════════════════════════════════════════════════════════════

def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    from pathlib import Path

    # 通过 `python -m` 直接运行时不会经过 main.py，需自行加载 .env
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="知识库向量维护（幽灵向量体检/清理）")
    parser.add_argument("--user-id", type=int, required=True, help="用户 ID")
    parser.add_argument("--purge-orphan-vectors", action="store_true",
                        help="删除 chunk_id 已不存在于 kb_chunks 的残留向量")
    parser.add_argument("--apply", action="store_true", help="真正执行删除（默认 dry-run 只报数）")
    args = parser.parse_args(argv)

    if args.purge_orphan_vectors:
        result = purge_orphan_vectors(args.user_id, dry_run=not args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.apply and result.get("orphan"):
            print(f"\n以上为 dry-run 统计。确认无误后加 --apply 执行删除（{result['orphan']} 条）")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    import sys as _sys

    _sys.exit(_main())
