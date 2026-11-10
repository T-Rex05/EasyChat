"""权限入口回归：file.delete / ledger.manage / system.config 的 service 层允许与拒绝。

P2 入口矩阵发现这三键无显式 allow/deny 用例（tests=0，docs/reviews/2026-11-10/P2-entry-matrix.md）。
本文件用真实 AccessService 有效权限判定（含撤销优先与未注册键惰性），
覆盖各键唯一的 service 入口；owner 边界另有 files 套件覆盖，不重复。
"""
from __future__ import annotations

import pytest

from backend.modules.files.contracts import SaveMetadata
from backend.modules.models.api import ModelsService
from backend.shared.errors import ForbiddenError
from tests.support.rig import TEST_JWT_SECRET, make_rig


@pytest.mark.asyncio
async def test_file_delete_denied_by_revoke_and_allowed_by_default(tmp_path):
    """user 默认含 file.delete：允许走通；显式撤销后同一入口必须拒绝（撤销优先）。"""
    rig = make_rig(tmp_path, seed_access=True)
    try:
        holder = rig.seed_user(role="user")
        rig.attach_files()
        saved = await rig.files.save_bytes(
            holder, b"payload", SaveMetadata(original_name="a.txt"),
        )
        file_id = saved.file.file_id
        # 默认授予：允许
        assert rig.files.delete_impact(holder, file_id) is not None
        # 撤销优先：拒绝
        revoker = rig.seed_user(role="user", revokes=("file.delete",))
        with pytest.raises(ForbiddenError):
            rig.files.delete_impact(revoker, file_id)
    finally:
        await rig.aclose()


@pytest.mark.asyncio
async def test_ledger_manage_denied_by_default_and_allowed_by_grant(tmp_path):
    """create_account 是 ledger.manage 唯一 service 入口：user 默认拒绝，grant 后允许。"""
    rig = make_rig(tmp_path, seed_access=True)
    try:
        rig.attach_files()
        rig.attach_ledger()
        plain = rig.seed_user(role="user")
        with pytest.raises(ForbiddenError):
            rig.ledger.create_account(plain, provider="wechat", account_alias="主账户")
        granted = rig.seed_user(role="user", grants=("ledger.manage",))
        row = rig.ledger.create_account(granted, provider="wechat", account_alias="主账户")
        assert row is not None
    finally:
        await rig.aclose()


@pytest.mark.asyncio
async def test_system_config_denied_by_default_and_allowed_by_grant(tmp_path):
    """ModelsService 经注入的 access.require_permission 走真实有效权限：默认拒绝，grant 后允许。"""
    rig = make_rig(tmp_path, seed_access=True)
    try:
        access = rig.access
        service = ModelsService(
            rig.db, encryption_secret=TEST_JWT_SECRET,
            permission_check=lambda actor, perm: access.require_permission(actor, perm),
        )
        plain = rig.seed_user(role="user")
        with pytest.raises(ForbiddenError):
            service.create_config(plain, name="m", provider="openai", model="gpt-x")
        granted = rig.seed_user(role="user", grants=("system.config",))
        cid = service.create_config(granted, name="m", provider="openai", model="gpt-x")
        assert cid > 0
    finally:
        await rig.aclose()
