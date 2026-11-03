"""AgentForge 权限子系统 — 注册、检查、播种。"""
from backend.permission.registry import (
    PermissionDef,
    register_perm,
    seed_to_db,
    get_all_permissions,
    get_permission_tree,
)
from backend.permission.builtin import register_all_builtin_permissions
from backend.permission.checker import (
    get_user_role,
    get_user_permissions,
    has_permission,
    get_user_hermes_tools,
    check_ownership,
)

__all__ = [
    # registry
    "PermissionDef", "register_perm", "seed_to_db",
    "get_all_permissions", "get_permission_tree",
    "register_all_builtin_permissions",
    # checker
    "get_user_role", "get_user_permissions", "has_permission",
    "get_user_hermes_tools", "check_ownership",
]
