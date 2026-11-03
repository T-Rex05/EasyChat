"""access 模块公开接口：认证、Principal、授权与用户/角色管理。

Web 与渠道共用同一实现；外部请求参数不能指定任意 owner（架构 §4/§6）。
缓存为进程内有界缓存，任何授权变更整体失效（revision 递增），不依赖 Redis。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import OrderedDict
from typing import Any

from backend.modules.access import policy
from backend.modules.access.contracts import (
    ALL_PERMISSION_KEYS,
    VALID_TOOLSETS,
    PermissionOverride,
    RoleInfo,
    UserSnapshot,
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

# 弱密钥拒绝（沿用旧 auth_service 规则）
_INSECURE_JWT_SECRETS = frozenset(
    {"", "secret", "your-secret-key", "your-secret-key-here", "jwt-secret", "jwt_secret", "changeme", "change-me"}
)
_MIN_SECRET_LEN = 32


def _validate_secret(secret: str, *, allow_weak: bool) -> str:
    low = secret.strip().lower()
    if low in _INSECURE_JWT_SECRETS:
        if allow_weak:
            return secret
        raise InvalidInputError("JWT_SECRET 不安全，拒绝启动；请设置 32 位以上随机密钥")
    if len(secret) < _MIN_SECRET_LEN and not allow_weak:
        raise InvalidInputError(f"JWT_SECRET 过短（{len(secret)} < {_MIN_SECRET_LEN}），拒绝启动")
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
        self._perm_cache: OrderedDict[int, tuple[int, frozenset[str]]] = OrderedDict()
        self._toolsets_cache: OrderedDict[int, tuple[int, tuple[str, ...]]] = OrderedDict()
        self._user_cache: OrderedDict[int, tuple[int, UserSnapshot]] = OrderedDict()

    # ---- 种子 ------------------------------------------------------------------

    def seed(self) -> None:
        """同步权限定义与内置角色。默认授权仅在角色零授权时播种，不覆盖自定义。"""
        self.repo.upsert_permission_defs()
        self.repo.seed_builtin_roles()
        self.invalidate_all()

    # ---- 缓存与版本 --------------------------------------------------------------

    @property
    def permission_revision(self) -> int:
        return self._revision

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

    def set_user_role(self, actor: Principal, user_id: int, role: str) -> None:
        self.require_permission(actor, "system.manage")
        if self.repo.get_role_id_by_name(role) is None:
            raise InvalidInputError(f"角色不存在: {role}")
        self.repo.set_user_role(user_id, role)
        self.invalidate_all()

    def set_user_status(self, actor: Principal, user_id: int, status: int) -> None:
        self.require_permission(actor, "system.manage")
        if status not in (0, 1):
            raise InvalidInputError("status 只能为 0 或 1")
        self.repo.set_user_status(user_id, status)
        self.invalidate_all()

    def set_user_permission(self, actor: Principal, user_id: int, permission: str, granted: bool) -> None:
        self.require_permission(actor, "system.manage")
        if permission not in ALL_PERMISSION_KEYS:
            raise InvalidInputError(f"未注册的权限: {permission}")
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

    # ---- 管理：角色 ------------------------------------------------------------------

    def list_roles(self, actor: Principal) -> list[RoleInfo]:
        self.require_permission(actor, "system.manage")
        return self.repo.list_roles()

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
        if permissions:
            unknown = set(permissions) - set(ALL_PERMISSION_KEYS)
            if unknown:
                raise InvalidInputError(f"未注册的权限: {sorted(unknown)}")
        if toolsets:
            unknown_tools = set(toolsets) - set(VALID_TOOLSETS)
            if unknown_tools:
                raise InvalidInputError(f"未注册的工具集: {sorted(unknown_tools)}")
        role_id = self.repo.create_role(name, display_name, description, permissions, toolsets)
        self.invalidate_all()
        return role_id

    def update_role(self, actor: Principal, role_id: int, **kwargs: Any) -> None:
        self.require_permission(actor, "system.manage")
        perms = kwargs.get("permissions")
        if perms is not None:
            unknown = set(perms) - set(ALL_PERMISSION_KEYS)
            if unknown:
                raise InvalidInputError(f"未注册的权限: {sorted(unknown)}")
        self.repo.update_role(role_id, **kwargs)
        self.invalidate_all()

    def delete_role(self, actor: Principal, role_id: int) -> None:
        self.require_permission(actor, "system.manage")
        self.repo.delete_role(role_id)
        self.invalidate_all()

    def list_permissions(self, actor: Principal) -> list[dict[str, Any]]:
        self.require_permission(actor, "system.manage")
        return self.repo.list_permission_defs()

    def list_toolsets(self, actor: Principal) -> list[dict[str, Any]]:
        self.require_permission(actor, "system.manage")
        return self.repo.list_toolset_defs()


def principal_role(principal: Principal) -> str:
    return principal.role
