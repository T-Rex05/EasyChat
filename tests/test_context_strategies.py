"""上下文压缩策略 单元测试

覆盖：
  - backend.context.config: 配置读取 + 合法性校验 + 默认值回退
  - backend.context.factory: 策略注册 + 未知策略回退 + 各策略实例化
  - backend.context.strategies.fact_anchor:
      * 代理机制（__getattr__ 透传给 inner）
      * JSON 解析多种回退
      * 事实格式化
      * 短对话短路（< 4 条消息不提取）
      * 正常提取 + 注入流程（mock LLM）
      * LLM 失败降级（mock LLM 抛异常）
      * FACT_ANCHOR_ENABLED=false 时透传

运行：
  pytest tests/test_context_strategies.py -v
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from backend.context.config import (
    DEFAULT_STRATEGY,
    VALID_STRATEGIES,
    get_context_strategy,
    get_fact_anchor_enabled,
    get_fact_anchor_max_facts,
)
from backend.context.factory import STRATEGIES, create_engine
from backend.context.strategies.fact_anchor import FactAnchorCompressor


# ═══════════════════════════════════════════════════════════
# config 模块
# ═══════════════════════════════════════════════════════════

class TestContextConfig:
    def test_valid_strategies_contains_expected(self):
        assert "default" in VALID_STRATEGIES
        assert "fact_anchor" in VALID_STRATEGIES
        assert "none" in VALID_STRATEGIES

    def test_default_strategy_is_default(self):
        assert DEFAULT_STRATEGY == "default"

    def test_get_context_strategy_default_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTEXT_STRATEGY", None)
            assert get_context_strategy() == "default"

    @pytest.mark.parametrize("value", ["default", "fact_anchor", "none", "FACT_ANCHOR", "Default"])
    def test_get_context_strategy_accepts_valid(self, value):
        with patch.dict(os.environ, {"CONTEXT_STRATEGY": value}, clear=False):
            result = get_context_strategy()
            assert result == value.lower()

    def test_get_context_strategy_rejects_invalid(self):
        with patch.dict(os.environ, {"CONTEXT_STRATEGY": "bogus"}, clear=False):
            assert get_context_strategy() == "default"

    def test_fact_anchor_max_facts_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FACT_ANCHOR_MAX_FACTS", None)
            assert get_fact_anchor_max_facts() == 20

    def test_fact_anchor_max_facts_custom(self):
        with patch.dict(os.environ, {"FACT_ANCHOR_MAX_FACTS": "10"}, clear=False):
            assert get_fact_anchor_max_facts() == 10

    def test_fact_anchor_max_facts_invalid_falls_back(self):
        with patch.dict(os.environ, {"FACT_ANCHOR_MAX_FACTS": "not-a-number"}, clear=False):
            assert get_fact_anchor_max_facts() == 20

    def test_fact_anchor_max_facts_zero_bumped_to_one(self):
        with patch.dict(os.environ, {"FACT_ANCHOR_MAX_FACTS": "0"}, clear=False):
            assert get_fact_anchor_max_facts() >= 1

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
            ("false", False), ("0", False), ("no", False),
            # 空字符串等价于未配置 → 默认开启
            ("", True),
        ],
    )
    def test_fact_anchor_enabled_parsing(self, value, expected):
        with patch.dict(os.environ, {"FACT_ANCHOR_ENABLED": value}, clear=False):
            assert get_fact_anchor_enabled() is expected


# ═══════════════════════════════════════════════════════════
# factory 模块
# ═══════════════════════════════════════════════════════════

class TestContextFactory:
    def test_strategies_registered(self):
        assert "default" in STRATEGIES
        assert "fact_anchor" in STRATEGIES

    def test_default_returns_none(self):
        # default 策略透传 Hermes 默认实例，build() 返回 None
        assert create_engine("default", engine_kwargs={}) is None

    def test_none_returns_none(self):
        assert create_engine("none", engine_kwargs={}) is None

    def test_unknown_falls_back_to_default(self):
        # 未知策略回退为 default（返回 None）
        assert create_engine("does-not-exist", engine_kwargs={}) is None

    def test_fact_anchor_builds_instance(self):
        inner = MagicMock()
        engine = create_engine("fact_anchor", engine_kwargs={"inner": inner})
        assert isinstance(engine, FactAnchorCompressor)

    def test_fact_anchor_proxy_forwards_to_inner(self):
        inner = MagicMock()
        inner.some_custom_attr = "hello"
        inner.should_compress.return_value = True
        engine = create_engine("fact_anchor", engine_kwargs={"inner": inner})
        # 属性透传
        assert engine.some_custom_attr == "hello"
        # 方法调用透传
        assert engine.should_compress() is True
        inner.should_compress.assert_called_once()


# ═══════════════════════════════════════════════════════════
# fact_anchor 内部辅助方法
# ═══════════════════════════════════════════════════════════

class TestFactAnchorHelpers:
    def test_parse_json_direct(self):
        result = FactAnchorCompressor._parse_json('{"facts": [], "next_action": ""}')
        assert result == {"facts": [], "next_action": ""}

    def test_parse_json_with_code_fence(self):
        content = '```json\n{"facts": [{"category": "id", "content": "订单号 123"}], "next_action": "下一步"}\n```'
        result = FactAnchorCompressor._parse_json(content)
        assert result is not None
        assert result["facts"][0]["content"] == "订单号 123"

    def test_parse_json_with_embedded_block(self):
        content = '这里是一些解释\n{"facts": [], "next_action": ""}\n后续文字'
        result = FactAnchorCompressor._parse_json(content)
        assert result == {"facts": [], "next_action": ""}

    def test_parse_json_invalid_returns_none(self):
        assert FactAnchorCompressor._parse_json("not json at all") is None
        assert FactAnchorCompressor._parse_json("") is None
        assert FactAnchorCompressor._parse_json("{invalid") is None

    def test_format_facts(self):
        facts = [
            {"category": "id", "content": "订单号 123"},
            {"category": "decision", "content": "选择方案 A"},
            {"category": "", "content": "无分类的事实"},
        ]
        text = FactAnchorCompressor._format_facts(facts)
        assert "1. [id] 订单号 123" in text
        assert "2. [decision] 选择方案 A" in text
        assert "3. 无分类的事实" in text

    def test_format_facts_skips_empty_content(self):
        facts = [
            {"category": "id", "content": ""},  # 空 content 跳过
            {"category": "id", "content": "有效内容"},
        ]
        text = FactAnchorCompressor._format_facts(facts)
        assert "有效内容" in text
        # 空 content 的那条不应该出现（行号 1 应该是有效内容那条）
        assert text.startswith("1.")


# ═══════════════════════════════════════════════════════════
# fact_anchor compress 流程（mock LLM）
# ═══════════════════════════════════════════════════════════

def _build_fake_messages(n: int) -> list:
    """构造 n 条假对话消息"""
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"第 {i} 条消息内容" * 5})
    return msgs


class _FakeInnerCompressor:
    """模拟 Hermes ContextCompressor 的关键行为。

    compress() 返回原消息列表（模拟"压缩"后的结果）；
    其他属性/方法通过 __getattr__ 测试代理。
    """

    def __init__(self):
        self.compress_called_with = None
        self.some_attr = "inner-value"

    def compress(self, messages, current_tokens=None, focus_topic=None,
                 force=False, memory_context=""):
        self.compress_called_with = {
            "messages": messages,
            "memory_context": memory_context,
        }
        # 返回原消息的拷贝（模拟压缩后列表）
        return list(messages)

    def should_compress(self, prompt_tokens=None):
        return True


class TestFactAnchorCompress:
    def test_short_conversation_no_extraction(self):
        """消息少于 4 条时，跳过事实提取，直接调 inner.compress()"""
        inner = _FakeInnerCompressor()
        engine = FactAnchorCompressor(inner=inner)
        msgs = _build_fake_messages(2)
        result = engine.compress(msgs)
        # 没有事实 → 没有注入 <fact_anchor> 系统消息
        assert result == msgs
        # memory_context 应为空（没事实可注入）
        assert inner.compress_called_with["memory_context"] == ""

    def test_enabled_false_skips_extraction(self):
        """FACT_ANCHOR_ENABLED=false 时直接透传给 inner，不提取事实"""
        inner = _FakeInnerCompressor()
        engine = FactAnchorCompressor(inner=inner)
        msgs = _build_fake_messages(6)
        with patch("backend.context.strategies.fact_anchor.get_fact_anchor_enabled", return_value=False):
            result = engine.compress(msgs)
        assert result == msgs
        assert inner.compress_called_with["memory_context"] == ""

    def test_extract_and_inject(self):
        """正常路径：LLM 返回 JSON，事实被注入到压缩后列表"""
        inner = _FakeInnerCompressor()
        engine = FactAnchorCompressor(inner=inner)
        msgs = _build_fake_messages(10)

        fake_facts = {
            "facts": [
                {"category": "id", "content": "订单号 A123"},
                {"category": "decision", "content": "采用方案 B"},
            ],
            "next_action": "继续执行步骤 3",
        }

        # mock 事实提取方法，绕过真实 LLM 调用
        with patch.object(engine, "_extract_facts", return_value=fake_facts):
            result = engine.compress(msgs)

        # 1. inner.compress 被调用且 memory_context 包含事实
        mc = inner.compress_called_with["memory_context"]
        assert "<fact_anchor>" in mc
        assert "订单号 A123" in mc
        assert "采用方案 B" in mc

        # 2. 压缩后列表【末尾】追加了一条 role="user" 的 <fact_anchor> 消息
        #    （设计如此：动态内容放尾部，避免破坏前缀 KV Cache；
        #      旧实现插在 idx=1 的 system 位置，已废弃 —— 见 fact_anchor.py:195-218）
        anchor_msgs = [m for m in result if "<fact_anchor>" in (m.get("content") or "")]
        assert len(anchor_msgs) == 1
        assert result[-1] is anchor_msgs[0], "anchor 必须追加在列表末尾"
        assert anchor_msgs[0]["role"] == "user"
        assert "订单号 A123" in anchor_msgs[0]["content"]
        assert "继续执行步骤 3" in anchor_msgs[0]["content"]
        # 原始消息未被就地改写
        assert result[:-1] == msgs

    def test_extract_failure_degrades_gracefully(self):
        """事实提取失败 → 降级为普通压缩，不抛异常，不注入 anchor"""
        inner = _FakeInnerCompressor()
        engine = FactAnchorCompressor(inner=inner)
        msgs = _build_fake_messages(10)

        # mock _extract_facts 返回 None（模拟 LLM 失败）
        with patch.object(engine, "_extract_facts", return_value=None):
            result = engine.compress(msgs)

        # 不抛异常、返回的消息列表 == 原始消息（inner 的"压缩"结果）
        assert result == msgs
        # memory_context 为空（没有事实可注入）
        assert inner.compress_called_with["memory_context"] == ""

    def test_extract_returns_garbage_degrades(self):
        """LLM 返回非 dict 数据 → 降级处理，不崩溃"""
        inner = _FakeInnerCompressor()
        engine = FactAnchorCompressor(inner=inner)
        msgs = _build_fake_messages(10)

        for garbage in ["not a dict", 42, [1, 2, 3], {"facts": "not a list"}]:
            with patch.object(engine, "_extract_facts", return_value=garbage):
                result = engine.compress(msgs)
            # 不抛异常即可
            assert isinstance(result, list)

    def test_proxy_passthrough(self):
        """未重写的方法/属性通过 __getattr__ 透传给 inner"""
        inner = _FakeInnerCompressor()
        engine = FactAnchorCompressor(inner=inner)
        assert engine.some_attr == "inner-value"
        assert engine.should_compress() is True

    def test_existing_memory_context_preserved(self):
        """如果调用方传入了 memory_context，和 fact_anchor 块拼接而不是覆盖"""
        inner = _FakeInnerCompressor()
        engine = FactAnchorCompressor(inner=inner)
        msgs = _build_fake_messages(10)

        fake_facts = {"facts": [{"category": "id", "content": "X"}], "next_action": "Y"}
        with patch.object(engine, "_extract_facts", return_value=fake_facts):
            engine.compress(msgs, memory_context="已有的上游记忆上下文")

        mc = inner.compress_called_with["memory_context"]
        assert "已有的上游记忆上下文" in mc
        assert "<fact_anchor>" in mc
