"""access 模块 SQLite 数据访问。

只允许本模块写 users/roles/role_permissions/user_permissions/permission_defs；
其它模块通过公开 api 使用。所有 SQL 参数化，写入走短事务。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import ConflictError, NotFoundError
from backend.modules.access.contracts import (
    BUILTIN_ROLES,
    DEFAULT_ROLE_PERMISSIONS,
    DEFAULT_ROLE_TOOLSETS,
    PERMISSION_DEFS,
    TOOLSET_DEFS,
    PermissionOverride,
    RoleInfo,
    UserSnapshot,
    DEFAULT_TEMPLATE_VERSION,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_DEPRECATED,
)

# ---- scrypt 密码哈希（沿用旧 auth_service 格式，存量 SHA256+salt 登录时升级） ----

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _SCRYPT_DKLEN = 2**14, 8, 1, 64
_SCRYPT_PREFIX = "scrypt$"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.scrypt(password.encode(), salt=salt.encode(), n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN)
    return f"{_SCRYPT_PREFIX}{_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt}:{dk.hex()}"


def needs_rehash(hashed: str) -> bool:
    return not hashed.startswith(_SCRYPT_PREFIX)


def verify_password(password: str, hashed: str) -> bool:
    try:
        if hashed.startswith(_SCRYPT_PREFIX):
            params = hashed[len(_SCRYPT_PREFIX):]
            head, dk_hex = params.split(":", 1)
            n_s, r_s, p_s, salt = head.split("$")
            dk = hashlib.scrypt(password.encode(), salt=salt.encode(), n=int(n_s), r=int(r_s), p=int(p_s), dklen=_SCRYPT_DKLEN)
            return hmac.compare_digest(dk.hex(), dk_hex)
        # 旧格式：salt:sha256hex
        salt, expected = hashed.split(":", 1)
        actual = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def parse_toolsets(raw: str | None) -> list[str]:
    """hermes_tools JSON 解析；损坏/缺失返回空列表（fail-closed）。"""
    if not raw:
        return []
    try:
        tools = json.loads(raw)
        return [t for t in tools if isinstance(t, str)]
    except (json.JSONDecodeError, TypeError):
        return []


class AccessRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- users ----

    def create_user(self, username: str, password_hash: str, email: str = "", role: str = "user") -> int:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO users(username, password, email, role, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                (username, password_hash, email, role, now, now),
            )
            return int(cur.lastrowid)

    def get_user(self, user_id: int) -> UserSnapshot | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT id, username, email, role, status, avatar, created_at FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
            return self._snapshot(row) if row else None
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> UserSnapshot | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT id, username, email, role, status, avatar, created_at FROM users WHERE username=?",
                (username,),
            ).fetchone()
            return self._snapshot(row) if row else None
        finally:
            conn.close()

    def get_user_auth_row(self, username: str) -> dict[str, Any] | None:
        """登录用：含密码哈希与状态。"""
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT id, username, password, role, status FROM users WHERE username=?",
                (username,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_password(self, user_id: int, password_hash: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE users SET password=?, updated_at=? WHERE id=?", (password_hash, utc_now_iso(), user_id))

    def set_user_role(self, user_id: int, role: str) -> None:
        with self.db.transaction() as conn:
            cur = conn.execute("UPDATE users SET role=?, updated_at=? WHERE id=?", (role, utc_now_iso(), user_id))
            if cur.rowcount != 1:
                raise NotFoundError(f"用户不存在: {user_id}")

    def set_user_status(self, user_id: int, status: int) -> None:
        with self.db.transaction() as conn:
            cur = conn.execute("UPDATE users SET status=?, updated_at=? WHERE id=?", (status, utc_now_iso(), user_id))
            if cur.rowcount != 1:
                raise NotFoundError(f"用户不存在: {user_id}")

    def touch_last_login(self, user_id: int, ip: str = "") -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE users SET last_login_at=?, last_login_ip=?, updated_at=? WHERE id=?",
                (utc_now_iso(), ip, utc_now_iso(), user_id),
            )

    def list_users(self) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT id, username, email, role, status, avatar, created_at FROM users ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def users_with_role(self, role: str) -> list[int]:
        conn = self.db.connect()
        try:
            rows = conn.execute("SELECT id FROM users WHERE role=?", (role,)).fetchall()
            return [int(r["id"]) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _snapshot(row: Any) -> UserSnapshot:
        return UserSnapshot(
            user_id=int(row["id"]),
            username=str(row["username"]),
            email=str(row["email"] or ""),
            role=str(row["role"]),
            status=int(row["status"]),
            avatar=str(row["avatar"] or ""),
            created_at=str(row["created_at"]),
        )

    # ---- roles ----

    def get_role_id_by_name(self, name: str) -> int | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT id FROM roles WHERE name=?", (name,)).fetchone()
            return int(row["id"]) if row else None
        finally:
            conn.close()

    def get_role_by_name(self, name: str) -> RoleInfo | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT id FROM roles WHERE name=?", (name,)).fetchone()
            return self.get_role(int(row["id"])) if row else None
        finally:
            conn.close()

    def get_role_by_id(self, role_id: int) -> RoleInfo | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT id FROM roles WHERE id=?", (int(role_id),)).fetchone()
            return self.get_role(int(row["id"])) if row else None
        finally:
            conn.close()

    def get_role(self, role_id: int) -> RoleInfo:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"角色不存在: {role_id}")
            perms = [
                str(r["permission"])
                for r in conn.execute("SELECT permission FROM role_permissions WHERE role_id=?", (role_id,)).fetchall()
            ]
            return RoleInfo(
                role_id=int(row["id"]),
                name=str(row["name"]),
                display_name=str(row["display_name"] or ""),
                description=str(row["description"] or ""),
                is_system=bool(row["is_system"]),
                permissions=tuple(sorted(perms)),
                toolsets=tuple(parse_toolsets(row["hermes_tools"])),
            )
        finally:
            conn.close()

    def list_roles(self) -> list[RoleInfo]:
        conn = self.db.connect()
        try:
            rows = conn.execute("SELECT id FROM roles ORDER BY id").fetchall()
        finally:
            conn.close()
        return [self.get_role(int(r["id"])) for r in rows]

    def create_role(
        self,
        name: str,
        display_name: str,
        description: str = "",
        permissions: list[str] | None = None,
        toolsets: list[str] | None = None,
    ) -> int:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            existing = conn.execute("SELECT id FROM roles WHERE name=?", (name,)).fetchone()
            if existing:
                raise ConflictError(f"角色 '{name}' 已存在")
            cur = conn.execute(
                "INSERT INTO roles(name, display_name, description, is_system, hermes_tools, created_at, updated_at) "
                "VALUES(?,?,?,0,?,?,?)",
                (name, display_name, description, json.dumps(toolsets or [], ensure_ascii=False), now, now),
            )
            role_id = int(cur.lastrowid)
            for perm in permissions or []:
                conn.execute(
                    "INSERT OR IGNORE INTO role_permissions(role_id, permission, updated_at) VALUES(?,?,?)",
                    (role_id, perm, now),
                )
            return role_id

    def update_role(
        self,
        role_id: int,
        *,
        name: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        permissions: list[str] | None = None,
        toolsets: list[str] | None = None,
    ) -> None:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT name, is_system FROM roles WHERE id=?", (role_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"角色不存在: {role_id}")
            if row["is_system"] and name and name != row["name"]:
                raise ConflictError("系统内置角色不可重命名")
            updates, params = [], []
            if name:
                updates.append("name=?")
                params.append(name)
            if display_name is not None:
                updates.append("display_name=?")
                params.append(display_name)
            if description is not None:
                updates.append("description=?")
                params.append(description)
            if toolsets is not None:
                updates.append("hermes_tools=?")
                params.append(json.dumps(toolsets, ensure_ascii=False))
            if updates:
                updates.append("updated_at=?")
                params.append(now)
                params.append(role_id)
                conn.execute(f"UPDATE roles SET {', '.join(updates)} WHERE id=?", params)
            if permissions is not None:
                conn.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
                conn.executemany(
                    "INSERT OR IGNORE INTO role_permissions(role_id, permission, updated_at) VALUES(?,?,?)",
                    [(role_id, p, now) for p in permissions],
                )

    def delete_role(self, role_id: int) -> None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT name, is_system FROM roles WHERE id=?", (role_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"角色不存在: {role_id}")
            if row["is_system"]:
                raise ConflictError(f"系统内置角色不可删除: {row['name']}")
            # 该角色用户回退到 user（沿用旧行为）
            conn.execute("UPDATE users SET role='user', updated_at=? WHERE role=?", (utc_now_iso(), row["name"]))
            conn.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
            conn.execute("DELETE FROM roles WHERE id=?", (role_id,))

    def role_permission_count(self, name: str) -> int:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT count(*) AS c FROM role_permissions rp JOIN roles r ON r.id=rp.role_id WHERE r.name=?",
                (name,),
            ).fetchone()
            return int(row["c"])
        finally:
            conn.close()

    # ---- user permission overrides ----

    def get_user_overrides(self, user_id: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT permission, granted FROM user_permissions WHERE user_id=?", (user_id,)
            ).fetchall()
            grants = tuple(str(r["permission"]) for r in rows if r["granted"])
            revokes = tuple(str(r["permission"]) for r in rows if not r["granted"])
            return grants, revokes
        finally:
            conn.close()

    def get_user_overrides_full(self, user_id: int) -> list[PermissionOverride]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT permission, granted FROM user_permissions WHERE user_id=? ORDER BY permission",
                (user_id,),
            ).fetchall()
            return [PermissionOverride(permission=str(r["permission"]), granted=bool(r["granted"])) for r in rows]
        finally:
            conn.close()

    def set_user_permission(self, user_id: int, permission: str, granted: bool) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO user_permissions(user_id, permission, granted, updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id, permission) DO UPDATE SET granted=excluded.granted, updated_at=excluded.updated_at",
                (user_id, permission, 1 if granted else 0, utc_now_iso()),
            )

    def role_permissions_map(self) -> dict[str, frozenset[str]]:
        """角色名 → 权限集合（一次查询，供缓存填充）。"""
        conn = self.db.connect()
        try:
            out: dict[str, set[str]] = {}
            rows = conn.execute(
                "SELECT r.name AS role, rp.permission AS perm FROM roles r "
                "JOIN role_permissions rp ON rp.role_id = r.id"
            ).fetchall()
            for r in rows:
                out.setdefault(str(r["role"]), set()).add(str(r["perm"]))
            return {k: frozenset(v) for k, v in out.items()}
        finally:
            conn.close()

    def user_role_map(self) -> dict[int, str]:
        conn = self.db.connect()
        try:
            rows = conn.execute("SELECT id, role FROM users").fetchall()
            return {int(r["id"]): str(r["role"]) for r in rows}
        finally:
            conn.close()

    # ---- permission defs 与种子 ----

    def upsert_permission_defs(self) -> None:
        """同步权限定义与生命周期（只更新元数据，不触碰任何授权）。

        源码中不再注册的键不会被删除：存量行保留作审计（方案 §5.2）。
        """
        now = utc_now_iso()
        with self.db.transaction() as conn:
            for d in PERMISSION_DEFS:
                conn.execute(
                    "INSERT INTO permission_defs(key, label, description, group_name, group_label, sort_order, lifecycle, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET label=excluded.label, description=excluded.description, "
                    "group_name=excluded.group_name, group_label=excluded.group_label, "
                    "sort_order=excluded.sort_order, lifecycle=excluded.lifecycle",
                    (d["key"], d["label"], d["description"], d["group_name"], d["group_label"],
                     d["sort_order"], d["lifecycle"], now),
                )

    def list_permission_defs(self) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT key, label, description, group_name, group_label, sort_order, lifecycle "
                "FROM permission_defs ORDER BY group_name, sort_order"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def seed_builtin_roles(self) -> None:
        """播种内置角色与默认授权/工具集（按模板版本记录，方案 §5.2 修复）。

        - 角色在 role_seed_state 无记录 → 首次初始化：播种 v2 模板并登记版本；
        - 已有记录 → 一律跳过：管理员显式清空授权、存量 legacy 角色都不会被补种；
        - 存量库由迁移 0023 回填 template_version='legacy'，升级经拥有者
          显式 apply_role_template（先快照再应用）。
        super_admin 的全集在运行时计算，不落库。
        """
        now = utc_now_iso()
        with self.db.transaction() as conn:
            for r in BUILTIN_ROLES:
                conn.execute(
                    "INSERT OR IGNORE INTO roles(name, display_name, is_system, hermes_tools, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (
                        r["name"], r["display_name"], r["is_system"],
                        json.dumps(list(DEFAULT_ROLE_TOOLSETS.get(r["name"], ())), ensure_ascii=False),
                        now, now,
                    ),
                )
            for role_name, perms in DEFAULT_ROLE_PERMISSIONS.items():
                rid = conn.execute("SELECT id FROM roles WHERE name=?", (role_name,)).fetchone()
                if rid is None:
                    continue
                seeded = conn.execute(
                    "SELECT 1 FROM role_seed_state WHERE role_name=?", (role_name,)
                ).fetchone()
                if seeded is not None:
                    continue
                conn.executemany(
                    "INSERT OR IGNORE INTO role_permissions(role_id, permission, updated_at) VALUES(?,?,?)",
                    [(int(rid["id"]), p, now) for p in perms],
                )
                conn.execute(
                    "INSERT INTO role_seed_state(role_name, template_version, seeded_at, snapshot_json) "
                    "VALUES(?,?,?,?) ON CONFLICT(role_name) DO NOTHING",
                    (role_name, DEFAULT_TEMPLATE_VERSION, now, "[]"),
                )

    # ---- 模板版本与升级（P3 受控迁移） ------------------------------------------

    def get_role_seed_state(self, role_name: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT role_name, template_version, seeded_at, snapshot_json "
                "FROM role_seed_state WHERE role_name=?",
                (role_name,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _mark_role_seeded(self, role_name: str, version: str = "legacy") -> None:
        """测试/迁移辅助：登记初始化状态（不写授权）。"""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO role_seed_state(role_name, template_version, seeded_at, snapshot_json) "
                "VALUES(?,?,?,?) ON CONFLICT(role_name) DO NOTHING",
                (role_name, version, utc_now_iso(), "[]"),
            )

    def set_role_permissions_by_name(self, role_name: str, permissions: list[str]) -> None:
        """管理辅助（测试与模板应用共用）：整体替换角色授权。"""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM roles WHERE name=?", (role_name,)).fetchone()
            if row is None:
                raise NotFoundError(f"角色不存在: {role_name}")
            conn.execute("DELETE FROM role_permissions WHERE role_id=?", (int(row["id"]),))
            now = utc_now_iso()
            conn.executemany(
                "INSERT OR IGNORE INTO role_permissions(role_id, permission, updated_at) VALUES(?,?,?)",
                [(int(row["id"]), perm, now) for perm in permissions],
            )

    def snapshot_role_permissions(self, role_name: str) -> list[str]:
        """授权快照（升级前留存）。"""
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT rp.permission FROM role_permissions rp JOIN roles r ON r.id=rp.role_id "
                "WHERE r.name=? ORDER BY rp.permission",
                (role_name,),
            ).fetchall()
        finally:
            conn.close()
        return [str(r["permission"]) for r in rows]

    def record_template_upgrade(self, role_name: str, *, version: str, snapshot: list[str]) -> None:
        """登记模板升级；预览/拥有者确认等先决条件由调用方检查。"""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE role_seed_state SET template_version=?, seeded_at=?, snapshot_json=? "
                "WHERE role_name=?",
                (version, utc_now_iso(), json.dumps(snapshot, ensure_ascii=False), role_name),
            )
            if cur.rowcount != 1:
                raise NotFoundError(f"角色缺少初始化记录: {role_name}")

    def set_role_toolsets_by_name(self, role_name: str, toolsets: list[str]) -> None:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE roles SET hermes_tools=?, updated_at=? WHERE name=?",
                (json.dumps(toolsets, ensure_ascii=False), utc_now_iso(), role_name),
            )
            if cur.rowcount != 1:
                raise NotFoundError(f"角色不存在: {role_name}")

    def role_toolsets_by_name(self, role_name: str) -> list[str]:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT hermes_tools FROM roles WHERE name=?", (role_name,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise NotFoundError(f"角色不存在: {role_name}")
        try:
            data = json.loads(str(row["hermes_tools"] or "[]"))
        except ValueError:
            return []
        return [str(x) for x in data] if isinstance(data, list) else []

    def list_toolset_defs(self) -> list[dict[str, Any]]:
        return [dict(t) for t in TOOLSET_DEFS]
