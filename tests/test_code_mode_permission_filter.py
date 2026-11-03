"""
测试 Code Mode 权限过滤功能
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_tool_toolsets():
    """测试工具的 _toolset 属性记录"""
    from backend.tools.code_executor import _get_tool_functions, _get_tool_toolsets

    # 初始化工具
    tools = _get_tool_functions()
    toolsets = _get_tool_toolsets()

    print("=" * 60)
    print("测试 1: 工具的 _toolset 属性记录")
    print("=" * 60)

    print(f"\n共 {len(tools)} 个工具:")
    for name, toolset in sorted(toolsets.items()):
        print(f"  - {name}: {toolset}")

    # 验证关键工具的 _toolset
    expected = {
        "knowledge_search": "__always_available__",
        "sql_query": "__always_available__",
        "get_current_time": "__always_available__",
        "todo_add": "__always_available__",
        "todo_update": "__always_available__",
        "todo_get": "__always_available__",
        "cronjob_create": "schedule",
        "list_delivery_configs": "notification",
        "when_resolve": "__always_available__",
        "read_file": "file",
        "search_files": "file",
    }

    print("\n验证关键工具的 _toolset:")
    all_pass = True
    for name, expected_toolset in expected.items():
        actual = toolsets.get(name)
        if actual == expected_toolset:
            print(f"  [PASS] {name}: {actual}")
        else:
            print(f"  [FAIL] {name}: 期望 {expected_toolset}, 实际 {actual}")
            all_pass = False

    return all_pass


def test_permission_filter():
    """测试权限过滤功能"""
    from backend.tools.code_executor import build_safe_globals

    print("\n" + "=" * 60)
    print("测试 2: 权限过滤功能")
    print("=" * 60)

    # 模拟不同角色的用户
    test_cases = [
        {
            "user_id": None,
            "description": "无 user_id（不检查权限）",
            "expected_tools": ["cronjob_create", "read_file", "search_files"],  # 全量
        },
        {
            "user_id": 999,  # 假设不存在的用户，会返回空 toolset
            "description": "不存在的用户 (user_id=999)",
            "expected_tools": [],  # 只有 __always_available__ 的工具
            "unexpected_tools": ["cronjob_create", "read_file", "search_files"],
        },
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {case['description']}")

        # 注意：实际测试需要设置 _CURRENT_USER_ID_CTX
        # 这里只是验证 build_safe_globals 能正常调用
        try:
            globals_dict = build_safe_globals(user_id=case["user_id"])
            available_tools = [k for k in globals_dict.keys() if k != "__builtins__"]
            print(f"  可用工具: {len(available_tools)} 个")
            print(f"  工具列表: {sorted(available_tools)}")
        except Exception as e:
            print(f"  错误: {e}")

    print("\n注意: 完整的权限过滤测试需要:")
    print("  1. 设置 _CURRENT_USER_ID_CTX")
    print("  2. 在数据库中有对应用户和角色")
    print("  3. 重启服务后测试")


def test_role_toolsets():
    """测试不同角色的 toolset 分配"""
    from backend.permission.builtin import DEFAULT_ROLE_TOOLSETS

    print("\n" + "=" * 60)
    print("测试 3: 角色 toolset 分配")
    print("=" * 60)

    for role, toolsets in DEFAULT_ROLE_TOOLSETS.items():
        print(f"\n{role}: {toolsets}")

    print("\n权限过滤预期效果:")
    print("  - super_admin: 所有工具可用（包含 schedule, notification, file）")
    print("  - admin: 所有工具可用（包含 schedule, notification, file）")
    print("  - user: 只有 web 权限，无法使用 cronjob_create (schedule), read_file (file)")


def main():
    print("Code Mode 权限过滤功能测试")
    print("=" * 60)

    # 测试 1: 工具的 _toolset 属性记录
    if not test_tool_toolsets():
        print("\n测试 1 失败！")
        return 1

    # 测试 2: 权限过滤功能
    test_permission_filter()

    # 测试 3: 角色 toolset 分配
    test_role_toolsets()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n下一步:")
    print("  1. 重启 FastAPI 服务")
    print("  2. 使用 user 角色登录")
    print("  3. 尝试调用 cronjob_create() 或 read_file()")
    print("  4. 应该被权限过滤拦截")

    return 0


if __name__ == "__main__":
    sys.exit(main())
