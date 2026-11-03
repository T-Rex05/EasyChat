"""WeKnora 等远程 MCP 的窄配置/结果适配（架构 §6、R04）。

复用 Hermes 远程 MCP 实现（tools/mcp_tool.register_mcp_servers），本模块只做：
- 配置归一化（地址/凭证引用/允许工具/超时/结果上限）；
- 结果与错误分类（空结果/认证失败/超时/连接失败明确区分）；
- 能力健康状态（本机有界）；WeKnora 故障是能力故障，不影响核心聊天健康检查。

测试通过注入 registrar 替身进行，不安装 WeKnora 服务；真实 MCP 属 integration。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT_S = 60
DEFAULT_CALL_TIMEOUT_S = 300
DEFAULT_RESULT_LIMIT = 200_000  # 单工具结果字符上限

ERROR_EMPTY = "empty_result"
ERROR_AUTH = "auth_failed"
ERROR_TIMEOUT = "timeout"
ERROR_CONNECTION = "connection_failed"


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    name: str
    url: str
    credential_ref: str = ""       # 受保护凭证的引用名（不存明文）
    credential_value: str = ""     # 运行时解出的明文（仅内存；由调用方注入）
    allowed_tools: tuple[str, ...] = ()   # glob 列表；空=全部
    excluded_tools: tuple[str, ...] = ()
    connect_timeout_s: int = DEFAULT_CONNECT_TIMEOUT_S
    call_timeout_s: int = DEFAULT_CALL_TIMEOUT_S
    result_limit: int = DEFAULT_RESULT_LIMIT

    def to_server_dict(self) -> dict[str, Any]:
        """Hermes mcp_servers 条目格式（StreamableHTTP）。"""
        entry: dict[str, Any] = {
            "url": self.url,
            "timeout": self.call_timeout_s,
            "connect_timeout": self.connect_timeout_s,
        }
        if self.credential_value:
            entry["headers"] = {"Authorization": f"Bearer {self.credential_value}"}
        if self.allowed_tools:
            entry["tools"] = {"include": list(self.allowed_tools)}
        if self.excluded_tools:
            entry.setdefault("tools", {})["exclude"] = list(self.excluded_tools)
        return entry


@dataclass(slots=True)
class McpServerStatus:
    name: str
    registered: bool
    tools: tuple[str, ...] = ()
    error_kind: str | None = None
    error_message: str = ""


@dataclass(slots=True)
class McpRegistryState:
    servers: dict[str, McpServerStatus] = field(default_factory=dict)

    def healthy(self, name: str | None = None) -> bool:
        if name is not None:
            status = self.servers.get(name)
            return bool(status and status.registered)
        return any(s.registered for s in self.servers.values()) if self.servers else False


def classify_error(message: str) -> str:
    """按消息分类 MCP 失败：认证失败/超时/连接失败；其余为连接类。"""
    low = str(message).lower()
    if "401" in low or "403" in low or "unauthorized" in low or "auth" in low and "failed" in low:
        return ERROR_AUTH
    if "timeout" in low or "timed out" in low:
        return ERROR_TIMEOUT
    return ERROR_CONNECTION


class McpAdapter:
    """远程 MCP 能力的窄适配；注册与调用仍由 Hermes 工具 registry 承担。"""

    def __init__(self, registrar: Callable[[dict[str, dict]], dict[str, Any]] | None = None) -> None:
        """registrar: {server名: 配置} → {server名: 注册结果}。

        None → 启动期解析 Hermes register_mcp_servers；测试注入替身。
        """
        self._registrar = registrar
        self.state = McpRegistryState()

    def _resolve_registrar(self) -> Callable[[dict[str, dict]], dict[str, Any]]:
        if self._registrar is not None:
            return self._registrar
        from backend.runtime.hermes.paths import ensure_hermes_environment
        from backend.config.paths import get_hermes_dir
        from pathlib import Path

        ensure_hermes_environment(Path(get_hermes_dir()))
        from tools.mcp_tool import register_mcp_servers  # noqa: PLC0415  (Hermes 顶层模块)

        return register_mcp_servers

    def register(self, configs: list[McpServerConfig]) -> McpRegistryState:
        """批量注册；单个失败记入状态，不抛出、不影响其它 server 与核心服务。"""
        if not configs:
            return self.state
        payload = {c.name: c.to_server_dict() for c in configs}
        try:
            results = self._resolve_registrar()(payload) or {}
        except Exception as exc:  # noqa: BLE001  全局失败：全部标记
            logger.warning("MCP 批量注册失败: %s", exc)
            results = {}
        for config in configs:
            result = results.get(config.name)
            if isinstance(result, dict) and result.get("ok", False):
                tools = tuple(str(t) for t in (result.get("tools") or []))
                limited = tools[:200]
                self.state.servers[config.name] = McpServerStatus(
                    name=config.name, registered=bool(limited), tools=limited,
                    error_kind=ERROR_EMPTY if not limited else None,
                    error_message="目录为空" if not limited else "",
                )
            else:
                message = str(result.get("error") if isinstance(result, dict) else result or "无返回")
                self.state.servers[config.name] = McpServerStatus(
                    name=config.name, registered=False,
                    error_kind=classify_error(message), error_message=message[:200],
                )
        return self.state

    def refresh(self, configs: list[McpServerConfig]) -> McpRegistryState:
        """完整目录刷新：失败保留上一次完整目录（半份 schema 不上线）。"""
        previous = dict(self.state.servers)  # 快照，避免与 register 的原地更新别名
        self.register(configs)
        for name, status in self.state.servers.items():
            if not status.registered and name in previous and previous[name].registered:
                self.state.servers[name] = previous[name]
        return self.state

    def health(self) -> dict[str, Any]:
        """能力健康检查；与核心服务健康无关（R04）。"""
        return {
            name: {"registered": s.registered, "tools": len(s.tools),
                   "error": s.error_kind}
            for name, s in self.state.servers.items()
        }
