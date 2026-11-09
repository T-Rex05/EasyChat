"""ToolContext 双通道与线程传播。"""
from __future__ import annotations

import asyncio
import contextvars
import threading

import pytest

from backend.shared.context import Principal
from backend.shared.tool_context import (
    ToolContext,
    bind,
    config_with,
    current,
    from_config,
    resolve,
)


def _ctx(user_id: int = 7) -> ToolContext:
    return ToolContext(
        principal=Principal(user_id=user_id, role="user", permission_revision=3),
        run_id="run-1",
        session_id="sess-1",
        source="wechat",
        channel_account_id="acct-1",
    )


def test_bind_and_reset_are_scoped() -> None:
    assert current() is None
    ctx = _ctx()
    with bind(ctx):
        assert current() == ctx
    assert current() is None


def test_config_channel_wins_over_contextvar() -> None:
    config_ctx = _ctx(11)
    var_ctx = _ctx(22)
    with bind(var_ctx):
        assert resolve(config_with(config_ctx)) == config_ctx
        assert resolve({}) == var_ctx
        assert resolve(None) == var_ctx


def test_from_config_rejects_non_tool_context_values() -> None:
    assert from_config(None) is None
    assert from_config({"configurable": {"tool_context": "not-a-context"}}) is None
    assert from_config({"configurable": {}}) is None
    assert from_config(object()) is None


def test_contextvar_survives_copy_context_to_worker_thread() -> None:
    ctx = _ctx(31)
    seen: list[ToolContext | None] = []

    def run() -> None:
        seen.append(current())

    with bind(ctx):
        worker = threading.Thread(target=contextvars.copy_context().run, args=(run,))
        worker.start()
        worker.join()

    assert seen == [ctx]


def test_tool_schema_preserves_non_string_parameter_types() -> None:
    from backend.runtime.hermes.tools import _json_type, _tool_schema
    from backend.tools.business.ledger_tools import ImportPreviewInput

    assert _json_type(int) == "integer"
    assert _json_type(bool) == "boolean"
    assert _json_type(dict[str, object]) == "object"
    assert _json_type(list[str]) == "array"
    schema = _tool_schema(type("Fake", (), {
        "args_schema": ImportPreviewInput,
        "description": "preview",
    })())
    assert schema["parameters"]["properties"]["mapping"]["type"] == "object"


def test_tool_config_uses_session_when_no_hermes_thread() -> None:
    from backend.runtime.hermes.tools import _make_handler

    seen: list[str] = []

    class FakeTool:
        name = "todo_add"

        def invoke(self, args, config=None):
            seen.append(str((config or {}).get("configurable", {}).get("thread_id")))
            return "ok"

    handler = _make_handler(FakeTool(), lambda: None)
    for session_id in ("sess-a", "sess-b"):
        handler({}, config=config_with(ToolContext(
            principal=_ctx(7).principal, run_id=f"run-{session_id}", session_id=session_id,
        )))
    assert seen == ["sess-a", "sess-b"]


def test_async_handler_captures_config_before_coroutine_moves_threads() -> None:
    """Hermes 可以只把协程移到新线程；config 必须在返回协程前捕获。"""
    from backend.runtime.hermes.tools import _make_handler

    seen: list[str] = []

    class FakeAsyncTool:
        async def func(self, args, config=None):
            ctx = from_config(config)
            seen.append(ctx.run_id if ctx is not None else "missing")
            return "ok"

        async def ainvoke(self, args, config=None):
            return await self.func(args, config=config)

    handler = _make_handler(FakeAsyncTool(), lambda: None)
    with bind(_ctx(52)):
        coro = handler({})
    thread = threading.Thread(target=lambda: asyncio.run(coro))
    thread.start()
    thread.join()
    assert seen == ["run-1"]


@pytest.mark.asyncio
async def test_async_handler_resolves_context_before_leaving_current_thread() -> None:
    """handler 返回协程前必须已解析 config；新线程里不能再依赖 contextvar。"""
    import uuid

    from backend.runtime.hermes.tools import _ensure_hermes_loaded, _make_handler

    _ensure_hermes_loaded()
    from tools.registry import registry

    name = f"test_async_ctx_{uuid.uuid4().hex[:8]}"
    seen: list[str] = []

    class FakeAsyncTool:
        def __init__(self) -> None:
            self.name = name
            self.description = "test"

        async def func(self, args, config=None):
            ctx = from_config(config)
            seen.append(ctx.run_id if ctx is not None else "missing")
            return "ok"

        async def ainvoke(self, args, config=None):
            return await self.func(args, config=config)

    tool = FakeAsyncTool()
    registry.register(
        name, toolset="agentforge_project", schema={"description": "test"},
        handler=_make_handler(tool, lambda: None), is_async=True, override=True,
    )
    try:
        with bind(_ctx(51)):
            result = registry.dispatch(name, {})
            # registry.dispatch 为 async handler 启新线程；await 也必须成功。
            assert result == "ok"
        assert seen == ["run-1"]
    finally:
        registry._tools.pop(name, None)


def test_new_thread_without_context_uses_config_fallback() -> None:
    ctx = _ctx(41)

    def run() -> None:
        assert current() is None
        assert resolve(config_with(ctx)) == ctx

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
