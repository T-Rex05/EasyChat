"""
命令注入防护验证函数

提供严格的命令白名单和参数验证，防止命令注入攻击
"""

import re
from typing import Tuple

# 危险命令模式（扩展）
DANGEROUS_PATTERNS = [
    r';',           # 命令分隔符
    r'&&',          # 逻辑与
    r'\|\|',        # 逻辑或
    r'`',           # 命令替换
    r'\$\(',        # 命令替换 $(...)
    r'\$\{',        # 变量替换 ${...}
    r'>',           # 输出重定向
    r'<',           # 输入重定向
    r'\|\s*\b',     # 管道符后跟命令
    r'#',           # 注释符（可能用于绕过检测）
    r'\.\./',       # 路径遍历
    r'~/',          # 家目录引用
]

# 允许的命令白名单（严格模式）
# 格式：(命令模式, 参数限制)
ALLOWED_COMMANDS = [
    # Python 脚本执行（限制路径格式）
    (r'^python\d?\s+[\w/\.]+\.py$', 'script_path'),

    # Pip 安装（限制包名格式）
    (r'^pip\s+install\s+[\w\-\._]+$', 'package_name'),
    (r'^pip\s+install\s+-r\s+[\w/\.]+\.txt$', 'requirements_file'),

    # Pytest（限制路径）
    (r'^pytest\s+[\w/\.]+$', 'test_path'),
    (r'^pytest$', 'no_args'),

    # Make（限制目标名）
    (r'^make\s+[\w]+$', 'target'),

    # 目录操作（限制路径格式）
    (r'^mkdir\s+[\w/\.]+$', 'dir_path'),

    # 禁用高风险命令：
    # - ls: 可能用于信息收集
    # - cat: 可能读取敏感文件
    # - echo: 可能用于绕过检测
    # - rm: 高风险
    # - touch: 可能用于文件操作攻击
]

def validate_command(command: str) -> Tuple[bool, str]:
    """
    验证命令安全性（严格模式）

    Args:
        command: 要执行的命令

    Returns:
        Tuple[bool, str]: (是否安全, 错误信息)

    检查流程：
        1. 基本验证（空值、类型）
        2. 危险模式检测
        3. 白名单匹配
        4. 参数格式验证
    """
    if not command or not isinstance(command, str):
        return False, "命令为空或格式错误"

    command = command.strip()

    # 1. 检查危险模式
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return False, f"命令包含危险字符: {pattern}"

    # 2. 检查命令白名单
    command_allowed = False
    matched_pattern = None

    for pattern, _ in ALLOWED_COMMANDS:
        if re.match(pattern, command):
            command_allowed = True
            matched_pattern = pattern
            break

    if not command_allowed:
        # 提取命令名（第一个词）
        cmd_name = command.split()[0] if command.split() else command
        return False, f"命令不在白名单中: {cmd_name}"

    # 3. 额外的参数验证
    # 防止白名单绕过（如 python script.py # rm -rf /）
    if '#' in command:
        return False, "命令包含注释符，可能是绕过尝试"

    # 检查路径遍历
    if '..' in command or '~' in command:
        return False, "命令包含路径遍历字符"

    return True, ""

def validate_file_id(file_id: str) -> tuple[bool, str]:
    """
    验证文件 ID 合法性

    Args:
        file_id: 文件标识符

    Returns:
        tuple[bool, str]: (是否合法, 错误信息)
    """
    if not file_id or not isinstance(file_id, str):
        return False, "file_id 为空或格式错误"

    # 只允许字母、数字、下划线、短横线
    if not re.match(r'^[a-zA-Z0-9_-]+$', file_id):
        return False, f"file_id 包含非法字符: {file_id}"

    # 检查路径遍历尝试
    if '..' in file_id or '/' in file_id or '\\' in file_id:
        return False, f"file_id 包含路径遍历字符: {file_id}"

    # 长度限制
    if len(file_id) > 255:
        return False, "file_id 长度超过限制"

    return True, ""


def sanitize_path(base_dir: str, file_path: str) -> str:
    """
    安全的路径拼接和验证

    Args:
        base_dir: 基础目录
        file_path: 文件路径

    Returns:
        str: 安全的绝对路径

    Raises:
        ValueError: 如果路径不合法
    """
    from pathlib import Path

    base = Path(base_dir).resolve()
    target = (base / file_path).resolve()

    # 验证路径在允许范围内
    if not str(target).startswith(str(base)):
        raise ValueError(f"路径遍历攻击: {file_path}")

    return str(target)


# 测试
if __name__ == "__main__":
    # 测试命令验证
    print("测试命令验证:")
    test_commands = [
        ("python main.py", True),
        ("pip install numpy", True),
        ("ls -la", True),
        ("rm -rf /", False),
        ("cat /etc/passwd; ls", False),
        ("python main.py && rm -rf /", False),
        ("$(whoami)", False),
    ]

    for cmd, expected in test_commands:
        is_safe, error = validate_command(cmd)
        result = "✅" if is_safe == expected else "❌"
        print(f"{result} {cmd[:30]:<30} -> {is_safe} ({error or 'OK'})")

    print("\n测试文件 ID 验证:")
    test_file_ids = [
        ("abc123", True),
        ("file-123", True),
        ("../../../etc/passwd", False),
        ("file;rm -rf", False),
        ("file$(whoami)", False),
    ]

    for file_id, expected in test_file_ids:
        is_valid, error = validate_file_id(file_id)
        result = "✅" if is_valid == expected else "❌"
        print(f"{result} {file_id:<30} -> {is_valid} ({error or 'OK'})")