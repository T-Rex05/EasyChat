"""
基础设施管理器 - 统一管理 MySQL、Milvus、Neo4j、Redis 连接

设计原则:
- MySQL: 强依赖，不可用时抛出异常阻止启动
- Milvus: 可选，有 ChromaDB fallback
- Neo4j: 可选，不可用时静默跳过
- Redis: 可选，不可用时降级到进程内缓存
"""

import logging
from typing import Optional

from .status import InfrastructureStatus
from .milvus_client import MilvusClient
from .neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class InfrastructureManager:
    """
    基础设施管理器

    用法:
        manager = get_infrastructure()
        manager.initialize()

        if manager.milvus.is_available():
            manager.milvus.insert(...)

        if manager.neo4j.is_available():
            manager.neo4j.create_entity(...)

        if manager.is_cache_available():
            cache = manager.redis
            cache.set("key", "value")
    """

    def __init__(self):
        """初始化管理器（不立即连接）"""
        self._mysql_status = InfrastructureStatus.mysql_unavailable()
        self._milvus: Optional[MilvusClient] = None
        self._neo4j: Optional[Neo4jClient] = None
        self._initialized = False

    def initialize(self) -> InfrastructureStatus:
        """
        初始化所有基础设施连接

        Returns:
            整体状态（MySQL 强依赖，失败时 status=mysql_unavailable）
        """
        if self._initialized:
            return self.get_status()

        logger.info("Initializing infrastructure...")

        # 0. Redis - 可选，有 fallback（最先初始化，供后续组件使用）
        # 委托给 get_cache() 全局单例，避免多实例导致 stats/fallback 不一致
        try:
            from .redis_client import init_cache
            if init_cache():
                logger.info("Redis connected")
            else:
                logger.info("Redis unavailable, cache degraded to in-memory LRU")
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}")

        # 1. MySQL - 强依赖，失败则返回错误状态
        try:
            from backend.db.schema import get_conn
            conn = get_conn()
            try:
                cur = conn.execute("SELECT 1 AS ok")
                cur.fetchone()
                self._mysql_status = InfrastructureStatus.mysql_connected()
                logger.info("MySQL connected")
            finally:
                conn.close()
        except Exception as e:
            self._mysql_status = InfrastructureStatus.mysql_unavailable(str(e))
            logger.error(f"MySQL initialization failed: {e}")
            return self.get_status()

        # 2. Milvus - 可选，fallback 到 ChromaDB
        try:
            self._milvus = MilvusClient()
            if self._milvus.is_available():
                logger.info(f"Milvus connected: {self._milvus.status}")
            else:
                logger.info(f"Milvus unavailable: {self._milvus.status}, vector features degraded")
        except Exception as e:
            logger.warning(f"Milvus initialization failed: {e}")
            self._milvus = MilvusClient()  # 创建实例以获取 fallback 状态

        # 3. Neo4j - 可选，不可用时静默跳过
        try:
            self._neo4j = Neo4jClient()
            if self._neo4j.is_available():
                logger.info(f"Neo4j connected: {self._neo4j.status}")
            else:
                logger.info(f"Neo4j unavailable: {self._neo4j.status}, GraphRAG features disabled")
        except Exception as e:
            logger.warning(f"Neo4j initialization failed: {e}")
            self._neo4j = Neo4jClient()

        self._initialized = True
        return self.get_status()

    @property
    def milvus(self) -> MilvusClient:
        """获取 Milvus 客户端（自动重连）"""
        if self._milvus is None:
            self._milvus = MilvusClient()
        # 如果当前不可用，尝试重新连接
        elif not self._milvus.is_available():
            logger.info("Milvus connection lost, attempting to reconnect...")
            try:
                self._milvus = MilvusClient()
                if self._milvus.is_available():
                    logger.info("Milvus reconnected successfully")
            except Exception as e:
                logger.warning(f"Milvus reconnection failed: {e}")
        return self._milvus

    @property
    def neo4j(self) -> Neo4jClient:
        """获取 Neo4j 客户端（自动重连）"""
        if self._neo4j is None:
            self._neo4j = Neo4jClient()
        # 如果当前不可用，尝试重新连接
        elif not self._neo4j.is_available():
            logger.info("Neo4j connection lost, attempting to reconnect...")
            try:
                # 先关闭旧连接
                try:
                    self._neo4j.close()
                except Exception:
                    pass
                # 创建新连接
                self._neo4j = Neo4jClient()
                if self._neo4j.is_available():
                    logger.info("Neo4j reconnected successfully")
                else:
                    logger.warning("Neo4j reconnection still failed")
            except Exception as e:
                logger.warning(f"Neo4j reconnection failed: {e}")
        return self._neo4j

    @property
    def redis(self):
        """获取 Redis 客户端（委托给全局单例 get_cache()）"""
        from .redis_client import get_cache
        return get_cache()

    @property
    def mysql(self) -> bool:
        """MySQL 是否可用"""
        return self._mysql_status.mysql == "connected"

    def is_cache_available(self) -> bool:
        """Redis 缓存是否可用（connected 或 degraded 都算可用）"""
        from .redis_client import get_cache
        return get_cache().is_available

    def get_status(self) -> InfrastructureStatus:
        """获取整体状态"""
        milvus_status = "connected" if (self._milvus and self._milvus.is_available()) else "unavailable"
        neo4j_status = "connected" if (self._neo4j and self._neo4j.is_available()) else "unavailable"
        from .redis_client import get_cache
        redis_status = "connected" if get_cache().is_available else "degraded"

        return InfrastructureStatus(
            mysql=self._mysql_status.mysql,
            milvus=milvus_status,
            neo4j=neo4j_status,
            redis=redis_status
        )

    def close(self) -> None:
        """关闭所有连接"""
        if self._milvus:
            self._milvus.close()
        if self._neo4j:
            self._neo4j.close()
        from .redis_client import close_cache
        close_cache()
        self._initialized = False
        logger.info("Infrastructure connections closed")

    def is_memory_available(self) -> bool:
        """检查记忆系统是否可用（至少有 Milvus/ChromaDB）"""
        # 通过属性访问，确保自动初始化
        return self.milvus is not None and self.milvus.is_available()

    def is_graphrag_available(self) -> bool:
        """检查 GraphRAG 是否可用（需要 Neo4j），会主动尝试重连"""
        # 触发 neo4j 属性的自动重连逻辑
        client = self.neo4j
        return client is not None and client.is_available()


# 全局单例访问
_manager: Optional[InfrastructureManager] = None


def get_infrastructure() -> InfrastructureManager:
    """获取全局基础设施管理器实例"""
    global _manager
    if _manager is None:
        _manager = InfrastructureManager()
    return _manager


def init_infrastructure() -> InfrastructureStatus:
    """
    初始化基础设施（应用启动时调用）

    Returns:
        基础设施状态
    """
    manager = get_infrastructure()
    return manager.initialize()


def get_memory_client() -> Optional[MilvusClient]:
    """获取记忆存储客户端（向量库）"""
    manager = get_infrastructure()
    if manager.is_memory_available():
        return manager.milvus
    return None


def get_graph_client() -> Optional[Neo4jClient]:
    """获取图谱存储客户端"""
    manager = get_infrastructure()
    if manager.is_graphrag_available():
        return manager.neo4j
    return None


def get_redis_client():
    """获取 Redis 缓存客户端（委托给全局单例）"""
    from .redis_client import get_cache
    return get_cache()


# 兼容别名
InfrastructureManager.get_instance = staticmethod(get_infrastructure)