"""
Redis 缓存客户端 — 支持降级到进程内缓存 + Pub/Sub 多实例同步。

设计原则：
- 优雅降级：Redis 不可用时自动 fallback 到 FallbackCache
- 统一抽象：业务代码通过此模块访问缓存，不直接调用 redis-py
- Key 规范：agentforge:{module}:{entity}:{id} 命名空间
- 监控集成：缓存命中率统计，集成到 /health 端点
"""
import hashlib
import json
import logging
import os
import struct
import time
from typing import Any, Callable, Dict, List, Optional

from .fallback_cache import FallbackCache

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis 缓存客户端，支持降级到进程内缓存。

    用法：
        cache = get_cache()
        cache.set("key", {"data": "value"}, ttl=300)
        data = cache.get("key")

        # Embedding 向量
        cache.set_embedding("vec:123", [0.1, 0.2, ...], ttl=86400)
        vec = cache.get_embedding("vec:123")

        # Pub/Sub 多实例同步
        cache.publish_invalidation("agentforge:perm:*")
    """

    def __init__(self):
        """初始化 Redis 客户端（不立即连接）。"""
        self._client = None
        self._fallback = FallbackCache(maxsize=2048, default_ttl=300)
        self._available = False
        self._initialized = False
        self._last_reconnect_attempt = 0.0
        self._reconnect_interval = 30  # 秒
        self._hits = 0
        self._misses = 0
        self._pubsub_thread = None

    def initialize(self) -> bool:
        """
        初始化 Redis 连接。

        Returns:
            True 表示连接成功，False 表示降级到本地缓存
        """
        if self._initialized:
            return self._available

        try:
            import redis

            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            password = os.getenv("REDIS_PASSWORD", "") or None
            db = int(os.getenv("REDIS_DB", "0"))

            self._client = redis.Redis(
                host=host,
                port=port,
                password=password,
                db=db,
                socket_timeout=5,
                socket_connect_timeout=5,
                max_connections=20,
                decode_responses=False,  # 返回 bytes
                health_check_interval=30,
            )

            # 测试连接
            self._client.ping()
            self._available = True
            logger.info(f"✅ Redis connected: {host}:{port}/{db}")

        except ImportError:
            logger.warning(
                "⚠️ redis package not installed, cache degraded to in-memory LRU. "
                "Install with: pip install redis>=5.0.0"
            )
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed, cache degraded: {e}")

        self._initialized = True
        return self._available

    @property
    def is_available(self) -> bool:
        """检查 Redis 是否可用（自动尝试重连）。"""
        if not self._initialized:
            self.initialize()

        if not self._available and self._client is not None:
            now = time.time()
            if now - self._last_reconnect_attempt > self._reconnect_interval:
                self._last_reconnect_attempt = now
                try:
                    self._client.ping()
                    self._available = True
                    logger.info("✅ Redis reconnected")
                except Exception:
                    pass

        return self._available

    # ========== 核心 API ==========

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值（自动反序列化 JSON）。

        Args:
            key: 缓存键

        Returns:
            反序列化后的对象，miss 返回 None
        """
        if not self.is_available:
            raw = self._fallback.get(key)
            return self._deserialize(raw) if raw else None

        try:
            raw = self._client.get(key)
            if raw is None:
                self._misses += 1
                return None
            self._hits += 1
            return self._deserialize(raw)
        except Exception as e:
            logger.debug(f"Redis get failed: {e}")
            self._available = False
            # Fallback 不回填（避免不一致）
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        设置缓存值（自动序列化 JSON）。

        Args:
            key: 缓存键
            value: 要缓存的对象（dict/list/str/int 等）
            ttl: TTL（秒），0 表示不过期

        Returns:
            True 表示成功（包括降级模式）
        """
        serialized = self._serialize(value)

        # 总是写入 fallback（热备份）
        self._fallback.set(key, serialized, ttl)

        if not self.is_available:
            return True

        try:
            if ttl > 0:
                self._client.setex(key, ttl, serialized)
            else:
                self._client.set(key, serialized)
            return True
        except Exception as e:
            logger.warning(f"Redis set failed: {e}")
            self._available = False
            return False  # 明确返回失败，调用方可据此判断

    def delete(self, key: str) -> bool:
        """删除缓存条目。"""
        self._fallback.delete(key)

        if self.is_available:
            try:
                self._client.delete(key)
            except Exception as e:
                logger.debug(f"Redis delete failed: {e}")
                self._available = False

        return True

    def delete_pattern(self, pattern: str) -> int:
        """
        按模式批量删除缓存。

        Args:
            pattern: Redis 模式，如 "agentforge:model:*"

        Returns:
            删除的 key 数量
        """
        self._fallback.delete_pattern(pattern)

        if not self.is_available:
            return 0

        try:
            keys = list(self._client.scan_iter(match=pattern, count=100))
            if keys:
                return self._client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Redis delete_pattern failed: {e}")
            self._available = False
            return 0

    def exists(self, key: str) -> bool:
        """检查 key 是否存在。"""
        if not self.is_available:
            return self._fallback.get(key) is not None

        try:
            return bool(self._client.exists(key))
        except Exception:
            self._available = False
            return False

    # ========== 便捷方法 ==========

    def get_or_set(self, key: str, factory: Callable, ttl: int = 300) -> Any:
        """
        获取或设置缓存（cache-aside 模式）。

        Args:
            key: 缓存键
            factory: 缓存 miss 时的数据加载函数
            ttl: TTL（秒）

        Returns:
            缓存值或 factory() 的返回值
        """
        value = self.get(key)
        if value is not None:
            return value

        value = factory()
        if value is not None:
            self.set(key, value, ttl)
        return value

    def set_with_jitter(self, key: str, value: Any, base_ttl: int, jitter_range: int = 60):
        """
        设置缓存，TTL 加随机抖动（防雪崩）。

        Args:
            key: 缓存键
            value: 要缓存的对象
            base_ttl: 基础 TTL（秒）
            jitter_range: 抖动范围（±秒）
        """
        import random
        ttl = max(1, base_ttl + random.randint(-jitter_range, jitter_range))
        self.set(key, value, ttl)

    # ========== Embedding 向量专用 ==========

    def set_embedding(self, key: str, vector: List[float], ttl: int = 86400) -> bool:
        """
        存储 embedding 向量（float32 紧凑编码）。

        Args:
            key: 缓存键
            vector: embedding 向量（list of float）
            ttl: TTL（秒），默认 24h

        Returns:
            True 表示成功
        """
        # float32 紧凑编码，节省 50%+ 空间
        raw = struct.pack(f"{len(vector)}f", *vector)

        self._fallback.set(key, raw, ttl)

        if self.is_available:
            try:
                if ttl > 0:
                    self._client.setex(key, ttl, raw)
                else:
                    self._client.set(key, raw)
                return True
            except Exception as e:
                logger.debug(f"Redis set_embedding failed: {e}")
                self._available = False

        return True

    def get_embedding(self, key: str) -> Optional[List[float]]:
        """
        获取 embedding 向量。

        Args:
            key: 缓存键

        Returns:
            embedding 向量（list of float），miss 返回 None
        """
        if not self.is_available:
            raw = self._fallback.get(key)
            if raw is None:
                return None
            self._hits += 1
            return list(struct.unpack(f"{len(raw) // 4}f", raw))

        try:
            raw = self._client.get(key)
            if raw is None:
                self._misses += 1
                return None
            self._hits += 1
            return list(struct.unpack(f"{len(raw) // 4}f", raw))
        except Exception as e:
            logger.debug(f"Redis get_embedding failed: {e}")
            self._available = False
            return None

    # ========== Pub/Sub 多实例同步 ==========

    def publish_invalidation(self, pattern: str):
        """
        发布缓存失效事件（多实例同步）。

        Args:
            pattern: 要失效的 key 模式，如 "agentforge:perm:*"
        """
        if self.is_available:
            try:
                self._client.publish("cache:invalidate", pattern.encode("utf-8"))
                logger.debug(f"Published cache invalidation: {pattern}")
            except Exception as e:
                logger.debug(f"Redis publish failed: {e}")

    def subscribe_invalidation(self, callback: Callable[[str], None]):
        """
        订阅缓存失效事件（后台线程）。

        Args:
            callback: 收到失效事件时的回调函数，参数为 pattern
        """
        if not self.is_available:
            return

        def _listen():
            try:
                pubsub = self._client.pubsub()
                pubsub.subscribe("cache:invalidate")
                for message in pubsub.listen():
                    if message["type"] == "message":
                        pattern = message["data"].decode("utf-8")
                        try:
                            callback(pattern)
                        except Exception as e:
                            logger.warning(f"Invalidation callback failed: {e}")
            except Exception as e:
                logger.warning(f"Redis subscription ended: {e}")

        import threading
        self._pubsub_thread = threading.Thread(target=_listen, daemon=True)
        self._pubsub_thread.start()
        logger.info("✅ Redis Pub/Sub subscription started")

    # ========== 监控 ==========

    def stats(self) -> dict:
        """
        获取缓存统计信息。

        Returns:
            包含 hits, misses, hit_rate, backend 等信息的字典
        """
        if self.is_available:
            total = self._hits + self._misses
            try:
                mem = self._client.info("memory").get("used_memory_human", "N/A")
            except Exception:
                mem = "N/A"

            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
                "backend": "redis",
                "redis_memory": mem,
                "fallback": self._fallback.stats(),
            }

        return {
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "backend": "memory_degraded",
            "fallback": self._fallback.stats(),
        }

    def close(self):
        """关闭 Redis 连接。"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._available = False
        self._initialized = False
        logger.info("Redis connection closed")

    # ========== 内部方法 ==========

    @staticmethod
    def _serialize(value: Any) -> bytes:
        """序列化为 bytes（JSON）。"""
        if isinstance(value, bytes):
            return value
        return json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")

    @staticmethod
    def _deserialize(raw: bytes) -> Any:
        """从 bytes 反序列化。"""
        if raw is None or raw == b"":
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return raw  # 返回原始 bytes（如 embedding）


