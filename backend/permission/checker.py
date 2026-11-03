"""
权限检查器 — 计算用户的有效权限集合。

逻辑:
  1. super_admin → 返回 permission_defs 表中全部 key
  2. 查询角色 → 从 role_permissions 获取角色默认权限
  3. 查询 user_permissions → 用户级覆盖（granted=1 加, granted=0 减）
  4. 返回最终集合

性能优化：
- Redis 缓存：用户权限 5min，角色权限 30min
- Redis 不可用时降级到进程内 LRU 缓存
- 权限变更时主动失效（通过 invalidate_permission_cache）
"""
import json
from typing import List, Set
from functools import lru_cache
from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log


# ── 进程内 LRU 降级缓存（Redis 不可用时使用）──
@lru_cache(maxsize=256)
def _get_role_permissions_lru(role: str) -> frozenset:
    """角色权限 LRU 降级缓存。"""
    return _fetch_role_permissions(role)


@lru_cache(maxsize=256)
def _get_user_overrides_lru(user_id: int) -> tuple:
    """用户权限覆盖 LRU 降级缓存。"""
    return _fetch_user_overrides(user_id)


def _fetch_role_permissions(role: str) -> frozenset:
    """从数据库获取角色权限集合。"""
    conn = get_conn()
    try:
        role_row = conn.execute("SELECT id FROM roles WHERE name = %s", (role,)).fetchone()
        if not role_row:
            return frozenset()
        rows = conn.execute(
            "SELECT permission FROM role_permissions WHERE role_id = %s",
            (role_row["id"],),
        ).fetchall()
        return frozenset(r["permission"] for r in rows)
    finally:
        conn.close()


