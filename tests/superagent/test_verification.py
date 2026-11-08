"""T3/T4 验证门禁与进程限时回归（真实子进程，离线快速）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.modules.superagent.verification import (
    VerifyCommand,
    load_verify_commands,
    run_verification,
)
from backend.modules.superagent.worker import _run_git


def test_load_verify_commands_parses_and_validates() -> None:
    profile = '[{"name":"pytest","command":"python -m pytest -q","timeout_seconds":120},{"command":"echo hi"},{"name":"bad"}]'
    commands = load_verify_commands(profile)
    assert len(commands) == 2  # 缺 command 的条目被丢弃
    assert commands[0].name == "pytest"
    assert commands[0].timeout_seconds == 120
    assert load_verify_commands("not-json") == []
    assert load_verify_commands('{"a":1}') == []  # 非 数组


async def test_verification_passes_and_writes_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    artifacts = tmp_path / "artifacts"
    commands = [VerifyCommand(name="ok", command=f'"{sys.executable}" -c "print(\'hello\')"')]
    result = await run_verification(
        commands=commands, workspace=workspace, artifacts_dir=artifacts,
        head_sha="a" * 40, git_runner=None, token="",
    )
    assert result.passed is True
    assert result.commands[0]["exit_code"] == 0
    log = (artifacts / "ok.log").read_text(encoding="utf-8")
    assert "hello" in log


async def test_verification_failure_stops_on_required(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    fail_cmd = f'"{sys.executable}" -c "import sys; sys.exit(3)"'
    commands = [
        VerifyCommand(name="bad", command=fail_cmd),
        VerifyCommand(name="after", command=f'"{sys.executable}" -c "print(1)"', required=False),
    ]
    result = await run_verification(
        commands=commands, workspace=workspace, artifacts_dir=tmp_path / "a2",
        head_sha="a" * 40, git_runner=None, token="",
    )
    assert result.passed is False
    assert "验证命令失败" in result.failure_reason
    assert result.commands[0]["exit_code"] == 3
    # required 失败后短路：后续命令未执行
    assert len(result.commands) == 1


async def test_verification_timeout_kills_process(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sleeper = f'"{sys.executable}" -c "import time; time.sleep(30)"'
    commands = [VerifyCommand(name="slow", command=sleeper, timeout_seconds=1.0)]
    result = await run_verification(
        commands=commands, workspace=workspace, artifacts_dir=tmp_path / "a3",
        head_sha="a" * 40, git_runner=None, token="",
    )
    assert result.passed is False
    assert result.commands[0]["timed_out"] is True
    assert result.commands[0]["exit_code"] == 124


async def test_run_git_missing_binary_raises(tmp_path: Path) -> None:
    """镜像缺 git 时给出明确错误（部署 readiness 契约）。
    （进程树限时回收由 verification 超时用例覆盖同一条 _terminate_tree 路径。）
    """
    import backend.modules.superagent.worker as worker_mod

    original = worker_mod.shutil.which
    worker_mod.shutil.which = lambda name: None  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="git"):
            await _run_git(tmp_path, 5.0, (), {}, "status")
    finally:
        worker_mod.shutil.which = original  # type: ignore[method-assign]
