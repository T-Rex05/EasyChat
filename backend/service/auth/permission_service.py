"""
权限服务 — RBAC 权限检查（薄胶水层，核心逻辑在 backend/permission/）。

用法:
    from backend.service.auth.permission_service import has_permission, get_user_permissions
"""
import json
from typing import Optional, Set, List, Dict, Any

from backend.permission.checker import (
    get_user_permissions,
    has_permission,
    get_user_hermes_tools,
    check_ownership,
    get_user_role,
)
from backend.permission.registry import (
    get_all_permissions as _get_all_perms,
    get_permission_tree,
)
from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log

# ── Re-export checker functions ──
__all__ = [
    "get_user_role",
    "get_user_permissions",
    "has_permission",
    "get_user_hermes_tools",
    "check_ownership",
    "get_all_permissions",
    "get_permission_tree",
    # 角色管理
    "list_roles",
    "create_role",
    "update_role",
    "delete_role",
    # 用户管理
    "set_user_role",
    "set_user_permission",
    "get_user_perm_overrides",
]


def get_all_permissions() -> List[dict]:
    """列出所有可用权限定义（供前端展示）。"""
    return _get_all_perms()


# ── 角色管理（保持不变，因为直接操作 roles 表）──

def list_roles() -> List[Dict[str, Any]]:
    """列出所有角色（含权限信息 + hermes_tools）。"""
    conn = get_conn()
    try:
        roles = []
        for row in conn.execute("SELECT * FROM roles ORDER BY id").fetchall():
            r = dict(row)
            perms = conn.execute(
                "SELECT permission FROM role_permissions WHERE role_id = %s", (r["id"],)
            ).fetchall()
            r["permissions"] = [p["permission"] for p in perms]
            # hermes_tools 从 JSON 字符串解析
            try:
                r["hermes_tools"] = json.loads(r.get("hermes_tools", "[]") or "[]")
            except (json.JSONDecodeError, TypeError):
                r["hermes_tools"] = []
            roles.append(r)
        return roles
    finally:
        conn.close()


def create_role(name: str, display_name: str, description: str = "",
                permissions: List[str] = None,
                hermes_tools: List[str] = None) -> Dict[str, Any]:
    """创建自定义角色。"""
    from backend.permission.checker import _invalidate_permission_cache
    if not name or not name.strip():
        raise ValueError("角色标识不能为空")
    if not display_name:
        raise ValueError("显示名称不能为空")

    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM roles WHERE name = %s", (name,)).fetchone()
        if existing:
            raise ValueError(f"角色 '{name}' 已存在")

        tools_json = json.dumps(hermes_tools or [], ensure_ascii=False)

        cur = conn.execute(
            "INSERT INTO roles (name, display_name, description, is_system, hermes_tools) VALUES (%s, %s, %s, 0, %s)",
            (name, display_name, description, tools_json),
        )
        role_id = cur.lastrowid
        if permissions:
            for perm in permissions:
                conn.execute(
                    "INSERT IGNORE INTO role_permissions (role_id, permission) VALUES (%s, %s)",
                    (role_id, perm),
                )
        conn.commit()
        
        # 刷新权限缓存
        _invalidate_permission_cache()
        
        logger.info(f"创建角色: {display_name} ({name}) → {len(permissions or [])} 权限")
        return {"id": role_id, "name": name, "display_name": display_name}
    finally:
        conn.close()


def update_role(role_id: int, name: str = None, display_name: str = None,
                description: str = None, permissions: List[str] = None,
                hermes_tools: List[str] = None) -> None:
    """更新角色信息及权限。"""
    from backend.permission.checker import _invalidate_permission_cache
    conn = get_conn()
    try:
        row = conn.execute("SELECT is_system, name FROM roles WHERE id = %s", (role_id,)).fetchone()
        if not row:
            raise ValueError(f"角色不存在: {role_id}")
        if row["is_system"] and name and name != row["name"]:
            raise ValueError("系统内置角色不可重命名")

        updates = []
        params = []
        if name:
            updates.append("name = %s"); params.append(name)
        if display_name:
            updates.append("display_name = %s"); params.append(display_name)
        if description is not None:
            updates.append("description = %s"); params.append(description)
        if hermes_tools is not None:
            updates.append("hermes_tools = %s")
            params.append(json.dumps(hermes_tools, ensure_ascii=False))

        if updates:
            updates.append("updated_at = NOW()")
            params.append(role_id)
            conn.execute(f"UPDATE roles SET {', '.join(updates)} WHERE id = %s", params)

        if permissions is not None:
            conn.execute("DELETE FROM role_permissions WHERE role_id = %s", (role_id,))
            for perm in permissions:
                conn.execute(
                    "INSERT INTO role_permissions (role_id, permission) VALUES (%s, %s)",
                    (role_id, perm),
                )
        conn.commit()
        
        # 刷新权限缓存
        _invalidate_permission_cache()
        
        logger.info(f"更新角色: role_id={role_id}")
    finally:
        conn.close()


def delete_role(role_id: int) -> None:
    """删除自定义角色（内置角色不可删）。"""
    from backend.permission.checker import _invalidate_permission_cache
    conn = get_conn()
    try:
        row = conn.execute("SELECT is_system, name FROM roles WHERE id = %s", (role_id,)).fetchone()
        if not row:
            raise ValueError(f"角色不存在: {role_id}")
        if row["is_system"]:
            raise ValueError(f"系统内置角色不可删除: {row['name']}")

        conn.execute("UPDATE users SET role = 'user' WHERE role = (SELECT name FROM roles WHERE id = %s)", (role_id,))
        conn.execute("DELETE FROM role_permissions WHERE role_id = %s", (role_id,))
        conn.execute("DELETE FROM roles WHERE id = %s", (role_id,))
        conn.commit()
        
        # 刷新权限缓存
        _invalidate_permission_cache()
        
        logger.info(f"删除角色: role_id={role_id}")
    finally:
        conn.close()


# ── 用户管理 ──

def set_user_role(user_id: int, role: str) -> None:
    """修改用户角色（角色名，非 ID）。"""
    from backend.permission.checker import _invalidate_permission_cache
    conn = get_conn()
    try:
        exists = conn.execute("SELECT id FROM roles WHERE name = %s", (role,)).fetchone()
        if not exists:
            raise ValueError(f"角色不存在: {role}")
        conn.execute(
            "UPDATE users SET role = %s, updated_at = NOW() WHERE id = %s",
            (role, user_id),
        )
        conn.commit()
        
        # 刷新该用户的权限缓存
        _invalidate_permission_cache(user_id)
        
        logger.info(f"角色更新: user_id={user_id} → {role}")
    finally:
        conn.close()


def set_user_permission(user_id: int, permission: str, granted: bool) -> None:
    """设置用户的自定义权限覆盖。"""
    from backend.permission.checker import _invalidate_permission_cache
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO user_permissions (user_id, permission, granted)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE granted = %s, updated_at = NOW()""",
            (user_id, permission, 1 if granted else 0, 1 if granted else 0),
        )
        conn.commit()
        
        # 刷新该用户的权限缓存
        _invalidate_permission_cache(user_id)
        
        logger.info(f"{'[授权]' if granted else '[拒绝]'} 权限更新: user_id={user_id}, {permission}")
    finally:
        conn.close()


def get_user_perm_overrides(user_id: int) -> List[dict]:
    """获取用户的所有自定义权限覆盖。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT permission, granted FROM user_permissions WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        return [{"permission": r["permission"], "granted": bool(r["granted"])} for r in rows]
    finally:
        conn.close()
