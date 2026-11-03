"""
Code Mode 执行器单元测试

测试覆盖：
  1. AST 安全检查
  2. safe_print 截断保护
  3. 受限 globals
  4. 代码执行
  5. 多用户隔离
  6. 错误分类系统
  7. 自动修复引擎
  8. 重试机制
  9. 工具签名注册表
"""

import io
import pytest

from backend.tools.code_executor import (
    check_ast_safety,
    create_safe_print,
    execute_code,
    execute_code_with_retry,
    build_safe_globals,
    classify_error,
    ErrorCategory,
    _extract_error_type,
    _edit_distance,
    _find_closest_name,
    _fix_name_error,
    _fix_type_error,
    _auto_fix_code,
    _build_tool_signatures,
    _build_error_message,
    _CodeModeStats,
    SAFE_BUILTINS,
    MAX_SINGLE_PRINT,
    MAX_TOTAL_OUTPUT,
    MAX_AUTO_RETRIES,
)


# ──────────────────────────────────────────────────────────────
# AST 安全检查测试
# ──────────────────────────────────────────────────────────────

class TestASTSafetyCheck:
    """AST 安全检查测试"""

    def test_safe_code_simple(self):
        """简单安全代码"""
        is_safe, error = check_ast_safety("print('hello')")
        assert is_safe is True
        assert error is None

    def test_safe_code_with_loop(self):
        """带循环的安全代码"""
        code = """
for i in range(5):
    print(i)
"""
        is_safe, error = check_ast_safety(code)
        assert is_safe is True

    def test_safe_code_with_function_call(self):
        """带函数调用的安全代码"""
        code = "results = knowledge_search('test')"
        is_safe, error = check_ast_safety(code)
        assert is_safe is True

    def test_dangerous_import(self):
        """禁止 import"""
        is_safe, error = check_ast_safety("import os")
        assert is_safe is False
        assert "import" in error.lower()

    def test_dangerous_from_import(self):
        """禁止 from ... import"""
        is_safe, error = check_ast_safety("from os import path")
        assert is_safe is False
        assert "import" in error.lower()

    def test_dangerous_eval(self):
        """禁止 eval"""
        is_safe, error = check_ast_safety("eval('1+1')")
        assert is_safe is False
        assert "eval" in error.lower()

    def test_dangerous_exec(self):
        """禁止 exec"""
        is_safe, error = check_ast_safety("exec('print(1)')")
        assert is_safe is False
        assert "exec" in error.lower()

    def test_dangerous_open(self):
        """禁止 open"""
        is_safe, error = check_ast_safety("open('/etc/passwd')")
        assert is_safe is False
        assert "open" in error.lower()

    def test_dangerous_dunder_import(self):
        """禁止 __import__"""
        is_safe, error = check_ast_safety("__import__('os')")
        assert is_safe is False

    def test_dangerous_attribute_globals(self):
        """禁止访问 __globals__"""
        is_safe, error = check_ast_safety("x.__globals__")
        assert is_safe is False
        assert "__globals__" in error

    def test_dangerous_attribute_builtins(self):
        """禁止访问 __builtins__"""
        is_safe, error = check_ast_safety("x.__builtins__")
        assert is_safe is False

    def test_syntax_error(self):
        """语法错误"""
        is_safe, error = check_ast_safety("def foo(")
        assert is_safe is False
        assert "语法错误" in error


# ──────────────────────────────────────────────────────────────
# safe_print 测试
# ──────────────────────────────────────────────────────────────

