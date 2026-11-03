"""
RAG 模块 — 检索增强生成能力

提供文档摄入和语义检索功能，让 Agent 能够基于知识库回答问题。

快速开始：
    from backend.rag import get_rag_pipeline

    pipeline = get_rag_pipeline()

    # 摄入文档
    pipeline.ingest_files(["./docs/manual.pdf"])

    # 检索
    results = pipeline.retrieve("如何报销？")

配置（通过 .env 环境变量）：
    RAG_VECTORSTORE_TYPE=chroma          # 向量库类型: chroma | faiss
    RAG_EMBEDDING_PROVIDER=openai        # 嵌入模型: openai | ollama
    RAG_EMBEDDING_MODEL=text-embedding-3-small
    RAG_CHUNK_SIZE=1000                  # 文档分割块大小
    RAG_CHUNK_OVERLAP=200                # 块重叠大小
    RAG_TOP_K=5                          # 检索返回数量
    RAG_PERSIST_DIR=./data/rag_vectors   # 向量库持久化目录
"""

# 公开 API
from backend.rag.config import RAGConfig, get_rag_config
from backend.rag.embeddings import get_embeddings
from backend.rag.vectorstore import get_vectorstore
from backend.rag.pipeline import RAGPipeline, get_rag_pipeline

__all__ = [
    "RAGConfig",
    "get_rag_config",
    "get_embeddings",
    "get_vectorstore",
    "RAGPipeline",
    "get_rag_pipeline",
]
