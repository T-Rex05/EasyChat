"""
SQL 记录器 — 所有通过 sql_db_query 执行的 SQL 自动记录

并发安全：用 contextvars 按请求隔离当前 thread_id，record() 只写入本请求的桶；
会话结束时由 chat/stream 的 finally 统一 drain 落库（与 exec_approval_recorder 同款模式）。
"""
import contextvars
import threading
from typing import List, Dict, Any, Optional

from backend.utils.log_utils import log

logger = log

_lock = threading.Lock()
_records: Dict[str, List[Dict[str, Any]]] = {}

# 当前请求的 thread_id（chat_controller 在请求协程内 set，工具线程经 copy_context 继承）
_current_thread_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "sql_recorder_thread_id", default=None
)


def set_context(thread_id: str) -> None:
    """设置当前会话上下文（chat_controller 在请求开始时调用）。"""
    _current_thread_id.set(thread_id)
    with _lock:
        if thread_id not in _records:
            _records[thread_id] = []


def record(thread_id: str, query: str, status: int = 1, error: Optional[str] = None) -> None:
    """登记一条 SQL 操作记录到内存缓冲（会话结束时批量落库）。

    Args:
        thread_id: 会话线程 ID
        query: SQL 查询语句
        status: 执行状态（1=成功, 0=失败）
        error: 错误信息（status=0 时填写）
    """
    if not thread_id:
        return
    try:
        with _lock:
            bucket = _records.setdefault(thread_id, [])
            bucket.append({
                "query": query,
                "status": status,
                "error": error,
            })
    except Exception:
        pass


def drain(thread_id: str) -> List[Dict[str, Any]]:
    """清空并返回指定 thread_id 的 SQL 记录。"""
    with _lock:
        return _records.pop(thread_id, [])


def flush_to_db(thread_id: str, user_id=None, username: str = "") -> int:
    """将内存缓冲中的 SQL 记录批量写入 sql_operation_logs 表。返回写入条数。"""
    records = drain(thread_id)
    if not records:
        return 0
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            for rec in records:
                conn.execute(
                    "INSERT INTO sql_operation_logs "
                    "(thread_id, user_id, username, query, status, error_message) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        thread_id,
                        user_id,
                        username or "",
                        (rec.get("query") or "")[:4000],
                        rec.get("status", 1),
                        (rec.get("error") or "")[:500],
                    ),
                )
            conn.commit()
            logger.info(f"SQL 操作审计已落库: {len(records)} 条 (thread={thread_id})")
            return len(records)
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[SQL-Recorder] flush 异常: {e}")
        return 0
