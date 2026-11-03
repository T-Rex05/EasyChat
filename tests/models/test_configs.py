"""models 模块行为测试：配置CRUD、密钥保护、选择、fallback链、健康状态。"""
from __future__ import annotations

import pytest

from backend.modules.models.api import ModelsService
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError
from tests.support.rig import TEST_JWT_SECRET


@pytest.fixture
def models(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)

    def check(actor: Principal, permission: str) -> None:
        if actor.role != "super_admin":
            raise ForbiddenError(f"缺少权限: {permission}")

    svc = ModelsService(db, encryption_secret=TEST_JWT_SECRET, permission_check=check)
    yield svc, db, admin
    db.close()


def test_create_and_masking(models):
    svc, db, admin = models
    cid = svc.create_config(admin, name="main", provider="openai", model="gpt-x",
                            api_key="sk-abcdefghijklmnop1234", base_url="https://api.x.com")
    profile = svc.get_chat_profile()  # 尚未激活
    assert profile is None
    svc.set_active(admin, cid)
    profile = svc.get_chat_profile()
    assert profile is not None
    assert profile.has_api_key is True
    assert profile.api_key_masked.startswith("sk-a")
    assert profile.api_key_masked.endswith("1234")
    assert "*" in profile.api_key_masked
    # 原始密钥永不出现在任何公开表示
    dumped = str(profile)
    assert "sk-abcdefghijklmnop1234" not in dumped


def test_config_version_bumps_on_update(models):
    svc, db, admin = models
    cid = svc.create_config(admin, name="m1", provider="p", model="m1", api_key="k" * 20)
    v1 = svc.repo.get_config(cid).config_version
    svc.update_config(admin, cid, model="m2")
    v2 = svc.repo.get_config(cid).config_version
    assert v2 == v1 + 1


def test_active_pointer_switches_atomically(models):
    svc, db, admin = models
    c1 = svc.create_config(admin, name="a", provider="p", model="a")
    c2 = svc.create_config(admin, name="b", provider="p", model="b")
    svc.set_active(admin, c1)
    assert svc.get_chat_profile().config_id == c1
    svc.set_active(admin, c2)
    assert svc.get_chat_profile().config_id == c2


def test_delete_missing_and_invalid_inputs(models):
    svc, db, admin = models
    with pytest.raises(NotFoundError):
        svc.delete_config(admin, 999)
    with pytest.raises(InvalidInputError):
        svc.create_config(admin, name="", provider="p", model="m")


def test_permission_required_for_management(models):
    svc, db, admin = models
    plain = Principal(user_id=7, role="user", permission_revision=0)
    with pytest.raises(ForbiddenError):
        svc.list_configs(plain)
    with pytest.raises(ForbiddenError):
        svc.create_config(plain, name="x", provider="p", model="m")


def test_select_for_run_with_auxiliary_fallback(models):
    svc, db, admin = models
    c1 = svc.create_config(admin, name="chat", provider="p", model="chat-1", api_key="k" * 10)
    c2 = svc.create_config(admin, name="aux", provider="p", model="aux-1", api_key="k" * 10)
    svc.set_active(admin, c1)
    svc.save_fallback_chain(admin, [c2, c1])

    sel = svc.select_for_run()
    assert sel.chat.config_id == c1
    assert sel.fallback == ()  # 非auxiliary不加载链

    sel_aux = svc.select_for_run(auxiliary=True)
    assert [p.config_id for p in sel_aux.fallback] == [c2, c1]


def test_select_without_config_raises(tmp_path):
    db = Database(tmp_path / "empty.db")
    db.migrate()
    svc = ModelsService(db, encryption_secret=TEST_JWT_SECRET)
    with pytest.raises(NotFoundError):
        svc.select_for_run()
    db.close()


def test_fallback_chain_validates_ids(models):
    svc, db, admin = models
    with pytest.raises(InvalidInputError):
        svc.save_fallback_chain(admin, [42])


def test_health_state_bounded_and_local(models):
    svc, db, admin = models
    c1 = svc.create_config(admin, name="h", provider="p", model="h")
    for _ in range(3):
        svc.report_health(c1, ok=False)
    assert svc.is_healthy(c1) is False  # 连续3次失败视为不可用
    svc.report_health(c1, ok=True)
    assert svc.is_healthy(c1) is True
    # 有界：不超过64条
    for cid in range(100):
        svc.report_health(cid, ok=False)
    assert len(svc._fail_counts) <= 64
