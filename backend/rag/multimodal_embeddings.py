"""
多模态 Embedding 模型适配（火山方舟 doubao-embedding-vision 等）

与普通 OpenAI 兼容 embedding 的差异：
- 端点：POST {base}/embeddings/multimodal（而非 {base}/embeddings）
- 请求格式：input 为内容块数组 [{"type":"text","text":...}, {"type":"image_url",...}]

本类实现 LangChain Embeddings 接口（embed_documents / embed_query），
知识库向量化与检索可直接使用；文本块格式：
    [{"type": "text", "text": "<内容>"}]
图片 URL 块暂不用于知识库（当前 KB 为纯文本 chunk）。
"""
from typing import List

import httpx

from backend.utils.log_utils import log

logger = log


class MultimodalVisionEmbeddings:
    """OpenAI 兼容多模态 Embedding（如火山方舟 doubao-embedding-vision）。

    属性对齐 LangChain Embeddings 接口：embed_documents / embed_query。
    """

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120.0):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = timeout

    # ── 接口 ──

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文本（一次请求提交全部文本块）。"""
        if not texts:
            return []
        blocks = [{"type": "text", "text": t} for t in texts]
        resp = self._post(blocks)
        # 调试：检查响应格式
        if not isinstance(resp, dict):
            logger.error(f"embed_documents: _post 返回了非 dict 类型: {type(resp).__name__}")
            logger.error(f"响应内容: {str(resp)[:500]}")
            raise RuntimeError(f"Embedding API 返回格式错误: {type(resp).__name__}")
        if "data" not in resp:
            logger.error(f"embed_documents: 响应缺少 'data' 字段, keys={list(resp.keys())}")
            raise RuntimeError(f"Embedding API 响应缺少 'data' 字段")
        
        data_field = resp["data"]
        
        # 兼容火山方舟 doubao-embedding-vision 格式：data 可能是 dict 或 list
        if isinstance(data_field, dict):
            # 火山方舟格式：{"data": {"embedding": [...]}}
            # 但这是单条文本的格式，批量时需要特殊处理
            logger.warning(f"embed_documents: 'data' 是 dict（火山方舟格式），但批量请求需要 list 格式")
            logger.warning(f"火山方舟多模态 embedding 可能不支持批量，将逐条处理")
            # 逐条处理
            embeddings = []
            for i, text in enumerate(texts):
                single_blocks = [{"type": "text", "text": text}]
                single_resp = self._post(single_blocks)
                single_data = single_resp.get("data", {})
                if isinstance(single_data, dict):
                    emb = single_data.get("embedding", [])
                    embeddings.append(list(emb))
                elif isinstance(single_data, list) and single_data:
                    emb = single_data[0].get("embedding", [])
                    embeddings.append(list(emb))
                else:
                    raise RuntimeError(f"第 {i} 条文本的 embedding 格式错误")
            return embeddings
        
        # 标准 OpenAI 格式：{"data": [{"embedding": [...]}, ...]}
        if not isinstance(data_field, list):
            logger.error(f"embed_documents: 'data' 不是列表: {type(data_field).__name__}")
            raise RuntimeError(f"'data' 字段格式错误")
        
        # 检查每个元素
        for i, d in enumerate(data_field):
            if not isinstance(d, dict):
                logger.error(f"embed_documents: data[{i}] 不是 dict: {type(d).__name__}, value={str(d)[:200]}")
                raise RuntimeError(f"data[{i}] 格式错误")
            if "embedding" not in d:
                logger.error(f"embed_documents: data[{i}] 缺少 'embedding' 字段, keys={list(d.keys())}")
                raise RuntimeError(f"data[{i}] 缺少 'embedding' 字段")
        
        return [list(d["embedding"]) for d in data_field]

    def embed_query(self, text: str) -> List[float]:
        """嵌入单条查询文本。"""
        blocks = [{"type": "text", "text": text}]
        resp = self._post(blocks)
        if not resp.get("data"):
            return []
        data_field = resp["data"]
        # 火山方舟格式：{"data": {"embedding": [...]}}（单条 dict）
        if isinstance(data_field, dict):
            emb = data_field.get("embedding", [])
            return list(emb)
        # 标准 OpenAI 格式：{"data": [{"embedding": [...]}, ...]}
        if isinstance(data_field, list) and data_field:
            return list(data_field[0]["embedding"])
        return []

    # ── 内部 ──

    def _endpoint(self) -> str:
        base = self.base_url
        if base.endswith("/embeddings/multimodal"):
            return base
        return f"{base}/embeddings/multimodal"

    def _post(self, blocks: List[dict]) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "input": blocks}
        try:
            resp = httpx.post(
                self._endpoint(),
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            result = resp.json()
            # 验证返回格式
            if not isinstance(result, dict):
                logger.error(f"多模态 Embedding API 返回格式错误：期望 dict，实际 {type(result).__name__}")
                logger.error(f"响应内容: {str(result)[:500]}")
                raise RuntimeError(f"API 返回格式错误：期望 dict，实际 {type(result).__name__}: {str(result)[:200]}")
            logger.debug(f"多模态 Embedding API 响应: keys={list(result.keys())}, data_count={len(result.get('data', []))}")
            return result
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.text[:300]
            except Exception:
                pass
            raise RuntimeError(
                f"多模态 Embedding 请求失败（HTTP {e.response.status_code}）：{detail}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"多模态 Embedding 请求失败: {e}") from e
