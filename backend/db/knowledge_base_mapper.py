"""
知识库 Mapper - 知识库表的 CRUD 操作
"""
from typing import Optional, List, Dict, Any
from backend.db.schema import get_conn


class KnowledgeBaseMapper:
    """知识库数据访问层"""
    
    def create_knowledge_base(
        self,
        kb_name: str,
        kb_type: str,
        description: str,
        user_id: int,
        is_enabled: int = 1,
        is_system: int = 0
    ) -> int:
        """创建知识库，返回知识库ID
        
        Args:
            is_system: 是否为系统内置知识库（不可删除）
        """
        conn = get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO kb_knowledge_base 
                   (kb_name, kb_type, description, user_id, is_enabled, is_system) 
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (kb_name, kb_type, description, user_id, is_enabled, is_system)
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()
    
    def get_knowledge_base(self, kb_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取知识库"""
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM kb_knowledge_base WHERE id = %s",
                (kb_id,)
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return rows[0] if rows else None
        finally:
            conn.close()
    
    def list_knowledge_bases(
        self,
        user_id: Optional[int] = None,
        kb_type: Optional[str] = None,
        is_enabled: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """获取知识库列表"""
        conn = get_conn()
        try:
            sql = "SELECT * FROM kb_knowledge_base WHERE 1=1"
            params = []
            
            if user_id is not None:
                sql += " AND user_id = %s"
                params.append(user_id)
            
            if kb_type is not None:
                sql += " AND kb_type = %s"
                params.append(kb_type)
            
            if is_enabled is not None:
                sql += " AND is_enabled = %s"
                params.append(is_enabled)
            
            sql += " ORDER BY created_at DESC"
            
            cur = conn.execute(sql, tuple(params))
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return rows
        finally:
            conn.close()
    
    def update_knowledge_base(
        self,
        kb_id: int,
        kb_name: Optional[str] = None,
        kb_type: Optional[str] = None,
        description: Optional[str] = None,
        is_enabled: Optional[int] = None
    ) -> bool:
        """更新知识库"""
        conn = get_conn()
        try:
            updates = []
            params = []
            
            if kb_name is not None:
                updates.append("kb_name = %s")
                params.append(kb_name)
            
            if kb_type is not None:
                updates.append("kb_type = %s")
                params.append(kb_type)
            
            if description is not None:
                updates.append("description = %s")
                params.append(description)
            
            if is_enabled is not None:
                updates.append("is_enabled = %s")
                params.append(is_enabled)
            
            if not updates:
                return False
            
            params.append(kb_id)
            sql = f"UPDATE kb_knowledge_base SET {', '.join(updates)} WHERE id = %s"
            
            conn.execute(sql, tuple(params))
            conn.commit()
            return True
        finally:
            conn.close()
    
    def delete_knowledge_base(self, kb_id: int) -> bool:
        """删除知识库（级联删除文档和分片）
        
        Raises:
            ValueError: 如果是系统内置知识库（is_system=1），禁止删除
        """
        conn = get_conn()
        try:
            # 检查是否为系统内置知识库
            cur = conn.execute(
                "SELECT is_system, kb_name FROM kb_knowledge_base WHERE id = %s",
                (kb_id,)
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if not rows:
                return False  # 知识库不存在
            
            kb = rows[0]
            if kb.get("is_system"):
                raise ValueError(f"系统内置知识库不可删除: {kb.get('kb_name', '')}")
            
            # 先删除分片
            conn.execute(
                "DELETE FROM kb_chunks WHERE kb_id = %s",
                (kb_id,)
            )
            # 再删除文档
            conn.execute(
                "DELETE FROM kb_documents WHERE kb_id = %s",
                (kb_id,)
            )
            # 最后删除知识库
            conn.execute(
                "DELETE FROM kb_knowledge_base WHERE id = %s",
                (kb_id,)
            )
            conn.commit()
            return True
        finally:
            conn.close()
    
    def get_or_create_default_kb(self, user_id: int) -> int:
        """获取或创建默认知识库"""
        conn = get_conn()
        try:
            # 尝试获取默认知识库
            cur = conn.execute(
                "SELECT id FROM kb_knowledge_base WHERE kb_name = '默认知识库' AND user_id = %s",
                (user_id,)
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                return rows[0]["id"]
            
            # 创建默认知识库
            kb_id = self.create_knowledge_base(
                kb_name="默认知识库",
                kb_type="general",
                description="系统默认知识库",
                user_id=user_id,
                is_enabled=1
            )
            return kb_id
        finally:
            conn.close()
