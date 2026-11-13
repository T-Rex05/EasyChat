"""MCP StreamableHTTP 连接探测与目录发现（P4）。

只做 initialize → tools/list 有界探测，不进入全局工具注册表（注册由
integrations.mcp.McpAdapter 走 Hermes）。认证/超时/连接/空目录分类复用
integrations.mcp 的既有口径；follow_redirects=False（重定向按失败呈现，
避免目标被改写后凭据外流）。
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from backend.integrations.mcp import (
    ERROR_AUTH,
    ERROR_CONNECTION,
    ERROR_EMPTY,
    ERROR_TIMEOUT,
    McpServerConfig,
    classify_error,
)
from backend.modules.mcp.contracts import McpCheckResult

PROTOCOL_VERSION = "2024-11-05"
MAX_TOOLS = 200


def _parse_message(response: httpx.Response) -> dict[str, Any]:
    """响应体可为 application/json 或 SSE（event: message / data: {...}）。"""
    body = response.text
    if "text/event-stream" in (response.headers.get("content-type") or ""):
        for line in body.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    return json.loads(payload)
        raise ValueError("SSE 响应中没有 message 数据")
    return json.loads(body)


def probe_server(config: McpServerConfig, *, transport: httpx.BaseTransport | None = None) -> McpCheckResult:
    """有界探测；任何网络/协议异常分类返回，不抛出。"""
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if config.credential_value:
        headers["Authorization"] = f"Bearer {config.credential_value}"
    timeout = httpx.Timeout(
        float(config.connect_timeout_s), connect=float(config.connect_timeout_s)
    )
    base = {
        "jsonrpc": "2.0",
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "easychat-mcp-probe", "version": "1"},
    }
    try:
        with httpx.Client(
            transport=transport, timeout=timeout, follow_redirects=False
        ) as client:
            init = client.post(
                config.url,
                headers=headers,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": base},
            )
            if init.status_code in (301, 302, 303, 307, 308):
                return McpCheckResult(
                    ok=False, error_kind=ERROR_CONNECTION,
                    error_message="服务端返回重定向，已按边界策略拒绝跟随",
                )
            if init.status_code >= 400:
                kind = classify_error(f"HTTP {init.status_code}")
                return McpCheckResult(
                    ok=False, error_kind=kind,
                    error_message=f"initialize 失败: HTTP {init.status_code}",
                )
            session = {"mcp-session-id": init.headers.get("mcp-session-id", "")} \
                if init.headers.get("mcp-session-id") else {}
            init_body = _parse_message(init)
            if "error" in init_body:
                msg = str(init_body["error"].get("message", init_body["error"]))
                return McpCheckResult(
                    ok=False, error_kind=classify_error(msg), error_message=msg[:200]
                )

            notify_headers = {**headers, **session}
            client.post(
                config.url, headers=notify_headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            listed = client.post(
                config.url, headers=notify_headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            if listed.status_code >= 400:
                kind = classify_error(f"HTTP {listed.status_code}")
                return McpCheckResult(
                    ok=False, error_kind=kind,
                    error_message=f"tools/list 失败: HTTP {listed.status_code}",
                )
            body = _parse_message(listed)
            if "error" in body:
                msg = str(body["error"].get("message", body["error"]))
                return McpCheckResult(
                    ok=False, error_kind=classify_error(msg), error_message=msg[:200]
                )
            tools = [
                str(item.get("name") or "")
                for item in (body.get("result") or {}).get("tools", [])
                if item.get("name")
            ]
            truncated = len(tools) > MAX_TOOLS
            names = tuple(tools[:MAX_TOOLS])
            if not names:
                return McpCheckResult(
                    ok=False, error_kind=ERROR_EMPTY,
                    error_message="目录为空（连接成功但服务端未暴露工具）",
                )
            return McpCheckResult(ok=True, tools=names, truncated=truncated)
    except httpx.TimeoutException:
        return McpCheckResult(
            ok=False, error_kind=ERROR_TIMEOUT,
            error_message=f"连接/读取超时（{config.connect_timeout_s}s）",
        )
    except (httpx.HTTPError, ValueError, OSError) as exc:
        return McpCheckResult(
            ok=False, error_kind=classify_error(str(exc)),
            error_message=str(exc)[:200],
        )
