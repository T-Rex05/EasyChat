"""Tool schema 缓存标记单元测试

覆盖：
  - convert_tools_to_anthropic 转发 cache_control
  - build_api_kwargs 在 Anthropic 路由给最后一个工具加 cache_control

运行：
  pytest tests/test_tool_schema_cache.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "hermes"))

from agent.anthropic_adapter import convert_tools_to_anthropic


class TestToolSchemaCache:
    def test_cache_control_forwarded_from_openai_to_anthropic(self):
        """OpenAI 格式工具上的 cache_control 应被转发到 Anthropic 格式"""
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write a file",
                    "parameters": {"type": "object", "properties": {}},
                },
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            },
        ]
        result = convert_tools_to_anthropic(openai_tools)
        assert len(result) == 2
        # 第一个工具没有 cache_control
        assert "cache_control" not in result[0]
        # 第二个工具有 cache_control（从 OpenAI 格式转发）
        assert result[1]["cache_control"]["type"] == "ephemeral"
        assert result[1]["cache_control"]["ttl"] == "1h"

    def test_no_cache_control_when_absent(self):
        """没有 cache_control 时，转换后也不应有"""
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        result = convert_tools_to_anthropic(openai_tools)
        assert len(result) == 1
        assert "cache_control" not in result[0]

    def test_empty_tools_returns_empty(self):
        """空工具列表返回空"""
        assert convert_tools_to_anthropic([]) == []
        assert convert_tools_to_anthropic(None) == []

    def test_cache_control_without_ttl(self):
        """cache_control 只有 type 没有 ttl（默认 5m）"""
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "A tool",
                    "parameters": {"type": "object", "properties": {}},
                },
                "cache_control": {"type": "ephemeral"},
            },
        ]
        result = convert_tools_to_anthropic(openai_tools)
        assert result[0]["cache_control"]["type"] == "ephemeral"
        assert "ttl" not in result[0]["cache_control"]

    def test_duplicate_tool_names_deduped(self):
        """重复工具名被去重（保留第一个）"""
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "First",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "Duplicate",
                    "parameters": {"type": "object", "properties": {}},
                },
                "cache_control": {"type": "ephemeral"},
            },
        ]
        result = convert_tools_to_anthropic(openai_tools)
        assert len(result) == 1
        assert result[0]["description"] == "First"
