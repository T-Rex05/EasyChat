"""MCP 配置模块公共契约。

视图对象绝不含凭据明文——只出 credential_set 布尔；日志同规则。
"""
from __future__ import annotations

from dataclasses import dataclass, field

AUDIENCE_CONFIG_ADMIN = "config_admin"
AUDIENCE_ALL = "all"
VALID_AUDIENCES = frozenset({AUDIENCE_CONFIG_ADMIN, AUDIENCE_ALL})

CHECK_OK = "ok"
CHECK_EMPTY = "empty"
CHECK_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class McpServerView:
    id: str
    name: str
    url: str
    credential_set: bool
    allowed_tools: tuple[str, ...]
    excluded_tools: tuple[str, ...]
    connect_timeout_s: int
    call_timeout_s: int
    audience: str
    enabled: bool
    last_check_state: str
    last_check_error: str
    last_check_tools: tuple[str, ...] = ()
    last_checked_at: str = ""


@dataclass(frozen=True, slots=True)
class McpCheckResult:
    ok: bool
    tools: tuple[str, ...] = field(default=())
    error_kind: str = ""
    error_message: str = ""
    truncated: bool = False
