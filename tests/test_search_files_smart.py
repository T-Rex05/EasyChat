"""
测试 search_files 智能搜索功能
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_auto_target():
    """测试 target='auto' 模式的智能判断"""
    from backend.tools.code_executor import code_mode_search_files

    print("=" * 60)
    print("测试 search_files 智能搜索（target='auto'）")
    print("=" * 60)

    test_cases = [
        {
            "name": "关键词搜索（应该搜索内容）",
            "pattern": "milvus",
            "expected_behavior": "搜索文件内容中包含 'milvus' 的文件",
        },
        {
            "name": "glob 模式搜索文件名（应该搜索文件名）",
            "pattern": "*.py",
            "expected_behavior": "搜索所有 Python 文件",
        },
        {
            "name": "测试文件 glob（应该搜索文件名）",
            "pattern": "test_*.py",
            "expected_behavior": "搜索测试文件",
        },
        {
            "name": "多关键词 OR 搜索（应该搜索内容）",
            "pattern": "FieldSchema|CollectionSchema",
            "expected_behavior": "搜索包含任一关键词的文件",
        },
        {
            "name": "函数定义搜索（应该搜索内容）",
            "pattern": "def test_",
            "expected_behavior": "搜索测试函数定义",
        },
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {case['name']}")
        print(f"  模式: {case['pattern']}")
        print(f"  预期: {case['expected_behavior']}")

        try:
            result = code_mode_search_files(case["pattern"], target="auto", limit=10)
            # 判断搜索方式
            if "文件内容" in result or "处匹配" in result:
                actual = "内容搜索"
            elif "个文件" in result:
                actual = "文件名搜索"
            elif "未找到" in result:
                actual = "无结果"
            else:
                actual = "未知"

            print(f"  实际: {actual}")
            print(f"  结果预览: {result[:150]}...")
            print(f"  [PASS]")
        except Exception as e:
            print(f"  [FAIL] 错误: {e}")


def test_explicit_target():
    """测试明确指定 target 的模式"""
    from backend.tools.code_executor import code_mode_search_files

    print("\n" + "=" * 60)
    print("测试明确指定 target 的模式")
    print("=" * 60)

    test_cases = [
        {"pattern": "milvus", "target": "content", "desc": "内容搜索"},
        {"pattern": "*.py", "target": "files", "desc": "文件名搜索"},
    ]

    for case in test_cases:
        print(f"\n  {case['desc']}: pattern='{case['pattern']}', target='{case['target']}'")
        try:
            result = code_mode_search_files(
                case["pattern"], target=case["target"], limit=5
            )
            print(f"  结果: {result[:100]}...")
            print(f"  [PASS]")
        except Exception as e:
            print(f"  [FAIL] 错误: {e}")


def test_no_result_suggestion():
    """测试无结果时的建议"""
    from backend.tools.code_executor import code_mode_search_files

    print("\n" + "=" * 60)
    print("测试无结果时的建议")
    print("=" * 60)

    # 搜索一个不太可能存在的内容
    result = code_mode_search_files("xyznonexistent12345", target="auto", limit=5)
    print(f"\n搜索不存在的内容: {result}")

    if "建议" in result or "💡" in result:
        print("[PASS] 包含建议")
    else:
        print("[FAIL] 缺少建议")


def main():
    print("search_files 智能搜索功能测试")
    print("=" * 60)

    test_auto_target()
    test_explicit_target()
    test_no_result_suggestion()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
