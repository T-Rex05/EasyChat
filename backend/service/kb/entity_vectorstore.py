"""
实体描述向量库 —— 自适应检索的「实体优先」层

设计目标（对应 docs/adaptive_retrieval_design.md §10）：
- 知识图谱（Neo4j）是实体的**事实源**，本模块只维护一份**可重建的向量索引副本**
- 实体检索命中 → Local Search（实体 → 图扩展 → 文本块 / 记忆）
- 实体检索未命中 → 上层降级到文本块向量检索（Basic Search）

索引内容：
- 文档实体（`source_document_id IS NOT NULL`）→ 按部门/数据层级可见性过滤后入库
- 记忆实体（`source_memory_id IS NOT NULL` 或与 Memory 节点有 EXTRACTED_ENTITY 边）→ 按 user_id 隔离

向量库：
- Milvus collection `entity_desc_user_{user_id}`，**COSINE** 度量
  （不用 L2：实体命中判定需要一个有绝对语义的阈值，见设计文档 §10.3）
- Milvus 不可用时降级 Chroma（cosine space）

写入路径（三条 + 一条删除）：
1. KB 文档图谱抽取完成 → vectorize_document_entities()
2. 记忆实体提取完成   → vectorize_memory_entities()
3. 存量补齐           → python -m backend.service.kb.entity_vectorstore --user-id N
4. 文档/记忆删除       → delete_entity_vectors(document_id=... / memory_id=...)

⚠️ 删除失败**不吞异常**：残留向量会继续被检索并进入 LLM prompt（历史教训见
`kb_retriever.unvectorize_document` 的注释）。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.utils.log_utils import log

logger = log

# ════════════════════════════════════════════════════════════
# 常量与配置
# ════════════════════════════════════════════════════════════

ENTITY_COLLECTION_PREFIX = "entity_desc_user_"

# 实体命中阈值（余弦相似度）：低于此值视为"实体检索失败"，降级文本块检索
DEFAULT_ENTITY_THRESHOLD = 0.5
# 实体召回种子数
DEFAULT_TOP_K_ENTITIES = 10
# 单次 embedding 批大小（底层 embeddings 会再按 20 条切分调用 API，这里只控制内存与进度粒度）
DEFAULT_EMBED_BATCH = 64
# 关系文本翻译（进描述文本，用于增强语义）
_REL_TEXT: Dict[str, str] = {
    "LIKES": "喜欢",
    "PREFERS": "偏好",
    "DISLIKES": "不喜欢",
    "HAS_SKILL": "掌握技能",
    "EXPERT_IN": "擅长",
    "HAS_GOAL": "目标是",
    "KNOWS": "认识",
    "KNOWS_ABOUT": "了解",
    "WORKS_WITH": "共事",
    "WORKS_AT": "就职于",
    "WORKS_ON": "参与",
    "MEMBER_OF": "隶属于",
    "OWNS": "负责",
    "USES": "使用",
    "PART_OF": "属于",
    "RELATED_TO": "相关",
    "CAUSED": "导致",
    "DEPENDS_ON": "依赖",
    "LEARNED": "学过",
    "FOUNDED": "创立",
    "REPORTS_TO": "汇报给",
    "HAPPENED_AFTER": "发生在之后",
    "HAPPENED_BEFORE": "发生在之前",
}

SOURCE_TYPE_DOC = "doc"
SOURCE_TYPE_MEMORY = "memory"

# 每用户向量库实例缓存（构建一次 Milvus/Chroma 连接，避免每次检索重建）
_store_cache: Dict[Tuple[int, str], Tuple[Any, str]] = {}
_store_lock = threading.Lock()
# 每 key 一把锁：既避免"同一个 key 并发建两条连接"，又不让不同用户的首次建连互相阻塞
_store_locks: Dict[Tuple[int, str], threading.Lock] = {}
# 缓存上限：每个条目持有一条向量库连接，key 随"多少用户检索过"增长 → 必须封顶
_STORE_CACHE_MAX = 32


class EntityVectorStoreError(Exception):
    """实体向量库不可用（embedding 未配置 / 后端不可达）"""


# ════════════════════════════════════════════════════════════
# 基础工具
# ════════════════════════════════════════════════════════════

def get_entity_collection_name(user_id: int) -> str:
    """实体描述向量库的 collection 名（每用户一个，与 kb_user_{uid} 同构）。"""
    return f"{ENTITY_COLLECTION_PREFIX}{int(user_id)}"


def get_entity_threshold() -> float:
    """实体命中阈值（可配置）。"""
    try:
        return float(os.getenv("RAG_ENTITY_THRESHOLD", str(DEFAULT_ENTITY_THRESHOLD)))
    except (TypeError, ValueError):
        return DEFAULT_ENTITY_THRESHOLD


def get_top_k_entities() -> int:
    """实体召回种子数（可配置）。"""
    try:
        return max(1, int(os.getenv("RAG_TOP_K_ENTITIES", str(DEFAULT_TOP_K_ENTITIES))))
    except (TypeError, ValueError):
        return DEFAULT_TOP_K_ENTITIES


def _get_embeddings():
    """获取 embedding 实例（DB 配置优先，如 qwen3.7-text-embedding）。"""
    try:
        from backend.rag.embeddings import get_embeddings

        return get_embeddings()
    except Exception as e:  # noqa: BLE001
        raise EntityVectorStoreError(f"Embedding 服务不可用: {e}") from e


def _is_chroma_store(store: Any) -> bool:
    """判断向量库是否为 Chroma（过滤器语法与 Milvus 不同）。"""
    return store.__class__.__module__.startswith("langchain_chroma")


def _build_entity_store(user_id: int) -> Tuple[Any, str]:
    """
    构建（或复用）用户实体向量库。

    Returns:
        (store, metric) —— metric ∈ {"cosine", "chroma_cosine"}，用于把后端分值换算成相似度

    Raises:
        EntityVectorStoreError: embedding 未配置 / 向量库不可用
    """
    cache_key = (int(user_id), "default")
    with _store_lock:
        cached = _store_cache.get(cache_key)
        if cached is None:
            key_lock = _store_locks.get(cache_key)
            if key_lock is None:
                key_lock = threading.Lock()
                _store_locks[cache_key] = key_lock
    if cached is not None:
        return cached

    # 同一个 user_id 的首次建连串行化（check-then-act 竞态会让两条连接各自"逃逸"出缓存）
    with key_lock:
        with _store_lock:
            cached = _store_cache.get(cache_key)
        if cached is not None:
            return cached

        store, metric = _create_entity_store(collection_name=get_entity_collection_name(user_id))

        with _store_lock:
            _store_cache[cache_key] = (store, metric)
            if len(_store_cache) > _STORE_CACHE_MAX:
                # 近似 FIFO 淘汰一半（dict 保序）：未命中时按 collection 名重建，语义不受影响。
                # ⚠️ 不主动 close 被淘汰的 store —— 别的线程可能正持有该对象在用，
                # 关掉会造成"用着用着连接没了"的随机失败；交给 GC 回收。
                for key in list(_store_cache.keys())[: len(_store_cache) - _STORE_CACHE_MAX // 2]:
                    _store_cache.pop(key, None)
                    _store_locks.pop(key, None)
        return store, metric


def _create_entity_store(collection_name: str) -> Tuple[Any, str]:
    """真正创建向量库实例（调用方须已持有该 key 的锁）。

    Returns:
        (store, metric) —— metric ∈ {"cosine", "chroma_cosine"}

    Raises:
        EntityVectorStoreError: embedding 未配置 / 向量库不可用
    """
    embeddings = _get_embeddings()

    milvus_host = os.getenv("MILVUS_HOST", "")
    if milvus_host:
        try:
            from langchain_milvus import Milvus

            uri = f"http://{milvus_host}:{os.getenv('MILVUS_PORT', '19530')}"
            store = Milvus(
                embedding_function=embeddings,
                collection_name=collection_name,
                connection_args={"uri": uri},
                auto_id=False,
                primary_field="pk",
                text_field="text",
                vector_field="vector",
                # ★ COSINE：实体命中阈值需要绝对语义（L2 距离随维度/归一化漂移）
                index_params={"index_type": "AUTOINDEX", "metric_type": "COSINE"},
            )
            return store, "cosine"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[EntityStore] Milvus 不可用，降级 Chroma: {e}")

    try:
        from langchain_chroma import Chroma

        from backend.rag.config import get_rag_config

        persist_dir = get_rag_config().persist_dir
        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)
        store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_dir or None,
            # Chroma 默认 l2 空间；显式声明 cosine → 距离 = 1 - cos（_to_similarity 按此换算）
            collection_metadata={"hnsw:space": "cosine"},
        )
        return store, "chroma_cosine"
    except Exception as e:  # noqa: BLE001
        raise EntityVectorStoreError(f"实体向量库不可用（Milvus/Chroma 均失败）: {e}") from e


def _to_similarity(raw: float, metric: str) -> float:
    """把向量库返回的分值换算成 [0, 1] 的余弦相似度。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if metric == "cosine":
        # Milvus COSINE：分值本身就是余弦相似度（越大越相似）
        return max(0.0, min(1.0, value))
    # Chroma cosine 空间：返回 1 - cos 的距离
    return max(0.0, min(1.0, 1.0 - value))


