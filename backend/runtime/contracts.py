"""Runtime Seam 契约（架构 §4.1）。

这是唯一允许业务模块见到执行引擎的地方；Hermes Adapter 实现此 Protocol，
测试替身（FakeRuntime）同样实现它。业务层不导入 backend.hermes 任何内部模块。
"""
from dataclasses import dataclass
from typing import AsyncIterator, Mapping, Protocol

from backend.shared.context import ExecutionContext

# 项目工具（时间/待办/提醒/账本/收件箱/编码受理等 LangChain 工具）的 toolset 标记。
# 内核没有自动包含机制——对话类 run 的 allowed_tools 需显式带上该组名，
# 且 Adapter 注册时经 create_custom_toolset 声明，schema 才会暴露给模型（P9 实测缺陷）。
ALWAYS_AVAILABLE_TOOLSET = "__always_available__"


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
