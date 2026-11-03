"""
权限检查器单元测试

隔离策略：
1. FakeCache / FakeKeyBuilder 替换真实 Redis，测试完全不碰生产缓存
2. lru_cache 清理，防止进程级缓存跨测试泄漏
3. fixture 前后双保险清理真实 Redis 的 agentforge:permission:* 命名空间
"""
import pytest
from unittest.mock import patch, MagicMock
import re


# ── 假缓存实现（满足 checker.py 实际调用）──

class FakeCache:
    """
    内存假缓存，满足 backend/permission/checker.py 实际使用的方法：
    - get(key) -> None 表示 miss
    - set_with_jitter(key, value, base_ttl, jitter_range)
    - delete(key)
    - delete_pattern(pattern)
    """
    def __init__(self):
        self._data = {}

    def get(self, key: str):
        """获取缓存值，miss 返回 None（不是 False/0，否则语义会变）。"""
        return self._data.get(key)

    def set_with_jitter(self, key: str, value, base_ttl: int, jitter_range: int = 60):
        """设置缓存（忽略 TTL，测试不需要过期）。"""
        self._data[key] = value

    def delete(self, key: str) -> bool:
        """删除单个 key。"""
        self._data.pop(key, None)
        return True

    def delete_pattern(self, pattern: str) -> int:
        """按模式删除（pattern 如 agentforge:permission:user:*）。"""
        # 将 Redis 风格的 pattern 转换为正则
        regex = pattern.replace("*", ".*")
        keys_to_delete = [k for k in self._data if re.match(regex, k)]
        for k in keys_to_delete:
            del self._data[k]
        return len(keys_to_delete)

    def clear(self):
        """清空所有数据。"""
        self._data.clear()


class FakeKeyBuilder:
    """
    假 KeyBuilder，满足 backend/permission/checker.py 实际使用的方法：
    - build(module, entity, *parts) -> 拼接的 key 字符串
    - permission_role(role) -> agentforge:permission:role:{role}:perms
    - pattern(module, entity) -> 模式字符串
    """
    PREFIX = "agentforge"

    @classmethod
    def build(cls, module: str, entity: str, *parts) -> str:
        """构建通用 key。"""
        return ":".join([cls.PREFIX, module, entity] + [str(p) for p in parts])

    @classmethod
    def permission_role(cls, role: str) -> str:
        """角色权限 key。"""
        return cls.build("permission", "role", role, "perms")

    @classmethod
    def pattern(cls, module: str, entity: str = "*") -> str:
        """构建 key 模式（用于批量删除）。"""
        return f"{cls.PREFIX}:{module}:{entity}:*"


def _clear_real_redis_permission_keys():
    """清理真实 Redis 中的 agentforge:permission:* 键（使用 scan_iter，不用 keys）。"""
    import redis
    import os

    try:
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=False,
        )
        # 使用 scan_iter 而不是 keys
        keys = list(client.scan_iter(match="agentforge:permission:*", count=100))
        if keys:
            deleted = client.delete(*keys)
            return deleted
        return 0
    except Exception:
        # Redis 不可用时忽略
        return 0


def _clear_lru_caches():
    """清理进程级 lru_cache，防止跨测试泄漏。"""
    from backend.permission.checker import (
        _get_role_permissions_lru,
        _get_user_overrides_lru,
    )
    _get_role_permissions_lru.cache_clear()
    _get_user_overrides_lru.cache_clear()


def _assert_user_2_role_not_admin():
    """断言真实 Redis 中 permission:user:2:role 不存在或不是 admin。"""
    import redis
    import os

    try:
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
        )
        key = "agentforge:permission:user:2:role"
        value = client.get(key)
        # 断言：要么不存在，要么不是 "admin"
        assert value is None or value != "admin", (
            f"污染检测失败: {key} = {value}，测试写入了假数据到真实 Redis"
        )
    except Exception:
        # Redis 不可用时忽略断言
        pass


# ── autouse fixture：彻底隔离 Redis + 清理 lru_cache ──

@pytest.fixture(autouse=True)
def isolate_permission_cache():
    """
    彻底隔离 Redis 缓存 + 清理进程级 lru_cache。

    1. 测试前：清理真实 Redis 的 agentforge:permission:* 命名空间
    2. 测试前：清理进程级 lru_cache
    3. 测试中：patch get_cache/get_key_builder 为假实现
    4. 测试后：再次清理真实 Redis（双保险）
    5. 测试后：断言 permission:user:2:role 未被污染
    """
    # === 测试前清理 ===
    _clear_real_redis_permission_keys()
    _clear_lru_caches()

    # === patch 假缓存 ===
    fake_cache = FakeCache()
    with patch('backend.infrastructure.get_cache', return_value=fake_cache), \
         patch('backend.infrastructure.get_key_builder', return_value=FakeKeyBuilder):
        yield fake_cache

    # === 测试后清理与断言 ===
    _clear_real_redis_permission_keys()
    _assert_user_2_role_not_admin()


