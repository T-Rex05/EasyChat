"""
Outbox Worker - Outbox 事件消费者

核心职责：
- 从 memory_outbox 表领取待处理事件
- 幂等地执行同步操作（带版本校验）
- 失败重试（指数退避）直到成功或进入死信
- 支持多个目标库的处理器注册

并发安全：
- 使用 locked_at + locked_by 实现简单的分布式锁
- MySQL 8.0+ 可使用 FOR UPDATE SKIP LOCKED
"""

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from backend.db.schema import get_conn
from backend.service.memory.outbox_types import (
    EventType,
    Target,
    EventStatus,
)

logger = logging.getLogger(__name__)


class OutboxWorker:
    """
    Outbox 消费者
    
    从 outbox 表领取事件并执行对应的处理器。
    支持幂等处理、重试机制和死信队列。
    """
    
    def __init__(
        self,
        max_attempts: int = 5,
        retry_backoff_base: float = 2.0,      # 指数退避基数（秒）
        lock_timeout_seconds: int = 300,       # 锁超时时间
        poll_interval: float = 1.0,            # 轮询间隔（秒）
        batch_size: int = 10,                  # 每批领取数量
        worker_id: Optional[str] = None,
    ):
        self._max_attempts = max_attempts
        self._retry_backoff_base = retry_backoff_base
        self._lock_timeout = lock_timeout_seconds
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._worker_id = worker_id or f"worker-{threading.current_thread().ident}"

        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        # 目标库处理器映射: {Target: {EventType: handler}}
        self._handlers: Dict[Target, Dict[EventType, Callable]] = {}

        # ── 定期维护（晋升 + TTL 淘汰）──
        self._last_maintenance: float = 0.0
        self._maintenance_interval: float = 600.0  # 每 10 分钟执行一次
        
        # 统计
        self._stats = {
            "processed": 0,
            "failed": 0,
            "retried": 0,
            "dead": 0,
        }
    
    def register_handler(
        self,
        target: Target,
        event_type: EventType,
        handler: Callable[[int, int, Dict], None]
    ) -> None:
        """
        注册事件处理器
        
        Args:
            target: 目标库
            event_type: 事件类型
            handler: 处理函数，签名 (memory_id, expected_version, payload) -> None
                    处理器应该实现幂等逻辑，根据版本号判断是否需要执行。
        """
        if target not in self._handlers:
            self._handlers[target] = {}
        self._handlers[target][event_type] = handler
        logger.info(f"Registered handler for {target.value}.{event_type.value}")
    
    def start(self) -> None:
        """启动 Worker"""
        if self._running:
            logger.warning("Outbox worker already running")
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            name="outbox-worker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info(f"Outbox worker started (id={self._worker_id})")
    
    def stop(self) -> None:
        """停止 Worker"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info(f"Outbox worker stopped. Stats: {self._stats}")
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()
    
    def _run_loop(self) -> None:
        """主循环 - 带指数退避的连续错误处理"""
        consecutive_errors = 0
        max_backoff = 60  # 最大退避 60 秒

        while self._running:
            try:
                # 领取待处理事件
                events = self._fetch_pending_events()

                # 成功获取事件，重置错误计数
                consecutive_errors = 0

                if not events:
                    # ── 空闲时执行定期维护 ──
                    self._maybe_run_maintenance()
                    time.sleep(self._poll_interval)
                    continue

                # 处理每个事件
                for event in events:
                    if not self._running:
                        break
                    self._process_event(event)

                # ⚠️ 有事件时也要走一次定期维护（内部按 600s 时间窗自我节流）。
                # 旧实现只在 events 为空时维护 → 只要 outbox 持续有事件
                # （例如一批事件反复重试、或高峰期持续写入），
                # 情景→语义晋升与 TTL 淘汰就会**永久饿死**，从不执行。
                self._maybe_run_maintenance()

            except Exception as e:
                consecutive_errors += 1
                # 指数退避: poll_interval * 2^(n-1)，最大 max_backoff 秒
                backoff = min(
                    self._poll_interval * (2 ** (consecutive_errors - 1)),
                    max_backoff
                )
                logger.error(
                    f"Outbox worker loop error (连续第 {consecutive_errors} 次): {e}, "
                    f"{backoff:.1f}s 后重试"
                )
                time.sleep(backoff)

    def _maybe_run_maintenance(self) -> None:
        """定期执行记忆维护（晋升 + TTL 淘汰），每 10 分钟一次"""
        now = time.time()
        if now - self._last_maintenance < self._maintenance_interval:
            return
        self._last_maintenance = now

        try:
            promoted = self._promote_episodic_to_semantic()
            if promoted:
                logger.info(f"Memory maintenance: promoted {promoted} episodic → semantic")
        except Exception as e:
            logger.warning(f"Memory promotion failed: {e}")

        try:
            expired = self._cleanup_expired_memories()
            if expired:
                logger.info(f"Memory maintenance: cleaned up {expired} expired memories")
        except Exception as e:
            logger.warning(f"Memory TTL cleanup failed: {e}")

    def _promote_episodic_to_semantic(self) -> int:
        """
        情景晋升：将高重要性或高频访问的 Episodic 记忆晋升为 Semantic。

        晋升条件（满足任一）：
        1. importance_score >= 0.85
        2. access_count >= 10 且 importance_score >= 0.5

        Returns:
            晋升的记忆数量
        """
        from backend.utils.crypto_utils import decrypt_memory_content, encrypt_memory_content
        
        conn = get_conn()
        try:
            # 事务模式：关闭自动提交
            conn._conn.autocommit = False

            # 查找满足晋升条件的 Episodic 记忆
            cur = conn.execute(
                """SELECT id, user_id, content, memory_type, importance_score,
                          access_count, content_hash
                   FROM memory_episodic
                   WHERE deleted_at IS NULL
                     AND (promoted_to_semantic IS NULL OR promoted_to_semantic = 0)
                     AND (
                         importance_score >= 0.85
                         OR (access_count >= 10 AND importance_score >= 0.5)
                     )
                   ORDER BY id
                   LIMIT 50"""
            )
            candidates = [dict(r) for r in cur.fetchall()]

            if not candidates:
                conn.commit()
                return 0

            # 解密所有 candidate 的 content（数据库存的是 ENC: 密文）
            for mem in candidates:
                mem["content"] = decrypt_memory_content(mem.get("content", ""))

            promoted = 0
            for mem in candidates:
                try:
                    # 检查 Semantic 层是否已有相同 content_hash 的记忆
                    cur = conn.execute(
                        """SELECT id FROM memory_semantic
                           WHERE user_id = %s AND content_hash = %s AND deleted_at IS NULL""",
                        (mem["user_id"], mem["content_hash"]),
                    )
                    if cur.fetchone():
                        # 已存在，直接标记为已晋升
                        conn.execute(
                            """UPDATE memory_episodic SET promoted_to_semantic = 1
                               WHERE id = %s""",
                            (mem["id"],),
                        )
                        continue

                    # 插入 Semantic 层
                    cur_insert = conn.execute(
                        """INSERT INTO memory_semantic
                           (user_id, memory_type, content, importance_score,
                            access_count, content_hash, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())""",
                        (
                            mem["user_id"], mem["memory_type"], encrypt_memory_content(mem["content"]),
                            mem["importance_score"], mem["access_count"],
                            mem["content_hash"],
                        ),
                    )
                    semantic_id = cur_insert.lastrowid if hasattr(cur_insert, 'lastrowid') else None

                    # 写入 Outbox 事件：删除旧 episodic 向量 + 创建新 semantic 向量
                    _now_episodic = mem["id"]
                    if semantic_id:
                        # 删除旧 episodic 向量
                        conn.execute(
                            """INSERT IGNORE INTO memory_outbox
                               (event_id, memory_id, memory_version, event_type,
                                target, payload, status, memory_layer, created_at)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                            (str(uuid.uuid4()), _now_episodic, 1, "delete_vector",
                             "milvus", json.dumps({
                                 "memory_id": _now_episodic, "user_id": mem["user_id"],
                                 "memory_layer": "episodic"
                             }, ensure_ascii=False), "pending", "episodic")
                        )
                        # 创建新 semantic 向量
                        conn.execute(
                            """INSERT IGNORE INTO memory_outbox
                               (event_id, memory_id, memory_version, event_type,
                                target, payload, status, memory_layer, created_at)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                            (str(uuid.uuid4()), semantic_id, 1, "upsert_vector",
                             "milvus", json.dumps({
                                 "memory_id": semantic_id, "user_id": mem["user_id"],
                                 "content": mem["content"][:500], "memory_type": mem["memory_type"],
                                 "importance": mem["importance_score"],
                                 "memory_layer": "semantic"
                             }, ensure_ascii=False), "pending", "semantic")
                        )

                    # 标记 Episodic 为已晋升
                    conn.execute(
                        """UPDATE memory_episodic SET promoted_to_semantic = 1
                           WHERE id = %s""",
                        (mem["id"],),
                    )
                    promoted += 1
                except Exception as e:
                    logger.debug(f"Promotion failed for memory {mem['id']}: {e}")
                    continue

            conn.commit()
            return promoted

        except Exception:
            conn.rollback()
            raise
        finally:
            conn._conn.autocommit = True
            conn.close()

    def _cleanup_expired_memories(self) -> int:
        """
        TTL 淘汰：软删除过期且低重要性的 Episodic 记忆。

        淘汰条件（同时满足）：
        1. importance_score < 0.3
        2. 超过 TTL（created_at + ttl_days < NOW()）
        3. is_user_pinned = 0 或 NULL（用户置顶豁免）
        4. 未晋升（promoted_to_semantic = 0 或 NULL）

        同时生成 delete_vector Outbox 事件，确保 Milvus 中对应向量被清理。

        Returns:
            淘汰的记忆数量
        """
        conn = get_conn()
        try:
            conn._conn.autocommit = False

            # 1. 先查询即将过期的记忆 ID（用于生成 delete_vector 事件）
            cur = conn.execute(
                """SELECT id, embedding_id, user_id
                   FROM memory_episodic
                   WHERE deleted_at IS NULL
                     AND importance_score < 0.3
                     AND (is_user_pinned IS NULL OR is_user_pinned = 0)
                     AND (promoted_to_semantic IS NULL OR promoted_to_semantic = 0)
                     AND created_at < DATE_SUB(NOW(), INTERVAL COALESCE(ttl_days, 30) DAY)"""
            )
            expired = [dict(r) for r in cur.fetchall()]

            if not expired:
                conn.commit()
                return 0

            expired_ids = [m["id"] for m in expired]

            # 2. 批量软删除
            placeholders = ','.join(['%s'] * len(expired_ids))
            conn.execute(
                f"""UPDATE memory_episodic
                    SET deleted_at = NOW(), updated_at = NOW()
                    WHERE id IN ({placeholders})""",
                expired_ids
            )

            # 3. 始终为过期记忆生成 delete_vector 事件（即使 embedding_id 为空，
            # 向量也可能已由 outbox worker 异步写入 Milvus，需要确保清理）
            for mem in expired:
                conn.execute(
                    """INSERT IGNORE INTO memory_outbox
                       (event_id, memory_id, memory_version, event_type,
                        target, payload, status, memory_layer, created_at)
                       VALUES (%s, %s, 1, 'delete_vector',
                               'milvus', %s, 'pending', 'episodic', NOW())""",
                    (str(uuid.uuid4()), mem["id"],
                     json.dumps({
                         "embedding_id": mem.get("embedding_id") or f"mem_{mem['id']}",
                         "memory_id": mem["id"],
                         "user_id": mem.get("user_id"),
                         "memory_layer": "episodic"
                     }, ensure_ascii=False))
                )

            conn.commit()
            return len(expired)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn._conn.autocommit = True
            conn.close()
    
    def _fetch_pending_events(self) -> List[Dict]:
        """
        领取待处理事件

        使用 locked_at + locked_by 实现简单的分布式锁。
        同时处理超时的锁（卡住的 Worker）。
        """
        conn = get_conn()
        try:
            # 事务模式：关闭自动提交
            conn._conn.autocommit = False

            # 1. 先清理超时的锁
            conn.execute(
                """UPDATE memory_outbox
                   SET status = 'pending',
                       locked_at = NULL,
                       locked_by = NULL
                   WHERE status = 'processing'
                     AND locked_at < DATE_SUB(NOW(), INTERVAL %s SECOND)""",
                (self._lock_timeout,)
            )

            # 2. 领取事件（使用 FOR UPDATE 防止竞争）
            # 注意：MySQL 8.0+ 可以用 FOR UPDATE SKIP LOCKED
            cur = conn.execute(
                """SELECT * FROM memory_outbox
                   WHERE status = 'pending'
                     AND available_at <= NOW()
                   ORDER BY id
                   LIMIT %s
                   FOR UPDATE""",
                (self._batch_size,)
            )
            rows = cur.fetchall()

            if not rows:
                conn.commit()
                return []

            # 3. 标记为 processing（参数化查询，避免 SQL 注入）
            event_ids = [row["id"] for row in rows]
            placeholders = ",".join(["%s"] * len(event_ids))

            conn.execute(
                f"""UPDATE memory_outbox
                   SET status = 'processing',
                       locked_at = NOW(),
                       locked_by = %s
                   WHERE id IN ({placeholders})""",
                (self._worker_id, *event_ids)
            )

            conn.commit()

            return [dict(row) for row in rows]

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to fetch events: {e}")
            return []
        finally:
            conn._conn.autocommit = True
            conn.close()
    
    def _process_event(self, event: Dict) -> None:
        """
        处理单个事件
        
        Args:
            event: 事件记录
        """
        event_id = event["id"]
        memory_id = event["memory_id"]
        memory_version = event["memory_version"]
        event_type_str = event["event_type"]
        target_str = event["target"]
        payload_str = event["payload"]
        
        try:
            event_type = EventType(event_type_str)
            target = Target(target_str)
            payload = json.loads(payload_str) if payload_str else {}
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Invalid event format: {e}")
            self._mark_failed(event_id, str(e), permanent=True)
            return
        
        try:
            # 获取处理器
            handler = self._handlers.get(target, {}).get(event_type)
            if not handler:
                raise ValueError(f"No handler for {target.value}.{event_type.value}")
            
            # 执行处理器（幂等）
            handler(memory_id, memory_version, payload)
            
            # 标记成功
            self._mark_processed(event_id)
            self._stats["processed"] += 1
            
            logger.debug(f"Processed event {event_id}: {target.value}.{event_type.value}")
            
        except Exception as e:
            # 标记失败
            logger.warning(f"Event {event_id} ({target_str}.{event_type_str}, memory_id={memory_id}) failed: {e}")
            self._mark_failed(event_id, str(e))
            self._stats["failed"] += 1
    
    def _mark_processed(self, event_id: int) -> None:
        """标记事件处理成功"""
        conn = get_conn()
        try:
            conn._conn.autocommit = False
            conn.execute(
                """UPDATE memory_outbox
                   SET status = %s,
                       processed_at = NOW()
                   WHERE id = %s""",
                (EventStatus.PROCESSED.value, event_id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to mark event processed: {e}")
            raise
        finally:
            conn._conn.autocommit = True
            conn.close()
    
    def _mark_failed(
        self,
        event_id: int,
        error: str,
        permanent: bool = False
    ) -> None:
        """
        标记事件处理失败

        Args:
            event_id: 事件 ID
            error: 错误信息
            permanent: 是否永久失败（不重试）
        """
        conn = get_conn()
        try:
            conn._conn.autocommit = False

            # 获取当前重试次数
            cur = conn.execute(
                "SELECT attempts FROM memory_outbox WHERE id = %s",
                (event_id,)
            )
            row = cur.fetchone()
            attempts = (row["attempts"] + 1) if row else 1

            if permanent or attempts >= self._max_attempts:
                # 超过最大重试次数，进入死信
                conn.execute(
                    """UPDATE memory_outbox
                       SET status = %s,
                           attempts = %s,
                           last_error = %s,
                           processed_at = NOW()
                       WHERE id = %s""",
                    (EventStatus.DEAD.value, attempts, error[:500], event_id)
                )
                self._stats["dead"] += 1
                logger.error(f"Event {event_id} entered dead letter queue: {error}")
            else:
                # 计算下次可用时间（指数退避）
                backoff_seconds = self._retry_backoff_base ** attempts
                available_at = datetime.now() + timedelta(seconds=backoff_seconds)

                conn.execute(
                    """UPDATE memory_outbox
                       SET status = %s,
                           attempts = %s,
                           last_error = %s,
                           available_at = %s,
                           locked_at = NULL,
                           locked_by = NULL
                       WHERE id = %s""",
                    (EventStatus.PENDING.value, attempts, error[:500], available_at, event_id)
                )
                self._stats["retried"] += 1
                logger.warning(f"Event {event_id} scheduled for retry (attempt {attempts}): {error[:200]}")

            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to mark event failed: {e}")
            raise
        finally:
            conn._conn.autocommit = True
            conn.close()


# ========== 处理器实现 ==========

def _get_mapper_for_layer(memory_layer: str):
    """根据记忆层级获取对应的 mapper"""
    if memory_layer == "semantic":
        from backend.db.memory_mapper import get_semantic_mapper
        return get_semantic_mapper()
    else:
        # episodic 或 legacy（旧事件兼容）均走 episodic
        from backend.db.memory_mapper import get_episodic_mapper
        return get_episodic_mapper()


def handle_upsert_vector(memory_id: int, expected_version: int, payload: Dict) -> None:
    """
    幂等写入向量

    流程：
    1. 根据 memory_layer 获取对应的 mapper
    2. 检查当前记忆版本，如果版本更新则跳过
    3. 生成 embedding
    4. 写入向量库（使用 memory_id 作为主键，幂等 upsert）
    5. 更新 embedding_id
    """
    from backend.infrastructure import get_memory_client

    memory_layer = payload.get("memory_layer", "legacy")
    mapper = _get_mapper_for_layer(memory_layer)

    # 1. 检查版本
    memory = mapper.get_memory_by_id(memory_id)
    if not memory:
        logger.warning(f"Memory {memory_id} not found (layer={memory_layer}), skip vector upsert")
        return

    if memory.get("version", 1) > expected_version:
        logger.info(f"Skip vector upsert: memory {memory_id} has newer version {memory.get('version')} > {expected_version}")
        return

    # 如果已有 embedding_id 且版本匹配，检查是否需要重新生成
    if memory.get("embedding_id") and memory.get("version") == expected_version:
        logger.debug(f"Vector already exists for memory {memory_id}, skip")
        return

    # ── Bug fix: 始终使用 mapper 返回的解密内容 ──
    # payload 可能来自 reconciler（曾未解密），memory 由 mapper 返回（已解密）
    decrypted_content = memory.get("content", "")
    if not decrypted_content:
        from backend.utils.crypto_utils import decrypt_memory_content
        decrypted_content = decrypt_memory_content(payload.get("content", ""))

    # 2. 生成 embedding（复用 RAG 管线 embedding 实例）
    try:
        from backend.rag.embeddings import get_embeddings

        embedding_model = get_embeddings()
        embedding = embedding_model.embed_query(decrypted_content)
    except Exception as e:
        raise RuntimeError(f"Failed to generate embedding: {e}")

    # 3. 写入向量库
    vector_client = get_memory_client()
    if not vector_client or not vector_client.is_available():
        raise RuntimeError("Vector store unavailable")

    # ⚠️ user_id 不能直接 payload["user_id"]：
    # reconciler 生成的修复事件历史上不带 user_id（reconciler.py 现已补上），
    # 旧实现会在这里抛 KeyError —— 实测事件重试 5 次后进死信队列，
    # 即"对账发现向量缺失 → 修复事件永远失败 → 漂移永远修不好"。
    # payload 里的 user_id 只是副本，记忆行本身才是权威来源，故回退到 memory["user_id"]；
    # 这样连库里已有的历史坏事件也能自愈，无需人工清理。
    user_id = payload.get("user_id")
    if user_id is None:
        user_id = memory.get("user_id")
    if user_id is None:
        raise RuntimeError(
            f"无法确定向量归属：payload 与记忆行都没有 user_id (memory_id={memory_id})"
        )
    collection_name = f"user_{user_id}_memories"
    vector_id = f"mem_{memory_id}"

    try:
        # 幂等 upsert: 先删除旧数据再插入
        vector_client.delete(collection_name, [vector_id])
        vector_client.insert(
            collection_name=collection_name,
            ids=[vector_id],
            embeddings=[embedding],
            metadatas=[{
                "memory_id": memory_id,
                "user_id": user_id,
                "version": expected_version,
                "memory_type": payload.get("memory_type", "general"),
                "memory_layer": memory_layer,
                "content": decrypted_content[:500]
            }]
        )
    except Exception as e:
        raise RuntimeError(f"Failed to upsert vector: {e}")

    # 4. 更新 embedding_id（回写 MySQL）
    # ⚠️ bump_version=False：这里只是把派生库的 id 写回，属于"元数据回写"，
    # 不是内容变更。若递增 version，同一条记忆的兄弟事件（upsert_graph_node
    # 用 memory_version 判断新旧）会被判成过期而静默跳过 —— 实测：
    # 晋升出的 semantic 记忆全部只写向量、不建图节点、不抽实体。
    update_ok, _ = mapper.update_memory(memory_id, embedding_id=vector_id, bump_version=False)
    if not update_ok:
        # 补偿：向量已写入 Milvus 但 embedding_id 回写失败（记忆可能已被软删除），
        # 立即删除刚写入的向量，防止残留脏数据
        logger.warning(
            f"embedding_id 回写失败 (memory_id={memory_id}, 可能已被删除)，"
            f"执行补偿删除向量 {vector_id}"
        )
        try:
            vector_client.delete(collection_name, [vector_id])
        except Exception as cleanup_err:
            logger.warning(f"补偿删除向量失败: {cleanup_err}")
    else:
        logger.debug(f"Vector upserted: {vector_id} (version={expected_version}, layer={memory_layer})")


def handle_delete_vector(memory_id: int, expected_version: int, payload: Dict) -> None:
    """
    幂等删除向量

    即使记忆在 MySQL 中已不存在，也尝试删除 Milvus 中的向量（清理脏数据）。
    """
    from backend.infrastructure import get_memory_client

    memory_layer = payload.get("memory_layer", "legacy")
    user_id = payload.get("user_id")
    mapper = _get_mapper_for_layer(memory_layer)
    # 传入 user_id 防止跨用户 ID 碰撞导致误判版本
    memory = mapper.get_memory_by_id(memory_id, user_id=user_id)

    # 如果记忆已不存在（已删除或从未存在），向量也应该删除
    if not memory:
        logger.debug(f"Memory {memory_id} not found (layer={memory_layer}), deleting vector if exists")

    # 如果版本更新，说明记忆已被恢复或更新，不删除
    if memory and memory.get("version", 1) > expected_version:
        logger.info(f"Skip vector delete: memory {memory_id} has newer version (layer={memory_layer})")
        return

    vector_client = get_memory_client()
    if vector_client and vector_client.is_available():
        vector_id = f"mem_{memory_id}"
        collection_name = f"user_{user_id}_memories" if user_id else None
        try:
            if collection_name:
                vector_client.delete(collection_name, [vector_id])
                logger.debug(f"Vector deleted: {vector_id} (layer={memory_layer})")
            else:
                logger.warning(
                    f"Cannot delete vector {vector_id}: user_id missing in payload, "
                    f"collection_name unknown"
                )
        except Exception as e:
            logger.warning(f"Failed to delete vector {vector_id}: {e}")
            raise  # 重新抛出以触发事件重试


def handle_upsert_graph_node(memory_id: int, expected_version: int, payload: Dict) -> None:
    """
    幂等写入图节点

    注意：只有 semantic 层和 legacy 层的记忆才会写入图节点

    流程：
    1. 写入 GraphMemory（Memory 节点 + FOLLOWS/SIMILAR_TO 边）
    2. 提取 Entity/Relation 写入 KGStore（文档图谱）← 新增
    """
    from backend.memory.graph_memory import get_graph_memory

    memory_layer = payload.get("memory_layer", "legacy")

    # episodic 层不写入图节点
    if memory_layer == "episodic":
        logger.debug(f"Skip graph upsert: episodic layer memory {memory_id}")
        return

    mapper = _get_mapper_for_layer(memory_layer)

    graph_memory = get_graph_memory()
    if not graph_memory or not graph_memory._available():
        raise RuntimeError("Graph store unavailable")

    # 检查版本
    memory = mapper.get_memory_by_id(memory_id)

    if not memory:
        logger.warning(f"Memory {memory_id} not found (layer={memory_layer}), skip graph upsert")
        return

    if memory.get("version", 1) > expected_version:
        logger.info(f"Skip graph upsert: memory {memory_id} has newer version (layer={memory_layer})")
        return

    # ── Bug fix: 始终使用 mapper 返回的解密内容，而非 payload 中的内容 ──
    # payload 可能来自 reconciler（曾未解密），memory 由 mapper 返回（已解密）
    # 这是最可靠的明文来源
    decrypted_content = memory.get("content", "")
    if not decrypted_content:
        # 兜底：如果 mapper 返回的 content 为空，尝试从 payload 取并解密
        from backend.utils.crypto_utils import decrypt_memory_content
        decrypted_content = decrypt_memory_content(payload.get("content", ""))

    # 1. 写入 GraphMemory（Memory 节点）
    # ⚠️ 必须把 memory_layer 传进去：Memory 节点身份是 "{layer}:{id}"。
    # episodic / semantic 两张表的 id 会重号（实测 218 条 semantic 全部与 episodic 重号），
    # 不带层级就会把两条不同记忆合并成同一个节点，后写的覆盖前一条。
    from backend.memory.types import MemoryItem
    item = MemoryItem(
        id=memory_id,
        content=decrypted_content,
        importance=payload.get("importance", 0.5),
        category=payload.get("memory_type", "general"),
        user_id=payload.get("user_id"),
        layer=memory_layer,
    )

    graph_memory.update_node(item)
    logger.debug(f"GraphMemory node upserted: {memory_id} (version={expected_version}, layer={memory_layer})")

    # 2. 提取 Entity/Relation 写入 KGStore（文档图谱）← 新增
    # 这样永久记忆的实体可以被 GraphRetriever 检索到
    _extract_entities_to_kgstore(
        memory_id=memory_id,
        content=decrypted_content,
        user_id=payload.get("user_id"),
        layer=memory_layer,
    )


def _extract_entities_to_kgstore(memory_id: int, content: str, user_id: Optional[int],
                                 layer: Optional[str] = None) -> None:
    """
    从记忆内容提取实体和关系，写入 KGStore（文档图谱）

    这样永久记忆的实体可以被 GraphRetriever 检索到，
    并享受实体对齐、时间属性提取等优化。

    Args:
        memory_id: 记忆ID
        content: 记忆内容
        user_id: 用户ID

    Raises:
        ExtractionLLMError: LLM 调用失败（429/500），调用方应让事件重试
    """
    try:
        from backend.graphrag import get_entity_extractor, get_kg_store, ExtractionLLMError

        # 检查图谱是否可用
        kg_store = get_kg_store()
        if not kg_store.is_available():
            logger.debug(f"KGStore unavailable, skip entity extraction for memory {memory_id}")
            return

        # 注：不再做熔断器预检。
        # 当 LLM 调用失败（429/500）时，extractor.extract 会抛出 ExtractionLLMError，
        # 由下方 except ExtractionLLMError 向上传播，让事件进入指数退避重试队列。
        # 这比预检更准确（不依赖私有 API），且 ModelRouter 自带降级链兜底。

        # P1-4 修复：先提取实体对象（内存中），成功后再删除旧实体，最后存储新实体
        # 避免提取失败时旧实体已被删除且无法恢复
        # 步骤 1：提取实体和关系（使用 EntityExtractor，支持实体对齐和时间属性提取）
        extractor = get_entity_extractor()
        result = extractor.extract(content, source_memory_id=memory_id)

        if not result.entities:
            logger.debug(f"No entities extracted from memory {memory_id}")
            return

        # 步骤 2：提取成功后，删除旧版本提取的实体和关系
        # 此时新实体尚未存储（还没有 source_memory_id），不会被误删
        kg_store.delete_entities_by_memory_id(memory_id, user_id)

        # 步骤 3：存储实体节点（启用实体对齐）
        entities_created = 0
        entity_ids = []
        for entity in result.entities:
            entity.source_memory_id = memory_id
            created_id = kg_store.create_entity(entity, user_id, enable_alignment=True)
            if created_id:
                entities_created += 1
                entity_ids.append(created_id)  # 使用实际存储的 ID（对齐合并时是已有实体的 ID）
            else:
                logger.warning(
                    f"[KG] Failed to create entity '{entity.name}' from memory {memory_id}"
                )

        # 存储关系（包含时间属性）
        relations_created = 0
        for relation in result.relations:
            relation.source_memory_id = memory_id
            if kg_store.create_relation(relation, user_id):
                relations_created += 1

        # Gap 5: 创建 Memory ↔ Entity 跨层边（连接 GraphMemory 和 KGStore 两层图谱）
        if entity_ids:
            kg_store.create_memory_entity_edges(memory_id, entity_ids, user_id, layer=layer)

        if entities_created > 0 or relations_created > 0:
            logger.info(
                f"KGStore: extracted {entities_created} entities, {relations_created} relations "
                f"from memory {memory_id} (cross-layer edges: {len(entity_ids)})"
            )

        # 记忆实体描述向量化（自适应检索的"实体优先"层，失败不影响主链路）
        if entity_ids:
            try:
                from backend.service.kb.entity_vectorstore import vectorize_memory_entities

                vectorize_memory_entities(user_id, memory_id)
            except Exception as e:
                logger.warning(f"[KG] 记忆实体向量化失败 memory_id={memory_id}: {e}")

    except ExtractionLLMError:
        # ── Bug fix: LLM 调用失败必须向上抛出 ──
        # 让 _process_event 捕获后标记事件为 failed → 进入重试队列（指数退避）
        # 而不是静默吞掉异常导致事件被标记为 processed
        raise
    except Exception as e:
        # 其他异常（KGStore 写入失败、解析错误等）不影响主流程，只记录警告
        logger.warning(f"Entity extraction failed for memory {memory_id}: {e}")


def handle_delete_graph_node(memory_id: int, expected_version: int, payload: Dict) -> None:
    """
    幂等删除图节点

    注意：只有 semantic 层和 legacy 层的记忆才会从图中删除
    """
    from backend.memory.graph_memory import get_graph_memory

    memory_layer = payload.get("memory_layer", "legacy")
    user_id = payload.get("user_id")

    # episodic 层不写入图节点，所以也不需要删除
    if memory_layer == "episodic":
        logger.debug(f"Skip graph delete: episodic layer memory {memory_id}")
        return

    mapper = _get_mapper_for_layer(memory_layer)

    # 检查记忆状态：软删除的继续清理图；活跃的仅在版本匹配时清理
    memory = mapper.get_memory_by_id(memory_id)
    if memory:
        is_soft_deleted = memory.get("deleted_at") is not None
        if not is_soft_deleted and memory.get("version", 1) > expected_version:
            logger.info(f"Skip graph delete: memory {memory_id} has newer version (layer={memory_layer})")
            return

    # 1. 清除缓存 + 软删除从该记忆提取的 KGStore 实体和关系
    try:
        from backend.graphrag.kg_store import get_kg_store
        kg_store = get_kg_store()
        if kg_store.is_available():
            kg_store.invalidate_cache_by_memory_id(memory_id)
            kg_store.delete_entities_by_memory_id(memory_id, user_id)
    except Exception as e:
        logger.warning(f"Failed to clean KGStore for memory {memory_id}: {e}")

    # 1.5 同步清理实体描述向量（图谱删了、向量还在 → 幽灵召回）
    # 删除失败必须向上抛：事件会标记 failed 并进入退避重试，而不是"标记成功但向量残留"
    from backend.service.kb.entity_vectorstore import delete_entity_vectors

    delete_entity_vectors(user_id, memory_id=memory_id)

    # 2. 删除图节点
    graph_memory = get_graph_memory()
    if graph_memory and graph_memory._available():
        graph_memory.delete_from_graph(memory_id, user_id=user_id)
        logger.debug(f"Graph node deleted: {memory_id} (layer={memory_layer})")


def handle_invalidate_cache(memory_id: int, expected_version: int, payload: Dict) -> None:
    """Redis 缓存失效处理器。

    处理 INVALIDATE_CACHE 事件，删除指定的 Redis 缓存 key。

    Args:
        payload: {
            "cache_keys": ["key1", "key2"],      # 精确匹配的 key
            "cache_patterns": ["pattern1:*"],    # 模式匹配的前缀
        }
    """
    from backend.infrastructure import get_cache

    cache = get_cache()
    if not cache:
        logger.warning("Cache not available, skipping invalidation")
        return

    cache_keys = payload.get("cache_keys", [])
    cache_patterns = payload.get("cache_patterns", [])

    # 删除精确匹配的 key
    for key in cache_keys:
        cache.delete(key)
        logger.debug(f"Cache invalidated via outbox: {key}")

    # 删除模式匹配的 key
    for pattern in cache_patterns:
        cache.delete_pattern(pattern)
        logger.debug(f"Cache pattern invalidated via outbox: {pattern}")

    if cache_keys or cache_patterns:
        logger.info(
            f"Cache invalidation completed: {len(cache_keys)} keys, "
            f"{len(cache_patterns)} patterns"
        )


# ========== 单例和初始化 ==========

_outbox_worker: Optional[OutboxWorker] = None
_worker_lock = threading.Lock()


def get_outbox_worker() -> OutboxWorker:
    """获取 OutboxWorker 单例"""
    global _outbox_worker
    with _worker_lock:
        if _outbox_worker is None:
            _outbox_worker = OutboxWorker()
            
            # 注册默认处理器
            _outbox_worker.register_handler(
                Target.MILVUS, EventType.UPSERT_VECTOR, handle_upsert_vector
            )
            _outbox_worker.register_handler(
                Target.MILVUS, EventType.DELETE_VECTOR, handle_delete_vector
            )
            _outbox_worker.register_handler(
                Target.NEO4J, EventType.UPSERT_GRAPH_NODE, handle_upsert_graph_node
            )
            _outbox_worker.register_handler(
                Target.NEO4J, EventType.DELETE_GRAPH_NODE, handle_delete_graph_node
            )
            # Redis 缓存失效处理器
            _outbox_worker.register_handler(
                Target.REDIS, EventType.INVALIDATE_CACHE, handle_invalidate_cache
            )

        return _outbox_worker


def start_outbox_worker() -> None:
    """启动 Outbox Worker"""
    worker = get_outbox_worker()
    worker.start()


def stop_outbox_worker() -> None:
    """停止 Outbox Worker"""
    global _outbox_worker
    if _outbox_worker:
        _outbox_worker.stop()