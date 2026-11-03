"""本地 Embedding 服务（借鉴 Eyes local_embedding_server）

独立 FastAPI 进程跑 BGE 模型（CPU 可跑），OpenAI 兼容 POST /v1/embeddings。
用于无外部 embedding API 的场景（如 DeepSeek 无 embedding）：

  1. pip install sentence-transformers（可选依赖）
  2. python scripts/start_local_embedding.py（默认端口 8081）
  3. .env 配置 RAG_EMBEDDING_PROVIDER=local、RAG_EMBEDDING_BASE_URL=http://localhost:8081/v1

env：BGE_MODEL_NAME（默认 BAAI/bge-large-zh-v1.5）/ BGE_MODEL_PATH（本地权重路径）
     BGE_DEVICE（cpu/cuda）/ BGE_NORMALIZE / BGE_BATCH_SIZE
"""
import logging
import os
from functools import lru_cache
from typing import List, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("local_embedding_server")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

BGE_MODEL_NAME = os.getenv("BGE_MODEL_NAME", "BAAI/bge-large-zh-v1.5")
BGE_MODEL_PATH = os.getenv("BGE_MODEL_PATH", "")
BGE_DEVICE = os.getenv("BGE_DEVICE", "cpu")
BGE_NORMALIZE = os.getenv("BGE_NORMALIZE", "true").lower() not in {"0", "false", "no"}
BGE_BATCH_SIZE = int(os.getenv("BGE_BATCH_SIZE", "8"))
BGE_MAX_TEXTS_PER_REQUEST = int(os.getenv("BGE_MAX_TEXTS_PER_REQUEST", "64"))

app = FastAPI(title="AgentForge Local BGE Embedding Service")


class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: str = Field(default=BGE_MODEL_NAME)


@lru_cache(maxsize=1)
def load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise RuntimeError(
            "sentence-transformers 未安装。请先 pip install sentence-transformers（可选依赖）。"
        ) from exc
    model_source = BGE_MODEL_PATH if BGE_MODEL_PATH and os.path.exists(BGE_MODEL_PATH) else BGE_MODEL_NAME
    logger.info("加载 BGE 模型 source=%s device=%s", model_source, BGE_DEVICE)
    return SentenceTransformer(model_source, device=BGE_DEVICE)


def encode_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = load_model()
    vectors = model.encode(
        texts,
        batch_size=BGE_BATCH_SIZE,
        normalize_embeddings=BGE_NORMALIZE,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


@app.post("/v1/embeddings")
async def create_embeddings(req: EmbeddingRequest):
    texts = [req.input] if isinstance(req.input, str) else req.input
    if len(texts) > BGE_MAX_TEXTS_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"单次最多 {BGE_MAX_TEXTS_PER_REQUEST} 条文本")
    vectors = encode_texts([str(t) for t in texts])
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": v}
            for i, v in enumerate(vectors)
        ],
        "model": req.model,
        "usage": {"prompt_tokens": sum(len(t) for t in texts), "total_tokens": sum(len(t) for t in texts)},
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": BGE_MODEL_NAME, "device": BGE_DEVICE}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BGE_PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port)