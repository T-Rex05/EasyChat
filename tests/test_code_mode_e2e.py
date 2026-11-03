"""
Code Mode 文件操作端到端测试

测试场景：模拟用户询问"查看 code mode 的实现"，
验证 Hermes 是否会使用 run_python + read_file 来读取代码。
"""

import sys
import os
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_code_mode_integration():
    """测试 Code Mode 文件操作集成"""
    print("=" * 80)
    print("Code Mode 文件操作端到端测试")
    print("=" * 80)

    # 1. 验证工具已注册
    print("\n[步骤 1] 验证文件操作工具已注册到 Code Mode...")
    from backend.tools.code_executor import _get_tool_functions

    tools = _get_tool_functions()
    tool_names = list(tools.keys())

    print(f"已注册的工具: {', '.join(tool_names)}")

    if 'read_file' in tools and 'search_files' in tools:
        print("[PASS] read_file 和 search_files 已注册")
    else:
        print("[FAIL] 文件操作工具未注册")
        return False

    # 2. 验证工具签名
    print("\n[步骤 2] 验证工具签名...")
    from backend.tools.code_executor import _build_tool_signatures

    signatures = _build_tool_signatures()
    print(f"read_file 签名: {signatures.get('read_file', '未找到')}")
    print(f"search_files 签名: {signatures.get('search_files', '未找到')}")

    if 'read_file' in signatures and 'search_files' in signatures:
        print("[PASS] 工具签名正确")
    else:
        print("[FAIL] 工具签名缺失")
        return False

    # 3. 测试实际文件读取
    print("\n[步骤 3] 测试实际文件读取...")
    from backend.tools.code_executor import code_mode_read_file

    try:
        # 读取 code_executor.py 的前 30 行
        result = code_mode_read_file(
            "backend/tools/code_executor.py",
            offset=1,
            limit=30
        )

        # 验证返回内容
        if "Code Mode" in result and "行" in result:
            print("[PASS] 文件读取成功")
            print(f"返回内容长度: {len(result)} 字符")
        else:
            print("[FAIL] 文件读取结果异常")
            return False

    except Exception as e:
        print(f"[FAIL] 文件读取失败: {e}")
        return False

    # 4. 测试实际文件搜索
    print("\n[步骤 4] 测试实际文件搜索...")
    from backend.tools.code_executor import code_mode_search_files

    try:
        # 搜索包含 "def code_mode" 的文件
        result = code_mode_search_files(
            pattern="def code_mode",
            target="content",
            file_glob="*.py",
            limit=5
        )

        if "code_executor.py" in result:
            print("[PASS] 文件搜索成功")
            print(f"找到匹配数: {result.count('code_executor.py')}")
        else:
            print("[FAIL] 文件搜索结果异常")
            return False

    except Exception as e:
        print(f"[FAIL] 文件搜索失败: {e}")
        return False

    # 5. 测试安全检查
    print("\n[步骤 5] 测试安全检查...")
    from backend.tools.code_executor import FileOperationError

    security_tests = [
        ("../../Windows/System32/config/SAM", "路径遍历"),
        (".git/config", "禁止目录"),
        ("node_modules/package.json", "禁止目录"),
    ]

    all_passed = True
    for path, test_name in security_tests:
        try:
            code_mode_read_file(path)
            print(f"  [FAIL] {test_name}: 应该拒绝但通过了")
            all_passed = False
        except FileOperationError:
            print(f"  [PASS] {test_name}: 正确拦截")
        except Exception as e:
            print(f"  [WARN] {test_name}: 意外错误 - {e}")
            all_passed = False

    if not all_passed:
        return False

    # 6. 测试 run_python 集成
    print("\n[步骤 6] 测试 run_python 集成...")
    from backend.tools.code_executor import execute_code_with_retry

    test_code = """
# 测试在 Code Mode 中使用文件操作
content = read_file("backend/tools/code_executor.py", offset=1, limit=10)
print(f"读取成功，内容长度: {len(content)}")

results = search_files("*.py", target="files", path="backend/tools", limit=5)
print(f"搜索成功，结果: {results[:100]}...")
"""

    result = execute_code_with_retry(test_code, timeout=15)

    if result["success"]:
        print("[PASS] run_python 集成成功")
        print(f"输出: {result['output'][:200]}")
    else:
        print(f"[FAIL] run_python 集成失败: {result['error']}")
        return False

    # 7. 验证提示词更新
    print("\n[步骤 7] 验证提示词已更新...")
    from backend.agents.prompts import get_decision_system_prompt

    prompt = get_decision_system_prompt(available_tools=["read_file", "search_files"])

    if "read_file" in prompt and "search_files" in prompt:
        print("[PASS] 提示词已包含文件操作工具说明")
    else:
        print("[WARN] 提示词可能未更新（这不一定是错误）")

    print("\n" + "=" * 80)
    print("[PASS] 所有测试通过！Code Mode 文件操作功能已就绪")
    print("=" * 80)

    return True


