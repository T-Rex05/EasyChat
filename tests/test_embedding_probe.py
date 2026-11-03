"""
Embedding 连通性探测测试

背景：火山方舟（Ark）等平台不实现 OpenAI 的 GET /models，
旧探测逻辑会误报 401。新逻辑对 embedding 分类用 POST /embeddings 真实调用路径探测。

- 端点构造单元测试
- 本地 mock 服务器模拟 Ark 行为（GET → 401；POST /embeddings → 按 Key 返回 200/401）
"""
import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


def _mysql_available() -> bool:
    try:
        from backend.db.connection_pool import get_pool_connection
        conn = get_pool_connection()
        conn.close()
        return True
    except Exception:
        return False


requires_mysql = pytest.mark.skipif(
    not _mysql_available(), reason="MySQL 不可用，跳过 DB 集成测试"
)


class _MockArkHandler(BaseHTTPRequestHandler):
    """模拟火山方舟：GET 一律 401；POST /api/v3/embeddings 按 Key 判定。"""

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(401, {"error": {"message": "Authentication Fails"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        auth = self.headers.get("Authorization", "")
        if auth != "Bearer sk-valid-ark-key":
            self._send(401, {"error": {"message": "Authentication Fails"}})
            return
        self._send(200, {"object": "list", "data": [{"object": "embedding", "index": 0, "embedding": [0.1] * 4}]})

    def log_message(self, *args):  # 静默
        pass


@pytest.fixture(scope="module")
def mock_ark():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockArkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/api/v3"
    server.shutdown()


class TestEmbeddingProbeEndpoints:
    def test_v1_suffix(self):
        from backend.controller.model_config_controller import _build_embedding_probe_endpoints
        assert _build_embedding_probe_endpoints("https://x.com/v1") == ["https://x.com/v1/embeddings"]

    def test_ark_v3(self):
        from backend.controller.model_config_controller import _build_embedding_probe_endpoints
        assert _build_embedding_probe_endpoints("https://ark.cn-beijing.volces.com/api/v3") == [
            "https://ark.cn-beijing.volces.com/api/v3/embeddings",
            "https://ark.cn-beijing.volces.com/api/v3/v1/embeddings",
        ]

    def test_already_embeddings(self):
        from backend.controller.model_config_controller import _build_embedding_probe_endpoints
        assert _build_embedding_probe_endpoints("https://x.com/v1/embeddings") == ["https://x.com/v1/embeddings"]

    def test_dashscope_compatible(self):
        from backend.controller.model_config_controller import _build_embedding_probe_endpoints
        endpoints = _build_embedding_probe_endpoints("https://dashscope.aliyuncs.com/compatible-mode")
        assert endpoints[0] == "https://dashscope.aliyuncs.com/compatible-mode/embeddings"


@requires_mysql
class TestEmbeddingProbeE2E:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from backend.db.schema import init_db
        init_db()
        self._created_ids = []
        yield
        self._cleanup()

    def _conn(self):
        from backend.db.connection_pool import get_pool_connection
        return get_pool_connection()

    def _create_embedding_config(self, base_url: str, api_key: str) -> int:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO model_configs "
                "(user_id, config_name, config_type, api_url, api_key, model_name, provider, category, is_multimodal, reasoning_effort, is_current, enabled) "
                "VALUES (1, 'probe-test', 'URL', %s, %s, 'doubao-embedding-vision', '', 'embedding', 0, '', 0, 1)",
                (base_url, api_key),
            )
            conn.commit()
            self._created_ids.append(cur.lastrowid)
            return cur.lastrowid
        finally:
            conn.close()

    def _cleanup(self):
        conn = self._conn()
        try:
            cur = conn.cursor()
            if self._created_ids:
                cur.execute(
                    "DELETE FROM model_configs WHERE id IN ({})".format(
                        ",".join(str(i) for i in self._created_ids)
                    )
                )
            conn.commit()
        finally:
            conn.close()

    def test_valid_key_ok(self, mock_ark):
        """正确 Key + Ark 风格 Base URL（GET 401 但 POST /embeddings 通过）→ 测试通过。"""
        from backend.controller import model_config_controller as ctrl

        cid = self._create_embedding_config(mock_ark, "sk-valid-ark-key")
        result = asyncio.run(ctrl.test_connection(cid, {"user_id": 1}))
        assert result["ok"] is True, result["message"]
        assert "Key 验证通过" in result["message"]

    def test_invalid_key_rejected(self, mock_ark):
        """错误 Key → POST /embeddings 401 → 明确提示 Key 被拒绝。"""
        from backend.controller import model_config_controller as ctrl

        cid = self._create_embedding_config(mock_ark, "sk-wrong-key")
        result = asyncio.run(ctrl.test_connection(cid, {"user_id": 1}))
        assert result["ok"] is False
        assert "API Key 被拒绝" in result["message"]
        assert "doubao" in result["message"] or "ep-xxx" in result["message"]  # 提示含方舟排查指引
