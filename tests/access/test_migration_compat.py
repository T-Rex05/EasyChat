"""P3 受控迁移回归：存量库升级兼容、快照回滚、模板版本语义。

模拟迁移 0023 之后的存量库：角色已有授权、seed_state 标记 legacy，
验证读取/升级/回滚全程保持有效权限范围。
"""
from __future__ import annotations

import json


from tests.access.test_seed_lifecycle import _env  # noqa: F401  复用环境装配


async def test_rollback_restores_snapshot_exactly(rig) -> None:
    """回滚：应用模板后用快照恢复授权，有效权限范围与升级前一致。"""
    ready, access = await _env(rig)
    owner = ready.seed_user(role="super_admin")
    ready.seed_user(role="user")  # 供有效权限断言使用
    principal = access.snapshot_principal(owner.user_id)
    access.repo._mark_role_seeded("user", "legacy")  # noqa: SLF001
    before = ["chat.use", "cron.create"]
    access.repo.set_role_permissions_by_name("user", before)
    access.invalidate_all()

    result = access.apply_role_template(principal, "user")
    assert result["previous_permissions"] == before
    assert "superagent.create" in access.effective_permissions(_any_user_of(access, "user"))

    # 回滚：按快照恢复 + 登记回 legacy（模拟部署回退到旧版本代码）
    access.repo.set_role_permissions_by_name("user", result["previous_permissions"])
    access.repo._mark_role_seeded("user", "legacy")  # noqa: SLF001  (ON CONFLICT 不覆盖，需先删)
    import sqlite3

    conn = sqlite3.connect(str(access.repo.db.path))
    try:
        conn.execute("DELETE FROM role_seed_state WHERE role_name='user'")
        conn.commit()
    finally:
        conn.close()
    access.repo._mark_role_seeded("user", "legacy")  # noqa: SLF001
    access.invalidate_all()
    after = access.effective_permissions(_any_user_of(access, "user"))
    assert set(before) <= after
    assert "superagent.create" not in after
    # 旧版本 seed 逻辑（本修复后）不会再补种
    access.seed()
    assert "superagent.create" not in access.effective_permissions(_any_user_of(access, "user"))


async def test_migration_backfills_legacy_for_existing_roles(rig) -> None:
    """迁移 0023 语义：迁移执行时已存在的内置角色回填 legacy（不再被新版本播种）。

    直接执行迁移 SQL 的回填子句验证。
    """
    ready, access = await _env(rig)
    # 模拟存量库：删掉 seed_state（迁移前的状态），恢复角色旧授权
    import sqlite3

    conn = sqlite3.connect(str(access.repo.db.path))
    try:
        conn.execute("DELETE FROM role_seed_state")
        conn.execute("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name='admin')")
        conn.commit()
    finally:
        conn.close()
    # 重放迁移 0023 的回填段
    from pathlib import Path

    sql = Path("backend/platform/migrations/0023_permission_lifecycle.sql").read_text(encoding="utf-8")
    backfill = sql[sql.index("INSERT INTO role_seed_state"):]
    with access.repo.db.transaction() as c:
        for statement in _split_simple(backfill):
            c.execute(statement)
    state = access.repo.get_role_seed_state("admin")
    assert state is not None and state["template_version"] == "legacy"
    # 重新 seed：legacy 不被补种
    access.seed()
    conn = sqlite3.connect(str(access.repo.db.path))
    try:
        count = conn.execute(
            "SELECT count(*) c FROM role_permissions rp JOIN roles r ON r.id=rp.role_id WHERE r.name='admin'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 0  # 旧库授权保持为空，未被 v2 模板补入


async def test_snapshot_json_records_pre_upgrade_state(rig) -> None:
    ready, access = await _env(rig)
    owner = ready.seed_user(role="super_admin")
    principal = access.snapshot_principal(owner.user_id)
    access.repo._mark_role_seeded("admin", "legacy")  # noqa: SLF001
    before = ["chat.use", "system.manage"]
    access.repo.set_role_permissions_by_name("admin", before)
    access.apply_role_template(principal, "admin")
    state = access.repo.get_role_seed_state("admin")
    snapshot = json.loads(str(state["snapshot_json"]))
    assert sorted(snapshot) == sorted(before)
    assert state["template_version"] == "v2"


async def test_unseeded_role_is_distinct_from_explicitly_empty(rig) -> None:
    """「尚未初始化」与「明确空授权」可区分（方案 §3 兼容迁移）。"""
    ready, access = await _env(rig)
    # user 已初始化（seed 播种过）
    assert access.repo.get_role_seed_state("user") is not None
    # 自定义角色从未初始化
    admin = ready.seed_user(role="admin", grants=("system.manage",))
    principal = access.snapshot_principal(admin.user_id)
    role_id = access.create_role(principal, name="custom_x", display_name="X")
    assert role_id > 0
    assert access.repo.get_role_seed_state("custom_x") is None
    # 显式清空内置角色：seed_state 仍在（=已初始化），授权为空
    access.repo.set_role_permissions_by_name("user", [])
    access.invalidate_all()
    access.seed()
    assert access.repo.get_role_seed_state("user") is not None
    assert access.repo.snapshot_role_permissions("user") == []


def _split_simple(sql: str) -> list[str]:
    out = []
    for chunk in sql.split(";"):
        line = chunk.strip()
        if line and not line.startswith("--"):
            out.append(line)
    return out


def _any_user_of(access, role: str) -> int:
    import sqlite3

    conn = sqlite3.connect(str(access.repo.db.path))
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1", (role,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return int(row[0])


async def test_apply_preserves_custom_permissions_and_toolsets(rig) -> None:
    """评审 P1-2：合并语义——模板外自定义授权与工具组在升级后保留。"""
    ready, access = await _env(rig)
    owner = ready.seed_user(role="super_admin")
    ready.seed_user(role="user")
    principal = access.snapshot_principal(owner.user_id)
    access.repo._mark_role_seeded("user", "legacy")  # noqa: SLF001
    custom = ["chat.use", "trace.manage"]  # trace.manage 是模板外自定义
    access.repo.set_role_permissions_by_name("user", custom)
    access.repo.set_role_toolsets_by_name("user", ["terminal"])  # 自定义高风险工具
    access.invalidate_all()

    access.apply_role_template(principal, "user")
    perms = access.effective_permissions(_any_user_of(access, "user"))
    # 模板新增生效
    assert "superagent.create" in perms
    # 模板外自定义保留
    assert "trace.manage" in perms
    toolsets = access.repo.role_toolsets_by_name("user")
    assert "terminal" in toolsets and "web" in toolsets  # 并集
    state = access.repo.get_role_seed_state("user")
    assert json.loads(str(state["snapshot_json"])) == sorted(custom)  # 快照为升级前状态
