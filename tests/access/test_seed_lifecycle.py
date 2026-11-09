"""权限整改回归（P1）：模板版本、空权限保持、不自动授予、生命周期、委派边界。

每项先于实现编写；修复前这些用例失败。
"""
from __future__ import annotations

import json

import pytest

from tests.support.rig import make_rig


async def _env(rig):
    ready = rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)
    rig.db, rig.access = ready.db, ready.access
    return ready, ready.access


def _force_legacy_state(access, role_name: str) -> None:
    """把角色重置为「存量库 legacy」状态（删除 v2 记录 → 标记 legacy → 缩授权）。"""
    import sqlite3

    conn = sqlite3.connect(str(access.repo.db.path))
    try:
        conn.execute("DELETE FROM role_seed_state WHERE role_name=?", (role_name,))
        conn.commit()
    finally:
        conn.close()
    access.repo._mark_role_seeded(role_name, "legacy")  # noqa: SLF001


def _user_id_of(access, role: str) -> int:
    import sqlite3

    conn = sqlite3.connect(str(access.repo.db.path))
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1", (role,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, f"没有 {role} 角色的用户"
    return int(row[0])


# ---- 模板版本与播种 ---------------------------------------------------------------


async def test_builtin_role_with_empty_permissions_stays_empty_after_reseed(rig) -> None:
    """验收 2：管理员显式清空内置角色授权，重启（重新 seed）后保持为空。"""
    ready, access = await _env(rig)
    access.repo.set_role_permissions_by_name("user", [])
    access.invalidate_all()
    access.seed()  # 模拟重启（bootstrap.run_startup 同一入口）
    user = ready.seed_user(role="user")
    perms = access.effective_permissions(user.user_id)
    assert perms == frozenset(), f"空权限被重新播种: {sorted(perms)}"


async def test_existing_roles_do_not_gain_new_template_permissions(rig) -> None:
    """验收 3：存量库（legacy 标记）重新 seed，新增模板权限不会自动授予。"""
    ready, access = await _env(rig)
    access.repo._mark_role_seeded("admin", "legacy")  # noqa: SLF001  模拟迁移 0023 回填
    access.repo.set_role_permissions_by_name("admin", ["chat.use"])
    access.invalidate_all()
    access.seed()
    admin = ready.seed_user(role="admin")
    perms = access.effective_permissions(admin.user_id)
    assert "superagent.manage" not in perms
    assert "superagent.view" not in perms
    assert "chat.use" in perms


async def test_fresh_database_seeds_v2_template(rig) -> None:
    """全新库（无 seed_state 记录）：播种 v2 模板并登记版本。"""
    ready, access = await _env(rig)
    state = access.repo.get_role_seed_state("user")
    assert state is not None
    assert state["template_version"] != "legacy"
    user = ready.seed_user(role="user")
    perms = access.effective_permissions(user.user_id)
    assert "superagent.view" in perms
    assert "chat.use" in perms


# ---- 生命周期 --------------------------------------------------------------------


async def test_deprecated_permissions_do_not_participate_in_effective_grants(rig) -> None:
    """验收 1/8：deprecated 键（terminal.audit/evolution.manage）不参与有效授权。

    两条来源都封死：service 拒绝 override 写入（与角色 CRUD 同口径）；
    存量行（绕过 service 直插）也在 policy 统一过滤。
    """
    ready, access = await _env(rig)
    admin = ready.seed_user(role="admin")
    principal = access.snapshot_principal(admin.user_id)
    # service 写入被拒（评审 P2-1 口径对齐）
    with pytest.raises(Exception, match="已退役"):
        access.set_user_permission(principal, admin.user_id, "terminal.audit", True)
    # 存量行（直插，模拟旧库残留）不参与有效授权
    access.repo.set_user_permission(admin.user_id, "terminal.audit", True)
    access.invalidate_all()
    perms = access.effective_permissions(admin.user_id)
    assert "terminal.audit" not in perms
    assert "evolution.manage" not in perms


async def test_admin_can_manage_normal_users(rig) -> None:
    """评审 P0-1 回归正向用例：admin 对普通用户的常规管理不受拥有者边界影响。"""
    ready, access = await _env(rig)
    admin = ready.seed_user(role="admin", grants=("system.manage",))
    normal = ready.seed_user(role="user")
    another = ready.seed_user(role="user")
    principal = access.snapshot_principal(admin.user_id)
    # 改角色 / 禁用 / 启用 / 写覆盖 全部允许
    access.set_user_role(principal, normal.user_id, "admin")
    access.set_user_status(principal, another.user_id, 0)
    access.set_user_status(principal, another.user_id, 1)
    access.set_user_permission(principal, normal.user_id, "chat.use", True)


def test_permission_catalog_covers_all_active_permissions() -> None:
    """验收 11：所有 active 权限都登记在目录中，且归属 9 模块或 internal。"""
    from backend.modules.access.contracts import (
        ALL_PERMISSION_KEYS,
        DEPRECATED_PERMISSION_KEYS,
        MODULE_KEYS,
        permission_catalog,
    )

    active = ALL_PERMISSION_KEYS - DEPRECATED_PERMISSION_KEYS
    catalog = permission_catalog()
    for key in active:
        entry = catalog.get(key)
        assert entry is not None, f"active 权限未登记目录: {key}"
        assert entry["module"] in MODULE_KEYS or entry.get("internal"), (
            f"{key} 既不属于 9 功能模块也不是 internal: {entry['module']}"
        )


# ---- 委派边界与拥有者保护 -----------------------------------------------------------


