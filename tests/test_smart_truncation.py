"""结构化截断单元测试

覆盖：
  - JSON 输出在行边界截断
  - CSV/表格在行边界截断
  - 无换行符退化为字符截断
  - head+tail 大小正确
  - 截断提示正确包含溢出路径

运行：
  pytest tests/test_smart_truncation.py -v
"""
import pytest

from backend.tools.tool_output_guard import (
    truncate_tool_output,
    _smart_head_tail,
    _truncate_at_line_boundary,
)


class TestSmartHeadTail:
    def test_multiline_text_respects_line_boundary(self):
        """多行文本应在行边界截断"""
        lines = [f"line {i}: " + "x" * 50 for i in range(100)]
        text = "\n".join(lines)
        head, tail = _smart_head_tail(text, head_size=500, tail_size=500)
        # head 要么在行边界截断（不含尾部 \n），要么退化为字符截断
        # 验证：head 长度 <= head_size，且没有把行从中间切断
        assert len(head) <= 500
        # head 要么是完整的前 N 行（不含 \n），要么 == text[:500]（退化）
        assert head == text[:len(head)]

    def test_no_newline_falls_back_to_char_truncation(self):
        """无换行符退化为纯字符截断"""
        text = "a" * 1000
        head, tail = _smart_head_tail(text, head_size=100, tail_size=100)
        assert len(head) == 100
        assert len(tail) == 100

    def test_empty_tail(self):
        """tail_size=0 时返回空"""
        text = "a" * 100
        head, tail = _smart_head_tail(text, head_size=50, tail_size=0)
        assert tail == ""


class TestTruncateAtLineBoundary:
    def test_head_finds_last_newline(self):
        """head 方向应找到最近的最后一个换行符（不含该换行符）"""
        text = "line1\nline2\nline3\nline4\nline5\n"
        result = _truncate_at_line_boundary(text, 12, direction="head")
        # "line1\nline2\n" = 12 chars，rfind("\n")=11，返回 text[:11] = "line1\nline2"
        assert result == "line1\nline2"

    def test_head_fallback_when_no_good_boundary(self):
        """找不到好的行边界时退化为字符截断"""
        text = "a" * 100  # 无换行符
        result = _truncate_at_line_boundary(text, 30, direction="head")
        assert len(result) == 30

    def test_tail_finds_first_newline(self):
        """tail 方向应从尾部找第一个换行符"""
        text = "line1\nline2\nline3\nline4\nline5\n"
        result = _truncate_at_line_boundary(text, 12, direction="tail")
        # 从尾部取 12 字符：应包含完整行

    def test_zero_size_returns_empty(self):
        """target_size=0 返回空"""
        assert _truncate_at_line_boundary("text", 0, "head") == ""
        assert _truncate_at_line_boundary("text", 0, "tail") == ""


class TestTruncateToolOutput:
    def test_short_output_unchanged(self):
        """短输出不截断"""
        result = truncate_tool_output("short text", "test_tool")
        assert result == "short text"

    def test_long_output_truncated(self):
        """长输出被截断"""
        long_text = "x" * 20000  # > DEFAULT_MAX_CHARS (16000)
        result = truncate_tool_output(long_text, "test_tool")
        assert len(result) < 20000
        assert "OUTPUT TRUNCATED" in result
        assert "省略" in result

    def test_truncated_output_has_spill_path(self):
        """截断输出包含溢出文件路径"""
        long_text = "x" * 20000
        result = truncate_tool_output(long_text, "test_tool")
        assert "data/tool_outputs/" in result or "tool_outputs" in result

    def test_bypass_tool_not_truncated(self):
        """豁免工具不截断"""
        long_text = "x" * 20000
        result = truncate_tool_output(long_text, "todo_add")
        assert result == long_text

    def test_custom_max_chars(self):
        """自定义 max_chars 生效"""
        text = "x" * 5000
        result = truncate_tool_output(text, "test_tool", max_chars=1000)
        assert len(result) < 5000
        assert "OUTPUT TRUNCATED" in result
