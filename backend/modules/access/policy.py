"""纯函数权限规则（架构 §6）：优先级为 revoke > grant > 角色；super_admin 取全集。

本文件不得有 IO；所有输入显式传入，便于穷举测试。
"""
from __future__ import annotations

from backend.modules.access.contracts import (
    DEPRECATED_TOOLSETS,
    SUPER_ADMIN_ROLE,
    VALID_TOOLSETS,
)


def effective_permissions(
    *,
    role_name: str,
    role_permissions: frozenset[str],
    grants: frozenset[str],
    revokes: frozenset[str],
    all_registered_permissions: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """有效权限 = (角色权限 ∪ 用户grant) − 用户revoke；super_admin 取已注册全集。"""
    if role_name == SUPER_ADMIN_ROLE:
        return frozenset(all_registered_permissions)
    effective = set(role_permissions) | set(grants)
    effective -= set(revokes)
    return frozenset(effective)


def effective_toolsets(raw_toolsets: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """角色工具集过滤：剔除历史废弃键与未注册键；缺失/损坏配置不授予工具（fail-closed）。"""
    if not raw_toolsets:
        return ()
    return tuple(t for t in raw_toolsets if t in VALID_TOOLSETS and t not in DEPRECATED_TOOLSETS)


def can_manage_resource(
    *,
    item_owner_id: int,
    principal_user_id: int,
    role_name: str,
    effective_permissions: frozenset[str],
    manage_perm: str,
) -> bool:
    """统一资源归属规则（沿用旧 check_ownership 语义）：

    super_admin、持有 manage_perm 的管理者、或 owner 本人可操作。
    """
    if role_name == SUPER_ADMIN_ROLE:
        return True
    if manage_perm in effective_permissions:
        return True
    return item_owner_id == principal_user_id