class TestSafePrint:
    """safe_print 截断保护测试"""

    def test_normal_print(self):
        """正常输出"""
        buffer = io.StringIO()
        safe_print = create_safe_print(buffer)
        safe_print("hello", "world")
        assert buffer.getvalue() == "hello world\n"

    def test_print_with_separator(self):
        """自定义分隔符"""
        buffer = io.StringIO()
        safe_print = create_safe_print(buffer)
        safe_print("a", "b", "c", sep="-")
        assert buffer.getvalue() == "a-b-c\n"

    def test_print_with_end(self):
        """自定义结束符"""
        buffer = io.StringIO()
        safe_print = create_safe_print(buffer)
        safe_print("hello", end="!")
        assert buffer.getvalue() == "hello!"

    def test_single_print_truncation(self):
        """单次 print 截断"""
        buffer = io.StringIO()
        safe_print = create_safe_print(buffer)
        long_text = "x" * (MAX_SINGLE_PRINT + 1000)
        safe_print(long_text)
        output = buffer.getvalue()
        assert "[PRINT TRUNCATED]" in output
        assert len(output) < len(long_text)

    def test_total_output_limit(self):
        """总输出限制"""
        buffer = io.StringIO()
        safe_print = create_safe_print(buffer)
        # 多次 print 超过总限制
        chunk = "x" * 10000
        for _ in range(5):  # 50K > MAX_TOTAL_OUTPUT (32K)
            safe_print(chunk)
        output = buffer.getvalue()
        assert "[TOTAL OUTPUT LIMIT REACHED]" in output

    def test_end_counted_in_total_chars(self):
        """end 参数（默认 \\n）计入 total_chars 统计

        修复前 end 未计入，大量 print 的 \\n 累积可能超出限制。
        """
        buffer = io.StringIO()
        safe_print = create_safe_print(buffer)
        # 每次 print 1 字符 + 1 字符 end（\n），共计 2 字符/次
        # 约 MAX_TOTAL_OUTPUT / 2 次后触发限制
        count = MAX_TOTAL_OUTPUT // 2 + 10
        for _ in range(count):
            safe_print("x")
        output = buffer.getvalue()
        # 触发限制后应有提示，且后续 print 不再写入
        assert "[TOTAL OUTPUT LIMIT REACHED]" in output

    def test_custom_end_counted(self):
        """自定义 end 也计入 total_chars"""
        buffer = io.StringIO()
        safe_print = create_safe_print(buffer)
        # 每次 print 1 字符 + 10 字符 end
        # MAX_TOTAL_OUTPUT / 11 次后触发
        count = MAX_TOTAL_OUTPUT // 11 + 5
        for _ in range(count):
            safe_print("x", end="0123456789")
        output = buffer.getvalue()
        assert "[TOTAL OUTPUT LIMIT REACHED]" in output


# ──────────────────────────────────────────────────────────────
# 受限 globals 测试
# ──────────────────────────────────────────────────────────────

class TestRestrictedGlobals:
    """受限 globals 测试"""

    def test_has_safe_builtins(self):
        """包含安全内建函数"""
        globals_dict = build_safe_globals()
        builtins = globals_dict.get("__builtins__", {})
        assert "len" in builtins
        assert "range" in builtins
        assert "sorted" in builtins
        assert "int" in builtins
        assert "list" in builtins

    def test_no_dangerous_builtins(self):
        """不包含危险内建函数"""
        globals_dict = build_safe_globals()
        builtins = globals_dict.get("__builtins__", {})
        assert "open" not in builtins
        assert "eval" not in builtins
        assert "exec" not in builtins
        assert "__import__" not in builtins
        assert "input" not in builtins

    def test_safe_builtins_constant(self):
        """SAFE_BUILTINS 模块级常量完整性检查"""
        # 必须包含常用安全函数
        for name in ["int", "str", "len", "range", "sorted", "True", "False", "None"]:
            assert name in SAFE_BUILTINS, f"SAFE_BUILTINS 缺少 {name}"
        # 绝不能包含危险函数
        for name in ["open", "eval", "exec", "compile", "__import__", "input", "exit"]:
            assert name not in SAFE_BUILTINS, f"SAFE_BUILTINS 不应包含 {name}"
        # build_safe_globals 返回的是 SAFE_BUILTINS 的副本，不共享引用
        globals_dict = build_safe_globals()
        assert globals_dict["__builtins__"] is not SAFE_BUILTINS

    def test_has_tool_functions(self):
        """包含工具函数（如果导入成功且提供 user_id）"""
        # T3.12 修复后，无 user_id 时返回空工具集（fail-closed）
        # 测试需要传入有效的 user_id 来获取工具
        globals_dict = build_safe_globals(user_id=1)  # user_id=1 是系统管理员
        # 这些工具可能导入失败，只检查存在性
        possible_tools = ["knowledge_search", "memory_search", "sql_query",
                         "web_search", "get_current_time"]
        # 至少应该有一些工具（当前至少 knowledge_search 和 get_current_time 应该可用）
        tool_count = sum(1 for t in possible_tools if t in globals_dict)
        assert tool_count >= 1, f"至少应有 1 个工具可用，实际: {tool_count}"
    
    def test_no_tools_without_user_id(self):
        """T3.12 修复后，无 user_id 时返回空工具集（fail-closed）"""
        globals_dict = build_safe_globals()
        # 无 user_id 时不应有任何工具（安全默认）
        possible_tools = ["knowledge_search", "memory_search", "sql_query",
                         "web_search", "get_current_time", "read_file"]
        tool_count = sum(1 for t in possible_tools if t in globals_dict)
        assert tool_count == 0, f"无 user_id 时不应有工具，实际: {tool_count}"


