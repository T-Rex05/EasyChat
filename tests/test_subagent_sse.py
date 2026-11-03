"""子 Agent SSE 可视化 -- 单元测试

覆盖：
  - SSE 帧类型常量完整性
  - _push_subagent_sse 正确推送帧到 queue
  - ContextVar 隔离和降级行为
  - 各事件类型的数据结构正确性

运行：
  pytest tests/test_subagent_sse.py -v
"""

import json
import queue
import pytest
from unittest.mock import patch


class TestSSEFrameContract:
    """SSE 帧类型定义"""

    def test_new_frame_types_defined(self):
        from backend.service.sse_frame_contract import (
            FRAME_SUBAGENT_START,
            FRAME_SUBAGENT_TOKEN,
            FRAME_SUBAGENT_TOOL,
            FRAME_SUBAGENT_COMPLETE,
        )
        assert FRAME_SUBAGENT_START == "subagent_start"
        assert FRAME_SUBAGENT_TOKEN == "subagent_token"
        assert FRAME_SUBAGENT_TOOL == "subagent_tool"
        assert FRAME_SUBAGENT_COMPLETE == "subagent_complete"

    def test_all_frame_types_includes_subagent(self):
        from backend.service.sse_frame_contract import ALL_FRAME_TYPES
        assert "subagent_start" in ALL_FRAME_TYPES
        assert "subagent_token" in ALL_FRAME_TYPES
        assert "subagent_tool" in ALL_FRAME_TYPES
        assert "subagent_complete" in ALL_FRAME_TYPES


class TestPushSubagentSSE:
    """_push_subagent_sse 函数"""

    def test_push_to_queue(self):
        """正常推送到 queue"""
        from backend.service.delegation.sse_bridge import _push_subagent_sse, _DELEGATION_SSE_QUEUE_CTX

        q = queue.Queue()
        token = _DELEGATION_SSE_QUEUE_CTX.set(q)
        try:
            _push_subagent_sse("subagent_start", {
                "subagent_id": "sa-001",
                "goal": "查询物流",
                "depth": 0,
                "model": "qwen3-coder-plus",
            })
        finally:
            _DELEGATION_SSE_QUEUE_CTX.reset(token)

        assert not q.empty()
        frame = q.get_nowait()
        assert frame.startswith("data: ")
        data = json.loads(frame[6:].strip())
        assert data["type"] == "subagent_start"
        assert data["subagent_id"] == "sa-001"
        assert data["goal"] == "查询物流"

    def test_no_queue_silent_skip(self):
        """queue 未设置时静默跳过"""
        from backend.service.delegation.sse_bridge import _push_subagent_sse, _DELEGATION_SSE_QUEUE_CTX

        # 确保 ContextVar 为 None
        token = _DELEGATION_SSE_QUEUE_CTX.set(None)
        try:
            # 不应抛异常
            _push_subagent_sse("subagent_start", {"subagent_id": "sa-001"})
        finally:
            _DELEGATION_SSE_QUEUE_CTX.reset(token)

    def test_queue_exception_silent(self):
        """queue.put 异常时静默跳过"""
        from backend.service.delegation.sse_bridge import _push_subagent_sse, _DELEGATION_SSE_QUEUE_CTX

        class BrokenQueue:
            def put(self, item):
                raise RuntimeError("queue broken")

        token = _DELEGATION_SSE_QUEUE_CTX.set(BrokenQueue())
        try:
            # 不应抛异常
            _push_subagent_sse("subagent_start", {"subagent_id": "sa-001"})
        finally:
            _DELEGATION_SSE_QUEUE_CTX.reset(token)

    def test_subagent_token_frame(self):
        """subagent_token 帧格式"""
        from backend.service.delegation.sse_bridge import _push_subagent_sse, _DELEGATION_SSE_QUEUE_CTX

        q = queue.Queue()
        token = _DELEGATION_SSE_QUEUE_CTX.set(q)
        try:
            _push_subagent_sse("subagent_token", {
                "subagent_id": "sa-001",
                "content": "正在查询...",
            })
        finally:
            _DELEGATION_SSE_QUEUE_CTX.reset(token)

        data = json.loads(q.get_nowait()[6:].strip())
        assert data["type"] == "subagent_token"
        assert data["content"] == "正在查询..."

    def test_subagent_tool_frame(self):
        """subagent_tool 帧格式"""
        from backend.service.delegation.sse_bridge import _push_subagent_sse, _DELEGATION_SSE_QUEUE_CTX

        q = queue.Queue()
        token = _DELEGATION_SSE_QUEUE_CTX.set(q)
        try:
            _push_subagent_sse("subagent_tool", {
                "subagent_id": "sa-001",
                "tool_name": "web_search",
                "preview": "查询物流状态",
            })
        finally:
            _DELEGATION_SSE_QUEUE_CTX.reset(token)

        data = json.loads(q.get_nowait()[6:].strip())
        assert data["type"] == "subagent_tool"
        assert data["tool_name"] == "web_search"

    def test_subagent_complete_frame(self):
        """subagent_complete 帧格式"""
        from backend.service.delegation.sse_bridge import _push_subagent_sse, _DELEGATION_SSE_QUEUE_CTX

        q = queue.Queue()
        token = _DELEGATION_SSE_QUEUE_CTX.set(q)
        try:
            _push_subagent_sse("subagent_complete", {
                "subagent_id": "sa-001",
                "status": "completed",
                "summary": "物流状态已查询完毕",
                "duration_seconds": 12.5,
                "tokens": {"input": 1500, "output": 300},
                "api_calls": 3,
            })
        finally:
            _DELEGATION_SSE_QUEUE_CTX.reset(token)

        data = json.loads(q.get_nowait()[6:].strip())
        assert data["type"] == "subagent_complete"
        assert data["status"] == "completed"
        assert data["duration_seconds"] == 12.5
        assert data["tokens"]["input"] == 1500

    def test_unicode_content(self):
        """中文/特殊字符正确序列化"""
        from backend.service.delegation.sse_bridge import _push_subagent_sse, _DELEGATION_SSE_QUEUE_CTX

        q = queue.Queue()
        token = _DELEGATION_SSE_QUEUE_CTX.set(q)
        try:
            _push_subagent_sse("subagent_token", {
                "subagent_id": "sa-001",
                "content": "中文内容 🎉 émojis",
            })
        finally:
            _DELEGATION_SSE_QUEUE_CTX.reset(token)

        frame = q.get_nowait()
        data = json.loads(frame[6:].strip())
        assert data["content"] == "中文内容 🎉 émojis"

    def test_multiple_events_ordering(self):
        """多事件顺序正确"""
        from backend.service.delegation.sse_bridge import _push_subagent_sse, _DELEGATION_SSE_QUEUE_CTX

        q = queue.Queue()
        token = _DELEGATION_SSE_QUEUE_CTX.set(q)
        try:
            _push_subagent_sse("subagent_start", {"subagent_id": "sa-001"})
            _push_subagent_sse("subagent_tool", {"subagent_id": "sa-001", "tool_name": "web_search"})
            _push_subagent_sse("subagent_token", {"subagent_id": "sa-001", "content": "结果"})
            _push_subagent_sse("subagent_complete", {"subagent_id": "sa-001", "status": "completed"})
        finally:
            _DELEGATION_SSE_QUEUE_CTX.reset(token)

        types = []
        while not q.empty():
            data = json.loads(q.get_nowait()[6:].strip())
            types.append(data["type"])

        assert types == ["subagent_start", "subagent_tool", "subagent_token", "subagent_complete"]
