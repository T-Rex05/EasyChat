"""
Outbox Writer - Outbox 事件写入器

核心职责：
- 与业务操作在同一个事务中写入事件
- 确保业务数据 + 同步事件要么都成功，要么都回滚
- 支持批量写入

使用方式：
    # 在业务事务中
    conn = get_conn()
    try:
        # 1. 写业务数据
        conn.execute("INSERT INTO memory_episodic ...")
        
        # 2. 写 outbox 事件（同一事务）
        outbox_writer.write_events(conn, events)
        
        # 3. 提交事务
        conn.commit()
    except Exception:
        conn.rollback()
"""

import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Any

from backend.service.memory.outbox_types import (
    OutboxEvent,
    EventStatus,
    EventType,
    Target,
    compute_content_hash,
    generate_repair_event_id,
)

logger = logging.getLogger(__name__)


class OutboxWriter:
    """
    Outbox 写入器
    
    所有方法设计为在调用方事务中执行，不自己管理事务。
    """
    
    def __init__(self):
        pass
    
    def write_events(
        self,
        conn: Any,
        events: List[OutboxEvent],
        memory_layer: str = "legacy"
    ) -> bool:
        """
        批量写入事件（在调用方事务中执行）

        Args:
            conn: 数据库连接（复用调用方的事务）
            events: 事件列表
            memory_layer: 记忆层级（legacy/episodic/semantic）

        Returns:
            是否成功
        """
        if not events:
            return True

        try:
            for event in events:
                # 使用 INSERT IGNORE 避免重复 event_id 报错（幂等写入）
                conn.execute(
                    """INSERT IGNORE INTO memory_outbox
                       (event_id, memory_id, memory_version, event_type,
                        target, payload, status, memory_layer, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                    (
                        event.event_id,
                        event.memory_id,
                        event.memory_version,
                        event.event_type.value,
                        event.target.value,
                        json.dumps(event.payload, ensure_ascii=False),
                        EventStatus.PENDING.value,
                        memory_layer
                    )
                )

            logger.debug(f"Written {len(events)} events to outbox (layer={memory_layer})")
            return True

        except Exception as e:
            logger.error(f"Failed to write outbox events: {e}")
            return False
    
    def write_single_event(
        self,
        conn: Any,
        event: OutboxEvent,
        memory_layer: str = "legacy"
    ) -> bool:
        """写入单个事件"""
        return self.write_events(conn, [event], memory_layer=memory_layer)
    
    def write_repair_event(
        self,
        conn: Any,
        memory_id: int,
        memory_version: int,
        event_type: str,
        target: str,
        payload: dict,
        event_id: Optional[str] = None,
        memory_layer: str = "legacy"
    ) -> bool:
        """
        写入修复事件（幂等）
        
        使用 INSERT IGNORE 避免重复创建修复事件。
        修复事件的 event_id 包含 memory_id 和 event_type，确保幂等。
        
        Args:
            conn: 数据库连接
            memory_id: 记忆 ID
            memory_version: 记忆版本
            event_type: 事件类型
            target: 目标库
            payload: 事件载荷
            event_id: 可选的事件 ID（不提供则自动生成）
        """
        if event_id is None:
            event_id = generate_repair_event_id(
                memory_id,
                EventType(event_type),
                Target(target)
            )
        
        try:
            cur = conn.execute(
                """INSERT IGNORE INTO memory_outbox
                   (event_id, memory_id, memory_version, event_type,
                    target, payload, status, memory_layer, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, NOW())""",
                (
                    event_id,
                    memory_id,
                    memory_version,
                    event_type,
                    target,
                    json.dumps(payload, ensure_ascii=False),
                    memory_layer
                )
            )
            # 按 rowcount 判断是否真的新建
            rowcount = getattr(cur, 'rowcount', 0) or 0
            return rowcount > 0
        except Exception as e:
            logger.warning(f"Failed to write repair event: {e}")
            return False


# 单例
_outbox_writer: Optional[OutboxWriter] = None


def get_outbox_writer() -> OutboxWriter:
    """获取 OutboxWriter 单例"""
    global _outbox_writer
    if _outbox_writer is None:
        _outbox_writer = OutboxWriter()
    return _outbox_writer