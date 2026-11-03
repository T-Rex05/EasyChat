"""技能按用户隔离（每用户技能视图）单元测试"""
import sys
from pathlib import Path

import pytest

# Hermes 内部模块使用顶层导入（from hermes_constants import ...），需要 hermes 在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "hermes"))


def _make_skill(tmp_path, name, description=""):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description or name}\n---\n\nBody\n", encoding="utf-8")


class TestPromptBuilderScope:
    """系统提示词技能索引按 scope 过滤（cold 路径 + 缓存隔离）。"""

    def _setup(self, tmp_path, monkeypatch):
        from agent import prompt_builder as pb
        monkeypatch.setattr(pb, "get_skills_dir", lambda: tmp_path)
        monkeypatch.setattr(pb, "get_all_skills_dirs", lambda: [tmp_path])
        monkeypatch.setattr(pb, "get_disabled_skill_names", lambda platform=None: set())
        monkeypatch.setattr(pb, "get_hermes_home", lambda: tmp_path)
        return pb

    def test_full_scope_includes_all(self, tmp_path, monkeypatch):
        pb = self._setup(tmp_path, monkeypatch)
        _make_skill(tmp_path, "alpha")
        _make_skill(tmp_path, "beta")
        prompt = pb.build_skills_system_prompt(visible_skills=None)
        assert "alpha" in prompt and "beta" in prompt

    def test_scope_filters_cold_path(self, tmp_path, monkeypatch):
        pb = self._setup(tmp_path, monkeypatch)
        _make_skill(tmp_path, "alpha")
        _make_skill(tmp_path, "beta")
        prompt = pb.build_skills_system_prompt(visible_skills={"alpha"})
        assert "alpha" in prompt
        assert "beta" not in prompt

    def test_cache_isolated_by_scope(self, tmp_path, monkeypatch):
        """不同 scope 不能互相命中缓存（否则用户 B 会看到用户 A 的索引）。"""
        pb = self._setup(tmp_path, monkeypatch)
        _make_skill(tmp_path, "alpha")
        _make_skill(tmp_path, "beta")
        p1 = pb.build_skills_system_prompt(visible_skills={"alpha"})
        p2 = pb.build_skills_system_prompt(visible_skills={"beta"})
        assert p1 != p2
        assert "alpha" in p1 and "beta" not in p1
        assert "beta" in p2 and "alpha" not in p2


class TestSkillsToolScope:
    """对话中 skills_list / skill_view 按 contextvar 过滤。"""

    def test_scope_allows_helper(self):
        from tools import skills_tool
        skills_tool.SKILLS_SCOPE_CTX.set(None)
        assert skills_tool._agentforge_scope_allows("anything") is True
        skills_tool.SKILLS_SCOPE_CTX.set({"a", "b"})
        assert skills_tool._agentforge_scope_allows("a") is True
        assert skills_tool._agentforge_scope_allows("c") is False

    def test_filter_locked_skills_scoped(self):
        from tools import skills_tool
        skills_tool.SKILLS_SCOPE_CTX.set({"a", "b"})
        skills = [{"name": "a"}, {"name": "c"}, {"name": "b"}]
        result = skills_tool._filter_locked_skills(skills)
        assert [s["name"] for s in result] == ["a", "b"]
        skills_tool.SKILLS_SCOPE_CTX.set(None)

    def test_skill_view_out_of_scope_rejected(self, tmp_path, monkeypatch):
        import json
        from tools import skills_tool
        _make_skill(tmp_path, "secret_skill", "secret")
        monkeypatch.setattr(skills_tool, "_skills_dir", lambda: tmp_path)
        monkeypatch.setattr(skills_tool, "SKILLS_DIR", tmp_path)
        skills_tool.SKILLS_SCOPE_CTX.set(set())  # 空 scope：什么都不可见
        result = json.loads(skills_tool.skill_view("secret_skill"))
        assert result.get("success") is False
        assert "not available" in result.get("error", "")
        skills_tool.SKILLS_SCOPE_CTX.set(None)

    def test_skill_view_in_scope_allowed(self, tmp_path, monkeypatch):
        import json
        from tools import skills_tool
        _make_skill(tmp_path, "open_skill", "open")
        monkeypatch.setattr(skills_tool, "_skills_dir", lambda: tmp_path)
        monkeypatch.setattr(skills_tool, "SKILLS_DIR", tmp_path)
        skills_tool.SKILLS_SCOPE_CTX.set({"open_skill"})
        result = json.loads(skills_tool.skill_view("open_skill"))
        assert result.get("success") is True
        skills_tool.SKILLS_SCOPE_CTX.set(None)


class TestComputeUserSkillScope:
    """AgentForge 侧可见集计算。"""

    class FakeConn:
        def __init__(self, rows):
            self._rows = rows

        def execute(self, sql, params):
            class Cur:
                def fetchall(self):
                    return self.rows
            return Cur()

        def close(self):
            pass

    def test_admin_returns_full(self, monkeypatch):
        # 模块路径已迁移：backend.service.permission_service → backend.service.auth.permission_service
        # （_compute_user_skill_scope 内部是延迟 import，patch 源模块即可生效）
        monkeypatch.setattr("backend.service.auth.permission_service.get_user_role", lambda uid: "super_admin")
        from backend.hermes_adapter import _compute_user_skill_scope
        assert _compute_user_skill_scope(1) is None

    def test_user_scope_composition(self, monkeypatch):
        monkeypatch.setattr("backend.service.auth.permission_service.get_user_role", lambda uid: "user")
        monkeypatch.setattr("backend.permission.checker.has_permission", lambda uid, perm: False)
        monkeypatch.setattr("backend.service.skill_service._meta_all", lambda: {
            "own_skill": {"owner_id": 5, "category": ""},
            "public_skill": {"owner_id": 1, "category": "其他"},
            "ai_skill": {"owner_id": 1, "category": "AI生成"},
            "other_user_skill": {"owner_id": 9, "category": ""},
        })

        class Cur:
            @staticmethod
            def fetchall():
                return [{"content_name": "pool_skill"}]

        class Conn:
            def execute(self, sql, params):
                return Cur()

            def close(self):
                pass

        monkeypatch.setattr("backend.db.schema.get_conn", lambda: Conn())
        from backend.hermes_adapter import _compute_user_skill_scope
        scope = _compute_user_skill_scope(5)
        assert "own_skill" in scope
        assert "public_skill" in scope
        assert "pool_skill" in scope
        assert "ai_skill" not in scope
        assert "other_user_skill" not in scope

    def test_failure_degrades_to_full(self, monkeypatch):
        def boom(uid):
            raise RuntimeError("db down")

        monkeypatch.setattr("backend.service.auth.permission_service.get_user_role", boom)
        from backend.hermes_adapter import _compute_user_skill_scope
        assert _compute_user_skill_scope(5) is None