# ========== Key Builder ==========


class KeyBuilder:
    """
    缓存 Key 生成器，统一命名空间规范。

    Key 格式：agentforge:{module}:{entity}:{identifier}

    用法：
        kb = KeyBuilder()
        key = kb.model_config(42)  # "agentforge:model:config:42"
        pattern = kb.pattern("model", "configs")  # "agentforge:model:configs:*"
    """

    PREFIX = "agentforge"

    @classmethod
    def build(cls, module: str, entity: str, *parts) -> str:
        """构建通用 key。"""
        return ":".join([cls.PREFIX, module, entity] + [str(p) for p in parts])

    @classmethod
    def pattern(cls, module: str, entity: str = "*") -> str:
        """构建 key 模式（用于批量删除）。"""
        return f"{cls.PREFIX}:{module}:{entity}:*"

    # ========== 快捷工厂方法 ==========

    @classmethod
    def model_config(cls, config_id: int) -> str:
        """模型配置 key。"""
        return cls.build("model", "config", config_id)

    @classmethod
    def model_configs_by_category(cls, category: str) -> str:
        """按分类的模型配置列表 key。"""
        return cls.build("model", "configs", category)

    @classmethod
    def embedding(cls, text: str, model: str = "") -> str:
        """Embedding 向量 key（基于内容 hash）。"""
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return cls.build("embedding", model or "default", h)

    @classmethod
    def permission_user(cls, user_id: int) -> str:
        """用户权限 key。"""
        return cls.build("permission", "user", user_id, "perms")

    @classmethod
    def permission_role(cls, role: str) -> str:
        """角色权限 key。"""
        return cls.build("permission", "role", role, "perms")

    @classmethod
    def breaker_state(cls, model_name: str) -> str:
        """熔断器状态 key。"""
        return cls.build("gateway", "breaker", model_name)

    @classmethod
    def dashboard_stats(cls, user_id: int, days: int) -> str:
        """Dashboard 统计 key。"""
        return cls.build("trace", "dashboard", user_id, days)

    @classmethod
    def rerank_result(cls, query: str, items_hash: str) -> str:
        """Rerank 结果 key。"""
        qh = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
        return cls.build("rerank", "result", qh, items_hash)

    @classmethod
    def query_rewrite(cls, query: str) -> str:
        """查询改写结果 key。"""
        qh = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
        return cls.build("rewrite", "result", qh)

    @classmethod
    def memory_prefetch(cls, user_id: int, query_hash: str) -> str:
        """记忆 prefetch 结果 key。"""
        return cls.build("memory", "prefetch", user_id, query_hash)


# ========== 全局单例 ==========

_cache: Optional[RedisClient] = None
_keys = KeyBuilder()


def get_cache() -> RedisClient:
    """获取全局 Redis 客户端实例。"""
    global _cache
    if _cache is None:
        _cache = RedisClient()
    return _cache


def get_key_builder() -> KeyBuilder:
    """获取 Key 构建器实例。"""
    return _keys


def init_cache() -> bool:
    """初始化缓存（应用启动时调用）。"""
    return get_cache().initialize()


def close_cache():
    """关闭缓存连接（应用关闭时调用）。"""
    global _cache
    if _cache:
        _cache.close()
        _cache = None
