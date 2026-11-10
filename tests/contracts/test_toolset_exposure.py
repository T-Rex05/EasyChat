"""P9 实测缺陷回归：项目业务工具必须可经 toolset 暴露进模型 schema。

背景：`__always_available__` 曾被误认为内核自动包含组（tools.py 旧注释），
实际内核按 enabled_toolsets 严格白名单解析——未声明的 toolset 永不可见，
导致对话 run 里模型从未拿到 superagent_submit_task 等工具（自然语言受理假阴性）。
修复三件套：contracts 常量、register_safe_project_tools 经 create_custom_toolset
声明组、dispatcher 对话请求显式启用该组。本文件锁死前两件的行为。
"""
from __future__ import annotations

import pytest

from backend.runtime.contracts import ALWAYS_AVAILABLE_TOOLSET


@pytest.fixture(scope="module")
def tool_definitions(tmp_path_factory):
    """真实内核装配：注册基础+业务工具，返回 get_tool_definitions 查询函数。"""
    from pathlib import Path

    from backend.config.paths import get_hermes_dir
    from backend.runtime.hermes.paths import ensure_hermes_environment

    ensure_hermes_environment(Path(get_hermes_dir()))

    from backend.runtime.hermes.tools import register_safe_project_tools

    class _Stub:
        def create_task(self, *a, **k):  # pragma: no cover - 仅装配不出调用
            raise AssertionError("handler must not run")

    from backend.tools.business.superagent_tools import build_superagent_tools

    extra = build_superagent_tools(superagent=_Stub())
    count = register_safe_project_tools(lambda: None, extra_tools=extra)
    assert count >= 6  # 基础 5 + submit（业务面在 bootstrap 更多）

    from model_tools import get_tool_definitions  # Hermes 顶层模块（adapter 层测试豁免架构约束）

    def definitions(enabled: list[str]) -> set[str]:
        return {d["function"]["name"] for d in get_tool_definitions(enabled_toolsets=enabled, quiet_mode=True)}

    return definitions


def test_always_group_resolves_project_tools(tool_definitions):
    names = tool_definitions([ALWAYS_AVAILABLE_TOOLSET])
    assert "get_current_time" in names
    assert "superagent_submit_task" in names


def test_groups_without_always_do_not_leak_project_tools(tool_definitions):
    """fail-closed 语义保持：不启用 always 组时项目工具不在 schema。"""
    names = tool_definitions(["terminal", "file"])
    assert "superagent_submit_task" not in names
    assert "get_current_time" not in names


def test_dispatcher_chat_request_enables_always_group():
    """对话请求装配层锁死：allowed_tools 含 always 组（Web 与微信共用该构造）。"""
    import inspect

    from backend.modules.assistant.dispatcher import RunDispatcher

    src = inspect.getsource(RunDispatcher._build_request)
    assert "ALWAYS_AVAILABLE_TOOLSET" in src, "对话 run 必须显式启用项目工具组"


def test_project_tools_survive_tool_search_disclosure(tool_definitions):
    """P9 修复第二层：项目工具注入内核 core 白名单，不被渐进披露折叠
    （tool_search tier 会把非 core 工具收进桥接元工具，弱模型不会主动发现）。"""
    names = tool_definitions([ALWAYS_AVAILABLE_TOOLSET])
    assert "superagent_submit_task" in names, "submit 必须直接可见，不能只可搜索"
    assert "get_current_time" in names
