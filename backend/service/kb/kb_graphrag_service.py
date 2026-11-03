"""
知识库文档 GraphRAG 提取服务

提供 KB 文档的实体关系提取能力：
- 提取父片内容（保留上下文完整性）
- 增量写入 Neo4j
- 支持删除和重新提取
- 分片级多线程并发提取
- 文档进度追踪

参考 AGI-saber 的 KGStore 实现
"""

import threading
from typing import Any, Dict, List, Optional, Set

from backend.db.schema import get_conn
from backend.graphrag.kg_store import get_kg_store
from backend.utils.log_utils import log, rag

logger = log

# 兼容旧版：正在提取的文档 ID 集合（防止重复提取）
_extracting_documents: Set[int] = set()
_extracting_lock = threading.Lock()


def is_document_extracting(document_id: int) -> bool:
    """检查文档是否正在提取中"""
    # 优先使用线程池的状态
    try:
        from backend.service.graph.extractor_pool import get_extractor_pool
        pool = get_extractor_pool()
        if pool._running:
            return pool.is_document_processing(document_id)
    except Exception:
        pass
    
    # 回退到旧版检查
    with _extracting_lock:
        return document_id in _extracting_documents


def _get_parent_chunks(document_id: int) -> List[Dict[str, Any]]:
    """
    获取文档的父片列表
    
    Args:
        document_id: 文档ID
        
    Returns:
        [{"id": int, "content": str}, ...]
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id, content FROM kb_chunks "
            "WHERE document_id = %s AND kind = 'parent' "
            "ORDER BY chunk_index ASC",
            (document_id,)
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [{"id": row["id"], "content": row["content"]} for row in rows]
    finally:
        conn.close()


def _update_document_graph_flag(document_id: int, extracted: bool = True) -> None:
    """更新文档的 graph_extracted 标记"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kb_documents SET graph_extracted = %s WHERE id = %s",
            (1 if extracted else 0, document_id)
        )
        conn.commit()
    except Exception as e:
        rag.warning(f"Failed to update graph_extracted flag: {e}")
    finally:
        conn.close()


