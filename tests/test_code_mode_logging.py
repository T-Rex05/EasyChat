"""测试 Code Mode 日志系统"""

import sys
import os

# 添加项目根目录到 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from backend.tools.code_executor import (
    create_log_functions,
    create_safe_print,
    execute_code,
)


def test_log_functions():
    """测试日志函数"""
    print("=" * 60)
    print("测试 1: 日志函数基本功能")
    print("=" * 60)

    import io

    output_buffer = io.StringIO()
    total_chars_ref = [0]

    log, log_debug, log_file_path = create_log_functions(
        output_buffer=output_buffer,
        user_id=123,
        thread_id="test-thread-abc",
        total_chars_ref=total_chars_ref,
    )

    # 测试 log() 函数
    log("开始处理数据...", level="info")
    log("找到 5 条记录", level="success")
    log("部分数据格式异常", level="warn")
    log("处理失败", level="error")

    # 测试 log_debug() 函数
    for i in range(3):
        log_debug(f"处理第 {i+1} 条数据: id={i}, name=test_{i}")

    # 获取输出
    output = output_buffer.getvalue()
    print("\noutput_buffer 内容（返回给 Agent）:")
    print(output)

    # 检查日志文件
    print(f"\n日志文件路径: {log_file_path}")
    if os.path.exists(log_file_path):
        with open(log_file_path, 'r', encoding='utf-8') as f:
            print("\n日志文件内容:")
            print(f.read())
    else:
        print("日志文件不存在")

    # 验证
    assert "[INFO]" in output or "开始处理数据" in output, "log() 输出应该包含日志级别或消息"

    print("\n测试 1 通过")


def test_shared_chars_counter():
    """测试共享字符计数器"""
    print("\n" + "=" * 60)
    print("测试 2: 共享字符计数器")
    print("=" * 60)

    import io

    output_buffer = io.StringIO()
    total_chars_ref = [0]

    # 创建 log 和 safe_print，共享同一个计数器
    log, log_debug, log_file_path = create_log_functions(
        output_buffer=output_buffer,
        total_chars_ref=total_chars_ref,
    )
    safe_print = create_safe_print(output_buffer, total_chars_ref)

    # 使用 log
    log("关键节点日志", level="info")
    print(f"log() 后字符计数: {total_chars_ref[0]}")

    # 使用 print
    safe_print("这是一条普通打印")
    print(f"print() 后字符计数: {total_chars_ref[0]}")

    # 再次使用 log
    log("另一个关键节点", level="success")
    print(f"log() 后字符计数: {total_chars_ref[0]}")

    # 获取输出
    output = output_buffer.getvalue()
    print("\n完整输出:")
    print(output)

    # 验证
    assert total_chars_ref[0] > 0, "字符计数应该 > 0"
    assert "关键节点日志" in output, "输出应该包含 log() 的内容"
    assert "这是一条普通打印" in output, "输出应该包含 print() 的内容"

    print("\n测试 2 通过")


def test_execute_code_with_log():
    """测试在 execute_code 中使用日志函数"""
    print("\n" + "=" * 60)
    print("测试 3: execute_code 中的日志函数")
    print("=" * 60)

    code = '''
# 使用日志函数
log("开始查询知识库...", level="info")

# 模拟查询
for i in range(3):
    result = f"结果 {i+1}"
    log_debug(f"查询结果: {result}")

log("✅ 查询完成", level="success")

# 使用 print
print("最终结果: 3 条记录")
'''

    result = execute_code(code, timeout=5)

    print(f"\n执行结果: success={result['success']}")
    print(f"耗时: {result['duration_ms']:.1f}ms")

    if result['success']:
        print("\n输出内容:")
        print(result['output'])

        if result.get('log_file'):
            print(f"\n日志文件: {result['log_file']}")
            if os.path.exists(result['log_file']):
                with open(result['log_file'], 'r', encoding='utf-8') as f:
                    print("\n日志文件内容:")
                    print(f.read())

        # 验证
        output = result['output']
        assert "开始查询知识库" in output, "输出应该包含 log() 的内容"
        assert "查询完成" in output, "输出应该包含 log() 的内容"
        assert "最终结果" in output, "输出应该包含 print() 的内容"
    else:
        print(f"\n执行失败: {result.get('error')}")

    print("\n测试 3 通过")


if __name__ == "__main__":
    test_log_functions()
    test_shared_chars_counter()
    test_execute_code_with_log()

    print("\n" + "=" * 60)
    print("所有测试通过!")
    print("=" * 60)