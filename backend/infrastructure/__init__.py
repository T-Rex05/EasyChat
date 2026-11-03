# backend/infrastructure/__init__.py
"""基础设施管理器 - 统一管理 MySQL、Milvus、Neo4j、Redis 连接"""

from .status import InfrastructureStatus
from .milvus_client import MilvusClient
from .neo4j_client import Neo4jClient, Neo4jStatus
from .manager import (
    InfrastructureManager,
    get_infrastructure,
    init_infrastructure,
    get_memory_client,
    get_graph_client,
    get_redis_client,
)
from .redis_client import (
    RedisClient,
    KeyBuilder,
    get_cache,
    get_key_builder,
    init_cache,
    close_cache,
)
from .fallback_cache import FallbackCache
from .safe_executor import (
    go_safe,
    goSafe,
    safe_submit,
    safe_execute,
    SafeTask,
    publish_event_safe
)

__all__ = [
    # 状态
    "InfrastructureStatus",
    # 客户端
    "MilvusClient",
    "Neo4jClient",
    "Neo4jStatus",
    "RedisClient",
    "FallbackCache",
    # 管理器
    "InfrastructureManager",
    "get_infrastructure",
    "init_infrastructure",
    "get_memory_client",
    "get_graph_client",
    "get_redis_client",
    # 缓存
    "get_cache",
    "get_key_builder",
    "init_cache",
    "close_cache",
    "KeyBuilder",
    # 安全执行
    "go_safe",
    "goSafe",
    "safe_submit",
    "safe_execute",
    "SafeTask",
    "publish_event_safe",
]