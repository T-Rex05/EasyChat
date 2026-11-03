"""
模型配置分类（聊天 / Embedding）测试

- agent_controller.get_current_model_config 按 category 读取
- model_config_controller 创建/激活按分类互不影响
- rag/embeddings 与 RAGAS 裁判的 embedding 配置 DB 优先
"""
import asyncio
import sys
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


@requires_mysql
class TestModelConfigCategory:
    """注意：model_configs 是全局表，测试会写入真实数据，结束后完整清理并恢复原激活状态。"""

    _created_ids: list = []

    @pytest.fixture(autouse=True)
    def _setup(self):
        from backend.db.schema import init_db
        init_db()
        self._created_ids = []

        # 记录每类当前激活 id，测试后恢复
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT category, id FROM model_configs WHERE is_current = 1")
            self._saved_current = {r["category"]: r["id"] for r in cur.fetchall()}
        finally:
            conn.close()
        yield
        self._cleanup()

    def _conn(self):
        from backend.db.connection_pool import get_pool_connection
        return get_pool_connection()

    def _insert(self, category: str, model: str, url: str = "", is_current: int = 0) -> int:
        conn = self._conn()
        try:
            cur = conn.cursor()
            # 与生产一致：同类仅一个激活，插入前清掉同类其他激活
            if is_current:
                cur.execute("UPDATE model_configs SET is_current = 0 WHERE category = %s", (category,))
            cur.execute(
                "INSERT INTO model_configs "
                "(user_id, config_name, config_type, api_url, api_key, model_name, provider, category, is_multimodal, reasoning_effort, is_current, enabled) "
                "VALUES (1, %s, 'URL', %s, 'sk-test', %s, '', %s, 0, '', %s, 1)",
                (model, url or "https://test.local/v1", model, category, is_current),
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
                ids = ",".join(str(i) for i in self._created_ids)
                cur.execute(f"DELETE FROM model_configs WHERE id IN ({ids})")
            # 恢复原激活状态（每类一个）— 仅当原激活项仍存在时
            for category, cid in (self._saved_current or {}).items():
                cur.execute("SELECT id FROM model_configs WHERE id = %s", (cid,))
                if not cur.fetchone():
                    continue
                cur.execute("UPDATE model_configs SET is_current = 0 WHERE category = %s", (category,))
                cur.execute("UPDATE model_configs SET is_current = 1 WHERE id = %s AND category = %s", (cid, category))
            conn.commit()
        finally:
            conn.close()

    def test_get_current_model_config_by_category(self):
        from backend.controller.agent_controller import get_current_model_config

        chat_id = self._insert("chat", "chat-model-a", is_current=1)
        emb_id = self._insert("embedding", "emb-model-a", is_current=1)

        chat_cfg = get_current_model_config(1, "chat")
        assert chat_cfg and chat_cfg["model_name"] == "chat-model-a"
        assert chat_cfg["category"] == "chat"

        emb_cfg = get_current_model_config(1, "embedding")
        assert emb_cfg and emb_cfg["model_name"] == "emb-model-a"
        assert emb_cfg["category"] == "embedding"

        # 默认 category 仍是 chat（兼容既有调用方）
        assert get_current_model_config(1)["model_name"] == "chat-model-a"

    def test_controller_create_per_category(self):
        from backend.controller import model_config_controller as ctrl

        user = {"user_id": 1, "role": "super_admin", "permissions": set()}
        # 先插入一个 embedding 激活项，再通过控制器创建第二个 embedding → 只有后者激活
        self._insert("embedding", "emb-base", is_current=1)

        async def _run():
            r1 = await ctrl.create_model_config(
                ctrl.ModelConfigCreate(
                    config_name="emb-new", config_type="URL",
                    api_url="https://emb.new/v1", api_key="k", model_name="emb-new-model",
                    category="embedding",
                ),
                user,
            )
            r2 = await ctrl.create_model_config(
                ctrl.ModelConfigCreate(
                    config_name="chat-new", config_type="URL",
                    api_url="https://chat.new/v1", api_key="k", model_name="chat-new-model",
                    category="chat",
                ),
                user,
            )
            return r1, r2

        r1, r2 = asyncio.run(_run())
        assert r1["ok"] and r2["ok"]
        # 控制器创建的行也要纳入清理
        self._created_ids.extend([r1["id"], r2["id"]])

        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, category FROM model_configs WHERE is_current = 1 ORDER BY category")
            currents = {r["category"]: r["id"] for r in cur.fetchall()}
        finally:
            conn.close()

        # 每个分类各自只有 1 个激活，且是最新创建的
        assert currents["embedding"] == r1["id"]
        assert currents["chat"] == r2["id"]

    def test_set_active_within_category(self):
        from backend.controller import model_config_controller as ctrl

        user = {"user_id": 1, "role": "super_admin", "permissions": set()}
        a = self._insert("chat", "chat-a", is_current=1)
        b = self._insert("chat", "chat-b", is_current=0)
        e = self._insert("embedding", "emb-a", is_current=1)

        async def _run():
            return await ctrl.set_active(b, user)

        asyncio.run(_run())
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT category, id FROM model_configs WHERE is_current = 1 ORDER BY category")
            currents = {r["category"]: r["id"] for r in cur.fetchall()}
        finally:
            conn.close()

        assert currents["chat"] == b          # chat 切换到 b
        assert currents["embedding"] == e     # embedding 不受影响

    def test_embeddings_db_first(self):
        from backend.rag.embeddings import get_embeddings

        self._insert("embedding", "emb-openai-model", url="https://emb.test/v1", is_current=1)
        emb = get_embeddings()
        assert emb.__class__.__name__ == "ArrayInputOpenAIEmbeddings"
        assert getattr(emb, "model", None) == "emb-openai-model"

    def test_embeddings_ollama_type(self):
        from backend.rag.embeddings import get_embeddings

        conn = self._conn()
        try:
            cur = conn.cursor()
            # 清掉同类其他激活（含用户真实配置），确保 OLLAMA 行是唯一当前
            cur.execute("UPDATE model_configs SET is_current = 0 WHERE category = 'embedding'")
            cur.execute(
                "INSERT INTO model_configs "
                "(user_id, config_name, config_type, api_url, api_key, model_name, provider, category, is_multimodal, reasoning_effort, is_current, enabled) "
                "VALUES (1, 'ollama-emb', 'OLLAMA', 'http://localhost:11434', 'ollama', 'qwen3-embedding:8b', '', 'embedding', 0, '', 1, 1)"
            )
            conn.commit()
            self._created_ids.append(cur.lastrowid)
        finally:
            conn.close()

        emb = get_embeddings()
        assert emb.__class__.__name__ == "OllamaEmbeddings"
        assert getattr(emb, "model", None) == "qwen3-embedding:8b"

    def test_ragas_embedding_config_db_first(self):
        from backend.service.kb.kb_eval_metrics import _ragas_embedding_config

        # DB-first：插入并激活测试 embedding 配置后，应读到该配置（无论环境是否有真实配置）
        self._insert("embedding", "emb-ragas", url="https://emb.ragas/v1", is_current=1)
        cfg = _ragas_embedding_config()
        assert cfg is not None
        assert cfg["base_url"] == "https://emb.ragas/v1"
        assert cfg["model"] == "emb-ragas"
        assert cfg["api_key"]  # DB 中的 sk-test（明文兼容解密）
