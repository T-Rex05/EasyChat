"""
Outbox Types - 记忆同步事件类型定义

Outbox 模式核心概念：
- 业务数据 + 同步事件在同一事务中提交
- 确保派生库（Milvus/Neo4j）的同步事件不会丢失
- Worker 可以幂等地消费事件，直到成功

版本号作用：
- 防止旧操作覆盖新状态
- 支持 incremental 对账
- 实现幂等写入
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(str, Enum):
    """事件类型"""
    # 向量库操作
    UPSERT_VECTOR = "upsert_vector"      # 新增/更新向量
    DELETE_VECTOR = "delete_vector"      # 删除向量

    # 图数据库操作
    UPSERT_GRAPH_NODE = "upsert_graph_node"      # 新增/更新图节点
    DELETE_GRAPH_NODE = "delete_graph_node"      # 删除图节点
    UPSERT_GRAPH_EDGE = "upsert_graph_edge"      # 新增/更新图边
    DELETE_GRAPH_EDGE = "delete_graph_edge"      # 删除图边

    # Redis 缓存操作
    INVALIDATE_CACHE = "invalidate_cache"  # 缓存失效


class Target(str, Enum):
    """目标库"""
    MILVUS = "milvus"
    NEO4J = "neo4j"
    REDIS = "redis"  # Redis 缓存


class EventStatus(str, Enum):
    """事件状态"""
    PENDING = "pending"          # 等待处理
    PROCESSING = "processing"    # 处理中
    PROCESSED = "processed"      # 已处理
    DEAD = "dead"                # 死信（超过最大重试次数）


@dataclass
class OutboxEvent:
    """Outbox 事件"""
    event_id: str
    memory_id: int
    memory_version: int
    event_type: EventType
    target: Target
    payload: Dict[str, Any]
    
    @classmethod
    def create(
        cls,
        memory_id: int,
        memory_version: int,
        event_type: EventType,
        target: Target,
        payload: Optional[Dict[str, Any]] = None
    ) -> "OutboxEvent":
        """创建新事件"""
        return cls(
            event_id=str(uuid.uuid4()),
            memory_id=memory_id,
            memory_version=memory_version,
            event_type=event_type,
            target=target,
            payload=payload or {}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "memory_id": self.memory_id,
            "memory_version": self.memory_version,
            "event_type": self.event_type.value,
            "target": self.target.value,
            "payload": self.payload
        }


@dataclass
class ConsolidationResult:
    """
    记忆合并结果（与 AGI-saber 对齐）
    
    consolidate 只改内存，返回此结构让调用方决定如何持久化。
    """
    deduped: int = 0                              # 去重数量
    merged: int = 0                               # 合并数量
    expired: int = 0                              # 过期淘汰数量
    delete_from_db: List[int] = field(default_factory=list)   # 需要从 DB 删除的 ID
    update_in_db: List[Dict[str, Any]] = field(default_factory=list)  # 需要在 DB 更新的条目


def compute_content_hash(
    content: str,
    memory_type: str,
    importance: float,
    extra: Optional[Dict[str, Any]] = None
) -> str:
    """
    计算内容哈希，用于对账
    
    哈希包含所有会影响派生投影的字段，便于快速判断是否需要同步。
    
    Args:
        content: 记忆内容
        memory_type: 记忆类型
        importance: 重要性分数
        extra: 额外字段（如 tags, category）
    
    Returns:
        32 字符的 SHA256 哈希
    """
    data = {
        "content": content,
        "memory_type": memory_type,
        "importance": round(importance, 4),  # 避免浮点精度问题
    }
    if extra:
        data.update(extra)
    
    data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode()).hexdigest()[:32]


def generate_repair_event_id(
    memory_id: int,
    event_type: EventType,
    target: Target
) -> str:
    """
    生成修复事件 ID（含时间片防重）

    使用固定格式 + 时间片确保同一修复可以重复创建（处理多次不一致）。
    INSERT IGNORE 配合此 ID 实现幂等写入。
    """
    import time
    return f"repair-{memory_id}-{event_type.value}-{target.value}-{int(time.time())}"


# 事件载荷模板
def make_vector_payload(
    content: str,
    memory_type: str,
    importance: float,
    user_id: int,
    **kwargs
) -> Dict[str, Any]:
    """构造向量同步事件载荷"""
    return {
        "content": content,
        "memory_type": memory_type,
        "importance": importance,
        "user_id": user_id,
        **kwargs
    }


def make_graph_payload(
    content: str,
    memory_type: str,
    importance: float,
    user_id: int,
    embedding: Optional[List[float]] = None,
    **kwargs
) -> Dict[str, Any]:
    """构造图同步事件载荷"""
    payload = {
        "content": content,
        "memory_type": memory_type,
        "importance": importance,
        "user_id": user_id,
        **kwargs
    }
    if embedding:
        # embedding 太大，只传是否存在
        payload["has_embedding"] = True
        payload["embedding_dim"] = len(embedding)
    return payload


def make_cache_invalidation_payload(
    cache_keys: Optional[List[str]] = None,
    cache_patterns: Optional[List[str]] = None,
    **kwargs
) -> Dict[str, Any]:
    """构造缓存失效事件载荷。

    Args:
        cache_keys: 精确匹配要失效的 key 列表
        cache_patterns: 模式匹配的 key 前缀列表（如 "agentforge:permission:user:*"）

    Returns:
        缓存失效载荷字典
    """
    return {
        "cache_keys": cache_keys or [],
        "cache_patterns": cache_patterns or [],
        **kwargs
    }