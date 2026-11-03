"""
Graph Change Log Mapper - 知识图谱变更日志数据访问

负责记录知识图谱的每次修改操作（实体/关系的增删改），支持：
- 审计追溯：谁在什么时间改了什么
- 回滚支持：通过 before_json 恢复到修改前状态
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log


class GraphChangeLogMapper:
    """知识图谱变更日志 Mapper"""

    def insert(
        self,
        user_id: int,
        event_type: str,
        entity_id: Optional[str] = None,
        entity_name: str = "",
        entity_type: str = "",
        before: Optional[Dict] = None,
        after: Optional[Dict] = None,
        ip_address: str = "",
    ) -> Optional[int]:
        """
        插入一条变更日志

        Returns:
            新记录ID，失败返回 None
        """
        conn = get_conn()
        try:
            before_json = json.dumps(before, ensure_ascii=False) if before else None
            after_json = json.dumps(after, ensure_ascii=False) if after else None

            sql = """
                INSERT INTO graph_change_log
                (user_id, event_type, entity_id, entity_name, entity_type,
                 before_json, after_json, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur = conn.execute(sql, (
                user_id, event_type, entity_id, entity_name, entity_type,
                before_json, after_json, ip_address
            ))
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.warning(f"[GraphChangeLog] insert failed: {e}")
            return None
        finally:
            conn.close()

    def list_by_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询用户的变更历史
        """
        conn = get_conn()
        try:
            if event_type:
                sql = """
                    SELECT id, user_id, event_type, entity_id, entity_name,
                           entity_type, before_json, after_json, ip_address, created_at
                    FROM graph_change_log
                    WHERE user_id = %s AND event_type = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                cur = conn.execute(sql, (user_id, event_type, limit, offset))
            else:
                sql = """
                    SELECT id, user_id, event_type, entity_id, entity_name,
                           entity_type, before_json, after_json, ip_address, created_at
                    FROM graph_change_log
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                cur = conn.execute(sql, (user_id, limit, offset))

            rows = cur.fetchall() if hasattr(cur, 'fetchall') else []

            result = []
            for row in rows:
                item = dict(row)
                if isinstance(item.get("before_json"), str):
                    item["before_json"] = json.loads(item["before_json"])
                if isinstance(item.get("after_json"), str):
                    item["after_json"] = json.loads(item["after_json"])
                result.append(item)
            return result
        except Exception as e:
            logger.warning(f"[GraphChangeLog] list_by_user failed: {e}")
            return []
        finally:
            conn.close()

    def list_by_entity(
        self,
        entity_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        查询某个实体的变更历史
        """
        conn = get_conn()
        try:
            sql = """
                SELECT id, user_id, event_type, entity_id, entity_name,
                       entity_type, before_json, after_json, ip_address, created_at
                FROM graph_change_log
                WHERE entity_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            cur = conn.execute(sql, (entity_id, limit))
            rows = cur.fetchall() if hasattr(cur, 'fetchall') else []

            result = []
            for row in rows:
                item = dict(row)
                if isinstance(item.get("before_json"), str):
                    item["before_json"] = json.loads(item["before_json"])
                if isinstance(item.get("after_json"), str):
                    item["after_json"] = json.loads(item["after_json"])
                result.append(item)
            return result
        except Exception as e:
            logger.warning(f"[GraphChangeLog] list_by_entity failed: {e}")
            return []
        finally:
            conn.close()

    def get_by_id(self, log_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取单条日志"""
        conn = get_conn()
        try:
            sql = """
                SELECT id, user_id, event_type, entity_id, entity_name,
                       entity_type, before_json, after_json, ip_address, created_at
                FROM graph_change_log
                WHERE id = %s
            """
            cur = conn.execute(sql, (log_id,))
            row = cur.fetchone()

            if not row:
                return None

            item = dict(row)
            if isinstance(item.get("before_json"), str):
                item["before_json"] = json.loads(item["before_json"])
            if isinstance(item.get("after_json"), str):
                item["after_json"] = json.loads(item["after_json"])
            return item
        except Exception as e:
            logger.warning(f"[GraphChangeLog] get_by_id failed: {e}")
            return None
        finally:
            conn.close()

    def count_by_user(self, user_id: int) -> int:
        """统计用户的变更日志数量"""
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) as cnt FROM graph_change_log WHERE user_id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            return row.get("cnt", 0) if row else 0
        except Exception as e:
            logger.warning(f"[GraphChangeLog] count_by_user failed: {e}")
            return 0
        finally:
            conn.close()


# 全局实例
_mapper: Optional[GraphChangeLogMapper] = None


def get_graph_change_log_mapper() -> GraphChangeLogMapper:
    """获取 GraphChangeLogMapper 单例"""
    global _mapper
    if _mapper is None:
        _mapper = GraphChangeLogMapper()
    return _mapper
