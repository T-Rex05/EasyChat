"""命令黑名单服务 — 管理自定义的危险命令正则规则

管理员可以添加自定义正则表达式，命中这些规则的命令会触发审批流程。
"""
import re
from typing import List, Dict, Any, Optional
from backend.utils.log_utils import log

logger = log


def _conn():
    from backend.db.schema import get_conn
    return get_conn()


def list_rules(enabled_only: bool = False) -> List[Dict[str, Any]]:
    """列出所有命令黑名单规则。
    
    Args:
        enabled_only: 是否只返回启用的规则
    
    Returns:
        规则列表 [{id, pattern, description, enabled, created_at, updated_at}]
    """
    conn = _conn()
    try:
        if enabled_only:
            cur = conn.execute(
                "SELECT id, pattern, description, enabled, created_at, updated_at "
                "FROM command_blacklist WHERE enabled = 1 ORDER BY id DESC"
            )
        else:
            cur = conn.execute(
                "SELECT id, pattern, description, enabled, created_at, updated_at "
                "FROM command_blacklist ORDER BY id DESC"
            )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_rule(pattern: str, description: str = "", enabled: bool = True,
             created_by: Optional[int] = None) -> Dict[str, Any]:
    """添加一条命令黑名单规则。
    
    Args:
        pattern: 正则表达式
        description: 规则描述
        enabled: 是否启用
        created_by: 创建人 ID
    
    Returns:
        新创建的规则 {id, pattern}
    
    Raises:
        ValueError: 正则表达式不合法
    """
    pattern = (pattern or "").strip()
    if not pattern:
        raise ValueError("正则表达式不能为空")
    
    # 验证正则表达式合法性
    try:
        re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"正则表达式不合法: {e}")
    
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO command_blacklist (pattern, description, enabled, created_by) "
            "VALUES (%s, %s, %s, %s)",
            (pattern, description, 1 if enabled else 0, created_by),
        )
        conn.commit()
        return {"id": cur.lastrowid, "pattern": pattern}
    finally:
        conn.close()


def update_rule(rule_id: int, **fields) -> bool:
    """更新一条命令黑名单规则。
    
    Args:
        rule_id: 规则 ID
        **fields: 要更新的字段（pattern, description, enabled）
    
    Returns:
        是否更新成功
    """
    allowed = {"pattern", "description", "enabled"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    
    # 如果更新了 pattern，需要验证正则表达式
    if "pattern" in updates:
        pattern = (updates["pattern"] or "").strip()
        if not pattern:
            return False
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error:
            return False
        updates["pattern"] = pattern
    
    # enabled 字段转换为 0/1
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0
    
    if not updates:
        return False
    
    conn = _conn()
    try:
        # 先检查规则是否存在
        cur = conn.execute("SELECT id FROM command_blacklist WHERE id = %s", (int(rule_id),))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if not rows:
            return False
        
        # 执行更新（不检查 rowcount，因为值未改变时 MySQL 可能返回 0）
        sets = ", ".join(f"{k} = %s" for k in updates.keys())
        conn.execute(
            f"UPDATE command_blacklist SET {sets} WHERE id = %s",
            list(updates.values()) + [int(rule_id)],
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_rule(rule_id: int) -> bool:
    """删除一条命令黑名单规则。
    
    Args:
        rule_id: 规则 ID
    
    Returns:
        是否删除成功
    """
    conn = _conn()
    try:
        cur = conn.execute("DELETE FROM command_blacklist WHERE id = %s", (int(rule_id),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_compiled_patterns() -> List[tuple]:
    """获取所有启用的命令黑名单规则（编译后的正则）。
    
    Returns:
        [(compiled_pattern, description), ...]
    """
    rules = list_rules(enabled_only=True)
    compiled = []
    for rule in rules:
        try:
            pattern = re.compile(rule["pattern"], re.IGNORECASE)
            compiled.append((pattern, rule["description"] or "自定义黑名单规则"))
        except Exception as e:
            logger.warning(f"命令黑名单规则编译失败 id={rule['id']}: {e}")
    return compiled


def check_command_blacklist(command: str) -> Optional[str]:
    """检查命令是否命中黑名单。
    
    Args:
        command: 要检查的命令
    
    Returns:
        命中规则的 description，未命中返回 None
    """
    if not command:
        return None
    
    patterns = get_compiled_patterns()
    for pattern_re, description in patterns:
        if pattern_re.search(command):
            return description
    
    return None


def sync_hermes_builtin_patterns() -> int:
    """同步 Hermes 内置的 DANGEROUS_PATTERNS 到 command_blacklist 表。
    
    幂等操作：已存在的规则不会重复添加。
    
    Returns:
        新增的规则数量
    """
    try:
        from backend.hermes.tools.approval import DANGEROUS_PATTERNS
    except ImportError:
        logger.warning("无法导入 Hermes DANGEROUS_PATTERNS，跳过同步")
        return 0
    
    conn = _conn()
    try:
        # 获取已存在的规则（按 pattern 去重）
        cur = conn.execute("SELECT pattern FROM command_blacklist")
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        existing_patterns = {r["pattern"] for r in rows}
        
        added_count = 0
        for pattern, description in DANGEROUS_PATTERNS:
            # 跳过已存在的规则
            if pattern in existing_patterns:
                continue
            
            # 验证正则表达式合法性
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                logger.warning(f"Hermes 内置规则不合法，跳过: {e}")
                continue
            
            # 插入新规则
            conn.execute(
                "INSERT INTO command_blacklist (pattern, description, enabled, created_by) "
                "VALUES (%s, %s, %s, %s)",
                (pattern, description or "Hermes 内置危险命令规则", 1, None),
            )
            added_count += 1
        
        if added_count > 0:
            conn.commit()
            logger.info(f"同步 Hermes 内置规则完成，新增 {added_count} 条")
        
        return added_count
    except Exception as e:
        logger.error(f"同步 Hermes 内置规则失败: {e}")
        return 0
    finally:
        conn.close()
