"""
Memory Service - 记忆管理服务

负责:
- 记忆 CRUD 操作（使用 Outbox 模式确保一致性）
- 向量化存储（通过 Outbox 异步调用 MilvusClient）
- 滑动窗口轮次管理
- 记忆检索（向量相似度搜索）

Outbox 模式：
- 业务数据 + 同步事件在同一事务中提交
- 后台 Worker 异步消费事件，更新派生库
- 确保数据不会丢失，支持重试和对账
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.db.memory_mapper import (
    EpisodicMapper, get_episodic_mapper,
    SemanticMapper, get_semantic_mapper,
    RoundsMapper, get_rounds_mapper,
)
from backend.infrastructure.safe_executor import go_safe
from backend.utils.log_utils import log

logger = log


def _normalize_memory(mem: dict, layer: str) -> dict:
    """
    统一记忆格式

    不同层的表结构略有差异，这里统一字段名。
    """
    return {
        "id": mem.get("id"),
        "user_id": mem.get("user_id"),
        "memory_type": mem.get("memory_type", "fact"),
        "content": mem.get("content", ""),
        "importance_score": mem.get("importance_score", 0.5),
        "access_count": mem.get("access_count", 0),
        "created_at": mem.get("created_at"),
        "updated_at": mem.get("updated_at"),
        "embedding_id": mem.get("embedding_id", ""),
        # 标记来源层
        "_memory_layer": layer
    }


class MemoryService:
    """记忆管理服务"""
    
    # 记忆类型定义
    MEMORY_TYPES = ["preference", "fact", "event", "skill"]
    
    def __init__(
        self,
        delay_rounds: int = 10,
        ttl_days: int = 60,
        decay_rate: float = 0.95
    ):
        """
        初始化记忆服务
        
        Args:
            delay_rounds: 延迟存储轮次（达到此轮次才提取记忆）
            ttl_days: 默认存活天数
            decay_rate: 默认衰减率
        """
        self._rounds_mapper = get_rounds_mapper()
        self._episodic_mapper = get_episodic_mapper()
        self._semantic_mapper = get_semantic_mapper()
        self._delay_rounds = delay_rounds
        self._ttl_days = ttl_days
        self._episodic_ttl_days = 30  # 近期记忆默认 30 天
        self._decay_rate = decay_rate
        
        # 嵌入模型（延迟加载）
        self._embedding_model = None
    
    def _get_embedding_model(self):
        """获取嵌入模型（延迟加载）"""
        if self._embedding_model is None:
            try:
                from langchain_openai import OpenAIEmbeddings
                from backend.db.schema import get_conn
                from backend.utils.crypto_utils import decrypt
                
                # 从 model_configs 表获取 embedding 类型的配置
                conn = get_conn()
                try:
                    cur = conn.execute(
                        """SELECT id, config_name, model_name, api_url, api_key
                           FROM model_configs
                           WHERE category = 'embedding' AND is_current = 1 AND enabled = 1
                           LIMIT 1"""
                    )
                    row = cur.fetchone()

                    if row:
                        config = dict(row)
                        api_key_encrypted = config.get("api_key", "")
                        base_url = config.get("api_url", "")
                        model_name = config.get("model_name", "text-embedding-3-small")

                        # 解密 API Key
                        api_key = ""
                        if api_key_encrypted:
                            try:
                                api_key = decrypt(api_key_encrypted)
                            except Exception as e:
                                logger.warning(f"Failed to decrypt API key: {e}")

                        if api_key and base_url:
                            self._embedding_model = OpenAIEmbeddings(
                                model=model_name,
                                openai_api_key=api_key,
                                openai_api_base=base_url
                            )
                            logger.info(f"Loaded embedding model: {model_name}")
                        else:
                            logger.warning("Embedding config missing api_key or api_url")
                    else:
                        logger.warning("No active embedding config found")
                finally:
                    conn.close()
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
        return self._embedding_model
    
    def _get_vector_client(self):
        """获取向量客户端"""
        from backend.infrastructure import get_memory_client
        return get_memory_client()
    
    # ========== 滑动窗口轮次管理 ==========
    
    def process_round(
        self,
        thread_id: str,
        user_id: int,
        message: str
    ) -> Tuple[bool, int]:
        """
        处理轮次计数
        
        Args:
            thread_id: 会话ID
            user_id: 用户ID
            message: 用户消息
            
        Returns:
            (should_extract, current_round)
            - should_extract: 是否应该提取记忆
            - current_round: 当前轮次（计数失败时为 0，且 should_extract=False）

        容错约定：轮次计数失败**不向上冒到对话主链路**，但必须记 error 级日志。
        （此前 mapper 层吞异常返回 0，会让调用方以为"轮次为 0、无需提取"，
          且计数未推进 → 记忆提取永久静默停机，用户以为记住了实际一条没落库。）
        """
        # 计算消息哈希（防重）
        message_hash = hashlib.md5(message.encode()).hexdigest()[:16]

        # 增加轮次（失败时按"本轮不提取"处理，并留 error 日志）
        try:
            round_count = self._rounds_mapper.increment_round(thread_id, user_id, message_hash)
        except Exception as e:
            logger.error(
                f"记忆轮次计数失败，本轮跳过提取（不影响对话）"
                f" thread_id={thread_id} user_id={user_id}: {e}"
            )
            return False, 0

        # 判断是否达到提取阈值
        should_extract = round_count > 0 and round_count % self._delay_rounds == 0

        return should_extract, round_count
    
    def get_round_count(self, thread_id: str) -> int:
        """获取当前轮次"""
        return self._rounds_mapper.get_round_count(thread_id)
    
    # ========== 记忆 CRUD（使用 Outbox 模式）==========
    
    def create_memory(
        self,
        user_id: int,
        memory_type: str,
        content: str,
        importance_score: float = 0.5,
        source_thread_id: str = "",
        source_round: int = 0,
        vectorize: bool = True,
        **_kwargs  # 兼容旧调用中的 extract_graph 等参数
    ) -> Optional[int]:
        """
        创建记忆（兼容入口，统一写入 episodic 层）

        新代码请直接调用 create_episodic() 或 create_semantic()。
        """
        return self.create_episodic(
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            importance_score=importance_score,
            source_thread_id=source_thread_id,
            source_round=source_round,
            vectorize=vectorize,
        )
    
    def get_memory(self, memory_id: int, user_id: Optional[int] = None) -> Optional[dict]:
        """获取记忆（层级感知：先 episodic，后 semantic）

        Args:
            memory_id: 记忆 ID
            user_id: 可选，传入时在 SQL 层校验归属，防止跨层 ID 碰撞导致查到他人记忆
        """
        # SQL 级别 user_id 过滤：传入 user_id 时 mapper 只返回归属匹配的记录
        memory = self._episodic_mapper.get_memory_by_id(memory_id, user_id=user_id)
        if memory:
            self._episodic_mapper.increment_access_count(memory_id)
            memory["memory_layer"] = "episodic"
            return memory
        # episodic 未命中，查 semantic
        memory = self._semantic_mapper.get_memory_by_id(memory_id, user_id=user_id)
        if memory:
            self._semantic_mapper.increment_access_count(memory_id)
            memory["memory_layer"] = "semantic"
            return memory
        return None
    
    def get_user_memories(
        self,
        user_id: Optional[int] = None,
        memory_type: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        获取用户记忆列表（双层合并）

        Args:
            user_id: 用户ID（None 表示所有用户）
            memory_type: 记忆类型过滤
            limit: 返回数量限制
        """
        if user_id is None:
            return []
        result = []
        for m in self._episodic_mapper.get_memories_by_user(
            user_id=user_id, memory_type=memory_type, limit=limit
        ):
            m["memory_layer"] = "episodic"
            result.append(m)
        for m in self._semantic_mapper.get_memories_by_user(
            user_id=user_id, memory_type=memory_type, limit=limit
        ):
            m["memory_layer"] = "semantic"
            result.append(m)
        return result
    
    def update_memory(
        self,
        memory_id: int,
        content: Optional[str] = None,
        importance_score: Optional[float] = None,
        is_user_edited: Optional[bool] = None,
        re_vectorize: bool = True,
        user_id: Optional[int] = None,
        layer: Optional[str] = None
    ) -> bool:
        """
        更新记忆（使用 Outbox 模式，层级感知）

        Args:
            memory_id: 记忆ID
            content: 新内容（可选）
            importance_score: 新重要性分数（可选）
            is_user_edited: 是否用户手动编辑（可选）
            re_vectorize: 是否重新向量化（默认 True）
            user_id: 可选，传入时校验归属
            layer: 可选，显式指定层级（"episodic"/"semantic"），避免删错层

        Returns:
            是否成功
        """
        from backend.db.schema import get_conn
        from backend.service.memory.outbox_types import (
            OutboxEvent, EventType, Target,
            compute_content_hash, make_vector_payload, make_graph_payload
        )
        from backend.service.memory.outbox_writer import get_outbox_writer

        # 查找记忆所在层（显式 layer 优先）
        layer = self._find_memory_layer_for_id(memory_id, user_id=user_id, layer=layer)
        if not layer:
            logger.warning(f"Memory {memory_id} not found in any layer")
            return False

        mapper = self._episodic_mapper if layer == "episodic" else self._semantic_mapper
        memory = mapper.get_memory_by_id(memory_id, user_id=user_id)
        if not memory or memory.get("deleted_at"):
            logger.warning(f"Memory {memory_id} not found or deleted")
            return False

        # 归属校验：传入 user_id 时，必须匹配
        if user_id is not None and memory.get("user_id") != user_id:
            logger.warning(f"User {user_id} cannot update memory {memory_id} (belongs to user {memory.get('user_id')})")
            return False

        current_version = memory.get("version", 1)
        events: List[OutboxEvent] = []

        # 计算新的内容哈希
        new_content_hash = None
        if content is not None:
            new_content_hash = compute_content_hash(
                content,
                memory.get("memory_type", "general"),
                importance_score or memory.get("importance_score", 0.5)
            )

        conn = get_conn()
        outbox_writer = get_outbox_writer()

        try:
            # 1. 更新业务数据（乐观锁）
            success, new_version = mapper.update_memory(
                memory_id=memory_id,
                content=content,
                importance_score=importance_score,
                is_user_edited=is_user_edited,
                content_hash=new_content_hash,
                expected_version=current_version,
                user_id=user_id,
                conn=conn
            )

            if not success:
                logger.warning(f"Update memory {memory_id} failed: version conflict "
                               f"(layer={layer}, expected_version={current_version})")
                conn.rollback()
                return False

            # 2. 生成同步事件
            if re_vectorize and content:
                events.append(OutboxEvent.create(
                    memory_id=memory_id,
                    memory_version=new_version,
                    event_type=EventType.UPSERT_VECTOR,
                    target=Target.MILVUS,
                    payload=make_vector_payload(
                        content,
                        memory.get("memory_type", "general"),
                        importance_score or memory.get("importance_score", 0.5),
                        memory.get("user_id"),
                        memory_layer=layer
                    )
                ))

                # 只有 semantic 层才生成图节点事件（episodic 不入图）
                if layer == "semantic":
                    events.append(OutboxEvent.create(
                        memory_id=memory_id,
                        memory_version=new_version,
                        event_type=EventType.UPSERT_GRAPH_NODE,
                        target=Target.NEO4J,
                        payload=make_graph_payload(
                            content,
                            memory.get("memory_type", "general"),
                            importance_score or memory.get("importance_score", 0.5),
                            memory.get("user_id"),
                            memory_layer=layer
                        )
                    ))

            # 3. 写入 Outbox
            if events and not outbox_writer.write_events(conn, events, memory_layer=layer):
                conn.rollback()
                logger.error(f"Failed to write outbox events for memory {memory_id}")
                return False

            # 提交事务
            conn.commit()
            logger.info(f"Updated {layer} memory {memory_id} (version {current_version} -> {new_version})")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update memory: {e}")
            return False
        finally:
            conn.close()

    def _find_memory_layer_for_id(self, memory_id: int, user_id: Optional[int] = None,
                                  layer: Optional[str] = None) -> Optional[str]:
        """查找记忆所在层级。

        Args:
            memory_id: 记忆ID
            user_id: 可选，传入时校验归属
            layer: 显式传入的层级（"episodic"/"semantic"），直接使用，不推断

        Returns:
            层级名称或 None
        """
        # 显式给了 layer 就直接用（id 在两张表里会重号，不能靠推断）
        if layer in ("episodic", "semantic"):
            return layer
        mem = self._episodic_mapper.get_memory_by_id(memory_id, user_id=user_id)
        if mem:
            return "episodic"
        mem = self._semantic_mapper.get_memory_by_id(memory_id, user_id=user_id)
        if mem:
            return "semantic"
        return None

    def delete_memory(self, memory_id: int, user_id: Optional[int] = None, layer: Optional[str] = None) -> bool:
        """
        删除记忆（使用 Outbox 模式，层级感知，软删除）

        Args:
            memory_id: 记忆ID
            user_id: 可选，传入时校验归属
            layer: 可选，显式指定层级（"episodic"/"semantic"），避免删错层
        """
        from backend.db.schema import get_conn
        from backend.service.memory.outbox_types import (
            OutboxEvent, EventType, Target
        )
        from backend.service.memory.outbox_writer import get_outbox_writer

        # 查找记忆所在层（显式 layer 优先）
        layer = self._find_memory_layer_for_id(memory_id, user_id=user_id, layer=layer)
        if not layer:
            logger.warning(f"Memory {memory_id} not found in any layer")
            return False

        mapper = self._episodic_mapper if layer == "episodic" else self._semantic_mapper
        memory = mapper.get_memory_by_id(memory_id, user_id=user_id)
        if not memory:
            return False

        # 归属校验
        if user_id is not None and memory.get("user_id") != user_id:
            logger.warning(f"User {user_id} cannot delete memory {memory_id} (belongs to user {memory.get('user_id')})")
            return False

        current_version = memory.get("version", 1)
        events: List[OutboxEvent] = []

        conn = get_conn()
        outbox_writer = get_outbox_writer()

        try:
            # 1. 软删除
            success = mapper.soft_delete(memory_id, user_id=user_id, conn=conn)
            if not success:
                conn.rollback()
                return False

            # 2. 生成删除事件
            # 始终创建 delete_vector 事件：即使 embedding_id 为空（向量可能已由
            # outbox worker 异步写入 Milvus，但 embedding_id 回写失败），
            # 也需要确保 Milvus 中的向量被清理（vector_id 固定为 f"mem_{memory_id}"）
            events.append(OutboxEvent.create(
                memory_id=memory_id,
                memory_version=current_version,
                event_type=EventType.DELETE_VECTOR,
                target=Target.MILVUS,
                payload={
                    "embedding_id": memory.get("embedding_id") or f"mem_{memory_id}",
                    "memory_id": memory_id,
                    "user_id": memory.get("user_id"),
                    "memory_layer": layer
                }
            ))

            if layer == "semantic":
                events.append(OutboxEvent.create(
                    memory_id=memory_id,
                    memory_version=current_version,
                    event_type=EventType.DELETE_GRAPH_NODE,
                    target=Target.NEO4J,
                    payload={"memory_layer": layer, "user_id": memory.get("user_id")}
                ))

            # 3. 写入 Outbox
            if events and not outbox_writer.write_events(conn, events, memory_layer=layer):
                conn.rollback()
                logger.error(f"Failed to write delete events for memory {memory_id}")
                return False

            # 提交事务
            conn.commit()
            logger.info(f"Deleted {layer} memory {memory_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete memory: {e}")
            return False
        finally:
            conn.close()

    # ========== 检索 ==========
    
    def _get_embeddings(self, texts: list) -> Optional[list]:
        """
        获取文本的 embedding 向量（兼容阿里云等 API）
        
        Args:
            texts: 文本列表
            
        Returns:
            embedding 向量列表
        """
        from backend.db.schema import get_conn
        from backend.utils.crypto_utils import decrypt
        import requests

        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            # 获取 embedding 配置
            conn = get_conn()
            cur = conn.execute(
                """SELECT model_name, api_url, api_key, dimension, send_dimensions
                   FROM model_configs 
                   WHERE category = 'embedding' AND is_current = 1 AND enabled = 1
                   LIMIT 1"""
            )
            row = cur.fetchone()
            
            if not row:
                logger.warning("No embedding config found")
                return None
            
            config = dict(row)
            api_key = decrypt(config["api_key"])
            base_url = config["api_url"].rstrip("/")
            model_name = config["model_name"]
            
            # 维度配置：仅当 send_dimensions=1 且 dimension>0 时传给 API
            _dim = int(config.get("dimension") or 0)
            _send_dim = bool(config.get("send_dimensions"))
            dimension = _dim if (_send_dim and _dim > 0) else None
            
            # 调用 embedding API（兼容 OpenAI 和阿里云格式）
            url = f"{base_url}/embeddings"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model_name,
                "input": texts,  # 阿里云要求 input 是数组
            }
            # 仅当配置了维度时才传给 API（部分模型支持如 text-embedding-3-*）
            if dimension is not None:
                payload["dimensions"] = dimension
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            
            return embeddings
            
        except Exception as e:
            logger.warning(f"Failed to get embeddings: {e}")
            return None
        finally:
            if conn is not None:
                conn.close()

    def search_memories(
        self,
        user_id: int,
        query: str,
        top_k: int = 10,
        memory_type: Optional[str] = None,
        min_score: float = 0.5
    ) -> list:
        """
        搜索相似记忆
        
        Args:
            user_id: 用户ID
            query: 查询文本
            top_k: 返回数量
            memory_type: 记忆类型过滤
            min_score: 最小相似度
            
        Returns:
            记忆列表 [{memory, score}, ...]
        """
        vector_client = self._get_vector_client()
        if not vector_client or not vector_client.is_available():
            # 降级到关键词搜索
            return self._keyword_search(user_id, query, top_k, memory_type)
        
        # 获取查询向量
        query_embeddings = self._get_embeddings([query])
        if not query_embeddings:
            return self._keyword_search(user_id, query, top_k, memory_type)
        
        query_embedding = query_embeddings[0]
        
        try:
            # 向量搜索
            collection_name = f"user_{user_id}_memories"
            results = vector_client.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                top_k=top_k * 2  # 多取一些用于过滤
            )

            memories = []
            for hit in results:
                score = hit.get("score", 0)
                if score < min_score:
                    continue

                metadata = hit.get("metadata", {})
                if memory_type and metadata.get("memory_type") != memory_type:
                    continue

                memory_id = metadata.get("memory_id")
                if memory_id:
                    # 根据 memory_layer 从对应的表加载记忆（强制 user_id 校验，防跨用户泄露）
                    memory_layer = metadata.get("memory_layer", "legacy")
                    memory = self._get_memory_by_id_from_layer(memory_id, memory_layer, user_id=user_id)
                    if memory:
                        # 防御性二次校验：确保 MySQL 返回的记忆确实属于当前用户
                        mem_user_id = memory.get("user_id")
                        if mem_user_id is not None and int(mem_user_id) != int(user_id):
                            logger.warning(
                                f"⚠️ 记忆隔离告警: memory_id={memory_id} 属于 user={mem_user_id}，"
                                f"但被 user={user_id} 的向量检索命中（向量库可能残留脏数据）"
                            )
                            continue
                        # 增加访问计数
                        self._increment_access_count_in_layer(memory_id, memory_layer)
                        memories.append({
                            "memory": memory,
                            "score": score
                        })

            # 按分数排序
            memories.sort(key=lambda x: x["score"], reverse=True)
            return memories[:top_k]

        except Exception as e:
            logger.warning(f"Vector search failed, fallback to keyword: {e}")
            return self._keyword_search(user_id, query, top_k, memory_type)

    def _get_memory_by_id_from_layer(self, memory_id: int, memory_layer: str,
                                      user_id: Optional[int] = None) -> Optional[dict]:
        """根据记忆层级从对应的表加载记忆

        Args:
            memory_id: 记忆ID
            memory_layer: 记忆层级（episodic/semantic）
            user_id: 用户ID（传入时强制校验归属，防止跨用户数据泄露）
        """
        if memory_layer == "episodic":
            return self._episodic_mapper.get_memory_by_id(memory_id, user_id=user_id)
        elif memory_layer == "semantic":
            return self._semantic_mapper.get_memory_by_id(memory_id, user_id=user_id)
        else:
            logger.debug(f"Unknown memory_layer '{memory_layer}', trying episodic then semantic")
            mem = self._episodic_mapper.get_memory_by_id(memory_id, user_id=user_id)
            if mem:
                return mem
            return self._semantic_mapper.get_memory_by_id(memory_id, user_id=user_id)

    def _increment_access_count_in_layer(self, memory_id: int, memory_layer: str) -> None:
        """根据记忆层级增加访问计数

        Episodic 层：同时微增 importance（在 mapper SQL 中完成），
                     并异步检查是否达到自动晋升阈值。
        """
        try:
            if memory_layer == "episodic":
                self._episodic_mapper.increment_access_count(memory_id)
                # 异步检查是否达到晋升阈值（不阻塞检索路径）
                go_safe(
                    "memory.auto_promote",
                    lambda: self._try_auto_promote_episodic(memory_id)
                )
            elif memory_layer == "semantic":
                self._semantic_mapper.increment_access_count(memory_id)
            else:
                # 未知层，尝试两层
                self._episodic_mapper.increment_access_count(memory_id)
        except Exception as e:
            logger.debug(f"Failed to increment access count: {e}")

    def _try_auto_promote_episodic(self, memory_id: int) -> None:
        """尝试自动晋升近期记忆为永久知识

        当 episodic 记忆的 importance_score >= 阈值（默认 0.85）时，
        自动调用 promote_to_semantic 晋升为永久知识。

        触发时机：每次检索命中后异步调用（由 _increment_access_count_in_layer 触发）。
        晋升后 episodic 记忆被软删除，语义层创建新记录 + 向量 + 图节点。
        """
        threshold = float(os.getenv("MEMORY_AUTO_PROMOTE_THRESHOLD", "0.85"))
        try:
            episodic = self._episodic_mapper.get_memory_by_id(memory_id)
            if not episodic:
                return

            importance = float(episodic.get("importance_score", 0))
            if importance < threshold:
                return

            user_id = episodic.get("user_id")
            if not user_id:
                return

            semantic_id = self.promote_to_semantic(memory_id, user_id)
            if semantic_id:
                logger.info(
                    f"Auto-promoted episodic {memory_id} → semantic {semantic_id} "
                    f"(importance={importance:.3f} >= {threshold})"
                )
        except Exception as e:
            logger.warning(f"Auto-promote failed for episodic {memory_id}: {e}")
    
    def _keyword_search(
        self,
        user_id: int,
        query: str,
        limit: int = 10,
        memory_type: Optional[str] = None
    ) -> list:
        """
        关键词搜索（降级方案）

        从 episodic + semantic 两层查询，用 LIKE 匹配。
        """
        query_lower = query.lower()
        results = []

        # episodic 层
        memories = self._episodic_mapper.get_memories_by_user(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit * 2
        )
        for memory in memories:
            if query_lower in memory.get("content", "").lower():
                memory["memory_layer"] = "episodic"
                results.append({"memory": memory, "score": 0.5})

        # semantic 层
        memories = self._semantic_mapper.get_memories_by_user(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit * 2
        )
        for memory in memories:
            if query_lower in memory.get("content", "").lower():
                memory["memory_layer"] = "semantic"
                results.append({"memory": memory, "score": 0.5})

        return results[:limit]

    # ========== 混合检索（纯向量检索） ==========

    def hybrid_search(
        self,
        user_id: int,
        query: str,
        top_k: int = 30,
        memory_type: Optional[str] = None,
        min_score: float = 0.3
    ) -> list:
        """
        混合检索（简化版：纯向量检索）

        记忆系统场景下，语义检索比关键词检索更重要，
        因此移除了 BM25 和 RRF 融合，只保留向量检索。

        Args:
            user_id: 用户ID
            query: 查询文本
            top_k: 返回数量
            memory_type: 记忆类型过滤
            min_score: 最低相似度阈值

        Returns:
            [{memory: {...}, score: vector_score, source: "vector"}, ...]
        """
        return self.search_memories(
            user_id=user_id,
            query=query,
            top_k=top_k,
            memory_type=memory_type,
            min_score=min_score
        )

    def rerank_memories(
        self,
        memories: List[Dict],
        top_k: int = 10
    ) -> List[Dict]:
        """
        多维加权精排（规则 Reranker）

        在向量检索结果基础上，综合重要性、时间新鲜度、访问频率进行二次排序。
        权重从环境变量读取，默认：vector*0.6 + importance*0.2 + recency*0.1 + access*0.1

        Args:
            memories: 向量检索结果 [{memory: {...}, score: float}, ...]
            top_k: 返回数量

        Returns:
            精排后的记忆列表 [{memory: {...}, score: float, final_score: float}, ...]
        """
        if not memories:
            return []

        import os
        from datetime import datetime
        from math import log

        # 从环境变量读取权重
        w_vector = float(os.getenv("MEMORY_RERANK_VECTOR_WEIGHT", "0.6"))
        w_importance = float(os.getenv("MEMORY_RERANK_IMPORTANCE_WEIGHT", "0.2"))
        w_recency = float(os.getenv("MEMORY_RERANK_RECENCY_WEIGHT", "0.1"))
        w_access = float(os.getenv("MEMORY_RERANK_ACCESS_WEIGHT", "0.1"))
        halflife_days = float(os.getenv("MEMORY_RERANK_RECENCY_HALFLIFE_DAYS", "30"))

        # 归一化权重（确保和为 1）
        total_weight = w_vector + w_importance + w_recency + w_access
        if total_weight > 0:
            w_vector /= total_weight
            w_importance /= total_weight
            w_recency /= total_weight
            w_access /= total_weight

        now = datetime.now()
        reranked = []

        for item in memories:
            mem = item.get("memory", {})
            vector_score = item.get("score", 0)

            # 1. 重要性分数（默认 0.5）
            importance = float(mem.get("importance_score", 0.5))
            importance = max(0, min(1, importance))  # 限制在 [0, 1]

            # 2. 时间新鲜度（指数衰减）
            created_at_str = mem.get("created_at")
            recency = 0.5  # 默认值
            if created_at_str:
                try:
                    if isinstance(created_at_str, str):
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    else:
                        created_at = created_at_str

                    days_old = (now - created_at.replace(tzinfo=None)).days
                    recency = 2 ** (-days_old / halflife_days) if halflife_days > 0 else 0.5
                except Exception:
                    pass

            # 3. 访问频率（log 归一化）
            access_count = int(mem.get("access_count", 0))
            access_freq = min(1.0, log(1 + access_count) / log(101)) if access_count > 0 else 0

            # 加权融合
            final_score = (
                vector_score * w_vector +
                importance * w_importance +
                recency * w_recency +
                access_freq * w_access
            )

            reranked.append({
                **item,
                "final_score": final_score
            })

        # 按最终分数排序
        reranked.sort(key=lambda x: x["final_score"], reverse=True)
        return reranked[:top_k]

    # ========== 统计 ==========
    
    def get_memory_stats(self, user_id: Optional[int] = None) -> dict:
        """
        获取记忆统计（双层汇总）

        Args:
            user_id: 用户ID（None 表示所有用户）
        """
        stats = {
            "total": 0,
            "episodic": 0,
            "semantic": 0,
            "by_type": {}
        }

        if user_id is None:
            return stats

        # episodic 层统计
        episodic = self._episodic_mapper.get_memories_by_user(user_id=user_id, limit=10000)
        stats["episodic"] = len(episodic)
        for m in episodic:
            mt = m.get("memory_type", "fact")
            stats["by_type"][mt] = stats["by_type"].get(mt, 0) + 1

        # semantic 层统计
        semantic = self._semantic_mapper.get_memories_by_user(user_id=user_id, limit=10000)
        stats["semantic"] = len(semantic)
        for m in semantic:
            mt = m.get("memory_type", "fact")
            stats["by_type"][mt] = stats["by_type"].get(mt, 0) + 1

        stats["total"] = stats["episodic"] + stats["semantic"]
        return stats
    
    # ========== 两层记忆：Episodic + Semantic ==========

    def create_episodic(
        self,
        user_id: int,
        memory_type: str,
        content: str,
        importance_score: float = 0.5,
        source_thread_id: str = "",
        source_round: int = 0,
        vectorize: bool = True
    ) -> Optional[int]:
        """
        创建近期记忆（使用 Outbox 模式）

        写入前会进行去重检查：如果已存在语义相似度 >= 0.92 的记忆，
        则更新已有记忆的 access_count 而非创建新条目。

        Args:
            user_id: 用户ID
            memory_type: 记忆类型
            content: 记忆内容
            importance_score: 重要性分数
            source_thread_id: 来源会话ID
            source_round: 来源轮次
            vectorize: 是否向量化

        Returns:
            记忆ID（新建时返回新ID，去重时返回已有ID）
        """
        # ── 去重检查：写入前检查语义相似度 ──
        # 使用纯向量搜索（search_memories），不用 hybrid_search
        # 因为 hybrid_search 的 RRF 分数会归一化，导致 top1 永远是 1.0，误判为重复
        try:
            similar = self.search_memories(
                user_id=user_id,
                query=content,
                top_k=3,
                min_score=0.92,  # 原始余弦相似度阈值
            )
            if similar:
                existing = similar[0]
                existing_id = existing["memory"]["id"]
                existing_layer = existing.get("memory", {}).get("memory_layer", "episodic")
                # 更新已有记忆的 access_count 和 importance（取较大值）
                self._increment_access_count_in_layer(existing_id, existing_layer)
                if importance_score > existing["memory"].get("importance_score", 0):
                    self.update_memory(
                        existing_id,
                        importance_score=importance_score,
                        re_vectorize=False,
                    )
                logger.info(
                    f"Memory dedup: existing id={existing_id} score={existing['score']:.3f}, "
                    f"skipping creation of similar memory"
                )
                return existing_id
        except Exception as e:
            # 去重检查失败不阻塞正常写入
            logger.debug(f"Memory dedup check failed (non-blocking): {e}")

        from backend.db.schema import get_conn
        from backend.service.memory.outbox_types import (
            OutboxEvent, EventType, Target,
            compute_content_hash, make_vector_payload
        )
        from backend.service.memory.outbox_writer import get_outbox_writer

        if memory_type not in self.MEMORY_TYPES:
            logger.warning(f"Invalid memory type: {memory_type}")
            return None

        content_hash = compute_content_hash(content, memory_type, importance_score)
        events: List[OutboxEvent] = []

        conn = get_conn()
        outbox_writer = get_outbox_writer()
        memory_id = None

        try:
            # 1. 插入业务数据
            memory_id = self._episodic_mapper.create_memory(
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                importance_score=importance_score,
                source_thread_id=source_thread_id,
                source_round=source_round,
                ttl_days=self._episodic_ttl_days,
                decay_rate=self._decay_rate,
                content_hash=content_hash,
                conn=conn
            )

            if not memory_id:
                conn.rollback()
                return None

            # 2. 生成 Outbox 事件
            if vectorize:
                events.append(OutboxEvent.create(
                    memory_id=memory_id,
                    memory_version=1,
                    event_type=EventType.UPSERT_VECTOR,
                    target=Target.MILVUS,
                    payload=make_vector_payload(
                        content, memory_type, importance_score, user_id,
                        memory_layer="episodic"
                    )
                ))

            # 3. 写入 Outbox（同一事务）
            if events and not outbox_writer.write_events(conn, events, memory_layer="episodic"):
                conn.rollback()
                logger.error(f"Failed to write outbox events for episodic memory {memory_id}")
                return None

            conn.commit()
            logger.info(f"Created episodic memory {memory_id} with {len(events)} outbox events")
            return memory_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create episodic memory: {e}")
            return None
        finally:
            conn.close()

    def create_semantic(
        self,
        user_id: int,
        memory_type: str,
        content: str,
        importance_score: float = 0.5,
        source_thread_id: str = "",
        source_round: int = 0,
        source_episodic_id: Optional[int] = None,
        vectorize: bool = True,
        extract_graph: bool = True
    ) -> Optional[int]:
        """
        创建永久知识（使用 Outbox 模式，含图节点）

        Args:
            user_id: 用户ID
            memory_type: 记忆类型
            content: 记忆内容
            importance_score: 重要性分数
            source_thread_id: 来源会话ID
            source_round: 来源轮次
            source_episodic_id: 来源 episodic 记忆ID（晋升时）
            vectorize: 是否向量化
            extract_graph: 是否提取图节点

        Returns:
            记忆ID
        """
        from backend.db.schema import get_conn
        from backend.service.memory.outbox_types import (
            OutboxEvent, EventType, Target,
            compute_content_hash, make_vector_payload, make_graph_payload
        )
        from backend.service.memory.outbox_writer import get_outbox_writer

        if memory_type not in self.MEMORY_TYPES:
            logger.warning(f"Invalid memory type: {memory_type}")
            return None

        content_hash = compute_content_hash(content, memory_type, importance_score)
        events: List[OutboxEvent] = []

        conn = get_conn()
        outbox_writer = get_outbox_writer()
        memory_id = None

        try:
            # 1. 插入业务数据
            memory_id = self._semantic_mapper.create_memory(
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                importance_score=importance_score,
                source_thread_id=source_thread_id,
                source_round=source_round,
                source_episodic_id=source_episodic_id,
                content_hash=content_hash,
                conn=conn
            )

            if not memory_id:
                conn.rollback()
                return None

            # 2. 生成 Outbox 事件
            if vectorize:
                events.append(OutboxEvent.create(
                    memory_id=memory_id,
                    memory_version=1,
                    event_type=EventType.UPSERT_VECTOR,
                    target=Target.MILVUS,
                    payload=make_vector_payload(
                        content, memory_type, importance_score, user_id,
                        memory_layer="semantic"
                    )
                ))

            if extract_graph:
                events.append(OutboxEvent.create(
                    memory_id=memory_id,
                    memory_version=1,
                    event_type=EventType.UPSERT_GRAPH_NODE,
                    target=Target.NEO4J,
                    payload=make_graph_payload(
                        content, memory_type, importance_score, user_id,
                        memory_layer="semantic"
                    )
                ))

            # 3. 写入 Outbox（同一事务）
            if events and not outbox_writer.write_events(conn, events, memory_layer="semantic"):
                conn.rollback()
                logger.error(f"Failed to write outbox events for semantic memory {memory_id}")
                return None

            conn.commit()
            logger.info(f"Created semantic memory {memory_id} with {len(events)} outbox events")
            return memory_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create semantic memory: {e}")
            return None
        finally:
            conn.close()

    def promote_to_semantic(
        self,
        episodic_id: int,
        user_id: int,
        new_content: Optional[str] = None,
        new_importance: Optional[float] = None
    ) -> Optional[int]:
        """
        晋升近期记忆为永久知识

        流程：
        1. 读取 episodic 记忆
        2. 创建 semantic 记忆（使用新内容或原内容）
        3. 软删除 episodic 记忆
        4. Outbox 事件：删除旧向量 + 创建新向量 + 创建图节点

        Args:
            episodic_id: 近期记忆ID
            user_id: 用户ID
            new_content: 新内容（None 表示使用原内容）
            new_importance: 新重要性（None 表示使用原重要性）

        Returns:
            新 semantic 记忆ID，失败返回 None
        """
        from backend.db.schema import get_conn
        from backend.service.memory.outbox_types import (
            OutboxEvent, EventType, Target,
            compute_content_hash, make_vector_payload, make_graph_payload
        )
        from backend.service.memory.outbox_writer import get_outbox_writer

        # 1. 读取 episodic 记忆
        episodic = self._episodic_mapper.get_memory_by_id(episodic_id)
        if not episodic:
            logger.warning(f"Episodic memory {episodic_id} not found")
            return None

        if episodic.get("user_id") != user_id:
            logger.warning(f"User {user_id} cannot promote memory {episodic_id}")
            return None

        content = new_content or episodic["content"]
        importance = new_importance or episodic.get("importance_score", 0.5)
        memory_type = episodic["memory_type"]

        content_hash = compute_content_hash(content, memory_type, importance)
        events: List[OutboxEvent] = []

        conn = get_conn()
        outbox_writer = get_outbox_writer()
        semantic_id = None

        try:
            # 2. 创建 semantic 记忆
            semantic_id = self._semantic_mapper.create_memory(
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                importance_score=importance,
                source_thread_id=episodic.get("source_thread_id", ""),
                source_round=episodic.get("source_round", 0),
                source_episodic_id=episodic_id,
                content_hash=content_hash,
                conn=conn
            )

            if not semantic_id:
                conn.rollback()
                return None

            # 3. 软删除 episodic 记忆
            if not self._episodic_mapper.soft_delete(episodic_id, conn=conn):
                conn.rollback()
                return None

            # 4. 生成 Outbox 事件
            # 4.1 删除旧 episodic 向量（始终创建事件，确保 Milvus 脏数据被清理）
            old_embedding_id = episodic.get("embedding_id")
            events.append(OutboxEvent.create(
                memory_id=episodic_id,
                memory_version=episodic.get("version", 1),
                event_type=EventType.DELETE_VECTOR,
                target=Target.MILVUS,
                payload={
                    "embedding_id": old_embedding_id or f"mem_{episodic_id}",
                    "memory_id": episodic_id,
                    "user_id": episodic.get("user_id"),
                    "memory_layer": "episodic"
                }
            ))

            # 4.2 创建新向量
            events.append(OutboxEvent.create(
                memory_id=semantic_id,
                memory_version=1,
                event_type=EventType.UPSERT_VECTOR,
                target=Target.MILVUS,
                payload=make_vector_payload(
                    content, memory_type, importance, user_id,
                    memory_layer="semantic"
                )
            ))

            # 4.3 创建图节点
            events.append(OutboxEvent.create(
                memory_id=semantic_id,
                memory_version=1,
                event_type=EventType.UPSERT_GRAPH_NODE,
                target=Target.NEO4J,
                payload=make_graph_payload(
                    content, memory_type, importance, user_id,
                    memory_layer="semantic"
                )
            ))

            # 5. 写入 Outbox
            if events and not outbox_writer.write_events(conn, events, memory_layer="semantic"):
                conn.rollback()
                logger.error(f"Failed to write outbox events for promotion {episodic_id} -> {semantic_id}")
                return None

            conn.commit()
            logger.info(f"Promoted episodic {episodic_id} to semantic {semantic_id}")
            return semantic_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to promote memory: {e}")
            return None
        finally:
            conn.close()

    def get_episodic_memories(
        self,
        user_id: int,
        memory_type: Optional[str] = None,
        include_expired: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """
        获取用户近期记忆列表

        Args:
            user_id: 用户 ID
            memory_type: 记忆类型过滤
            include_expired: 是否包含已过期的记忆
            limit: 返回数量限制
            offset: 偏移量
        """
        memories = self._episodic_mapper.get_memories_by_user(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit,
            offset=offset
        )

        # 如果不包含过期记忆，过滤掉已过期的
        if not include_expired:
            now = datetime.now()
            memories = [
                m for m in memories
                if not m.get("expires_at") or m.get("expires_at") >= now
            ]

        return memories

    def get_semantic_memories(
        self,
        user_id: int,
        memory_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """获取用户永久知识列表"""
        return self._semantic_mapper.get_memories_by_user(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit,
            offset=offset
        )

    def get_episodic_memory(self, memory_id: int, user_id: Optional[int] = None) -> Optional[dict]:
        """获取单条情景记忆"""
        return self._episodic_mapper.get_memory_by_id(memory_id, user_id=user_id)

    def get_semantic_memory(self, memory_id: int, user_id: Optional[int] = None) -> Optional[dict]:
        """获取单条语义记忆"""
        return self._semantic_mapper.get_memory_by_id(memory_id, user_id=user_id)

    def get_episodic_stats(self, user_id: int) -> dict:
        """
        获取情景记忆统计

        Returns:
            {
                "total": int,
                "active": int,  # 未过期
                "expired": int,  # 已过期
                "by_type": {"preference": int, "fact": int, ...}
            }
        """
        memories = self._episodic_mapper.get_memories_by_user(user_id=user_id, limit=10000)
        now = datetime.now()

        total = len(memories)
        active = 0
        expired = 0
        by_type = {t: 0 for t in self.MEMORY_TYPES}

        for m in memories:
            # 检查是否过期
            expires_at = m.get("expires_at")
            if expires_at and expires_at < now:
                expired += 1
            else:
                active += 1

            # 按类型统计
            mt = m.get("memory_type", "fact")
            if mt in by_type:
                by_type[mt] += 1

        return {
            "total": total,
            "active": active,
            "expired": expired,
            "by_type": by_type
        }

    def get_semantic_stats(self, user_id: int) -> dict:
        """
        获取语义记忆统计

        Returns:
            {
                "total": int,
                "by_type": {"preference": int, "fact": int, ...},
                "from_promotion": int  # 从情景记忆晋升而来
            }
        """
        memories = self._semantic_mapper.get_memories_by_user(user_id=user_id, limit=10000)

        total = len(memories)
        by_type = {t: 0 for t in self.MEMORY_TYPES}
        from_promotion = 0

        for m in memories:
            mt = m.get("memory_type", "fact")
            if mt in by_type:
                by_type[mt] += 1

            if m.get("source_episodic_id"):
                from_promotion += 1

        return {
            "total": total,
            "by_type": by_type,
            "from_promotion": from_promotion
        }


# 单例访问
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """获取 MemoryService 单例"""
    global _memory_service
    if _memory_service is None:
        # 从环境变量读取配置
        delay_rounds = int(os.getenv("MEMORY_DELAY_ROUNDS", "10"))
        ttl_days = int(os.getenv("MEMORY_TTL_DAYS", "60"))
        decay_rate = float(os.getenv("MEMORY_DECAY_RATE", "0.95"))
        
        _memory_service = MemoryService(
            delay_rounds=delay_rounds,
            ttl_days=ttl_days,
            decay_rate=decay_rate
        )
    return _memory_service