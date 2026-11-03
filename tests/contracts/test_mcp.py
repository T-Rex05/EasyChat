"""MCP 适配契约测试：配置归一化、错误分类、目录刷新保留、健康隔离（全部用假registrar）。"""
from __future__ import annotations

import pytest

from backend.integrations.mcp import (
    ERROR_AUTH,
    ERROR_CONNECTION,
    ERROR_EMPTY,
    ERROR_TIMEOUT,
    McpAdapter,
    McpServerConfig,
)


def _cfg(name="weknora", url="http://127.0.0.1:8000/mcp", credential="tok"):
    return McpServerConfig(name=name, url=url, credential_value=credential,
                           allowed_tools=("kb_*",), call_timeout_s=30, result_limit=1000)


def test_config_normalized_to_hermes_entry():
    entry = _cfg().to_server_dict()
    assert entry["url"] == "http://127.0.0.1:8000/mcp"
    assert entry["timeout"] == 30
    assert entry["connect_timeout"] == 60
    assert entry["headers"]["Authorization"] == "Bearer tok"
    assert entry["tools"]["include"] == ["kb_*"]


def test_register_ok_lists_tools():
    def registrar(payload):
        return {"weknora": {"ok": True, "tools": ["kb_search", "kb_fetch"]}}
    adapter = McpAdapter(registrar=registrar)
    state = adapter.register([_cfg()])
    assert state.servers["weknora"].registered is True
    assert state.servers["weknora"].tools == ("kb_search", "kb_fetch")
    assert adapter.health()["weknora"]["registered"] is True


def test_empty_catalog_is_explicit_error_kind():
    def registrar(payload):
        return {"weknora": {"ok": True, "tools": []}}
    adapter = McpAdapter(registrar=registrar)
    state = adapter.register([_cfg()])
    status = state.servers["weknora"]
    assert status.registered is False
    assert status.error_kind == ERROR_EMPTY


@pytest.mark.parametrize(
    "message,expected",
    [
        ("HTTP 401 unauthorized from server", ERROR_AUTH),
        ("request timed out after 30s", ERROR_TIMEOUT),
        ("connection refused", ERROR_CONNECTION),
        ("", ERROR_CONNECTION),
    ],
)
def test_error_classification(message, expected):
    from backend.integrations.mcp import classify_error

    assert classify_error(message) == expected


def test_failed_registration_does_not_raise_and_records_kind():
    def registrar(payload):
        return {"weknora": {"ok": False, "error": "HTTP 401 unauthorized"}}
    adapter = McpAdapter(registrar=registrar)
    state = adapter.register([_cfg()])
    status = state.servers["weknora"]
    assert status.registered is False
    assert status.error_kind == ERROR_AUTH


def test_registrar_exception_marks_all_failed():
    def boom(payload):
        raise RuntimeError("connection refused to mcp host")

    adapter = McpAdapter(registrar=boom)
    state = adapter.register([_cfg(), _cfg(name="other")])
    assert all(not s.registered for s in state.servers.values())
    assert all(s.error_kind == ERROR_CONNECTION for s in state.servers.values())


def test_refresh_keeps_previous_full_catalog_on_failure():
    """刷新失败保留上一次完整目录，不上线半份 schema。"""
    def good(payload):
        return {"weknora": {"ok": True, "tools": ["kb_search", "kb_fetch", "kb_list"]}}
    adapter = McpAdapter(registrar=good)
    adapter.register([_cfg()])
    # 切换到失败的 registrar（模拟服务端断线）
    def broken(payload):
        return {"weknora": {"ok": False, "error": "connection refused"}}

    adapter._registrar = broken
    state = adapter.refresh([_cfg()])
    assert state.servers["weknora"].registered is True
    assert state.servers["weknora"].tools == ("kb_search", "kb_fetch", "kb_list")  # 保留旧目录


def test_health_is_isolated_capability_signal():
    """WeKnora 故障只反映在能力健康里，不抛异常影响调用方（R04）。"""
    def no_result(payload):
        return {}

    adapter = McpAdapter(registrar=no_result)
    state = adapter.register([_cfg()])  # registrar无结果 → 全部失败但不抛
    assert state.servers["weknora"].registered is False
    assert adapter.health()["weknora"]["error"] == ERROR_CONNECTION
    # 无任何注册时 healthy() 为 False——能力不可用，但不影响核心聊天
    empty = McpAdapter(registrar=no_result)
    assert empty.health() == {}
