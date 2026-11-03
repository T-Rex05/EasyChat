"""会话自动标题单元测试"""
import asyncio

from backend.service.session_title import (
    _clean_title, auto_title_enabled, schedule_auto_title, auto_title_task,
)


class TestCleanTitle:
    def test_clean_basic(self):
        assert _clean_title('"会议纪要"') == "会议纪要"
        assert _clean_title("\"总结\"") == "总结"

    def test_clean_newlines(self):
        assert _clean_title("第一行\n第二行") == "第一行 第二行"

    def test_clean_truncate(self):
        assert len(_clean_title("x" * 100)) == 30

    def test_clean_empty(self):
        assert _clean_title("") == ""
        assert _clean_title(None) == ""


class TestAutoTitleEnabled:
    def test_default_enabled(self, monkeypatch):
        monkeypatch.delenv("AUTO_SESSION_TITLE", raising=False)
        assert auto_title_enabled() is True

    def test_explicit_false(self, monkeypatch):
        monkeypatch.setenv("AUTO_SESSION_TITLE", "false")
        assert auto_title_enabled() is False


class TestScheduleAutoTitle:
    def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setenv("AUTO_SESSION_TITLE", "false")
        assert schedule_auto_title("s1", 1, "hello") is None

    def test_enabled_schedules_task(self, monkeypatch):
        monkeypatch.setenv("AUTO_SESSION_TITLE", "true")
        called = []

        async def fake_task(session_id, user_id, first_message):
            called.append((session_id, user_id, first_message))

        monkeypatch.setattr("backend.service.session_title.auto_title_task", fake_task)

        async def main():
            t = schedule_auto_title("s1", 7, "hi")
            assert t is not None
            await t
            assert called == [("s1", 7, "hi")]

        asyncio.run(main())


class TestAutoTitleTask:
    def test_no_config_returns_none(self, monkeypatch):
        monkeypatch.setenv("AUTO_SESSION_TITLE", "true")
        monkeypatch.setattr(
            "backend.controller.agent_controller.get_current_model_config",
            lambda uid, category="chat": None,
        )

        async def main():
            assert await auto_title_task("s1", 1, "hi") is None

        asyncio.run(main())

    def test_writes_title_to_db(self, monkeypatch):
        monkeypatch.setenv("AUTO_SESSION_TITLE", "true")
        monkeypatch.setattr(
            "backend.controller.agent_controller.get_current_model_config",
            lambda uid, category="chat": {"api_key": "k", "model_name": "m", "api_url": "http://x/v1"},
        )

        async def fake_gen(cfg, msg, timeout=15.0):
            return "测试标题"

        monkeypatch.setattr("backend.service.session_title.generate_title_with_llm", fake_gen)

        executed = []

        class FakeCur:
            def execute(self, sql, params):
                executed.append((sql, params))

        class FakeConn:
            def __init__(self):
                self._cur = FakeCur()

            def cursor(self):
                return self._cur

            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr("backend.db.connection_pool.get_pool_connection", lambda: FakeConn())

        async def main():
            title = await auto_title_task("s1", 1, "hello world")
            assert title == "测试标题"
            assert len(executed) == 1
            sql, params = executed[0]
            assert "session_title" in sql
            assert params[0] == "测试标题" and params[1] == "s1"

        asyncio.run(main())

    def test_llm_failure_silent(self, monkeypatch):
        monkeypatch.setenv("AUTO_SESSION_TITLE", "true")
        monkeypatch.setattr(
            "backend.controller.agent_controller.get_current_model_config",
            lambda uid, category="chat": {"api_key": "k", "model_name": "m", "api_url": "http://x/v1"},
        )

        async def fake_gen(cfg, msg, timeout=15.0):
            raise RuntimeError("LLM down")

        monkeypatch.setattr("backend.service.session_title.generate_title_with_llm", fake_gen)

        async def main():
            assert await auto_title_task("s1", 1, "hi") is None  # 静默失败

        asyncio.run(main())