"""技能 toolset 依赖过滤 + session_search 用户作用域 单元测试"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "hermes"))


def _make_skill(tmp_path, name, requires=None):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    fm = f"---\nname: {name}\ndescription: {name}\n"
    if requires:
        fm += "metadata:\n  hermes:\n    requires_toolsets:\n"
        for ts in requires:
            fm += f"      - {ts}\n"
    fm += "---\n\nBody\n"
    (d / "SKILL.md").write_text(fm, encoding="utf-8")


class TestSkillToolsetFilter:
    """skills_list / skill_view 按 requires_toolsets 过滤（与提示词索引语义一致）。"""

    def test_denied_helper(self):
        from tools import skills_tool
        skills_tool._AGENTFORGE_AVAILABLE_TOOLSETS_CTX.set(None)
        assert skills_tool._agentforge_toolset_denied({"requires_toolsets": ["terminal"]}) is False
        skills_tool._AGENTFORGE_AVAILABLE_TOOLSETS_CTX.set({"web", "memory"})
        assert skills_tool._agentforge_toolset_denied({"requires_toolsets": ["web"]}) is False
        assert skills_tool._agentforge_toolset_denied({"requires_toolsets": ["terminal"]}) is True
        assert skills_tool._agentforge_toolset_denied({"requires_toolsets": ["web", "terminal"]}) is True
        assert skills_tool._agentforge_toolset_denied({"requires_toolsets": []}) is False
        skills_tool._AGENTFORGE_AVAILABLE_TOOLSETS_CTX.set(None)

    def test_find_all_skills_filters_by_toolset(self, tmp_path, monkeypatch):
        from tools import skills_tool
        monkeypatch.setattr(skills_tool, "_skills_dir", lambda: tmp_path)
        monkeypatch.setattr("agent.skill_utils.get_external_skills_dirs", lambda: [])
        _make_skill(tmp_path, "needs_terminal", requires=["terminal"])
        _make_skill(tmp_path, "needs_web", requires=["web"])
        skills_tool._SKILLS_CACHE.clear()
        skills_tool._AGENTFORGE_AVAILABLE_TOOLSETS_CTX.set({"web", "memory", "utility"})
        names = [s["name"] for s in skills_tool._find_all_skills()]
        assert "needs_web" in names
        assert "needs_terminal" not in names
        # 未设置上下文 → 全量（原生行为）
        skills_tool._SKILLS_CACHE.clear()
        skills_tool._AGENTFORGE_AVAILABLE_TOOLSETS_CTX.set(None)
        names_full = [s["name"] for s in skills_tool._find_all_skills()]
        assert "needs_terminal" in names_full
        skills_tool._SKILLS_CACHE.clear()

    def test_skill_view_rejects_missing_toolset(self, tmp_path, monkeypatch):
        from tools import skills_tool
        _make_skill(tmp_path, "needs_terminal", requires=["terminal"])
        monkeypatch.setattr(skills_tool, "_skills_dir", lambda: tmp_path)
        monkeypatch.setattr(skills_tool, "SKILLS_DIR", tmp_path)
        monkeypatch.setattr("agent.skill_utils.get_external_skills_dirs", lambda: [])
        skills_tool._AGENTFORGE_AVAILABLE_TOOLSETS_CTX.set({"web"})
        result = json.loads(skills_tool.skill_view("needs_terminal"))
        assert result.get("success") is False
        assert "requires toolsets" in result.get("error", "")
        skills_tool._AGENTFORGE_AVAILABLE_TOOLSETS_CTX.set(None)


class TestSessionSearchScope:
    """session_search 用户作用域：只查自己的会话。"""

    def test_owned_helper(self):
        from tools import session_search_tool as sst
        sst.SESSION_SCOPE_CTX.set(5)
        assert sst._agentforge_session_owned("5_1699999999") is True
        assert sst._agentforge_session_owned("wx_5_openid") is True
        assert sst._agentforge_session_owned("6_1699999999") is False
        assert sst._agentforge_session_owned("wx_6_openid") is False
        sst.SESSION_SCOPE_CTX.set(None)
        assert sst._agentforge_session_owned("6_1699999999") is True  # 未设置 → 不限

    def test_scope_result_filters_foreign_sessions(self):
        from tools import session_search_tool as sst
        payload = json.dumps({
            "success": True,
            "mode": "discover",
            "count": 2,
            "results": [
                {"session_id": "5_111", "title": "mine"},
                {"session_id": "6_222", "title": "others"},
            ],
        }, ensure_ascii=False)
        sst.SESSION_SCOPE_CTX.set(5)
        data = json.loads(sst._agentforge_scope_result(payload))
        assert data["count"] == 1
        assert [r["session_id"] for r in data["results"]] == ["5_111"]
        sst.SESSION_SCOPE_CTX.set(None)

    def test_scope_result_unchanged_without_ctx(self):
        from tools import session_search_tool as sst
        payload = json.dumps({"success": True, "count": 1, "results": [{"session_id": "6_222"}]})
        sst.SESSION_SCOPE_CTX.set(None)
        data = json.loads(sst._agentforge_scope_result(payload))
        assert data["count"] == 1