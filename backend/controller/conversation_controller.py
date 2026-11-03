"""
对话历史控制器 — 内存历史存储管理

提供内存级聊天历史管理（defaultdict），用于：
- 请求内快速读取最近 N 条历史（兜底窗口）
- 新对话检测与清理
- 取消标记（防止 cancel 后从 DB 恢复旧数据）

持久化由 conversation_mapper 负责，本模块只管内存。
"""
from typing import Dict, Any, List, Set
from collections import defaultdict
from backend.utils.log_utils import log
from backend.utils.time_utils import now_local_iso
from backend.controller.chat_cleanup import update_activity, mark_cancelled_time

logger = log

# 内存聊天历史存储
# key: thread_id → value: [{role, content, timestamp}, ...]
chat_histories: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

# 已取消的会话标记（防止 cancel 后 DB 恢复又把旧数据加载回来）
_cancelled_threads: Set[str] = set()


def mark_thread_cancelled(thread_id: str) -> None:
    """标记会话已被用户取消，后续请求不应从 DB 恢复旧记录。"""
    _cancelled_threads.add(thread_id)
    mark_cancelled_time(thread_id)
    logger.info(f"标记已取消会话 - thread_id={thread_id}")


def is_thread_cancelled(thread_id: str) -> bool:
    """检查会话是否已被用户取消。"""
    return thread_id in _cancelled_threads


def limit_chat_history(thread_id: str, max_messages: int, histories: Dict[str, Any] = None):
    """限制聊天历史记录长度，只保留最近的消息。"""
    store = histories if histories is not None else chat_histories
    if thread_id not in store:
        return
    messages = store[thread_id]
    if len(messages) > max_messages:
        original_count = len(messages)
        store[thread_id] = messages[-max_messages:]
        logger.info(f"限制历史长度 - thread_id={thread_id}, {original_count}→{max_messages} 条")


def clear_thread_history(thread_id: str, histories: Dict[str, Any] = None):
    """清理指定线程的历史记录（用于新对话开始时）。"""
    store = histories if histories is not None else chat_histories
    if thread_id in store:
        message_count = len(store[thread_id])
        del store[thread_id]
        logger.info(f"清理历史 - thread_id={thread_id}, 清除 {message_count} 条")


def save_message(thread_id: str, role: str, content: str, histories: Dict[str, Any] = None) -> None:
    """保存消息到内存历史。"""
    store = histories if histories is not None else chat_histories
    store[thread_id].append({
        "role": role,
        "content": content,
        "timestamp": now_local_iso(),
    })
    update_activity(thread_id)


def get_chat_histories():
    """获取所有聊天历史存储。"""
    return chat_histories


def get_chat_history(thread_id: str, histories: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """获取指定对话的历史记录。"""
    store = histories if histories is not None else chat_histories
    update_activity(thread_id)
    return store.get(thread_id, [])
