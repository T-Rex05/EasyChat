"""
RAG 模块配置

从环境变量读取 RAG 相关配置，遵循项目"环境变量驱动"的统一风格。
下游项目通过 .env 文件配置即可启用 RAG 功能。
"""
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RAGConfig:
    """RAG 管线配置"""

    # ── 向量库配置 ──
    vectorstore_type: str = "chroma"  # chroma | faiss
    persist_dir: str = ""  # 向量库持久化目录（空则使用默认路径）

    # ── 嵌入模型配置 ──
    embedding_provider: str = "openai"  # openai | ollama
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str = ""  # 自定义 API 地址（可选）
    embedding_api_key: str = ""  # 自定义 API Key（可选，默认复用 LLM_API_KEY）

    # ── 文档分割配置 ──
    chunk_size: int = 2000   # 父片默认大小（子片固定600，检索最优）
    chunk_overlap: int = 200

    # ── 检索配置 ──
    top_k: int = 5

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """从环境变量构建配置"""
        project_root = Path(__file__).parent.parent.parent

        # 默认持久化目录：项目根目录/data/rag_vectors/
        default_persist_dir = str(project_root / "data" / "rag_vectors")

        return cls(
            vectorstore_type=os.getenv("RAG_VECTORSTORE_TYPE", "chroma").lower(),
            persist_dir=os.getenv("RAG_PERSIST_DIR", default_persist_dir),
            embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "openai").lower(),
            embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_base_url=os.getenv("RAG_EMBEDDING_BASE_URL", ""),
            embedding_api_key=os.getenv("RAG_EMBEDDING_API_KEY", ""),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "2000")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "200")),
            top_k=int(os.getenv("RAG_TOP_K", "5")),
        )


# 全局配置单例（懒初始化）
_config: RAGConfig = None


def get_rag_config() -> RAGConfig:
    """获取 RAG 配置（全局单例）"""
    global _config
    if _config is None:
        _config = RAGConfig.from_env()
    return _config
