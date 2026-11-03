"""
知识图谱审核候选 Mapper - kg_alignment_candidates 表的 CRUD 操作
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from backend.db.schema import get_conn


class KgCandidateMapper:
    """知识图谱审核候选数据访问层"""

    def insert_candidate(
        self,
        user_id: int,
        candidate_type: str,
        entity_a_id: str,
        entity_a_name: str = "",
        entity_b_id: Optional[str] = None,
        entity_b_name: str = "",
        score: Optional[float] = None,
        reason: str = ""
    ) -> int:
        """插入审核候选，返回候选 ID"""
        conn = get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO kg_alignment_candidates
                   (user_id, candidate_type, entity_a_id, entity_a_name,
                    entity_b_id, entity_b_name, score, reason)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (user_id, candidate_type, entity_a_id, entity_a_name,
                 entity_b_id, entity_b_name, score, reason)
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def list_candidates(
        self,
        user_id: int,
        status: Optional[str] = None,
        candidate_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """分页查询审核候选

        Returns:
            (candidates_list, total_count)
        """
        conn = get_conn()
        try:
            where_clauses = ["user_id = %s"]
            params: list = [user_id]

            if status:
                where_clauses.append("status = %s")
                params.append(status)
            if candidate_type:
                where_clauses.append("candidate_type = %s")
                params.append(candidate_type)

            where_sql = " AND ".join(where_clauses)

            # 查总数
            cur = conn.execute(
                f"SELECT COUNT(*) as total FROM kg_alignment_candidates WHERE {where_sql}",
                tuple(params)
            )
            total = cur.fetchone().get("total", 0) if hasattr(cur, "fetchone") else 0

            # 查数据
            offset = (page - 1) * page_size
            params.extend([page_size, offset])
            cur = conn.execute(
                f"""SELECT * FROM kg_alignment_candidates
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s""",
                tuple(params)
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return list(rows), total
        finally:
            conn.close()

    def update_status(self, candidate_id: int, status: str) -> bool:
        """更新候选状态（同时设置 reviewed_at）"""
        conn = get_conn()
        try:
            conn.execute(
                """UPDATE kg_alignment_candidates
                   SET status = %s, reviewed_at = %s
                   WHERE id = %s""",
                (status, datetime.now(), candidate_id)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_candidate(self, candidate_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取单条候选"""
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM kg_alignment_candidates WHERE id = %s",
                (candidate_id,)
            )
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            return dict(row) if row else None
        finally:
            conn.close()

    def count_pending(self, user_id: int) -> int:
        """统计待审核数量"""
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) as cnt FROM kg_alignment_candidates WHERE user_id = %s AND status = 'pending'",
                (user_id,)
            )
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            return row.get("cnt", 0) if row else 0
        finally:
            conn.close()

    def delete_candidate(self, candidate_id: int) -> bool:
        """删除候选记录"""
        conn = get_conn()
        try:
            conn.execute(
                "DELETE FROM kg_alignment_candidates WHERE id = %s",
                (candidate_id,)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def exists_pending(
        self,
        user_id: int,
        candidate_type: str,
        entity_a_id: str,
        entity_b_id: Optional[str] = None
    ) -> bool:
        """检查是否已存在相同的待审核候选（避免重复写入）"""
        conn = get_conn()
        try:
            if entity_b_id:
                cur = conn.execute(
                    """SELECT COUNT(*) as cnt FROM kg_alignment_candidates
                       WHERE user_id = %s AND candidate_type = %s
                       AND entity_a_id = %s AND entity_b_id = %s AND status = 'pending'""",
                    (user_id, candidate_type, entity_a_id, entity_b_id)
                )
            else:
                cur = conn.execute(
                    """SELECT COUNT(*) as cnt FROM kg_alignment_candidates
                       WHERE user_id = %s AND candidate_type = %s
                       AND entity_a_id = %s AND entity_b_id IS NULL AND status = 'pending'""",
                    (user_id, candidate_type, entity_a_id)
                )
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            return (row.get("cnt", 0) if row else 0) > 0
        finally:
            conn.close()
