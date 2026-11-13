"""MCP 配置服务（P4）：持久化、加密凭据、连接探测、启用注册与运行授权。

- 凭据只以 enc:v1: 密文落库；视图/日志只出 credential_set 布尔。
- 能力默认关闭：新建 enabled=False；注册只发生在显式启用/更新时。
- 网络外呼（probe/register）全部在事务之外；表操作短事务。
- 运行授权模型：每个 server 注册为 Hermes 工具组 `mcp-<name>`；
  dispatcher 按 audience 逐 run 注入——config_admin 仅授权持有者，
  all 面向所有登录用户（由系统配置者显式选择）。Agent 缓存键含
  allowed_tools 与 permission_revision，跨 owner 不复用。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from backend.integrations.mcp import McpServerConfig
from backend.modules.mcp.contracts import (
    AUDIENCE_ALL,
    AUDIENCE_CONFIG_ADMIN,
    CHECK_EMPTY,
    CHECK_FAILED,
    CHECK_OK,
    VALID_AUDIENCES,
    McpServerView,
)
from backend.modules.mcp.repository import McpRepository
from backend.platform.sqlite import Database
from backend.shared.crypto import decrypt_secret, encrypt_secret
from backend.shared.errors import ConflictError, InvalidInputError, NotFoundError

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
_TIMEOUT_RANGE = (1, 600)


def _validate_name(name: str) -> str:
    value = str(name or "").strip().lower()
    if not _NAME_RE.match(value):
        raise InvalidInputError(
            "MCP 服务名需为 2-41 位小写字母/数字/下划线/连字符（用作工具组标识）"
        )
    return value


def _validate_url(url: str) -> str:
    from urllib.parse import urlparse

    value = str(url or "").strip()
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise InvalidInputError("MCP 地址无法解析") from exc
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidInputError("MCP 地址必须是完整的 http(s) URL")
    if parsed.username or parsed.password:
        raise InvalidInputError("URL 不允许内嵌凭据，请使用凭据字段")
    return value


def _validate_timeout(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(_TIMEOUT_RANGE[0], min(_TIMEOUT_RANGE[1], number))


class McpService:
    def __init__(
        self,
        db: Database,
        *,
        access: Any,
        encryption_secret: str,
        adapter: Any = None,
        probe: Callable[[McpServerConfig], Any] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.repo = McpRepository(db)
        self.access = access
        self._secret = encryption_secret
        self.adapter = adapter
        self._probe = probe
        self._clock = clock

    # ---- 内部 --------------------------------------------------------------------

    def _guard(self, actor):
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "system.config")
        if not self._secret:
            raise ConflictError("未配置 EASYCHAT_ENCRYPTION_SECRET，凭据能力关闭")
        return principal

    def _now(self) -> str:
        from backend.platform.sqlite import utc_now_iso

        return utc_now_iso()

    def _probe_impl(self) -> Callable[[McpServerConfig], Any]:
        if self._probe is not None:
            return self._probe

        def _default(config: McpServerConfig):
            import httpx

            from backend.integrations.mcp_probe import probe_server

            return probe_server(config)

        return _default

    def _view(self, row: dict[str, Any]) -> McpServerView:
        return McpServerView(
            id=str(row["id"]),
            name=str(row["name"]),
            url=str(row["url"]),
            credential_set=bool(row["credential_enc"]),
            allowed_tools=tuple(json.loads(row["allowed_tools"] or "[]")),
            excluded_tools=tuple(json.loads(row["excluded_tools"] or "[]")),
            connect_timeout_s=int(row["connect_timeout_s"]),
            call_timeout_s=int(row["call_timeout_s"]),
            audience=str(row["audience"]),
            enabled=bool(row["enabled"]),
            last_check_state=str(row["last_check_state"]),
            last_check_error=str(row["last_check_error"]),
            last_check_tools=tuple(json.loads(row["last_check_tools"] or "[]")),
            last_checked_at=str(row["last_checked_at"]),
        )

    def _config(self, row: dict[str, Any], *, decrypt: bool) -> McpServerConfig:
        credential = ""
        if decrypt and row["credential_enc"]:
            credential = decrypt_secret(str(row["credential_enc"]), self._secret)
        return McpServerConfig(
            name=str(row["name"]),
            url=str(row["url"]),
            credential_value=credential,
            allowed_tools=tuple(json.loads(row["allowed_tools"] or "[]")),
            excluded_tools=tuple(json.loads(row["excluded_tools"] or "[]")),
            connect_timeout_s=int(row["connect_timeout_s"]),
            call_timeout_s=int(row["call_timeout_s"]),
        )

    # ---- CRUD ---------------------------------------------------------------------

    def list(self, actor) -> list[McpServerView]:
        principal = self._guard(actor)
        return [self._view(row) for row in self.repo.list()] \
            if principal is not None else []

    def create(
        self, actor, *, name: str, url: str, credential: str = "",
        allowed_tools: list[str] | None = None, excluded_tools: list[str] | None = None,
        connect_timeout_s: Any = 60, call_timeout_s: Any = 300,
        audience: str = AUDIENCE_CONFIG_ADMIN, enabled: bool = False,
    ) -> McpServerView:
        self._guard(actor)
        clean_name = _validate_name(name)
        if self.repo.get_by_name(clean_name) is not None:
            raise ConflictError(f"MCP 服务名已存在: {clean_name}")
        if audience not in VALID_AUDIENCES:
            raise InvalidInputError("未知的 audience")
        server_id = self.repo.create(
            name=clean_name,
            url=_validate_url(url),
            credential_enc=(
                encrypt_secret(credential.strip(), self._secret) if credential.strip() else ""
            ),
            allowed_tools=list(allowed_tools or []),
            excluded_tools=list(excluded_tools or []),
            connect_timeout_s=_validate_timeout(connect_timeout_s, 60),
            call_timeout_s=_validate_timeout(call_timeout_s, 300),
            audience=audience,
            enabled=False,  # 能力默认关闭；启用是显式动作
        )
        if enabled:
            self.set_enabled(actor, server_id, True)
        return self._view(self.repo.get(server_id))

    def update(
        self, actor, server_id: str, **fields: Any,
    ) -> McpServerView:
        self._guard(actor)
        row = self.repo.get(server_id)
        if row is None:
            raise NotFoundError("MCP 服务不存在")
        sets: dict[str, Any] = {}
        if "name" in fields:
            clean = _validate_name(fields["name"])
            clash = self.repo.get_by_name(clean)
            if clash is not None and clash["id"] != server_id:
                raise ConflictError(f"MCP 服务名已存在: {clean}")
            sets["name"] = clean
        if "url" in fields:
            sets["url"] = _validate_url(fields["url"])
        if "audience" in fields:
            if fields["audience"] not in VALID_AUDIENCES:
                raise InvalidInputError("未知的 audience")
            sets["audience"] = fields["audience"]
        for key, default in (
            ("connect_timeout_s", 60), ("call_timeout_s", 300),
        ):
            if key in fields:
                sets[key] = _validate_timeout(fields[key], default)
        for key in ("allowed_tools", "excluded_tools"):
            if key in fields:
                sets[key] = json.dumps(
                    [str(x) for x in (fields[key] or [])][:200], ensure_ascii=False,
                )
        credential = str(fields.get("credential") or "").strip()
        if credential:
            sets["credential_enc"] = encrypt_secret(credential, self._secret)
        elif fields.get("clear_credential") is True:
            sets["credential_enc"] = ""
        # 凭据缺省：保留既有密文（更新不隐式清空）
        self.repo.update(server_id, **sets)
        updated = self.repo.get(server_id)
        if updated["enabled"]:
            self._sync_registration(updated)
        return self._view(updated)

    def delete(self, actor, server_id: str) -> None:
        self._guard(actor)
        row = self.repo.get(server_id)
        if row is None:
            raise NotFoundError("MCP 服务不存在")
        self.repo.delete(server_id)
        # Hermes 注册表无运行时注销接口：已注册工具组保留连接，
        # 但 enabled=0 + 不再注入任何 run（生效面即时收敛），资源回收依赖重启。
        if row["enabled"]:
            logger.info("MCP %s 已删除；如曾注册，工具组 mcp-%s 将在重启后消失",
                        row["name"], row["name"])

    def set_enabled(self, actor, server_id: str, enabled: bool) -> McpServerView:
        self._guard(actor)
        row = self.repo.get(server_id)
        if row is None:
            raise NotFoundError("MCP 服务不存在")
        self.repo.update(server_id, enabled=1 if enabled else 0)
        updated = self.repo.get(server_id)
        if enabled:
            self._sync_registration(updated)
        return self._view(updated)

    # ---- 探测与注册 ---------------------------------------------------------------

    def test(self, actor, server_id: str, *, credential: str | None = None) -> dict[str, Any]:
        """连接测试与目录发现：独立超时、不进入全局注册表、结果落检查态。

        credential 仅当次内存内用于探测（不落库）；缺省用已存凭据。
        """
        self._guard(actor)
        row = self.repo.get(server_id)
        if row is None:
            raise NotFoundError("MCP 服务不存在")
        config = self._config(row, decrypt=True)
        if credential and credential.strip():
            config = McpServerConfig(
                name=config.name, url=config.url,
                credential_value=credential.strip(),
                allowed_tools=config.allowed_tools,
                excluded_tools=config.excluded_tools,
                connect_timeout_s=config.connect_timeout_s,
                call_timeout_s=config.call_timeout_s,
            )
        result = self._probe_impl()(config)
        state = (
            CHECK_OK if result.ok
            else CHECK_EMPTY if result.error_kind == "empty_result"
            else CHECK_FAILED
        )
        self.repo.set_check_result(
            server_id, state=state, error=result.error_message or "",
            tools=list(result.tools), checked_at=self._now(),
        )
        return {
            "ok": bool(result.ok),
            "state": state,
            "tools": list(result.tools),
            "truncated": bool(getattr(result, "truncated", False)),
            "error_kind": result.error_kind or "",
            "error_message": (result.error_message or "")[:200],
        }

    def _sync_registration(self, row: dict[str, Any]) -> None:
        if self.adapter is None:
            return
        try:
            self.adapter.register([self._config(row, decrypt=True)])
        except Exception:  # noqa: BLE001  注册失败不影响配置持久化
            logger.exception("MCP %s 注册失败（配置已保存）", row["name"])

    def register_enabled(self) -> Any:
        """启动装配：注册所有 enabled 配置；失败只记状态不抛出。"""
        if self.adapter is None:
            return None
        rows = [row for row in self.repo.list() if row["enabled"]]
        if not rows:
            return self.adapter.state
        try:
            return self.adapter.register(
                [self._config(row, decrypt=True) for row in rows]
            )
        except Exception:  # noqa: BLE001  MCP 故障不影响核心聊天（R04）
            logger.exception("MCP 启动注册失败")
            return self.adapter.state

    # ---- 运行授权 ------------------------------------------------------------------

    def granted_toolsets(self, principal) -> tuple[str, ...]:
        """dispatcher 逐 run 注入的 MCP 工具组名（mcp-<name>）。"""
        can_config = False
        try:
            can_config = self.access.has_permission(principal, "system.config")
        except Exception:  # noqa: BLE001  判定失败按最小授权
            can_config = False
        out: list[str] = []
        for row in self.repo.list():
            if not row["enabled"]:
                continue
            if row["audience"] == AUDIENCE_ALL or can_config:
                out.append(f"mcp-{row['name']}")
        return tuple(out)

    def server_view_public(self, server_id: str) -> McpServerView | None:
        row = self.repo.get(server_id)
        return self._view(row) if row else None