def test_performance_comparison():
    """对比测试：传统方式 vs Code Mode"""
    print("\n" + "=" * 80)
    print("性能对比测试：传统工具调用 vs Code Mode")
    print("=" * 80)

    import time
    from backend.tools.code_executor import code_mode_read_file, execute_code_with_retry

    # 场景：读取 4 个文件
    files_to_read = [
        "backend/tools/code_executor.py",
        "backend/tools/tools_decorator.py",
        "backend/tools/text_to_sql.py",
        "backend/tools/data_visualization.py",
    ]

    # 方式 1：模拟传统方式（逐个读取，每次返回完整内容）
    print("\n[方式 1] 模拟传统工具调用（4 次单独调用）...")
    start = time.time()
    traditional_tokens = 0
    for file_path in files_to_read:
        result = code_mode_read_file(file_path, limit=50)
        traditional_tokens += len(result)
    traditional_time = time.time() - start

    print(f"  总输出: {traditional_tokens} 字符")
    print(f"  耗时: {traditional_time:.3f} 秒")
    print(f"  估算 Token: ~{traditional_tokens // 4} tokens")

    # 方式 2：Code Mode（1 次 run_python）
    print("\n[方式 2] Code Mode（1 次 run_python）...")
    code_mode_code = """
files = [
    "backend/tools/code_executor.py",
    "backend/tools/tools_decorator.py",
    "backend/tools/text_to_sql.py",
    "backend/tools/data_visualization.py",
]

total_output = 0
for f in files:
    content = read_file(f, limit=50)
    # 只输出摘要，不输出完整内容
    summary = f"文件: {f}, 长度: {len(content)} 字符"
    print(summary)
    total_output += len(summary)

print(f"\\n总计输出: {total_output} 字符")
"""

    start = time.time()
    result = execute_code_with_retry(code_mode_code, timeout=15)
    code_mode_time = time.time() - start

    if result["success"]:
        code_mode_output = result["output"]
        code_mode_chars = len(code_mode_output)

        print(f"  总输出: {code_mode_chars} 字符")
        print(f"  耗时: {code_mode_time:.3f} 秒")
        print(f"  估算 Token: ~{code_mode_chars // 4} tokens")

        # 计算节省
        token_savings = (traditional_tokens - code_mode_chars) / traditional_tokens * 100
        time_savings = (traditional_time - code_mode_time) / traditional_time * 100

        print("\n[对比结果]")
        print(f"  Token 节省: {token_savings:.1f}%")
        print(f"  时间节省: {max(0, time_savings):.1f}%")
        print(f"  工具调用次数: 4 → 1 (减少 75%)")

        return True
    else:
        print(f"  [FAIL] Code Mode 执行失败: {result['error']}")
        return False


def main():
    """运行所有测试"""
    print("\n")

    # 测试 1：集成测试
    success1 = test_code_mode_integration()

    # 测试 2：性能对比
    success2 = test_performance_comparison()

    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    if success1 and success2:
        print("[PASS] 所有测试通过！")
        print("\n下一步：")
        print("1. 重启 FastAPI 服务")
        print("2. 在前端发送消息：'查看 code mode 的实现'")
        print("3. 观察 Hermes 是否使用 run_python + read_file")
        return 0
    else:
        print("[FAIL] 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
