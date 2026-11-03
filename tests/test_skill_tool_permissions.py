"""技能/工具 归属、发布与审核权限单元测试"""
import json

import pytest

from backend.service import skill_service


class TestCanAccessSkill:
    def test_owner_allowed(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_meta_get", lambda name: {"owner_id": 7})
        assert skill_service.can_access_skill("s1", user_id=7, role="user") is True

    def test_stranger_denied(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_meta_get", lambda name: {"owner_id": 7})
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        assert skill_service.can_access_skill("s1", user_id=8, role="user") is False

    def test_manage_allowed(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_meta_get", lambda name: {"owner_id": 7})
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: perm == "skill.manage")
        assert skill_service.can_access_skill("s1", user_id=8, role="user") is True

    def test_super_admin_without_meta(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_meta_get", lambda name: None)
        assert skill_service.can_access_skill("s1", user_id=1, role="super_admin") is True

    def test_no_meta_stranger_denied(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_meta_get", lambda name: None)
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        assert skill_service.can_access_skill("s1", user_id=8, role="user") is False


class TestCreateSkillPermission:
    def test_user_without_perm_denied(self, monkeypatch):
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        with pytest.raises(ValueError):
            skill_service.create_skill("x", "content", user_id=3, role="user")

    def test_admin_role_does_not_bypass_permission(self, monkeypatch, tmp_path):
        """回归防护：`role="admin"` 本身**不再**构成授权，必须真的持有 `skill.create`。

        契约变更说明：`create_skill` 此前写成
        `role not in ("admin","super_admin") and not has_permission(...)`，
        于是 admin 角色名可以绕过勾选。已移除该旁路（那会让"取消勾选"不生效）。
        生产里 `admin` 在 DB 中持有 `skill.create`，所以实际权限不受影响 ——
        本测试断言的正是"角色名不构成授权"这一点。
        """
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        monkeypatch.setattr(skill_service, "_get_skills_dir", lambda: tmp_path)
        monkeypatch.setattr(skill_service, "_meta_insert", lambda *a, **k: None)
        with pytest.raises(ValueError):
            skill_service.create_skill("x", "内容", user_id=1, role="admin")

    def test_admin_with_create_perm_ok(self, monkeypatch, tmp_path):
        """持有 `skill.create` 时创建成功（admin 的默认权限集里就有它）。"""
        monkeypatch.setattr("backend.permission.checker.has_permission",
                            lambda uid, perm: perm == "skill.create")
        monkeypatch.setattr(skill_service, "_get_skills_dir", lambda: tmp_path)
        monkeypatch.setattr(skill_service, "_meta_insert", lambda *a, **k: None)
        result = skill_service.create_skill("x", "内容", user_id=1, role="admin")
        assert isinstance(result, dict) and "status" in result


class TestPublishToPool:
    def test_publish_stranger_skill_denied(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_query_all_skills", lambda: [{"name": "s1", "owner_id": 9}])
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        with pytest.raises(ValueError):
            skill_service.publish_to_pool("skill", "s1", user_id=3)

    def test_publish_own_skill_ok(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_query_all_skills", lambda: [{"name": "s1", "owner_id": 3}])
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        monkeypatch.setattr(skill_service, "_can_skip_review", lambda uid, ct: False)
        executed = []

        class FakeConn:
            def execute(self, sql, params):
                executed.append((sql, params))

            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(skill_service, "_meta_conn", lambda: FakeConn())
        result = skill_service.publish_to_pool("skill", "s1", user_id=3)
        assert result["status"] == "pending"
        assert executed and "content_pool" in executed[0][0]

    def test_publish_missing_skill_raises(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_query_all_skills", lambda: [])
        with pytest.raises(FileNotFoundError):
            skill_service.publish_to_pool("skill", "ghost", user_id=3)

    def test_publish_pending_tool_denied(self, monkeypatch, tmp_path):
        # 工具审核已废弃（工具现由系统内置），此测试保留但不再测试工具发布
        # 改为测试技能发布
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: True)
        monkeypatch.setattr(skill_service, "_get_skills_dir", lambda: tmp_path)
        (tmp_path / "s1.json").write_text(
            json.dumps({"name": "s1", "status": "pending", "owner_id": 3}), encoding="utf-8")
        with pytest.raises(ValueError):
            skill_service.publish_to_pool("skill", "s1", user_id=3)

    def test_publish_approved_skill_ok(self, monkeypatch, tmp_path):
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        monkeypatch.setattr(skill_service, "_can_skip_review", lambda uid, ct: False)
        monkeypatch.setattr(skill_service, "_get_skills_dir", lambda: tmp_path)
        (tmp_path / "s1.json").write_text(
            json.dumps({"name": "s1", "status": "approved", "owner_id": 3}), encoding="utf-8")
        executed = []

        class FakeConn:
            def execute(self, sql, params):
                executed.append((sql, params))

            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(skill_service, "_meta_conn", lambda: FakeConn())
        result = skill_service.publish_to_pool("skill", "s1", user_id=3)
        assert result["status"] == "pending"


class TestPublishSkipReview:
    def test_skip_review_logic(self, monkeypatch):
        """`_can_skip_review` 只看 `skill.manage` 权限。

        契约变更说明：此前 admin / super_admin **角色**直通（硬编码旁路），
        但那会让"在角色编辑里取消勾选"不生效，故已移除旁路，改为纯权限判定。
        本测试原先断言 `skill.share` 可跳过审核、且断言 `skill.manage` 返回 False
        （与语义相反），均按新契约修正。
        """
        from backend.permission import checker

        # 仅 skill.pool.review（审核权）不足以跳过自己的审核
        monkeypatch.setattr(checker, "get_user_permissions", lambda uid: {"skill.pool.review"})
        assert skill_service._can_skip_review(1, "skill") is False

        # 有 skill.manage 才可以跳过
        monkeypatch.setattr(checker, "get_user_permissions", lambda uid: {"skill.manage"})
        assert skill_service._can_skip_review(2, "skill") is True

        # 无权限 → 不允许
        monkeypatch.setattr(checker, "get_user_permissions", lambda uid: set())
        assert skill_service._can_skip_review(3, "skill") is False

        # user_id 缺失 / 为 0 → fail-closed
        assert skill_service._can_skip_review(0, "skill") is False

    def test_publish_admin_active(self, monkeypatch):
        monkeypatch.setattr(skill_service, "_query_all_skills", lambda: [{"name": "s1", "owner_id": 3}])
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        monkeypatch.setattr(skill_service, "_can_skip_review", lambda uid, ct: True)
        executed = []

        class FakeConn:
            def execute(self, sql, params):
                executed.append((sql, params))

            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(skill_service, "_meta_conn", lambda: FakeConn())
        result = skill_service.publish_to_pool("skill", "s1", user_id=3)
        assert result["status"] == "active"
        assert executed and executed[0][1][-1] == "active"


class TestAdminReviewPermission:
    def test_admin_role_passes(self):
        """审核准入**只认 `skill.pool.review`** —— admin 通过靠的是它实际持有的该权限，
        而不是角色名、也不是 `skill.manage`。

        `admin` / `super_admin` 在 `role_permissions` 里同时持有两者
        （见 backend/permission/builtin.py 的 15 个 key），生产里
        `get_current_user` 总会填 permissions，所以实际不受影响。
        """
        from backend.controller.admin_controller import _can_review

        for role in ("admin", "super_admin"):
            assert _can_review({"role": role, "permissions": {"skill.pool.review"}}, "skill") is True

    def test_skill_manage_alone_cannot_review(self):
        """回归防护：只有 `skill.manage`、没有 `skill.pool.review` 时**不能**审核。

        「技能池审核」是独立能力，此前写成「skill.pool.review **或** skill.manage」，
        导致该勾选框失效（取消勾选后只要还留着「管理全部技能」就照样放行），
        与已修复的 kb.eval 属同类问题。
        """
        from backend.controller.admin_controller import _can_review

        assert _can_review({"role": "admin", "permissions": {"skill.manage"}}, "skill") is False
        assert _can_review({"role": "user", "permissions": {"skill.manage"}}, "skill") is False

    def test_pool_review_perm_passes(self):
        """持有 `skill.pool.review` 的普通用户即可审核（旧测试误用了不存在的 `skill.share`）。"""
        from backend.controller.admin_controller import _can_review

        assert _can_review({"role": "user", "permissions": {"skill.pool.review"}}, "skill") is True

    def test_role_name_alone_is_not_enough(self):
        """回归防护：只给角色名、不给 permissions 时**不再**直通。

        这条断言正是"勾选才生效"的核心保障——若有人重新引入角色旁路，它会失败。
        """
        from backend.controller.admin_controller import _can_review

        assert _can_review({"role": "admin"}, "skill") is False
        assert _can_review({"role": "super_admin"}, "skill") is False

    def test_plain_user_denied(self):
        from backend.controller.admin_controller import _can_review
        assert _can_review({"role": "user", "permissions": set()}, "skill") is False
        assert _can_review({"role": "user", "permissions": set()}, None) is False