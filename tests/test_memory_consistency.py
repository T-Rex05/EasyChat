"""
测试记忆一致性架构

测试内容：
1. 版本号机制
2. Outbox 事件写入
3. 乐观锁更新
4. 软删除
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

# 导入被测试的模块
from backend.service.memory.outbox_types import (
    EventType, Target, EventStatus,
    OutboxEvent, compute_content_hash, generate_repair_event_id
)
from backend.service.memory.outbox_writer import OutboxWriter


class TestOutboxTypes:
    """测试 Outbox 类型定义"""
    
    def test_event_type_values(self):
        """测试事件类型枚举值"""
        assert EventType.UPSERT_VECTOR.value == "upsert_vector"
        assert EventType.DELETE_VECTOR.value == "delete_vector"
        assert EventType.UPSERT_GRAPH_NODE.value == "upsert_graph_node"
        assert EventType.DELETE_GRAPH_NODE.value == "delete_graph_node"
    
    def test_target_values(self):
        """测试目标库枚举值"""
        assert Target.MILVUS.value == "milvus"
        assert Target.NEO4J.value == "neo4j"
    
    def test_outbox_event_create(self):
        """测试事件创建"""
        event = OutboxEvent.create(
            memory_id=123,
            memory_version=1,
            event_type=EventType.UPSERT_VECTOR,
            target=Target.MILVUS,
            payload={"content": "test"}
        )
        
        assert event.memory_id == 123
        assert event.memory_version == 1
        assert event.event_type == EventType.UPSERT_VECTOR
        assert event.target == Target.MILVUS
        assert event.payload["content"] == "test"
        assert len(event.event_id) == 36  # UUID 格式
    
    def test_outbox_event_to_dict(self):
        """测试事件序列化"""
        event = OutboxEvent.create(
            memory_id=123,
            memory_version=1,
            event_type=EventType.UPSERT_VECTOR,
            target=Target.MILVUS,
            payload={"content": "test"}
        )
        
        data = event.to_dict()
        
        assert data["memory_id"] == 123
        assert data["event_type"] == "upsert_vector"
        assert data["target"] == "milvus"
    
    def test_compute_content_hash(self):
        """测试内容哈希计算"""
        hash1 = compute_content_hash("用户喜欢咖啡", "preference", 0.8)
        hash2 = compute_content_hash("用户喜欢咖啡", "preference", 0.8)
        hash3 = compute_content_hash("用户喜欢茶", "preference", 0.8)
        
        # 相同输入产生相同哈希
        assert hash1 == hash2
        # 不同输入产生不同哈希
        assert hash1 != hash3
        # 哈希长度为 32
        assert len(hash1) == 32
    
    def test_generate_repair_event_id(self):
        """测试修复事件 ID 生成（幂等）"""
        # 同样的参数应该产生相同 ID（幂等，配合 INSERT IGNORE 去重）
        id1 = generate_repair_event_id(123, EventType.UPSERT_VECTOR, Target.MILVUS)
        id2 = generate_repair_event_id(123, EventType.UPSERT_VECTOR, Target.MILVUS)

        # 幂等：相同参数 → 相同 ID
        assert id1 == id2
        # 格式应该是 repair- 前缀
        assert id1.startswith("repair-")
        assert "123" in id1
        assert "upsert_vector" in id1


class TestOutboxWriter:
    """测试 Outbox 写入器"""
    
    def test_write_events_empty(self):
        """测试空事件列表"""
        writer = OutboxWriter()
        mock_conn = Mock()
        
        result = writer.write_events(mock_conn, [])
        
        assert result is True
        # 不应该执行任何 SQL
        mock_conn.execute.assert_not_called()
    
    def test_write_events_single(self):
        """测试写入单个事件"""
        writer = OutboxWriter()
        mock_conn = Mock()
        
        event = OutboxEvent.create(
            memory_id=123,
            memory_version=1,
            event_type=EventType.UPSERT_VECTOR,
            target=Target.MILVUS,
            payload={"content": "test"}
        )
        
        result = writer.write_events(mock_conn, [event])
        
        assert result is True
        mock_conn.execute.assert_called_once()
        
        # 验证 SQL 参数
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        assert "INSERT IGNORE INTO memory_outbox" in sql
        assert params[1] == 123  # memory_id
        assert params[2] == 1    # memory_version
        assert params[3] == "upsert_vector"
        assert params[4] == "milvus"
    
    def test_write_events_multiple(self):
        """测试批量写入事件"""
        writer = OutboxWriter()
        mock_conn = Mock()
        
        events = [
            OutboxEvent.create(1, 1, EventType.UPSERT_VECTOR, Target.MILVUS, {}),
            OutboxEvent.create(2, 1, EventType.UPSERT_GRAPH_NODE, Target.NEO4J, {}),
        ]
        
        result = writer.write_events(mock_conn, events)
        
        assert result is True
        assert mock_conn.execute.call_count == 2



class TestMemoryServiceOutbox:
    """测试 MemoryService Outbox 集成"""
    
    @patch('backend.db.schema.get_conn')
    @patch('backend.service.memory.outbox_writer.get_outbox_writer')
    def test_create_memory_with_outbox(self, mock_outbox_writer, mock_get_conn):
        """测试创建记忆时写入 Outbox 事件"""
        from backend.service.memory.memory_service import MemoryService
        
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.lastrowid = 123
        mock_conn.execute.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        
        mock_writer = Mock()
        mock_writer.write_events.return_value = True
        mock_outbox_writer.return_value = mock_writer
        
        service = MemoryService()

        # Mock mapper (create_memory 委托到 create_episodic，使用 _episodic_mapper)
        with patch.object(service._episodic_mapper, 'create_memory', return_value=123):
            result = service.create_memory(
                user_id=1,
                memory_type="preference",
                content="用户喜欢咖啡"
            )
            
            # 应该成功
            assert result == 123
            
            # 应该写入 Outbox 事件
            mock_writer.write_events.assert_called_once()
            
            # 验证事件内容（episodic 层只生成向量事件，不入图）
            events = mock_writer.write_events.call_args[0][1]
            assert len(events) == 1  # 只有向量事件


if __name__ == "__main__":
    pytest.main([__file__, "-v"])