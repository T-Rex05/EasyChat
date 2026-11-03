"""
进程内 LRU 降级缓存 — Redis 不可用时的兜底方案。

设计原则：
- 线程安全（threading.Lock）
- TTL 惰性检查（get 时验证过期）
- LRU 淘汰（OrderedDict + move_to_end）
- 容量限制（maxsize 默认 1024）
"""
import threading
import time
from collections import OrderedDict
from typing import Optional


class FallbackCache:
    """
    进程内 LRU + TTL 缓存，用于 Redis 不可用时的降级。

    用法：
        cache = FallbackCache(maxsize=1024, default_ttl=300)
        cache.set("key", b"value", ttl=60)
        data = cache.get("key")
    """

    def __init__(self, maxsize: int = 1024, default_ttl: int = 300):
        """
        初始化降级缓存。

        Args:
            maxsize: 最大缓存条目数（LRU 淘汰）
            default_ttl: 默认 TTL（秒）
        """
        self._cache: OrderedDict = OrderedDict()  # key -> (value_bytes, expire_at)
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[bytes]:
        """
        获取缓存值（惰性 TTL 检查）。

        Returns:
            缓存的 bytes 数据，过期或不存在返回 None
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expire_at = self._cache[key]

            # TTL 检查
            if expire_at and time.time() > expire_at:
                del self._cache[key]
                self._misses += 1
                return None

            # 移动到末尾（LRU）
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: bytes, ttl: int = None):
        """
        设置缓存值。

        Args:
            key: 缓存键
            value: 缓存值（bytes）
            ttl: TTL（秒），None 使用默认值，0 表示不过期
        """
        with self._lock:
            expire_at = None
            actual_ttl = ttl if ttl is not None else self._default_ttl
            if actual_ttl > 0:
                expire_at = time.time() + actual_ttl

            # 更新或新增
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, expire_at)

            # LRU 淘汰
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def delete(self, key: str):
        """删除缓存条目。"""
        with self._lock:
            self._cache.pop(key, None)

    def delete_pattern(self, pattern: str):
        """
        按前缀模式删除缓存。

        Args:
            pattern: 前缀模式，如 "agentforge:model:*"
        """
        prefix = pattern.replace("*", "")
        with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_delete:
                self._cache.pop(k, None)

    def clear(self):
        """清空所有缓存。"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """
        获取缓存统计信息。

        Returns:
            包含 hits, misses, hit_rate, size, maxsize 的字典
        """
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
            "size": len(self._cache),
            "maxsize": self._maxsize,
            "backend": "memory",
        }
