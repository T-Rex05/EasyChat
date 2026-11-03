"""Hermes MemoryProvider 桥接：只调用 memory 公开接口。

不导入 Hermes 内部模块；后台旧 AgentForgeMemoryProvider/Dreaming 不在这里复活。
"""
from __future__ import annotations

from backend.modules.memory.contracts import MemoryCandidate, MemoryRecord
from backend.modules.memory.api import MemoryService
from backend.shared.context import Principal


class MemoryBridge:
    def __init__(self, memory: MemoryService, principal: Principal) -> None:
        self.memory = memory
        self.principal = principal

    def prefetch(self, query: str, *, budget: int | None = None) -> str:
        result = self.memory.recall(self.principal, query, token_budget=budget)
        if result.no_result:
            return "【记忆】无相关记忆"
        lines = ["【相关记忆】"]
        for index, item in enumerate(result.items, start=1):
            sources = ", ".join(f"{ref.kind}:{ref.ref}" for ref in item.memory.source_refs)
            lines.append(f"{index}. [{item.memory.kind}] {item.memory.content}")
            if sources:
                lines.append(f"   来源: {sources}")
        return "\n".join(lines)

    def remember(self, candidate: MemoryCandidate) -> MemoryRecord:
        return self.memory.remember(self.principal, candidate)
