"""
多模态 Embedding 适配测试（火山方舟 doubao-embedding-vision 等）

- 模型判定 _is_vision_embedding_model
- 探测端点构造（vision → /embeddings/multimodal）
- MultimodalVisionEmbeddings 请求格式与响应解析（mock 服务器）
- get_embeddings 对 vision 模型返回多模态实例
- test_connection 对 vision 配置走 multimodal 探测（mock 服务器）
"""
import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


class _MockVisionArkHandler(BaseHTTPRequestHandler):
    """模拟方舟多模态 embedding：/embeddings/multimodal 按 Key 判定并校验内容块格式。"""

    def _send(self, code: int, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if self.headers.get("Authorization") != "Bearer sk-vision-valid":
            self._send(401, {"error": {"message": "Authentication Fails"}})
            return
        try:
            payload = json.loads(raw)
        except Exception:
            self._send(400, {"error": {"message": "InvalidParameter: bad json"}})
            return
        # 校验内容块格式（vision 模型必须是 block 数组）
        inp = payload.get("input")
        if not isinstance(inp, list) or not all(isinstance(i, dict) and i.get("type") for i in inp):
            self._send(400, {"error": {"message": "InvalidParameter: input must be content blocks"}})
            return
        self._send(200, {
            "object": "list",
            "data": [{"object": "embedding", "index": i, "embedding": [0.1 * (i + 1)] * 4} for i in range(len(inp))],
            "model": payload.get("model", ""),
        })

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def mock_vision():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockVisionArkHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/api/v3"
    server.shutdown()


class TestVisionEmbeddingDetection:
    def test_vision_model(self):
        from backend.rag.embeddings import _is_vision_embedding_model
        assert _is_vision_embedding_model("doubao-embedding-vision-250328") is True
        assert _is_vision_embedding_model("doubao-embedding-vision") is True
        assert _is_vision_embedding_model("xxx-multimodal-1") is True

    def test_text_model(self):
        from backend.rag.embeddings import _is_vision_embedding_model
        assert _is_vision_embedding_model("text-embedding-v3") is False
        assert _is_vision_embedding_model("bge-large-zh") is False
        assert _is_vision_embedding_model("") is False


class TestVisionProbeEndpoints:
    def test_vision_ark_base(self):
        from backend.controller.model_config_controller import _build_embedding_probe_endpoints
        eps = _build_embedding_probe_endpoints("https://ark.cn-beijing.volces.com/api/v3", vision=True)
        assert eps[0] == "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"
        assert "https://ark.cn-beijing.volces.com/api/v3/embeddings" in eps  # 文本端点兜底

    def test_text_ark_base_unchanged(self):
        from backend.controller.model_config_controller import _build_embedding_probe_endpoints
        eps = _build_embedding_probe_endpoints("https://ark.cn-beijing.volces.com/api/v3", vision=False)
        assert eps[0] == "https://ark.cn-beijing.volces.com/api/v3/embeddings"

    def test_already_multimodal(self):
        from backend.controller.model_config_controller import _build_embedding_probe_endpoints
        eps = _build_embedding_probe_endpoints("https://x.com/api/v3/embeddings/multimodal", vision=True)
        assert eps == ["https://x.com/api/v3/embeddings/multimodal"]


class TestMultimodalEmbeddings:
    def test_embed_documents_and_query(self, mock_vision):
        from backend.rag.multimodal_embeddings import MultimodalVisionEmbeddings

        emb = MultimodalVisionEmbeddings(
            base_url=mock_vision, api_key="sk-vision-valid", model="doubao-embedding-vision-250328",
        )
        docs = emb.embed_documents(["天很蓝", "海很深"])
        assert len(docs) == 2 and len(docs[0]) == 4

        q = emb.embed_query("什么是缓存雪崩")
        assert len(q) == 4

    def test_bad_key_raises(self, mock_vision):
        from backend.rag.multimodal_embeddings import MultimodalVisionEmbeddings

        emb = MultimodalVisionEmbeddings(base_url=mock_vision, api_key="sk-wrong", model="doubao-embedding-vision")
        with pytest.raises(RuntimeError):
            emb.embed_query("ping")

    def test_empty_docs(self, mock_vision):
        from backend.rag.multimodal_embeddings import MultimodalVisionEmbeddings

        emb = MultimodalVisionEmbeddings(base_url=mock_vision, api_key="sk-vision-valid", model="m")
        assert emb.embed_documents([]) == []


class TestVisionEmbeddingsFactory:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from backend.db.schema import init_db
        init_db()
        self._created_ids = []
        # ⚠️ 这些用例会直接改**线上库**的 model_configs（把 embedding 的 is_current 清 0
        #    再插入自己的行）。只删自己插入的行、不恢复原激活项的话，跑完测试整个系统的
        #    embedding 就没了 —— 检索全线降级（实测踩过：向量路报 "Request URL is missing
        #    protocol"、记忆 embedding 报 "No embedding config found"）。
        #    这里先快照原状态，teardown 时按快照恢复。
        self._prev_current = self._snapshot_current()
        yield
        conn = self._conn()
        try:
            cur = conn.cursor()
            if self._created_ids:
                cur.execute(
                    "DELETE FROM model_configs WHERE id IN ({})".format(
                        ",".join(str(i) for i in self._created_ids)
                    )
                )
            self._restore_current(cur)
            conn.commit()
        finally:
            conn.close()

    def _snapshot_current(self):
        """快照当前被激活的 (id, category, is_current)。"""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, category, is_current FROM model_configs")
            return [(r["id"], r["category"], int(r["is_current"] or 0)) for r in cur.fetchall()]
        finally:
            conn.close()

    def _restore_current(self, cur):
        for _id, _cat, _cur in self._prev_current:
            cur.execute("UPDATE model_configs SET is_current = %s WHERE id = %s", (_cur, _id))

    def _conn(self):
        from backend.db.connection_pool import get_pool_connection
        return get_pool_connection()

    def _insert_embedding(self, model: str, url: str, api_key: str, is_multimodal: int = 0):
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE model_configs SET is_current = 0 WHERE category = 'embedding'")
            cur.execute(
                "INSERT INTO model_configs "
                "(user_id, config_name, config_type, api_url, api_key, model_name, provider, category, is_multimodal, reasoning_effort, is_current, enabled) "
                "VALUES (1, %s, 'URL', %s, %s, %s, '', 'embedding', %s, '', 1, 1)",
                (model, url, api_key, model, is_multimodal),
            )
            conn.commit()
            self._created_ids.append(cur.lastrowid)
        finally:
            conn.close()

    def test_vision_model_returns_multimodal(self, mock_vision):
        from backend.rag.embeddings import get_embeddings

        self._insert_embedding("doubao-embedding-vision-250328", mock_vision, "sk-vision-valid")
        emb = get_embeddings()
        assert emb.__class__.__name__ == "MultimodalVisionEmbeddings"

    def test_text_model_returns_openai(self, mock_vision):
        from backend.rag.embeddings import get_embeddings

        self._insert_embedding("text-embedding-v3", mock_vision, "sk-vision-valid")
        emb = get_embeddings()
        assert emb.__class__.__name__ == "OpenAIEmbeddings"

    def test_ep_endpoint_with_multimodal_flag(self, mock_vision):
        """ep-xxx 接入点 ID（名字不含 vision）+ 多模态开关 → 走多模态端点。"""
        from backend.rag.embeddings import get_embeddings

        self._insert_embedding("ep-20260814-abcde", mock_vision, "sk-vision-valid", is_multimodal=1)
        emb = get_embeddings()
        assert emb.__class__.__name__ == "MultimodalVisionEmbeddings"

    def test_ep_endpoint_without_flag_text(self, mock_vision):
        """ep-xxx 接入点 ID 未勾选多模态 → 走普通 OpenAI 兼容。"""
        from backend.rag.embeddings import get_embeddings

        self._insert_embedding("ep-20260814-abcde", mock_vision, "sk-vision-valid", is_multimodal=0)
        emb = get_embeddings()
        assert emb.__class__.__name__ == "OpenAIEmbeddings"

    def test_test_connection_vision(self, mock_vision):
        from backend.controller import model_config_controller as ctrl

        self._insert_embedding("doubao-embedding-vision-250328", mock_vision, "sk-vision-valid")
        # 取刚插入的配置 id（当前激活 embedding 分类）
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM model_configs WHERE category = 'embedding' AND is_current = 1 LIMIT 1"
            )
            row = cur.fetchone()
            cid = row["id"]
        finally:
            conn.close()

        result = asyncio.run(ctrl.test_connection(cid, {"user_id": 1}))
        assert result["ok"] is True, result["message"]
        assert "/embeddings/multimodal" in result["tested_url"]
        assert "Key 验证通过" in result["message"]
