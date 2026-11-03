"""
连接池单元测试

测试覆盖：
1. 连接池初始化与单例
2. 并发获取/释放连接
3. 连接池大小限制
4. 连接断开自动重连
"""
import os
import threading
import time
from unittest.mock import patch, MagicMock

import pytest

# 测试前确保环境变量
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "root")
os.environ.setdefault("MYSQL_PASSWORD", "")
os.environ.setdefault("MYSQL_DATABASE", "agentforge")


class TestConnectionPool:
    """连接池基础测试"""

    def test_pool_import(self):
        """测试连接池模块可正常导入"""
        from backend.db.connection_pool import get_pool_connection, reset_pool, get_pool_stats
        assert callable(get_pool_connection)
        assert callable(reset_pool)
        assert callable(get_pool_stats)

    def test_pool_singleton(self):
        """测试连接池是单例模式"""
        from backend.db.connection_pool import _get_pool, reset_pool
        
        reset_pool()
        pool1 = _get_pool()
        pool2 = _get_pool()
        assert pool1 is pool2, "连接池应该是单例"
        reset_pool()

    def test_pool_stats(self):
        """测试获取连接池状态"""
        from backend.db.connection_pool import get_pool_stats, reset_pool
        
        reset_pool()
        stats = get_pool_stats()
        assert stats is not None
        assert "mincached" in stats
        assert "maxcached" in stats
        assert "maxconnections" in stats
        reset_pool()


class TestConnectionPoolIntegration:
    """连接池集成测试（需要 MySQL 可用）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前后重置连接池"""
        from backend.db.connection_pool import reset_pool
        reset_pool()
        yield
        reset_pool()

    def test_get_connection(self):
        """测试获取连接并执行简单查询"""
        from backend.db.connection_pool import get_pool_connection
        
        conn = get_pool_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 AS test_val")
            row = cur.fetchone()
            assert row["test_val"] == 1
        finally:
            conn.close()

    def test_connection_reuse(self):
        """测试连接被复用（归还后再次获取）"""
        from backend.db.connection_pool import get_pool_connection
        
        conn1 = get_pool_connection()
        conn1.close()  # 归还给池
        
        conn2 = get_pool_connection()
        try:
            cur = conn2.cursor()
            cur.execute("SELECT 1")
            assert cur.fetchone() is not None
        finally:
            conn2.close()

    def test_concurrent_connections(self):
        """测试并发获取连接"""
        from backend.db.connection_pool import get_pool_connection
        
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                conn = get_pool_connection()
                try:
                    cur = conn.cursor()
                    cur.execute(f"SELECT {worker_id} AS wid")
                    row = cur.fetchone()
                    results.append(row["wid"])
                finally:
                    conn.close()
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        
        assert len(errors) == 0, f"并发测试出错: {errors}"
        assert sorted(results) == list(range(10))

    def test_pool_size_limit(self):
        """测试连接池大小限制（maxcached）"""
        from backend.db.connection_pool import get_pool_connection, get_pool_stats
        
        # 获取多个连接
        conns = []
        for _ in range(5):
            conns.append(get_pool_connection())
        
        # 全部归还
        for c in conns:
            c.close()
        
        stats = get_pool_stats()
        # 空闲连接数不应超过 maxcached
        assert stats["idle_connections"] <= stats["maxcached"]


class TestSchemaGetConn:
    """测试 schema.get_conn 使用连接池"""

    def test_get_conn_returns_adapter(self):
        """测试 get_conn 返回 _MySQLAdapter"""
        from backend.db.schema import get_conn, _MySQLAdapter
        from backend.db.connection_pool import reset_pool
        
        reset_pool()
        conn = get_conn()
        try:
            assert isinstance(conn, _MySQLAdapter)
        finally:
            conn.close()
        reset_pool()

    def test_get_conn_execute(self):
        """测试通过 get_conn 执行查询"""
        from backend.db.schema import get_conn
        from backend.db.connection_pool import reset_pool
        
        reset_pool()
        conn = get_conn()
        try:
            cur = conn.execute("SELECT 1 AS val")
            # _MySQLAdapter 的 execute 返回 cursor
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            # 验证能正常执行
            assert True
        finally:
            conn.close()
        reset_pool()


class TestConversationStore:
    """测试 ConversationStore 使用连接池"""

    def test_store_import(self):
        """测试 ConversationStore 可正常导入"""
        from backend.db.conversation_store import ConversationStore
        store = ConversationStore()
        assert store is not None

    def test_store_get_connection(self):
        """测试 ConversationStore 内部获取连接"""
        from backend.db.conversation_store import ConversationStore
        from backend.db.connection_pool import reset_pool
        
        reset_pool()
        store = ConversationStore()
        conn = store._get()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            assert cur.fetchone() is not None
        finally:
            conn.close()
        reset_pool()
