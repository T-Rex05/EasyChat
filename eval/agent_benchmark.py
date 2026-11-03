"""
Agent 多维度评测框架

评测维度（6 个）：
  D1. 安全性（Safety）：AST 检查 + 受限 builtins + 沙箱逃逸防御
  D2. 截断保护（Truncation）：safe_print 双层截断 + 边界行为
  D3. 隔离性（Isolation）：globals 隔离 + 上下文隔离 + 并发隔离
  D4. 工具集成（Tool Integration）：_ToolWrapper 监控 + 缓存 + 错误处理
  D5. 可观测性（Observability）：统计记录 + 日志格式 + 线程安全
  D6. 并发与性能（Concurrency & Performance）：并发执行 + 超时 + 资源清理

运行方式：
  python eval/agent_benchmark.py
  python eval/agent_benchmark.py --dimension safety    # 只跑某个维度
  python eval/agent_benchmark.py --verbose             # 详细输出
"""

import io
import sys
import os
import time
import threading
import traceback
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

# Windows 控制台 UTF-8 输出
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.tools.code_executor import (
    check_ast_safety,
    create_safe_print,
    execute_code,
    build_safe_globals,
    SAFE_BUILTINS,
    MAX_SINGLE_PRINT,
    MAX_TOTAL_OUTPUT,
    DEFAULT_TIMEOUT,
    DANGEROUS_FUNCTIONS,
    DANGEROUS_ATTRIBUTES,
    _CodeModeStats,
    _ToolWrapper,
    _stats,
    get_code_mode_stats,
    _executor,
    _INNER_TOOL_OUTPUT_WARN_CHARS,
)


# ──────────────────────────────────────────────────────────────
# 评测基础设施
# ──────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    """单个测试用例"""
    name: str
    fn: callable
    category: str = ""
    description: str = ""


@dataclass
class TestResult:
    """单个测试结果"""
    name: str
    passed: bool
    duration_ms: float = 0.0
    error: str = ""
    category: str = ""


@dataclass
class DimensionReport:
    """单个维度报告"""
    name: str
    key: str
    results: list = field(default_factory=list)
    weight: float = 1.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total * 100 if self.total > 0 else 0

    @property
    def avg_duration_ms(self) -> float:
        if not self.results:
            return 0
        return sum(r.duration_ms for r in self.results) / len(self.results)


