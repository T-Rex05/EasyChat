"""语义 TTL 分级单元测试

覆盖：
  - apply_anthropic_cache_control 的 static_system_ttl 参数
  - 静态前缀用长 TTL，易变后缀和最近消息用短 TTL
  - 向后兼容：不传 static_system_ttl 时行为不变
  - 无静态前缀时 static_system_ttl 不影响任何东西

运行：
  pytest tests/test_semantic_ttl.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "hermes"))

from agent.prompt_caching import apply_anthropic_cache_control


def _extract_markers(messages):
    """提取所有 cache_control marker，返回 [(role, ttl)] 列表"""
    result = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "cache_control" in part:
                    ttl = part["cache_control"].get("ttl", "5m")
                    result.append((role, ttl))
        elif isinstance(content, str) and "cache_control" in msg:
            ttl = msg["cache_control"].get("ttl", "5m")
            result.append((role, ttl))
    return result


class TestSemanticTTL:
    def test_backward_compat_no_static_ttl(self):
        """不传 static_system_ttl 时，所有标记用同一 TTL"""
        msgs = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = apply_anthropic_cache_control(msgs, cache_ttl="5m")
        markers = _extract_markers(result)
        # 所有标记应为 5m
        for role, ttl in markers:
            assert ttl == "5m", f"{role} 应该是 5m 但得到 {ttl}"

    def test_static_prefix_gets_long_ttl(self):
        """静态前缀应获得长 TTL（1h），后缀获得短 TTL（5m）"""
        static_prefix = "You are a helpful assistant. "
        full_system = static_prefix + "Today's date is 2026-09-20."
        msgs = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = apply_anthropic_cache_control(
            msgs,
            cache_ttl="5m",
            static_system_prefix=static_prefix,
            static_system_ttl="1h",
        )
        # 系统消息被拆成两个 block：static_prefix (1h) + suffix (5m)
        system_msg = result[0]
        assert isinstance(system_msg["content"], list)
        assert len(system_msg["content"]) == 2
        # 静态前缀块：1h
        assert system_msg["content"][0]["text"] == static_prefix
        assert system_msg["content"][0]["cache_control"]["ttl"] == "1h"
        # 易变后缀块：5m
        assert system_msg["content"][1]["text"] == "Today's date is 2026-09-20."
        assert system_msg["content"][1]["cache_control"].get("ttl", "5m") == "5m"

    def test_no_static_prefix_ignores_static_ttl(self):
        """没有 static_system_prefix 时，static_system_ttl 不影响任何事"""
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        result = apply_anthropic_cache_control(
            msgs,
            cache_ttl="5m",
            static_system_ttl="1h",  # 无 prefix，此参数无效
        )
        markers = _extract_markers(result)
        # 所有标记应为 5m（因为没有可拆分的静态前缀）
        for role, ttl in markers:
            assert ttl == "5m", f"{role} 应该是 5m 但得到 {ttl}"

    def test_default_5m_when_no_ttl_specified(self):
        """默认参数下 marker 没有 ttl 字段（Anthropic 默认 5m）"""
        msgs = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
        ]
        result = apply_anthropic_cache_control(msgs)
        system_msg = result[0]
        # 字符串 content 被转为 list with cache_control
        if isinstance(system_msg["content"], list):
            for part in system_msg["content"]:
                if "cache_control" in part:
                    # 5m 默认不写 ttl 字段
                    assert "ttl" not in part["cache_control"]

    def test_recent_messages_get_short_ttl(self):
        """最近消息总是获得 cache_ttl（短 TTL），不受 static_system_ttl 影响"""
        msgs = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "msg 1"},
            {"role": "assistant", "content": "reply 1"},
            {"role": "user", "content": "msg 2"},
            {"role": "assistant", "content": "reply 2"},
        ]
        result = apply_anthropic_cache_control(
            msgs, cache_ttl="5m", static_system_ttl="1h"
        )
        # 最近 3 条非系统消息（因为没有 static prefix split）应该有 marker
        # 它们都应该是 5m
        non_system_markers = [
            (msg.get("role"), _get_ttl(msg))
            for msg in result[1:]
            if _has_marker(msg)
        ]
        for role, ttl in non_system_markers:
            assert ttl == "5m", f"recent {role} 应该是 5m 但得到 {ttl}"


def _has_marker(msg):
    content = msg.get("content")
    if isinstance(content, list):
        return any("cache_control" in p for p in content if isinstance(p, dict))
    return "cache_control" in msg


def _get_ttl(msg):
    content = msg.get("content")
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and "cache_control" in p:
                return p["cache_control"].get("ttl", "5m")
    if "cache_control" in msg:
        return msg["cache_control"].get("ttl", "5m")
    return None
