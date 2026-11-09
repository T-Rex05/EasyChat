"""Execute the real adapter handler without importing its service bootstrapping."""
import ast
import asyncio
import contextvars
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.context.tool_results.runtime import bind_runtime, current_runtime

if not Path("backend/hermes_adapter.py").exists():
    pytest.skip("legacy backend/hermes_adapter.py removed", allow_module_level=True)


def handler_factory():
    source = Path("backend/hermes_adapter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_make_project_tool_handler")
    calls = []
    namespace = {
        "asyncio": asyncio, "json": json, "logger": logging.getLogger("test"),
        "_THREAD_ID_CTX": contextvars.ContextVar("test_thread", default="t"),
        "should_truncate": lambda *args: True,
        "truncate_tool_output": lambda content, name: calls.append(name) or "legacy cropped",
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<adapter-handler>", "exec"), namespace)
    return namespace["_make_project_tool_handler"], calls


def test_project_handler_preserves_original_until_managed_boundary(tmp_path):
    make_handler, calls = handler_factory()
    tool = SimpleNamespace(name="query", invoke=lambda *args, **kwargs: "large original " * 3000)
    handler = make_handler(tool)
    agent = SimpleNamespace(session_id="s")
    with bind_runtime(agent, user_id="u", thread_id="t", root=tmp_path, enabled=True):
        with current_runtime(agent).tool_context("query", "c1", 3000):
            output = handler({})
    assert output == "large original " * 3000
    assert calls == []


def test_project_handler_retains_disabled_legacy_guard():
    make_handler, calls = handler_factory()
    result = make_handler(SimpleNamespace(name="query", invoke=lambda *a, **k: "original"))({})
    assert result == "legacy cropped"
    assert calls == ["query"]
