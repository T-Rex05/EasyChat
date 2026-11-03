"""受限脚本 Runner 契约（Task 13）：输入只含 artifact 引用与显式能力，不传业务凭证。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

STATUS_EXIT = "exit"
STATUS_TIMEOUT = "timeout"
STATUS_DENIED = "denied"
STATUS_ERROR = "error"


@dataclass(frozen=True, slots=True)
class RunnerLimits:
    deadline_seconds: float = 30.0
    memory_mb: int = 256
    output_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if self.deadline_seconds <= 0 or self.deadline_seconds > 600:
            raise ValueError("deadline_seconds 必须在 (0, 600]")
        if self.memory_mb <= 0 or self.memory_mb > 2048:
            raise ValueError("memory_mb 必须在 (0, 2048]")
        if self.output_bytes <= 0:
            raise ValueError("output_bytes 必须为正")


@dataclass(frozen=True, slots=True)
class RunnerCapabilities:
    read_paths: tuple[str, ...] = ()
    write_paths: tuple[str, ...] = ()
    network_hosts: tuple[str, ...] = ()
    env_allow: tuple[str, ...] = ()

    @property
    def needs_network(self) -> bool:
        return bool(self.network_hosts)


@dataclass(frozen=True, slots=True)
class RunnerInput:
    artifact_version_id: str
    workspace_ref: str
    argv: tuple[str, ...]
    input_artifacts: tuple[str, ...] = ()
    limits: RunnerLimits = field(default_factory=RunnerLimits)
    capabilities: RunnerCapabilities = field(default_factory=RunnerCapabilities)


@dataclass(frozen=True, slots=True)
class RunnerResult:
    status: str
    exit_code: int = -1
    stdout_tail: str = ""
    stderr_tail: str = ""
    artifacts: tuple[str, ...] = ()
    duration_seconds: float = 0.0
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == STATUS_EXIT and self.exit_code == 0


class ScriptRunner(Protocol):
    capability: str

    async def run(self, request: RunnerInput) -> RunnerResult: ...
