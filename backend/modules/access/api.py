"""access 模块公开接口：认证、Principal、授权与用户/角色管理。

Web 与渠道共用同一实现；外部请求参数不能指定任意 owner（架构 §4/§6）。
缓存为进程内有界缓存，任何授权变更整体失效（revision 递增），不依赖 Redis。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import OrderedDict
from typing import Any

from backend.modules.access import policy
from backend.modules.access.contracts import (
    permission_catalog,
    ALL_PERMISSION_KEYS,
    VALID_TOOLSETS,
    PermissionOverride,
    RoleInfo,
    UserSnapshot,
    DEFAULT_ROLE_PERMISSIONS,
    DEFAULT_ROLE_TOOLSETS,
    DEPRECATED_PERMISSION_KEYS,
    DEFAULT_TEMPLATE_VERSION,
    MODULE_KEYS,
    MODULE_LABELS,
    SUPER_ADMIN_ROLE,
)
from backend.modules.access.repository import (
    AccessRepository,
    hash_password,
    needs_rehash,
    verify_password,
)
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import ConflictError, ForbiddenError, InvalidInputError, UnauthenticatedError

# 弱密钥拒绝（沿用旧 auth_service 规则）；必须包含仓库模板曾发布过的全部占位值，
# 使"照抄快速上手"在启动期失败而不是带着公开密钥上线。
_INSECURE_JWT_SECRETS = frozenset(
    {
        "",
        "secret",
        "your-secret-key",
        "your-secret-key-here",
        "jwt-secret",
        "jwt_secret",
        "changeme",
        "change-me",
        "please-change-to-a-random-64-char-secret",
    }
)
# 占位值的模式特征：未来模板默认值换文案也能被拦住（不依赖精确枚举）。
_INSECURE_SECRET_PATTERNS = ("please-change", "change-me", "changeme")
_MIN_SECRET_LEN = 32


def _validate_secret(secret: str, *, allow_weak: bool) -> str:
    low = secret.strip().lower()
    if low in _INSECURE_JWT_SECRETS or any(p in low for p in _INSECURE_SECRET_PATTERNS):
        if allow_weak:
            return secret
        raise InvalidInputError("JWT_SECRET 不安全，拒绝启动；请设置 32 位以上随机密钥")
    if len(secret) < _MIN_SECRET_LEN and not allow_weak:
        raise InvalidInputError(f"JWT_SECRET 过短（{len(secret)} < {_MIN_SECRET_LEN}），拒绝启动")
    return secret


def validate_deployment_secret(secret: str, *, kind: str = "JWT_SECRET") -> str:
    """部署密钥启动校验（JWT 与 EASYCHAT_ENCRYPTION_SECRET 共用同一套下限）。

    加密密钥保护的凭据信封（模型 key/SMTP 密码/渠道 token）比 JWT 更敏感，
    不得只做真值判断；低熵或占位值一律拒绝启动。
    """
    low = secret.strip().lower()
    if low in _INSECURE_JWT_SECRETS or any(p in low for p in _INSECURE_SECRET_PATTERNS):
        raise InvalidInputError(f"{kind} 不安全，拒绝启动；请设置 32 位以上随机密钥")
    if len(secret) < _MIN_SECRET_LEN:
        raise InvalidInputError(f"{kind} 过短（{len(secret)} < {_MIN_SECRET_LEN}），拒绝启动")
    return secret


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


class AccessService:
    """认证与授权的唯一公开入口（跨渠道共用）。"""

    def __init__(
        self,
        db: Database,
        *,
        jwt_secret: str,
        allow_weak_secret: bool = False,
        token_expiry_hours: int = 720,
        renew_threshold_seconds: int = 604_800,
        refresh_grace_seconds: int = 604_800,
        cache_maxsize: int = 1024,
        sse_ticket_ttl_seconds: int = 60,
        clock: Any = None,
    ) -> None:
        self.repo = AccessRepository(db)
        self.jwt_secret = _validate_secret(jwt_secret, allow_weak=allow_weak_secret)
        self.token_expiry_hours = token_expiry_hours
        self.renew_threshold_seconds = renew_threshold_seconds
        self.refresh_grace_seconds = refresh_grace_seconds
        self.clock = clock or time.time
        self._revision = 0
        self._cache_maxsize = cache_maxsize
        self._sse_ticket_ttl = sse_ticket_ttl_seconds
        self._sse_ticket_max = 512
        self._sse_tickets: dict[str, tuple[int, float]] = {}
        self._perm_cache: OrderedDict[int, tuple[int, frozenset[str]]] = OrderedDict()
        self._toolsets_cache: OrderedDict[int, tuple[int, tuple[str, ...]]] = OrderedDict()
        self._user_cache: OrderedDict[int, tuple[int, UserSnapshot]] = OrderedDict()

    # ---- SSE 一次性 ticket（审计 #3：长效 JWT 不得进 URL/访问日志） --------------

    def issue_sse_ticket(self, user_id: int) -> str:
        """签发秒级一次性 ticket：EventSource 无法带 Header，URL 上只允许出现
        短时效凭据；ticket 单次消费、进程内有界，泄露后的重放价值可忽略。"""
        ticket = secrets.token_urlsafe(32)
        now = self.clock()
        expired = [key for key, (_, exp) in self._sse_tickets.items() if exp <= now]
        for key in expired:
            self._sse_tickets.pop(key, None)
        while len(self._sse_tickets) >= self._sse_ticket_max:
            self._sse_tickets.pop(next(iter(self._sse_tickets)))
        self._sse_tickets[ticket] = (int(user_id), now + self._sse_ticket_ttl)
        return ticket

    def consume_sse_ticket(self, ticket: str) -> Principal:
        entry = self._sse_tickets.pop(ticket, None)  # 单次消费
        if entry is None or self.clock() > entry[1]:
            raise UnauthenticatedError("ticket 无效或已过期")
        return self.snapshot_principal(entry[0])

    # ---- 种子 ------------------------------------------------------------------

    def seed(self) -> None:
        """同步权限定义与内置角色（按模板版本记录；显式清空/legacy 角色不再补种）。"""
        self.repo.upsert_permission_defs()
        self.repo.seed_builtin_roles()
        self.invalidate_all()

    # ---- 缓存与版本 --------------------------------------------------------------

    @property
    def permission_revision(self) -> int:
        return self._revision

    @property
    def sse_ticket_ttl(self) -> int:
        return self._sse_ticket_ttl

    def invalidate_all(self) -> None:
        """任何角色/授权/用户状态变更后整体失效（有界缓存，revision 递增）。"""
        self._revision += 1
        self._perm_cache.clear()
        self._toolsets_cache.clear()
        self._user_cache.clear()

    def _cached(self, cache: OrderedDict, key: Any) -> Any:
        entry = cache.get(key)
        if entry is None or entry[0] != self._revision:
            return None
        cache.move_to_end(key)
        return entry[1]

    def _store(self, cache: OrderedDict, key: Any, value: Any) -> None:
        cache[key] = (self._revision, value)
        cache.move_to_end(key)
        while len(cache) > self._cache_maxsize:
            cache.popitem(last=False)

    # ---- Token（格式沿用旧 auth_service，旧 Token 保持可验证） -------------------

    def create_token(self, user_id: int, username: str, role: str) -> str:
        iat = int(self.clock())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"uid": user_id, "name": username, "role": role, "iat": iat, "exp": iat + self.token_expiry_hours * 3600}
        h = _b64url(json.dumps(header).encode())
        p = _b64url(json.dumps(payload).encode())
        sig = _b64url(hmac.new(self.jwt_secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
        return f"{h}.{p}.{sig}"

    def _decode_token(self, token: str) -> dict[str, Any] | None:
        try:
            h, p, sig = token.split(".")
            expected = _b64url(hmac.new(self.jwt_secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, expected):
                return None
            payload = json.loads(_b64url_decode(p))
            if payload.get("exp", 0) < self.clock():
                return None
            return payload
        except (ValueError, KeyError, json.JSONDecodeError, TypeError):
            return None

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """签名+有效期校验，返回 {user_id, username, role} 或 None（兼容旧返回结构）。"""
        payload = self._decode_token(token)
        if payload is None:
            return None
        return {"user_id": payload["uid"], "username": payload["name"], "role": payload["role"]}

    def _decode_expired(self, token: str) -> dict[str, Any] | None:
        """验签但放过过期（供宽限期刷新使用）。"""
        try:
            h, p, sig = token.split(".")
            expected = _b64url(hmac.new(self.jwt_secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, expected):
                return None
            return json.loads(_b64url_decode(p))
        except (ValueError, KeyError, json.JSONDecodeError, TypeError):
            return None

    def renew_token(self, token: str) -> str | None:
        """宽限期刷新：已过期但在 refresh_grace 内 → 新 token；否则 None。"""
        payload = self._decode_expired(token)
        if payload is None:
            return None
        expired_for = self.clock() - payload.get("exp", 0)
        if not (0 < expired_for <= self.refresh_grace_seconds):
            return None
        return self.create_token(payload["uid"], payload["name"], payload["role"])

    def check_token_renewal(self, token: str) -> str | None:
        """滑动窗口续期：未过期但剩余 < renew_threshold → 新 token；否则 None。"""
        payload = self._decode_token(token)
        if payload is None:
            return None
        remaining = payload["exp"] - self.clock()
        if 0 < remaining < self.renew_threshold_seconds:
            return self.create_token(payload["uid"], payload["name"], payload["role"])
        return None

    # ---- 注册 / 登录 ---------------------------------------------------------------

    def register(self, username: str, password: str, email: str = "") -> dict[str, Any]:
        if len(username) < 2:
            raise InvalidInputError("用户名至少 2 个字符")
        if len(password) < 6:
            raise InvalidInputError("密码至少 6 个字符")
        if self.repo.get_user_by_username(username) is not None:
            raise ConflictError(f"用户名 '{username}' 已存在")
        user_id = self.repo.create_user(username, hash_password(password), email)
        token = self.create_token(user_id, username, "user")
        return {"user_id": user_id, "username": username, "token": token}

    def login(self, username: str, password: str) -> dict[str, Any]:
        row = self.repo.get_user_auth_row(username)
        if row is None:
            raise UnauthenticatedError("用户名或密码错误")
        if row["status"] != 1:
            raise UnauthenticatedError("账号已被禁用")
        if not verify_password(password, str(row["password"])):
            raise UnauthenticatedError("用户名或密码错误")
        if needs_rehash(str(row["password"])):
            self.repo.update_password(int(row["id"]), hash_password(password))
        self.repo.touch_last_login(int(row["id"]))
        token = self.create_token(int(row["id"]), str(row["username"]), str(row["role"]))
        return {"user_id": int(row["id"]), "username": str(row["username"]), "role": str(row["role"]), "token": token}

    # ---- Principal ---------------------------------------------------------------

    def snapshot_principal(self, user_id: int) -> Principal:
        """从数据库构造可信 Principal（角色/状态以 DB 为准）。"""
        user = self._user(user_id)
        if user.status != 1:
            raise ForbiddenError("账号已被禁用")
        return Principal(user_id=user.user_id, role=user.role, permission_revision=self._revision)

    def authenticate_token(self, token: str) -> Principal:
        """验证 Token 并对 DB 重查用户状态与角色（禁用立即生效；token 角色不信任）。"""
        payload = self._decode_token(token)
        if payload is None:
            raise UnauthenticatedError("Token 无效或已过期，请重新登录")
        return self.snapshot_principal(int(payload["uid"]))

    def validate_principal(self, principal: Principal) -> Principal:
        """排队执行/重要工具调用/后台重试前的重校验：状态与授权版本必须仍然有效。"""
        user = self._user(principal.user_id)
        if user.status != 1:
            raise ForbiddenError("账号已被禁用")
        if user.role != principal.role or self._revision != principal.permission_revision:
            return Principal(user_id=user.user_id, role=user.role, permission_revision=self._revision)
        return principal

    # ---- 权限 ------------------------------------------------------------------

    def _user(self, user_id: int) -> UserSnapshot:
        cached = self._cached(self._user_cache, user_id)
        if cached is not None:
            return cached
        user = self.repo.get_user(user_id)
        if user is None:
            raise UnauthenticatedError(f"用户不存在: {user_id}")
        self._store(self._user_cache, user_id, user)
        return user

    def effective_permissions(self, user_id: int) -> frozenset[str]:
        cached = self._cached(self._perm_cache, user_id)
        if cached is not None:
            return cached
        user = self._user(user_id)
        grants, revokes = self.repo.get_user_overrides(user_id)
        perms = policy.effective_permissions(
            role_name=user.role,
            role_permissions=self._role_permissions(user.role),
            grants=frozenset(grants),
            revokes=frozenset(revokes),
            all_registered_permissions=ALL_PERMISSION_KEYS,
        )
        # 防御：DEPRECATED 键过滤已在 policy 内完成；这里保留断言语义（避免未来重构回归）
        self._store(self._perm_cache, user_id, perms)
        return perms

    def _role_permissions(self, role_name: str) -> frozenset[str]:
        perms = self.repo.role_permissions_map()
        return perms.get(role_name, frozenset())

    def has_permission(self, principal: Principal, permission: str) -> bool:
        """权限校验以 DB 实时角色为准（principal 只携带 user_id/角色快照）。"""
        return permission in self.effective_permissions(principal.user_id)

    def require_permission(self, principal: Principal, permission: str) -> None:
        if not self.has_permission(principal, permission):
            raise ForbiddenError(f"缺少权限: {permission}")

    def hermes_toolsets(self, user_id: int) -> tuple[str, ...]:
        """角色 toolsets（来源角色配置；缺失/损坏不授予任何工具）。"""
        cached = self._cached(self._toolsets_cache, user_id)
        if cached is not None:
            return cached
        user = self._user(user_id)
        role = self.repo.get_role_by_name(user.role)
        raw = list(role.toolsets) if role is not None else []
        tools = policy.effective_toolsets(raw)
        self._store(self._toolsets_cache, user_id, tools)
        return tools

    # ---- 资源归属 ------------------------------------------------------------------

    def can_access_resource(self, principal: Principal, item_owner_id: int, manage_perm: str) -> bool:
        user = self._user(principal.user_id)
        return policy.can_manage_resource(
            item_owner_id=item_owner_id,
            principal_user_id=principal.user_id,
            role_name=user.role,
            effective_permissions=self.effective_permissions(principal.user_id),
            manage_perm=manage_perm,
        )

    def authorize_resource(self, principal: Principal, item_owner_id: int, manage_perm: str) -> None:
        if not self.can_access_resource(principal, item_owner_id, manage_perm):
            raise ForbiddenError("无权访问该资源")

    # ---- 管理：用户 ------------------------------------------------------------------

    def _is_super_admin(self, user_id: int) -> bool:
        return self._user(user_id).role == SUPER_ADMIN_ROLE

    def _require_owner_management(
        self, actor: Principal, target_user_id: int, *, granting_owner: bool = False
    ) -> None:
        """拥有者边界：admin 可管理普通用户；涉及拥有者身份（目标/结果）时必须 super_admin。

        - 目标是 super_admin（改角色/禁用/写覆盖）→ 仅 super_admin；
        - 把普通用户提升为 super_admin → 仅 super_admin（granting_owner）；
        - admin 对普通用户的常规管理不受影响（修复 P0-1 回归）。
        """
        if self._is_super_admin(actor.user_id):
            return
        if self._is_super_admin(target_user_id):
            raise ForbiddenError("拥有者身份只能由超级管理员管理")
        if granting_owner:
            raise ForbiddenError("分配拥有者角色需要超级管理员确认")

    def capabilities(self, principal: Principal) -> dict[str, Any]:
        """当前用户的功能能力（9 模块 + 工具 + 拥有者标志；前端菜单/路由/按钮唯一消费点）。

        聚合规则：模块 enabled = 任一归属权限在有效权限中；read/use/manage
        按目录 op 聚合（use/exec 含 read；manage 含 use）。工具 = 角色 toolsets。
        """
        perms = self.effective_permissions(principal.user_id)
        catalog = permission_catalog()
        modules: dict[str, dict[str, Any]] = {
            key: {"label": MODULE_LABELS.get(key, key), "enabled": False,
                  "read": False, "use": False, "manage": False}
            for key in MODULE_KEYS
        }
        for key in perms:
            entry = catalog.get(key)
            if entry is None:
                continue
            module = modules.get(entry["module"])
            if module is None:
                continue  # internal 模块（files）不进功能模块视图
            module["enabled"] = True
            op = entry["op"]
            if op == "read":
                module["read"] = True
            elif op in ("use", "execute"):
                module["use"] = True
                module["read"] = True
            elif op == "manage":
                module["manage"] = True
                module["use"] = True
                module["read"] = True
        # Partial legacy grants must describe the actual memory read check.
        modules["memory"]["read"] = "memory.view" in perms
        return {
            "modules": modules,
            "tools": list(self.hermes_toolsets(principal.user_id)),
            "super_admin": self._is_super_admin(principal.user_id),
            "permissions": sorted(perms),
        }

    def set_user_role(self, actor: Principal, user_id: int, role: str) -> None:
        self.require_permission(actor, "system.manage")
        if self.repo.get_role_id_by_name(role) is None:
            raise InvalidInputError(f"角色不存在: {role}")
        self._require_owner_management(actor, user_id, granting_owner=(role == SUPER_ADMIN_ROLE))
        self.repo.set_user_role(user_id, role)
        self.invalidate_all()

    def set_user_status(self, actor: Principal, user_id: int, status: int) -> None:
        self.require_permission(actor, "system.manage")
        if status not in (0, 1):
            raise InvalidInputError("status 只能为 0 或 1")
        self._require_owner_management(actor, user_id)
        self.repo.set_user_status(user_id, status)
        self.invalidate_all()

    def set_user_permission(self, actor: Principal, user_id: int, permission: str, granted: bool) -> None:
        self.require_permission(actor, "system.manage")
        if permission not in ALL_PERMISSION_KEYS:
            raise InvalidInputError(f"未注册的权限: {permission}")
        if permission in DEPRECATED_PERMISSION_KEYS:
            raise InvalidInputError("已退役权限不可授予（与角色 CRUD 口径一致；存量行仅作审计）")
        # 覆盖写会影响 super_admin 的有效授权语义（虽然 policy 当前短路忽略），
        # 与角色/状态同边界：涉及拥有者目标时必须 super_admin。
        self._require_owner_management(actor, user_id)
        self.repo.set_user_permission(user_id, permission, granted)
        self.invalidate_all()

    def get_user_perm_overrides(self, actor: Principal, user_id: int) -> list[PermissionOverride]:
        self.require_permission(actor, "system.manage")
        return self.repo.get_user_overrides_full(user_id)

    def list_users(self, actor: Principal) -> list[dict[str, Any]]:
        self.require_permission(actor, "system.manage")
        return self.repo.list_users()

    def get_user_detail(self, actor: Principal, user_id: int) -> UserSnapshot:
        """本人可查自己；他人需要 system.manage。"""
        if actor.user_id != user_id:
            self.require_permission(actor, "system.manage")
        return self._user(user_id)

    def get_user_effective_detail(self, actor: Principal, user_id: int) -> dict[str, Any]:
        """用户有效权限明细（来源可解释：角色授权 + 单独授予/撤销；撤销优先）。

        本人可查自己；他人需要 system.manage。deprecated 键标注 lifecycle。
        """
        if actor.user_id != user_id:
            self.require_permission(actor, "system.manage")
        user = self._user(user_id)
        role_perms = self._role_permissions(user.role)
        grants, revokes = self.repo.get_user_overrides(user_id)
        effective = self.effective_permissions(user_id)
        items = []
        for key in sorted(ALL_PERMISSION_KEYS | set(role_perms) | set(grants) | set(revokes)):
            entry = {
                "permission": key,
                "from_role": key in role_perms,
                "override": ("grant" if key in grants else "revoke" if key in revokes else ""),
                "effective": key in effective,
            }
            items.append(entry)
        return {
            "user_id": user_id,
            "role": user.role,
            "super_admin": user.role == SUPER_ADMIN_ROLE,
            "permissions": items,
            "effective_permissions": sorted(effective),
        }

    # ---- 管理：角色 ------------------------------------------------------------------

    def list_roles(self, actor: Principal) -> list[RoleInfo]:
        self.require_permission(actor, "system.manage")
        return self.repo.list_roles()

    def _validate_role_payload(
        self, *, permissions: list[str] | None, toolsets: list[str] | None
    ) -> None:
        """创建与更新共用的权限/工具组合法性校验（含生命周期）。"""
        if permissions is not None:
            unknown = set(permissions) - set(ALL_PERMISSION_KEYS)
            if unknown:
                raise InvalidInputError(f"未注册的权限: {sorted(unknown)}")
            deprecated = set(permissions) & DEPRECATED_PERMISSION_KEYS
            if deprecated:
                raise InvalidInputError(f"已退役权限不可授予: {sorted(deprecated)}")
        if toolsets is not None:
            unknown_tools = set(toolsets) - set(VALID_TOOLSETS)
            if unknown_tools:
                raise InvalidInputError(f"未注册的工具集: {sorted(unknown_tools)}")

    def create_role(
        self,
        actor: Principal,
        *,
        name: str,
        display_name: str,
        description: str = "",
        permissions: list[str] | None = None,
        toolsets: list[str] | None = None,
    ) -> int:
        self.require_permission(actor, "system.manage")
        self._validate_role_payload(permissions=permissions, toolsets=toolsets)
        role_id = self.repo.create_role(name, display_name, description, permissions, toolsets)
        self.invalidate_all()
        return role_id

    def update_role(self, actor: Principal, role_id: int, **kwargs: Any) -> None:
        self.require_permission(actor, "system.manage")
        # 创建与更新路径执行同等校验（方案 §5.3：此前更新只查 permissions）
        self._validate_role_payload(
            permissions=kwargs.get("permissions"), toolsets=kwargs.get("toolsets"),
        )
        row = self.repo.get_role_by_id(role_id)
        if row is not None and row.is_system and row.name == SUPER_ADMIN_ROLE and (
            kwargs.get("permissions") is not None or kwargs.get("toolsets") is not None
        ):
            raise InvalidInputError("super_admin 拥有全部权限，不可修改其角色配置")
        self.repo.update_role(role_id, **kwargs)
        self.invalidate_all()

    def delete_role(self, actor: Principal, role_id: int) -> None:
        self.require_permission(actor, "system.manage")
        self.repo.delete_role(role_id)
        self.invalidate_all()

    def list_permissions(self, actor: Principal) -> list[dict[str, Any]]:
        self.require_permission(actor, "system.manage")
        # 附带统一目录元数据（module/op/depends/risk/scope/internal），前端 9 功能项按此渲染
        catalog = permission_catalog()
        return [{**item, **catalog.get(item["key"], {})} for item in self.repo.list_permission_defs()]

    def list_toolsets(self, actor: Principal) -> list[dict[str, Any]]:
        self.require_permission(actor, "system.manage")
        return self.repo.list_toolset_defs()

    def _effective_template_diff(self, role_name: str) -> dict[str, Any]:
        """模板 vs 数据库当前授权的差异（只读；不做任何修改）。"""
        template = DEFAULT_ROLE_PERMISSIONS.get(role_name, ())
        template = tuple(k for k in template if k not in DEPRECATED_PERMISSION_KEYS)
        current = set(self.repo.snapshot_role_permissions(role_name))
        template_set = set(template)
        state = self.repo.get_role_seed_state(role_name) or {}
        version = str(state.get("template_version") or "unseeded")
        return {
            "role": role_name,
            "template_version": version,
            "pending": version != DEFAULT_TEMPLATE_VERSION,
            "missing_from_role": sorted(template_set - current),
            "not_in_template": sorted(current - template_set),
            "toolsets_in_db": self.repo.role_toolsets_by_name(role_name),
            "toolsets_in_template": list(DEFAULT_ROLE_TOOLSETS.get(role_name, ())),
        }

    def permission_upgrade_preview(self, actor: Principal) -> dict[str, Any]:
        """全部内置角色的模板差异预览（P3：先呈现，不修改授权）。"""
        self.require_permission(actor, "system.manage")
        catalog = permission_catalog()
        roles = []
        for role_name in DEFAULT_ROLE_PERMISSIONS:
            diff = self._effective_template_diff(role_name)
            high_risk_missing = [
                k for k in diff["missing_from_role"]
                if catalog.get(k, {}).get("risk") in ("high", "medium")
            ]
            roles.append({**diff, "high_risk_missing": high_risk_missing})
        return {"current_template_version": DEFAULT_TEMPLATE_VERSION, "roles": roles}

    def apply_role_template(self, actor: Principal, role_name: str) -> dict[str, Any]:
        """显式应用当前模板到内置角色（新增授权必须由拥有者确认，方案 §1/§3）。

        - 仅 super_admin 可执行（system.manage 不够——这是授权升级动作）；
        - 应用前留存授权快照（role_seed_state.snapshot_json），支持审计与回滚；
        - deprecated 键不写入。
        """
        if not self._is_super_admin(actor.user_id):
            raise ForbiddenError("应用权限模板需要超级管理员确认")
        if role_name not in DEFAULT_ROLE_PERMISSIONS:
            raise InvalidInputError(f"非内置角色: {role_name}")
        # 合并语义（与升级面板「模板外自定义授权保留」承诺一致）：
        # 新权限 = 模板 ∪ 现有；工具组 = 模板 ∪ 现有。
        template = [
            k for k in DEFAULT_ROLE_PERMISSIONS[role_name]
            if k not in DEPRECATED_PERMISSION_KEYS
        ]
        snapshot, merged = self.repo.apply_role_template_atomic(
            role_name,
            permissions=template,
            toolsets=list(DEFAULT_ROLE_TOOLSETS.get(role_name, ())),
            version=DEFAULT_TEMPLATE_VERSION,
        )
        self.invalidate_all()
        return {
            "role": role_name,
            "applied_version": DEFAULT_TEMPLATE_VERSION,
            "previous_permissions": snapshot,
            "merged_permissions": sorted(merged),
        }


def principal_role(principal: Principal) -> str:
    return principal.role
