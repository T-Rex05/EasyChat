"""
知识库 Service - 知识库业务逻辑层
"""
import json
import re
from typing import Optional, List, Dict, Any
from backend.db.knowledge_base_mapper import KnowledgeBaseMapper


class KnowledgeBaseService:
    """知识库业务逻辑层"""
    
    def __init__(self):
        self.mapper = KnowledgeBaseMapper()
    
    def create_knowledge_base(
        self,
        kb_name: str,
        kb_type: str,
        description: str,
        user_id: int,
        is_enabled: int = 1
    ) -> Dict[str, Any]:
        """创建知识库"""
        kb_id = self.mapper.create_knowledge_base(
            kb_name=kb_name,
            kb_type=kb_type,
            description=description,
            user_id=user_id,
            is_enabled=is_enabled
        )
        return self.get_knowledge_base(kb_id)
    
    def get_knowledge_base(self, kb_id: int) -> Optional[Dict[str, Any]]:
        """获取知识库详情"""
        return self.mapper.get_knowledge_base(kb_id)
    
    def list_knowledge_bases(
        self,
        user_id: Optional[int] = None,
        kb_type: Optional[str] = None,
        is_enabled: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """获取知识库列表"""
        return self.mapper.list_knowledge_bases(
            user_id=user_id,
            kb_type=kb_type,
            is_enabled=is_enabled
        )
    
    def update_knowledge_base(
        self,
        kb_id: int,
        kb_name: Optional[str] = None,
        kb_type: Optional[str] = None,
        description: Optional[str] = None,
        is_enabled: Optional[int] = None
    ) -> bool:
        """更新知识库"""
        return self.mapper.update_knowledge_base(
            kb_id=kb_id,
            kb_name=kb_name,
            kb_type=kb_type,
            description=description,
            is_enabled=is_enabled
        )
    
    def delete_knowledge_base(self, kb_id: int) -> bool:
        """删除知识库（级联删除文档、分片、向量和磁盘文件）
        
        Raises:
            ValueError: 如果是系统内置知识库（is_system=1），禁止删除
        """
        from backend.db.schema import get_conn
        from backend.utils.log_utils import log, rag
        from pathlib import Path
        
        logger = log
        
        # 1. 查询知识库信息获取 user_id 和 is_system
        kb = self.mapper.get_knowledge_base(kb_id)
        if not kb:
            return False
        
        # 检查是否为系统内置知识库
        if kb.get("is_system"):
            raise ValueError(f"系统内置知识库不可删除: {kb.get('kb_name', '')}")
        
        user_id = kb.get("user_id")
        
        # 2. 查询知识库下所有文档
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT id, stored_name, vectorized FROM kb_documents WHERE kb_id = %s",
                (kb_id,)
            )
            docs = cur.fetchall() if hasattr(cur, "fetchall") else []
        finally:
            conn.close()
        
        # 3. 清理每个文档的向量和磁盘文件
        for doc in docs:
            doc_id = doc["id"]
            
            # 清理向量
            if doc.get("vectorized"):
                try:
                    from backend.service.kb.kb_retriever import unvectorize_document
                    unvectorize_document(user_id, doc_id)
                    logger.info(f"[KB] 已清理向量 doc_id={doc_id}")
                except Exception as e:
                    logger.warning(f"[KB] 清理向量失败 doc_id={doc_id}: {e}")
            
            # 清理磁盘文件
            if doc.get("stored_name"):
                try:
                    from backend.service.kb.kb_service import kb_root
                    stored_path = kb_root() / str(user_id) / doc["stored_name"]
                    if stored_path.exists():
                        stored_path.unlink()
                        logger.info(f"[KB] 已删除文件 {stored_path}")
                except Exception as e:
                    logger.warning(f"[KB] 删除文件失败 doc_id={doc_id}: {e}")
        
        # 4. 删除数据库记录（mapper 层会删除 chunks 和 documents）
        return self.mapper.delete_knowledge_base(kb_id)
    
    def get_or_create_default_kb(self, user_id: int) -> int:
        """获取或创建默认知识库"""
        return self.mapper.get_or_create_default_kb(user_id)
    
    def get_text2sql_kb(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取 Text2SQL 知识库（如果不存在则创建为系统内置）"""
        # 尝试获取 Text2SQL 知识库
        kbs = self.mapper.list_knowledge_bases(
            user_id=None,  # 系统内置，不按 user_id 过滤
            kb_type="text2sql"
        )
        if kbs:
            return kbs[0]
        
        # 创建 Text2SQL 知识库（标记为系统内置）
        kb_id = self.mapper.create_knowledge_base(
            kb_name="Text2SQL 参考案例",
            kb_type="text2sql",
            description="存储 SQL 查询参考案例，用于 RAG 双路召回",
            user_id=user_id,
            is_enabled=1,
            is_system=1  # 系统内置，不可删除
        )
        return self.mapper.get_knowledge_base(kb_id)
    
    def get_history_correct_kb(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取历史正确案例知识库（如果不存在则创建为系统内置）"""
        # 尝试获取历史正确案例知识库
        kbs = self.mapper.list_knowledge_bases(
            user_id=None,  # 系统内置，不按 user_id 过滤
            kb_type="history_correct"
        )
        if kbs:
            return kbs[0]
        
        # 创建历史正确案例知识库（标记为系统内置）
        kb_id = self.mapper.create_knowledge_base(
            kb_name="历史正确案例",
            kb_type="history_correct",
            description="存储用户点赞的正确 SQL 案例，用于 RAG 双路召回",
            user_id=user_id,
            is_enabled=1,
            is_system=1  # 系统内置，不可删除
        )
        return self.mapper.get_knowledge_base(kb_id)

    def candidate_kbs_for_route(self, user_id: int = 0) -> List[Dict[str, Any]]:
        """候选知识库 = 正在使用（is_enabled=1）且用户有权访问的知识库。

        与 Eyes _candidate_kbs_for_route 同构：带上 kb_name/description 供 LLM 依据简介判断相关性。

        【重要】按数据层级过滤：只返回用户部门可见的知识库，避免搜索不可见库浪费资源，
        也防止 selected_kbs 泄露受限知识库名称。
        """
        all_kbs = self.mapper.list_knowledge_bases(
            user_id=None,  # 不按 user_id 过滤，所有用户都能检索所有启用的知识库
            is_enabled=1,
        )
        if not all_kbs:
            return all_kbs

        # ── 数据层级过滤 ──
        from backend.service.auth.data_layer_service import get_user_layers
        user_layers = set(get_user_layers(user_id))

        # ⚠️ 这里**不能**因为"用户只有全员层 0"就跳过过滤：
        #   kb_data_layers 里显式挂了 layer=2 的库，对只有 {0} 的用户是不可见的；
        #   跳过过滤会把这类受限库的名称/简介一起喂给 LLM 路由器（泄露 + 浪费召回）。
        #   语义必须与 kb_retriever._filter_by_scope_layer 保持一致。

        # 批量查询 KB 层级关联
        kb_ids = [kb["id"] for kb in all_kbs]
        kb_layer_map: Dict[int, set] = {}  # kb_id -> set of layer_ids
        conn = None
        try:
            from backend.db.schema import get_conn
            conn = get_conn()
            placeholders = ",".join(["%s"] * len(kb_ids))
            cur = conn.execute(
                f"SELECT kb_id, layer_id FROM kb_data_layers WHERE kb_id IN ({placeholders})",
                kb_ids,
            )
            for row in (cur.fetchall() if hasattr(cur, "fetchall") else []):
                kb_id = row["kb_id"]
                if kb_id not in kb_layer_map:
                    kb_layer_map[kb_id] = set()
                kb_layer_map[kb_id].add(row["layer_id"])
        except Exception as e:
            # fail-closed：层级查不出来就**不返回任何候选库**，与
            # kb_retriever._filter_by_scope_layer（同样 fail-closed）保持一致。
            # 旧实现返回 all_kbs 属于 fail-open —— 授权边界在故障时被静默放大。
            import logging
            logging.getLogger(__name__).warning(
                f"[DataLayer] KB 层级查询失败 → 本次不返回任何候选知识库（fail-closed）: {e}"
            )
            return []
        finally:
            if conn is not None:
                conn.close()

        # 过滤：KB 层级与用户层级有交集 → 可见；KB 无层级记录 → 默认全员可见
        filtered = []
        for kb in all_kbs:
            kb_layers = kb_layer_map.get(kb["id"], {0})  # 无记录时默认全员可见
            if kb_layers & user_layers:
                filtered.append(kb)
        return filtered

    def llm_select_kbs(self, query: str, user_id: int, candidate_kbs: List[Dict]) -> List[int]:
        """让 LLM 从候选知识库里多选出与 query 相关的库，返回选中的 kb_id 列表。

        健壮回退（与 Eyes 同构）：
        - 候选库为空 → []
        - 只有 1 个候选 → 直接选它（省一次 LLM 调用）
        - LLM 不可用/调用异常/返回空/解析失败 → 回退为"选中全部候选库"
        """
        if not candidate_kbs:
            return []
        all_ids = [int(kb["id"]) for kb in candidate_kbs]
        if len(candidate_kbs) == 1:
            return all_ids
        try:
            from backend.utils.traced_llm import traced_llm
            catalog = "\n".join(
                f'- id={kb["id"]}，名称：{kb.get("kb_name") or ""}，简介：{(kb.get("description") or "").strip() or "（无描述）"}'
                for kb in candidate_kbs
            )
            prompt = (
                "你是 RAG 知识库路由器。下面是当前正在使用的知识库清单（每个库有 id、名称、简介）。\n"
                "请根据用户问题，从中挑选出所有可能包含答案的知识库，可以多选。\n"
                "只依据名称和简介判断相关性；宁可多选也不要漏掉可能相关的库。\n"
                "只输出严格 JSON，不要 Markdown，不要解释。格式固定为：{\"kb_ids\": [id, id, ...]}。\n"
                "如果无法判断，或候选库都可能相关，就返回全部候选库的 id。\n\n"
                f"知识库清单：\n{catalog}\n\n"
                f"用户问题：{query}"
            )
            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="rag_router",
                user_id=int(user_id or 0),
                source="rag",
                temperature=0,
                max_tokens=1024,
            )
            content = (resp.content or "").strip()
            match = re.search(r"\{.*\}", content, flags=re.S)
            if not match:
                return all_ids
            data = json.loads(match.group(0))
            raw_ids = data.get("kb_ids") if isinstance(data, dict) else None
            if not isinstance(raw_ids, list):
                return all_ids
            valid = set(all_ids)
            selected = []
            for raw_id in raw_ids:
                try:
                    rid = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if rid in valid and rid not in selected:
                    selected.append(rid)
            return selected or all_ids
        except Exception as exc:
            from backend.utils.log_utils import log, rag
            log.warning(f"⚠️ RAG LLM 选库失败，回退为检索全部候选库: {exc}")
            return all_ids
