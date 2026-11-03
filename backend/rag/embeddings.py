"""
嵌入模型工厂

配置优先级：
1. 数据库 model_configs 表（category='embedding'，is_current=1 的激活项）— 前端「系统配置」管理
2. 环境变量 RAG_EMBEDDING_*（兜底）

支持 OpenAI 兼容（URL 类型 / DashScope 等）与 Ollama 两种提供商。

缓存机制：
- 对相同文本内容的 embedding 结果缓存 24 小时，避免重复调用 API
- 缓存 key: agentforge:embedding:{model}:{sha256(text)[:16]}
- Redis 不可用时自动降级到进程内 LRU 缓存
"""
import os
from typing import Any, List, Optional, Union

from backend.utils.log_utils import log

logger = log


class ArrayInputOpenAIEmbeddings:
    """OpenAI 兼容 Embedding 包装器 — 保证 input 始终为数组格式。

    某些 API（如阿里云 Qwen、火山方舟）严格要求 input 必须是字符串数组，
    而 langchain 的 OpenAIEmbeddings 在部分代码路径中会传空字符串 ""。
    本包装器在 embed_documents / embed_query 入口统一规范化输入，
    比 monkey-patch client.create 更可靠（不受 langchain 内部重建 client 影响）。

    实现 LangChain Embeddings 接口：embed_documents / embed_query。
    """

    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 120.0, dimensions: Optional[int] = None):
        import httpx

        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = timeout
        self.dimensions = dimensions
        self._http = httpx.Client(timeout=timeout)

    def _post(self, payload: dict) -> dict:
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # ★ 如果配置了 dimensions，加入请求体（部分模型支持如 text-embedding-3-*）
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions
        resp = self._http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文本 — 确保 input 为字符串数组，自动分批（API 限制 20 条/批）。

        缓存机制：先检查 Redis 缓存，只对 cache miss 的内容调用 API。
        """
        if not texts:
            return []

        # ★ 核心保障：过滤并确保 input 一定是字符串数组
        input_data = [str(t) if t is not None else "" for t in texts]

        # ── 缓存检查 ──
        from backend.infrastructure import get_cache, get_key_builder
        cache = get_cache()
        kb = get_key_builder()

        # 使用 Dict/List 兼容 Python 3.8+
        from typing import Dict
        cached_results: Dict[int, List[float]] = {}  # index → embedding
        uncached_indices: List[int] = []  # 需要调 API 的索引
        uncached_texts: List[str] = []  # 需要调 API 的文本

        for i, text in enumerate(input_data):
            cache_key = kb.embedding(text, model=self.model)
            cached = cache.get(cache_key)
            if cached is not None:
                cached_results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        cache_hits = len(cached_results)
        if cache_hits > 0:
            logger.debug(f"[Embedding] 缓存命中 {cache_hits}/{len(input_data)}，需调 API {len(uncached_texts)} 条")

        # ── 对 cache miss 的内容调 API ──
        if uncached_texts:
            batch_size = 20
            new_embeddings: List[List[float]] = []
            for start in range(0, len(uncached_texts), batch_size):
                batch = uncached_texts[start:start + batch_size]
                payload = {"input": batch, "model": self.model}
                resp = self._post(payload)
                if "data" not in resp:
                    logger.error(f"embed_documents: 响应缺少 'data' 字段, keys={list(resp.keys())}")
                    raise RuntimeError(f"Embedding API 响应格式错误: {str(resp)[:200]}")
                batch_embeddings = [item["embedding"] for item in sorted(resp["data"], key=lambda x: x["index"])]
                new_embeddings.extend(batch_embeddings)

            # ★ 数量一致性校验：下面按索引合并结果时用 new_embeddings[new_idx] 定位，
            #   若 API 返回条数少于请求条数，会抛出难以定位的 IndexError（并让
            #   zip() 静默漏写缓存）。这里显式失败，错误信息能直接指出问题来源。
            if len(new_embeddings) != len(uncached_indices):
                raise RuntimeError(
                    f"Embedding API 返回数量不匹配: 请求 {len(uncached_indices)} 条, "
                    f"实际返回 {len(new_embeddings)} 条 (model={self.model})"
                )

            # 写入缓存（24h TTL + 1h jitter）
            for idx, embedding in zip(uncached_indices, new_embeddings):
                text = input_data[idx]
                cache_key = kb.embedding(text, model=self.model)
                cache.set_with_jitter(cache_key, embedding, base_ttl=86400, jitter_range=3600)

            # 合并结果：按原始顺序
            all_embeddings: List[List[float]] = []
            cached_dict = dict(cached_results)
            new_idx = 0
            for i in range(len(input_data)):
                if i in cached_dict:
                    all_embeddings.append(cached_dict[i])
                else:
                    all_embeddings.append(new_embeddings[new_idx])
                    new_idx += 1
            return all_embeddings
        else:
            # 全部命中缓存
            return [cached_results[i] for i in range(len(input_data))]

    def embed_query(self, text: str) -> List[float]:
        """单条查询嵌入 — 包装为数组调用 embed_documents。"""
        # ★ 核心保障：始终用数组调用，不传裸字符串
        result = self.embed_documents([str(text) if text is not None else ""])
        return result[0]


def _create_openai_embeddings(model: str, api_key: str = None, base_url: str = None,
                               dimensions: Optional[int] = None):
    """
    创建兼容不同 API 要求的 OpenAI Embeddings 实例。

    使用 ArrayInputOpenAIEmbeddings 包装器，自动保证 input 始终为数组格式，
    兼容严格要求 input 为数组的 API（如阿里云 Qwen、火山方舟）。

    Args:
        model: 模型名称
        api_key: API 密钥
        base_url: API 基础 URL
        dimensions: 输出向量维度（可选，部分模型支持如 text-embedding-3-*）

    Returns:
        ArrayInputOpenAIEmbeddings 实例（实现 LangChain Embeddings 接口）
    """
    logger.info(f"[Embedding] 创建 ArrayInputOpenAIEmbeddings: model={model}, base_url={base_url}, dimensions={dimensions}")
    return ArrayInputOpenAIEmbeddings(
        model=model,
        api_key=api_key or "",
        base_url=base_url or "",
        dimensions=dimensions,
    )


def _get_db_embedding_config() -> Optional[dict]:
    """
    从 model_configs 表读取分类 embedding 的激活配置（解密 api_key）。

    Returns:
        {"provider": "openai"|"ollama", "model", "base_url", "api_key"} 或 None
    """
    try:
        from backend.db.connection_pool import get_pool_connection
        conn = get_pool_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT config_type, api_url, api_key, model_name, is_multimodal, "
                "dimension, send_dimensions "
                "FROM model_configs WHERE category = 'embedding' AND is_current = 1 AND enabled = 1 LIMIT 1"
            )
            row = cur.fetchone()
            if not row:
                return None
            api_key = row.get("api_key") or ""
            try:
                from backend.utils.crypto_utils import decrypt
                api_key = decrypt(api_key)
            except Exception:
                pass  # 明文兼容
            api_key = (api_key or "").strip()  # 容错：去除粘贴带入的空格/换行
            _ct = (row.get("config_type") or "").upper()
            is_ollama = _ct == "OLLAMA"
            is_local = _ct == "LOCAL"
            # dimensions：仅当 send_dimensions=1 且 dimension>0 时传给 API
            _dim = int(row.get("dimension") or 0)
            _send_dim = bool(row.get("send_dimensions"))
            dimensions = _dim if (_send_dim and _dim > 0) else None
            return {
                "provider": "ollama" if is_ollama else ("local" if is_local else "openai"),
                "model": row.get("model_name") or "text-embedding-3-small",
                "base_url": (row.get("api_url") or "").strip(),
                "api_key": api_key,
                "dimensions": dimensions,
                # 多模态 Embedding 开关（前端可勾选；模型名含 vision/multimodal 也可自动识别）
                "multimodal": bool(row.get("is_multimodal")),
            }
        finally:
            conn.close()
    except Exception:
        return None


def get_embeddings():
    """
    获取嵌入模型实例。

    优先级：DB embedding 分类配置 > 环境变量。
    根据 provider 选择：
    - openai: 使用 OpenAI Embeddings（默认，兼容 DashScope 等）
    - ollama: 使用 Ollama 本地 Embeddings

    特殊：模型名含 vision/multimodal（如火山方舟 doubao-embedding-vision）
    走 /embeddings/multimodal 多模态端点（见 MultimodalVisionEmbeddings）。
    """
    # ── 1. 数据库配置（前端「系统配置」维护）──
    db_cfg = _get_db_embedding_config()
    if db_cfg:
        embeddings = _build_embeddings_from_cfg(db_cfg)
        log.info(f"🔢 RAG 嵌入模型(DB): {db_cfg['model']} @ {db_cfg['base_url'] or '(默认地址)'}")
        return embeddings

    # ── 2. 环境变量兜底 ──
    from backend.rag.config import get_rag_config
    config = get_rag_config()
    provider = config.embedding_provider.lower()

    if provider in ("openai", "local"):
        return _get_openai_embeddings(config)
    elif provider == "ollama":
        return _get_ollama_embeddings(config)
    else:
        raise ValueError(
            f"不支持的嵌入模型提供商: {provider}。"
            f"支持的提供商: openai, ollama, local（本地 BGE 服务）"
        )


def _is_vision_embedding_model(model: str) -> bool:
    """多模态 embedding 模型判定（doubao-embedding-vision / xxx-multimodal 等）。"""
    m = (model or "").lower()
    return "vision" in m or "multimodal" in m


def _build_embeddings_from_cfg(cfg: dict):
    """根据配置构建 embedding 实例（openai 兼容 / ollama / local 本地 BGE / 多模态）。

    多模态判定：模型名含 vision/multimodal，或配置显式开启 multimodal 开关（ep-xxx 接入点场景）。
    """
    if cfg["provider"] == "ollama":
        return _get_ollama_embeddings_from_cfg(cfg)
    if cfg["provider"] == "local":
        return _get_openai_embeddings_from_cfg(cfg)  # 本地 BGE 服务为 OpenAI 兼容
    if _is_vision_embedding_model(cfg.get("model")) or cfg.get("multimodal"):
        from backend.rag.multimodal_embeddings import MultimodalVisionEmbeddings
        return MultimodalVisionEmbeddings(
            base_url=cfg.get("base_url") or "",
            api_key=cfg.get("api_key") or "",
            model=cfg.get("model") or "",
        )
    return _get_openai_embeddings_from_cfg(cfg)


def _get_openai_embeddings_from_cfg(cfg: dict):
    """从 DB 配置创建 OpenAI Embeddings 实例。"""
    return _create_openai_embeddings(
        model=cfg["model"],
        api_key=cfg.get("api_key"),
        base_url=cfg.get("base_url"),
        dimensions=cfg.get("dimensions"),
    )


def _get_ollama_embeddings_from_cfg(cfg: dict):
    """从 DB 配置创建 Ollama Embeddings 实例。"""
    from langchain_ollama import OllamaEmbeddings

    base_url = cfg.get("base_url") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return OllamaEmbeddings(model=cfg["model"], base_url=base_url)


def _get_openai_embeddings(config):
    """创建 OpenAI Embeddings 实例（env 配置）"""
    # API Key 优先级：RAG_EMBEDDING_API_KEY > LLM_API_KEY
    api_key = config.embedding_api_key or os.getenv("LLM_API_KEY", "")
    base_url = config.embedding_base_url or os.getenv("LLM_BASE_URL", "")

    # 多模态 embedding 模型（env 配置）走自定义端点
    if _is_vision_embedding_model(config.embedding_model):
        from backend.rag.multimodal_embeddings import MultimodalVisionEmbeddings
        embeddings = MultimodalVisionEmbeddings(
            base_url=base_url, api_key=api_key, model=config.embedding_model,
        )
        log.info(f"🔢 RAG 嵌入模型: 多模态 ({config.embedding_model})")
        return embeddings

    embeddings = _create_openai_embeddings(
        model=config.embedding_model,
        api_key=api_key,
        base_url=base_url
    )
    log.info(f"🔢 RAG 嵌入模型: OpenAI ({config.embedding_model})")
    return embeddings


def _get_ollama_embeddings(config):
    """创建 Ollama Embeddings 实例"""
    from langchain_ollama import OllamaEmbeddings

    base_url = config.embedding_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    embeddings = OllamaEmbeddings(
        model=config.embedding_model,
        base_url=base_url,
    )
    log.info(f"🔢 RAG 嵌入模型: Ollama ({config.embedding_model} @ {base_url})")
    return embeddings