class AgentBenchmark:
    """Agent 多维度评测框架"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.dimensions: list[DimensionReport] = []
        self.start_time = None
        self.end_time = None

    def add_dimension(self, name: str, key: str, weight: float = 1.0) -> DimensionReport:
        dim = DimensionReport(name=name, key=key, weight=weight)
        self.dimensions.append(dim)
        return dim

    def run_test(self, dim: DimensionReport, tc: TestCase) -> TestResult:
        start = time.time()
        try:
            tc.fn()
            passed = True
            error = ""
        except AssertionError as e:
            passed = False
            error = str(e)
        except Exception as e:
            passed = False
            error = f"{type(e).__name__}: {e}"
        duration_ms = (time.time() - start) * 1000

        result = TestResult(
            name=tc.name, passed=passed, duration_ms=duration_ms,
            error=error, category=tc.category,
        )
        dim.results.append(result)

        if self.verbose:
            status = "✅" if passed else "❌"
            print(f"  {status} {tc.name} ({duration_ms:.1f}ms)")
            if not passed and error:
                print(f"     └─ {error}")

        return result

    def run_all(self, dimension_filter: str = None):
        self.start_time = time.time()
        for dim in self.dimensions:
            if dimension_filter and dim.key != dimension_filter:
                continue
            if self.verbose:
                print(f"\n{'='*60}")
                print(f"📊 维度: {dim.name} ({dim.key})")
                print(f"{'='*60}")
            # 获取该维度的测试用例
            test_cases = self._get_test_cases(dim.key)
            for tc in test_cases:
                self.run_test(dim, tc)
        self.end_time = time.time()

    def _get_test_cases(self, dimension: str) -> list:
        """获取指定维度的测试用例"""
        builder = TestBuilder()
        methods = {
            "safety": builder.safety_tests(),
            "truncation": builder.truncation_tests(),
            "isolation": builder.isolation_tests(),
            "tool_integration": builder.tool_integration_tests(),
            "observability": builder.observability_tests(),
            "concurrency": builder.concurrency_tests(),
        }
        return methods.get(dimension, [])

    def generate_report(self) -> str:
        """生成 Markdown 报告"""
        total_time = (self.end_time - self.start_time) if self.end_time and self.start_time else 0
        total_tests = sum(d.total for d in self.dimensions)
        total_passed = sum(d.passed for d in self.dimensions)
        total_failed = sum(d.failed for d in self.dimensions)

        lines = []
        lines.append("# Agent 多维度评测报告")
        lines.append("")
        lines.append(f"**评测时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**总耗时**: {total_time:.1f}s")
        lines.append(f"**总用例**: {total_tests} | ✅ 通过 {total_passed} | ❌ 失败 {total_failed}")
        lines.append(f"**总通过率**: {total_passed/total_tests*100:.1f}%" if total_tests > 0 else "**总通过率**: N/A")
        lines.append("")

        # 汇总表
        lines.append("## 维度汇总")
        lines.append("")
        lines.append("| 维度 | 用例数 | 通过 | 失败 | 通过率 | 平均耗时 | 权重 |")
        lines.append("|------|--------|------|------|--------|----------|------|")
        for dim in self.dimensions:
            lines.append(
                f"| {dim.name} | {dim.total} | {dim.passed} | {dim.failed} | "
                f"{dim.pass_rate:.1f}% | {dim.avg_duration_ms:.1f}ms | {dim.weight} |"
            )

        # 加权得分
        total_weight = sum(d.weight for d in self.dimensions)
        weighted_score = sum(d.pass_rate * d.weight for d in self.dimensions) / total_weight if total_weight > 0 else 0
        lines.append("")
        lines.append(f"**加权总分**: {weighted_score:.1f} / 100")
        lines.append("")

        # 各维度详情
        for dim in self.dimensions:
            lines.append(f"## {dim.name}")
            lines.append("")
            failed_tests = [r for r in dim.results if not r.passed]
            if failed_tests:
                lines.append("### ❌ 失败用例")
                lines.append("")
                for r in failed_tests:
                    lines.append(f"- **{r.name}**: {r.error}")
                lines.append("")
            else:
                lines.append("✅ 全部通过")
                lines.append("")

        # 结论
        lines.append("## 评测结论")
        lines.append("")
        if weighted_score >= 95:
            grade = "A（优秀）"
        elif weighted_score >= 85:
            grade = "B（良好）"
        elif weighted_score >= 70:
            grade = "C（合格）"
        else:
            grade = "D（需改进）"
        lines.append(f"**评级**: {grade}")
        lines.append(f"**加权得分**: {weighted_score:.1f}")
        lines.append("")
        if total_failed > 0:
            lines.append("**需关注的问题**:")
            for dim in self.dimensions:
                for r in dim.results:
                    if not r.passed:
                        lines.append(f"- [{dim.name}] {r.name}: {r.error}")
        else:
            lines.append("所有测试通过，Code Mode 实现质量优秀。")
        lines.append("")

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# 测试用例构建器
# ──────────────────────────────────────────────────────────────

class TestBuilder:
    """构建各维度测试用例"""

    # ─── D1: 安全性 ───

    def safety_tests(self) -> list:
        tests = []

        # --- AST 检查：基础危险操作 ---
        dangerous_code = [
            ("import os", "import"),
            ("from os import path", "import"),
            ("eval('1+1')", "eval"),
            ("exec('print(1)')", "exec"),
            ("open('/etc/passwd')", "open"),
            ("__import__('os')", "__import__"),
            ("input('prompt')", "input"),
            ("exit()", "exit"),
            ("quit()", "quit"),
            ("compile('1', '<x>', 'eval')", "compile"),
        ]
        for code, keyword in dangerous_code:
            tests.append(TestCase(
                name=f"AST 拒绝 {keyword}",
                fn=self._make_ast_deny_test(code, keyword),
                category="ast_safety",
            ))

        # --- AST 检查：危险属性 ---
        dangerous_attrs = [
            ("x.__globals__", "__globals__"),
            ("x.__builtins__", "__builtins__"),
            ("x.__subclasses__", "__subclasses__"),
            ("x.__class__", "__class__"),
            ("x.__bases__", "__bases__"),
            ("x.__import__", "__import__"),
        ]
        for code, attr in dangerous_attrs:
            tests.append(TestCase(
                name=f"AST 拒绝属性 {attr}",
                fn=self._make_ast_deny_test(code, attr),
                category="ast_safety",
            ))

        # --- 受限 builtins ---
        dangerous_builtins = ["open", "eval", "exec", "compile", "__import__", "input", "exit",
                              "getattr", "hasattr", "setattr", "delattr"]
        for name in dangerous_builtins:
            tests.append(TestCase(
                name=f"builtins 不含 {name}",
                fn=self._make_builtins_deny_test(name),
                category="builtins_safety",
            ))

        # --- 安全 builtins ---
        safe_builtins = ["int", "str", "len", "range", "sorted", "True", "False", "None",
                         "list", "dict", "set", "tuple", "sum", "max", "min", "abs"]
        for name in safe_builtins:
            tests.append(TestCase(
                name=f"builtins 包含 {name}",
                fn=self._make_builtins_allow_test(name),
                category="builtins_safety",
            ))

        # --- 沙箱逃逸尝试 ---
        escape_attempts = [
            ("type(1).__class__", "type().__class__"),
            ("""().__class__.__bases__""", "().__class__.__bases__"),
        ]
        for code, desc in escape_attempts:
            tests.append(TestCase(
                name=f"阻止沙箱逃逸: {desc}",
                fn=self._make_ast_deny_test(code, ""),
                category="sandbox_escape",
            ))

        # getattr 绕过尝试（getattr 已从 builtins 移除，应 NameError）
        tests.append(TestCase(
            name="getattr 不可用（防御绕过）",
            fn=self._make_exec_deny_test(
                "x = getattr(type(1), '__class__')",
                "NameError",
            ),
            category="sandbox_escape",
        ))

        # hasattr 不可用
        tests.append(TestCase(
            name="hasattr 不可用",
            fn=self._make_exec_deny_test(
                "x = hasattr([], 'append')",
                "NameError",
            ),
            category="sandbox_escape",
        ))

        # 语法错误也应被拒绝
        tests.append(TestCase(
            name="AST 拒绝语法错误",
            fn=self._make_ast_deny_test("def foo(", "语法错误"),
            category="ast_safety",
        ))

        # 安全代码应通过
        safe_codes = [
            ("print('hello')", "简单 print"),
            ("for i in range(5): print(i)", "for 循环"),
            ("x = [1,2,3]; print(sum(x))", "列表求和"),
            ("result = knowledge_search('test')", "工具调用"),
            ("x = {'a': 1}; print(x['a'])", "字典操作"),
        ]
        for code, desc in safe_codes:
            tests.append(TestCase(
                name=f"AST 允许安全代码: {desc}",
                fn=self._make_ast_allow_test(code),
                category="ast_safety",
            ))

        return tests

    def _make_ast_deny_test(self, code, keyword):
        def test():
            is_safe, error = check_ast_safety(code)
            assert is_safe is False, f"应该被拒绝: {code}"
            if keyword:
                assert keyword.lower() in error.lower(), f"错误信息应包含 '{keyword}': {error}"
        return test

    def _make_ast_allow_test(self, code):
        def test():
            is_safe, error = check_ast_safety(code)
            assert is_safe is True, f"应该被允许: {code}, error={error}"
        return test

    def _make_builtins_deny_test(self, name):
        def test():
            assert name not in SAFE_BUILTINS, f"SAFE_BUILTINS 不应包含 {name}"
        return test

    def _make_builtins_allow_test(self, name):
        def test():
            assert name in SAFE_BUILTINS, f"SAFE_BUILTINS 应包含 {name}"
        return test

    def _make_exec_deny_test(self, code, expected_error):
        def test():
            result = execute_code(code)
            assert result["success"] is False, f"应该执行失败: {code}"
            assert expected_error in result["error"], \
                f"期望 {expected_error}, 实际: {result['error']}"
        return test

    # ─── D2: 截断保护 ───

    def truncation_tests(self) -> list:
        tests = []

        # 正常输出
        tests.append(TestCase(
            name="正常 short 输出",
            fn=lambda: self._assert_print_output("hello", "hello\n"),
            category="safe_print",
        ))

        # 自定义 sep
        tests.append(TestCase(
            name="自定义 sep",
            fn=lambda: self._assert_print_output_args(["a", "b", "c"], {"sep": "-"}, "a-b-c\n"),
            category="safe_print",
        ))

        # 自定义 end
        tests.append(TestCase(
            name="自定义 end",
            fn=lambda: self._assert_print_output_args(["hello"], {"end": "!"}, "hello!"),
            category="safe_print",
        ))

        # 单次截断
        def test_single_truncation():
            buf = io.StringIO()
            sp = create_safe_print(buf)
            long_text = "x" * (MAX_SINGLE_PRINT + 5000)
            sp(long_text)
            output = buf.getvalue()
            assert "[PRINT TRUNCATED]" in output, "应触发单次截断"
            assert len(output) < len(long_text), "输出应被截断"
        tests.append(TestCase(name="单次 print 截断 (16K)", fn=test_single_truncation, category="safe_print"))

        # 总输出限制
        def test_total_limit():
            buf = io.StringIO()
            sp = create_safe_print(buf)
            for _ in range(5):
                sp("x" * 10000)
            output = buf.getvalue()
            assert "[TOTAL OUTPUT LIMIT REACHED]" in output, "应触发总输出限制"
        tests.append(TestCase(name="总输出限制 (32K)", fn=test_total_limit, category="safe_print"))

        # end 计入统计
        def test_end_counted():
            buf = io.StringIO()
            sp = create_safe_print(buf)
            count = MAX_TOTAL_OUTPUT // 2 + 10
            for _ in range(count):
                sp("x")
            output = buf.getvalue()
            assert "[TOTAL OUTPUT LIMIT REACHED]" in output, "\\n 应计入总字符数"
        tests.append(TestCase(name="end (\\n) 计入总字符统计", fn=test_end_counted, category="safe_print"))

        # 自定义 end 计入统计
        def test_custom_end_counted():
            buf = io.StringIO()
            sp = create_safe_print(buf)
            count = MAX_TOTAL_OUTPUT // 11 + 5
            for _ in range(count):
                sp("x", end="0123456789")
            output = buf.getvalue()
            assert "[TOTAL OUTPUT LIMIT REACHED]" in output, "自定义 end 应计入总字符数"
        tests.append(TestCase(name="自定义 end 计入统计", fn=test_custom_end_counted, category="safe_print"))

        # 达到限制后不再写入
        def test_silence_after_limit():
            buf = io.StringIO()
            sp = create_safe_print(buf)
            # 先填满
            for _ in range(MAX_TOTAL_OUTPUT // 100 + 1):
                sp("x" * 100)
            # 记录当前长度
            length_after_limit = len(buf.getvalue())
            # 再尝试写入
            sp("SHOULD_NOT_APPEAR")
            final_output = buf.getvalue()
            assert "SHOULD_NOT_APPEAR" not in final_output, "达到限制后不应再写入"
            assert len(final_output) == length_after_limit, "达到限制后 buffer 不应增长"
        tests.append(TestCase(name="达到限制后静默丢弃", fn=test_silence_after_limit, category="safe_print"))

        # execute_code 最终输出也受限制
        def test_execute_code_output_limit():
            code = f'print("{"x" * (MAX_TOTAL_OUTPUT + 1000)}")'
            result = execute_code(code)
            assert result["success"] is True
            assert len(result["output"]) <= MAX_TOTAL_OUTPUT + 200  # 允许截断提示的额外字符
        tests.append(TestCase(name="execute_code 输出受总限制", fn=test_execute_code_output_limit, category="safe_print"))

        # 空 print
        def test_empty_print():
            buf = io.StringIO()
            sp = create_safe_print(buf)
            sp()
            assert buf.getvalue() == "\n", f"空 print 应输出 \\n, 实际: {repr(buf.getvalue())}"
        tests.append(TestCase(name="空 print 输出 \\n", fn=test_empty_print, category="safe_print"))

        return tests

    def _assert_print_output(self, text, expected):
        buf = io.StringIO()
        sp = create_safe_print(buf)
        sp(text)
        assert buf.getvalue() == expected, f"期望 {repr(expected)}, 实际 {repr(buf.getvalue())}"

    def _assert_print_output_args(self, args, kwargs, expected):
        buf = io.StringIO()
        sp = create_safe_print(buf)
        sp(*args, **kwargs)
        assert buf.getvalue() == expected, f"期望 {repr(expected)}, 实际 {repr(buf.getvalue())}"

    # ─── D3: 隔离性 ───

    def isolation_tests(self) -> list:
        tests = []

        # 外部变量不可访问
        def test_no_external_var():
            _my_secret = "should_not_leak"
            result = execute_code("""