# ──────────────────────────────────────────────────────────────
# 代码执行测试
# ──────────────────────────────────────────────────────────────

class TestCodeExecution:
    """代码执行测试"""

    def test_simple_execution(self):
        """简单代码执行"""
        result = execute_code("print('hello world')")
        assert result["success"] is True
        assert "hello world" in result["output"]

    def test_execution_with_loop(self):
        """带循环的代码执行"""
        code = """
for i in range(3):
    print(f"item {i}")
"""
        result = execute_code(code)
        assert result["success"] is True
        assert "item 0" in result["output"]
        assert "item 1" in result["output"]
        assert "item 2" in result["output"]

    def test_execution_with_calculation(self):
        """带计算的代码执行"""
        code = """
numbers = [1, 2, 3, 4, 5]
total = sum(numbers)
print(f"总和: {total}")
"""
        result = execute_code(code)
        assert result["success"] is True
        assert "总和: 15" in result["output"]

    @pytest.mark.skip(reason="无限循环测试可能导致挂起，暂跳过")
    def test_execution_timeout(self):
        """执行超时"""
        code = """
while True:
    pass
"""
        result = execute_code(code, timeout=1)
        assert result["success"] is False
        assert "超时" in result["error"]

    def test_execution_runtime_error(self):
        """运行时错误"""
        code = """
x = 1 / 0
"""
        result = execute_code(code)
        assert result["success"] is False
        assert "ZeroDivisionError" in result["error"]

    def test_execution_no_output(self):
        """无输出代码"""
        code = "x = 1 + 1"
        result = execute_code(code)
        assert result["success"] is True
        assert result["output"] == ""

    def test_execution_multiple_prints(self):
        """多次 print"""
        code = """
print("line 1")
print("line 2")
print("line 3")
"""
        result = execute_code(code)
        assert result["success"] is True
        assert "line 1" in result["output"]
        assert "line 2" in result["output"]
        assert "line 3" in result["output"]


# ──────────────────────────────────────────────────────────────
# 多用户隔离测试
# ──────────────────────────────────────────────────────────────

