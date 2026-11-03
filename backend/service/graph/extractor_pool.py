"""
GraphRAG 提取线程池服务

核心设计：
- 固定工作线程池（默认 4 个）
- Chunk 任务队列，线程空闲时自动取下一个
- 文档进度追踪
- MERGE 幂等写入，无需额外锁

使用方式：
    pool = get_extractor_pool()
    
    # 提交文档提取
    pool.submit_document(user_id=1, document_id=123)
    
    # 查询进度
    progress = pool.get_progress(document_id=123)
    # {"pending": 50, "processed": 50, "total": 100, "percent": 50.0}
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from queue import Queue

from backend.utils.log_utils import log

logger = log


@dataclass
class ChunkTask:
    """Chunk 提取任务"""
    document_id: int
    chunk_id: int
    content: str
    user_id: int
    submitted_at: float = field(default_factory=time.time)


@dataclass 
class DocumentProgress:
    """文档提取进度"""
    document_id: int
    user_id: int
    total_chunks: int = 0
    processed_chunks: int = 0
    entities_created: int = 0
    relations_created: int = 0
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    status: str = "pending"  # pending / processing / completed / failed
    error: Optional[str] = None
    
    @property
    def pending_chunks(self) -> int:
        return self.total_chunks - self.processed_chunks
    
    @property
    def percent(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return (self.processed_chunks / self.total_chunks) * 100
    
    @property
    def is_completed(self) -> bool:
        return self.status == "completed"
    
    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "total_chunks": self.total_chunks,
            "processed_chunks": self.processed_chunks,
            "pending_chunks": self.pending_chunks,
            "percent": round(self.percent, 1),
            "entities_created": self.entities_created,
            "relations_created": self.relations_created,
            "status": self.status,
            "error": self.error,
            "elapsed_seconds": round(time.time() - self.started_at, 1) if self.status != "completed" else round((self.completed_at or time.time()) - self.started_at, 1)
        }


class GraphExtractorPool:
    """
    GraphRAG 提取线程池
    
    特点：
    - 固定线程池，避免过度并发
    - Chunk 级并发，单文档也能多线程加速
    - 文档进度追踪
    - MERGE 幂等写入，无需额外锁
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        chunk_timeout: float = 300.0
    ):
        self._max_workers = max_workers
        self._chunk_timeout = chunk_timeout
        
        # 线程池
        self._executor: Optional[ThreadPoolExecutor] = None
        
        # 任务队列
        self._task_queue: Queue[ChunkTask] = Queue()
        
        # 文档进度
        self._progress: Dict[int, DocumentProgress] = {}
        self._progress_lock = threading.Lock()
        
        # 正在处理的文档（防止重复提交）
        self._processing_docs: Set[int] = set()
        self._processing_lock = threading.Lock()
        
        # 运行状态
        self._running = False
        self._shutdown = False
        
        # 统计
        self._stats = {
            "documents_processed": 0,
            "chunks_processed": 0,
            "entities_created": 0,
            "relations_created": 0,
        }
    
    def start(self) -> None:
        """启动线程池"""
        if self._running:
            return
        
        self._running = True
        self._shutdown = False
        
        # 创建线程池
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="kg-extractor"
        )
        
        # 启动队列消费者
        for i in range(self._max_workers):
            self._executor.submit(self._worker, i)
        
        logger.info(f"[KG-Pool] Started with {self._max_workers} workers")
    
    def stop(self) -> None:
        """停止线程池"""
        if not self._running:
            return
        
        self._shutdown = True
        self._running = False
        
        # 清空队列
        while not self._task_queue.empty():
            try:
                self._task_queue.get_nowait()
            except Exception:
                break
        
        # 关闭线程池
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None
        
        logger.info(f"[KG-Pool] Stopped. Stats: {self._stats}")
    
    def submit_document(
        self,
        user_id: int,
        document_id: int,
        chunks: List[Dict[str, Any]]
    ) -> bool:
        """
        提交文档提取任务
        
        Args:
            user_id: 用户 ID
            document_id: 文档 ID
            chunks: 父片列表 [{"id": int, "content": str}, ...]
            
        Returns:
            是否成功提交（False 表示文档正在处理中）
        """
        # 检查是否已在处理
        with self._processing_lock:
            if document_id in self._processing_docs:
                logger.info(f"[KG-Pool] Document {document_id} already in progress")
                return False
            self._processing_docs.add(document_id)
        
        # 初始化进度
        with self._progress_lock:
            self._progress[document_id] = DocumentProgress(
                document_id=document_id,
                user_id=user_id,
                total_chunks=len(chunks),
                status="processing"
            )
        
        # 提交所有 chunks 到队列
        for chunk in chunks:
            task = ChunkTask(
                document_id=document_id,
                chunk_id=chunk["id"],
                content=chunk.get("content", ""),
                user_id=user_id
            )
            self._task_queue.put(task)
        
        logger.info(f"[KG-Pool] Submitted doc_id={document_id}, chunks={len(chunks)}")
        return True
    
    def get_progress(self, document_id: int) -> Optional[Dict[str, Any]]:
        """获取文档提取进度"""
        with self._progress_lock:
            if document_id not in self._progress:
                return None
            return self._progress[document_id].to_dict()
    
    def get_all_progress(self) -> List[Dict[str, Any]]:
        """获取所有文档的进度"""
        with self._progress_lock:
            return [p.to_dict() for p in self._progress.values()]
    
    def get_queue_size(self) -> int:
        """获取队列中待处理的任务数"""
        return self._task_queue.qsize()
    
    def is_document_processing(self, document_id: int) -> bool:
        """检查文档是否正在处理"""
        with self._processing_lock:
            return document_id in self._processing_docs
    
    def _worker(self, worker_id: int) -> None:
        """工作线程"""
        logger.debug(f"[KG-Pool] Worker {worker_id} started")
        
        while not self._shutdown:
            try:
                # 从队列获取任务（带超时，避免永久阻塞）
                try:
                    task = self._task_queue.get(timeout=1.0)
                except Exception:
                    # 队列为空，继续等待
                    continue
                
                # 处理任务
                self._process_chunk(task, worker_id)
                
            except Exception as e:
                logger.error(f"[KG-Pool] Worker {worker_id} error: {e}")
        
        logger.debug(f"[KG-Pool] Worker {worker_id} stopped")
    
    def _process_chunk(self, task: ChunkTask, worker_id: int) -> None:
        """处理单个 Chunk"""
        from backend.graphrag.kg_store import get_kg_store
        from backend.graphrag.extractor import get_entity_extractor
        
        kg_store = get_kg_store()
        if not kg_store.is_available():
            logger.warning(f"[KG-Pool] Neo4j not available, skipping chunk {task.chunk_id}")
            self._update_progress(task.document_id, 0, 0)
            return
        
        try:
            extractor = get_entity_extractor()
            
            # 提取实体关系
            extraction = extractor.extract(
                text=task.content,
                source_document_id=task.document_id,
                source_chunk_id=task.chunk_id
            )
            
            entities_count = 0
            relations_count = 0
            
            # 写入实体（启用对齐，返回的 ID 可能是合并后已有实体的 ID）
            for entity in extraction.entities:
                created_id = kg_store.create_entity(entity, task.user_id, enable_alignment=True)
                if created_id:
                    entities_count += 1
                else:
                    logger.warning(
                        f"[KG-Pool] Failed to create entity '{entity.name}' for chunk {task.chunk_id}"
                    )
            
            # 写入关系
            for relation in extraction.relations:
                if kg_store.create_relation(relation, task.user_id):
                    relations_count += 1
            
            # 更新进度
            self._update_progress(task.document_id, entities_count, relations_count)
            
            logger.debug(
                f"[KG-Pool] Worker {worker_id} processed chunk {task.chunk_id}: "
                f"{entities_count} entities, {relations_count} relations"
            )
            
        except Exception as e:
            logger.error(f"[KG-Pool] Failed to process chunk {task.chunk_id}: {e}")
            self._update_progress(task.document_id, 0, 0)
    
    def _update_progress(
        self,
        document_id: int,
        entities_count: int,
        relations_count: int
    ) -> None:
        """更新文档进度"""
        completed_user_id = None
        with self._progress_lock:
            if document_id not in self._progress:
                return

            progress = self._progress[document_id]
            progress.processed_chunks += 1
            progress.entities_created += entities_count
            progress.relations_created += relations_count

            # 检查是否完成
            if progress.processed_chunks >= progress.total_chunks:
                progress.status = "completed"
                progress.completed_at = time.time()

                # 更新统计
                self._stats["documents_processed"] += 1
                self._stats["chunks_processed"] += progress.processed_chunks
                self._stats["entities_created"] += progress.entities_created
                self._stats["relations_created"] += progress.relations_created

                # 更新 MySQL 标记
                self._update_document_flag(document_id, True)

                # 从正在处理集合中移除
                with self._processing_lock:
                    self._processing_docs.discard(document_id)

                logger.info(
                    f"[KG-Pool] Document {document_id} completed: "
                    f"{progress.entities_created} entities, {progress.relations_created} relations"
                )
                completed_user_id = progress.user_id

        # 实体描述向量化放在锁外：涉及 embedding API + 向量库 IO，
        # 持锁执行会阻塞其它文档的进度更新。
        if completed_user_id:
            try:
                from backend.service.kb.entity_vectorstore import vectorize_document_entities

                vectorize_document_entities(completed_user_id, document_id)
            except Exception as e:
                logger.warning(f"[KG-Pool] 实体向量化失败 doc_id={document_id}: {e}")
    
    def _update_document_flag(self, document_id: int, extracted: bool) -> None:
        """更新文档的 graph_extracted 标记"""
        try:
            from backend.db.schema import get_conn
            conn = get_conn()
            conn.execute(
                "UPDATE kb_documents SET graph_extracted = %s WHERE id = %s",
                (1 if extracted else 0, document_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[KG-Pool] Failed to update flag for doc {document_id}: {e}")


# 单例
_pool: Optional[GraphExtractorPool] = None
_pool_lock = threading.Lock()


def get_extractor_pool() -> GraphExtractorPool:
    """获取提取线程池单例"""
    global _pool
    with _pool_lock:
        if _pool is None:
            max_workers = int(os.getenv("KG_EXTRACTOR_THREADS", "4") or 4)
            _pool = GraphExtractorPool(max_workers=max_workers)
        return _pool


def start_extractor_pool() -> None:
    """启动提取线程池"""
    get_extractor_pool().start()


def stop_extractor_pool() -> None:
    """停止提取线程池"""
    global _pool
    if _pool:
        _pool.stop()