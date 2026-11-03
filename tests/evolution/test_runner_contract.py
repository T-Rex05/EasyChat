"""Runner 契约测试（Task 13）：默认关闭、能力/路径拒绝、假 Runner 流程。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.integrations.script_runner import (
    DisabledScriptRunner,
    LocalSubprocessRunner,
    build_default_runner,
)
from backend.modules.evolution.runner_contracts import (
    STATUS_DENIED,
    STATUS_EXIT,
    RunnerCapabilities,
    RunnerInput,
    RunnerLimits,
    RunnerResult,
)
from backend.platform.settings import default_settings


class FakeRunner:
    capability = "fake"

    def __init__(self) -> None:
        self.requests: list[RunnerInput] = []

    async def run(self, request: RunnerInput) -> RunnerResult:
        self.requests.append(request)
        return RunnerResult(status=STATUS_EXIT, exit_code=0, stdout_tail="ok")


def _input(**kw) -> RunnerInput:
    base = dict(
        artifact_version_id="skv_" + "0" * 32,
        workspace_ref=str(Path(".").resolve()),
        argv=("python", "main.py"),
    )
    base.update(kw)
    return RunnerInput(**base)


def test_limits_reject_unsafe_values():
    with pytest.raises(ValueError):
        RunnerLimits(deadline_seconds=0)
    with pytest.raises(ValueError):
        RunnerLimits(deadline_seconds=601)
    with pytest.raises(ValueError):
        RunnerLimits(memory_mb=4096)
    assert RunnerLimits().deadline_seconds == 30


async def test_default_runner_is_disabled_and_says_denied():
    runner = build_default_runner(default_settings())
    assert isinstance(runner, DisabledScriptRunner)
    result = await runner.run(_input())
    assert result.status == STATUS_DENIED
    assert "关闭" in result.reason


async def test_fake_runner_flow_carries_only_capabilities(tmp_path):
    runner = FakeRunner()
    request = _input(
        limits=RunnerLimits(deadline_seconds=5, output_bytes=1024),
        capabilities=RunnerCapabilities(read_paths=(str(tmp_path),)),
    )
    result = await runner.run(request)
    assert result.ok
    assert runner.requests[0].argv == ("python", "main.py")
    assert not hasattr(request, "api_key")
    assert not hasattr(request, "token")


async def test_local_runner_network_and_path_denied(tmp_path, monkeypatch):
    runner = LocalSubprocessRunner(
        workspace_root=tmp_path, artifacts_root=tmp_path / "artifacts", enabled=True,
    )
    # 在非 Linux 上先模拟平台，只验证拒绝路径，不真正执行
    monkeypatch.setattr("backend.integrations.script_runner.sys.platform", "linux")

    network = await runner.run(_input(
        workspace_ref=str(tmp_path), capabilities=RunnerCapabilities(network_hosts=("evil.example",)),
    ))
    assert network.status == STATUS_DENIED
    assert "网络" in network.reason

    outside = await runner.run(_input(
        workspace_ref=str(tmp_path.parent),
    ))
    assert outside.status == STATUS_DENIED
    assert "越界" in outside.reason

    read_outside = await runner.run(_input(
        workspace_ref=str(tmp_path),
        capabilities=RunnerCapabilities(read_paths=("/etc/passwd",)),
    ))
    assert read_outside.status == STATUS_DENIED


async def test_local_runner_disabled_by_default(tmp_path):
    runner = LocalSubprocessRunner(workspace_root=tmp_path, artifacts_root=tmp_path, enabled=False)
    result = await runner.run(_input(workspace_ref=str(tmp_path)))
    assert result.status == STATUS_DENIED
    if sys.platform != "linux":
        assert "仅支持 Linux" in result.reason or "未启用" in result.reason
