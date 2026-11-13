"""P4 探测闭环：成功(JSON/SSE)、401、超时、空目录、重定向、目录变更保留。"""
from __future__ import annotations

import json

import httpx
import pytest

from backend.integrations.mcp import (
    ERROR_AUTH,
    ERROR_CONNECTION,
    ERROR_EMPTY,
    ERROR_TIMEOUT,
    McpAdapter,
    McpServerConfig,
)
from backend.integrations.mcp_probe import probe_server

CFG = McpServerConfig(name="s1", url="https://mcp.test/rpc", credential_value="tok")


def _handler(responses):
    """按请求顺序回放 (status, headers, body)。"""
    queue = list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        if not queue:
            raise AssertionError("超出预置响应数")
        status, headers, payload = queue[0]
        if len(queue) > 1:
            queue.pop(0)
        return httpx.Response(status, headers=headers, content=payload)

    return handle


def _json_response(payload):
    return httpx.Response(200, headers={"content-type": "application/json"},
                          content=json.dumps(payload).encode())


def test_probe_success_json_and_sse() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "initialize":
            return _json_response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}})
        if body["method"] == "notifications/initialized":
            return _json_response({"jsonrpc": "2.0", "result": {}})
        # tools/list → SSE 帧
        sse = 'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"search"},{"name":"ask"}]}}\n\n'
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())

    result = probe_server(CFG, transport=httpx.MockTransport(handle))
    assert result.ok and result.tools == ("search", "ask")


def test_probe_auth_401_classified() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"{}")

    result = probe_server(CFG, transport=httpx.MockTransport(handle))
    assert not result.ok and result.error_kind == ERROR_AUTH


def test_probe_timeout_classified() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    result = probe_server(CFG, transport=httpx.MockTransport(handle))
    assert result.error_kind == ERROR_TIMEOUT


def test_probe_empty_catalog() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return _json_response({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}})
        return _json_response({"jsonrpc": "2.0", "id": 1, "result": {}})

    result = probe_server(CFG, transport=httpx.MockTransport(handle))
    assert result.error_kind == ERROR_EMPTY


def test_probe_redirect_rejected() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.test/steal"})

    result = probe_server(CFG, transport=httpx.MockTransport(handle))
    assert result.error_kind == ERROR_CONNECTION
    assert "重定向" in result.error_message


def test_probe_truncates_large_catalog() -> None:
    many = [{"name": f"t{i}"} for i in range(500)]

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return _json_response({"jsonrpc": "2.0", "id": 2, "result": {"tools": many}})
        return _json_response({"jsonrpc": "2.0", "id": 1, "result": {}})

    result = probe_server(CFG, transport=httpx.MockTransport(handle))
    assert len(result.tools) == 200 and result.truncated


def test_adapter_refresh_keeps_previous_catalog_on_failure() -> None:
    """目录刷新失败：保留上一次完整目录（半份 schema 不上线）。"""
    calls = {"n": 0}

    def registrar(payload):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"s1": {"ok": True, "tools": ["a", "b"]}}
        return {"s1": {"ok": False, "error": "HTTP 500"}}

    adapter = McpAdapter(registrar=registrar)
    adapter.refresh([CFG])
    assert adapter.state.servers["s1"].registered and adapter.state.servers["s1"].tools == ("a", "b")
    adapter.refresh([CFG])
    assert adapter.state.servers["s1"].registered, "刷新失败必须保留上次目录"
    assert adapter.state.servers["s1"].tools == ("a", "b")


def test_probe_never_leaks_credential_in_result() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"unauthorized token tok")

    result = probe_server(CFG, transport=httpx.MockTransport(handle))
    assert "tok" not in result.error_message  # 上游响应不回显我们的凭据
