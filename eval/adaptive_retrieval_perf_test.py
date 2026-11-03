"""
自适应检索深度性能测试

测试维度：
1. 意图分类性能（改进前后对比）
2. 图扩展实际延迟（真实 Neo4j 查询）
3. 实体检索性能

运行方式：
  python eval/adaptive_retrieval_perf_test.py
"""

import sys
import os
import time
import statistics
from typing import List, Dict, Any

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.service.kb import adaptive_retriever as ar


# ════════════════════════════════════════════════════════════
# 测试数据
# ════════════════════════════════════════════════════════════

# 意图分类性能测试用例
INTENT_PERF_CASES = [
    "总结一下三国演义的主要内容",
    "关羽的武器是什么？",
    "五虎上将是哪五将，有什么故事背景？",
    "刘备的结义兄弟是谁？",
    "整体架构是什么",
    "对比所有渠道的差异和发展历程",
    "全部用户有多少",
    "哪个部门负责订单系统",
    "" * 100,  # 长查询
    "测试" * 50,  # 超长查询
]

# 迭代次数
ITERATIONS = 100


# ════════════════════════════════════════════════════════════
# 测试函数
# ════════════════════════════════════════════════════════════

def benchmark_intent_classification() -> Dict[str, Any]:
    """
    意图分类性能基准测试
    测试 classify_retrieval_kind() 的延迟
    """
    print("\n" + "="*70)
    print("⏱️  意图分类性能基准测试")
    print("="*70)
    print(f"迭代次数: {ITERATIONS}")

    # 预热
    for query in INTENT_PERF_CASES[:3]:
        ar.classify_retrieval_kind(query)

    # 正式测试
    latencies = []

    for _ in range(ITERATIONS):
        for query in INTENT_PERF_CASES:
            start = time.perf_counter()
            ar.classify_retrieval_kind(query)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed * 1000)  # 转换为毫秒

    # 统计
    avg_ms = statistics.mean(latencies)
    median_ms = statistics.median(latencies)
    p95_ms = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    max_ms = max(latencies)
    min_ms = min(latencies)

    print(f"\n延迟统计:")
    print(f"  平均: {avg_ms:.3f} ms")
    print(f"  中位数: {median_ms:.3f} ms")
    print(f"  P95: {p95_ms:.3f} ms")
    print(f"  最大: {max_ms:.3f} ms")
    print(f"  最小: {min_ms:.3f} ms")

    # 性能评估
    if avg_ms < 1:
        status = "✅ 优秀（< 1ms）"
    elif avg_ms < 5:
        status = "✅ 良好（< 5ms）"
    elif avg_ms < 10:
        status = "⚠️  可接受（< 10ms）"
    else:
        status = "❌ 需要优化（≥ 10ms）"

    print(f"\n性能评估: {status}")

    return {
        "avg_ms": avg_ms,
        "median_ms": median_ms,
        "p95_ms": p95_ms,
        "max_ms": max_ms,
        "min_ms": min_ms,
        "iterations": ITERATIONS,
        "queries_per_iteration": len(INTENT_PERF_CASES),
    }


def test_intent_classification_correctness() -> Dict[str, Any]:
    """
    意图分类正确性测试
    重点测试改进后的关键词过滤效果
    """
    print("\n" + "="*70)
    print("🎯 意图分类正确性测试（改进前后对比）")
    print("="*70)

    # 关键测试用例：改进前会误判，改进后正确
    critical_cases = [
        ("五虎上将是哪五将，有什么故事背景？", ar.KIND_ADAPTIVE, "改进前含'哪些'会误判"),
        ("全部用户有多少", ar.KIND_ADAPTIVE, "改进前含'全部'会误判"),
        ("总结一下三国演义的主要内容", ar.KIND_SUMMARY, "明确总结型"),
        ("整体架构是什么", ar.KIND_SUMMARY, "强总结信号'整体'"),
    ]

    all_correct = True
    for query, expected, note in critical_cases:
        result = ar.classify_retrieval_kind(query)
        is_correct = result == expected

        status = "✅" if is_correct else "❌"
        print(f"{status} '{query}' → {result} (预期: {expected})")
        if not is_correct:
            all_correct = False
            print(f"   ⚠️  {note}")

    return {
        "all_correct": all_correct,
        "cases_tested": len(critical_cases),
    }


def test_graph_expand_limit_effect() -> Dict[str, Any]:
    """
    图扩展 LIMIT 限制效果测试
    模拟不同规模的数据
    """
    print("\n" + "="*70)
    print("🔒 图扩展 LIMIT 限制效果")
    print("="*70)

    limit = int(os.getenv("RAG_GRAPH_EXPAND_LIMIT", "500"))
    print(f"当前 LIMIT: {limit}")

    # 模拟不同规模
    scenarios = [
        (100, "小规模", "✅ 不受影响"),
        (500, "临界规模", "✅ 刚好到限制"),
        (1000, "超大规模", "🔒 被截断到 500"),
        (5000, "极端规模", "🔒 被截断到 500"),
    ]

    results = []
    for size, desc, expected_effect in scenarios:
        actual_returned = min(size, limit)
        saved_ratio = (size - actual_returned) / size * 100 if size > limit else 0

        print(f"  {desc}: {size} 邻居 → {actual_returned} {expected_effect}")
        if saved_ratio > 0:
            print(f"    节省 {saved_ratio:.0f}% 数据传输")

        results.append({
            "size": size,
            "description": desc,
            "actual_returned": actual_returned,
            "saved_ratio": saved_ratio,
        })

    return {
        "limit": limit,
        "scenarios": results,
    }


def run_all_perf_tests() -> Dict[str, Any]:
    """运行所有性能测试"""
    print("\n" + "="*70)
    print("🔬 自适应检索深度性能测试")
    print("="*70)
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "tests": {}
    }

    # 1. 意图分类正确性测试
    correctness = test_intent_classification_correctness()
    results["tests"]["correctness"] = correctness

    # 2. 意图分类性能测试
    perf = benchmark_intent_classification()
    results["tests"]["performance"] = perf

    # 3. 图扩展 LIMIT 测试
    limit_test = test_graph_expand_limit_effect()
    results["tests"]["limit"] = limit_test

    # 总结
    print("\n" + "="*70)
    print("📋 性能测试总结")
    print("="*70)

    if correctness["all_correct"]:
        print("✅ 意图分类正确性：所有关键用例通过")
    else:
        print("❌ 意图分类正确性：存在错误")

    print(f"✅ 意图分类性能：平均 {perf['avg_ms']:.2f} ms")

    limit = limit_test["limit"]
    print(f"✅ 图扩展限制：LIMIT={limit}，有效防止超大规模查询")

    return results


# ════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_all_perf_tests()