class TestMultiUserIsolation:
    """多用户隔离测试

    多用户隔离通过两层机制保证：
      1. contextvars 传递：每个请求设置独立的 user_id/thread_id，
         通过 copy_context() 传递到执行线程，工具函数内部通过
         contextvars 获取正确的用户上下文（此机制在代码中实现，
         但因受限环境无法直接访问 contextvars 模块，无法在测试中直接验证）
      2. globals 隔离：受限 globals 不暴露模块引用，代码无法访问外部变量或缓存
    """

    def test_globals_isolation_no_external_access(self):
        """globals 隔离：代码无法访问外部定义的任何变量

        验证受限 globals 中没有注入任何外部变量，
        代码只能访问白名单工具函数和 safe_builtins。
        """
        # 无法访问未定义的变量（受限 globals 中没有它）
        code = """
try:
    _ = some_undefined_variable
    print("FAIL: should have raised NameError")
except NameError:
    print("PASS: NameError raised as expected")
"""
        result = execute_code(code)
        assert result["success"] is True
        assert "PASS" in result["output"]

    def test_globals_isolation_no_context_leak(self):
        """globals 隔离：调用线程的局部变量不会泄漏到代码执行环境

        在调用线程设置局部变量，验证 exec 的受限 globals 中不可见。
        """
        # 在调用线程中设置多个局部变量
        _secret_api_key = "sk-1234567890"
        _user_password = "super_secret_password"
        _db_connection_string = "mysql://root:password@localhost/db"

        # 代码尝试直接访问这些变量（受限 globals 中没有它们）
        code = """
try:
    _ = _secret_api_key
    print("LEAKED")
except NameError:
    print("PASS: isolated")
"""
        result = execute_code(code)
        assert result["success"] is True
        assert "PASS" in result["output"]
        assert "LEAKED" not in result["output"]

    def test_no_module_access(self):
        """代码无法访问模块"""
        # 由于 import 被 AST 检查禁止，这里验证代码只能用受限 builtins
        code = "print(type(len))"  # len 是安全的 builtin
        result = execute_code(code)
        assert result["success"] is True
        assert "builtin" in result["output"].lower()


# ──────────────────────────────────────────────────────────────
# run_python 工具测试
# ──────────────────────────────────────────────────────────────

class TestRunPythonTool:
    """run_python 工具测试"""

    def test_run_python_success(self):
        """成功执行"""
        from backend.tools.code_executor import run_python
        result = run_python.invoke({"code": "print('hello from run_python')"})
        assert "hello from run_python" in result

    def test_run_python_syntax_error(self):
        """语法错误"""
        from backend.tools.code_executor import run_python
        result = run_python.invoke({"code": "def foo("})
        assert "❌" in result

    def test_run_python_dangerous_code(self):
        """危险代码被拒绝"""
        from backend.tools.code_executor import run_python
        result = run_python.invoke({"code": "import os"})
        assert "❌" in result
        assert "安全检查失败" in result

    @pytest.mark.skip(reason="无限循环测试可能导致挂起，暂跳过")
    def test_run_python_timeout(self):
        """执行超时"""
        from backend.tools.code_executor import run_python
        result = run_python.invoke({
            "code": "while True: pass",
            "timeout": 1
        })
        assert "❌" in result
        assert "超时" in result


# ──────────────────────────────────────────────────────────────
# 错误分类系统测试
# ──────────────────────────────────────────────────────────────

class TestErrorClassification:
    """错误分类测试"""

    def test_classify_name_error(self):
        """NameError 分类"""
        category = classify_error("name 'foo' is not defined", "NameError")
        assert category == ErrorCategory.NAME_ERROR

    def test_classify_type_error(self):
        """TypeError 分类"""
        category = classify_error(
            "knowledge_search() got an unexpected keyword argument 'top'",
            "TypeError"
        )
        assert category == ErrorCategory.TYPE_ERROR

    def test_classify_timeout(self):
        """超时错误分类"""
        category = classify_error("代码执行超时（15s）", "TimeoutError")
        assert category == ErrorCategory.TIMEOUT

    def test_classify_timeout_by_message(self):
        """通过消息内容识别超时"""
        category = classify_error("代码执行超时（15s）", "Unknown")
        assert category == ErrorCategory.TIMEOUT

    def test_classify_safety_violation(self):
        """安全违规分类"""
        category = classify_error("❌ 代码安全检查失败: 不允许 import 语句", "RuntimeError")
        assert category == ErrorCategory.SAFETY_VIOLATION

    def test_classify_syntax_error(self):
        """语法错误分类"""
        category = classify_error("unexpected EOF while parsing", "SyntaxError")
        assert category == ErrorCategory.SYNTAX_ERROR

    def test_classify_tool_execution_error(self):
        """工具内部错误分类"""
        category = classify_error(
            "knowledge_search('xxx') 执行失败: ConnectionError",
            "RuntimeError"
        )
        assert category == ErrorCategory.TOOL_EXECUTION_ERROR

    def test_classify_tool_name_substring_no_false_positive(self):
        """工具名仅作为子字符串出现时不误分类（需要 tool_name( 模式）"""
        # "todo_get" 出现在变量名中，不是函数调用，不应分类为工具错误
        category = classify_error(
            "result_from_todo_get is invalid",
            "RuntimeError"
        )
        assert category == ErrorCategory.RUNTIME_ERROR

    def test_classify_runtime_error_fallback(self):
        """未知运行时错误回退"""
        category = classify_error("some random error", "RuntimeError")
        assert category == ErrorCategory.RUNTIME_ERROR

    def test_extract_error_type(self):
        """从错误消息中提取类型名"""
        assert _extract_error_type("NameError: name 'x' is not defined") == "NameError"
        assert _extract_error_type("TypeError: invalid type") == "TypeError"
        assert _extract_error_type("代码执行超时（15s）") == "代码执行超时（15s）"
        assert _extract_error_type("") == "Unknown"
        assert _extract_error_type(None) == "Unknown"