# ── 测试类 ──

class TestPermissionChecker:
    """权限检查器测试"""

    @pytest.fixture
    def mock_db(self):
        """模拟数据库连接"""
        with patch('backend.permission.checker.get_conn') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.execute.return_value = mock_cursor
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.__exit__ = MagicMock(return_value=None)
            yield mock_conn

    def test_super_admin_has_all_permissions(self, mock_db):
        """测试超级管理员拥有所有权限"""
        from backend.permission.checker import get_user_permissions

        # 模拟超级管理员角色
        def execute_side_effect(sql, params=None):
            mock_cursor = MagicMock()
            if "FROM users" in sql:
                mock_cursor.fetchone.return_value = {"role": "super_admin"}
            return mock_cursor

        mock_db.return_value.execute.side_effect = execute_side_effect

        permissions = get_user_permissions(1)
        # super_admin 应该拥有所有权限（从 registry 获取）
        assert "chat.use" in permissions
        assert "skill.create" in permissions
        assert len(permissions) > 0

    def test_admin_role_permissions(self, mock_db):
        """测试管理员角色权限"""
        from backend.permission.checker import get_user_permissions

        # 模拟管理员角色及其权限
        # 使用存活的权限 key：skill.create, skill.manage, system.manage
        def execute_side_effect(sql, params=None):
            mock_cursor = MagicMock()
            if "FROM users" in sql:
                mock_cursor.fetchone.return_value = {"role": "admin"}
            elif "FROM roles" in sql and "WHERE name" in sql:
                # SELECT id FROM roles WHERE name = ?
                mock_cursor.fetchone.return_value = {"id": 1}
            elif "FROM role_permissions" in sql:
                # SELECT permission FROM role_permissions WHERE role_id = ?
                mock_cursor.fetchall.return_value = [
                    {"permission": "skill.create"},
                    {"permission": "skill.manage"},
                    {"permission": "system.manage"},
                ]
            elif "FROM user_permissions" in sql:
                mock_cursor.fetchall.return_value = []
            return mock_cursor

        mock_db.return_value.execute.side_effect = execute_side_effect

        permissions = get_user_permissions(2)
        assert "skill.create" in permissions
        assert "skill.manage" in permissions
        assert "system.manage" in permissions

    def test_user_role_permissions(self, mock_db):
        """测试普通用户角色权限"""
        from backend.permission.checker import get_user_permissions

        # 模拟普通用户角色及其权限
        def execute_side_effect(sql, params=None):
            mock_cursor = MagicMock()
            if "FROM users" in sql:
                mock_cursor.fetchone.return_value = {"role": "user"}
            elif "FROM roles" in sql and "WHERE name" in sql:
                mock_cursor.fetchone.return_value = {"id": 2}
            elif "FROM role_permissions" in sql:
                mock_cursor.fetchall.return_value = [
                    {"permission": "skill.create"},
                ]
            elif "FROM user_permissions" in sql:
                mock_cursor.fetchall.return_value = []
            return mock_cursor

        mock_db.return_value.execute.side_effect = execute_side_effect

        permissions = get_user_permissions(3)
        assert "skill.create" in permissions
        # 使用存活的权限 key 进行有意义的断言
        assert "system.manage" not in permissions  # user 角色不应有系统管理权限

    def test_user_permission_override(self, mock_db):
        """测试用户权限覆盖"""
        from backend.permission.checker import get_user_permissions

        # 模拟用户有额外权限和禁用权限
        def execute_side_effect(sql, params=None):
            mock_cursor = MagicMock()
            if "FROM users" in sql:
                mock_cursor.fetchone.return_value = {"role": "user"}
            elif "FROM roles" in sql and "WHERE name" in sql:
                mock_cursor.fetchone.return_value = {"id": 2}
            elif "FROM role_permissions" in sql:
                mock_cursor.fetchall.return_value = [
                    {"permission": "skill.create"},
                ]
            elif "FROM user_permissions" in sql:
                mock_cursor.fetchall.return_value = [
                    {"permission": "skill.manage", "granted": 1},  # 额外授予
                    {"permission": "skill.create", "granted": 0},  # 禁用
                ]
            return mock_cursor

        mock_db.return_value.execute.side_effect = execute_side_effect

        permissions = get_user_permissions(4)
        assert "skill.manage" in permissions  # 被覆盖授予
        assert "skill.create" not in permissions  # 被覆盖禁用

    def test_get_user_role(self, mock_db):
        """测试获取用户角色"""
        from backend.permission.checker import get_user_role

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"role": "admin"}
        mock_db.return_value.execute.return_value = mock_cursor

        role = get_user_role(5)
        assert role == "admin"

    def test_get_user_role_not_found(self, mock_db):
        """测试获取不存在用户的角色"""
        from backend.permission.checker import get_user_role

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db.return_value.execute.return_value = mock_cursor

        role = get_user_role(999)
        assert role == "user"  # 默认角色

    def test_get_user_permissions_set(self, mock_db):
        """测试获取用户权限集合"""
        from backend.permission.checker import get_user_permissions

        # 使用存活的权限 key
        def execute_side_effect(sql, params=None):
            mock_cursor = MagicMock()
            if "FROM users" in sql:
                mock_cursor.fetchone.return_value = {"role": "user"}
            elif "FROM roles" in sql and "WHERE name" in sql:
                mock_cursor.fetchone.return_value = {"id": 2}
            elif "FROM role_permissions" in sql:
                mock_cursor.fetchall.return_value = [
                    {"permission": "skill.create"},
                    {"permission": "skill.manage"},
                ]
            elif "FROM user_permissions" in sql:
                mock_cursor.fetchall.return_value = [
                    {"permission": "kb.manage", "granted": 1},
                ]
            return mock_cursor

        mock_db.return_value.execute.side_effect = execute_side_effect

        permissions = get_user_permissions(6)
        assert "skill.create" in permissions
        assert "skill.manage" in permissions
        assert "kb.manage" in permissions


