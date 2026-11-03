"""Provider Cache Policy 注册表单元测试

覆盖：
  - 各规则匹配正确性
  - 新增 Provider 只需添加规则即可生效
  - 默认 fallback 为 (False, False)

运行：
  pytest tests/test_cache_policy_registry.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "hermes"))

from types import SimpleNamespace
from agent.agent_runtime_helpers import (
    anthropic_prompt_cache_policy,
    _CACHE_POLICY_RULES,
    _CachePolicyContext,
)


def _make_agent(provider="", base_url="", api_mode="", model=""):
    return SimpleNamespace(
        provider=provider, base_url=base_url,
        api_mode=api_mode, model=model,
    )


class TestCachePolicyRules:
    def test_registry_not_empty(self):
        """注册表至少有一条规则"""
        assert len(_CACHE_POLICY_RULES) >= 5

    def test_all_rules_have_required_keys(self):
        """每条规则必须有 name/match/should_cache/native_layout"""
        for rule in _CACHE_POLICY_RULES:
            assert "name" in rule
            assert "match" in rule
            assert "should_cache" in rule
            assert "native_layout" in rule

    def test_rule_names_unique(self):
        """规则名不能重复"""
        names = [r["name"] for r in _CACHE_POLICY_RULES]
        assert len(names) == len(set(names)), f"重复规则名: {names}"


class TestNativeAnthropic:
    def test_direct_anthropic(self):
        """原生 Anthropic → (True, True)"""
        agent = _make_agent(provider="anthropic", api_mode="anthropic_messages", model="claude-sonnet-4-20250514")
        result = anthropic_prompt_cache_policy(agent)
        assert result == (True, True)

    def test_api_anthropic_com_host(self):
        """api.anthropic.com 主机名 → (True, True)"""
        agent = _make_agent(
            provider="custom", base_url="https://api.anthropic.com/v1",
            api_mode="anthropic_messages", model="claude-opus-4-20250514",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (True, True)


class TestOpenRouter:
    def test_openrouter_claude(self):
        """OpenRouter Claude → (True, False) — envelope layout"""
        agent = _make_agent(
            provider="openrouter", base_url="https://openrouter.ai/api/v1",
            api_mode="chat_completions", model="anthropic/claude-sonnet-4-20250514",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (True, False)

    def test_openrouter_kimi(self):
        """OpenRouter Kimi → (True, False)"""
        agent = _make_agent(
            provider="openrouter", base_url="https://openrouter.ai/api/v1",
            api_mode="chat_completions", model="moonshotai/kimi-k2.6",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (True, False)

    def test_openrouter_gpt_no_cache(self):
        """OpenRouter GPT → (False, False) — 非 Claude/Kimi 无缓存"""
        agent = _make_agent(
            provider="openrouter", base_url="https://openrouter.ai/api/v1",
            api_mode="chat_completions", model="openai/gpt-4o",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (False, False)


class TestQwen:
    def test_opencode_qwen(self):
        """OpenCode Qwen → (True, False) — envelope layout"""
        agent = _make_agent(
            provider="opencode", base_url="https://opencode.example.com",
            api_mode="chat_completions", model="qwen3.6-plus",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (True, False)

    def test_alibaba_qwen(self):
        """Alibaba provider + Qwen → (True, False)"""
        agent = _make_agent(
            provider="alibaba", base_url="https://dashscope.aliyuncs.com",
            api_mode="chat_completions", model="qwen-plus",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (True, False)

    def test_opencode_non_qwen(self):
        """OpenCode 非 Qwen → (False, False)"""
        agent = _make_agent(
            provider="opencode", base_url="https://opencode.example.com",
            api_mode="chat_completions", model="llama-3",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (False, False)


class TestMiniMax:
    def test_minimax_anthropic_wire(self):
        """MiniMax anthropic_messages → (True, True)"""
        agent = _make_agent(
            provider="minimax", base_url="https://api.minimax.io/anthropic",
            api_mode="anthropic_messages", model="MiniMax-M2.7",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (True, True)


class TestFallback:
    def test_unknown_provider_returns_false(self):
        """未知 provider → (False, False)"""
        agent = _make_agent(
            provider="unknown", base_url="https://example.com",
            api_mode="chat_completions", model="some-model",
        )
        result = anthropic_prompt_cache_policy(agent)
        assert result == (False, False)
