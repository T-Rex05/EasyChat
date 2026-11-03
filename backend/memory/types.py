"""
Memory Types - 记忆系统数据类型

对齐 AGI-saber 的 Item 数据结构，支持：
- 分类标签
- 槽位暗示 (slot_hint)
- 图关联 (graph_node_id)
- 向量化 (embedding)
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class MemoryItem:
    """
    增强的记忆条目结构（对齐 AGI-saber Item）

    字段说明：
    - id: 数据库主键
    - content: 记忆内容
    - importance: 重要性分数 (0-1)
    - embedding: 向量化表示
    - created_at: 创建时间戳
    - last_accessed: 最后访问时间
    - category: 分类 (preference/fact/event/skill/conversation)
    - tags: 标签列表
    - slot_hint: 提示词槽位暗示（用于注入到特定 prompt 槽位）
    - score: 召回时计算的分数
    - graph_node_id: Neo4j 节点 ID（图增强）
    - user_id: 所属用户
    - layer: 记忆层级 (episodic/semantic)，用于删除时精确定位
    - access_count: 访问次数（用于智能遗忘公式）
    - is_user_pinned: 用户锁定标记（锁定后不参与自动衰减淘汰）
    """

    id: Optional[int] = None
    content: str = ""
    importance: float = 0.5
    embedding: Optional[List[float]] = None

    # 时间戳
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    # 分类与标签
    category: str = ""  # preference/fact/event/skill/conversation
    tags: List[str] = field(default_factory=list)
    slot_hint: str = ""

    # 召回分数
    score: float = 0.0

    # 图关联
    graph_node_id: Optional[str] = None

    # 用户归属
    user_id: Optional[int] = None

    # 记忆层级（episodic/semantic），用于删除时精确定位，避免删错层
    layer: Optional[str] = None

    # 智能遗忘因子
    access_count: int = 0
    is_user_pinned: bool = False

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "importance": self.importance,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "category": self.category,
            "tags": self.tags,
            "slot_hint": self.slot_hint,
            "score": self.score,
            "graph_node_id": self.graph_node_id,
            "user_id": self.user_id,
            "layer": self.layer,
            "access_count": self.access_count,
            "is_user_pinned": self.is_user_pinned,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryItem":
        """从字典创建"""
        return cls(
            id=data.get("id"),
            content=data.get("content", ""),
            importance=data.get("importance", 0.5),
            embedding=data.get("embedding"),
            created_at=data.get("created_at", time.time()),
            last_accessed=data.get("last_accessed", time.time()),
            category=data.get("category", ""),
            tags=data.get("tags", []),
            slot_hint=data.get("slot_hint", ""),
            score=data.get("score", 0.0),
            graph_node_id=data.get("graph_node_id"),
            user_id=data.get("user_id"),
            layer=data.get("layer"),
            access_count=data.get("access_count", 0),
            is_user_pinned=bool(data.get("is_user_pinned", False)),
        )


@dataclass
class ConsolidationResult:
    """
    合并结果（对齐 AGI-saber ConsolidationResult）
    
    用于跟踪合并操作的效果，并告知调用方需要同步到数据库的变更
    """
    
    deduped: int = 0       # 去重数量
    merged: int = 0        # 合并数量
    expired: int = 0       # 过期淘汰数量
    
    # 需要从数据库删除的 ID
    delete_from_db: List[int] = field(default_factory=list)
    
    # 与 delete_from_db 一一对应的 (id, layer) 元组列表
    # layer 为 None 表示调用方未能确定层级，由服务层推断
    # 之所以不复用 delete_from_db 的元素类型：filter_protected/delete_from_graph 等都要求 int
    delete_targets: List[Tuple[int, Optional[str]]] = field(default_factory=list)
    
    # 需要更新到数据库的条目
    update_in_db: List[MemoryItem] = field(default_factory=list)

    # 需要写入 memory_versions 表的旧版本记录
    # 每条: {"memory_id": int, "version": int, "content": str,
    #         "importance_score": float, "memory_type": str,
    #         "change_reason": str, "source_memory_id": Optional[int]}
    versions_to_save: List[dict] = field(default_factory=list)

    # 剩余记忆数量
    remaining: int = 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "deduped": self.deduped,
            "merged": self.merged,
            "expired": self.expired,
            "delete_from_db": self.delete_from_db,
            "delete_targets": self.delete_targets,
            "update_count": len(self.update_in_db),
            "versions_count": len(self.versions_to_save),
            "remaining": self.remaining
        }


@dataclass
class RecallFilter:
    """
    记忆召回过滤器（对齐 AGI-saber RecallFilter）
    
    支持多维度过滤召回
    """
    
    categories: List[str] = field(default_factory=list)
    require_tags: List[str] = field(default_factory=list)
    max_age_hours: int = 0
    min_score: float = 0.0
    top_k: int = 10


# 记忆类型常量
class MemoryCategory:
    """记忆分类常量"""
    
    PREFERENCE = "preference"   # 用户偏好
    FACT = "fact"               # 事实知识
    EVENT = "event"             # 事件记录
    SKILL = "skill"             # 技能知识
    CONVERSATION = "conversation"  # 对话摘要
    GENERAL = "general"         # 通用


# 默认合并配置
class ConsolidationConfig:
    """合并配置常量"""
    
    DECAY_RATE = 0.99           # 衰减率
    DEDUP_THRESHOLD = 0.95      # 去重阈值
    MERGE_THRESHOLD = 0.85      # 合并阈值
    TTL_DAYS = 30               # 生存期（天）
    MIN_IMPORTANCE = 0.1        # 最低重要性
    TRIGGER_THRESHOLD = 10      # 触发阈值（新增多少条后触发）
    INDEGREE_PROTECT = 3        # 图中心度保护阈值