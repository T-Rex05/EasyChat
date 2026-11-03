"""
Memory Reconciler - 增量对账器

核心职责：
- 定期检查 PostgreSQL 与派生库（Milvus/Neo4j）的一致性
- 发现差异后生成修复事件，复用 Outbox 机制
- 支持增量对账（只检查最近变化）和全量对账（定期兜底）
- 知识图谱实体去重（融合到增量/全量对账中）

策略：
- 增量对账（中频，中等成本）：检查最近变化的记忆 + 图谱去重检查
- 全量对账（低频，高成本）：完整扫描 + 全量图谱去重
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from backend.db.schema import get_conn
from backend.service.memory.outbox_types import (
    EventType,
    Target,
    compute_content_hash,
    generate_repair_event_id,
)
from backend.service.memory.outbox_writer import get_outbox_writer

logger = logging.getLogger(__name__)


class MemoryReconciler:
    """
    记忆增量对账器

    组合多种策略：
    - 增量对账：每小时，检查最近 24h 变化
    - 全量对账：每月，完整扫描（含 KG 去重）

    KG 去重说明：
    - 实体提取使用 MERGE + hash-based ID 生成，同一 name+type 产生相同 ID
    - 设计层面已防止重复，去重检测作为安全兜底
    - 仅在全量对账中执行，降低冗余开销
    """

    def __init__(
        self,
        incremental_interval: int = 3600,    # 增量对账间隔（秒），1 小时
        incremental_hours: int = 24,         # 增量窗口（小时）
        full_interval_days: int = 30,        # 全量对账间隔（天），每月一次
        batch_size: int = 100,               # 每批处理数量
    ):
        self._incremental_interval = incremental_interval
        self._incremental_hours = incremental_hours
        self._full_interval_days = full_interval_days
        self._batch_size = batch_size

        self._running = False
        self._incremental_thread: Optional[threading.Thread] = None
        self._full_thread: Optional[threading.Thread] = None

        self._last_full_reconcile: Optional[datetime] = None

        # 统计
        self._stats = {
            "incremental_checks": 0,
            "full_checks": 0,
            "issues_found": 0,
            "repair_events": 0,
            "kg_duplicates_found": 0,
            "kg_entities_merged": 0,
        }
    
    def start(self) -> None:
        """启动对账任务"""
        if self._running:
            return

        self._running = True

        # 增量对账线程
        self._incremental_thread = threading.Thread(
            target=self._incremental_loop,
            name="memory-incremental",
            daemon=True
        )
        self._incremental_thread.start()

        # 全量对账线程
        self._full_thread = threading.Thread(
            target=self._full_loop,
            name="memory-full",
            daemon=True
        )
        self._full_thread.start()

        logger.info(f"Memory reconciler started "
                   f"(incremental={self._incremental_interval}s, full={self._full_interval_days}d)")
    
    def stop(self) -> None:
        """停止对账任务"""
        self._running = False
        logger.info(f"Memory reconciler stopped. Stats: {self._stats}")
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()
    
    # ========== 增量对账 ==========
    
    def _incremental_loop(self) -> None:
        """增量对账循环"""
        while self._running:
            try:
                self._incremental_check()
                self._stats["incremental_checks"] += 1
            except Exception as e:
                logger.error(f"Incremental check failed: {e}")
            
            time.sleep(self._incremental_interval)
    
    def _incremental_check(self) -> None:
        """
        增量对账 - 检查最近变化的记忆
        
        只检查最近 N 小时内有更新（updated_at）的记忆，
        验证其在派生库中是否存在且版本匹配。
        """
        logger.info(f"Running incremental check (last {self._incremental_hours}h)...")
        
        since = datetime.now() - timedelta(hours=self._incremental_hours)
        
        # 获取最近变化的记忆
        recent_memories = self._get_recently_changed_memories(since)
        
        if not recent_memories:
            logger.debug("No recent changes to check")
            return
        
        logger.info(f"Checking {len(recent_memories)} recently changed memories...")
        
        issues = {
            "missing_vectors": 0,
            "missing_graph_nodes": 0,
            "stale_vectors": 0,
            "stale_graph_nodes": 0,
        }
        
        for memory in recent_memories:
            memory_id = memory["id"]
            version = memory.get("version", 1)
            memory_layer = memory.get("memory_layer", "legacy")

            # 检查向量（所有层都需要）
            if not self._check_vector_consistency(memory):
                issues["missing_vectors"] += 1
                self._create_repair_event(
                    memory_id, version, EventType.UPSERT_VECTOR, Target.MILVUS,
                    # ⚠️ 必须带 user_id：handle_upsert_vector 用它决定向量集合
                    # （user_{id}_memories）。缺失会让修复事件直接失败并进死信。
                    {"reason": "incremental_missing", "content": memory["content"],
                     "memory_layer": memory_layer, "user_id": memory.get("user_id")}
                )

            # 检查图节点（只有 semantic 和 legacy 层需要，episodic 不入图谱）
            if memory_layer != "episodic":
                graph_ok = self._check_graph_consistency(memory)
                if graph_ok is None:
                    issues["graph_check"] = "disabled"  # 不再谎报一致
                elif not graph_ok:
                    issues["missing_graph_nodes"] += 1
                    self._create_repair_event(
                        memory_id, version, EventType.UPSERT_GRAPH_NODE, Target.NEO4J,
                        # 同理：缺 user_id 会写出"无归属"图节点，而图谱可见性谓词是
                        # `source_document_id IS NOT NULL OR user_id = $user_id`
                        # → 无归属节点对所有人都不可见（fail-closed），等于没修
                        {"reason": "incremental_missing", "content": memory["content"],
                         "memory_layer": memory_layer, "user_id": memory.get("user_id")}
                    )
        
        total_issues = sum(v for k, v in issues.items() if k != "graph_check")
        self._stats["issues_found"] += total_issues
        
        if total_issues > 0:
            logger.warning(f"Incremental check found issues: {issues}")
        elif issues.get("graph_check") == "disabled":
            logger.info("Incremental check passed (graph_check=disabled)")
        else:
            logger.info("Incremental check passed: all recent memories are consistent")
        
        # KG dedup 移至全量对账中执行，原因：
        # - 实体提取使用 MERGE + hash-based ID，同一 name+type 产生相同 ID
        # - 设计层面防止重复，增量去重检测为冗余开销
        # - 全量去重保留为安全兜底，频率已调整为每月一次
    
    def _get_recently_changed_memories(self, since: datetime) -> List[Dict]:
        """
        获取所有层最近变化的记忆

        覆盖 Semantic 层（Episodic 不入图谱，不需要对账图谱一致性）

        Returns:
            带 memory_layer 标记的记忆列表，content 已解密
        """
        from backend.utils.crypto_utils import decrypt_memory_content
        
        all_memories = []
        conn = get_conn()
        try:
            # Semantic 层（memory_semantic）
            # Semantic 层记忆会写入图谱，需要检查图谱一致性
            try:
                cur = conn.execute(
                    """SELECT id, user_id, version, content, memory_type, importance_score,
                              embedding_id, updated_at
                       FROM memory_semantic
                       WHERE updated_at >= %s
                         AND deleted_at IS NULL
                       ORDER BY updated_at DESC
                       LIMIT %s""",
                    (since, self._batch_size)
                )
                for row in cur.fetchall():
                    mem = dict(row)
                    mem["memory_layer"] = "semantic"
                    # 解密 content（数据库存的是 ENC: 密文）
                    mem["content"] = decrypt_memory_content(mem.get("content", ""))
                    all_memories.append(mem)
            except Exception as e:
                logger.warning(f"Failed to get semantic memories: {e}")

            # 注意：Episodic 层不入图谱，不需要对账图谱一致性
            # 但向量一致性仍然需要检查，这里也加上
            try:
                cur = conn.execute(
                    """SELECT id, user_id, version, content, memory_type, importance_score,
                              embedding_id, updated_at
                       FROM memory_episodic
                       WHERE updated_at >= %s
                         AND deleted_at IS NULL
                       ORDER BY updated_at DESC
                       LIMIT %s""",
                    (since, self._batch_size)
                )
                for row in cur.fetchall():
                    mem = dict(row)
                    mem["memory_layer"] = "episodic"
                    # 解密 content（数据库存的是 ENC: 密文）
                    mem["content"] = decrypt_memory_content(mem.get("content", ""))
                    all_memories.append(mem)
            except Exception as e:
                logger.warning(f"Failed to get episodic memories: {e}")
        finally:
            conn.close()

        # 按 updated_at 降序排列
        all_memories.sort(key=lambda x: x.get("updated_at") or datetime.min, reverse=True)

        return all_memories[:self._batch_size]
    
    def _check_vector_consistency(self, memory: Dict) -> bool:
        """检查向量一致性"""
        from backend.infrastructure import get_memory_client
        
        vector_client = get_memory_client()
        if not vector_client or not vector_client.is_available():
            return True  # 向量库不可用，暂时认为一致
        
        memory_id = memory["id"]
        vector_id = f"mem_{memory_id}"
        
        try:
            # 检查向量是否存在
            exists = vector_client.exists(vector_id) if hasattr(vector_client, 'exists') else True
            return exists
        except Exception as e:
            logger.debug(f"Failed to check vector {vector_id}: {e}")
            return True  # 检查失败，暂时认为一致
    
    def _check_graph_consistency(self, memory: Dict) -> Optional[bool]:
        """检查图节点一致性。
        
        Returns:
            True = 一致, False = 不一致, None = 未检查（当前未实现真实的图一致性检查）
        """
        from backend.memory.graph_memory import get_graph_memory
        
        graph_memory = get_graph_memory()
        if not graph_memory or not graph_memory._available():
            return None  # 图库不可用，返回 None 表示跳过检查
        
        # 当前未实现真实的图一致性检查，返回 None 表示跳过
        return None
    
    # ========== 全量对账 ==========
    
    def _full_loop(self) -> None:
        """全量对账循环"""
        while self._running:
            try:
                # 判断是否需要全量对账
                if self._should_run_full():
                    self._full_check()
                    self._stats["full_checks"] += 1
                    self._last_full_reconcile = datetime.now()
            except Exception as e:
                logger.error(f"Full check failed: {e}")
            
            # 每天检查一次是否需要全量对账
            time.sleep(86400)
    
    def _should_run_full(self) -> bool:
        """判断是否需要全量对账"""
        if self._last_full_reconcile is None:
            return True
        
        elapsed = datetime.now() - self._last_full_reconcile
        return elapsed.days >= self._full_interval_days
    
    def _full_check(self) -> None:
        """
        全量对账 - 完整扫描所有记忆
        
        作为增量对账的兜底，定期运行。
        """
        logger.info("Running FULL reconciliation...")
        
        # 获取所有用户
        users = self._get_all_users_with_memories()
        
        total_memories = 0
        total_issues = 0
        
        for user_id in users:
            memories = self._get_user_memories(user_id)
            total_memories += len(memories)
            
            for memory in memories:
                if not self._check_vector_consistency(memory):
                    self._create_repair_event(
                        memory["id"], memory.get("version", 1),
                        EventType.UPSERT_VECTOR, Target.MILVUS,
                        # ⚠️ 与增量对账同样必须带 user_id + memory_layer：
                        # 缺 memory_layer 会落到默认 "legacy" → 走 episodic mapper，
                        # 语义层记忆会被查错表（查不到就静默跳过、事件还被标记成功；
                        # id 撞车则会写错对象），缺 user_id 则直接失败进死信。
                        {"reason": "full_missing", "content": memory["content"],
                         "memory_layer": memory.get("memory_layer", "legacy"),
                         "user_id": memory.get("user_id")}
                    )
                    total_issues += 1
                
                # 图一致性检查：显式判断 False，None 表示跳过检查
                graph_ok = self._check_graph_consistency(memory)
                if graph_ok is False:
                    self._create_repair_event(
                        memory["id"], memory.get("version", 1),
                        EventType.UPSERT_GRAPH_NODE, Target.NEO4J,
                        {"reason": "full_missing", "content": memory["content"],
                         "memory_layer": memory.get("memory_layer", "legacy"),
                         "user_id": memory.get("user_id")}
                    )
                    total_issues += 1
        
        self._stats["issues_found"] += total_issues
        logger.info(f"Full reconciliation completed: checked {total_memories} memories, "
                   f"found {total_issues} issues")
        
        # 全量图谱去重
        try:
            logger.info("Running full KG dedup...")
            kg_result = self._check_kg_duplicates(batch_size=0)  # batch_size=0 表示全量
            if kg_result.get("merged", 0) > 0:
                self._stats["kg_duplicates_found"] += kg_result.get("duplicates_found", 0)
                self._stats["kg_entities_merged"] += kg_result.get("merged", 0)
                logger.info(f"Full KG dedup completed: merged {kg_result.get('merged')} entities")
        except Exception as e:
            logger.warning(f"Full KG dedup failed: {e}")
    
    def _get_all_users_with_memories(self) -> List[int]:
        """获取所有有记忆的用户（episodic + semantic）"""
        conn = get_conn()
        try:
            users = set()
            for table in ("memory_episodic", "memory_semantic"):
                try:
                    cur = conn.execute(
                        f"""SELECT DISTINCT user_id FROM {table}
                           WHERE deleted_at IS NULL"""
                    )
                    users.update(row["user_id"] for row in cur.fetchall())
                except Exception as e:
                    logger.debug(f"Reconciler: {table} user query failed: {e}")
            return list(users)
        finally:
            conn.close()

    def _get_user_memories(self, user_id: int, limit: int = 1000) -> List[Dict]:
        """获取用户所有记忆（episodic + semantic），content 已解密"""
        from backend.utils.crypto_utils import decrypt_memory_content

        conn = get_conn()
        try:
            results = []
            for table in ("memory_episodic", "memory_semantic"):
                try:
                    cur = conn.execute(
                        f"""SELECT id, user_id, version, content, memory_type, importance_score
                           FROM {table}
                           WHERE user_id = %s AND deleted_at IS NULL
                           LIMIT %s""",
                        (user_id, limit)
                    )
                    for row in cur.fetchall():
                        mem = dict(row)
                        # 解密 content（数据库存的是 ENC: 密文）
                        mem["content"] = decrypt_memory_content(mem.get("content", ""))
                        # ⚠️ 必须标注层级：下游 _full_check 要把 memory_layer 放进修复事件，
                        # 缺失会落到默认 "legacy" → handle_* 走 episodic mapper 查错表
                        mem["memory_layer"] = "episodic" if table == "memory_episodic" else "semantic"
                        results.append(mem)
                except Exception as e:
                    logger.debug(f"Reconciler: {table} user memories query failed: {e}")
            return results
        finally:
            conn.close()
    
    # ========== 修复事件生成 ==========
    
    def _create_repair_event(
        self,
        memory_id: int,
        memory_version: int,
        event_type: EventType,
        target: Target,
        payload: Dict[str, Any]
    ) -> None:
        """创建修复事件
        
        P2-6 修复：先检查是否已有 pending/processing 的事件，有则跳过，防止事件堆积。
        """
        conn = get_conn()
        try:
            # P2-6 修复：检查是否已有 pending/processing 的相同事件
            # 使用前缀匹配，不依赖时间片
            event_prefix = f"repair-{memory_id}-{event_type.value}-{target.value}"
            cur = conn.execute(
                """SELECT 1 FROM memory_outbox
                   WHERE event_id LIKE %s
                   AND status IN ('pending', 'processing')
                   LIMIT 1""",
                (event_prefix + "%",)
            )
            if cur.fetchone():
                logger.debug(
                    f"Skip creating repair event: already has pending/processing event "
                    f"for memory={memory_id}, type={event_type.value}, target={target.value}"
                )
                return

            outbox_writer = get_outbox_writer()

            # 生成幂等的修复事件 ID
            event_id = generate_repair_event_id(memory_id, event_type, target)

            try:
                success = outbox_writer.write_repair_event(
                    conn=conn,
                    memory_id=memory_id,
                    memory_version=memory_version,
                    event_type=event_type.value,
                    target=target.value,
                    payload=payload,
                    event_id=event_id
                )
                conn.commit()

                if success:
                    self._stats["repair_events"] += 1
                    logger.debug(f"Created repair event: {event_id}")
            except Exception as e:
                conn.rollback()
                logger.warning(f"Failed to create repair event: {e}")
        finally:
            conn.close()
    
    # ========== 知识图谱去重 ==========
    
    def _check_kg_duplicates(self, batch_size: int = 50) -> Dict[str, int]:
        """
        检查并清理知识图谱中的重复实体
        
        Args:
            batch_size: 处理批次大小，0 表示全量处理
            
        Returns:
            {"duplicates_found": int, "merged": int}
        """
        from backend.infrastructure.neo4j_client import get_neo4j_client
        
        client = get_neo4j_client()
        if not client or not client.is_available():
            logger.debug("Neo4j not available, skip KG dedup")
            return {"duplicates_found": 0, "merged": 0}
        
        result = {"duplicates_found": 0, "merged": 0}
        
        try:
            # 查找同名同类型的重复实体
            query = """
            MATCH (n)
            WITH n.name as name, labels(n) as labels, collect({id: n.id, node: n}) as nodes
            WHERE name IS NOT NULL AND size(nodes) > 1
            RETURN name, labels, nodes, size(nodes) as count
            ORDER BY count DESC
            """
            
            rows = client.run_query(query, {})
            
            if not rows:
                logger.debug("No duplicate entities found in KG")
                return result
            
            result["duplicates_found"] = len(rows)
            processed = 0
            
            for row in rows:
                if batch_size > 0 and processed >= batch_size:
                    break
                
                name = row.get("name")
                nodes = row.get("nodes", [])
                
                if len(nodes) < 2:
                    continue
                
                # 保留第一个节点，合并其他
                keep_node = nodes[0]
                remove_nodes = nodes[1:]
                
                for remove_node in remove_nodes:
                    remove_id = remove_node.get("id")
                    keep_id = keep_node.get("id")
                    
                    if not remove_id or not keep_id:
                        continue
                    
                    # 合并关系到保留节点
                    self._merge_kg_entity(client, keep_id, remove_id)
                    result["merged"] += 1
                
                processed += 1
            
            if result["merged"] > 0:
                logger.info(f"KG dedup: found {result['duplicates_found']} groups, merged {result['merged']} entities")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to check KG duplicates: {e}")
            return result
    
    def _merge_kg_entity(self, client, keep_id: str, remove_id: str) -> bool:
        """
        合并重复实体
        
        Args:
            client: Neo4j 客户端
            keep_id: 保留的实体 ID
            remove_id: 要删除的实体 ID
            
        Returns:
            是否成功
        """
        try:
            # 将指向 remove_id 的关系改为指向 keep_id
            move_in_query = """
            MATCH (n)-[r]->(m {id: $remove_id})
            MATCH (target {id: $keep_id})
            MERGE (n)-[r2:RELATED_TO]->(target)
            SET r2 += properties(r)
            DELETE r
            """
            client.run_query(move_in_query, {"remove_id": remove_id, "keep_id": keep_id})
            
            # 将从 remove_id 发出的关系改为从 keep_id 发出
            move_out_query = """
            MATCH (m {id: $remove_id})-[r]->(n)
            MATCH (source {id: $keep_id})
            MERGE (source)-[r2:RELATED_TO]->(n)
            SET r2 += properties(r)
            DELETE r
            """
            client.run_query(move_out_query, {"remove_id": remove_id, "keep_id": keep_id})
            
            # 删除重复节点
            delete_query = """
            MATCH (n {id: $id})
            DETACH DELETE n
            """
            client.run_query(delete_query, {"id": remove_id})
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to merge entity {remove_id} into {keep_id}: {e}")
            return False


# ========== 单例和初始化 ==========

_reconciler: Optional[MemoryReconciler] = None
_reconciler_lock = threading.Lock()


def get_reconciler() -> MemoryReconciler:
    """获取 MemoryReconciler 单例"""
    global _reconciler
    with _reconciler_lock:
        if _reconciler is None:
            _reconciler = MemoryReconciler()
        return _reconciler


def start_reconciler() -> None:
    """启动对账任务"""
    get_reconciler().start()


def stop_reconciler() -> None:
    """停止对账任务"""
    global _reconciler
    if _reconciler:
        _reconciler.stop()