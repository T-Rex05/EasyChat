"""
AgentForge 数据层 — 数据库工厂与抽象接口

仅支持 MySQL。

用法：
    from backend.db import get_database
    db = get_database()
    db.insert_conversation(...)
"""
from typing import Optional
from backend.utils.log_utils import log

logger = log


def get_database():
    """获取 MySQL mapper 实例（单例）。"""
    try:
        from backend.db.mysql_impl import MySQLMapper
        mapper = MySQLMapper.from_env()
        conn = mapper._get_conn()
        conn.close()
        logger.info(f"数据库模式: MySQL — {mapper.host}/{mapper.database}")
        return mapper
    except Exception as e:
        logger.warning(f"MySQL 连接失败: {e}")
        return None


# ── 抽象接口定义 ──

class ConversationMapperBase:
    """对话数据访问抽象接口。所有实现必须实现以下方法。"""

    def insert_conversation(
        self, session_id: str, user_id: int,
        user_question: str, agent_answer: str,
        status: int = 1, problem_type: Optional[int] = None,
    ) -> int:
        raise NotImplementedError

    def get_conversations_by_session(self, session_id: str) -> list:
        raise NotImplementedError

    def get_conversations_by_user(self, user_id: int, limit: int = 50) -> list:
        raise NotImplementedError

    def update_conversation_answer(
        self, conversation_id: int, agent_answer: str, status: int = 1,
    ) -> bool:
        raise NotImplementedError

    def update_conversation_status(self, conversation_id: int, status: int, user_id: Optional[int] = None) -> bool:
        raise NotImplementedError

    def mark_conversation_failed(self, conversation_id: int) -> bool:
        raise NotImplementedError

    def insert_attachment(
        self, session_id: str, conversation_id: int,
        file_type: int, file_path: str, file_name: Optional[str] = None,
    ) -> int:
        raise NotImplementedError

    def get_attachments_by_session(self, session_id: str) -> list:
        raise NotImplementedError