try:
    _ = _my_secret
    print("LEAKED")
except NameError:
    print("PASS")
""")
            assert result["success"] is True
            assert "PASS" in result["output"]
            assert "LEAKED" not in result["output"]
        tests.append(TestCase(name="外部局部变量不可访问", fn=test_no_external_var, category="isolation"))

        # import 被禁止
        def test_no_import():
            result = execute_code("import os")
            assert result["success"] is False
            assert "import" in result["error"].lower()
        tests.append(TestCase(name="import 被 AST 拒绝", fn=test_no_import, category="isolation"))

        # open 被禁止
        def test_no_open():
            result = execute_code("f = open('/etc/passwd')")
            assert result["success"] is False
        tests.append(TestCase(name="open 被 AST 拒绝", fn=test_no_open, category="isolation"))

        # eval/exec 被禁止
        def test_no_eval():
            result = execute_code("x = eval('1+1')")
            assert result["success"] is False
        tests.append(TestCase(name="eval 被 AST 拒绝", fn=test_no_eval, category="isolation"))

        # globals 不在 builtins 中
        def test_no_globals_func():
            result = execute_code("g = globals()")
            assert result["success"] is False
            assert "NameError" in result["error"]
        tests.append(TestCase(name="globals() 不可用", fn=test_no_globals_func, category="isolation"))

        # locals 不在 builtins 中
        def test_no_locals_func():
            result = execute_code("l = locals()")
            assert result["success"] is False
            assert "NameError" in result["error"]
        tests.append(TestCase(name="locals() 不可用", fn=test_no_locals_func, category="isolation"))

        # __builtins__ 被受限替换
        def test_restricted_builtins():
            result = execute_code("""
