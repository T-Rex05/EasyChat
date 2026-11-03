"""exec 审批记录器 — 命令执行审批决议的落库缓冲区（借鉴 Eyes exec_approval_recorder）

resolve_pending_approval() 发生在独立 HTTP 请求，用内存缓冲按 thread_id 分桶；
chat/stream 落库时 drain() 写出到 exec_approval_logs 表（正常收尾与兜底均可调用）。
"""
import threading
from typing import Any, Dict, List

_lock = threading.Lock()
_records: Dict[str, List[Dict[str, Any]]] = {}


def record(thread_id: str, command: str, decision: str, allow_permanent: bool,
           description: str = "", confirmed_by_user_id=None,
           confirmed_by_name: str = None) -> None:
    """登记一条已决议的 exec 审批，供该 thread 落库时读取。"""
    if not thread_id:
        return
    try:
        with _lock:
            _records.setdefault(thread_id, []).append({
                "command": command,
                "description": description,
                "decision": decision,
                "allow_permanent": bool(allow_permanent),
                "confirmed_by_user_id": confirmed_by_user_id,
                "confirmed_by_name": confirmed_by_name,
            })
    except Exception:
        pass


def drain(thread_id: str) -> List[Dict[str, Any]]:
    """清空并返回指定 thread_id 的审批记录。"""
    with _lock:
        return _records.pop(thread_id, [])