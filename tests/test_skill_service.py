"""技能服务单元测试"""
import pytest
from backend.service.skill_service import (
    _parse_frontmatter,
    _strip_frontmatter,
    _validate_name,
    _validate_subpath,
)


class TestParseFrontmatter:
    """测试 frontmatter 解析"""

    def test_parse_valid_frontmatter(self):
        """解析有效的 frontmatter"""
        content = """---
name: test-skill
description: A test skill
author: John Doe
version: 1.0.0
---

# Skill Content
"""
        result = _parse_frontmatter(content)
        assert result["name"] == "test-skill"
        assert result["description"] == "A test skill"
        assert result["author"] == "John Doe"
        assert result["version"] == "1.0.0"

    def test_parse_frontmatter_with_quotes(self):
        """解析带引号的 frontmatter"""
        content = """---
name: "quoted-name"
description: 'single-quoted'
---
"""
        result = _parse_frontmatter(content)
        assert result["name"] == "quoted-name"
        assert result["description"] == "single-quoted"

    def test_parse_no_frontmatter(self):
        """解析无 frontmatter 的内容"""
        content = "# Just a heading\n\nSome content"
        result = _parse_frontmatter(content)
        assert result == {}

    def test_parse_incomplete_frontmatter(self):
        """解析不完整的 frontmatter（缺少结束标记）"""
        content = """---
name: test
description: test
"""
        result = _parse_frontmatter(content)
        assert result == {}

    def test_parse_empty_frontmatter(self):
        """解析空的 frontmatter"""
        content = """---
---
"""
        result = _parse_frontmatter(content)
        assert result == {}

    def test_parse_frontmatter_with_colon_in_value(self):
        """解析值中包含冒号的 frontmatter"""
        content = """---
description: This is a test: with colon
---
"""
        result = _parse_frontmatter(content)
        assert result["description"] == "This is a test: with colon"


class TestStripFrontmatter:
    """测试移除 frontmatter"""

    def test_strip_valid_frontmatter(self):
        """移除有效的 frontmatter"""
        content = """---
name: test
description: test
---

# Main Content
"""
        result = _strip_frontmatter(content)
        assert "---" not in result
        assert "# Main Content" in result

    def test_strip_no_frontmatter(self):
        """移除无 frontmatter 的内容"""
        content = "# Just a heading\n\nSome content"
        result = _strip_frontmatter(content)
        assert result == content

    def test_strip_incomplete_frontmatter(self):
        """移除不完整的 frontmatter"""
        content = """---
name: test
description: test
"""
        result = _strip_frontmatter(content)
        assert result == content  # 不完整的 frontmatter 应该原样返回

    def test_strip_frontmatter_windows_line_endings(self):
        """移除 Windows 换行符的 frontmatter"""
        content = "---\r\nname: test\r\n---\r\n# Content"
        result = _strip_frontmatter(content)
        assert "---" not in result
        assert "# Content" in result


class TestValidateName:
    """测试技能名称验证"""

    def test_valid_name_lowercase(self):
        """验证有效的小写名称"""
        _validate_name("test-skill")  # 不应抛出异常

    def test_valid_name_with_numbers(self):
        """验证包含数字的有效名称"""
        _validate_name("skill-v2")  # 不应抛出异常

    def test_valid_name_with_underscores(self):
        """验证包含下划线的有效名称"""
        _validate_name("my_skill")  # 不应抛出异常

    def test_valid_name_with_dots(self):
        """验证包含点号的有效名称"""
        _validate_name("skill.v1")  # 不应抛出异常

    def test_invalid_name_uppercase(self):
        """验证无效的大写名称"""
        with pytest.raises(ValueError, match="技能名称不合法"):
            _validate_name("Test-Skill")

    def test_invalid_name_spaces(self):
        """验证无效的空格名称"""
        with pytest.raises(ValueError, match="技能名称不合法"):
            _validate_name("test skill")

    def test_invalid_name_special_chars(self):
        """验证无效的特殊字符名称"""
        with pytest.raises(ValueError, match="技能名称不合法"):
            _validate_name("test@skill")

    def test_invalid_name_starts_with_dash(self):
        """验证无效的以连字符开头的名称"""
        with pytest.raises(ValueError, match="技能名称不合法"):
            _validate_name("-test-skill")

    def test_invalid_name_empty(self):
        """验证无效的空名称"""
        with pytest.raises(ValueError, match="技能名称不合法"):
            _validate_name("")

    def test_invalid_name_too_long(self):
        """验证无效的过长名称（超过 64 字符）"""
        long_name = "a" * 65
        with pytest.raises(ValueError, match="技能名称不合法"):
            _validate_name(long_name)


class TestValidateSubpath:
    """测试子路径验证"""

    def test_valid_subpath_references(self):
        """验证有效的 references 子路径"""
        _validate_subpath("references/doc.md")  # 不应抛出异常

    def test_valid_subpath_templates(self):
        """验证有效的 templates 子路径"""
        _validate_subpath("templates/config.yaml")  # 不应抛出异常

    def test_valid_subpath_scripts(self):
        """验证有效的 scripts 子路径"""
        _validate_subpath("scripts/run.py")  # 不应抛出异常

    def test_valid_subpath_assets(self):
        """验证有效的 assets 子路径"""
        _validate_subpath("assets/image.png")  # 不应抛出异常

    def test_valid_subpath_examples(self):
        """验证有效的 examples 子路径"""
        _validate_subpath("examples/demo.py")  # 不应抛出异常

    def test_valid_nested_subpath(self):
        """验证有效的嵌套子路径"""
        _validate_subpath("references/subdir/doc.md")  # 不应抛出异常

    def test_invalid_subpath_parent_directory(self):
        """验证无效的父目录遍历"""
        with pytest.raises(ValueError, match="不允许路径遍历"):
            _validate_subpath("../outside/file.md")

    def test_invalid_subpath_root_level(self):
        """验证无效的根级文件"""
        with pytest.raises(ValueError, match="附属文件必须在以下目录之一"):
            _validate_subpath("file.md")

    def test_invalid_subpath_unknown_directory(self):
        """验证无效的未知目录"""
        with pytest.raises(ValueError, match="附属文件必须在以下目录之一"):
            _validate_subpath("unknown/file.md")
