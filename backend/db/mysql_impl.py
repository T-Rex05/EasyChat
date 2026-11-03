"""
MySQL 数据层实现 — 生产环境数据库

需要额外依赖：pip install pymysql
通过环境变量配置连接参数。
"""
import os
import json
from typing import Optional, List, Dict, Any

from backend.db import ConversationMapperBase
from backend.utils.log_utils import log

logger = log


class MySQLMapper(ConversationMapperBase):
    """MySQL 对话数据访问实现。"""

    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self._pool = None

    @classmethod
    def from_env(cls) -> "MySQLMapper":
        """从环境变量创建实例。"""
        return cls(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            database=os.getenv("MYSQL_DATABASE", "agentforge"),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
        )

    def _get_conn(self):
        """获取 MySQL 连接（走统一连接池）。"""
        from backend.db.connection_pool import get_pool_connection
        return get_pool_connection()

    def init_schema(self):
        """初始化 MySQL 表结构（首次使用时调用）。"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        session_id VARCHAR(128) NOT NULL,
                        user_id BIGINT,
                        chat_mode VARCHAR(32) DEFAULT 'normal',
                        user_question TEXT NOT NULL,
                        agent_answer TEXT NOT NULL,
                        status INT NOT NULL DEFAULT 1,
                        session_title VARCHAR(255),
                        problem_type INT,
                        metadata JSON,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_session (session_id),
                        INDEX idx_user (user_id),
                        INDEX idx_status (status),
                        INDEX idx_created_at (created_at),
                        INDEX idx_user_created (user_id, created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS attachments (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        session_id VARCHAR(128),
                        conversation_id BIGINT,
                        file_type INT NOT NULL DEFAULT 0,
                        file_name VARCHAR(512),
                        file_path TEXT,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_session (session_id),
                        INDEX idx_conv (conversation_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
            logger.info(f"MySQL schema 初始化完成: {self.database}")
        finally:
            conn.close()

    # ── 对话 CRUD ──

    def insert_conversation(
        self, session_id: str, user_id: int,
        user_question: str, agent_answer: str,
        status: int = 1, problem_type: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO conversations
                       (session_id, user_id, user_question, agent_answer, status, problem_type, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (session_id, str(user_id), user_question, agent_answer, status, problem_type, 
                     json.dumps(metadata) if metadata else None),
                )
                return cur.lastrowid
        finally:
            conn.close()

    def get_conversations_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, session_id, user_id, user_question, agent_answer,
                              status, problem_type, metadata, created_at, updated_at
                       FROM conversations
                       WHERE session_id = %s AND status != 0
                       ORDER BY created_at ASC""",
                    (session_id,),
                )
                return cur.fetchall()
        finally:
            conn.close()

    def get_conversations_by_user(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, session_id, user_id, user_question, agent_answer,
                              status, problem_type, created_at, updated_at
                       FROM conversations
                       WHERE user_id = %s AND status != 0
                       ORDER BY created_at DESC LIMIT %s""",
                    (str(user_id), limit),
                )
                return cur.fetchall()
        finally:
            conn.close()

    def update_conversation_answer(
        self, conversation_id: int, agent_answer: str, status: int = 1,
    ) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE conversations SET agent_answer = %s, status = %s WHERE id = %s",
                    (agent_answer, status, conversation_id),
                )
                return cur.rowcount > 0
        finally:
            conn.close()

    def update_conversation_status(self, conversation_id: int, status: int, user_id: Optional[int] = None) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                if user_id is not None:
                    cur.execute(
                        "UPDATE conversations SET status = %s WHERE id = %s AND user_id = %s",
                        (status, conversation_id, user_id),
                    )
                else:
                    cur.execute(
                        "UPDATE conversations SET status = %s WHERE id = %s",
                        (status, conversation_id),
                    )
                return cur.rowcount > 0
        finally:
            conn.close()

    def mark_conversation_failed(self, conversation_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE conversations SET status = 2
                       WHERE id = %s AND status = 4
                         AND (agent_answer = '' OR agent_answer IS NULL)""",
                    (conversation_id,),
                )
                return cur.rowcount > 0
        finally:
            conn.close()

    # ── 附件 ──

    def insert_attachment(
        self, session_id: str, conversation_id: int,
        file_type: int, file_path: str, file_name: Optional[str] = None,
    ) -> int:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO attachments (session_id, conversation_id, file_type, file_name, file_path)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (session_id, conversation_id, file_type, file_name, file_path),
                )
                return cur.lastrowid
        finally:
            conn.close()

    def get_attachments_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, session_id, conversation_id, file_type, file_name, file_path, created_at
                       FROM attachments WHERE session_id = %s ORDER BY created_at ASC""",
                    (session_id,),
                )
                return cur.fetchall()
        finally:
            conn.close()
