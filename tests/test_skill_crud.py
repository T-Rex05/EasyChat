"""
技能 CRUD 服务测试

覆盖 create_skill, update_skill, delete_skill, list_skills, get_skill
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestSkillCRUD:
    """技能 CRUD 操作测试"""

    @pytest.fixture
    def temp_skills_dir(self):
        """创建临时技能目录"""
        temp_dir = tempfile.mkdtemp()
        # Mock skill_service 模块中的 _get_skills_dir 引用
        with patch('backend.service.skill_service._get_skills_dir') as mock_dir:
            mock_dir.return_value = Path(temp_dir)
            yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_db(self):
        """模拟数据库连接"""
        with patch('backend.db.schema.get_conn') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.execute.return_value = mock_cursor
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.__exit__ = MagicMock(return_value=None)
            yield mock_conn

    def test_create_skill_basic(self, temp_skills_dir, mock_db):
        """测试创建基础技能"""
        from backend.service.skill_service import create_skill

        result = create_skill(
            name="test-skill",
            content="# Test Skill\n\nThis is a test.",
            description="A test skill",
            author="tester",
            user_id=1
        )

        assert result["name"] == "test-skill"
        assert result["status"] == "approved"
        assert Path(temp_skills_dir, "test-skill", "SKILL.md").exists()

    def test_create_skill_with_category(self, temp_skills_dir, mock_db):
        """测试创建带分类的技能"""
        from backend.service.skill_service import create_skill

        result = create_skill(
            name="categorized-skill",
            content="# Categorized\n\nContent here.",
            category="engineering",
            user_id=1
        )

        assert Path(temp_skills_dir, "engineering", "categorized-skill", "SKILL.md").exists()

    def test_create_skill_duplicate_fails(self, temp_skills_dir, mock_db):
        """测试重复创建技能失败"""
        from backend.service.skill_service import create_skill

        create_skill(name="dup-skill", content="# Dup", user_id=1)

        with pytest.raises(FileExistsError, match="技能已存在"):
            create_skill(name="dup-skill", content="# Dup again", user_id=1)

    def test_create_skill_invalid_name(self, temp_skills_dir, mock_db):
        """测试创建技能名称不合法"""
        from backend.service.skill_service import create_skill

        with pytest.raises(ValueError, match="技能名称不合法"):
            create_skill(name="Invalid_Name!", content="# Bad", user_id=1)

    def test_create_skill_with_frontmatter(self, temp_skills_dir, mock_db):
        """测试创建带 frontmatter 的技能"""
        from backend.service.skill_service import create_skill

        content = """---
name: custom-skill
description: Custom description
author: custom-author
---

# Custom Skill

