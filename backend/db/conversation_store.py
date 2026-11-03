"""对话持久化 — MySQL conversations 表（走统一连接池）

注意：连接池默认 autocommit=True，写操作自动提交。
"""
import json as _json
from backend.utils.log_utils import log
logger = log


class ConversationStore:
    """MySQL 对话存储。"""

    def _get(self):
        from backend.db.connection_pool import get_pool_connection
        return get_pool_connection()

    def insert_conversation(self, session_id, user_id, user_question, agent_answer, status=1, problem_type=None, chat_mode='normal', source='web', metadata=None):
        conn = self._get()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO conversations (session_id, user_id, chat_mode, source, user_question, agent_answer, status, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (session_id, int(user_id), chat_mode, source, user_question, agent_answer, status, _json.dumps(metadata) if metadata else None),
            )
            return cur.lastrowid
        finally:
            conn.close()

    def get_conversations_by_session(self, session_id):
        conn = self._get()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, session_id, user_id, chat_mode, source, user_question, agent_answer, status, metadata, created_at, updated_at FROM conversations WHERE session_id = %s AND status != 0 ORDER BY created_at ASC",
                (session_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    def get_conversation_by_id(self, conversation_id):
        """按 id 查单条对话（反馈归属校验用）。"""
        conn = self._get()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, session_id, user_id FROM conversations WHERE id = %s LIMIT 1",
                (conversation_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_conversation_answer(self, conversation_id, agent_answer, status=1):
        conn = self._get()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE conversations SET agent_answer = %s, status = %s WHERE id = %s",
                (agent_answer, status, conversation_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_conversation_status(self, conversation_id, status, user_id=None):
        conn = self._get()
        try:
            cur = conn.cursor()
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

    def mark_conversation_failed(self, conversation_id):
        conn = self._get()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE conversations SET status = 2 WHERE id = %s AND status = 4 AND (agent_answer = '' OR agent_answer IS NULL)",
                (conversation_id,),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def insert_attachment(self, session_id, conversation_id, file_type, file_path, file_name=None):
        conn = self._get()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO attachments (session_id, conversation_id, file_type, file_name, file_path) VALUES (%s, %s, %s, %s, %s)",
                (session_id, conversation_id, file_type, file_name, file_path),
            )
            return cur.lastrowid
        finally:
            conn.close()

    def get_attachments_by_session(self, session_id):
        conn = self._get()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, session_id, conversation_id, file_type, file_name, file_path, created_at FROM attachments WHERE session_id = %s ORDER BY created_at ASC",
                (session_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()