def _fetch_user_overrides(user_id: int) -> tuple:
    """从数据库获取用户权限覆盖。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT permission, granted FROM user_permissions WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        granted = tuple(r["permission"] for r in rows if r["granted"])
        revoked = tuple(r["permission"] for r in rows if not r["granted"])
        return (granted, revoked)
    finally:
        conn.close()


def _get_role_permissions(role: str) -> frozenset:
    """获取角色权限（带 Redis 缓存，降级到 LRU）。"""
    from backend.infrastructure import get_cache, get_key_builder
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.permission_role(role)

    # 尝试 Redis
    cached = cache.get(cache_key)
    if cached is not None:
        return frozenset(cached)

    # 缓存 miss，查数据库
    perms = _fetch_role_permissions(role)

    # 写入 Redis（30min TTL + 2min jitter）
    cache.set_with_jitter(cache_key, list(perms), base_ttl=1800, jitter_range=120)

    return perms


def _get_user_overrides(user_id: int) -> tuple:
    """获取用户权限覆盖（带 Redis 缓存，降级到 LRU）。"""
    from backend.infrastructure import get_cache, get_key_builder
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.build("permission", "user", user_id, "overrides")

    # 尝试 Redis
    cached = cache.get(cache_key)
    if cached is not None:
        # 修复：cached 是 [granted_list, revoked_list]，需要转换为 tuple of tuples
        granted, revoked = cached
        return (tuple(granted), tuple(revoked))

    # 缓存 miss，查数据库
    result = _fetch_user_overrides(user_id)

    # 写入 Redis（5min TTL + 30s jitter）
    cache.set_with_jitter(cache_key, list(result), base_ttl=300, jitter_range=30)

    return result


def _invalidate_permission_cache(user_id: int = None) -> None:
    """使权限缓存失效（权限变更时调用）。

    Args:
        user_id: 指定用户ID则只失效该用户，None 则失效所有用户权限缓存。
    """
    from backend.infrastructure import get_cache, get_key_builder
    cache = get_cache()
    kb = get_key_builder()

    if user_id is not None:
        # 失效特定用户的缓存
        cache.delete(kb.build("permission", "user", user_id, "perms"))
        cache.delete(kb.build("permission", "user", user_id, "role"))
        cache.delete(kb.build("permission", "user", user_id, "overrides"))
        cache.delete(kb.build("permission", "user", user_id, "tools"))
        logger.debug(f"[Permission] 缓存失效: user_id={user_id}")
    else:
        # 失效所有用户权限缓存
        cache.delete_pattern(kb.pattern("permission", "user"))
        # 同时失效角色权限缓存（命名空间修正）
        cache.delete_pattern(kb.pattern("permission", "role"))
        # 同时失效 LRU 降级缓存
        _get_role_permissions_lru.cache_clear()
        _get_user_overrides_lru.cache_clear()
        logger.info("[Permission] 全部权限缓存失效")


def get_user_role(user_id: int) -> str:
    """获取用户当前角色名（带 Redis 缓存）。"""
    from backend.infrastructure import get_cache, get_key_builder
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.build("permission", "user", user_id, "role")

    # 尝试 Redis
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 缓存 miss，查数据库
    conn = get_conn()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = %s", (user_id,)).fetchone()
        role = row["role"] if row else "user"
    finally:
        conn.close()

    # 写入 Redis（5min TTL + 30s jitter）
    cache.set_with_jitter(cache_key, role, base_ttl=300, jitter_range=30)

    return role


def get_user_permissions(user_id: int) -> Set[str]:
    """获取用户有效权限集合 = 角色默认 + 用户覆盖。

    优化：Redis 缓存 5 分钟，权限变更时主动失效。
    """
    role = get_user_role(user_id)

    # super_admin 拥有全部定义的权限
    if role == "super_admin":
        from backend.permission.registry import get_all_permissions
        return {p["key"] for p in get_all_permissions()}

    # 从缓存获取角色默认权限
    perms: Set[str] = set(_get_role_permissions(role))

    # 从缓存获取用户级权限覆盖
    granted, revoked = _get_user_overrides(user_id)
    perms.update(granted)
    perms.difference_update(revoked)

    return perms


def has_permission(user_id: int, permission: str) -> bool:
    """检查用户是否拥有指定权限。"""
    return permission in get_user_permissions(user_id)


def get_user_hermes_tools(user_id: int) -> List[str]:
    """获取用户的 Hermes 工具集（从 roles 表 hermes_tools JSON 字段）。

    如果 roles 表尚无 hermes_tools 字段（MySQL 迁移未执行），返回空列表。
    优化：Redis 缓存 5 分钟。
    """
    from backend.infrastructure import get_cache, get_key_builder
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.build("permission", "user", user_id, "tools")

    # 尝试 Redis
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 缓存 miss，查数据库
    role = get_user_role(user_id)
    conn = get_conn()
    try:
        row = conn.execute("SELECT hermes_tools FROM roles WHERE name = %s", (role,)).fetchone()
    except Exception:
        # MySQL 尚未迁移 hermes_tools 字段，或查询失败
        # fail-closed：异常时不授予任何工具集（比静默发权限安全）
        logger.warning(f"roles 表缺少 hermes_tools 字段或查询失败，本次不授予任何工具集（role={role}）")
        return []
    finally:
        conn.close()

    if row and row["hermes_tools"]:
        try:
            tools = json.loads(row["hermes_tools"])
            # 永久排除已废弃工具集。`utility` 是漏网之鱼：它早已改为
            # `__always_available__`（见 builtin.py 的说明），但历史数据里仍可能
            # 残留，此前过滤元组只挡了 vision/session_search/memory，于是
            # `utility` 会作为 toolset 传给 Hermes。
            tools = [t for t in tools if t not in ("vision", "session_search", "memory", "utility", "data", "email")]
        except json.JSONDecodeError:
            tools = []
    else:
        tools = []

    # 写入 Redis（5min TTL + 30s jitter）
    cache.set_with_jitter(cache_key, tools, base_ttl=300, jitter_range=30)

    return tools


def check_ownership(item_owner_id: int, user_id: int, role: str, manage_perm: str) -> bool:
    """统一的 ownership 检查。

    Returns True if:
      - 用户是 super_admin
      - 用户有 manage_perm 权限
      - 用户是 item 的 owner
    """
    if role == "super_admin":
        return True
    if has_permission(user_id, manage_perm):
        return True
    return item_owner_id == user_id


# ── 兼容旧接口 ──
def invalidate_permission_cache(user_id: int = None) -> None:
    """公开别名，供外部模块调用。"""
    _invalidate_permission_cache(user_id)