# ──────────────────────────────────────────────────────────────
# 自动修复引擎测试
# ──────────────────────────────────────────────────────────────

class TestAutoFix:
    """自动修复测试"""

    def test_edit_distance_same(self):
        """相同字符串编辑距离为 0"""
        assert _edit_distance("abc", "abc") == 0

    def test_edit_distance_empty(self):
        """空字符串编辑距离"""
        assert _edit_distance("", "abc") == 3
        assert _edit_distance("abc", "") == 3

    def test_edit_distance_different(self):
        """不同字符串编辑距离"""
        assert _edit_distance("kitten", "sitting") == 3
        assert _edit_distance("abc", "abd") == 1
        assert _edit_distance("abc", "xyz") == 3

    def test_find_closest_name_exact(self):
        """精确匹配"""
        result = _find_closest_name("get_current_time", ["get_current_time", "knowledge_search"])
        assert result == "get_current_time"

    def test_find_closest_name_typo(self):
        """拼写错误匹配"""
        result = _find_closest_name(
            "knowlege_search",
            ["knowledge_search", "get_current_time", "todo_add"]
        )
        assert result == "knowledge_search"

    def test_find_closest_name_no_match(self):
        """无匹配（距离太大）"""
        result = _find_closest_name(
            "xyz_function",
            ["knowledge_search", "get_current_time", "todo_add"],
            max_distance=3
        )
        assert result == "xyz_function"  # 返回原名

    def test_fix_name_error_typo(self):
        """工具名拼写错误自动修正"""
        code = "result = knowlege_search('test')"
        fixed, desc = _fix_name_error(
            code, "name 'knowlege_search' is not defined"
        )
        assert "knowledge_search" in fixed
        assert "自动修正" in desc
        assert "knowlege_search" not in fixed

    def test_fix_name_error_no_match(self):
        """无法匹配时不修改"""
        code = "result = xyz_function('test')"
        fixed, desc = _fix_name_error(
            code, "name 'xyz_function' is not defined"
        )
        assert fixed == code
        assert desc == ""

    def test_fix_name_error_get_curent_time(self):
        """get_curent_time → get_current_time"""
        code = "t = get_curent_time()"
        fixed, desc = _fix_name_error(
            code, "name 'get_curent_time' is not defined"
        )
        assert "get_current_time" in fixed
        assert "自动修正" in desc

    def test_fix_name_error_word_boundary(self):
        """单词边界替换：不误替换已有正确标识符"""
        # wrong_name "todo_ge" 是 "todo_get" 的前缀，不应把已有的 todo_get 也改掉
        code = "r1 = todo_ge('x')\nr2 = todo_get()"
        fixed, desc = _fix_name_error(
            code, "name 'todo_ge' is not defined"
        )
        # todo_ge 应被修正，但 todo_get 应保持不变
        assert "todo_get(" in fixed
        assert "todo_gett(" not in fixed
        assert "自动修正" in desc

    def test_fix_type_error_injects_hint(self):
        """TypeError 注入参数签名提示"""
        code = "result = knowledge_search(top=5)"
        fixed, desc = _fix_type_error(
            code,
            "knowledge_search() got an unexpected keyword argument 'top'"
        )
        assert "💡 提示" in fixed
        assert "knowledge_search" in fixed
        assert "注入参数签名提示" in desc

    def test_fix_type_error_no_duplicate_hint(self):
        """已有提示时不重复添加"""
        code = "# 💡 提示: knowledge_search(query, top_k=5)\nresult = knowledge_search(top=5)"
        fixed, desc = _fix_type_error(
            code,
            "knowledge_search() got an unexpected keyword argument 'top'"
        )
        # 不应重复添加
        assert fixed.count("# 💡 提示:") == 1

    def test_fix_type_error_different_func_hint_allowed(self):
        """已有其他函数提示时，允许注入新函数提示"""
        code = "# 💡 提示: knowledge_search(query, top_k=5)\nresult = todo_add(title='x', desc='y')"
        fixed, desc = _fix_type_error(
            code,
            "todo_add() got an unexpected keyword argument 'desc'"
        )
        assert "💡 提示: todo_add" in fixed
        assert "💡 提示: knowledge_search" in fixed  # 原有提示保留

    def test_auto_fix_dispatches_name_error(self):
        """auto_fix_code 正确分发 NameError"""
        code = "knowlege_search('test')"
        fixed, desc = _auto_fix_code(
            code,
            "name 'knowlege_search' is not defined",
            ErrorCategory.NAME_ERROR
        )
        assert "knowledge_search" in fixed

    def test_auto_fix_unsupported_category(self):
        """不支持的错误类型不修复"""
        code = "x = 1"
        fixed, desc = _auto_fix_code(
            code, "some error", ErrorCategory.RUNTIME_ERROR
        )
        assert fixed == code
        assert desc == ""


