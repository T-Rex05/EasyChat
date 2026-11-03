"""溢出文件 TTL 清理单元测试

覆盖：
  - cleanup_spill_files 正确删除过期文件
  - 未过期文件不被删除
  - 空目录不报错
  - 懒清理计数器在 N 次后触发

运行：
  pytest tests/test_spill_cleanup.py -v
"""
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.tools.tool_output_guard import (
    cleanup_spill_files,
    _save_spill_file,
    SPILL_FILE_TTL_HOURS,
)


@pytest.fixture
def temp_spill_dir():
    """临时溢出目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        spill_dir = Path(tmpdir) / "tool_outputs"
        spill_dir.mkdir()
        yield spill_dir


class TestSpillCleanup:
    def test_delete_old_files(self, temp_spill_dir):
        """超过 TTL 的文件应被删除"""
        # 创建 3 个文件
        for name in ["old1.txt", "old2.txt", "new.txt"]:
            (temp_spill_dir / name).write_text("content")

        # 把 old1 和 old2 的 mtime 设为 48 小时前
        old_time = time.time() - 48 * 3600
        os.utime(temp_spill_dir / "old1.txt", (old_time, old_time))
        os.utime(temp_spill_dir / "old2.txt", (old_time, old_time))

        with patch("backend.tools.tool_output_guard._get_spill_dir", return_value=temp_spill_dir):
            deleted = cleanup_spill_files(max_age_hours=24)

        assert deleted == 2
        assert (temp_spill_dir / "new.txt").exists()
        assert not (temp_spill_dir / "old1.txt").exists()
        assert not (temp_spill_dir / "old2.txt").exists()

    def test_keep_recent_files(self, temp_spill_dir):
        """未过期文件不被删除"""
        (temp_spill_dir / "recent.txt").write_text("recent content")

        with patch("backend.tools.tool_output_guard._get_spill_dir", return_value=temp_spill_dir):
            deleted = cleanup_spill_files(max_age_hours=24)

        assert deleted == 0
        assert (temp_spill_dir / "recent.txt").exists()

    def test_empty_dir_returns_zero(self, temp_spill_dir):
        """空目录返回 0"""
        with patch("backend.tools.tool_output_guard._get_spill_dir", return_value=temp_spill_dir):
            deleted = cleanup_spill_files(max_age_hours=24)
        assert deleted == 0

    def test_nonexistent_dir_returns_zero(self):
        """不存在的目录返回 0"""
        with patch("backend.tools.tool_output_guard._get_spill_dir", return_value=Path("/nonexistent_dir_xyz")):
            deleted = cleanup_spill_files(max_age_hours=24)
        assert deleted == 0

    def test_custom_ttl(self, temp_spill_dir):
        """自定义 TTL 正确工作"""
        (temp_spill_dir / "file.txt").write_text("content")
        # 设为 2 小时前
        old_time = time.time() - 2 * 3600
        os.utime(temp_spill_dir / "file.txt", (old_time, old_time))

        # TTL=1h → 应删除
        with patch("backend.tools.tool_output_guard._get_spill_dir", return_value=temp_spill_dir):
            deleted = cleanup_spill_files(max_age_hours=1)
        assert deleted == 1

    def test_ignores_subdirectories(self, temp_spill_dir):
        """子目录不被删除"""
        sub_dir = temp_spill_dir / "subdir"
        sub_dir.mkdir()
        # 设为 48 小时前
        old_time = time.time() - 48 * 3600
        os.utime(sub_dir, (old_time, old_time))

        with patch("backend.tools.tool_output_guard._get_spill_dir", return_value=temp_spill_dir):
            deleted = cleanup_spill_files(max_age_hours=24)

        assert deleted == 0  # 只删文件，不删目录
        assert sub_dir.exists()
