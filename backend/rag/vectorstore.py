"""
向量库工厂

根据配置创建对应的向量数据库实例。
优先级：Milvus > Chroma（Milvus 不可用时自动降级到 Chroma）
"""
import os
from pathlib import Path
from typing import Optional

from backend.rag.config import get_rag_config
from backend.utils.log_utils import log

# Milvus 可用性检查
try:
    from pymilvus import MilvusClient as _MilvusClient
    _HAS_MILVUS = True
except ImportError:
    _MilvusClient = None
    _HAS_MILVUS = False


def get_vectorstore(embeddings=None, collection: Optional[str] = None):
    """
    获取向量库实例。

    优先级：
    1. Milvus（如果配置了 MILVUS_HOST 且可用）
    2. Chroma（Milvus 不可用时降级）

    Args:
        embeddings: 嵌入模型实例（可选，不提供则自动创建）
        collection: collection 名称（可选，默认 agentforge_knowledge；
            知识库按用户隔离时传 get_user_collection_name(user_id) 的结果）

    Returns:
        VectorStore: LangChain 向量库实例
    """
    if embeddings is None:
        from backend.rag.embeddings import get_embeddings
        embeddings = get_embeddings()

    config = get_rag_config()
    collection_name = collection or "agentforge_knowledge"
    
    # 1. 尝试使用 Milvus
    milvus_host = os.getenv("MILVUS_HOST", "")
    milvus_port = os.getenv("MILVUS_PORT", "19530")
    
    if milvus_host and _HAS_MILVUS:
        try:
            from langchain_milvus import Milvus
            uri = f"http://{milvus_host}:{milvus_port}"
            vectorstore = Milvus(
                embedding_function=embeddings,
                collection_name=collection_name,
                connection_args={"uri": uri},
            )
            log.info(f"💾 RAG 向量库: Milvus collection={collection_name} ({uri})")
            return vectorstore
        except Exception as e:
            log.warning(f"Milvus 连接失败，降级到 ChromaDB: {e}")
    
    # 2. 降级到 Chroma
    persist_dir = config.persist_dir
    if persist_dir:
        os.makedirs(persist_dir, exist_ok=True)
    
    return _get_chroma_vectorstore(embeddings, persist_dir, collection_name)


def get_user_collection_name(user_id) -> str:
    """知识库按用户隔离的 collection 名：kb_user_{user_id}"""
    return f"kb_user_{user_id}"


def _get_chroma_vectorstore(embeddings, persist_dir: str, collection: Optional[str] = None):
    """创建 Chroma 向量库实例（支持持久化 + 指定 collection）"""
    try:
        from langchain_chroma import Chroma
    except ImportError:
        raise ImportError(
            "Chroma 向量库未安装。请运行: pip install langchain-chroma"
        )

    collection_name = collection or "agentforge_knowledge"

    if persist_dir:
        # 持久化模式：数据保存到本地目录
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )
        log.info(f"💾 RAG 向量库: Chroma collection={collection_name} (持久化到 {persist_dir})")
    else:
        # 临时模式：进程结束即丢失
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
        )
        log.info(f"💾 RAG 向量库: Chroma collection={collection_name} (临时模式)")

    return vectorstore


def _get_faiss_vectorstore(embeddings, persist_dir: str):
    """创建 FAISS 向量库实例"""
    try:
        from langchain_community.vectorstores import FAISS
    except ImportError:
        raise ImportError(
            "FAISS 向量库未安装。请运行: pip install faiss-cpu"
        )

    index_path = os.path.join(persist_dir, "faiss_index") if persist_dir else None

    if index_path and os.path.exists(index_path):
        # 安全校验：确保 index_path 在预期的数据目录下，防止路径穿越加载恶意文件
        from backend.config.paths import DATA_ROOT
        resolved = os.path.realpath(index_path)
        allowed_root = os.path.realpath(str(DATA_ROOT))
        if not resolved.startswith(allowed_root + os.sep) and resolved != allowed_root:
            raise ValueError(f"FAISS 索引路径非法: {index_path}")
        # 从已存在的索引加载
        vectorstore = FAISS.load_local(
            folder_path=index_path,
            embeddings=embeddings,
            allow_dangerous_deserialization=True,
        )
        log.info(f"💾 RAG 向量库: FAISS (从 {index_path} 加载)")
    else:
        # 创建空索引
        # FAISS 需要一个初始文档来创建索引，这里用空文本占位
        from langchain_core.documents import Document
        vectorstore = FAISS.from_documents(
            [Document(page_content="初始化占位", metadata={"_init": True})],
            embedding=embeddings,
        )
        log.info("💾 RAG 向量库: FAISS (新建)")

    return vectorstore
