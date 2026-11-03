"""聊天控制器 - 对话持久化辅助函数"""
from typing import Optional, Dict, Any, List
from backend.utils.log_utils import log

logger = log

# 数据访问层（延迟初始化，由外部注入）
conversation_mapper = None


def set_conversation_mapper(conv_mapper):
    """设置对话映射器（由 main.py 或应用初始化代码调用）。"""
    global conversation_mapper
    conversation_mapper = conv_mapper


def _insert_running_conversation(
    thread_id: str, 
    user_id: int, 
    user_question: str, 
    chat_mode: str = 'normal', 
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[int]:
    """请求开始即落库用户消息（status=4 进行中），返回 conversation_id。"""
    if not conversation_mapper:
        return None
    try:
        conversation_id = conversation_mapper.insert_conversation(
            session_id=thread_id, user_id=user_id,
            user_question=user_question, agent_answer="", status=4,
            chat_mode=chat_mode, metadata=metadata,
        )
        logger.debug(f"用户消息已落库 - session_id={thread_id}, conv_id={conversation_id}")
        return conversation_id
    except Exception as e:
        logger.error(f"用户消息落库失败（不阻断）: {e}")
        return None


def _persist_conversation_answer(
    running_conversation_id: Optional[int],
    thread_id: str, 
    user_id: int,
    user_question: str, 
    agent_answer: str,
) -> Optional[int]:
    """完成时回填答案。"""
    if not conversation_mapper or not agent_answer:
        return running_conversation_id
    try:
        if running_conversation_id:
            conversation_mapper.update_conversation_answer(
                conversation_id=running_conversation_id,
                agent_answer=agent_answer, status=1,
            )
            return running_conversation_id
        return conversation_mapper.insert_conversation(
            session_id=thread_id, user_id=user_id,
            user_question=user_question, agent_answer=agent_answer, status=1,
        )
    except Exception as e:
        logger.error(f"对话答案持久化失败: {e}")
        return None


def _mark_conversation_failed(conversation_id: Optional[int]):
    """异常时将进行中(4)的行标记为异常(2)。"""
    if not conversation_mapper or not conversation_id:
        return
    try:
        conversation_mapper.mark_conversation_failed(conversation_id)
    except Exception as e:
        logger.error(f"标记对话异常失败: {e}")


def _mark_conversation_cancelled(conversation_id: Optional[int], user_id: Optional[int] = None):
    """用户取消时将进行中(4)的行标记为用户中断(3)。"""
    if not conversation_mapper or not conversation_id:
        return
    try:
        conversation_mapper.update_conversation_status(conversation_id, status=3, user_id=user_id)
    except Exception as e:
        logger.error(f"标记用户中断失败: {e}")
