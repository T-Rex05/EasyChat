# backend/infrastructure/milvus_client.py
"""Milvus 向量客户端，支持降级到 ChromaDB"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 尝试导入 Milvus
try:
    from pymilvus import MilvusClient as _MilvusClient
    _HAS_MILVUS = True
except ImportError:
    _MilvusClient = None
    _HAS_MILVUS = False


class MilvusClient:
    """Milvus 向量客户端
    
    降级策略：
    - Milvus 可用 → 使用 Milvus
    - Milvus 不可用 → 降级到 ChromaDB（现有知识库向量存储）
    """
    
    def __init__(self, host: str = None, port: int = None, chroma_store=None):
        self._client: Optional[Any] = None
        self._fallback_chroma = chroma_store
        self.status = "disconnected"
        
        # 从参数或环境变量读取配置
        self._host = host or os.getenv("MILVUS_HOST", "")
        self._port = port or int(os.getenv("MILVUS_PORT", "19530"))
        
        if self._host:
            self._connect()
    
    def _connect(self) -> None:
        """连接 Milvus，失败则降级"""
        if not _HAS_MILVUS:
            logger.warning("pymilvus 未安装，Milvus 不可用")
            self.status = "chromadb-fallback" if self._fallback_chroma else "disconnected"
            return
        
        try:
            uri = f"http://{self._host}:{self._port}"
            self._client = _MilvusClient(uri=uri)
            self.status = "connected"
            logger.info(f"Milvus 已连接: {uri}")
        except Exception as e:
            logger.warning(f"Milvus 连接失败: {e}，降级到 ChromaDB")
            self._client = None
            self.status = "chromadb-fallback" if self._fallback_chroma else "disconnected"
    
    def is_available(self) -> bool:
        """向量存储是否可用"""
        return self._client is not None or self._fallback_chroma is not None
    
    def insert(self, collection_name: str, ids: List[int], 
               embeddings: List[List[float]], metadatas: List[dict]) -> bool:
        """插入向量"""
        if self._client:
            try:
                data = [
                    {"id": id_, "embedding": emb, **meta}
                    for id_, emb, meta in zip(ids, embeddings, metadatas)
                ]
                self._client.insert(collection_name=collection_name, data=data)
                return True
            except Exception as e:
                logger.warning(f"Milvus 插入失败: {e}")
                return False
        elif self._fallback_chroma:
            try:
                self._fallback_chroma.add(
                    ids=[str(id_) for id_ in ids],
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                return True
            except Exception as e:
                logger.warning(f"ChromaDB 插入失败: {e}")
                return False
        return False
    
    def search(self, collection_name: str, query_embedding: List[float], 
               top_k: int = 10, filter_expr: str = None) -> List[dict]:
        """向量检索"""
        if self._client:
            try:
                results = self._client.search(
                    collection_name=collection_name,
                    data=[query_embedding],
                    limit=top_k,
                    filter=filter_expr,
                    output_fields=["*"]  # 返回所有字段
                )
                hits = []
                for hit in results[0] if results else []:
                    # Milvus 新版返回格式: {'id': ..., 'distance': ..., 'entity': {...}}
                    entity = hit.get("entity", {})
                    # 从 entity 中提取动态字段
                    hits.append({
                        "id": entity.get("id") or hit.get("id"),
                        "score": hit.get("distance", 0),
                        "metadata": entity
                    })
                return hits
            except Exception as e:
                logger.warning(f"Milvus 检索失败: {e}")
                return []
        elif self._fallback_chroma:
            try:
                results = self._fallback_chroma.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k
                )
                hits = []
                ids = results.get("ids", [[]])[0]
                distances = results.get("distances", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]
                for id_, dist, meta in zip(ids, distances, metadatas):
                    hits.append({
                        "id": int(id_) if id_.isdigit() else id_,
                        "score": dist,
                        "metadata": meta
                    })
                return hits
            except Exception as e:
                logger.warning(f"ChromaDB 检索失败: {e}")
                return []
        return []
    
    def delete(self, collection_name: str, ids: List[int]) -> bool:
        """删除向量"""
        if self._client:
            try:
                self._client.delete(collection_name=collection_name, ids=ids)
                return True
            except Exception as e:
                logger.warning(f"Milvus 删除失败: {e}")
                return False
        elif self._fallback_chroma:
            try:
                self._fallback_chroma.delete(ids=[str(id_) for id_ in ids])
                return True
            except Exception as e:
                logger.warning(f"ChromaDB 删除失败: {e}")
                return False
        return False
    
    def close(self) -> None:
        """关闭连接"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self.status = "disconnected"