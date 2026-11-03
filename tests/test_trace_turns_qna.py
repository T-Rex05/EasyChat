"""
可观测性 — 按会话聚合 + 用户问题/AI 回复 测试

- list_turns(with_text=True) 从 conversations 表附加 user_question / ai_reply
- conversations 缺失时回退 traces.prompt_text / completion_text
- /api/traces/all aggregated=1 返回 turns（含问答）
"""
import sys
import uuid
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
class TestTraceTurnsQna:
    _sessions: list = []

    @pytest.fixture(autouse=True)
    def _setup(self):
        from backend.db.schema import init_db
        init_db()
        self._sessions = []
        yield
        self._cleanup()

    def _conn(self):
        from backend.db.schema import get_conn
        return get_conn()

    def _insert_trace(self, session_id: str, user_id: int = 888001, prompt: str = "", completion: str = ""):
        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO traces (session_id, user_id, source, model, provider, turn_index, "
                "input_tokens, output_tokens, total_tokens, latency_ms, status, prompt_text, completion_text) "
                "VALUES (?, ?, 'web', 'test-model', '', 0, 10, 20, 30, 100, 1, ?, ?)",
                (session_id, user_id, prompt, completion),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _insert_conversation(self, session_id: str, question: str, answer: str, user_id: int = 888001):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO conversations (session_id, user_id, user_question, agent_answer, status, source) "
                "VALUES (?, ?, ?, ?, 1, 'web')",
                (session_id, user_id, question, answer),
            )
            conn.commit()
        finally:
            conn.close()

    def _cleanup(self):
        if not self._sessions:
            return
        conn = self._conn()
        try:
            ph = ",".join("?" for _ in self._sessions)
            conn.execute(f"DELETE FROM conversations WHERE session_id IN ({ph})", self._sessions)
            conn.execute(f"DELETE FROM traces WHERE session_id IN ({ph})", self._sessions)
            conn.commit()
        finally:
            conn.close()

    def _new_session(self) -> str:
        sid = f"test_qna_{uuid.uuid4().hex[:12]}"
        self._sessions.append(sid)
        return sid

    def test_attach_qna_from_conversations(self):
        from backend.service.trace.query import list_turns

        sid = self._new_session()
        self._insert_trace(sid, prompt="旧文本问题", completion="旧文本回复")
        self._insert_conversation(sid, "缓存雪崩是什么？", "缓存雪崩是大量 key 同时过期...")

        result = list_turns(user_id=888001, with_text=True)
        turn = next(t for t in result["turns"] if t["session_id"] == sid)
        assert turn["user_question"] == "缓存雪崩是什么？"
        assert "缓存雪崩是" in turn["ai_reply"]
        assert turn["api_calls"] == 1

    def test_attach_qna_fallback_to_traces(self):
        from backend.service.trace.query import list_turns

        sid = self._new_session()
        # 只有 traces 文本（无 conversations 记录）→ 回退
        self._insert_trace(sid, prompt="JWT 为什么无状态？", completion="因为服务端不保存会话...")

        result = list_turns(user_id=888001, with_text=True)
        turn = next(t for t in result["turns"] if t["session_id"] == sid)
        assert turn["user_question"] == "JWT 为什么无状态？"
        assert "服务端不保存" in turn["ai_reply"]

    def test_without_text_no_qna_fields(self):
        from backend.service.trace.query import list_turns

        sid = self._new_session()
        self._insert_trace(sid, prompt="问题", completion="回复")
        self._insert_conversation(sid, "问题", "回复")

        result = list_turns(user_id=888001, with_text=False)
        turn = next(t for t in result["turns"] if t["session_id"] == sid)
        assert "user_question" not in turn
        assert "ai_reply" not in turn

    def test_turn_detail_qna_list(self):
        """turn_detail 返回会话全部问答轮次（多轮）。"""
        from backend.controller import trace_controller as ctrl
        import asyncio

        sid = self._new_session()
        self._insert_trace(sid, prompt="", completion="")
        self._insert_conversation(sid, "第一问：缓存雪崩？", "第一答：缓存雪崩是...")
        self._insert_conversation(sid, "第二问：如何解决？", "第二答：加随机过期时间...")

        detail = asyncio.run(ctrl.turn_detail(sid, {"user_id": 888001, "role": "user", "permissions": set()}))
        assert len(detail["qna_list"]) == 2
        assert detail["qna_list"][0]["question"] == "第一问：缓存雪崩？"
        assert "第二答" in detail["qna_list"][1]["reply"]

    def test_turn_detail_qna_empty(self):
        """无 conversations 记录时 qna_list 为空数组（不报错）。"""
        from backend.controller import trace_controller as ctrl
        import asyncio

        sid = self._new_session()
        self._insert_trace(sid, prompt="", completion="")

        detail = asyncio.run(ctrl.turn_detail(sid, {"user_id": 888001, "role": "user", "permissions": set()}))
        assert detail["qna_list"] == []

    def test_all_endpoint_aggregated(self):
        from backend.controller import trace_controller as ctrl
        import asyncio

        sid = self._new_session()
        self._insert_trace(sid, prompt="", completion="")
        self._insert_conversation(sid, "Kafka 如何顺序消费？", "单分区内写入有序...")

        # 管理员查看指定用户聚合记录
        async def _run():
            return await ctrl.list_all_traces(
                user_id=888001, username="", session_id="", model="", source="",
                status=-1, days=0, when="", aggregated=1, offset=0, limit=50,
                user={"user_id": 1, "role": "super_admin", "permissions": set()},
            )

        result = asyncio.run(_run())
        turns = result.get("turns", [])
        turn = next(t for t in turns if t["session_id"] == sid)
        assert turn["user_question"] == "Kafka 如何顺序消费？"
        assert "单分区" in turn["ai_reply"]

        # 原始模式仍返回 traces 字段
        async def _run_raw():
            return await ctrl.list_all_traces(
                user_id=888001, username="", session_id="", model="", source="",
                status=-1, days=0, when="", aggregated=0, offset=0, limit=50,
                user={"user_id": 1, "role": "super_admin", "permissions": set()},
            )

        raw = asyncio.run(_run_raw())
        assert "traces" in raw and raw["total"] >= 1