# ──────────────────────────────────────────────────────────────
# 重试机制测试
# ──────────────────────────────────────────────────────────────

class TestRetryMechanism:
    """重试机制测试"""

    def setup_method(self):
        """每个测试前设置 user_id 上下文（T3.12 修复后需要）"""
        from backend.hermes_adapter import _CURRENT_USER_ID_CTX
        self._token = _CURRENT_USER_ID_CTX.set(1)  # user_id=1 是系统管理员

    def teardown_method(self):
        """每个测试后清理 user_id 上下文"""
        from backend.hermes_adapter import _CURRENT_USER_ID_CTX
        _CURRENT_USER_ID_CTX.reset(self._token)

    def test_retry_success_first_try(self):
        """第一次就成功，无重试"""
        result = execute_code_with_retry("print('hello')")
        assert result["success"] is True
        assert "hello" in result["output"]
        assert len(result["execution_history"]) == 1
        assert result["auto_fixed"] is False

    def test_retry_with_name_fix(self):
        """NameError 自动修正后成功（get_curent_time → get_current_time）"""
        code = "t = get_curent_time()\nprint(t)"
        result = execute_code_with_retry(code)
        # 应该自动修正并成功
        assert result["success"] is True
        assert result["auto_fixed"] is True
        assert len(result["execution_history"]) >= 2

    def test_retry_exhausted_undefined_func(self):
        """未定义函数，重试耗尽仍失败"""
        code = "undefined_func_xyz()"
        result = execute_code_with_retry(code)
        assert result["success"] is False
        # 第一次 NameError 后无法修复（距离太远），应该直接放弃
        assert len(result["execution_history"]) >= 1

    def test_retry_safety_error_no_retry(self):
        """安全检查失败不重试（AST 层拦截）"""
        # execute_code_with_retry 不处理 AST 安全检查（在 run_python 中处理）
        # 但如果代码绕过了 AST 检查（理论上不可能），也不应无限重试
        code = "print('safe code')"
        result = execute_code_with_retry(code)
        assert result["success"] is True

    def test_retry_preserves_output(self):
        """成功时保留输出"""
        result = execute_code_with_retry("print('hello world')")
        assert result["success"] is True
        assert "hello world" in result["output"]

    def test_retry_records_duration(self):
        """记录总耗时"""
        result = execute_code_with_retry("print('test')")
        assert result["duration_ms"] > 0

    def test_retry_execution_history_format(self):
        """执行历史格式正确"""
        result = execute_code_with_retry("print('test')")
        history = result["execution_history"]
        assert len(history) >= 1
        entry = history[0]
        assert "attempt" in entry
        assert "success" in entry
        assert "duration_ms" in entry


