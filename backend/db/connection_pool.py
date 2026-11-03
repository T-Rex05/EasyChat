"""
统一 MySQL 连接池 — 全局唯一，替代散落的 pymysql.connect()

使用 DBUtils.PooledDB 实现同步连接池，所有需要 MySQL 连接的模块统一从此获取。
连接池参数通过环境变量配置，默认值适合中小规模部署。

用法：
    from backend.db.connection_pool import get_pool_connection
    conn = get_pool_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
    finally:
        conn.close()   # 归还连接池，不是真正关闭
"""
import os
import threading
import time
import weakref
from typing import Optional, Set

from backend.utils.log_utils import log

logger = log

_pool = None
_pool_lock = threading.Lock()

# 活跃连接追踪（用于强制清理孤儿连接）
_active_connections: Set = set()
_active_connections_lock = threading.Lock()


def _build_pool():
    """根据环境变量构建连接池（惰性单例）。"""
    # 确保加载 .env（pytest 环境 conftest.py 加载太晚）
    from dotenv import load_dotenv
    load_dotenv()

    from dbutils.pooled_db import PooledDB
    import pymysql
    from pymysql.constants import CLIENT

    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE", "agentforge")

    mincached = int(os.getenv("DB_POOL_MIN", "2"))
    maxcached = int(os.getenv("DB_POOL_MAX", "10"))
    maxconnections = int(os.getenv("DB_POOL_MAX_CONN", "20"))

    pool = PooledDB(
        creator=pymysql,
        mincached=mincached,
        maxcached=maxcached,
        maxconnections=maxconnections,
        blocking=True,         # 池满时阻塞等待
        maxusage=None,         # 不限制单个连接复用次数
        setsession=[],         # 不执行额外 SET 命令
        ping=1,                # 每次获取连接时 ping 一次验证可用性
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        client_flag=CLIENT.MULTI_STATEMENTS,  # 支持批量 DDL（减少 init_db 网络往返）
    )
    logger.info(
        f"MySQL 连接池已创建: min={mincached}, max_cached={maxcached}, "
        f"max_conn={maxconnections}, db={database}@{host}:{port}"
    )
    return pool


def _get_pool():
    """获取连接池实例（线程安全惰性初始化）。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _build_pool()
    return _pool


def get_pool_connection(retries: int = 3, delay: float = 0.5, timeout: float = 30.0):
    """
    从连接池获取一个 MySQL 连接（带重试、超时和连接追踪）。

    返回 pymysql 连接对象，使用完毕后 conn.close() 归还给池。
    自带 DictCursor + autocommit=True，与原有散落代码行为一致。

    Args:
        retries: 最大重试次数，默认 3 次
        delay: 初始延迟秒数，每次重试递增（0.5s, 1.0s, 1.5s）
        timeout: 单次获取连接的超时秒数，默认 30s（防止无限阻塞）

    Returns:
        pymysql 连接对象

    Raises:
        TimeoutError: 获取连接超时
        Exception: 最后一次重试的异常（如果所有重试都失败）
    """
    last_error = None
    _pool_reset_done = False

    for attempt in range(retries):
        try:
            # 使用线程 + 超时机制，防止 DBUtils blocking=True 无限等待
            result_container = [None]
            error_container = [None]

            def _acquire():
                try:
                    result_container[0] = _get_pool().connection()
                except Exception as e:
                    error_container[0] = e

            acquire_thread = threading.Thread(target=_acquire, daemon=True)
            acquire_thread.start()
            acquire_thread.join(timeout=timeout)

            if acquire_thread.is_alive():
                # 超时：线程仍在运行
                raise TimeoutError(
                    f"获取数据库连接超时（{timeout}s）。"
                    f"连接池可能已耗尽，请检查是否有连接泄漏或增加 DB_POOL_MAX_CONN。"
                )

            if error_container[0]:
                raise error_container[0]

            conn = result_container[0]

            # 追踪活跃连接（用于强制清理孤儿连接）
            with _active_connections_lock:
                # 使用 weakref 避免阻止连接被垃圾回收
                _active_connections.add(weakref.ref(conn, _on_connection_gc))

            return conn

        except TimeoutError:
            raise  # 超时直接抛出，不重试
        except Exception as e:
            last_error = e
            logger.warning(f"获取 MySQL 连接失败 (尝试 {attempt + 1}/{retries}): {e}")
            # 首次失败后重置连接池（清空坏连接），仅重置一次避免雪崩
            if not _pool_reset_done:
                _pool_reset_done = True
                reset_pool()
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))  # 递增延迟

    raise last_error


def _on_connection_gc(ref):
    """连接被垃圾回收时的回调（从活跃集合移除）"""
    with _active_connections_lock:
        _active_connections.discard(ref)


def reset_pool():
    """
    重置连接池（用于测试或环境变量变更后）。

    会强制关闭所有活跃连接（孤儿连接清理），避免连接泄漏。

    ⚠️ 生产环境谨慎使用，会中断正在执行的查询。
    """
    global _pool, _active_connections

    with _pool_lock:
        # 1. 强制关闭所有活跃连接（孤儿连接清理）
        with _active_connections_lock:
            closed_count = 0
            for conn_ref in list(_active_connections):
                conn = conn_ref()  # 解引用
                if conn is not None:
                    try:
                        # 关闭底层 pymysql 连接
                        if hasattr(conn, '_conn') and conn._conn:
                            conn._conn.close()
                            closed_count += 1
                    except Exception as e:
                        logger.debug(f"强制关闭孤儿连接失败: {e}")
            _active_connections.clear()

            if closed_count > 0:
                logger.warning(f"[连接池] 强制关闭了 {closed_count} 个孤儿连接")

        # 2. 关闭连接池（空闲连接）
        if _pool is not None:
            try:
                _pool.close()
            except Exception as e:
                logger.debug(f"关闭连接池失败: {e}")
            _pool = None

        logger.info("MySQL 连接池已重置")


def get_pool_stats() -> Optional[dict]:
    """获取连接池状态信息（用于健康检查/监控）。"""
    pool = _get_pool()
    try:
        # DBUtils PooledDB 使用 _idle_cache 存储空闲连接
        idle_count = len(pool._idle_cache) if hasattr(pool, "_idle_cache") else None

        # 统计活跃连接数（排除已 GC 的）
        with _active_connections_lock:
            active_count = sum(1 for ref in _active_connections if ref() is not None)

        return {
            "mincached": int(os.getenv("DB_POOL_MIN", "2")),
            "maxcached": int(os.getenv("DB_POOL_MAX", "10")),
            "maxconnections": int(os.getenv("DB_POOL_MAX_CONN", "20")),
            "idle_connections": idle_count,
            "active_connections": active_count,
            "total_connections": (idle_count or 0) + active_count,
        }
    except Exception:
        return None
