"""AI 操作审计日志服务 — 记录对话过程中 AI 执行的每一个操作

每次工具调用（特别是 ssh/scp 远程命令）都会写入 agent_operation_logs 表，
供管理员审计留痕。
"""
import threading
from typing import Optional
from backend.utils.log_utils import log

logger = log

# 内存缓冲：thread_id → [record]，会话结束时 drain 落库
_lock = threading.Lock()
_records: dict = {}


def record_operation(
    thread_id: str,
    user_id=None,
    username: str = "",
    tool_name: str = "",
    operation_type: str = "tool_call",
    command: str = "",
    args_summary: str = "",
    result_summary: str = "",
    target_host: str = "",
    status: int = 1,
    error_message: str = "",
) -> None:
    """登记一条 AI 操作记录到内存缓冲（会话结束时批量落库）。"""
    if not thread_id:
        return
    try:
        with _lock:
            _records.setdefault(thread_id, []).append({
                "user_id": user_id,
                "username": username or "",
                "tool_name": tool_name or "unknown",
                "operation_type": operation_type,
                "command": (command or "")[:4000],
                "args_summary": (args_summary or "")[:1024],
                "result_summary": (result_summary or "")[:1024],
                "target_host": (target_host or "")[:128],
                "status": status,
                "error_message": (error_message or "")[:500],
            })
    except Exception as e:
        logger.debug(f"[AgentOpLog] record 异常: {e}")


def drain(thread_id: str) -> list:
    """清空并返回指定 thread_id 的操作记录。"""
    with _lock:
        return _records.pop(thread_id, [])


def flush_to_db(thread_id: str, user_id=None, username: str = "") -> int:
    """将内存缓冲中的操作记录批量写入 agent_operation_logs 表。返回写入条数。"""
    records = drain(thread_id)
    if not records:
        return 0
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            for rec in records:
                conn.execute(
                    "INSERT INTO agent_operation_logs "
                    "(thread_id, user_id, username, tool_name, operation_type, command, "
                    "args_summary, result_summary, target_host, status, error_message) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        thread_id,
                        rec.get("user_id") or user_id,
                        rec.get("username") or username or "",
                        rec.get("tool_name", ""),
                        rec.get("operation_type", "tool_call"),
                        rec.get("command", ""),
                        rec.get("args_summary", ""),
                        rec.get("result_summary", ""),
                        rec.get("target_host", ""),
                        rec.get("status", 1),
                        rec.get("error_message", ""),
                    ),
                )
            conn.commit()
            logger.info(f"AI 操作审计日志已落库: {len(records)} 条 (thread={thread_id})")
            return len(records)
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[AgentOpLog] flush 异常: {e}")
        return 0
