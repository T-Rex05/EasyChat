# backend/memory/__init__.py
"""
AgentForge 记忆系统 - Hermes MemoryProvider 实现

组件：
- AgentForgeMemoryProvider: Hermes MemoryProvider 接口实现
- MemoryItem: 增强的记忆条目数据结构
- ConsolidationResult: 合并结果
- GraphMemory: 图增强层
- MemoryConsolidator: 三阶段合并器
"""

from .agentforge_provider import AgentForgeMemoryProvider
from .types import (
    MemoryItem,
    ConsolidationResult,
    RecallFilter,
    MemoryCategory,
    ConsolidationConfig
)
from .graph_memory import GraphMemory, get_graph_memory
from .consolidator import MemoryConsolidator, get_consolidator

__all__ = [
    # Provider
    "AgentForgeMemoryProvider",
    
    # Types
    "MemoryItem",
    "ConsolidationResult",
    "RecallFilter",
    "MemoryCategory",
    "ConsolidationConfig",
    
    # Graph enhancement
    "GraphMemory",
    "get_graph_memory",
    
    # Consolidation
    "MemoryConsolidator",
    "get_consolidator",
]