def extract_document_entities(
    user_id: int,
    document_id: int,
    chunk_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    从 KB 文档提取实体关系（同步版本）
    
    只提取父片内容，保留上下文完整性
    
    Args:
        user_id: 用户ID
        document_id: 文档ID
        chunk_ids: 可选，指定提取哪些父片；None 表示全部
        
    Returns:
        {"entities": int, "relations": int, "chunks_processed": int}
    """
    kg_store = get_kg_store()
    if not kg_store.is_available():
        rag.info(f"[KB-GraphRAG] Neo4j 不可用，跳过提取 doc_id={document_id}")
        return {"entities": 0, "relations": 0, "chunks_processed": 0}
    
    # 获取父片
    all_chunks = _get_parent_chunks(document_id)
    
    # 过滤指定的 chunk
    if chunk_ids:
        chunks = [c for c in all_chunks if c["id"] in chunk_ids]
    else:
        chunks = all_chunks
    
    if not chunks:
        rag.warning(f"[KB-GraphRAG] 没有找到父片 doc_id={document_id}")
        return {"entities": 0, "relations": 0, "chunks_processed": 0}
    
    # 提取并写入图谱
    result = kg_store.index_document_chunks(
        document_id=document_id,
        chunks=chunks,
        user_id=user_id
    )
    
    # 更新标记
    if result["entities"] > 0 or result["relations"] > 0:
        _update_document_graph_flag(document_id, True)

    # 实体描述向量化（自适应检索的"实体优先"层，失败不影响主链路）
    try:
        from backend.service.kb.entity_vectorstore import vectorize_document_entities

        vectorize_document_entities(user_id, document_id)
    except Exception as e:
        rag.warning(f"[KB-GraphRAG] 实体向量化失败 doc_id={document_id}: {e}")

    return result


def refresh_document_entities(
    user_id: int,
    document_id: int
) -> Dict[str, Any]:
    """
    重新提取文档实体（删除旧实体 + 重新提取）
    
    Args:
        user_id: 用户ID
        document_id: 文档ID
        
    Returns:
        {"deleted": dict, "extracted": dict}
    """
    kg_store = get_kg_store()
    
    # 1. 删除旧实体
    deleted = kg_store.delete_document_entities(document_id)
    
    # 2. 重新提取
    extracted = extract_document_entities(user_id, document_id)
    
    return {
        "deleted": deleted,
        "extracted": extracted
    }


def clear_document_entities(document_id: int) -> Dict[str, Any]:
    """
    清除文档关联的所有实体
    
    Args:
        document_id: 文档ID
        
    Returns:
        {"deleted_relations": int, "deleted_entities": int}
    """
    kg_store = get_kg_store()
    result = kg_store.delete_document_entities(document_id)
    
    # 更新标记
    if result["deleted_entities"] > 0 or result["deleted_relations"] > 0:
        _update_document_graph_flag(document_id, False)

    # 同步清理实体向量（图谱删了、向量还在 → 会继续被检索并进 LLM prompt 的幽灵召回）
    try:
        from backend.service.kb.entity_vectorstore import delete_entity_vectors

        delete_entity_vectors(_document_owner_user_id(document_id), document_id=document_id)
    except Exception as e:
        rag.warning(f"[KB-GraphRAG] 实体向量清理失败 doc_id={document_id}: {e}")
        raise

    return result


def _document_owner_user_id(document_id: int) -> int:
    """读取文档上传者 ID（实体向量库按用户分 collection，删除时需要）。"""
    conn = get_conn()
    try:
        cur = conn.execute("SELECT user_id FROM kb_documents WHERE id = %s", (document_id,))
        row = cur.fetchone() if hasattr(cur, "fetchone") else None
        return int(row["user_id"]) if row and row.get("user_id") is not None else 0
    except Exception:  # noqa: BLE001
        return 0
    finally:
        conn.close()


def extract_document_entities_async(user_id: int, document_id: int) -> bool:
    """
    异步提取文档实体（使用分片级多线程）
    
    使用 GraphExtractorPool 实现多文档并发 + 单文档多线程
    
    Args:
        user_id: 用户ID
        document_id: 文档ID
        
    Returns:
        是否成功启动提取（False 表示已在提取中）
    """
    from backend.service.graph.extractor_pool import get_extractor_pool, start_extractor_pool
    
    # 确保线程池已启动
    pool = get_extractor_pool()
    if not pool._running:
        start_extractor_pool()
    
    # 获取父片
    chunks = _get_parent_chunks(document_id)
    
    if not chunks:
        rag.warning(f"[KB-GraphRAG] 没有找到父片 doc_id={document_id}")
        return False
    
    # 提交到线程池
    success = pool.submit_document(
        user_id=user_id,
        document_id=document_id,
        chunks=chunks
    )
    
    if success:
        logger.info(f"[KB-GraphRAG] 已提交到线程池 doc_id={document_id}, chunks={len(chunks)}")
    else:
        logger.info(f"[KB-GraphRAG] 文档已在处理中 doc_id={document_id}")
    
    return success


def get_extraction_progress(document_id: int) -> Optional[Dict[str, Any]]:
    """
    获取文档提取进度
    
    Args:
        document_id: 文档ID
        
    Returns:
        进度信息，如果文档未被处理则返回 None
    """
    from backend.service.graph.extractor_pool import get_extractor_pool
    
    pool = get_extractor_pool()
    return pool.get_progress(document_id)


def get_all_extraction_progress() -> List[Dict[str, Any]]:
    """
    获取所有文档的提取进度
    
    Returns:
        进度列表
    """
    from backend.service.graph.extractor_pool import get_extractor_pool
    
    pool = get_extractor_pool()
    return pool.get_all_progress()