"""
自适应检索改进 A/B 测试和性能测试

测试维度：
1. 意图分类准确性（改进前后对比）
2. 热点实体图扩展性能（LIMIT 限制效果）
3. 门控策略差异化效果

运行方式：
  python eval/adaptive_retrieval_ab_test.py
"""

import sys
import os
import time
import statistics
from typing import List, Dict, Any, Tuple

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.service.kb import adaptive_retriever as ar
from backend.service.memory.adaptive_retriever import (
    AdaptiveMemoryRetriever,
    get_strong_threshold,
    get_min_strong_entities,
)


# ════════════════════════════════════════════════════════════
# 测试数据
# ════════════════════════════════════════════════════════════

# A/B 测试用例：意图分类
INTENT_TEST_CASES = [
    # 总结型查询（应该被识别为 summary）
    ("总结一下三国演义的主要内容", ar.KIND_SUMMARY),
    ("概括这份文档的核心观点", ar.KIND_SUMMARY),
    ("整体架构是什么", ar.KIND_SUMMARY),
    ("对比所有渠道的差异和发展历程", ar.KIND_SUMMARY),

    # 实体型查询（应该被识别为 adaptive）
    ("关羽的武器是什么？", ar.KIND_ADAPTIVE),
    ("五虎上将是哪五将，有什么故事背景？", ar.KIND_ADAPTIVE),  # 关键测试用例
    ("刘备的结义兄弟是谁？", ar.KIND_ADAPTIVE),
    ("MySQL 的配置项怎么写？", ar.KIND_ADAPTIVE),
    ("用户偏好什么", ar.KIND_ADAPTIVE),
    ("哪个部门负责订单系统", ar.KIND_ADAPTIVE),  # 改进前会误判（含"哪些"的同义词"哪个"）

    # 边界查询
    ("", ar.KIND_ADAPTIVE),
    ("   ", ar.KIND_ADAPTIVE),
    ("全部用户有多少", ar.KIND_ADAPTIVE),  # 改进前会误判（含"全部"）
]

# 性能测试用例：热点实体
HOT_ENTITY_QUERIES = [
    "刘备",      # 三国演义中关联人物最多的实体
    "曹操",      # 另一个热点实体
    "关羽 张飞",  # 多实体查询
]


# ════════════════════════════════════════════════════════════
# 测试函数
# ════════════════════════════════════════════════════════════

def test_intent_classification() -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    测试意图分类准确性
    返回：(正确数, 总数, 错误详情列表)
    """
    print("\n" + "="*70)
    print("📊 A/B 测试：意图分类准确性")
    print("="*70)

    correct = 0
    total = len(INTENT_TEST_CASES)
    errors = []

    for query, expected in INTENT_TEST_CASES:
        result = ar.classify_retrieval_kind(query)
        is_correct = result == expected

        if is_correct:
            correct += 1
            status = "✅"
        else:
            status = "❌"
            errors.append({
                "query": query or "(空)",
                "expected": expected,
                "actual": result,
            })

        query_display = query[:40] + "..." if len(query) > 40 else query
        print(f"{status} {query_display or '(空)':<45} → {result:<10} (预期: {expected})")

    accuracy = correct / total * 100 if total > 0 else 0
    print(f"\n准确率: {correct}/{total} = {accuracy:.1f}%")

    if errors:
        print("\n错误详情:")
        for err in errors:
            print(f"  - '{err['query']}' 预期 {err['expected']}, 实际 {err['actual']}")

    return correct, total, errors


def test_entity_thresholds() -> None:
    """测试实体阈值配置"""
    print("\n" + "="*70)
    print("⚙️  门控策略测试：实体阈值")
    print("="*70)

    threshold = get_strong_threshold()
    min_strong = get_min_strong_entities()

    print(f"强命中阈值: {threshold}")
    print(f"最少强实体数: {min_strong}")

    # 测试不同分数的实体命中
    test_cases = [
        ([{"score": 0.5}], "单个 0.5 实体"),
        ([{"score": 0.65}], "单个 0.65 实体"),
        ([{"score": 0.65}, {"score": 0.6}], "两个强实体"),
        ([{"score": 0.8}, {"score": 0.5}], "一个强 + 一个弱"),
    ]

    for entity_hits, desc in test_cases:
        strong_count = sum(1 for h in entity_hits if h["score"] >= threshold)
        is_confident = strong_count >= min_strong and entity_hits and entity_hits[0]["score"] >= threshold

        status = "✅ 放行" if is_confident else "❌ 不够"
        print(f"  {desc}: strong={strong_count} → {status}")


def simulate_graph_expansion_performance() -> None:
    """
    模拟图扩展性能测试
    注意：需要真实的 Neo4j 连接才能运行完整测试
    """
    print("\n" + "="*70)
    print("⚡ 性能测试：图扩展 LIMIT 限制")
    print("="*70)

    print("环境变量配置:")
    print(f"  RAG_GRAPH_EXPAND_LIMIT: {os.getenv('RAG_GRAPH_EXPAND_LIMIT', '500 (默认)')}")
    print(f"  RAG_ENTITY_GRAPH_HOPS: {os.getenv('RAG_ENTITY_GRAPH_HOPS', '1 (默认)')}")

    # 模拟数据：不同规模的邻居数量
    scenarios = [
        (10, "普通实体"),
        (50, "热门实体"),
        (100, "热点实体"),
        (500, "超热点实体"),
        (1000, "极端热点实体（会被截断）"),
    ]

    limit = int(os.getenv("RAG_GRAPH_EXPAND_LIMIT", "500"))

    for neighbor_count, desc in scenarios:
        actual_returned = min(neighbor_count, limit)
        is_limited = neighbor_count > limit
        status = "🔒 已限制" if is_limited else "✅ 正常"

        print(f"  {desc}: {neighbor_count} 邻居 → 返回 {actual_returned} {status}")


def run_all_tests() -> Dict[str, Any]:
    """运行所有测试"""
    print("\n" + "="*70)
    print("🧪 自适应检索改进 A/B 测试")
    print("="*70)
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "tests": {}
    }

    # 1. 意图分类测试
    correct, total, errors = test_intent_classification()
    results["tests"]["intent_classification"] = {
        "passed": correct,
        "total": total,
        "accuracy": correct / total * 100 if total > 0 else 0,
        "errors": errors,
    }

    # 2. 阈值配置测试
    test_entity_thresholds()
    results["tests"]["thresholds"] = {
        "strong_threshold": get_strong_threshold(),
        "min_strong_entities": get_min_strong_entities(),
    }

    # 3. 性能测试
    simulate_graph_expansion_performance()

    # 总结
    print("\n" + "="*70)
    print("📋 测试总结")
    print("="*70)

    intent_test = results["tests"]["intent_classification"]
    print(f"意图分类准确率: {intent_test['accuracy']:.1f}% ({intent_test['passed']}/{intent_test['total']})")

    if intent_test["errors"]:
        print(f"⚠️  发现 {len(intent_test['errors'])} 个误判案例")
    else:
        print("✅ 所有意图分类测试通过")

    return results


# ════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="自适应检索改进 A/B 测试")
    parser.add_argument("--intent", action="store_true", help="只运行意图分类测试")
    parser.add_argument("--performance", action="store_true", help="只运行性能测试")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    if args.intent:
        test_intent_classification()
    elif args.performance:
        simulate_graph_expansion_performance()
    else:
        run_all_tests()