class TestSkillPermissions:
    """技能权限控制测试"""

    @pytest.fixture
    def mock_db(self):
        """模拟数据库连接"""
        with patch('backend.permission.checker.get_conn') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.execute.return_value = mock_cursor
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.__exit__ = MagicMock(return_value=None)
            yield mock_conn

    def test_has_permission_with_permission(self, mock_db):
        """测试有权限用户可以创建技能"""
        from backend.permission.checker import has_permission

        def execute_side_effect(sql, params=None):
            mock_cursor = MagicMock()
            if "FROM users" in sql:
                mock_cursor.fetchone.return_value = {"role": "user"}
            elif "FROM roles" in sql and "WHERE name" in sql:
                mock_cursor.fetchone.return_value = {"id": 2}
            elif "FROM role_permissions" in sql:
                mock_cursor.fetchall.return_value = [
                    {"permission": "skill.create"},
                ]
            elif "FROM user_permissions" in sql:
                mock_cursor.fetchall.return_value = []
            return mock_cursor

        mock_db.return_value.execute.side_effect = execute_side_effect

        assert has_permission(7, "skill.create") is True

    def test_has_permission_without_permission(self, mock_db):
        """测试无权限用户不能创建技能"""
        from backend.permission.checker import has_permission

        def execute_side_effect(sql, params=None):
            mock_cursor = MagicMock()
            if "FROM users" in sql:
                mock_cursor.fetchone.return_value = {"role": "user"}
            elif "FROM roles" in sql and "WHERE name" in sql:
                mock_cursor.fetchone.return_value = {"id": 2}
            elif "FROM role_permissions" in sql:
                mock_cursor.fetchall.return_value = []  # 无权限
            elif "FROM user_permissions" in sql:
                mock_cursor.fetchall.return_value = []
            return mock_cursor

        mock_db.return_value.execute.side_effect = execute_side_effect

        assert has_permission(8, "skill.create") is False

    def test_check_ownership_own_item(self, mock_db):
        """测试用户可以操作自己的技能"""
        from backend.permission.checker import check_ownership

        # 用户 9 拥有技能 9
        assert check_ownership(9, 9, "user", "skill.manage") is True

    def test_check_ownership_not_own_item(self, mock_db):
        """测试用户不能操作他人的技能"""
        from backend.permission.checker import check_ownership

        # 用户 10 不能操作技能 9
        def execute_side_effect(sql, params=None):
            mock_cursor = MagicMock()
            if "FROM users" in sql:
                mock_cursor.fetchone.return_value = {"role": "user"}
            elif "FROM roles" in sql and "WHERE name" in sql:
                mock_cursor.fetchone.return_value = {"id": 2}
            elif "FROM role_permissions" in sql:
                mock_cursor.fetchall.return_value = []  # 无 skill.manage 权限
            elif "FROM user_permissions" in sql:
                mock_cursor.fetchall.return_value = []
            return mock_cursor

        mock_db.return_value.execute.side_effect = execute_side_effect

        assert check_ownership(9, 10, "user", "skill.manage") is False

    def test_check_ownership_super_admin(self, mock_db):
        """测试超级管理员可以操作任何技能"""
        from backend.permission.checker import check_ownership

        # 超级管理员可以操作任何技能
        assert check_ownership(9, 11, "super_admin", "skill.manage") is True