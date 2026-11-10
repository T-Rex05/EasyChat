"""P4 回归：git 进程树回收原语的真实行为 + 超时路径（集成）。

test_terminate_tree 在默认定向套件运行（不起网络）；test_run_git_timeout 需要真实
git 对不可达地址的连接挂起，标记 integration 由维护全集排除、CI/手动包含运行。
"""
from __future__ import annotations

import asyncio
import sys
import time

import pytest

from backend.modules.superagent.worker import _run_git, _terminate_tree


async def test_terminate_tree_stops_process_and_blocks_late_side_effect(tmp_path):
    """_terminate_tree 必须真停止进程：30 秒后写 marker 的副作用不得发生。"""
    marker = tmp_path / "marker.txt"
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c",
        f"import time; time.sleep(1.5); open({str(marker)!r}, 'w').write('late')",
    )
    # 立即回收（此时 sleep 未到 marker 写入点）
    await _terminate_tree(process)
    assert process.returncode is not None, "回收后进程必须已退出（停止证据）"
    # 越过 marker 写入时刻再检查：无残留子进程完成任务
    await asyncio.sleep(2.5)
    assert not marker.exists(), "进程树回收失败：marker 被晚到子进程写出"


@pytest.mark.integration
async def test_run_git_timeout_raises_after_terminating(tmp_path):
    """真实 git 对 RFC5737 不可达地址挂起 → 超时抛错并回收（>1s 内返回）。"""
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="超时"):
        await _run_git(
            tmp_path, 1.0, ("clone",), {},
            "https://203.0.113.1/easychat-probe.git", str(tmp_path / "dst"),
        )
    assert time.monotonic() - start < 30, "超时链路必须远早于 TCP 自然超时"