async def test_owner_protection_last_super_admin_cannot_be_demoted_or_disabled(rig) -> None:
    """验收 9：最后一个 super_admin 不可降级/禁用。"""
    ready, access = await _env(rig)
    owner = ready.seed_user(role="super_admin")
    actor = ready.seed_user(role="super_admin")
    access.set_user_role(
        access.snapshot_principal(actor.user_id), owner.user_id, "admin"
    )
    actor_principal = access.snapshot_principal(actor.user_id)
    with pytest.raises(Exception, match="拥有者|最后一个|super_admin"):
        access.set_user_role(actor_principal, actor.user_id, "admin")
    with pytest.raises(Exception, match="拥有者|最后一个|super_admin"):
        access.set_user_status(actor_principal, actor.user_id, 0)


async def test_admin_cannot_manage_super_admin_or_grant_owner_role(rig) -> None:
    """验收 9：拥有者身份只能由拥有者管理（system.manage 不够）。"""
    ready, access = await _env(rig)
    admin = ready.seed_user(role="admin", grants=("system.manage",))
    owner = ready.seed_user(role="super_admin")
    normal = ready.seed_user(role="user")
    admin_principal = access.snapshot_principal(admin.user_id)
    owner_principal = access.snapshot_principal(owner.user_id)
    with pytest.raises(Exception):
        access.set_user_role(admin_principal, owner.user_id, "admin")
    with pytest.raises(Exception):
        access.set_user_status(admin_principal, owner.user_id, 0)
    with pytest.raises(Exception):
        access.set_user_role(admin_principal, normal.user_id, "super_admin")
    # super_admin 可以委派 admin
    access.set_user_role(owner_principal, normal.user_id, "admin")


# ---- 角色 CRUD 校验一致性 -----------------------------------------------------------


async def test_update_role_validates_toolsets_like_create(rig) -> None:
    """验收：创建与更新路径执行同等的工具组合法性校验。"""
    ready, access = await _env(rig)
    admin = ready.seed_user(role="admin", grants=("system.manage",))
    principal = access.snapshot_principal(admin.user_id)
    role_id = access.create_role(principal, name="ops", display_name="运维")
    with pytest.raises(Exception, match="工具集"):
        access.update_role(principal, role_id, toolsets=["data", "kb_search"])
    access.update_role(principal, role_id, toolsets=["web"])


async def test_deprecated_permissions_rejected_in_role_crud(rig) -> None:
    ready, access = await _env(rig)
    admin = ready.seed_user(role="admin", grants=("system.manage",))
    principal = access.snapshot_principal(admin.user_id)
    with pytest.raises(Exception, match="已退役|terminal.audit"):
        access.create_role(principal, name="legacy", display_name="x",
                           permissions=["terminal.audit"])
    role_id = access.create_role(principal, name="legacy2", display_name="x")
    with pytest.raises(Exception, match="已退役|terminal.audit"):
        access.update_role(principal, role_id, permissions=["chat.use", "terminal.audit"])


# ---- capabilities 统一出口 -----------------------------------------------------------


async def test_capabilities_outputs_nine_modules_and_ops(rig) -> None:
    """验收 4：9 个功能模块；只读角色 read=True/use=False。"""
    from backend.modules.access.contracts import MODULE_KEYS

    ready, access = await _env(rig)
    reader = ready.seed_user(role="reader_memo", grants=("memory.view", "chat.use"))
    caps = access.capabilities(access.snapshot_principal(reader.user_id))
    assert set(caps["modules"].keys()) >= set(MODULE_KEYS)
    assert caps["modules"]["memory"]["read"] is True
    assert caps["modules"]["memory"]["use"] is False
    assert caps["modules"]["chat"]["use"] is True
    assert caps["modules"]["ledger"]["enabled"] is False


async def test_capabilities_super_admin_is_full(rig) -> None:
    ready, access = await _env(rig)
    owner = ready.seed_user(role="super_admin")
    caps = access.capabilities(access.snapshot_principal(owner.user_id))
    assert caps["super_admin"] is True
    for module in caps["modules"].values():
        assert module["enabled"] is True


# ---- 升级预览与显式应用（P3 受控迁移） -------------------------------------------------


async def test_upgrade_preview_reports_template_diff(rig) -> None:
    ready, access = await _env(rig)
    admin = ready.seed_user(role="admin", grants=("system.manage",))
    _force_legacy_state(access, "admin")
    access.repo.set_role_permissions_by_name("admin", ["chat.use"])
    access.invalidate_all()
    preview = access.permission_upgrade_preview(access.snapshot_principal(admin.user_id))
    admin_row = next(r for r in preview["roles"] if r["role"] == "admin")
    assert "superagent.manage" in admin_row["missing_from_role"]
    assert admin_row["template_version"] == "legacy"
    assert admin_row["pending"] is True
    assert "superagent.manage" in admin_row["high_risk_missing"]


async def test_apply_template_requires_owner_and_snapshots(rig) -> None:
    ready, access = await _env(rig)
    admin = ready.seed_user(role="admin", grants=("system.manage",))
    owner = ready.seed_user(role="super_admin")
    _force_legacy_state(access, "admin")
    access.repo.set_role_permissions_by_name("admin", ["chat.use"])
    access.invalidate_all()
    # system.manage 不足以执行升级（新增授权需要拥有者确认）
    with pytest.raises(Exception):
        access.apply_role_template(access.snapshot_principal(admin.user_id), "admin")
    result = access.apply_role_template(access.snapshot_principal(owner.user_id), "admin")
    assert result["previous_permissions"] == ["chat.use"]
    state = access.repo.get_role_seed_state("admin")
    assert state["template_version"] != "legacy"
    snapshot = json.loads(state["snapshot_json"])
    assert snapshot == ["chat.use"]
    admin_id = _user_id_of(access, "admin")
    perms = access.effective_permissions(admin_id)
    assert "superagent.manage" in perms
    assert "chat.use" in perms
