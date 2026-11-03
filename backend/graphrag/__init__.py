# backend/graphrag/__init__.py
"""GraphRAG 知识图谱增强"""

from .types import (
    EntityType,
    RelationType,
    Entity,
    Relation,
    ExtractionResult,
    Subgraph,
    # Claim 相关
    ClaimType,
    ClaimStatus,
    Claim,
    ClaimExtractionResult,
    GraphWalkResult,
)
from .extractor import EntityExtractor, get_entity_extractor, ExtractionLLMError
from .kg_store import KGStore, get_kg_store

__all__ = [
    # 类型
    "EntityType",
    "RelationType",
    "Entity",
    "Relation",
    "ExtractionResult",
    "Subgraph",
    # Claim 相关
    "ClaimType",
    "ClaimStatus",
    "Claim",
    "ClaimExtractionResult",
    "GraphWalkResult",
    # 组件
    "EntityExtractor",
    "get_entity_extractor",
    "KGStore",
    "get_kg_store",
    # 异常
    "ExtractionLLMError",
]