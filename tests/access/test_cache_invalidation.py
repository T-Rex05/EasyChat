"""缓存失效与即时生效测试：角色变更/禁用用户/授权覆盖立即影响下一次操作。"""
from __future__ import annotations

import pytest

from backend.shared.errors import ForbiddenError, InvalidInputError
from tests.support.rig import make_rig


@pytest.fixture
def rig(tmp_path):
    r = make_rig(tmp_path, seed_access=True)
    yield r


@pytest.mark.asyncio
async def test_role_permission_change_affects_all_role_users_immediately(rig):
    access = rig.access
    admin = rig.seed_user(role="super_admin")
    member = rig.seed_user(role="user")  # 依赖角色默认授权
    granted_member = rig.seed_user(role="user", grants=("chat.use",))  # 个人 grant 兜底
    assert "chat.use" in access.effective_permissions(member.user_id)

    # admin 修改 user 角色权限：移除 chat.use（replace 语义）
    user_role_id = access.repo.get_role_by_name("user").role_id
    access.update_role(
        admin,
        user_role_id,
        permissions=["skill.create", "memory.view", "memory.edit", "cron.create", "trace.view"],
    )
    # 角色路径立即失效；个人 grant 仍在（grant 独立于角色）
    assert "chat.use" not in access.effective_permissions(member.user_id)
    assert "chat.use" in access.effective_permissions(granted_member.user_id)

    # 恢复后立即生效
    access.update_role(
        admin,
        user_role_id,
        permissions=["chat.use", "skill.create", "memory.view", "memory.edit", "cron.create", "trace.view"],
    )
    assert "chat.use" in access.effective_permissions(member.user_id)
    await rig.aclose()


@pytest.mark.asyncio
async def test_user_role_change_immediate(rig):
    access = rig.access
    admin = rig.seed_user(role="super_admin")
    member = rig.seed_user(role="user")
    assert "system.manage" not in access.effective_permissions(member.user_id)

    access.set_user_role(admin, member.user_id, "admin")
    assert "system.manage" in access.effective_permissions(member.user_id)
    await rig.aclose()


@pytest.mark.asyncio
async def test_grant_revoke_immediate(rig):
    access = rig.access
    admin = rig.seed_user(role="super_admin")
    member = rig.seed_user(role="user")

    access.set_user_permission(admin, member.user_id, "system.manage", True)
    assert "system.manage" in access.effective_permissions(member.user_id)
    access.set_user_permission(admin, member.user_id, "system.manage", False)
    assert "system.manage" not in access.effective_permissions(member.user_id)
    await rig.aclose()


@pytest.mark.asyncio
async def test_disable_user_blocks_next_operation_even_with_valid_token(rig):
    access = rig.access
    admin = rig.seed_user(role="super_admin")
    member = rig.seed_user(role="user")
    token = access.create_token(member.user_id, "member", "user")

    # 未禁用：token 可用
    principal = access.authenticate_token(token)
    assert principal.user_id == member.user_id

    access.set_user_status(admin, member.user_id, 0)

    # 禁用立即生效：有效 token 也被拒
    with pytest.raises(ForbiddenError):
        access.authenticate_token(token)
    with pytest.raises(ForbiddenError):
        access.snapshot_principal(member.user_id)
    await rig.aclose()


@pytest.mark.asyncio
async def test_validate_principal_revalidates_role_and_revision(rig):
    access = rig.access
    admin = rig.seed_user(role="super_admin")
    member = rig.seed_user(role="user")
    stale = access.snapshot_principal(member.user_id)

    access.set_user_role(admin, member.user_id, "admin")
    refreshed = access.validate_principal(stale)
    assert refreshed.role == "admin"
    assert refreshed.permission_revision == access.permission_revision
    assert refreshed.permission_revision != stale.permission_revision
    await rig.aclose()


@pytest.mark.asyncio
async def test_service_rejects_unregistered_permissions(rig):
    """未注册权限键在服务层入口被拒绝（R03：已删业务的权限不得再授）。"""
    access = rig.access
    admin = rig.seed_user(role="super_admin")
    member = rig.seed_user(role="user")
    with pytest.raises(InvalidInputError):
        access.set_user_permission(admin, member.user_id, "kb.manage", True)
    with pytest.raises(InvalidInputError):
        access.create_role(admin, name="r1", display_name="R1", permissions=["graph.manage"])
    await rig.aclose()


@pytest.mark.asyncio
async def test_seed_does_not_overwrite_custom_role_permissions(rig):
    """默认授权只在角色零授权时播种；已有授权的角色不被覆盖。"""
    access = rig.access
    admin = rig.seed_user(role="super_admin")
    # 自定义 user 角色：只留一个权限
    access.update_role(
        admin,
        access.repo.get_role_by_name("user").role_id,
        permissions=["chat.use"],
    )
    # 再次 seed：不覆盖
    access.seed()
    perms = access.effective_permissions(rig.seed_user(role="user").user_id)
    assert perms == frozenset({"chat.use"})
    await rig.aclose()


@pytest.mark.asyncio
async def test_cache_is_bounded(rig):
    access = rig.access
    for i in range(50):
        u = rig.seed_user(role="user", username=f"bounded_{i}")
        access.effective_permissions(u.user_id)
        access.hermes_toolsets(u.user_id)
    assert len(access._perm_cache) <= access._cache_maxsize
    assert len(access._toolsets_cache) <= access._cache_maxsize
    assert len(access._user_cache) <= access._cache_maxsize
    await rig.aclose()
