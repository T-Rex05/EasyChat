"""真实 Linux Runner 隔离验收（integration，默认排除；未通过前自动执行保持关闭）。"""
from __future__ import annotations

import sys

import pytest

from backend.integrations.script_runner import LocalSubprocessRunner
from backend.modules.evolution.runner_contracts import RunnerInput, RunnerLimits

pytestmark = pytest.mark.integration


@pytest.mark.skipif(sys.platform != "linux", reason="仅 Linux 目标环境")
async def test_linux_runner_blocks_path_escape_and_timeout(tmp_path):
    runner = LocalSubprocessRunner(
        workspace_root=tmp_path / "ws", artifacts_root=tmp_path / "art", enabled=True,
    )
    (tmp_path / "ws").mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    denied = await runner.run(RunnerInput(
        artifact_version_id="skv_" + "0" * 32,
        workspace_ref=str(tmp_path / "ws"),
        argv=("sh", "-c", "cat ../outside.txt"),
        limits=RunnerLimits(deadline_seconds=2),
    ))
    assert denied.status in ("exit", "denied")
    # 真实隔离验收要求看不到凭证/越界文件；未接 bubblewrap 时此断言会失败，
    # 此时自动执行必须保持关闭，不能把本测试当作已通过。
    if denied.status == "exit":
        assert "secret" not in denied.stdout_tail

    timeout = await runner.run(RunnerInput(
        artifact_version_id="skv_" + "0" * 32,
        workspace_ref=str(tmp_path / "ws"),
        argv=("sh", "-c", "sleep 10"),
        limits=RunnerLimits(deadline_seconds=1),
    ))
    assert timeout.status == "timeout"
