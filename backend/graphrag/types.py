"""
GraphRAG 类型定义

定义实体、关系、知识图谱相关的数据结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EntityType(str, Enum):
    """实体类型"""
    PERSON = "person"           # 人物
    ORGANIZATION = "org"        # 组织/公司
    LOCATION = "location"       # 地点
    CONCEPT = "concept"         # 概念/主题
    EVENT = "event"             # 事件
    SKILL = "skill"             # 技能
    PREFERENCE = "preference"   # 偏好
    FACT = "fact"               # 事实
    PROJECT = "project"         # 项目
    TOOL = "tool"               # 工具
    OTHER = "other"             # 其他


class RelationType(str, Enum):
    """关系类型"""
    # 人物关系
    KNOWS = "knows"                     # 认识
    WORKS_WITH = "works_with"           # 共事
    REPORTS_TO = "reports_to"           # 汇报关系
    
    # 组织关系
    WORKS_AT = "works_at"               # 在...工作
    MEMBER_OF = "member_of"             # 是...成员
    FOUNDED = "founded"                 # 创立
    
    # 项目关系
    WORKS_ON = "works_on"               # 参与
    OWNS = "owns"                       # 负责
    USES = "uses"                       # 使用
    
    # 知识关系
    KNOWS_ABOUT = "knows_about"         # 了解
    EXPERT_IN = "expert_in"             # 专家
    LEARNED = "learned"                 # 学到
    
    # 偏好关系
    PREFERS = "prefers"                 # 偏好
    DISLIKES = "dislikes"               # 不喜欢
    
    # 因果关系
    CAUSED = "caused"                   # 导致
    DEPENDS_ON = "depends_on"           # 依赖
    
    # 时间关系
    HAPPENED_AFTER = "happened_after"   # 发生在...之后
    HAPPENED_BEFORE = "happened_before" # 发生在...之前
    
    # 其他
    RELATED_TO = "related_to"           # 相关
    PART_OF = "part_of"                 # 部分属于


@dataclass
class Entity:
    """
    实体定义

    表示知识图谱中的一个节点
    """
    id: str                                      # 唯一标识
    name: str                                    # 实体名称
    entity_type: EntityType                      # 实体类型
    description: str = ""                        # 描述
    aliases: List[str] = field(default_factory=list)  # 别名列表（如"阿里巴巴"的别名["阿里", "Alibaba"]）
    properties: Dict[str, Any] = field(default_factory=dict)  # 额外属性
    source_memory_id: Optional[int] = None       # 来源记忆ID（Memory 服务）
    source_document_id: Optional[int] = None     # 来源文档ID（KB 服务）
    source_chunk_id: Optional[int] = None        # 来源父片ID（KB 服务）
    confidence: float = 1.0                      # 提取置信度
    created_at: Optional[str] = None             # 创建时间
    updated_at: Optional[str] = None             # 更新时间
    deleted_at: Optional[str] = None             # 软删除时间（None 表示未删除）
    version: int = 1                             # 版本号（每次更新+1）
    # 冷热分离字段（P2 优化）
    last_accessed_at: Optional[str] = None       # 最后访问时间（用于冷热分离）
    access_count: int = 0                        # 访问次数（用于冷热分离）

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type.value,
            "group": self.entity_type.value,  # for vis.js compatibility
            "description": self.description,
            "aliases": self.aliases,
            "properties": self.properties,
            "source_memory_id": self.source_memory_id,
            "source_document_id": self.source_document_id,
            "source_chunk_id": self.source_chunk_id,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "version": self.version,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        """从字典创建"""
        return cls(
            id=data["id"],
            name=data["name"],
            entity_type=EntityType(data["entity_type"]),
            description=data.get("description", ""),
            aliases=data.get("aliases", []),
            properties=data.get("properties", {}),
            source_memory_id=data.get("source_memory_id"),
            source_document_id=data.get("source_document_id"),
            source_chunk_id=data.get("source_chunk_id"),
            confidence=data.get("confidence", 1.0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            deleted_at=data.get("deleted_at"),
            version=data.get("version", 1),
            last_accessed_at=data.get("last_accessed_at"),
            access_count=data.get("access_count", 0)
        )


@dataclass
class Relation:
    """
    关系定义

    表示知识图谱中的一条边
    """
    id: str                                      # 唯一标识
    source_id: str                               # 起始实体ID
    target_id: str                               # 目标实体ID
    relation_type: RelationType                  # 关系类型
    description: str = ""                        # 关系描述
    properties: Dict[str, Any] = field(default_factory=dict)  # 额外属性
    source_memory_id: Optional[int] = None       # 来源记忆ID（Memory 服务）
    source_document_id: Optional[int] = None     # 来源文档ID（KB 服务）
    source_chunk_id: Optional[int] = None        # 来源父片ID（KB 服务）
    confidence: float = 1.0                      # 提取置信度
    weight: float = 1.0                          # 关系权重
    created_at: Optional[str] = None             # 创建时间
    # 时间属性（P2+ 优化：区分"曾任职"和"任职"）
    valid_from: Optional[str] = None             # 生效时间（ISO 8601，如 "2018-01-01"）
    valid_until: Optional[str] = None            # 失效时间（null 表示当前有效）
    is_current: bool = True                      # 是否当前有效（默认 True）

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "description": self.description,
            "properties": self.properties,
            "source_memory_id": self.source_memory_id,
            "source_document_id": self.source_document_id,
            "source_chunk_id": self.source_chunk_id,
            "confidence": self.confidence,
            "weight": self.weight,
            "created_at": self.created_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "is_current": self.is_current
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Relation":
        """从字典创建"""
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation_type=RelationType(data["relation_type"]),
            description=data.get("description", ""),
            properties=data.get("properties", {}),
            source_memory_id=data.get("source_memory_id"),
            source_document_id=data.get("source_document_id"),
            source_chunk_id=data.get("source_chunk_id"),
            confidence=data.get("confidence", 1.0),
            weight=data.get("weight", 1.0),
            created_at=data.get("created_at"),
            valid_from=data.get("valid_from"),
            valid_until=data.get("valid_until"),
            is_current=data.get("is_current", True)
        )


@dataclass
class ExtractionResult:
    """
    提取结果

    LLM 从文本中提取的实体、关系和 Claim
    """
    entities: List[Entity] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    claims: List["Claim"] = field(default_factory=list)  # 新增：Claim 列表
    source_text: str = ""                       # 原始文本
    source_memory_id: Optional[int] = None      # 来源记忆ID
    source_document_id: Optional[int] = None    # 来源文档ID
    source_chunk_id: Optional[int] = None       # 来源父片ID
    extraction_time: float = 0.0                # 提取耗时（秒）
    model: str = ""                             # 使用的模型
    coverage_check: List[Dict[str, Any]] = field(default_factory=list)  # 关系完备性自检
    orphan_entities: List[str] = field(default_factory=list)            # 自检发现的孤立实体名

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "entities": [e.to_dict() for e in self.entities],
            "relations": [r.to_dict() for r in self.relations],
            "claims": [c.to_dict() for c in self.claims],
            "source_text": self.source_text,
            "source_memory_id": self.source_memory_id,
            "source_document_id": self.source_document_id,
            "source_chunk_id": self.source_chunk_id,
            "extraction_time": self.extraction_time,
            "model": self.model
        }


# ════════════════════════════════════════════════════════════
# Claim 类型定义（微软 GraphRAG Covariate）
# ════════════════════════════════════════════════════════════

class ClaimType(str, Enum):
    """Claim 类型"""
    FACT = "fact"           # 事实：有明确时间/地点/数据支撑
    OPINION = "opinion"     # 观点：人物观点或评价
    INFERENCE = "inference" # 推论：从上下文推断出的结论


class ClaimStatus(str, Enum):
    """Claim 状态"""
    ACTIVE = "active"           # 当前有效
    REFUTED = "refuted"         # 已被反驳
    SUPERSEDED = "superseded"   # 已被取代


@dataclass
class Claim:
    """
    Claim 定义

    从文本中提取的事实陈述（不同于实体和关系）

    示例：
        claim_text: "关羽在公元 219 年败走麦城"
        claim_type: fact
        subject: 关羽
        object: 麦城
        claim_value: 败走
        time: 公元 219 年
    """
    id: str                                      # 唯一标识 (claim_xxx)
    claim_type: ClaimType                        # Claim 类型
    claim_text: str                              # Claim 文本
    subject: str                                 # 主体实体名称
    object: Optional[str] = None                 # 客体实体名称（可选）
    claim_value: str = ""                        # Claim 值（如"败走"）
    time: Optional[str] = None                   # 时间属性
    confidence: float = 1.0                      # 置信度
    source_entity_id: Optional[str] = None       # 来源实体 ID
    source_chunk_id: Optional[int] = None        # 来源文本块 ID
    source_document_id: Optional[int] = None     # 来源文档 ID
    status: ClaimStatus = ClaimStatus.ACTIVE     # Claim 状态
    properties: Dict[str, Any] = field(default_factory=dict)  # 额外属性
    created_at: Optional[str] = None             # 创建时间
    updated_at: Optional[str] = None             # 更新时间

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "claim_type": self.claim_type.value,
            "claim_text": self.claim_text,
            "subject": self.subject,
            "object": self.object,
            "claim_value": self.claim_value,
            "time": self.time,
            "confidence": self.confidence,
            "source_entity_id": self.source_entity_id,
            "source_chunk_id": self.source_chunk_id,
            "source_document_id": self.source_document_id,
            "status": self.status.value,
            "properties": self.properties,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Claim":
        """从字典创建"""
        return cls(
            id=data.get("id", ""),
            claim_type=ClaimType(data.get("claim_type", "fact")),
            claim_text=data.get("claim_text", ""),
            subject=data.get("subject", ""),
            object=data.get("object"),
            claim_value=data.get("claim_value", ""),
            time=data.get("time"),
            confidence=data.get("confidence", 1.0),
            source_entity_id=data.get("source_entity_id"),
            source_chunk_id=data.get("source_chunk_id"),
            source_document_id=data.get("source_document_id"),
            status=ClaimStatus(data.get("status", "active")),
            properties=data.get("properties", {}),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ClaimExtractionResult:
    """
    Claim 提取结果

    LLM 从文本中提取的 Claim 列表
    """
    claims: List[Claim] = field(default_factory=list)
    source_text: str = ""
    source_chunk_id: Optional[int] = None
    source_document_id: Optional[int] = None
    extraction_time: float = 0.0
    model: str = ""

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "claims": [c.to_dict() for c in self.claims],
            "source_text": self.source_text,
            "source_chunk_id": self.source_chunk_id,
            "source_document_id": self.source_document_id,
            "extraction_time": self.extraction_time,
            "model": self.model,
        }


# ════════════════════════════════════════════════════════════
# 图遍历结果
# ════════════════════════════════════════════════════════════

@dataclass
class GraphWalkResult:
    """
    图遍历结果

    从某个中心实体出发，遍历 N 跳得到的所有实体和关系
    """
    nodes: List[Entity] = field(default_factory=list)      # 遍历到的实体
    edges: List[Relation] = field(default_factory=list)    # 遍历到的关系
    center_id: str = ""                                     # 中心实体 ID
    depth: int = 0                                          # 遍历深度

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "center_id": self.center_id,
            "depth": self.depth
        }

    def to_visjs_format(self) -> dict:
        """
        转换为 vis.js Network 格式

        Returns:
            {
                nodes: [{id, label, group, ...}],
                edges: [{from, to, label, ...}]
            }
        """
        nodes = []
        for entity in self.nodes:
            nodes.append({
                "id": entity.id,
                "label": entity.name,
                "group": entity.entity_type.value,
                "title": entity.description,
                "shape": self._get_node_shape(entity.entity_type),
                "color": self._get_node_color(entity.entity_type),
                **entity.properties
            })

        edges = []
        for relation in self.edges:
            edges.append({
                "id": relation.id or f"{relation.source_id}_{relation.target_id}",
                "from": relation.source_id,
                "to": relation.target_id,
                "label": relation.relation_type.value,
                "title": relation.description,
                "arrows": "to",
                "width": relation.weight,
                **relation.properties
            })

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _get_node_shape(entity_type: EntityType) -> str:
        """获取节点形状"""
        shapes = {
            EntityType.PERSON: "dot",
            EntityType.ORGANIZATION: "square",
            EntityType.LOCATION: "diamond",
            EntityType.CONCEPT: "triangle",
            EntityType.EVENT: "star",
            EntityType.SKILL: "hexagon",
            EntityType.PREFERENCE: "dot",
            EntityType.FACT: "triangle",
            EntityType.PROJECT: "box",
            EntityType.TOOL: "square",
            EntityType.OTHER: "dot"
        }
        return shapes.get(entity_type, "dot")

    @staticmethod
    def _get_node_color(entity_type: EntityType) -> str:
        """获取节点颜色"""
        colors = {
            EntityType.PERSON: "#4CAF50",       # 绿色
            EntityType.ORGANIZATION: "#2196F3", # 蓝色
            EntityType.LOCATION: "#FF9800",     # 橙色
            EntityType.CONCEPT: "#9C27B0",      # 紫色
            EntityType.EVENT: "#F44336",        # 红色
            EntityType.SKILL: "#00BCD4",        # 青色
            EntityType.PREFERENCE: "#E91E63",   # 粉色
            EntityType.FACT: "#795548",         # 棕色
            EntityType.PROJECT: "#3F51B5",      # 靛蓝
            EntityType.TOOL: "#607D8B",         # 灰色
            EntityType.OTHER: "#9E9E9E"         # 中灰
        }
        return colors.get(entity_type, "#9E9E9E")


# 兼容别名
Subgraph = GraphWalkResult


__all__ = [
    "EntityType",
    "RelationType",
    "Entity",
    "Relation",
    "ExtractionResult",
    "ClaimType",
    "ClaimStatus",
    "Claim",
    "ClaimExtractionResult",
    "GraphWalkResult",
    "Subgraph",
]