Body content.
"""
        result = create_skill(name="custom-skill", content=content, user_id=1)

        assert result["name"] == "custom-skill"
        skill_file = Path(temp_skills_dir, "custom-skill", "SKILL.md")
        assert skill_file.exists()
        assert "custom-author" in skill_file.read_text()

    def test_get_skill_exists(self, temp_skills_dir, mock_db):
        """测试获取存在的技能"""
        from backend.service.skill_service import create_skill, get_skill

        create_skill(
            name="get-test",
            content="# Get Test\n\nContent.",
            description="Test get",
            user_id=1
        )

        # 模拟数据库返回技能元数据
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "name": "get-test",
            "owner_id": 1,
            "category": "",
            "status": "approved",
            "locked": 0
        }
        mock_db.return_value.execute.return_value = mock_cursor

        result = get_skill("get-test", user_id=1)

        assert result["name"] == "get-test"
        assert result["description"] == "Test get"
        assert "# Get Test" in result["body"]

    def test_get_skill_not_exists(self, temp_skills_dir, mock_db):
        """测试获取不存在的技能"""
        from backend.service.skill_service import get_skill

        with pytest.raises(FileNotFoundError, match="技能不存在"):
            get_skill("nonexistent-skill", user_id=1)

    def test_list_skills_empty(self, temp_skills_dir, mock_db):
        """测试空技能列表"""
        from backend.service.skill_service import list_skills

        # Mock has_permission to return False for non-admin
        # Mock _query_all_skills to return empty list
        with patch('backend.permission.checker.has_permission', return_value=False):
            with patch('backend.service.skill_service._query_all_skills', return_value=[]):
                result = list_skills(user_id=1)

                assert result["my_skills"] == []
                # 普通用户没有 all_skills key，只有管理员才有
                assert "all_skills" not in result

    def test_list_skills_with_skills(self, temp_skills_dir, mock_db):
        """测试列出技能"""
        from backend.service.skill_service import create_skill, list_skills

        create_skill(name="skill-a", content="# A", user_id=1)
        create_skill(name="skill-b", content="# B", user_id=1)

        # 模拟数据库返回
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_db.return_value.execute.return_value = mock_cursor

        # Mock _query_all_skills to return the created skills
        mock_skills = [
            {"name": "skill-a", "owner_id": 1, "author": "user", "category": "", "status": "approved"},
            {"name": "skill-b", "owner_id": 1, "author": "user", "category": "", "status": "approved"},
        ]
        with patch('backend.service.skill_service._query_all_skills', return_value=mock_skills):
            result = list_skills(user_id=1)

            skill_names = [s["name"] for s in result["my_skills"]]
            assert "skill-a" in skill_names
            assert "skill-b" in skill_names

    def test_update_skill_owner(self, temp_skills_dir, mock_db):
        """测试所有者更新技能"""
        from backend.service.skill_service import create_skill, update_skill

        create_skill(name="update-test", content="# Old", user_id=1)

        # 模拟权限检查通过
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"name": "update-test", "owner_id": 1}
        mock_db.return_value.execute.return_value = mock_cursor

        result = update_skill(
            name="update-test",
            content="# New\n\nUpdated content.",
            user_id=1
        )

        assert result["name"] == "update-test"
        skill_file = Path(temp_skills_dir, "update-test", "SKILL.md")
        assert "# New" in skill_file.read_text()

    def test_update_skill_no_permission(self, temp_skills_dir, mock_db):
        """测试无权限更新技能"""
        from backend.service.skill_service import create_skill, update_skill

        create_skill(name="no-perm", content="# Original", user_id=1)

        # Mock _meta_get to return skill owned by user 1
        # Mock has_permission to return False (no skill.manage permission)
        with patch('backend.service.skill_service._meta_get', return_value={"owner_id": 1, "locked": 0}):
            with patch('backend.permission.checker.has_permission', return_value=False):
                # user_id=2 尝试更新
                with pytest.raises(ValueError, match="无权修改"):
                    update_skill(name="no-perm", content="# Hack", user_id=2)

    def test_delete_skill_owner(self, temp_skills_dir, mock_db):
        """测试所有者删除技能"""
        from backend.service.skill_service import create_skill, delete_skill

        create_skill(name="delete-test", content="# Delete me", user_id=1)

        # 模拟权限检查
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"name": "delete-test", "owner_id": 1}
        mock_db.return_value.execute.return_value = mock_cursor

        result = delete_skill("delete-test", user_id=1)

        # delete_skill 返回 bool
        assert result is True
        assert not Path(temp_skills_dir, "delete-test").exists()

    def test_delete_skill_not_exists(self, temp_skills_dir, mock_db):
        """测试删除不存在的技能"""
        from backend.service.skill_service import delete_skill

        with pytest.raises(FileNotFoundError, match="技能不存在"):
            delete_skill("ghost-skill", user_id=1)

    def test_delete_skill_no_permission(self, temp_skills_dir, mock_db):
        """测试无权限删除技能"""
        from backend.service.skill_service import create_skill, delete_skill

        create_skill(name="protected", content="# Protected", user_id=1)

        # Mock _meta_get to return skill owned by user 1
        # Mock has_permission to return False (no skill.manage permission)
        with patch('backend.service.skill_service._meta_get', return_value={"owner_id": 1, "locked": 0}):
            with patch('backend.permission.checker.has_permission', return_value=False):
                # user_id=2 尝试删除
                with pytest.raises(ValueError, match="无权删除"):
                    delete_skill("protected", user_id=2)

    def test_toggle_skill_status(self, temp_skills_dir, mock_db):
        """测试切换技能启用/禁用状态"""
        from backend.service.skill_service import create_skill, toggle_item_status

        create_skill(name="toggle-test", content="# Toggle", user_id=1)

        # 模拟数据库状态变化
        call_count = [0]
        
        def mock_fetchall():
            call_count[0] += 1
            # 第一次调用：技能存在且启用（enabled=1）
            # 第二次调用：技能已被禁用（enabled=0）
            if call_count[0] == 1:
                return [{"enabled": 1}]
            else:
                return [{"enabled": 0}]
        
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = mock_fetchall
        mock_db.return_value.execute.return_value = mock_cursor

        # 第一次切换：启用 → 禁用
        result1 = toggle_item_status("skill", "toggle-test")
        assert result1 is False  # 禁用
        
        # 第二次切换：禁用 → 启用
        result2 = toggle_item_status("skill", "toggle-test")
        assert result2 is True  # 启用