def _filter_kwargs(store: Any, conditions: Dict[str, Any], for_delete: bool = False) -> Dict[str, Any]:
    """
    把 {字段: 值} 条件转成对应向量库的过滤参数。

    ⚠️ 检索与删除的参数名不同（langchain-chroma：`filter` vs `where`），
    传错不会报错而是"静默删不掉/查不到"。
    """
    if not conditions:
        return {}
    if _is_chroma_store(store):
        key = "where" if for_delete else "filter"
        if len(conditions) == 1:
            return {key: dict(conditions)}
        return {key: {"$and": [{k: v} for k, v in conditions.items()]}}

    parts = []
    for key, value in conditions.items():
        if isinstance(value, str):
            parts.append(f'{key} == "{value}"')
        elif isinstance(value, (list, tuple, set)):
            values = ", ".join(
                f'"{v}"' if isinstance(v, str) else str(v) for v in value
            )
            parts.append(f"{key} in [{values}]")
        else:
            parts.append(f"{key} == {value}")
    return {"expr": " and ".join(parts)}


# ════════════════════════════════════════════════════════════
# 实体描述构建
# ════════════════════════════════════════════════════════════

def build_entity_description(entity: Dict[str, Any], relations: Optional[Sequence[Dict]] = None) -> str:
    """
    构建实体描述文本（用于向量化）。

    示例输出：
        "关羽，person，三国时期蜀汉名将，五虎上将之一，与刘备共事，与张飞共事"
    """
    parts: List[str] = []

    name = (entity.get("name") or "").strip()
    if name:
        parts.append(name)

    entity_type = (entity.get("entity_type") or "").strip()
    if entity_type:
        parts.append(entity_type)

    description = (entity.get("description") or "").strip()
    if description:
        parts.append(description)

    aliases = entity.get("aliases") or []
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except (TypeError, ValueError):
            aliases = []
    if aliases:
        alias_text = "、".join(str(a).strip() for a in aliases[:3] if str(a).strip())
        if alias_text:
            parts.append(f"别名{alias_text}")

    for rel in (relations or [])[:3]:
        rel_type = (rel.get("relation_type") or "").upper()
        other = (rel.get("other_name") or "").strip()
        if not other:
            continue
        rel_text = _REL_TEXT.get(rel_type, rel_type)
        parts.append(f"与{other}{rel_text}")

    return "，".join(p for p in parts if p)


