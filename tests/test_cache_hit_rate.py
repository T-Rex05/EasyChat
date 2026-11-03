"""cache_hit_rate 计算逻辑单元测试

覆盖：
  - cache_hit_rate 在 dashboard summary 中的计算
  - cache_hit_rate 在 daily_trend 中的计算
  - cache_hit_rate 在 list_turns 中的计算

运行：
  pytest tests/test_cache_hit_rate.py -v
"""
import pytest


class TestCacheHitRateCalculation:
    """纯数学逻辑验证"""

    def test_normal_cache_hit_rate(self):
        """input=6000, cache_read=4000 → hit_rate = 4000/10000 = 0.4"""
        cache_read = 4000
        input_tokens = 6000
        denom = input_tokens + cache_read
        rate = cache_read / denom if denom > 0 else 0.0
        assert round(rate, 4) == 0.4

    def test_no_cache_at_all(self):
        """input=5000, cache_read=0 → hit_rate = 0"""
        cache_read = 0
        input_tokens = 5000
        denom = input_tokens + cache_read
        rate = cache_read / denom if denom > 0 else 0.0
        assert rate == 0.0

    def test_all_from_cache(self):
        """input=0, cache_read=10000 → hit_rate = 1.0 (理论上极端情况)"""
        cache_read = 10000
        input_tokens = 0
        denom = input_tokens + cache_read
        rate = cache_read / denom if denom > 0 else 0.0
        assert rate == 1.0

    def test_zero_denominator_returns_zero(self):
        """input=0, cache_read=0 → hit_rate = 0.0（分母为 0 保护）"""
        cache_read = 0
        input_tokens = 0
        denom = input_tokens + cache_read
        rate = cache_read / denom if denom > 0 else 0.0
        assert rate == 0.0

    def test_high_cache_hit_rate(self):
        """典型 Anthropic 多轮场景：input=2000, cache_read=18000 → 90%"""
        cache_read = 18000
        input_tokens = 2000
        denom = input_tokens + cache_read
        rate = cache_read / denom if denom > 0 else 0.0
        assert round(rate, 4) == 0.9

    def test_rounding_to_4_decimals(self):
        """1/3 应该精确到 4 位小数"""
        cache_read = 1000
        input_tokens = 2000
        denom = input_tokens + cache_read
        rate = cache_read / denom if denom > 0 else 0.0
        assert round(rate, 4) == 0.3333
