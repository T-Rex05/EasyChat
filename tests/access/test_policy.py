"""纯规则测试：有效权限运算 / 工具集过滤 / 资源归属（无 IO）。"""
from __future__ import annotations

from backend.modules.access.contracts import ALL_PERMISSION_KEYS
from backend.modules.access.policy import (
    can_manage_resource,
    effective_permissions,
    effective_toolsets,
)


def test_revoke_wins_over_role_and_grant():
    assert effective_permissions(
        role_name="user",
        role_permissions=frozenset({"chat.use", "skill.create"}),
        grants=frozenset({"chat.use"}),
        revokes=frozenset({"chat.use"}),
    ) == frozenset({"skill.create"})


def test_grant_adds_to_role():
    assert effective_permissions(
        role_name="user",
        role_permissions=frozenset({"chat.use"}),
        grants=frozenset({"system.manage"}),
        revokes=frozenset(),
    ) == frozenset({"chat.use", "system.manage"})


def test_revoke_removes_role_permission():
    assert effective_permissions(
        role_name="user",
        role_permissions=frozenset({"chat.use", "trace.view"}),
        grants=frozenset(),
        revokes=frozenset({"trace.view"}),
    ) == frozenset({"chat.use"})


def test_super_admin_gets_all_registered_permissions():
    result = effective_permissions(
        role_name="super_admin",
        role_permissions=frozenset(),  # 即使库中零授权
        grants=frozenset(),
        revokes=frozenset({"chat.use"}),  # revoke 也无法收回 super_admin 全集
        all_registered_permissions=ALL_PERMISSION_KEYS,
    )
    assert result == ALL_PERMISSION_KEYS


def test_normal_role_cannot_exceed_registered():
    """未注册的权限键（如历史残留）不因 grant 而生效——旧规则允许 grant 任意键，
    新规则在服务层入口拒绝未注册键；此处验证纯函数按输入集合运算。"""
    result = effective_permissions(
        role_name="user",
        role_permissions=frozenset(),
        grants=frozenset({"kb.manage"}),  # 已删业务权限（R03）
        revokes=frozenset(),
    )
    assert result == frozenset({"kb.manage"})  # 纯函数按输入运算
    # 服务层 create/set 接口负责拒绝未注册键（见 test_cache_invalidation.py）


def test_empty_everything_is_empty():
    assert effective_permissions(
        role_name="ghost", role_permissions=frozenset(), grants=frozenset(), revokes=frozenset()
    ) == frozenset()


# ---- 工具集过滤 ----------------------------------------------------------------


def test_toolsets_filter_deprecated_and_unknown():
    result = effective_toolsets(["web", "terminal", "paper_repro", "vision", "utility", "bogus_tool"])
    assert result == ("web", "terminal")


def test_toolsets_empty_or_none_fail_closed():
    assert effective_toolsets(None) == ()
    assert effective_toolsets([]) == ()


def test_all_current_toolsets_pass_through():
    from backend.modules.access.contracts import TOOLSET_DEFS

    keys = [t["key"] for t in TOOLSET_DEFS]
    assert set(effective_toolsets(keys)) == set(keys)


# ---- 资源归属 --------------------------------------------------------------------


def test_owner_can_access_own_resource():
    assert can_manage_resource(
        item_owner_id=7, principal_user_id=7, role_name="user",
        effective_permissions=frozenset(), manage_perm="skill.manage",
    )


def test_manage_perm_holder_cross_owner_access():
    assert can_manage_resource(
        item_owner_id=7, principal_user_id=3, role_name="admin",
        effective_permissions=frozenset({"skill.manage"}), manage_perm="skill.manage",
    )


def test_super_admin_cross_owner_access():
    assert can_manage_resource(
        item_owner_id=7, principal_user_id=1, role_name="super_admin",
        effective_permissions=frozenset(), manage_perm="skill.manage",
    )


def test_plain_user_cannot_access_others_resource():
    assert not can_manage_resource(
        item_owner_id=7, principal_user_id=3, role_name="user",
        effective_permissions=frozenset({"chat.use"}), manage_perm="skill.manage",
    )
