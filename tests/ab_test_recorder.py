"""
A/B 测试数据收集脚本

用于记录每次测试的全面指标数据
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


class ABTestRecorder:
    """A/B 测试数据记录器"""

    def __init__(self, group: str, output_dir: str = "tests/results"):
        """
        初始化记录器

        Args:
            group: 测试组别 ("A" 或 "B")
            output_dir: 输出目录
        """
        self.group = group
        self.output_dir = output_dir
        self.results_file = os.path.join(output_dir, f"test_results_{group.lower()}.json")
        self.results: List[Dict] = []

        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

    def record_test(
        self,
        test_id: str,
        run: int,
        question: str,
        # 效率指标
        tool_calls_total: int,
        tools_breakdown: Dict[str, int],
        batch_operations: Dict[str, int],
        duration_total_ms: int,
        duration_per_tool_avg_ms: float,
        duration_per_tool_min_ms: int,
        duration_per_tool_max_ms: int,
        # Token 指标
        input_tokens: int,
        output_tokens: int,
        tokens_breakdown: Optional[Dict[str, int]] = None,
        cost_usd: Optional[float] = None,
        # 错误指标
        errors_total: int = 0,
        error_details: Optional[List[Dict]] = None,
        auto_fix_attempts: int = 0,
        auto_fix_successes: int = 0,
        # 质量指标（人工评估）
        answer_quality: Optional[Dict[str, int]] = None,
        code_quality: Optional[Dict[str, int]] = None,
        # 行为指标
        behavior: Optional[Dict] = None,
        # 其他指标
        memory_usage: Optional[Dict] = None,
        knowledge_base_usage: Optional[Dict] = None,
        # 备注
        notes: str = ""
    ):
        """
        记录一次测试结果

        Args:
            test_id: 测试用例 ID (如 "T1.1")
            run: 第几次运行 (1, 2, 3)
            question: 测试问题

            # 效率指标
            tool_calls_total: 工具调用总次数
            tools_breakdown: 各工具使用次数 {"run_python": 4, "terminal": 0, ...}
            batch_operations: 批量操作统计 {"batch_search_count": 2, "batch_read_count": 1, ...}
            duration_total_ms: 总响应延迟（毫秒）
            duration_per_tool_avg_ms: 平均每次工具调用延迟
            duration_per_tool_min_ms: 最小单次调用延迟
            duration_per_tool_max_ms: 最大单次调用延迟

            # Token 指标
            input_tokens: 输入 Token 数
            output_tokens: 输出 Token 数
            tokens_breakdown: Token 细分 {"system_prompt_tokens": 3000, ...}
            cost_usd: 成本（美元）

            # 错误指标
            errors_total: 错误总次数
            error_details: 错误详情列表
            auto_fix_attempts: 自动修复尝试次数
            auto_fix_successes: 自动修复成功次数

            # 质量指标
            answer_quality: 回答质量评分 {"overall_score": 4, "accuracy_score": 5, ...}
            code_quality: 代码质量评分 {"overall_score": 5, "efficiency_score": 5, ...}

            # 行为指标
            behavior: 行为模式 {"two_phase_pattern_used": True, ...}

            # 其他指标
            memory_usage: 记忆使用情况 {"prefetch_count": 16, ...}
            knowledge_base_usage: 知识库使用情况 {"kb_search_count": 0, ...}

            notes: 备注
        """
        result = {
            "group": self.group,
            "test_id": test_id,
            "run": run,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "question": question,
            "metrics": {
                # 效率指标
                "efficiency": {
                    "tool_calls_total": tool_calls_total,
                    "tools_breakdown": tools_breakdown,
                    "batch_operations": batch_operations,
                    "duration_total_ms": duration_total_ms,
                    "duration_per_tool_avg_ms": round(duration_per_tool_avg_ms, 1),
                    "duration_per_tool_min_ms": duration_per_tool_min_ms,
                    "duration_per_tool_max_ms": duration_per_tool_max_ms,
                },
                # Token 指标
                "tokens": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "breakdown": tokens_breakdown or {},
                    "cost_usd": cost_usd,
                },
                # 错误指标
                "errors": {
                    "total_count": errors_total,
                    "details": error_details or [],
                    "auto_fix_attempts": auto_fix_attempts,
                    "auto_fix_successes": auto_fix_successes,
                },
                # 质量指标
                "quality": {
                    "answer_quality": answer_quality or {},
                    "code_quality": code_quality or {},
                },
                # 行为指标
                "behavior": behavior or {},
                # 其他指标
                "usage": {
                    "memory": memory_usage or {},
                    "knowledge_base": knowledge_base_usage or {},
                },
            },
            "notes": notes,
        }

        self.results.append(result)
        print(f"[PASS] 已记录: {test_id} (run {run})")

    def save(self):
        """保存结果到文件"""
        with open(self.results_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"[PASS] 结果已保存到: {self.results_file}")

    def load(self):
        """从文件加载结果"""
        if os.path.exists(self.results_file):
            with open(self.results_file, 'r', encoding='utf-8') as f:
                self.results = json.load(f)
            print(f"[PASS] 已加载 {len(self.results)} 条记录")
        else:
            print(f"[WARN] 文件不存在: {self.results_file}")

    def summary(self) -> Dict:
        """生成统计摘要"""
        if not self.results:
            return {}

        # 按测试 ID 分组
        by_test = {}
        for r in self.results:
            test_id = r["test_id"]
            if test_id not in by_test:
                by_test[test_id] = []
            by_test[test_id].append(r)

        # 计算每个测试的平均值
        summary = {
            "group": self.group,
            "total_tests": len(by_test),
            "total_runs": len(self.results),
            "tests": {},
        }

        all_tool_calls = []
        all_tokens = []
        all_durations = []
        all_errors = []
        all_answer_quality = []
        all_code_quality = []

        for test_id, runs in by_test.items():
            metrics = [r["metrics"] for r in runs]

            # 效率指标
            avg_tool_calls = sum(m["efficiency"]["tool_calls_total"] for m in metrics) / len(metrics)
            avg_duration = sum(m["efficiency"]["duration_total_ms"] for m in metrics) / len(metrics)

            # Token 指标
            avg_tokens = sum(m["tokens"]["total_tokens"] for m in metrics) / len(metrics)
            avg_cost = sum(m["tokens"].get("cost_usd") or 0 for m in metrics) / len(metrics)

            # 错误指标
            avg_errors = sum(m["errors"]["total_count"] for m in metrics) / len(metrics)

            # 质量指标
            avg_answer_quality = sum(
                m["quality"]["answer_quality"].get("overall_score", 0)
                for m in metrics
            ) / len(metrics)
            avg_code_quality = sum(
                m["quality"]["code_quality"].get("overall_score", 0)
                for m in metrics
            ) / len(metrics)

            summary["tests"][test_id] = {
                "avg_tool_calls": round(avg_tool_calls, 1),
                "avg_tokens": round(avg_tokens, 0),
                "avg_cost_usd": round(avg_cost, 4),
                "avg_duration_ms": round(avg_duration, 0),
                "avg_errors": round(avg_errors, 1),
                "avg_answer_quality": round(avg_answer_quality, 1),
                "avg_code_quality": round(avg_code_quality, 1),
                "runs": len(runs),
            }

            all_tool_calls.extend(m["efficiency"]["tool_calls_total"] for m in metrics)
            all_tokens.extend(m["tokens"]["total_tokens"] for m in metrics)
            all_durations.extend(m["efficiency"]["duration_total_ms"] for m in metrics)
            all_errors.extend(m["errors"]["total_count"] for m in metrics)
            all_answer_quality.extend(
                m["quality"]["answer_quality"].get("overall_score", 0)
                for m in metrics
            )
            all_code_quality.extend(
                m["quality"]["code_quality"].get("overall_score", 0)
                for m in metrics
            )

        # 总体统计
        summary["overall"] = {
            "avg_tool_calls": round(sum(all_tool_calls) / len(all_tool_calls), 1),
            "avg_tokens": round(sum(all_tokens) / len(all_tokens), 0),
            "avg_cost_usd": round(sum(all_tokens) * 0.000001, 4),  # 估算成本
            "avg_duration_ms": round(sum(all_durations) / len(all_durations), 0),
            "avg_errors": round(sum(all_errors) / len(all_errors), 1),
            "avg_answer_quality": round(sum(all_answer_quality) / len(all_answer_quality), 1),
            "avg_code_quality": round(sum(all_code_quality) / len(all_code_quality), 1),
            "min_tool_calls": min(all_tool_calls),
            "max_tool_calls": max(all_tool_calls),
            "min_tokens": min(all_tokens),
            "max_tokens": max(all_tokens),
        }

        return summary

    def print_summary(self):
        """打印统计摘要"""
        summary = self.summary()
        if not summary:
            print("没有数据")
            return

        print("\n" + "=" * 80)
        print(f"A/B 测试统计摘要 - {self.group} 组")
        print("=" * 80)

        overall = summary["overall"]
        print(f"\n总体统计:")
        print(f"  测试用例数: {summary['total_tests']}")
        print(f"  总运行次数: {summary['total_runs']}")
        print(f"  平均工具调用: {overall['avg_tool_calls']} 次")
        print(f"  平均 Token 消耗: {overall['avg_tokens']} tokens")
        print(f"  平均成本: ${overall['avg_cost_usd']}")
        print(f"  平均响应延迟: {overall['avg_duration_ms']} ms")
        print(f"  平均错误数: {overall['avg_errors']}")
        print(f"  平均回答质量: {overall['avg_answer_quality']} / 5")
        print(f"  平均代码质量: {overall['avg_code_quality']} / 5")
        print(f"  工具调用范围: {overall['min_tool_calls']} - {overall['max_tool_calls']} 次")

        print(f"\n各测试用例统计:")
        print(f"{'测试ID':<8} {'调用':<6} {'Token':<8} {'成本($)':<8} {'延迟(ms)':<10} {'错误':<6} {'回答':<6} {'代码':<6}")
        print("-" * 80)

        for test_id, stats in sorted(summary["tests"].items()):
            print(f"{test_id:<8} {stats['avg_tool_calls']:<6} "
                  f"{stats['avg_tokens']:<8} "
                  f"{stats['avg_cost_usd']:<8} "
                  f"{stats['avg_duration_ms']:<10} "
                  f"{stats['avg_errors']:<6} "
                  f"{stats['avg_answer_quality']:<6} "
                  f"{stats['avg_code_quality']:<6}")

        print("=" * 80)


# 测试用例定义
TEST_CASES = [
    # S1: 单文件搜索
    {"id": "T1.1", "question": "查看项目中 Milvus 相关的代码实现", "scenario": "单文件搜索"},
    {"id": "T1.2", "question": "找到 search_files 函数的实现位置", "scenario": "单文件搜索"},
    {"id": "T1.3", "question": "查看项目的数据库配置在哪里", "scenario": "单文件搜索"},

    # S2: 多文件分析
    {"id": "T2.1", "question": "对比 outbox_worker.py 和 memory_service.py 的向量处理逻辑有什么不同", "scenario": "多文件分析"},
    {"id": "T2.2", "question": "找到所有包含 run_python 的文件，并统计每个文件中出现的次数", "scenario": "多文件分析"},
    {"id": "T2.3", "question": "分析 code_executor.py 依赖了哪些模块，这些模块的作用是什么", "scenario": "多文件分析"},

    # S3: 复杂搜索
    {"id": "T3.1", "question": "搜索所有包含 FieldSchema 或 CollectionSchema 的代码行", "scenario": "复杂搜索"},
    {"id": "T3.2", "question": "在 backend/service 目录下搜索所有包含 vector 的 Python 文件", "scenario": "复杂搜索"},
    {"id": "T3.3", "question": "找到所有测试文件（test_*.py），并统计其中包含 milvus 的文件", "scenario": "复杂搜索"},

    # S4: 代码理解
    {"id": "T4.1", "question": "解释 code_executor.py 中 build_safe_globals 函数的工作原理", "scenario": "代码理解"},
    {"id": "T4.2", "question": "分析项目的权限过滤机制是如何实现的", "scenario": "代码理解"},
    {"id": "T4.3", "question": "梳理从用户发送消息到工具执行的完整流程", "scenario": "代码理解"},

    # S5: 跨文件修改
    {"id": "T5.1", "question": "如何优化 search_files 的搜索性能？分析相关文件并给出建议", "scenario": "跨文件修改"},
    {"id": "T5.2", "question": "search_files 在搜索大文件时可能会很慢，如何改进？", "scenario": "跨文件修改"},
    {"id": "T5.3", "question": "如果要给 search_files 添加搜索并替换功能，需要修改哪些地方？", "scenario": "跨文件修改"},

    # S6: 数据统计
    {"id": "T6.1", "question": "统计 backend/tools 目录下所有 Python 文件的代码行数", "scenario": "数据统计"},
    {"id": "T6.2", "question": "统计项目中使用了多少种工具调用模式（直接调用 vs run_python）", "scenario": "数据统计"},
    {"id": "T6.3", "question": "统计 knowledge_search 工具在项目代码中被调用了多少次", "scenario": "数据统计"},

    # S7: 错误排查
    {"id": "T7.1", "question": "为什么 search_files(\"milvus\", target=\"files\") 返回空结果？", "scenario": "错误排查"},
    {"id": "T7.2", "question": "查看最近的错误日志，分析有什么问题", "scenario": "错误排查"},
    {"id": "T7.3", "question": "为什么这次请求耗时 77 秒？分析可能的原因", "scenario": "错误排查"},

    # S8: 文档生成
    {"id": "T8.1", "question": "为 search_files 函数生成 API 文档", "scenario": "文档生成"},
    {"id": "T8.2", "question": "编写 Code Mode 的使用指南，包括最佳实践", "scenario": "文档生成"},
    {"id": "T8.3", "question": "绘制项目的工具调用架构图（文字描述）", "scenario": "文档生成"},
]


def main():
    """示例：记录测试数据"""

    # 创建记录器（A 组）
    recorder = ABTestRecorder(group="A")

    # 示例：记录一个测试结果（GLM-5 表现）
    recorder.record_test(
        test_id="T1.1",
        run=1,
        question="查看项目中 Milvus 相关的代码实现，并分析其实现原理",
        # 效率指标
        tool_calls_total=4,
        tools_breakdown={"run_python": 4, "terminal": 0},
        batch_operations={
            "batch_search_count": 1,
            "batch_read_count": 1,
            "single_search_count": 0,
            "single_read_count": 2,
        },
        duration_total_ms=20000,
        duration_per_tool_avg_ms=5000,
        duration_per_tool_min_ms=3,
        duration_per_tool_max_ms=4008,
        # Token 指标
        input_tokens=5000,
        output_tokens=2000,
        tokens_breakdown={
            "system_prompt_tokens": 2500,
            "conversation_history_tokens": 1500,
            "tool_input_tokens": 500,
            "tool_output_tokens": 500,
        },
        cost_usd=0.0045,
        # 错误指标
        errors_total=0,
        error_details=[],
        auto_fix_attempts=0,
        auto_fix_successes=0,
        # 质量指标
        answer_quality={
            "overall_score": 4,
            "accuracy_score": 5,
            "completeness_score": 4,
            "clarity_score": 4,
            "usefulness_score": 4,
        },
        code_quality={
            "overall_score": 5,
            "efficiency_score": 5,
            "correctness_score": 5,
            "readability_score": 4,
            "best_practice_score": 5,
        },
        # 行为指标
        behavior={
            "two_phase_pattern_used": True,
            "batch_operations_used": True,
            "terminal_misuse_count": 0,
        },
        # 其他指标
        memory_usage={"prefetch_count": 14},
        knowledge_base_usage={"kb_search_count": 0},
        notes="GLM-5 模型，两阶段模式，批量操作"
    )

    # 保存结果
    recorder.save()

    # 打印摘要
    recorder.print_summary()

    print("\n提示：这是示例数据，实际测试时需要根据真实日志填写数据")


if __name__ == "__main__":
    main()
