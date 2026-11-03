"""
Code Mode 文件操作工具测试脚本

测试内容：
1. read_file 基本功能
2. search_files 基本功能
3. 安全检查（路径遍历、目录限制）
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.tools.code_executor import (
    code_mode_read_file,
    code_mode_search_files,
    FileOperationError,
)


def test_read_file_basic():
    """测试 read_file 基本功能"""
    print("=" * 60)
    print("测试 1: read_file 基本功能")
    print("=" * 60)

    try:
        # 读取当前文件
        result = code_mode_read_file("backend/tools/code_executor.py", offset=1, limit=50)
        print(result)
        print("\n[PASS] read_file 正常工作")
        return True
    except Exception as e:
        print(f"\n[FAIL] read_file 失败: {e}")
        return False


def test_search_files_content():
    """测试 search_files 内容搜索"""
    print("\n" + "=" * 60)
    print("测试 2: search_files 内容搜索")
    print("=" * 60)

    try:
        # 搜索包含 "def test" 的 Python 文件
        result = code_mode_search_files(
            pattern="def test",
            target="content",
            path="tests",
            file_glob="*.py",
            limit=10
        )
        print(result)
        print("\n[PASS] search_files 内容搜索正常工作")
        return True
    except Exception as e:
        print(f"\n[FAIL] search_files 内容搜索失败: {e}")
        return False


def test_search_files_name():
    """测试 search_files 文件名搜索"""
    print("\n" + "=" * 60)
    print("测试 3: search_files 文件名搜索")
    print("=" * 60)

    try:
        # 搜索所有 Python 文件
        result = code_mode_search_files(
            pattern="*.py",
            target="files",
            path="backend/tools",
            limit=20
        )
        print(result)
        print("\n[PASS] search_files 文件名搜索正常工作")
        return True
    except Exception as e:
        print(f"\n[FAIL] search_files 文件名搜索失败: {e}")
        return False


def test_path_traversal():
    """测试路径遍历防护"""
    print("\n" + "=" * 60)
    print("测试 4: 路径遍历防护")
    print("=" * 60)

    try:
        # 尝试访问项目目录外的文件
        result = code_mode_read_file("../../Windows/System32/config/SAM")
        print(f"\n[FAIL] 安全检查失败：应该拒绝访问，但返回了:\n{result}")
        return False
    except FileOperationError as e:
        print(f"[PASS] 正确拦截了路径遍历攻击: {e}")
        return True
    except Exception as e:
        print(f"[FAIL] 意外的错误: {e}")
        return False


def test_blocked_directory():
    """测试禁止目录访问"""
    print("\n" + "=" * 60)
    print("测试 5: 禁止目录访问")
    print("=" * 60)

    try:
        # 尝试访问 .git 目录
        result = code_mode_read_file(".git/config")
        print(f"\n[FAIL] 安全检查失败：应该拒绝访问 .git，但返回了:\n{result}")
        return False
    except FileOperationError as e:
        print(f"[PASS] 正确拦截了对 .git 的访问: {e}")
        return True
    except Exception as e:
        print(f"[FAIL] 意外的错误: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Code Mode 文件操作工具测试")
    print("=" * 60)

    tests = [
        test_read_file_basic,
        test_search_files_content,
        test_search_files_name,
        test_path_traversal,
        test_blocked_directory,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n[FAIL] 测试执行失败: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("\n[PASS] 所有测试通过！")
        return 0
    else:
        print(f"\n[FAIL] {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