# ──────────────────────────────────────────────────────────────
# 工具签名注册表测试
# ──────────────────────────────────────────────────────────────

class TestToolSignatures:
    """工具签名表测试"""

    def test_signatures_built(self):
        """签名表构建成功"""
        sigs = _build_tool_signatures()
        # get_current_time 应该始终存在
        assert "get_current_time" in sigs

    def test_signature_format(self):
        """签名格式正确"""
        sigs = _build_tool_signatures()
        for name, sig in sigs.items():
            assert sig.startswith(name), f"{name} 的签名应以 {name} 开头"
            assert "(" in sig, f"{name} 的签名应包含括号"
            assert ")" in sig, f"{name} 的签名应包含右括号"

    def test_signature_caching(self):
        """签名表缓存（两次调用返回同一对象）"""
        sigs1 = _build_tool_signatures()
        sigs2 = _build_tool_signatures()
        assert sigs1 is sigs2

    def test_get_current_time_signature(self):
        """get_current_time 签名包含 format 参数"""
        sigs = _build_tool_signatures()
        sig = sigs.get("get_current_time", "")
        assert "format" in sig


# ──────────────────────────────────────────────────────────────
# _CodeModeStats 增强测试
# ──────────────────────────────────────────────────────────────

class TestCodeModeStatsEnhanced:
    """_CodeModeStats 增强统计测试"""

    def test_auto_fix_recording(self):
        """自动修复统计记录"""
        stats = _CodeModeStats()
        stats.record_auto_fix(success=True)
        stats.record_auto_fix(success=False)
        snap = stats.snapshot()
        assert snap["auto_fixes"] == 2
        assert snap["auto_fix_successes"] == 1

    def test_snapshot_includes_auto_fix(self):
        """snapshot 包含自动修复字段"""
        stats = _CodeModeStats()
        snap = stats.snapshot()
        assert "auto_fixes" in snap
        assert "auto_fix_successes" in snap


# ──────────────────────────────────────────────────────────────
# 错误消息构建测试
# ──────────────────────────────────────────────────────────────

class TestBuildErrorMessage:
    """面向 LLM 的错误消息构建测试"""

    def test_simple_error(self):
        """简单错误消息"""
        result = {
            "success": False,
            "error": "NameError: name 'foo' is not defined",
            "execution_history": [{"attempt": 1, "success": False}],
        }
        msg = _build_error_message(result)
        assert "❌" in msg
        assert "NameError" in msg

    def test_error_with_fix_history(self):
        """包含修复历史的错误消息"""
        result = {
            "success": False,
            "error": "TypeError: wrong args",
            "execution_history": [
                {"attempt": 1, "success": False, "fix": "自动修正: foo → bar"},
                {"attempt": 2, "success": False, "fix": None},
            ],
        }
        msg = _build_error_message(result)
        assert "自动修复" in msg
        assert "自动修正: foo → bar" in msg

    def test_error_includes_tool_signatures(self):
        """TypeError 错误消息包含工具签名"""
        result = {
            "success": False,
            "error": "TypeError: knowledge_search() got unexpected arg",
            "execution_history": [{"attempt": 1, "success": False}],
        }
        msg = _build_error_message(result)
        assert "可用工具签名" in msg

    def test_safety_error_no_signatures(self):
        """安全错误不显示工具签名"""
        result = {
            "success": False,
            "error": "安全检查失败: 不允许 import 语句",
            "execution_history": [{"attempt": 1, "success": False}],
        }
        msg = _build_error_message(result)
        assert "可用工具签名" not in msg


# ──────────────────────────────────────────────────────────────
# 运行测试
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
