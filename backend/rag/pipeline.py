"""
RAG Pipeline — 检索增强生成管线

核心职责：
1. 文档摄入（Ingest）：加载 → 分割 → 嵌入 → 存入向量库
2. 语义检索（Retrieve）：问题 → 嵌入 → 向量相似度搜索
3. 便捷方法：支持文件路径、纯文本等多种摄入方式

下游开发者使用示例：
    from backend.rag import get_rag_pipeline

    pipeline = get_rag_pipeline()

    # 摄入文档
    pipeline.ingest_files(["./docs/manual.pdf", "./docs/faq.md"])

    # 检索
    results = pipeline.retrieve("如何报销？")
"""
import os
from pathlib import Path
from typing import List, Optional, Union

from backend.rag.config import get_rag_config
from backend.utils.log_utils import log


class RAGPipeline:
    """RAG 管线 — 封装文档摄入和语义检索的完整流程"""

    def __init__(self, embeddings=None, vectorstore=None):
        """
        初始化 RAG 管线。

        Args:
            embeddings: 嵌入模型实例（可选，不提供则自动创建）
            vectorstore: 向量库实例（可选，不提供则自动创建）
        """
        self._config = get_rag_config()
        self._embeddings = embeddings
        self._vectorstore = vectorstore

    @property
    def embeddings(self):
        """懒加载嵌入模型"""
        if self._embeddings is None:
            from backend.rag.embeddings import get_embeddings
            self._embeddings = get_embeddings()
        return self._embeddings

    @property
    def vectorstore(self):
        """懒加载向量库"""
        if self._vectorstore is None:
            from backend.rag.vectorstore import get_vectorstore
            self._vectorstore = get_vectorstore(self.embeddings)
        return self._vectorstore

    # ── 文档摄入 ──

    def ingest(self, loader) -> int:
        """
        使用 LangChain DocumentLoader 摄入文档。

        Args:
            loader: LangChain 文档加载器实例（如 PyPDFLoader、TextLoader 等）

        Returns:
            int: 成功摄入的文档块数量

        示例：
            from langchain_community.document_loaders import PyPDFLoader
            loader = PyPDFLoader("./docs/manual.pdf")
            count = pipeline.ingest(loader)
        """
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        # 加载文档
        docs = loader.load()
        log.info(f"📄 加载 {len(docs)} 个文档")

        # 分割文档
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._config.chunk_size,
            chunk_overlap=self._config.chunk_overlap,
        )
        chunks = splitter.split_documents(docs)
        log.info(f"✂️ 分割为 {len(chunks)} 个文档块")

        # 存入向量库
        self.vectorstore.add_documents(chunks)
        log.info(f"✅ 已摄入 {len(chunks)} 个文档块到向量库")

        return len(chunks)

    def ingest_files(
        self,
        file_paths: Union[str, List[str]],
        loader_type: Optional[str] = None,
    ) -> int:
        """
        从文件路径摄入文档（便捷方法）。

        自动根据文件后缀选择加载器：
        - .pdf → PyPDFLoader
        - .txt / .md → TextLoader
        - 其他 → TextLoader（默认）

        Args:
            file_paths: 文件路径（单个字符串或列表）
            loader_type: 强制指定加载器类型（如 "pdf"、"text"），可选

        Returns:
            int: 成功摄入的文档块数量
        """
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        total_chunks = 0
        for file_path in file_paths:
            file_path = str(file_path)
            if not os.path.exists(file_path):
                log.warning(f"⚠️ 文件不存在，跳过: {file_path}")
                continue

            loader = self._create_loader(file_path, loader_type)
            if loader:
                try:
                    chunks = self.ingest(loader)
                    total_chunks += chunks
                except Exception as e:
                    log.error(f"❌ 摄入文件失败 {file_path}: {e}")

        return total_chunks

    def ingest_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[dict]] = None,
    ) -> int:
        """
        直接摄入纯文本（便捷方法）。

        Args:
            texts: 文本列表
            metadatas: 每条文本的元数据（可选）

        Returns:
            int: 成功摄入的文本块数量
        """
        from langchain_core.documents import Document

        if metadatas is None:
            metadatas = [{} for _ in texts]

        docs = [
            Document(page_content=text, metadata=meta)
            for text, meta in zip(texts, metadatas)
        ]

        self.vectorstore.add_documents(docs)
        log.info(f"✅ 已摄入 {len(docs)} 条文本到向量库")
        return len(docs)

    # ── 语义检索 ──

    def retrieve(self, query: str, k: Optional[int] = None) -> list:
        """
        语义检索：根据问题从向量库中搜索最相关的文档块。

        Args:
            query: 查询问题
            k: 返回结果数量（可选，默认使用配置中的 RAG_TOP_K）

        Returns:
            list: 文档块列表（LangChain Document 对象）
        """
        if k is None:
            k = self._config.top_k

        results = self.vectorstore.similarity_search(query, k=k)
        log.info(f"🔍 检索到 {len(results)} 个相关文档块 (query={query[:50]}...)")
        return results

    def retrieve_as_context(self, query: str, k: Optional[int] = None) -> str:
        """
        检索并拼接为上下文文本（可直接塞入提示词）。

        Args:
            query: 查询问题
            k: 返回结果数量

        Returns:
            str: 拼接后的上下文文本
        """
        docs = self.retrieve(query, k)
        if not docs:
            return ""

        context_parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知来源")
            context_parts.append(f"[{i}] 来源: {source}\n{doc.page_content}")

        return "\n\n---\n\n".join(context_parts)

    # ── 内部方法 ──

    def _create_loader(self, file_path: str, loader_type: Optional[str] = None):
        """根据文件类型创建文档加载器"""
        ext = os.path.splitext(file_path)[1].lower()

        # 强制指定加载器类型
        if loader_type:
            ext = f".{loader_type}"

        if ext == ".pdf":
            try:
                from langchain_community.document_loaders import PyPDFLoader
                return PyPDFLoader(file_path)
            except ImportError:
                log.warning("⚠️ PyPDFLoader 未安装，请运行: pip install pypdf")
                return None

        elif ext in (".txt", ".md", ".markdown"):
            from langchain_community.document_loaders import TextLoader
            return TextLoader(file_path, encoding="utf-8")

        elif ext in (".docx", ".doc"):
            try:
                from langchain_community.document_loaders import Docx2txtLoader
                return Docx2txtLoader(file_path)
            except ImportError:
                log.warning("⚠️ Docx2txtLoader 未安装，请运行: pip install python-docx")
                return None

        else:
            # 默认用 TextLoader
            from langchain_community.document_loaders import TextLoader
            return TextLoader(file_path, encoding="utf-8")


# ── 全局单例 ──

_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    """
    获取 RAG 管线实例（全局单例，懒初始化）。

    Returns:
        RAGPipeline: RAG 管线实例
    """
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline
