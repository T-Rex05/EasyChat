"""记忆操作审计日志服务

记录记忆系统的所有操作（CRUD/搜索/晋升/恢复/合并），供管理员审计。
采用异步写入，不阻塞主流程。
"""
import threading
from typing import Optional
from backend.utils.log_utils import log

logger = log


def record_memory_operation(
    user_id: Optional[int] = None,
    username: str = "",
    action: str = "",
    memory_id: Optional[int] = None,
    memory_layer: str = "",
    detail: str = "",
    ip_address: str = "",
    status: int = 1,
) -> None:
    """
    异步记录一条记忆操作审计日志

    Args:
        user_id: 操作人用户ID
        username: 操作人用户名
        action: 操作类型 (create/read/update/delete/search/promote/restore/consolidate)
        memory_id: 操作对象的记忆ID（search 场景可为空）
        memory_layer: 记忆层 (legacy/episodic/semantic)
        detail: 操作详情摘要（截断到 1024 字符）
        ip_address: 操作人 IP
        status: 0=失败 1=成功
    """
    def _write():
        try:
            from backend.db.schema import get_conn
            conn = get_conn()
            try:
                conn.execute(
                    """INSERT INTO memory_operation_logs
                       (user_id, username, action, memory_id, memory_layer, detail, ip_address, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        user_id,
                        username or "",
                        action or "unknown",
                        memory_id,
                        memory_layer or "",
                        (detail or "")[:1024],
                        (ip_address or "")[:64],
                        status,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"[MemoryAudit] 写入异常: {e}")

    try:
        t = threading.Thread(target=_write, daemon=True)
        t.start()
    except Exception as e:
        logger.debug(f"[MemoryAudit] 启动异步写入异常: {e}")


def query_memory_operations(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    memory_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    """
    查询记忆操作审计日志

    Args:
        user_id: 按用户过滤
        action: 按操作类型过滤
        memory_id: 按记忆ID过滤
        limit: 返回数量
        offset: 偏移量

    Returns:
        审计日志列表
    """
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            where_clauses = []
            params = []

            if user_id is not None:
                where_clauses.append("user_id = %s")
                params.append(user_id)
            if action:
                where_clauses.append("action = %s")
                params.append(action)
            if memory_id is not None:
                where_clauses.append("memory_id = %s")
                params.append(memory_id)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            cur = conn.execute(
                f"""SELECT id, user_id, username, action, memory_id, memory_layer,
                           detail, ip_address, status, created_at
                    FROM memory_operation_logs
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s""",
                params + [limit, offset],
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [dict(row) for row in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[MemoryAudit] 查询异常: {e}")
        return []


def count_memory_operations(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
) -> int:
    """统计审计日志总数"""
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            where_clauses = []
            params = []

            if user_id is not None:
                where_clauses.append("user_id = %s")
                params.append(user_id)
            if action:
                where_clauses.append("action = %s")
                params.append(action)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            cur = conn.execute(
                f"SELECT COUNT(*) as cnt FROM memory_operation_logs WHERE {where_sql}",
                params,
            )
            row = cur.fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[MemoryAudit] 计数异常: {e}")
        return 0
