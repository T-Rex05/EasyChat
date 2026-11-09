"""Runtime Seam 契约（架构 §4.1）。

这是唯一允许业务模块见到执行引擎的地方；Hermes Adapter 实现此 Protocol，
测试替身（FakeRuntime）同样实现它。业务层不导入 backend.hermes 任何内部模块。
"""
from dataclasses import dataclass
from typing import AsyncIterator, Mapping, Protocol

from backend.shared.context import ExecutionContext


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    context: ExecutionContext
    text: str
    attachment_ids: tuple[str, ...]
    system_context: str
    allowed_tools: frozenset[str]
    skill_versions: tuple[tuple[str, str], ...]
    persona_context: str = ""
    context_prefix: str = ""
    persist_user_message: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    kind: str
    payload: Mapping[str, object]


class ExecutionRuntime(Protocol):
    def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]: ...

    async def cancel(self, run_id: str) -> None: ...

    async def aclose(self) -> None: ...
