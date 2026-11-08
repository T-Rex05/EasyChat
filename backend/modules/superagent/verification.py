"""superagent 验证门禁（T4，方案 §6 验证与预算）。

- 验证命令来自 settings.verify_profile（管理员配置的 JSON 数组）；
- 命令在工作区根目录由控制端执行（不在代理会话内，防止代理伪造证据）；
- 每条命令记录：名称、命令、退出码、耗时、日志工件路径、head_sha；
- 全部 required 命令通过才算 verified；未配置验证按 allow_unverified_draft
  策略放行，但报告必须记录「验证缺失」证据。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.modules.superagent.workspaces import WorkspaceError

logger = logging.getLogger(__name__)

DEFAULT_VERIFY_TIMEOUT_SECONDS = 600.0
MAX_VERIFY_COMMANDS = 10


@dataclass(frozen=True, slots=True)
class VerifyCommand:
    name: str
    command: str
    timeout_seconds: float = DEFAULT_VERIFY_TIMEOUT_SECONDS
    required: bool = True


@dataclass(slots=True)
class VerifyResult:
    passed: bool
    configured: bool
    head_sha: str
    commands: list[dict] = field(default_factory=list)
    artifacts_dir: str = ""
    failure_reason: str = ""

    def summary_text(self) -> str:
        if not self.configured:
            return "未配置验证命令"
        lines = ["✅ " + c["name"] if c["exit_code"] == 0 else f"❌ {c['name']}（exit {c['exit_code']}）"
                 for c in self.commands]
        return "\n".join(lines)


def load_verify_commands(profile_json: str) -> list[VerifyCommand]:
    """解析并校验验证策略；损坏项跳过，总量限 10。"""
    try:
        data = json.loads(profile_json or "[]")
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    commands: list[VerifyCommand] = []
    for item in data[:MAX_VERIFY_COMMANDS]:
        if not isinstance(item, dict):
            continue
        command = str(item.get("command") or "").strip()
        if not command:
            continue
        commands.append(VerifyCommand(
            name=str(item.get("name") or command.split()[0])[:60],
            command=command,
            timeout_seconds=float(item.get("timeout_seconds") or DEFAULT_VERIFY_TIMEOUT_SECONDS),
            required=bool(item.get("required", True)),
        ))
    return commands


async def run_verification(
    *, commands: list[VerifyCommand], workspace: Path, artifacts_dir: Path,
    head_sha: str, git_runner, token: str = "",
) -> VerifyResult:
    """在控制端执行验证命令；git_runner 用于记录 head（验证前复核由 worker 负责）。"""
    configured = bool(commands)
    artifacts = Path(artifacts_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    result = VerifyResult(passed=configured, configured=configured,
                          head_sha=head_sha, artifacts_dir=str(artifacts))
    if not configured:
        result.failure_reason = "仓库未配置验证命令"
        return result
    for command in commands:
        started = time.monotonic()
        exit_code, output, timed_out = await _run_one(command, workspace, token)
        elapsed = round(time.monotonic() - started, 2)
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in command.name)[:40] or "step"
        log_path = artifacts / f"{safe_name}.log"
        try:
            log_path.write_text(
                f"$ {command.command}\n\n# exit={exit_code} elapsed={elapsed}s timed_out={timed_out}\n\n"
                + output,
                encoding="utf-8",
            )
        except OSError:
            logger.exception("验证日志写入失败 task_dir=%s", artifacts)
        record = {
            "name": command.name, "command": command.command, "exit_code": exit_code,
            "elapsed_seconds": elapsed, "timed_out": timed_out,
            "required": command.required, "log": log_path.name,
        }
        result.commands.append(record)
        if exit_code != 0 and command.required:
            result.passed = False
            result.failure_reason = (
                f"验证命令失败：{command.name}（exit {exit_code}"
                + ("，超时" if timed_out else "") + "）"
            )
            break
    return result


async def _run_one(command: VerifyCommand, workspace: Path, token: str) -> tuple[int, str, bool]:
    """单条命令执行；超时回收进程树。输出经过脱敏。"""
    from backend.modules.superagent.credentials import sanitize_text

    try:
        process = await asyncio.create_subprocess_shell(
            command.command,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        return 127, sanitize_text(f"无法启动验证命令: {exc}", tokens=(token,) if token else ()), False
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=command.timeout_seconds)
    except asyncio.TimeoutError:
        await _terminate_tree(process)
        return 124, "验证命令超时被终止", True
    text = stdout.decode("utf-8", "replace")
    tail = text[-20000:]
    return int(process.returncode or 0), sanitize_text(tail, tokens=(token,) if token else ()), False


async def _terminate_tree(process: asyncio.subprocess.Process) -> None:
    """尽力而为回收进程树（Windows 用 taskkill /T；POSIX 先 terminate 再 kill）。"""
    import sys

    if process.returncode is not None:
        return
    try:
        if sys.platform == "win32":
            kill = await asyncio.create_subprocess_exec(
                "taskkill", "/T", "/F", "/PID", str(process.pid),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(kill.wait(), timeout=15)
        else:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            process.kill()
    except Exception:  # noqa: BLE001
        logger.exception("验证进程树回收失败 pid=%s", process.pid)


def workspace_within(workspace: Path, expected: Path) -> bool:
    """双保险：验证执行前确认 cwd 未漂移。"""
    try:
        return Path(workspace).resolve() == Path(expected).resolve()
    except (OSError, WorkspaceError):
        return False
