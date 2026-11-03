"""
Memory Mapper - 记忆数据访问层

负责 memory_episodic、memory_semantic 表的 CRUD 操作

版本号机制：
- version 字段每次更新自动 +1
- 更新时使用乐观锁（WHERE version = expected_version）
- 防止并发写入导致数据覆盖

内容哈希：
- content_hash 字段用于快速对账
- 基于所有影响派生投影的字段计算
"""

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.utils.log_utils import log
from backend.utils.crypto_utils import encrypt_memory_content, decrypt_memory_content

logger = log


def _decrypt_row_content(row: dict) -> dict:
    """对单行记忆数据的 content 字段解密（读取路径）"""
    if row and "content" in row:
        row["content"] = decrypt_memory_content(row["content"])
    return row


def _encrypt_row_for_write(content: str) -> str:
    """对记忆 content 字段加密（写入路径）"""
    return encrypt_memory_content(content)



class EpisodicMapper:
    """近期记忆数据访问层（memory_episodic 表）"""

    def __init__(self):
        from backend.db.schema import get_conn
        self._get_conn = get_conn

    def create_memory(
        self,
        user_id: int,
        memory_type: str,
        content: str,
        importance_score: float = 0.5,
        source_thread_id: str = "",
        source_round: int = 0,
        ttl_days: int = 30,
        decay_rate: float = 0.95,
        content_hash: str = "",
        conn: Optional[Any] = None
    ) -> Optional[int]:
        """创建近期记忆"""
        from datetime import timedelta
        expires_at = datetime.now() + timedelta(days=ttl_days)
        own_conn = conn is None

        try:
            if conn is None:
                conn = self._get_conn()

            cur = conn.execute(
                """INSERT INTO memory_episodic
                   (user_id, memory_type, content, importance_score,
                    source_thread_id, source_round, ttl_days, decay_rate,
                    expires_at, version, content_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)""",
                (user_id, memory_type, encrypt_memory_content(content), importance_score,
                 source_thread_id, source_round, ttl_days, decay_rate,
                 expires_at, content_hash)
            )

            if own_conn:
                conn.commit()
            return cur.lastrowid
        except Exception as e:
            if own_conn:
                conn.rollback()
            logger.error(f"Failed to create episodic memory: {e}")
            return None
        finally:
            if own_conn and conn:
                conn.close()

    def get_memory_by_id(self, memory_id: int, user_id: Optional[int] = None) -> Optional[dict]:
        """根据ID获取记忆"""
        conn = self._get_conn()
        try:
            if user_id is not None:
                cur = conn.execute(
                    "SELECT * FROM memory_episodic WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
                    (memory_id, user_id)
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM memory_episodic WHERE id = %s AND deleted_at IS NULL",
                    (memory_id,)
                )
            row = cur.fetchone()
            return _decrypt_row_content(dict(row)) if row else None
        except Exception as e:
            logger.error(f"Failed to get episodic memory: {e}")
            return None
        finally:
            conn.close()

    def get_memories_by_user(
        self,
        user_id: int,
        memory_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """获取用户近期记忆列表"""
        conn = self._get_conn()
        try:
            where_clauses = ["user_id = %s", "deleted_at IS NULL",
                           "(expires_at IS NULL OR expires_at > NOW())"]
            params = [user_id]

            if memory_type:
                where_clauses.append("memory_type = %s")
                params.append(memory_type)

            where_sql = " AND ".join(where_clauses)

            cur = conn.execute(
                f"""SELECT * FROM memory_episodic
                    WHERE {where_sql}
                    ORDER BY importance_score DESC, updated_at DESC
                    LIMIT %s OFFSET %s""",
                params + [limit, offset]
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [_decrypt_row_content(dict(row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get episodic memories: {e}")
            return []
        finally:
            conn.close()

    def update_memory(
        self,
        memory_id: int,
        content: Optional[str] = None,
        importance_score: Optional[float] = None,
        embedding_id: Optional[str] = None,
        is_user_edited: Optional[bool] = None,
        content_hash: Optional[str] = None,
        expected_version: Optional[int] = None,
        user_id: Optional[int] = None,
        conn: Optional[Any] = None
    ) -> Tuple[bool, int]:
        """更新近期记忆（支持乐观锁）"""
        updates = []
        params = []

        if content is not None:
            updates.append("content = %s")
            params.append(encrypt_memory_content(content))
        if importance_score is not None:
            updates.append("importance_score = %s")
            params.append(importance_score)
        if embedding_id is not None:
            updates.append("embedding_id = %s")
            params.append(embedding_id)
        if is_user_edited is not None:
            updates.append("is_user_edited = %s")
            params.append(1 if is_user_edited else 0)
        if content_hash is not None:
            updates.append("content_hash = %s")
            params.append(content_hash)

        if not updates:
            return False, -1

        updates.append("version = version + 1")

        where_clause = "id = %s AND deleted_at IS NULL"
        if user_id is not None:
            where_clause += " AND user_id = %s"
            params.append(user_id)
        params.append(memory_id)
        if expected_version is not None:
            where_clause += " AND version = %s"
            params.append(expected_version)

        own_conn = conn is None

        try:
            if conn is None:
                conn = self._get_conn()

            cur = conn.execute(
                f"UPDATE memory_episodic SET {', '.join(updates)} WHERE {where_clause}",
                params
            )

            if cur.rowcount == 0:
                if own_conn:
                    conn.rollback()
                return False, -1

            cur2 = conn.execute(
                "SELECT version FROM memory_episodic WHERE id = %s",
                (memory_id,)
            )
            row = cur2.fetchone()
            new_version = row["version"] if row else -1

            if own_conn:
                conn.commit()
            return True, new_version
        except Exception as e:
            if own_conn:
                conn.rollback()
            logger.error(f"Failed to update episodic memory: {e}")
            return False, -1
        finally:
            if own_conn and conn:
                conn.close()

    def soft_delete(self, memory_id: int, user_id: Optional[int] = None, conn: Optional[Any] = None) -> bool:
        """软删除记忆"""
        own_conn = conn is None
        try:
            if conn is None:
                conn = self._get_conn()
            if user_id is not None:
                conn.execute(
                    "UPDATE memory_episodic SET deleted_at = NOW() WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
                    (memory_id, user_id)
                )
            else:
                conn.execute(
                    "UPDATE memory_episodic SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL",
                    (memory_id,)
                )
            if own_conn:
                conn.commit()
            return True
        except Exception as e:
            if own_conn:
                conn.rollback()
            logger.error(f"Failed to soft delete episodic memory: {e}")
            return False
        finally:
            if own_conn and conn:
                conn.close()

    def update_embedding_id(self, memory_id: int, embedding_id: str) -> bool:
        """更新 embedding_id（向量库同步后回写）"""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE memory_episodic SET embedding_id = %s WHERE id = %s AND deleted_at IS NULL",
                (embedding_id, memory_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update episodic embedding_id: {e}")
            return False
        finally:
            conn.close()

    def increment_access_count(self, memory_id: int) -> bool:
        """增加访问计数 + 微增重要性（递减回报，越接近 1 增长越慢）

        公式: importance += 0.02 * (1 - importance)
        效果: 0.5 → 18 次检索后 ≈ 0.85 → 触发自动晋升
        """
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE memory_episodic
                   SET access_count = access_count + 1,
                       last_accessed_at = NOW(),
                       importance_score = importance_score + 0.02 * (1 - importance_score)
                   WHERE id = %s""",
                (memory_id,)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to increment access count: {e}")
            return False
        finally:
            conn.close()

    def get_expired_memories(self, limit: int = 1000) -> list:
        """获取过期记忆"""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """SELECT id, embedding_id FROM memory_episodic
                   WHERE expires_at IS NOT NULL AND expires_at < NOW()
                   AND deleted_at IS NULL
                   LIMIT %s""",
                (limit,)
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get expired episodic memories: {e}")
            return []
        finally:
            conn.close()


class SemanticMapper:
    """永久知识数据访问层（memory_semantic 表）"""

    def __init__(self):
        from backend.db.schema import get_conn
        self._get_conn = get_conn

    def create_memory(
        self,
        user_id: int,
        memory_type: str,
        content: str,
        importance_score: float = 0.5,
        source_thread_id: str = "",
        source_round: int = 0,
        source_episodic_id: Optional[int] = None,
        content_hash: str = "",
        conn: Optional[Any] = None
    ) -> Optional[int]:
        """创建永久知识"""
        own_conn = conn is None

        try:
            if conn is None:
                conn = self._get_conn()

            cur = conn.execute(
                """INSERT INTO memory_semantic
                   (user_id, memory_type, content, importance_score,
                    source_thread_id, source_round, source_episodic_id,
                    version, content_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)""",
                (user_id, memory_type, encrypt_memory_content(content), importance_score,
                 source_thread_id, source_round, source_episodic_id,
                 content_hash)
            )

            if own_conn:
                conn.commit()
            return cur.lastrowid
        except Exception as e:
            if own_conn:
                conn.rollback()
            logger.error(f"Failed to create semantic memory: {e}")
            return None
        finally:
            if own_conn and conn:
                conn.close()

    def get_memory_by_id(self, memory_id: int, user_id: Optional[int] = None) -> Optional[dict]:
        """根据ID获取记忆"""
        conn = self._get_conn()
        try:
            if user_id is not None:
                cur = conn.execute(
                    "SELECT * FROM memory_semantic WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
                    (memory_id, user_id)
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM memory_semantic WHERE id = %s AND deleted_at IS NULL",
                    (memory_id,)
                )
            row = cur.fetchone()
            return _decrypt_row_content(dict(row)) if row else None
        except Exception as e:
            logger.error(f"Failed to get semantic memory: {e}")
            return None
        finally:
            conn.close()

    def get_memories_by_user(
        self,
        user_id: int,
        memory_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """获取用户永久知识列表"""
        conn = self._get_conn()
        try:
            where_clauses = ["user_id = %s", "deleted_at IS NULL"]
            params = [user_id]

            if memory_type:
                where_clauses.append("memory_type = %s")
                params.append(memory_type)

            where_sql = " AND ".join(where_clauses)

            cur = conn.execute(
                f"""SELECT * FROM memory_semantic
                    WHERE {where_sql}
                    ORDER BY importance_score DESC, updated_at DESC
                    LIMIT %s OFFSET %s""",
                params + [limit, offset]
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [_decrypt_row_content(dict(row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get semantic memories: {e}")
            return []
        finally:
            conn.close()

    def update_memory(
        self,
        memory_id: int,
        content: Optional[str] = None,
        importance_score: Optional[float] = None,
        embedding_id: Optional[str] = None,
        graph_node_id: Optional[str] = None,
        is_user_edited: Optional[bool] = None,
        content_hash: Optional[str] = None,
        expected_version: Optional[int] = None,
        user_id: Optional[int] = None,
        conn: Optional[Any] = None,
        bump_version: bool = True
    ) -> Tuple[bool, int]:
        """
        更新永久知识（支持乐观锁）

        Args:
            bump_version: 是否递增 version。**派生库回写必须传 False**
                （如 outbox 写回 embedding_id）：version 表达的是"内容版本"，
                派生库回写把它 +1 会让同一批 outbox 事件里的兄弟事件
                （upsert_graph_node 用 memory_version 做新旧判断）被判成"过期"而静默跳过
                —— 实测晋升后的记忆因此永远不建图节点、不抽实体。
        """
        updates = []
        params = []

        if content is not None:
            updates.append("content = %s")
            params.append(encrypt_memory_content(content))
        if importance_score is not None:
            updates.append("importance_score = %s")
            params.append(importance_score)
        if embedding_id is not None:
            updates.append("embedding_id = %s")
            params.append(embedding_id)
        if graph_node_id is not None:
            updates.append("graph_node_id = %s")
            params.append(graph_node_id)
        if is_user_edited is not None:
            updates.append("is_user_edited = %s")
            params.append(1 if is_user_edited else 0)
        if content_hash is not None:
            updates.append("content_hash = %s")
            params.append(content_hash)

        if not updates:
            return False, -1

        if bump_version:
            updates.append("version = version + 1")

        where_clause = "id = %s AND deleted_at IS NULL"
        if user_id is not None:
            where_clause += " AND user_id = %s"
            params.append(user_id)
        params.append(memory_id)
        if expected_version is not None:
            where_clause += " AND version = %s"
            params.append(expected_version)

        own_conn = conn is None

        try:
            if conn is None:
                conn = self._get_conn()

            cur = conn.execute(
                f"UPDATE memory_semantic SET {', '.join(updates)} WHERE {where_clause}",
                params
            )

            if cur.rowcount == 0:
                if own_conn:
                    conn.rollback()
                return False, -1

            cur2 = conn.execute(
                "SELECT version FROM memory_semantic WHERE id = %s",
                (memory_id,)
            )
            row = cur2.fetchone()
            new_version = row["version"] if row else -1

            if own_conn:
                conn.commit()
            return True, new_version
        except Exception as e:
            if own_conn:
                conn.rollback()
            logger.error(f"Failed to update semantic memory: {e}")
            return False, -1
        finally:
            if own_conn and conn:
                conn.close()

    def soft_delete(self, memory_id: int, user_id: Optional[int] = None, conn: Optional[Any] = None) -> bool:
        """软删除记忆"""
        own_conn = conn is None
        try:
            if conn is None:
                conn = self._get_conn()
            if user_id is not None:
                conn.execute(
                    "UPDATE memory_semantic SET deleted_at = NOW() WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
                    (memory_id, user_id)
                )
            else:
                conn.execute(
                    "UPDATE memory_semantic SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL",
                    (memory_id,)
                )
            if own_conn:
                conn.commit()
            return True
        except Exception as e:
            if own_conn:
                conn.rollback()
            logger.error(f"Failed to soft delete semantic memory: {e}")
            return False
        finally:
            if own_conn and conn:
                conn.close()

    def update_embedding_id(self, memory_id: int, embedding_id: str) -> bool:
        """更新 embedding_id（向量库同步后回写）"""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE memory_semantic SET embedding_id = %s WHERE id = %s AND deleted_at IS NULL",
                (embedding_id, memory_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update semantic embedding_id: {e}")
            return False
        finally:
            conn.close()

    def update_graph_node_id(self, memory_id: int, graph_node_id: str) -> bool:
        """更新 graph_node_id（图节点创建后回写）"""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE memory_semantic SET graph_node_id = %s WHERE id = %s AND deleted_at IS NULL",
                (graph_node_id, memory_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update semantic graph_node_id: {e}")
            return False
        finally:
            conn.close()

    def increment_access_count(self, memory_id: int) -> bool:
        """增加访问计数"""
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE memory_semantic
                   SET access_count = access_count + 1,
                       last_accessed_at = NOW()
                   WHERE id = %s""",
                (memory_id,)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to increment access count: {e}")
            return False
        finally:
            conn.close()


# 单例访问
_episodic_mapper: Optional[EpisodicMapper] = None
_semantic_mapper: Optional[SemanticMapper] = None
_singleton_lock = threading.Lock()


def get_episodic_mapper() -> EpisodicMapper:
    """获取 EpisodicMapper 单例（线程安全）"""
    global _episodic_mapper
    if _episodic_mapper is None:
        with _singleton_lock:
            if _episodic_mapper is None:
                _episodic_mapper = EpisodicMapper()
    return _episodic_mapper


def get_semantic_mapper() -> SemanticMapper:
    """获取 SemanticMapper 单例（线程安全）"""
    global _semantic_mapper
    if _semantic_mapper is None:
        with _singleton_lock:
            if _semantic_mapper is None:
                _semantic_mapper = SemanticMapper()
    return _semantic_mapper


class RoundsMapper:
    """memory_rounds 表数据访问层 — 会话轮次追踪"""

    def __init__(self):
        from backend.db.schema import get_conn
        self._get_conn = get_conn

    def increment_round(
        self,
        thread_id: str,
        user_id: int,
        message_hash: str
    ) -> int:
        """
        递增轮次计数（幂等：相同 message_hash 不重复计数）

        Returns:
            current_round: 当前轮次

        Raises:
            Exception: DB 失败时**向上抛**（不再 `return 0`）。返回 0 会让调用方
                误判为"轮次为 0、不需提取"，且计数未推进 → 记忆提取会永久静默停机。
                调用方（process_round）负责捕获并记 error 级日志，保证不影响对话。
        """
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO memory_rounds (thread_id, user_id, round_count, last_message_hash)
                   VALUES (%s, %s, 1, %s)
                   ON DUPLICATE KEY UPDATE
                       round_count = round_count + 1,
                       last_message_hash = VALUES(last_message_hash),
                       updated_at = NOW()""",
                (thread_id, user_id, message_hash)
            )
            cur = conn.execute(
                "SELECT round_count FROM memory_rounds WHERE thread_id = %s",
                (thread_id,)
            )
            row = cur.fetchone()
            return row["round_count"] if row else 0
        finally:
            conn.close()

    def get_round_count(self, thread_id: str) -> int:
        """获取当前轮次"""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "SELECT round_count FROM memory_rounds WHERE thread_id = %s",
                (thread_id,)
            )
            row = cur.fetchone()
            return row["round_count"] if row else 0
        except Exception as e:
            logger.error(f"Failed to get round count: {e}")
            return 0
        finally:
            conn.close()


_rounds_mapper: Optional[RoundsMapper] = None


def get_rounds_mapper() -> RoundsMapper:
    """获取 RoundsMapper 单例"""
    global _rounds_mapper
    if _rounds_mapper is None:
        _rounds_mapper = RoundsMapper()
    return _rounds_mapper


class MemoryVersionsMapper:
    """memory_versions 表数据访问层 — 记忆版本历史"""

    def __init__(self):
        from backend.db.schema import get_conn
        self._get_conn = get_conn

    def get_memory_versions(
        self,
        memory_id: int,
        limit: int = 50
    ) -> list:
        """获取记忆的版本历史列表"""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """SELECT * FROM memory_versions
                   WHERE memory_id = %s
                   ORDER BY version DESC
                   LIMIT %s""",
                (memory_id, limit)
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get memory versions: {e}")
            return []
        finally:
            conn.close()

    def get_version_count(self, memory_id: int) -> int:
        """获取记忆的版本数量"""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) AS cnt FROM memory_versions WHERE memory_id = %s",
                (memory_id,)
            )
            row = cur.fetchone()
            return row["cnt"] if row else 0
        except Exception as e:
            logger.error(f"Failed to get version count: {e}")
            return 0
        finally:
            conn.close()

    def get_memory_version(self, memory_id: int, version: int) -> Optional[dict]:
        """获取指定版本的记忆快照"""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM memory_versions WHERE memory_id = %s AND version = %s",
                (memory_id, version)
            )
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get memory version: {e}")
            return None
        finally:
            conn.close()

    def insert_memory_version(
        self,
        memory_id: int,
        version: int,
        content: str,
        importance_score: float = 0.5,
        memory_type: Optional[str] = None,
        change_reason: str = "consolidation",
        source_memory_id: Optional[int] = None
    ) -> Optional[int]:
        """插入单条版本记录"""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO memory_versions
                   (memory_id, version, content, importance_score, memory_type,
                    change_reason, source_memory_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (memory_id, version, content, importance_score, memory_type,
                 change_reason, source_memory_id)
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert memory version: {e}")
            return None
        finally:
            conn.close()

    def batch_insert_memory_versions(self, versions: list) -> int:
        """批量插入版本记录

        Args:
            versions: [{"memory_id", "version", "content", "importance_score",
                        "memory_type", "change_reason", "source_memory_id"}, ...]

        Returns:
            成功插入的数量
        """
        if not versions:
            return 0
        conn = self._get_conn()
        try:
            conn.execute("START TRANSACTION")
            count = 0
            for v in versions:
                conn.execute(
                    """INSERT INTO memory_versions
                       (memory_id, version, content, importance_score, memory_type,
                        change_reason, source_memory_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (v.get("memory_id"), v.get("version"), v.get("content", ""),
                     v.get("importance_score", 0.5), v.get("memory_type"),
                     v.get("change_reason", "consolidation"), v.get("source_memory_id"))
                )
                count += 1
            conn.execute("COMMIT")
            return count
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"Failed to batch insert memory versions: {e}")
            return 0
        finally:
            conn.close()


_memory_versions_mapper: Optional[MemoryVersionsMapper] = None


def get_memory_versions_mapper() -> MemoryVersionsMapper:
    """获取 MemoryVersionsMapper 单例"""
    global _memory_versions_mapper
    if _memory_versions_mapper is None:
        _memory_versions_mapper = MemoryVersionsMapper()
    return _memory_versions_mapper