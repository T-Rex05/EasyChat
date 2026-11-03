"""脚本 Runner Adapter：默认关闭；只有显式启用且通过隔离验收才可自动执行。

本文件不声称 AST/子进程等于安全隔离：真正的文件/网络/凭证边界必须由
操作系统或远程 Runner 落实。未验收环境只能生成/静态检查，不能执行。
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from backend.modules.evolution.runner_contracts import (
    STATUS_DENIED,
    STATUS_ERROR,
    STATUS_EXIT,
    STATUS_TIMEOUT,
    RunnerInput,
    RunnerResult,
)


class DisabledScriptRunner:
    """默认 Runner：明确 denied，不静默假装执行成功。"""

    capability = "disabled"

    async def run(self, request: RunnerInput) -> RunnerResult:
        return RunnerResult(
            status=STATUS_DENIED,
            reason="未配置通过隔离验收的脚本 Runner；自动执行保持关闭",
        )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


class LocalSubprocessRunner:
    """受限本地子进程（仅 Linux 显式启用）；不做虚假隔离承诺。

    约束：cwd 必须在工作区根内；读写路径必须在工作区/产物根内；拒绝网络
    能力（本地实现无法强制网络隔离）；环境变量只白名单；超时硬终止并回收。
    """

    capability = "local-subprocess-unverified"

    def __init__(self, *, workspace_root: Path, artifacts_root: Path, enabled: bool = False) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.artifacts_root = Path(artifacts_root).resolve()
        self.enabled = bool(enabled)

    async def run(self, request: RunnerInput) -> RunnerResult:
        if not self.enabled:
            return RunnerResult(status=STATUS_DENIED, reason="本地 Runner 未启用")
        if sys.platform != "linux":
            return RunnerResult(status=STATUS_DENIED, reason="本地受限 Runner 仅支持 Linux")
        if request.capabilities.needs_network:
            return RunnerResult(
                status=STATUS_DENIED,
                reason="本地 Runner 无法强制网络隔离，拒绝带网络能力的任务",
            )
        workspace = Path(request.workspace_ref)
        if not _inside(workspace, self.workspace_root):
            return RunnerResult(status=STATUS_DENIED, reason="工作目录越界")
        for raw in (*request.capabilities.read_paths, *request.capabilities.write_paths):
            if not _inside(Path(raw), self.workspace_root) and not _inside(
                Path(raw), self.artifacts_root
            ):
                return RunnerResult(status=STATUS_DENIED, reason=f"路径越界: {raw}")
        if not request.argv:
            return RunnerResult(status=STATUS_DENIED, reason="缺少 argv")

        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(workspace)}
        for key in request.capabilities.env_allow:
            if key in os.environ and key not in ("LLM_API_KEY", "SMTP_PASSWORD", "EASYCHAT_ENCRYPTION_SECRET"):
                env[key] = os.environ[key]

        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *request.argv, cwd=str(workspace), env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:
            return RunnerResult(status=STATUS_ERROR, reason=f"启动失败: {exc}")
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=request.limits.deadline_seconds,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return RunnerResult(
                status=STATUS_TIMEOUT, exit_code=-1,
                reason="执行超时，已硬终止",
                duration_seconds=time.monotonic() - started,
            )
        duration = time.monotonic() - started
        limit = request.limits.output_bytes
        return RunnerResult(
            status=STATUS_EXIT,
            exit_code=int(process.returncode or 0),
            stdout_tail=stdout[-limit:].decode("utf-8", "replace"),
            stderr_tail=stderr[-limit:].decode("utf-8", "replace"),
            duration_seconds=duration,
        )


def build_default_runner(settings: Any) -> Any:
    """只有显式启用且 Linux 时才构造本地 Runner；否则保持 disabled。"""
    if not getattr(settings, "script_runner_enabled", False):
        return DisabledScriptRunner()
    if sys.platform != "linux":
        return DisabledScriptRunner()
    if shutil.which("bwrap") is None:
        # 无 bubblewrap 等隔离能力时不启用本地执行
        return DisabledScriptRunner()
    return LocalSubprocessRunner(
        workspace_root=settings.artifacts_dir / "runner-workspace",
        artifacts_root=settings.artifacts_dir,
        enabled=True,
    )