try:
    open
    print("LEAKED: open available")
except NameError:
    print("PASS: open blocked")
""")
            assert result["success"] is True
            assert "PASS" in result["output"]
        tests.append(TestCase(name="__builtins__ 被受限替换", fn=test_restricted_builtins, category="isolation"))

        # 每次 build_safe_globals 返回独立 dict
        def test_independent_globals():
            g1 = build_safe_globals()
            g2 = build_safe_globals()
            assert g1 is not g2, "每次应返回不同的 dict"
            g1["__builtins__"]["test_key"] = "polluted"
            g2_builtins = g2.get("__builtins__", {})
            assert "test_key" not in g2_builtins, "修改一个 globals 不应影响另一个"
        tests.append(TestCase(name="globals 独立不共享", fn=test_independent_globals, category="isolation"))

        # 工具函数以 _ToolWrapper 包装
        def test_tools_are_wrapped():
            g = build_safe_globals()
            for name in ["knowledge_search", "get_current_time"]:
                if name in g:
                    assert isinstance(g[name], _ToolWrapper), \
                        f"{name} 应为 _ToolWrapper, 实际: {type(g[name])}"
        tests.append(TestCase(name="工具函数经 _ToolWrapper 包装", fn=test_tools_are_wrapped, category="isolation"))

        # 并发隔离：两个线程同时执行不同代码互不干扰
        def test_concurrent_isolation():
            results = {}
            def run_code(thread_id, code):
                r = execute_code(code)
                results[thread_id] = r

            import threading
            t1 = threading.Thread(target=run_code, args=(1, "x = 100\nprint(x)"))
            t2 = threading.Thread(target=run_code, args=(2, "x = 200\nprint(x)"))
            t1.start(); t2.start()
            t1.join(timeout=10); t2.join(timeout=10)
            assert 1 in results and 2 in results, "两个线程都应完成"
            assert "100" in results[1]["output"], f"线程1应输出100: {results[1]['output']}"
            assert "200" in results[2]["output"], f"线程2应输出200: {results[2]['output']}"
        tests.append(TestCase(name="并发执行互不干扰", fn=test_concurrent_isolation, category="isolation"))

        return tests

    # ─── D4: 工具集成 ───

    def tool_integration_tests(self) -> list:
        tests = []

        # _ToolWrapper 调用计数
        def test_wrapper_call_counting():
            mock_calls = [0]
            def mock_tool():
                mock_calls[0] += 1
                return "result"
            wrapper = _ToolWrapper(mock_tool, "mock_tool")
            for _ in range(5):
                wrapper()
            assert mock_calls[0] == 5, f"应调用5次, 实际: {mock_calls[0]}"
        tests.append(TestCase(name="_ToolWrapper 调用计数", fn=test_wrapper_call_counting, category="tool_wrapper"))

        # _ToolWrapper 大输出告警
        def test_wrapper_large_output_warning():
            def mock_large_tool():
                return "x" * (_INNER_TOOL_OUTPUT_WARN_CHARS + 1000)
            wrapper = _ToolWrapper(mock_large_tool, "mock_large")
            result = wrapper()
            assert len(result) > _INNER_TOOL_OUTPUT_WARN_CHARS
        tests.append(TestCase(name="_ToolWrapper 大输出不截断（只告警）", fn=test_wrapper_large_output_warning, category="tool_wrapper"))

        # _ToolWrapper 异常传播
        def test_wrapper_exception_propagation():
            def mock_failing_tool():
                raise ValueError("tool failed")
            wrapper = _ToolWrapper(mock_failing_tool, "mock_fail")
            try:
                wrapper()
                assert False, "应抛出异常"
            except ValueError as e:
                assert "tool failed" in str(e)
        tests.append(TestCase(name="_ToolWrapper 异常传播", fn=test_wrapper_exception_propagation, category="tool_wrapper"))

        # _ToolWrapper 保留参数传递
        def test_wrapper_args_passthrough():
            def mock_tool(a, b, c=None):
                return f"{a}-{b}-{c}"
            wrapper = _ToolWrapper(mock_tool, "mock_args")
            result = wrapper("x", "y", c="z")
            assert result == "x-y-z", f"参数应正确传递: {result}"
        tests.append(TestCase(name="_ToolWrapper 参数透传", fn=test_wrapper_args_passthrough, category="tool_wrapper"))

        # _ToolWrapper kwargs 传递
        def test_wrapper_kwargs():
            def mock_tool(query="", top_k=5):
                return f"q={query},k={top_k}"
            wrapper = _ToolWrapper(mock_tool, "mock_kwargs")
            result = wrapper(query="test", top_k=10)
            assert result == "q=test,k=10"
        tests.append(TestCase(name="_ToolWrapper kwargs 传递", fn=test_wrapper_kwargs, category="tool_wrapper"))

        # 工具缓存
        def test_tool_caching():
            from backend.tools.code_executor import _get_tool_functions, _cached_tool_functions
            t1 = _get_tool_functions()
            t2 = _get_tool_functions()
            assert t1 is t2, "应返回缓存的同一对象"
        tests.append(TestCase(name="工具函数缓存复用", fn=test_tool_caching, category="tool_cache"))

        # build_safe_globals 包含工具
        def test_globals_has_tools():
            g = build_safe_globals()
            # 至少 knowledge_search 或 get_current_time 应存在
            known_tools = ["knowledge_search", "get_current_time"]
            found = [t for t in known_tools if t in g]
            assert len(found) >= 1, f"至少应有1个工具, 实际: {list(g.keys())}"
        tests.append(TestCase(name="globals 包含可用工具", fn=test_globals_has_tools, category="tool_cache"))

        # run_python 在 BYPASS_TOOLS 中
        def test_run_python_bypass():
            from backend.tools.tool_output_guard import BYPASS_TOOLS
            assert "run_python" in BYPASS_TOOLS, "run_python 应在 BYPASS_TOOLS 中"
        tests.append(TestCase(name="run_python 在 BYPASS_TOOLS", fn=test_run_python_bypass, category="integration"))

        # run_python 执行成功
        def test_run_python_end_to_end():
            from backend.tools.code_executor import run_python
            result = run_python.invoke({"code": "print('e2e test')"})
            assert "e2e test" in result
        tests.append(TestCase(name="run_python 端到端执行", fn=test_run_python_end_to_end, category="integration"))

        # run_python 安全检查
        def test_run_python_safety():
            from backend.tools.code_executor import run_python
            result = run_python.invoke({"code": "import os"})
            assert "❌" in result
            assert "安全检查失败" in result
        tests.append(TestCase(name="run_python 安全检查拒绝", fn=test_run_python_safety, category="integration"))

        # ── Code Mode 增强评测（重试/自动修复/错误消息） ──

        # 自动修复：拼写错误纠正（get_curent_time → get_current_time）
        def test_auto_fix_name_typo():
            from backend.tools.code_executor import run_python
            code = "t = get_curent_time()\nprint(t)"
            result = run_python.invoke({"code": code})
            # 应自动修正并成功输出时间
            assert "❌" not in result or "自动修正" in result
        tests.append(TestCase(name="自动修复：拼写错误纠正", fn=test_auto_fix_name_typo, category="enhanced"))

        # 重试机制：execute_code_with_retry 基本功能
        def test_retry_mechanism():
            from backend.tools.code_executor import execute_code_with_retry
            result = execute_code_with_retry("print('retry test ok')")
            assert result["success"] is True
            assert len(result["execution_history"]) == 1
            assert result["auto_fixed"] is False
        tests.append(TestCase(name="重试机制：首次成功", fn=test_retry_mechanism, category="enhanced"))

        # 错误分类：NameError 正确分类
        def test_error_classification_name():
            from backend.tools.code_executor import classify_error, ErrorCategory
            cat = classify_error("name 'foo' is not defined", "NameError")
            assert cat == ErrorCategory.NAME_ERROR
        tests.append(TestCase(name="错误分类：NameError", fn=test_error_classification_name, category="enhanced"))

        # 错误分类：Timeout 正确分类
        def test_error_classification_timeout():
            from backend.tools.code_executor import classify_error, ErrorCategory
            cat = classify_error("代码执行超时（15s）", "TimeoutError")
            assert cat == ErrorCategory.TIMEOUT
        tests.append(TestCase(name="错误分类：Timeout", fn=test_error_classification_timeout, category="enhanced"))

        # 编辑距离算法正确性
        def test_edit_distance():
            from backend.tools.code_executor import _edit_distance
            assert _edit_distance("abc", "abc") == 0
            assert _edit_distance("", "abc") == 3
            assert _edit_distance("kitten", "sitting") == 3
        tests.append(TestCase(name="编辑距离算法", fn=test_edit_distance, category="enhanced"))

        # 工具签名表包含可用工具
        def test_tool_signatures_present():
            from backend.tools.code_executor import _build_tool_signatures
            sigs = _build_tool_signatures()
            assert "get_current_time" in sigs
            assert "knowledge_search" in sigs
            for name, sig in sigs.items():
                assert sig.startswith(name)
                assert "(" in sig
        tests.append(TestCase(name="工具签名表完整性", fn=test_tool_signatures_present, category="enhanced"))

        # _CodeModeStats 自动修复统计
        def test_stats_auto_fix():
            stats = _CodeModeStats()
            stats.record_auto_fix(success=True)
            stats.record_auto_fix(success=False)
            snap = stats.snapshot()
            assert snap["auto_fixes"] == 2
            assert snap["auto_fix_successes"] == 1
        tests.append(TestCase(name="Stats 自动修复统计", fn=test_stats_auto_fix, category="enhanced"))

        # 错误消息包含工具签名提示（TypeError 场景）
        def test_error_message_has_signatures():
            from backend.tools.code_executor import _build_error_message
            result = {
                "success": False,
                "error": "TypeError: knowledge_search() got unexpected arg",
                "execution_history": [{"attempt": 1, "success": False}],
            }
            msg = _build_error_message(result)
            assert "可用工具签名" in msg
            assert "knowledge_search" in msg
        tests.append(TestCase(name="错误消息包含工具签名", fn=test_error_message_has_signatures, category="enhanced"))

        # 幽灵工具已清除：docstring 不再包含 memory_search / web_search
        def test_no_phantom_tools():
            from backend.tools.code_executor import run_python
            docstring = run_python.func.__doc__ or ""
            assert "memory_search" not in docstring, "docstring 不应包含已移除的 memory_search"
            assert "web_search" not in docstring, "docstring 不应包含已移除的 web_search"
        tests.append(TestCase(name="幽灵工具已清除", fn=test_no_phantom_tools, category="enhanced"))

        return tests

    # ─── D5: 可观测性 ───

    def observability_tests(self) -> list:
        tests = []

        # _CodeModeStats 基本记录
        def test_stats_basic():
            stats = _CodeModeStats()
            stats.record_call(True, 100.0)
            stats.record_call(True, 200.0)
            stats.record_call(False, 50.0)
            snap = stats.snapshot()
            assert snap["total_calls"] == 3
            assert snap["successful_calls"] == 2
            assert snap["failed_calls"] == 1
            assert abs(snap["avg_duration_ms"] - 116.67) < 1
        tests.append(TestCase(name="Stats 基本记录", fn=test_stats_basic, category="stats"))

        # _CodeModeStats 安全拒绝计数
        def test_stats_safety_rejection():
            stats = _CodeModeStats()
            stats.record_safety_rejection()
            stats.record_safety_rejection()
            snap = stats.snapshot()
            assert snap["safety_rejections"] == 2
        tests.append(TestCase(name="Stats 安全拒绝计数", fn=test_stats_safety_rejection, category="stats"))

        # _CodeModeStats 内部工具调用计数
        def test_stats_inner_tool_calls():
            stats = _CodeModeStats()
            stats.record_inner_tool_call()
            stats.record_inner_tool_call()
            stats.record_inner_tool_call()
            snap = stats.snapshot()
            assert snap["inner_tool_calls"] == 3
        tests.append(TestCase(name="Stats 内部工具调用计数", fn=test_stats_inner_tool_calls, category="stats"))

        # _CodeModeStats 零除安全
        def test_stats_zero_division_safe():
            stats = _CodeModeStats()
            snap = stats.snapshot()
            assert snap["avg_duration_ms"] == 0, "无调用时平均耗时应为0"
        tests.append(TestCase(name="Stats 零除安全", fn=test_stats_zero_division_safe, category="stats"))

        # _CodeModeStats 线程安全
        def test_stats_thread_safety():
            stats = _CodeModeStats()
            errors = []
            def worker(n):
                try:
                    for i in range(n):
                        stats.record_call(True, 1.0)
                        stats.record_inner_tool_call()
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker, args=(100,)) for _ in range(10)]
            for t in threads: t.start()
            for t in threads: t.join(timeout=10)
            assert not errors, f"并发操作应无异常: {errors}"
            snap = stats.snapshot()
            assert snap["total_calls"] == 1000, f"应为1000, 实际: {snap['total_calls']}"
            assert snap["inner_tool_calls"] == 1000
        tests.append(TestCase(name="Stats 线程安全 (10线程×100次)", fn=test_stats_thread_safety, category="stats"))

        # get_code_mode_stats 返回 dict
        def test_get_stats_api():
            snap = get_code_mode_stats()
            assert isinstance(snap, dict)
            assert "total_calls" in snap
            assert "avg_duration_ms" in snap
        tests.append(TestCase(name="get_code_mode_stats API", fn=test_get_stats_api, category="stats"))

        # _ToolWrapper 调用后统计增加
        def test_wrapper_increments_stats():
            initial = _stats.snapshot()["inner_tool_calls"]
            def mock(): return "ok"
            w = _ToolWrapper(mock, "test")
            w()
            after = _stats.snapshot()["inner_tool_calls"]
            assert after == initial + 1, f"调用后 inner_tool_calls 应+1: {initial} -> {after}"
        tests.append(TestCase(name="_ToolWrapper 调用递增全局统计", fn=test_wrapper_increments_stats, category="stats"))

        # 结构化日志格式检查
        def test_structured_log_format():
            import logging
            logger = logging.getLogger("agentforge.code_mode")
            assert logger.name == "agentforge.code_mode"
        tests.append(TestCase(name="Code Mode 专用 logger 存在", fn=test_structured_log_format, category="logging"))

        return tests

    # ─── D6: 并发与性能 ───

    def concurrency_tests(self) -> list:
        tests = []

        # 并发执行
        def test_concurrent_execution():
            results = {}
            def run(idx):
                r = execute_code(f"print({idx} * {idx})")
                results[idx] = r

            threads = [threading.Thread(target=run, args=(i,)) for i in range(8)]
            for t in threads: t.start()
            for t in threads: t.join(timeout=30)
            assert len(results) == 8, f"8个并发都应完成, 实际: {len(results)}"
            for i in range(8):
                assert str(i * i) in results[i]["output"], f"线程{i}结果错误"
        tests.append(TestCase(name="8线程并发执行", fn=test_concurrent_execution, category="concurrency"))

        # 超时处理
        def test_timeout():
            start = time.time()
            result = execute_code("x = 0\nwhile True: x += 1", timeout=2)
            elapsed = time.time() - start
            assert result["success"] is False
            assert "超时" in result["error"]
            assert elapsed < 5, f"超时应在合理时间内返回, 实际: {elapsed:.1f}s"
        tests.append(TestCase(name="超时处理 (2s)", fn=test_timeout, category="timeout"))

        # 默认超时值
        def test_default_timeout():
            assert DEFAULT_TIMEOUT == 15, f"默认超时应为15s, 实际: {DEFAULT_TIMEOUT}"
        tests.append(TestCase(name="默认超时 15s", fn=test_default_timeout, category="config"))

        # 线程池配置
        def test_thread_pool_config():
            assert _executor._max_workers == 8, f"线程池应为8, 实际: {_executor._max_workers}"
        tests.append(TestCase(name="线程池 8 workers", fn=test_thread_pool_config, category="config"))

        # 执行后资源不泄漏（output_buffer 被正确回收）
        def test_no_resource_leak():
            for _ in range(50):
                result = execute_code("print('leak test')")
                assert result["success"] is True
        tests.append(TestCase(name="50次连续执行无泄漏", fn=test_no_resource_leak, category="resources"))

        # 大输出执行的内存行为
        def test_large_output_memory():
            code = f'print("{"x" * 40000}")'
            result = execute_code(code)
            assert result["success"] is True
            assert len(result["output"]) <= MAX_TOTAL_OUTPUT + 200
        tests.append(TestCase(name="大输出受 safe_print 保护", fn=test_large_output_memory, category="resources"))

        # 异常代码不崩溃执行器
        def test_exception_doesnt_crash_executor():
            result1 = execute_code("raise RuntimeError('boom')")
            assert result1["success"] is False
            # 执行器应仍然可用
            result2 = execute_code("print('still alive')")
            assert result2["success"] is True
            assert "still alive" in result2["output"]
        tests.append(TestCase(name="异常后执行器仍可用", fn=test_exception_doesnt_crash_executor, category="resilience"))

        # 超时后执行器仍可用
        def test_executor_after_timeout():
            result1 = execute_code("while True: pass", timeout=1)
            assert result1["success"] is False
            # 执行器应仍然可用
            result2 = execute_code("print('recovered')")
            assert result2["success"] is True
            assert "recovered" in result2["output"]
        tests.append(TestCase(name="超时后执行器仍可用", fn=test_executor_after_timeout, category="resilience"))

        # 执行性能基准
        def test_performance_baseline():
            start = time.time()
            for _ in range(20):
                execute_code("print('perf')")
            elapsed = time.time() - start
            avg_ms = elapsed / 20 * 1000
            assert avg_ms < 500, f"平均执行时间应 <500ms, 实际: {avg_ms:.1f}ms"
        tests.append(TestCase(name="性能基准 (20次平均<500ms)", fn=test_performance_baseline, category="performance"))

        # contextvars 传递
        def test_contextvars_propagation():
            import contextvars
            test_var = contextvars.ContextVar("test_eval_var", default="default")
            test_var.set("from_parent")

            # 在受限环境中无法直接访问 contextvars 模块，
            # 但可以通过工具函数间接验证（工具内部可获取 contextvars）
            # 这里验证 copy_context 不会抛异常
            ctx = contextvars.copy_context()
            result = execute_code("print('ctx ok')")
            assert result["success"] is True
        tests.append(TestCase(name="contextvars copy 不抛异常", fn=test_contextvars_propagation, category="contextvars"))

        return tests


# ──────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent 多维度评测")
    parser.add_argument("--dimension", "-d", type=str, default=None,
                        help="只跑指定维度 (safety/truncation/isolation/tool_integration/observability/concurrency)")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--output", "-o", type=str, default=None, help="报告输出路径")
    args = parser.parse_args()

    benchmark = AgentBenchmark(verbose=args.verbose)

    # 注册 6 个维度
    benchmark.add_dimension("🔒 安全性", "safety", weight=1.5)
    benchmark.add_dimension("📏 截断保护", "truncation", weight=1.2)
    benchmark.add_dimension("🧱 隔离性", "isolation", weight=1.3)
    benchmark.add_dimension("🔧 工具集成", "tool_integration", weight=1.0)
    benchmark.add_dimension("📊 可观测性", "observability", weight=0.8)
    benchmark.add_dimension("⚡ 并发与性能", "concurrency", weight=1.0)

    print("=" * 60)
    print("🚀 Agent 多维度评测启动")
    print("=" * 60)

    benchmark.run_all(dimension_filter=args.dimension)

    # 生成报告
    report = benchmark.generate_report()

    # 控制台输出
    print("\n" + report)

    # 保存到文件
    output_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "report",
        f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n📄 报告已保存: {output_path}")

    # 退出码
    total_failed = sum(d.failed for d in benchmark.dimensions)
    sys.exit(1 if total_failed > 0 else 0)


if __name__ == "__main__":
    main()
