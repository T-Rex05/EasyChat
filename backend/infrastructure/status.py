# backend/infrastructure/status.py
"""基础设施状态追踪"""
from dataclasses import dataclass


@dataclass
class InfrastructureStatus:
    """各服务连接状态

    状态值:
    - "disconnected": 未连接
    - "connected": 正常连接
    - "unavailable": 不可用（无配置或连接失败）
    - "degraded": 降级（如 Redis fallback 到本地缓存）
    - "chromadb-fallback": Milvus 降级到 ChromaDB
    """
    mysql: str = "disconnected"
    milvus: str = "disconnected"
    neo4j: str = "disconnected"
    redis: str = "disconnected"  # 新增 Redis 状态
    error: str = ""  # 错误信息

    # ========== 工厂方法 ==========

    @classmethod
    def mysql_connected(cls) -> "InfrastructureStatus":
        """MySQL 已连接"""
        return cls(mysql="connected")

    @classmethod
    def mysql_unavailable(cls, error: str = "") -> "InfrastructureStatus":
        """MySQL 不可用"""
        return cls(mysql="unavailable", error=error)

    @classmethod
    def milvus_connected(cls) -> "InfrastructureStatus":
        """Milvus 已连接"""
        return cls(milvus="connected")

    @classmethod
    def milvus_chromadb_fallback(cls) -> "InfrastructureStatus":
        """Milvus 降级到 ChromaDB"""
        return cls(milvus="chromadb-fallback")

    @classmethod
    def neo4j_connected(cls) -> "InfrastructureStatus":
        """Neo4j 已连接"""
        return cls(neo4j="connected")

    @classmethod
    def redis_connected(cls) -> "InfrastructureStatus":
        """Redis 已连接"""
        return cls(redis="connected")

    @classmethod
    def redis_degraded(cls) -> "InfrastructureStatus":
        """Redis 降级到本地缓存"""
        return cls(redis="degraded")

    @classmethod
    def all_connected(cls) -> "InfrastructureStatus":
        """所有服务已连接"""
        return cls(mysql="connected", milvus="connected", neo4j="connected", redis="connected")

    # ========== 检查方法 ==========

    def is_mysql_available(self) -> bool:
        """MySQL 是否可用（强依赖）"""
        return self.mysql == "connected"

    def is_milvus_available(self) -> bool:
        """Milvus 或降级方案是否可用"""
        return self.milvus in ("connected", "chromadb-fallback")

    def is_neo4j_available(self) -> bool:
        """Neo4j 是否可用"""
        return self.neo4j == "connected"

    def is_redis_available(self) -> bool:
        """Redis 是否可用（connected 或 degraded 都算可用）"""
        return self.redis in ("connected", "degraded")

    def to_dict(self) -> dict:
        """转换为字典（用于 API 返回）"""
        return {
            "mysql": self.mysql,
            "milvus": self.milvus,
            "neo4j": self.neo4j,
            "redis": self.redis,
        }