# ════════════════════════════════════════════════════════════
# 实体加载（Neo4j → 可向量化的实体列表）
# ════════════════════════════════════════════════════════════

def _visible_doc_ids(user_id: int) -> List[int]:
    """该用户可见的 KB 文档 ID（部门/层级隔离，fail-closed）。"""
    try:
        from backend.service.auth.data_layer_service import get_visible_document_ids

        return list(get_visible_document_ids(int(user_id)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[EntityStore] 可见文档集合计算失败 → fail-closed（文档实体不入库）: {e}")
        return []


def _entity_projection() -> str:
    return (
        "n.id AS id, n.name AS name, n.entity_type AS entity_type, "
        "n.description AS description, n.aliases AS aliases, n.confidence AS confidence, "
        "n.source_document_id AS source_document_id, n.source_chunk_id AS source_chunk_id, "
        "n.source_memory_id AS source_memory_id, n.user_id AS user_id"
    )


def load_entities(
    user_id: int,
    scope: str = "all",
    document_id: Optional[int] = None,
    memory_id: Optional[int] = None,
    entity_ids: Optional[Sequence[str]] = None,
    with_relations: bool = True,
) -> List[Dict[str, Any]]:
    """
    从知识图谱加载待向量化的实体（事实源 = Neo4j）。

    Args:
        user_id: 用户 ID
        scope: all | doc | memory
        document_id: 只取某文档的实体（按 source_document_id）
        memory_id: 只取某记忆的实体（source_memory_id 或 EXTRACTED_ENTITY 边）
        entity_ids: 只取指定实体
        with_relations: 是否附带关键关系（用于增强实体描述语义）

    Returns:
        [{id, name, entity_type, description, aliases, confidence,
          source_type, source_document_id, source_chunk_id, source_memory_id,
          user_id, relations: [{relation_type, other_name}]}, ...]
    """
    from backend.graphrag.kg_store import get_kg_store

    kg_store = get_kg_store()
    if not kg_store.is_available():
        return []
    graph_client = kg_store._get_graph_client()  # noqa: SLF001 —— 复用同一连接，避免再造一层客户端

    doc_ids = _visible_doc_ids(user_id)
    params: Dict[str, Any] = {"user_id": int(user_id), "visible_doc_ids": doc_ids}

    # ── 可见性谓词（与 KGStore._vis_pred 一致：文档实体按部门层级，记忆实体按 user_id）──
    # fail-closed：$visible_doc_ids 为空时 `IN []` 恒 false → 文档实体一律不入索引
    visibility = (
        "((n.source_document_id IS NOT NULL AND n.source_document_id IN $visible_doc_ids) "
        "OR (n.source_document_id IS NULL AND n.user_id = $user_id))"
    )
    base_where = [
        "NOT n:Memory",
        "n.id IS NOT NULL",
        "n.name IS NOT NULL",
        "n.name <> ''",
    ]

    # 记忆实体的两种识别方式：
    #  1) 属性 source_memory_id（直接从记忆提取）
    #  2) 跨层边 (m:Memory)-[:EXTRACTED_ENTITY]->(e)（实体对齐合并进文档实体后属性会丢）
    memory_marker = (
        "(n.source_memory_id IS NOT NULL "
        "OR EXISTS { MATCH (m:Memory)-[:EXTRACTED_ENTITY]->(n) WHERE m.user_id = $user_id })"
    )

    if document_id is not None:
        query = (
            "MATCH (n) WHERE NOT n:Memory AND n.id IS NOT NULL AND n.name IS NOT NULL "
            "AND n.source_document_id = $document_id "
            f"RETURN {_entity_projection()}"
        )
        params["document_id"] = int(document_id)
    elif memory_id is not None:
        query = (
            "MATCH (n) WHERE NOT n:Memory AND n.id IS NOT NULL AND n.name IS NOT NULL "
            "AND (n.source_memory_id = $memory_id "
            "     OR EXISTS { MATCH (m:Memory)-[:EXTRACTED_ENTITY]->(n) WHERE m.mem_id = $memory_id }) "
            f"RETURN {_entity_projection()}"
        )
        params["memory_id"] = int(memory_id)
    elif entity_ids:
        # 显式指定 id 时不追加可见性过滤：调用方（重新索引已可见实体）已做过裁决
        query = (
            "MATCH (n) WHERE NOT n:Memory AND n.id IN $entity_ids "
            f"RETURN {_entity_projection()}"
        )
        params["entity_ids"] = [str(i) for i in entity_ids]
    else:
        where = list(base_where) + [visibility]
        if scope == SOURCE_TYPE_MEMORY:
            where.append(memory_marker)
        elif scope == SOURCE_TYPE_DOC:
            where.append("n.source_document_id IS NOT NULL")
        query = f"MATCH (n) WHERE {' AND '.join(where)} RETURN {_entity_projection()}"

    try:
        rows = graph_client.run_query(query, params) or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[EntityStore] 实体加载失败: {e}")
        return []

    entities: List[Dict[str, Any]] = []
    for row in rows:
        eid = row.get("id")
        name = row.get("name")
        if not eid or not name:
            continue
        source_document_id = row.get("source_document_id")
        source_memory_id = row.get("source_memory_id")
        entities.append({
            "id": str(eid),
            "name": str(name),
            "entity_type": (row.get("entity_type") or "other"),
            "description": row.get("description") or "",
            "aliases": row.get("aliases") or [],
            "confidence": float(row.get("confidence") or 1.0),
            "source_type": SOURCE_TYPE_DOC if source_document_id is not None else SOURCE_TYPE_MEMORY,
            "source_document_id": int(source_document_id) if source_document_id is not None else 0,
            "source_chunk_id": int(row["source_chunk_id"]) if row.get("source_chunk_id") is not None else 0,
            "source_memory_id": int(source_memory_id) if source_memory_id is not None else 0,
            "user_id": int(row["user_id"]) if row.get("user_id") is not None else int(user_id),
            "relations": [],
        })

    if with_relations and entities:
        _attach_relations(graph_client, entities)

    return entities


def _attach_relations(
    graph_client: Any,
    entities: List[Dict[str, Any]],
) -> None:
    """为实体补充关键关系（每个实体最多 3 条，按关系权重降序稳定排序）。"""
    ids = [e["id"] for e in entities]
    rel_map: Dict[str, List[Dict[str, Any]]] = {}

    chunk_size = 200
    for start in range(0, len(ids), chunk_size):
        batch = ids[start:start + chunk_size]
        query = (
            "MATCH (n)-[r]-(m) WHERE n.id IN $ids AND m.name IS NOT NULL "
            "AND NOT m:Memory "
            "RETURN n.id AS eid, type(r) AS relation_type, m.name AS other_name, "
            "coalesce(r.weight, 1.0) AS weight"
        )
        params = {"ids": batch}
        try:
            rows = graph_client.run_query(query, params) or []
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[EntityStore] 关系加载失败（跳过关系增强）: {e}")
            return
        for row in rows:
            eid = row.get("eid")
            other = row.get("other_name")
            if not eid or not other:
                continue
            rel_map.setdefault(str(eid), []).append({
                "relation_type": row.get("relation_type") or "",
                "other_name": str(other),
                "weight": float(row.get("weight") or 1.0),
            })

    for entity in entities:
        rels = rel_map.get(entity["id"], [])
        # 同一关系类型去重 + 按权重降序，保证描述文本稳定（利于 embedding 缓存命中）
        seen = set()
        deduped = []
        for rel in sorted(rels, key=lambda r: -r["weight"]):
            key = (rel["relation_type"], rel["other_name"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(rel)
        entity["relations"] = deduped[:3]


# ════════════════════════════════════════════════════════════
# 向量化（写入）
# ════════════════════════════════════════════════════════════

def _entity_metadata(entity: Dict[str, Any]) -> Dict[str, Any]:
    """向量库 metadata —— 字段集必须**完全一致**（Milvus 无 NULL，schema 由首条决定）。"""
    return {
        "entity_id": entity["id"],
        "entity_name": entity["name"],
        "entity_type": entity.get("entity_type") or "other",
        "source_type": entity.get("source_type") or SOURCE_TYPE_DOC,
        "source_document_id": int(entity.get("source_document_id") or 0),
        "source_chunk_id": int(entity.get("source_chunk_id") or 0),
        "source_memory_id": int(entity.get("source_memory_id") or 0),
        "user_id": int(entity.get("user_id") or 0),
        "confidence": float(entity.get("confidence") or 1.0),
    }


def delete_entity_vectors(
    user_id: int,
    entity_ids: Optional[Sequence[str]] = None,
    document_id: Optional[int] = None,
    memory_id: Optional[int] = None,
) -> bool:
    """
    删除实体向量（删除失败向上抛，避免"图谱删了、向量还在"的幽灵召回）。

    Args:
        user_id: 用户 ID
        entity_ids: 按实体 ID 删除
        document_id: 按来源文档删除（文档删除/重抽取时用）
        memory_id: 按来源记忆删除（记忆删除时用）

    Returns:
        True=成功（含"本来就没有"）；False=向量库不可用（无需处理）
    """
    try:
        store, _metric = _build_entity_store(user_id)
    except EntityVectorStoreError as e:
        logger.debug(f"[EntityStore] 向量库不可用，跳过删除: {e}")
        return False

    try:
        if entity_ids:
            store.delete(ids=[str(i) for i in entity_ids])
        if document_id is not None:
            store.delete(**_filter_kwargs(store, {"source_document_id": int(document_id)}, for_delete=True))
        if memory_id is not None:
            store.delete(**_filter_kwargs(store, {"source_memory_id": int(memory_id)}, for_delete=True))
        return True
    except Exception as e:  # noqa: BLE001
        logger.opt(exception=True).warning(
            f"[EntityStore] 实体向量删除失败 user_id={user_id} "
            f"entity_ids={len(entity_ids or [])} doc={document_id} mem={memory_id}: {e}"
        )
        raise


def vectorize_entities(
    user_id: int,
    entities: Sequence[Dict[str, Any]],
    batch_size: int = DEFAULT_EMBED_BATCH,
    replace: bool = True,
) -> Dict[str, int]:
    """
    把实体描述向量化写入向量库（幂等：先按 id 删除旧向量再写入）。

    Args:
        user_id: 用户 ID
        entities: load_entities() 的输出
        batch_size: 每批写入条数
        replace: 是否先删除同 id 旧向量（保证实体描述变更后不残留旧版本）

    Returns:
        {"indexed": n, "failed": m}
    """
    if not entities:
        return {"indexed": 0, "failed": 0}

    store, _metric = _build_entity_store(user_id)

    texts: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []
    for entity in entities:
        if not entity.get("id"):
            continue
        description = build_entity_description(entity, entity.get("relations") or [])
        if not description:
            continue
        texts.append(description)
        metadatas.append(_entity_metadata(entity))
        ids.append(str(entity["id"]))

    if not texts:
        return {"indexed": 0, "failed": 0}

    indexed = 0
    failed = 0
    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start:start + batch_size]
        batch_metas = metadatas[start:start + batch_size]
        batch_ids = ids[start:start + batch_size]
        try:
            if replace:
                try:
                    store.delete(ids=batch_ids)
                except Exception as e:  # noqa: BLE001 —— 首次建库时 collection 还不存在
                    logger.debug(f"[EntityStore] 预删除跳过（collection 可能未创建）: {e}")
            store.add_texts(texts=batch_texts, metadatas=batch_metas, ids=batch_ids)
            indexed += len(batch_texts)
        except Exception as e:  # noqa: BLE001
            failed += len(batch_texts)
            logger.warning(f"[EntityStore] 批量写入失败（{len(batch_texts)} 条）: {e}")

    return {"indexed": indexed, "failed": failed}


def vectorize_document_entities(user_id: int, document_id: int) -> Dict[str, int]:
    """
    按文档重建实体向量（图谱抽取完成后调用）。

    先按 `source_document_id` 清空该文档的向量：重新抽取后实体集合可能变小，
    只做"按 id 覆盖"会在库里留下已不存在的实体（幽灵召回）。
    """
    try:
        try:
            delete_entity_vectors(user_id, document_id=document_id)
        except Exception as e:  # noqa: BLE001 —— 预清理失败不能中断写入，但必须留痕（可能残留旧实体向量）
            logger.warning(
                f"[EntityStore] 文档实体向量预清理失败 doc_id={document_id}"
                f"（旧向量可能残留，需跑一次全量补齐/对账）: {e}"
            )

        entities = load_entities(user_id, document_id=document_id, with_relations=True)
        if not entities:
            return {"indexed": 0, "failed": 0}
        result = vectorize_entities(user_id, entities)
        logger.info(
            f"[EntityStore] 文档实体索引完成 doc_id={document_id}: "
            f"indexed={result['indexed']} failed={result['failed']}"
        )
        return result
    except Exception as e:  # noqa: BLE001 —— 索引失败不影响主链路
        logger.warning(f"[EntityStore] 文档实体索引失败 doc_id={document_id}: {e}")
        return {"indexed": 0, "failed": 0}


def vectorize_memory_entities(user_id: int, memory_id: int) -> Dict[str, int]:
    """按记忆重建实体向量（记忆实体提取完成后调用，同样先清空再写）。"""
    try:
        try:
            delete_entity_vectors(user_id, memory_id=memory_id)
        except Exception as e:  # noqa: BLE001 —— 同上：留痕但不中断写入
            logger.warning(
                f"[EntityStore] 记忆实体向量预清理失败 memory_id={memory_id}"
                f"（旧向量可能残留，需跑一次全量补齐/对账）: {e}"
            )

        entities = load_entities(user_id, memory_id=memory_id, with_relations=True)
        if not entities:
            return {"indexed": 0, "failed": 0}
        result = vectorize_entities(user_id, entities)
        logger.info(
            f"[EntityStore] 记忆实体索引完成 memory_id={memory_id}: "
            f"indexed={result['indexed']} failed={result['failed']}"
        )
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[EntityStore] 记忆实体索引失败 memory_id={memory_id}: {e}")
        return {"indexed": 0, "failed": 0}


def vectorize_user_entities(
    user_id: int,
    scope: str = "all",
    batch_size: int = DEFAULT_EMBED_BATCH,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    全量/增量重建某用户的实体向量索引（存量补齐入口）。

    Args:
        user_id: 用户 ID
        scope: all | doc | memory
        batch_size: 每批写入条数
        limit: 最多处理多少实体（调试用）

    Returns:
        {"total": n, "indexed": n, "failed": m, "scope": scope}
    """
    entities = load_entities(user_id, scope=scope, with_relations=True)
    if limit:
        entities = entities[: int(limit)]
    result = vectorize_entities(user_id, entities, batch_size=batch_size)
    return {
        "total": len(entities),
        "indexed": result["indexed"],
        "failed": result["failed"],
        "scope": scope,
    }


# ════════════════════════════════════════════════════════════
# 检索（读）
# ════════════════════════════════════════════════════════════

def search_entities(
    user_id: int,
    query: str,
    top_k: Optional[int] = None,
    scope: str = "all",
    entity_types: Optional[Sequence[str]] = None,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    实体描述向量检索。

    Args:
        user_id: 用户 ID
        query: 查询文本
        top_k: 返回数量（默认 RAG_TOP_K_ENTITIES）
        scope: all | doc | memory
        entity_types: 实体类型过滤（如 ["person", "skill"]）
        min_score: 最低余弦相似度

    Returns:
        [{entity_id, entity_name, entity_type, description, source_type,
          source_document_id, source_chunk_id, source_memory_id, user_id,
          confidence, score}, ...]（按 score 降序）
    """
    if not query or not query.strip():
        return []

    top_k = int(top_k or get_top_k_entities())

    try:
        store, metric = _build_entity_store(user_id)
    except EntityVectorStoreError as e:
        logger.debug(f"[EntityStore] 检索跳过（向量库不可用）: {e}")
        return []

    conditions: Dict[str, Any] = {}
    if scope in (SOURCE_TYPE_DOC, SOURCE_TYPE_MEMORY):
        conditions["source_type"] = scope
    if entity_types:
        types = [t.lower() for t in entity_types if t]
        if len(types) == 1:
            conditions["entity_type"] = types[0]
        elif types:
            conditions["entity_type"] = types

    try:
        raw_hits = store.similarity_search_with_score(
            query, k=top_k, **_filter_kwargs(store, conditions)
        )
    except Exception as e:  # noqa: BLE001
        # 过滤条件命中 0 行时 pymilvus 3.0.1 在结果解析阶段抛
        # "Unsupported field type: 0" —— 语义是"没有结果"，按空结果处理（详见
        # kb_retriever.get_kb_index_status 的说明），避免把"没数据"误报成"向量库故障"。
        if "Unsupported field type" in str(e) and "MilvusException" in str(e):
            logger.debug(f"[EntityStore] 过滤条件零命中（按空结果处理）: {conditions}")
            return []
        logger.warning(f"[EntityStore] 实体检索失败: {e}")
        return []

    hits: List[Dict[str, Any]] = []
    for doc, score in raw_hits:
        meta = dict(doc.metadata or {})
        similarity = _to_similarity(score, metric)
        if similarity < min_score:
            continue
        hits.append({
            "entity_id": meta.get("entity_id"),
            "entity_name": meta.get("entity_name"),
            "entity_type": meta.get("entity_type"),
            "description": doc.page_content,
            "source_type": meta.get("source_type"),
            "source_document_id": meta.get("source_document_id") or 0,
            "source_chunk_id": meta.get("source_chunk_id") or 0,
            "source_memory_id": meta.get("source_memory_id") or 0,
            "user_id": meta.get("user_id"),
            "confidence": meta.get("confidence"),
            "score": round(similarity, 6),
        })

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:top_k]


def is_available(user_id: int) -> bool:
    """实体向量库是否可用（Milvus/Chroma + embedding 均已就绪）。"""
    try:
        _build_entity_store(user_id)
        return True
    except EntityVectorStoreError:
        return False
    except Exception:  # noqa: BLE001
        return False


def get_index_stats(user_id: int) -> Dict[str, Any]:
    """索引统计（运维/测试用）。"""
    stats: Dict[str, Any] = {
        "collection": get_entity_collection_name(user_id),
        "available": False,
        "rows": None,
        "metric": None,
    }
    try:
        store, metric = _build_entity_store(user_id)
        stats["available"] = True
        stats["metric"] = metric
        stats["rows"] = _count_rows(store, stats["collection"])
    except EntityVectorStoreError as e:
        stats["error"] = str(e)
    return stats


def _count_rows(store: Any, collection_name: str) -> Optional[int]:
    """读取 collection 行数（取不到返回 None，不影响主流程）。

    注意 `get_collection_stats()['row_count']` 读的是**已 flush** 的行数，
    刚写入的向量还看不到 → 用 `count(*)` 强一致查询才是真实值。
    """
    client = getattr(store, "client", None)
    if client is None or not hasattr(client, "query"):
        try:
            from pymilvus import MilvusClient

            uri = f"http://{os.getenv('MILVUS_HOST', '')}:{os.getenv('MILVUS_PORT', '19530')}"
            client = MilvusClient(uri=uri)
        except Exception:  # noqa: BLE001
            return None

    try:
        rows = client.query(
            collection_name=collection_name,
            filter="",
            output_fields=["count(*)"],
            consistency_level="Strong",
        )
        if rows:
            first = rows[0]
            if isinstance(first, dict):
                return int(first.get("count(*)", 0))
        return 0
    except Exception:  # noqa: BLE001
        try:
            return int(client.get_collection_stats(collection_name).get("row_count"))
        except Exception:  # noqa: BLE001
            return None


# ════════════════════════════════════════════════════════════
# CLI（存量补齐）
# ════════════════════════════════════════════════════════════

def _main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    from pathlib import Path

    # 通过 `python -m` 直接运行时不会经过 main.py，需自行加载 .env
    # （否则 Neo4j/Milvus 连接参数缺失 → 加载到 0 个实体，静默"假成功"）
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="实体描述向量库维护（存量补齐/统计）")
    parser.add_argument("--user-id", type=int, required=True, help="用户 ID")
    parser.add_argument("--scope", choices=["all", "doc", "memory"], default="all")
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少实体")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_EMBED_BATCH)
    parser.add_argument("--stats-only", action="store_true", help="只打印索引统计")
    args = parser.parse_args(argv)

    if args.stats_only:
        print(json.dumps(get_index_stats(args.user_id), ensure_ascii=False, indent=2))
        return 0

    result = vectorize_user_entities(
        args.user_id, scope=args.scope, batch_size=args.batch_size, limit=args.limit
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(get_index_stats(args.user_id), ensure_ascii=False, indent=2))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(_main())
