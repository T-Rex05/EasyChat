"""
Code Mode 执行器 —— 让 Agent 写 Python 代码组合调用工具

解决的问题：
  传统 Tool Calling 模式下，每次工具调用都需要一轮 LLM 推理，
  复杂任务需要多轮对话，导致：
    1. Token 消耗高（每轮工具结果都进上下文）
    2. 延迟高（多轮 LLM 推理）
    3. 数据在上下文中堆积（大输出截断后信息丢失）

设计思路（参考 Claude Code / Cursor 的 Code Execution）：
  Agent 写 Python 代码来组合调用工具：
    1. 代码在同进程线程中执行（通过 copy_context 传递 contextvars）
    2. 受限 globals：只暴露白名单工具函数，不暴露模块引用
    3. AST 静态检查：禁止 import、eval、exec 等危险操作
    4. safe_print：捕获输出，带截断保护
    5. 只有 print() 的内容返回给 Agent，中间数据留在代码里

工程化增强：
  - _ToolWrapper：包装工具函数，提供内部调用次数统计 + 大输出（>50K）告警日志
  - _CodeModeStats：线程安全计数器，记录调用/成功/失败/安全检查拦截/内部工具调用
  - Trace span 集成：接入 trace_spans 表（span_type="code_mode"），可观测性面板可查
  - 结构化日志：agentforge.code_mode logger 便于日志采集系统解析
  - 线程池优化：8 worker + 15s 超时；worker 为 daemon（不阻塞进程退出），
    超时后退役重建池（跑飞的线程无法回收，但容量能恢复）
  - run_python 加入 BYPASS_TOOLS，避免与 safe_print 双重截断

多用户隔离保证：
  - contextvars 通过 copy_context() 传递到执行线程
  - 受限 globals 不暴露模块引用，代码无法访问其他用户数据
  - 工具函数内部通过 contextvars 获取正确的 user_id/thread_id
"""

import ast
import contextvars
import inspect
import io
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Tuple

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.context.tool_results.capture import OutputSink, get_capture_session

logger = logging.getLogger(__name__)

# Code Mode 专用日志（结构化，便于后续采集分析）
_code_mode_logger = logging.getLogger("agentforge.code_mode")

# ──────────────────────────────────────────────────────────────
# 配置常量
# ──────────────────────────────────────────────────────────────

# 单次 print 最大字符数（超出即截断）
MAX_SINGLE_PRINT = 16_000

# 总输出最大字符数（所有 print 累计）
MAX_TOTAL_OUTPUT = 32_000

# 默认执行超时时间（秒）
# 15 秒足够大多数工具组合调用，同时降低超时后线程 lingering 的风险
DEFAULT_TIMEOUT = 15

# 安全的内建函数白名单（替换默认的 __builtins__）
# 只包含类型转换、集合操作、数学运算、类型检查、字符串操作、异常类和常量
# 不包含 open/eval/exec/__import__/input 等危险函数
SAFE_BUILTINS = {
    # 类型转换
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "set": set, "tuple": tuple,
    # 集合操作
    "len": len, "range": range, "sorted": sorted,
    "reversed": reversed, "enumerate": enumerate,
    "zip": zip, "map": map, "filter": filter,
    # 数学运算
    "sum": sum, "max": max, "min": min,
    "abs": abs, "round": round, "pow": pow,
    # 类型检查
    "isinstance": isinstance, "issubclass": issubclass,
    "type": type,
    # 字符串操作
    "chr": chr, "ord": ord, "repr": repr, "hash": hash,
    "id": id, "iter": iter, "next": next,
    "slice": slice, "object": object,
    # 异常类
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "KeyError": KeyError,
    "IndexError": IndexError, "AttributeError": AttributeError,
    "RuntimeError": RuntimeError, "StopIteration": StopIteration,
    "NameError": NameError, "ZeroDivisionError": ZeroDivisionError,
    # 常量
    "True": True, "False": False, "None": None,
}

# 线程池（复用，避免每次创建）
# max_workers=8：支持 8 个并发 Code Mode 执行，降低线程池耗尽风险
_CODEX_MAX_WORKERS = 8
_POOL_LOCK = threading.Lock()


def _load_daemon_executor_cls():
    """返回 DaemonThreadPoolExecutor 类，取不到时返回 None。

    ⚠️ 必须**先按文件路径**加载，不要先试 `from tools.daemon_pool import ...`：
    `tools` 是个有歧义的名字（`backend/tools/` 与 `backend/hermes/tools/` 同名），
    包导入会把整个 Hermes `tools` 包在 `code_executor` 被 import 时就拉起来，
    **改变全局 import 顺序并触发其 `__init__` 的副作用**（实测：会让
    tests/test_skill_scope.py 的 7 个用例从通过变失败）。
    `daemon_pool.py` 只依赖 stdlib，按路径加载零副作用。
    """
    try:
        import importlib.util
        from pathlib import Path as _Path

        _p = _Path(__file__).resolve().parents[1] / "hermes" / "tools" / "daemon_pool.py"
        if _p.exists():
            _spec = importlib.util.spec_from_file_location("_agentforge_daemon_pool", _p)
            if _spec is not None and _spec.loader is not None:
                _mod = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                _cls = getattr(_mod, "DaemonThreadPoolExecutor", None)
                if _cls is not None:
                    return _cls
    except Exception as _e:
        logger.debug(f"按路径加载 daemon_pool 失败: {_e}")

    # 兜底：文件不在预期位置时才走包导入
    try:
        from tools.daemon_pool import DaemonThreadPoolExecutor  # noqa: F401

        return DaemonThreadPoolExecutor
    except Exception as _e:
        logger.debug(f"包导入 daemon_pool 失败: {_e}")
        return None


def _new_executor():
    """新建执行器。

    优先用 Hermes 的 DaemonThreadPoolExecutor：stdlib 的 ThreadPoolExecutor
    worker 是非 daemon 的，concurrent.futures 的 atexit 钩子会**无条件 join**
    所有 worker —— 只要有一个超时后仍在空转的代码，整个后端进程就永远退不出去
    （实测复现：Ctrl+C / 重启全部无效）。daemon worker 不参与该 join。
    """
    _cls = _load_daemon_executor_cls()
    if _cls is None:
        logger.warning(
            "DaemonThreadPoolExecutor 不可用，回退 stdlib 线程池"
            "（超时后的空转线程会阻塞进程退出）"
        )
        _cls = ThreadPoolExecutor
    return _cls(max_workers=_CODEX_MAX_WORKERS, thread_name_prefix="code_mode")


_executor = _new_executor()


def _retire_poisoned_executor() -> None:
    """退役被超时任务污染的线程池并重建，避免容量永久损失。

    背景：线程无法被强杀（`future.cancel()` 对已开始的线程是 no-op）。一次超时
    就永久占住一个 worker；由于池上限只有 8，**8 次超时即可让 Code Mode 对所有
    用户永久不可用**（实测复现：8 个 `while` 空转后，一个 `print('hello')` 的
    正常任务也直接超时且无输出）。

    退役后：新建的池立刻恢复全部容量；旧池里的空闲 worker 收到哨兵后正常退出，
    只有真正跑飞的那几个线程会继续空转（那部分只能靠进程级隔离根治）。
    """
    global _executor
    with _POOL_LOCK:
        old = _executor
        _executor = _new_executor()
    try:
        old.shutdown(wait=False, cancel_futures=True)
    except Exception as _e:
        logger.debug(f"退役旧 Code Mode 线程池失败（忽略）: {_e}")
    logger.warning(
        "Code Mode 线程池已因超时退役重建：跑飞的线程无法回收，"
        "仅恢复了可用容量（根治需要进程级隔离）"
    )


# 内部工具调用输出监控阈值（超过此长度记录警告日志）
_INNER_TOOL_OUTPUT_WARN_CHARS = 50_000

# 自动修复最大重试次数（生产环境中，大多数拼写/参数错误 2 次内可修复）
MAX_AUTO_RETRIES = 2

# ──────────────────────────────────────────────────────────────
# 文件操作安全配置
# ──────────────────────────────────────────────────────────────

# 单次读取文件最大字节数（1MB，防止读取超大文件导致内存问题）
MAX_FILE_READ_SIZE = 1_000_000

# 搜索文件时最大结果数（防止返回过多结果）
MAX_SEARCH_RESULTS = 100

# 允许访问的目录白名单（相对于项目根目录）
# 空列表表示允许项目根目录下的所有目录（除了明确禁止的）
ALLOWED_DIRECTORIES = []

# 禁止访问的目录（优先级高于白名单）
BLOCKED_DIRECTORIES = [
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "data/logs",      # 日志目录
    "data/uploads",   # 上传文件
    "data/rag_vectors",  # 向量数据
    "data/tool_results",  # 旧位置的私有工具原文也不能绕过恢复授权
]

# 项目根目录（运行时动态获取）
_PROJECT_ROOT = None

def _get_project_root() -> str:
    """获取项目根目录路径。"""
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        # 从当前文件位置推断项目根目录（backend/tools/code_executor.py → 项目根）
        import os
        _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return _PROJECT_ROOT


# ──────────────────────────────────────────────────────────────
# Code Mode 使用统计（P5 可观测性）
# ──────────────────────────────────────────────────────────────

class _CodeModeStats:
    """Code Mode 运行统计（线程安全）

    记录调用次数、成功/失败率、安全检查拦截率等，
    便于评估 Code Mode 的使用情况和 Token 降本效果。
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.safety_rejections = 0
        self.total_duration_ms = 0.0
        self.inner_tool_calls = 0  # 内部工具调用总次数
        self.auto_fixes = 0          # 自动修复尝试次数
        self.auto_fix_successes = 0  # 自动修复后成功的次数

    def record_call(self, success: bool, duration_ms: float):
        with self._lock:
            self.total_calls += 1
            if success:
                self.successful_calls += 1
            else:
                self.failed_calls += 1
            self.total_duration_ms += duration_ms

    def record_safety_rejection(self):
        with self._lock:
            self.safety_rejections += 1

    def record_inner_tool_call(self):
        with self._lock:
            self.inner_tool_calls += 1

    def record_auto_fix(self, success: bool = False):
        with self._lock:
            self.auto_fixes += 1
            if success:
                self.auto_fix_successes += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total_calls": self.total_calls,
                "successful_calls": self.successful_calls,
                "failed_calls": self.failed_calls,
                "safety_rejections": self.safety_rejections,
                "avg_duration_ms": (
                    self.total_duration_ms / self.total_calls
                    if self.total_calls > 0 else 0
                ),
                "inner_tool_calls": self.inner_tool_calls,
                "auto_fixes": self.auto_fixes,
                "auto_fix_successes": self.auto_fix_successes,
            }


_stats = _CodeModeStats()


def get_code_mode_stats() -> dict:
    """获取 Code Mode 运行统计快照（供 API 端点或管理面板调用）"""
    return _stats.snapshot()


# ──────────────────────────────────────────────────────────────
# 文件操作安全检查
# ──────────────────────────────────────────────────────────────

class FileOperationError(Exception):
    """文件操作安全错误。"""
    pass


def _validate_file_path(path: str) -> str:
    """验证文件路径的安全性，返回规范化后的绝对路径。

    安全检查：
    1. 目录遍历防护：禁止 ../ 等相对路径逃逸
    2. 白名单检查：只允许访问项目目录下的文件
    3. 黑名单检查：禁止访问敏感目录（.git、node_modules 等）
    4. 符号链接防护：检查符号链接是否指向允许范围外
    5. Windows 特殊防护：大小写不敏感、ADS、尾部点/空格

    Args:
        path: 用户提供的文件路径（相对或绝对）

    Returns:
        规范化后的绝对路径

    Raises:
        FileOperationError: 路径不安全时抛出
    """
    import os

    project_root = _get_project_root()

    # ── Windows 特殊防护 ──
    # 1. 拒绝 ADS（备用数据流）：路径中含 :
    #    注意：Windows 盘符如 C: 只出现在绝对路径开头，这里处理的是相对路径
    if ':' in path:
        # 检查是否是绝对路径的盘符（如 C:\...）
        # 相对路径中的 : 都是 ADS，需要拒绝
        if not (len(path) >= 2 and path[1] == ':' and path[0].isalpha()):
            raise FileOperationError(
                f"路径 '{path}' 包含非法字符 ':'（可能是 NTFS 备用数据流攻击）。"
            )
        # 如果是绝对路径，检查是否在项目根目录内
        # （后续会再次检查，这里只是确保盘符是合法的）

    # 2. 拒绝路径段末尾的点或空格（Windows 会忽略）
    #    例如 ".env." 或 ".env " 会被解析为 ".env"
    for part in re.split(r"[\\/]+", path):
        if not part:
            continue
        # 检查是否以点或空格结尾（排除 . 和 .. 本身）
        if part not in ('.', '..') and (part.endswith('.') or part.endswith(' ')):
            raise FileOperationError(
                f"路径 '{path}' 包含非法的路径段 '{part}'（末尾点或空格会被 Windows 忽略）。"
            )

    # 处理相对路径
    if not os.path.isabs(path):
        path = os.path.join(project_root, path)

    # 规范化路径（消除 ../ 等）
    normalized = os.path.realpath(path)
    project_root = os.path.realpath(project_root)

    # 检查是否在项目目录内
    try:
        inside_project = os.path.normcase(os.path.commonpath([normalized, project_root])) == os.path.normcase(project_root)
    except ValueError:
        inside_project = False
    if not inside_project:
        raise FileOperationError(
            f"路径 '{path}' 超出允许范围。只能访问项目目录下的文件。"
        )
    from backend.context.tool_results.runtime import is_result_store_path
    if is_result_store_path(normalized):
        raise FileOperationError("工具原文存储目录禁止直接访问，请使用 context_read/context_search。")

    # 检查是否包含禁止的目录
    rel_path = os.path.relpath(normalized, project_root)
    # 规范化后按段比较，让多段条目（如 "data/logs"）也能命中
    parts = [p for p in re.split(r"[\\/]+", rel_path) if p]

    for blocked in BLOCKED_DIRECTORIES:
        blocked_parts = [p for p in re.split(r"[\\/]+", blocked) if p]
        if not blocked_parts:
            continue
        # ── Windows 大小写不敏感比较 ──
        # 使用 casefold() 进行大小写不敏感匹配
        blocked_parts_lower = [p.casefold() for p in blocked_parts]
        parts_lower = [p.casefold() for p in parts]
        # 命中任意位置的连续子序列都算（前导、中间、结尾都禁止）
        n = len(blocked_parts_lower)
        if any(parts_lower[i:i + n] == blocked_parts_lower for i in range(len(parts_lower) - n + 1)):
            raise FileOperationError(
                f"路径 '{path}' 包含禁止访问的目录 '{blocked}'。"
            )

    # 检查符号链接（如果存在）
    if os.path.islink(path):
        real_path = os.path.realpath(path)
        if not real_path.startswith(project_root):
            raise FileOperationError(
                f"符号链接 '{path}' 指向项目目录外的位置，禁止访问。"
            )

    return normalized


def _search_path_allowed(path: str) -> bool:
    try:
        _validate_file_path(path)
        return True
    except (FileOperationError, OSError, ValueError):
        return False


def _check_file_size(file_path: str) -> int:
    """检查文件大小是否在允许范围内。

    Args:
        file_path: 文件的绝对路径

    Returns:
        文件大小（字节）

    Raises:
        FileOperationError: 文件过大时抛出
    """
    import os

    try:
        size = os.path.getsize(file_path)
    except OSError as e:
        raise FileOperationError(f"无法获取文件大小: {e}")

    if size > MAX_FILE_READ_SIZE:
        size_mb = size / (1024 * 1024)
        limit_mb = MAX_FILE_READ_SIZE / (1024 * 1024)
        raise FileOperationError(
            f"文件过大 ({size_mb:.1f}MB)，超过限制 ({limit_mb:.1f}MB)。"
            f"请使用 offset 和 limit 参数分段读取。"
        )

    return size


# ──────────────────────────────────────────────────────────────
# 安全的文件操作函数
# ──────────────────────────────────────────────────────────────

def code_mode_read_file(path, offset: int = 1, limit: int = 500) -> str:
    """安全地读取文件内容（带行号）。支持批量读取。

    安全特性：
    - 路径白名单：只允许访问项目目录
    - 目录遍历防护：禁止 ../ 逃逸
    - 文件大小限制：单次读取 < 1MB
    - 符号链接检查：防止指向项目外

    Args:
        path: 文件路径（str 或 List[str]）。
              传入列表时批量读取多个文件。
        offset: 起始行号（从 1 开始，默认 1）
        limit: 最大读取行数（默认 500）

    Returns:
        带行号的文件内容（格式：行号|内容）

    Raises:
        FileOperationError: 路径不安全或文件不存在时抛出

    示例:
        >>> # 读取单个文件
        >>> content = read_file("backend/tools/code_executor.py")
        >>> content = read_file("README.md", offset=10, limit=100)

        >>> # 批量读取多个文件（推荐）
        >>> content = read_file(["file1.py", "file2.py", "file3.py"])
    """
    import os

    # ── 批量读取模式 ──
    if isinstance(path, (list, tuple)):
        if not path:
            return "(空文件列表)"
        results = []
        for p in path:
            try:
                content = code_mode_read_file(p, offset=offset, limit=limit)
                results.append(content)
            except FileOperationError as e:
                results.append(f"❌ {p}: {e}")
        return "\n\n" + "=" * 60 + "\n\n".join(results)

    # ── 单文件读取模式 ──
    # 安全检查
    safe_path = _validate_file_path(path)
    _check_file_size(safe_path)

    # 检查文件是否存在
    if not os.path.exists(safe_path):
        raise FileOperationError(f"文件不存在: {path}")

    if not os.path.isfile(safe_path):
        raise FileOperationError(f"不是文件: {path}")

    # 读取文件
    try:
        with open(safe_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        raise FileOperationError(f"读取文件失败: {e}")

    # 分页处理
    total_lines = len(lines)
    start_idx = max(0, offset - 1)
    end_idx = min(total_lines, start_idx + limit)

    if start_idx >= total_lines:
        return f"(文件共 {total_lines} 行，offset={offset} 超出范围)"

    # 格式化输出（带行号）
    result_lines = []
    for i in range(start_idx, end_idx):
        line_num = i + 1
        line_content = lines[i].rstrip('\n')
        result_lines.append(f"{line_num:>4}| {line_content}")

    # 添加摘要信息
    header = f"文件: {path} (共 {total_lines} 行，显示 {start_idx + 1}-{end_idx})\n"
    header += "─" * 60 + "\n"

    return header + "\n".join(result_lines)


def code_mode_search_files(
    pattern,
    target: str = "auto",
    path: str = ".",
    file_glob: str = None,
    limit: int = 50
) -> str:
    """智能搜索文件内容或文件名。支持批量搜索。

    安全特性：
    - 路径白名单：只允许在项目目录内搜索
    - 禁止访问敏感目录（.git、node_modules 等）
    - 结果数量限制：最多返回 100 条

    智能特性（target="auto"）：
    - 自动判断搜索模式类型（glob vs 正则）
    - 搜索无结果时自动切换搜索方式并给出建议

    Args:
        pattern: 搜索模式（str 或 List[str]）。
                 传入列表时批量搜索多个模式。
        target: 搜索目标（默认 "auto"）
            - "auto": 智能判断（推荐）
              - 如果 pattern 包含 * 或 ?，按文件名搜索
              - 否则按文件内容搜索
              - 如果无结果，自动尝试另一种方式
            - "content": 搜索文件内容（正则表达式）
            - "files": 搜索文件名（glob 模式，如 "*.py"）
        path: 搜索的根目录（默认当前目录，相对于项目根）
        file_glob: 文件过滤模式（仅 target="content" 时有效，如 "*.py"）
        limit: 最大结果数（默认 50，最大 100）

    Returns:
        搜索结果（格式化的文本）

    Raises:
        FileOperationError: 路径不安全或搜索失败时抛出

    示例:
        >>> # 搜索单个模式
        >>> results = search_files("milvus")
        >>> results = search_files("*.py")

        >>> # 批量搜索多个模式（推荐）
        >>> results = search_files(["milvus", "vector", "schema"])
        >>> results = search_files(["*.py", "*.js"])  # 批量搜索文件名
    """
    import os
    import fnmatch
    import re

    # ── 批量搜索模式 ──
    if isinstance(pattern, (list, tuple)):
        if not pattern:
            return "(空搜索模式列表)"
        results = []
        # 批量搜索时，自动分配 limit（每个模式平分总 limit）
        per_pattern_limit = max(5, limit // len(pattern))
        for p in pattern:
            try:
                result = code_mode_search_files(
                    p, target=target, path=path,
                    file_glob=file_glob, limit=per_pattern_limit
                )
                results.append(f"\n=== 搜索 '{p}' ===\n{result}")
            except FileOperationError as e:
                results.append(f"\n=== 搜索 '{p}' ===\n❌ 错误: {e}")
        return "\n".join(results)

    # ── 单模式搜索 ──
    # 安全检查
    safe_path = _validate_file_path(path)

    # 限制结果数量
    limit = min(limit, MAX_SEARCH_RESULTS)

    # ── 智能模式：自动判断搜索方式 ──
    if target == "auto":
        # 判断 pattern 是否像 glob 模式（包含 * 或 ?）
        is_glob_pattern = ('*' in pattern or '?' in pattern) and not any(
            c in pattern for c in r'()[]{}+^$|\\'
        )

        if is_glob_pattern:
            # 看起来像 glob 模式，先搜索文件名
            actual_target = "files"
        else:
            # 看起来像关键词/正则，先搜索内容
            actual_target = "content"
    else:
        # 支持常见别名
        target_aliases = {
            "filename": "files",
            "file": "files",
            "name": "files",
            "content": "content",
            "text": "content",
            "files": "files",
        }
        actual_target = target_aliases.get(target.lower(), target)

    results = []

    if actual_target == "files":
        # 文件名搜索（glob 模式）
        for root, dirs, files in os.walk(safe_path):
            # 过滤禁止的目录
            dirs[:] = [d for d in dirs if _search_path_allowed(os.path.join(root, d))]

            for filename in files:
                if fnmatch.fnmatch(filename, pattern):
                    full_path = os.path.join(root, filename)
                    if not _search_path_allowed(full_path):
                        continue
                    rel_path = os.path.relpath(full_path, _get_project_root())
                    results.append(rel_path)

                    if len(results) >= limit:
                        break

            if len(results) >= limit:
                break

        if not results:
            # 智能模式下，文件名搜索无结果时给出建议
            if target == "auto":
                return (
                    f"未找到文件名匹配 '{pattern}' 的文件。\n"
                    f"💡 建议：如果你想搜索文件内容，请使用 search_files(\"{pattern}\", target=\"content\")\n"
                    f"   或者简写为 search_files(\"{pattern}\") （默认搜索内容）"
                )
            return f"未找到匹配 '{pattern}' 的文件"

        return f"找到 {len(results)} 个文件:\n" + "\n".join(results)

    elif actual_target == "content":
        # 内容搜索（正则表达式）
        try:
            # 如果用户输入的是简单关键词（非正则），自动转义特殊字符
            # 但保留 | 用于 OR 搜索（常见用法）
            if not any(c in pattern for c in r'()[]{}+*?^$\\'):
                # 简单关键词，直接搜索（不转义 |）
                regex = re.compile(re.escape(pattern).replace(r'\|', '|'), re.IGNORECASE)
            else:
                regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise FileOperationError(f"无效的正则表达式: {e}")

        search_count = 0

        for root, dirs, files in os.walk(safe_path):
            # 过滤禁止的目录
            dirs[:] = [d for d in dirs if _search_path_allowed(os.path.join(root, d))]

            for filename in files:
                # 应用文件过滤
                if file_glob and not fnmatch.fnmatch(filename, file_glob):
                    continue

                full_path = os.path.join(root, filename)
                if not _search_path_allowed(full_path):
                    continue
                rel_path = os.path.relpath(full_path, _get_project_root())

                # 跳过二进制文件
                if full_path.endswith(('.pyc', '.pyo', '.so', '.dll', '.exe', '.png', '.jpg', '.gif', '.pdf')):
                    continue

                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                                search_count += 1

                                if search_count >= limit:
                                    break
                except Exception:
                    # 跳过无法读取的文件
                    continue

                if search_count >= limit:
                    break

            if search_count >= limit:
                break

        if not results:
            # 智能模式下，内容搜索无结果时给出建议
            if target == "auto":
                return (
                    f"未找到包含 '{pattern}' 的文件内容。\n"
                    f"💡 建议：\n"
                    f"   - 检查拼写是否正确\n"
                    f"   - 尝试更宽泛的关键词\n"
                    f"   - 如果你想搜索文件名，请使用 search_files(\"{pattern}\", target=\"files\")"
                )
            return f"未找到包含 '{pattern}' 的内容"

        # 添加搜索结果摘要
        header = f"找到 {len(results)} 处匹配"
        if target == "auto":
            header += "（智能搜索：文件内容）"
        header += ":\n"

        return header + "\n".join(results)

    else:
        raise FileOperationError(
            f"无效的 target 参数: {target}，必须是 'auto'、'content' 或 'files'"
        )


class _ToolWrapper:
    """工具函数监控包装器（P2 + P5）

    包装 LangChain StructuredTool 或普通函数，添加：
      - 内部调用次数统计
      - 大输出（>50K）警告日志
      - 执行耗时监控

    Code Mode 内部调用的工具函数不经过 _make_project_tool_handler，
    因此不受 tool_output_guard 截断。此包装提供轻量级监控。
    """
    def __init__(self, tool_func, tool_name: str):
        self._tool_func = tool_func
        self._tool_name = tool_name
        # 预提取 BaseTool 输入字段名（排除 RunnableConfig），用于位置参数映射
        schema = getattr(tool_func, 'args_schema', None)
        if schema is not None:
            fields = getattr(schema, 'model_fields', None) or getattr(schema, '__fields__', {})
            type_hints = {}
            try:
                import typing
                func = getattr(tool_func, 'func', None) or getattr(tool_func, 'coroutine', None)
                if func is not None:
                    type_hints = typing.get_type_hints(func)
            except Exception:
                pass
            from langchain_core.runnables import RunnableConfig
            self._input_field_names = [
                fname for fname in fields
                if type_hints.get(fname) is not RunnableConfig
            ]
        else:
            self._input_field_names = None

    def __call__(self, *args, **kwargs):
        _stats.record_inner_tool_call()
        start = time.perf_counter()
        try:
            # BaseTool (StructuredTool) 不可直接调用，需通过 .invoke() 传入 dict
            # LangChain @tool 装饰器返回的是 StructuredTool 实例而非普通函数
            if hasattr(self._tool_func, 'invoke') and hasattr(self._tool_func, 'name'):
                input_dict = _build_tool_input(self._input_field_names, args, kwargs)
                try:
                    result = self._tool_func.invoke(input_dict)
                except Exception:
                    # 部分工具可能需要 config 注入，重试时传空 dict
                    result = self._tool_func.invoke({})
            elif callable(self._tool_func):
                result = self._tool_func(*args, **kwargs)
            else:
                raise TypeError(
                    f"工具 {self._tool_name} 既非 BaseTool 也非可调用对象"
                )

            duration_ms = (time.perf_counter() - start) * 1000
            # 仅对字符串结果做精确长度检查，避免对复杂对象做昂贵的 str() 转换
            result_len = len(result) if isinstance(result, str) else 0
            if result_len > _INNER_TOOL_OUTPUT_WARN_CHARS:
                logger.warning(
                    f"Code Mode 内部工具 {self._tool_name} 输出较大: "
                    f"{result_len:,} 字符, 耗时 {duration_ms:.1f}ms"
                )
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.warning(
                f"Code Mode 内部工具 {self._tool_name} 执行失败: "
                f"{type(e).__name__}: {e}, 耗时 {duration_ms:.1f}ms"
            )
            raise


def _build_tool_input(field_names, args, kwargs) -> dict:
    """将位置参数和关键字参数映射为 BaseTool.invoke 所需的 input dict。

    通过预提取的 field_names（已排除 RunnableConfig）将位置参数
    按顺序映射到正确的字段名。
    """
    input_dict = {}
    if field_names:
        for i, arg in enumerate(args):
            if i < len(field_names):
                input_dict[field_names[i]] = arg
    input_dict.update(kwargs)
    return input_dict


def _wrap_tool_for_code_mode(tool_func, tool_name: str) -> _ToolWrapper:
    """创建工具函数的监控包装器"""
    return _ToolWrapper(tool_func, tool_name)


# ──────────────────────────────────────────────────────────────
# 危险操作检测
# ──────────────────────────────────────────────────────────────

# 禁止调用的函数名
DANGEROUS_FUNCTIONS = frozenset({
    # 代码执行
    "eval", "exec", "compile", "__import__",
    # 文件 IO（不允许直接操作文件）
    "open", "input", "raw_input",
    # 系统操作
    "exit", "quit",
})

# 禁止访问的属性名
DANGEROUS_ATTRIBUTES = frozenset({
    "__globals__", "__builtins__", "__import__",
    "__subclasses__", "__class__", "__bases__",
})


# ──────────────────────────────────────────────────────────────
# AST 安全检查
# ──────────────────────────────────────────────────────────────

def check_ast_safety(code: str) -> tuple[bool, Optional[str]]:
    """检查代码是否包含危险操作。

    ⚠️ 已知局限（2026-09-18 实测，勿当作完备沙箱）
    ──────────────────────────────────────────────────────────
    本函数是**基于名字的静态黑名单**：只检查 `ast.Call` 的直接函数名与
    `ast.Attribute` 的字面属性名。**它看不见运行期才解析出来的属性名**，
    因此下面两行一个放行、一个拦截：

        "{0.__globals__}".format(print)     # → is_safe=True（放行）
        print.__globals__                   # → is_safe=False（拦截）

    因为 `str.format` 在**运行期**解析字段名里的 `__globals__`，
    AST 里只看到一个普通的 `.format(...)` 调用。

    已实测的影响边界（不要夸大，也不要低估）：
      - 能把 globals 中的属性链**渲染成字符串**读出（属性名泄露面）；
      - **未能**取到对象本身 → **未能**实现任意代码执行
        （`str.format` 只返回 str）；
      - `code_executor` 模块命名空间里没有 `os` → **未能**读出环境变量
        （实测 `KeyError: 'os'`）。
    `getattr` / `globals` / `vars` / `dir` 都不在 SAFE_BUILTINS 中，
    所以 `getattr(type(x), '__subclasses__')` 这类间接路径走不通。

    结论：需要真隔离时应改为**子进程 + 受限环境**；继续往黑名单里加名字
    堵不住 —— 只要还存在"运行期解析属性名"的入口就会继续漏。
    ──────────────────────────────────────────────────────────

    Args:
        code: 要检查的 Python 代码

    Returns:
        (is_safe, error_message): 是否安全，如果不安全则包含错误信息
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"语法错误: {e}"

    for node in ast.walk(tree):
        # 禁止 import 语句
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "不允许 import 语句"

        # 检查函数调用
        if isinstance(node, ast.Call):
            safe, msg = _check_call_safety(node)
            if not safe:
                return safe, msg

        # 检查属性访问
        if isinstance(node, ast.Attribute):
            if node.attr in DANGEROUS_ATTRIBUTES:
                return False, f"不允许访问属性: {node.attr}"

    return True, None


def _check_call_safety(node: ast.Call) -> tuple[bool, Optional[str]]:
    """检查函数调用是否安全"""
    # 直接调用：func_name(...)
    if isinstance(node.func, ast.Name):
        if node.func.id in DANGEROUS_FUNCTIONS:
            return False, f"不允许调用函数: {node.func.id}"

    # 属性调用：obj.method(...)
    if isinstance(node.func, ast.Attribute):
        if node.func.attr in DANGEROUS_FUNCTIONS:
            return False, f"不允许调用方法: {node.func.attr}"
        if node.func.attr in DANGEROUS_ATTRIBUTES:
            return False, f"不允许访问属性: {node.func.attr}"

    return True, None


# ──────────────────────────────────────────────────────────────
# safe_print 实现
# ──────────────────────────────────────────────────────────────

def create_safe_print(
    output_buffer: io.StringIO,
    total_chars_ref: list = None,
    capture_sink: Optional[OutputSink] = None,
):
    """创建带截断保护的 safe_print 函数。

    Args:
        output_buffer: 输出缓冲区
        total_chars_ref: 总字符数引用（用于截断保护，与 log 函数共享）

    Returns:
        safe_print 函数
    """
    # 如果没有提供 total_chars_ref，创建一个新的
    if total_chars_ref is None:
        total_chars_ref = [0]

    def safe_print(*args, **kwargs):
        # 构建输出字符串
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '\n')
        output = sep.join(str(arg) for arg in args)

        # Capture emitted text before legacy presentation limits. A timed-out
        # attempt owns a closed sink and must not emit any further output.
        if capture_sink is not None:
            if not capture_sink.write(output) or not capture_sink.write(end):
                return

        # 检查总输出限制（达到限制后直接返回，不再写入任何内容）
        if total_chars_ref[0] >= MAX_TOTAL_OUTPUT:
            return

        # 单次 print 截断保护
        if len(output) > MAX_SINGLE_PRINT:
            truncated = output[:MAX_SINGLE_PRINT]
            omitted = len(output) - MAX_SINGLE_PRINT
            output_buffer.write(truncated)
            output_buffer.write(f"\n[PRINT TRUNCATED] 省略 {omitted:,} 字符...\n")
            total_chars_ref[0] += MAX_SINGLE_PRINT + 50
        else:
            output_buffer.write(output)
            total_chars_ref[0] += len(output)

        # end 也计入总字符数（防止大量 print 的 \n 累积超出限制）
        output_buffer.write(end)
        total_chars_ref[0] += len(end)

        # 写入后再次检查是否超过总限制，如果超过则写入限制提示
        if total_chars_ref[0] >= MAX_TOTAL_OUTPUT:
            output_buffer.write("\n[TOTAL OUTPUT LIMIT REACHED] 已停止输出...")

    return safe_print


# ──────────────────────────────────────────────────────────────
# 日志函数实现（关键节点日志 vs 详细日志）
# ──────────────────────────────────────────────────────────────

def create_log_functions(
    output_buffer: io.StringIO,
    user_id: int = None,
    thread_id: str = None,
    total_chars_ref: list = None,
    capture_sink: Optional[OutputSink] = None,
) -> Tuple[Callable, Callable, str]:
    """创建日志函数（关键节点日志 vs 详细日志）。

    设计思路：
      - log(msg, level="info"): 关键节点日志，进入 output_buffer，返回给 Agent
      - log_debug(msg): 详细调试日志，写入文件，不进入上下文

    Args:
        output_buffer: 输出缓冲区（关键节点日志写入这里）
        user_id: 用户 ID（用于日志文件命名）
        thread_id: 会话 ID（用于日志文件命名）
        total_chars_ref: 总字符数引用（用于截断保护，与 safe_print 共享）

    Returns:
        (log, log_debug, log_file_path) 元组
    """
    # 创建详细日志目录
    log_dir = os.path.join(_get_project_root(), "data", "logs", "code_mode")
    os.makedirs(log_dir, exist_ok=True)

    # 日志文件命名：debug_{user_id}_{thread_id}_{timestamp}.log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_part = str(user_id) if user_id else "unknown"
    thread_part = thread_id[:8] if thread_id else "default"
    log_file_path = os.path.join(log_dir, f"debug_{user_part}_{thread_part}_{timestamp}.log")

    # 如果没有提供 total_chars_ref，创建一个新的
    if total_chars_ref is None:
        total_chars_ref = [0]

    # 日志级别图标映射
    level_icons = {
        "info": "[I]",
        "warn": "[W]",
        "warning": "[W]",  # 别名
        "error": "[E]",
        "success": "[OK]",
        "ok": "[OK]",  # 别名
    }

    def log(message: str, level: str = "info") -> None:
        """记录关键节点日志（返回给 Agent）。

        适用场景：
          - 任务开始/完成
          - 重要决策点
          - 错误/警告
          - 最终结果摘要

        Args:
            message: 日志消息
            level: 日志级别（info/warn/error/success）

        示例:
            log("开始检索知识库...", level="info")
            log("✅ 检索完成，找到 5 条结果", level="success")
            log("⚠️ 部分数据缺失，已跳过", level="warn")
        """
        # Preserve disabled-mode behavior, including its early return.
        if capture_sink is None and total_chars_ref[0] >= MAX_TOTAL_OUTPUT:
            return

        # 格式化日志
        ts = datetime.now().strftime("%H:%M:%S")
        icon = level_icons.get(level.lower(), "")
        formatted = f"[{ts}] {icon} {message}\n"

        if capture_sink is not None and not capture_sink.write(formatted):
            return

        # 检查总输出限制（与 safe_print 共享）
        if total_chars_ref[0] >= MAX_TOTAL_OUTPUT:
            return

        # 截断保护
        if len(formatted) > MAX_SINGLE_PRINT:
            formatted = formatted[:MAX_SINGLE_PRINT] + "[TRUNCATED]\n"

        output_buffer.write(formatted)
        total_chars_ref[0] += len(formatted)

        # 同时写入详细日志文件（便于排查）
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] [{level.upper()}] {message}\n")
        except Exception:
            pass  # 文件写入失败不影响主流程

    def log_debug(message: str) -> None:
        """记录详细调试日志（写入文件，不进上下文）。

        适用场景：
          - 中间数据处理过程
          - 循环内的详细日志
          - 性能计时
          - 调试信息

        Args:
            message: 日志消息

        示例:
            log_debug("开始处理第 1 条数据...")
            log_debug("数据内容: {id: 1, name: 'test'}")
            log_debug("处理耗时: 123ms")
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] [DEBUG] {message}\n")
        except Exception:
            pass  # 文件写入失败不影响主流程

    return log, log_debug, log_file_path


# ──────────────────────────────────────────────────────────────
# 受限 globals 构建
# ──────────────────────────────────────────────────────────────

# 缓存工具函数（首次调用时导入并缓存，后续直接返回）
# CPython GIL 保证并发安全：最坏情况是首次并发时重复导入，结果一致无副作用
_cached_tool_functions: Optional[dict] = None
# 缓存工具的 _toolset 属性（用于权限过滤）
_cached_tool_toolsets: Optional[dict] = None


def _get_tool_functions() -> dict:
    """获取可用工具函数白名单（经监控包装）。

    首次调用时导入并缓存，后续调用直接返回缓存。
    每个工具函数经 _wrap_tool_for_code_mode 包装，提供：
      - 内部调用次数统计
      - 大输出警告日志

    Returns:
        工具函数字典 {name: wrapper}
    """
    global _cached_tool_functions, _cached_tool_toolsets
    if _cached_tool_functions is not None:
        return _cached_tool_functions

    tools = {}
    toolsets = {}  # 记录每个工具的 _toolset 属性

    def _add(name: str, func, toolset: str = None):
        """添加工具函数，并记录其 _toolset 属性。未显式指定时读函数自身的 _toolset；
        两者都没有则记 None —— 让 build_safe_globals 的 fail-closed 分支真正生效。"""
        tools[name] = _wrap_tool_for_code_mode(func, name)
        if toolset is None:
            toolset = getattr(func, '_toolset', None)
        toolsets[name] = toolset

    # 知识库检索
    try:
        from backend.tools.tools_decorator import knowledge_search
        _add("knowledge_search", knowledge_search)
    except ImportError as e:
        logger.warning(f"无法导入 knowledge_search: {e}")

    # SQL 查询（注意：sql_db_query 在 text_to_sql.py 中定义）
    try:
        from backend.tools.text_to_sql import sql_db_query
        _add("sql_query", sql_db_query)
    except ImportError as e:
        logger.warning(f"无法导入 sql_db_query: {e}")

    # 当前时间
    try:
        from backend.tools.tools_decorator import get_current_time
        _add("get_current_time", get_current_time)
    except ImportError as e:
        logger.warning(f"无法导入 get_current_time: {e}")

    # 待办事项工具
    for name in ("todo_add", "todo_update", "todo_get"):
        try:
            mod = __import__("backend.tools.tools_decorator", fromlist=[name])
            _add(name, getattr(mod, name))
        except (ImportError, AttributeError) as e:
            logger.warning(f"无法导入 {name}: {e}")

    # 定时任务工具
    for name in ("cronjob_create", "list_delivery_configs"):
        try:
            mod = __import__("backend.tools.tools_decorator", fromlist=[name])
            _add(name, getattr(mod, name))
        except (ImportError, AttributeError) as e:
            logger.warning(f"无法导入 {name}: {e}")

    # 时间解析工具
    try:
        from backend.tools.tools_decorator import when_resolve
        _add("when_resolve", when_resolve)
    except ImportError as e:
        logger.warning(f"无法导入 when_resolve: {e}")

    # 文件操作工具（只读，带安全检查）
    # 直接添加，因为这些函数定义在当前模块中
    # 文件操作工具属于 file toolset（已通过 Hermes 禁用，但 Code Mode 内部也需要权限检查）
    _add("read_file", code_mode_read_file, "file")
    _add("search_files", code_mode_search_files, "file")

    _cached_tool_functions = tools
    _cached_tool_toolsets = toolsets
    return tools


def _get_tool_toolsets() -> dict:
    """获取工具的 _toolset 属性映射。

    Returns:
        {tool_name: toolset_name} 映射
    """
    if _cached_tool_toolsets is None:
        _get_tool_functions()  # 确保已初始化
    return _cached_tool_toolsets


def build_safe_globals(user_id: int = None) -> dict:
    """构建受限的执行环境 globals。

    每次返回新的 dict，防止用户代码通过 globals() 修改顶层键。
    工具函数对象为缓存共享（_ToolWrapper 无状态，安全）。

    Args:
        user_id: 当前用户 ID（可选）。如果提供，会根据用户权限过滤工具。

    Returns:
        受限的 globals 字典
    """
    # 工具函数白名单 + 安全内建函数
    # 不暴露任何模块引用，代码无法访问全局缓存或其他用户数据
    all_tools = _get_tool_functions()

    # 如果提供了 user_id，根据用户权限过滤工具
    if user_id is not None:
        try:
            from backend.permission.checker import get_user_hermes_tools

            # 获取用户的 toolset 权限（Redis 缓存，性能很好）
            user_toolsets = set(get_user_hermes_tools(user_id))
            tool_toolsets = _get_tool_toolsets()

            # 过滤工具：只保留 _toolset 在用户权限中的工具
            # __always_available__ 的工具始终保留
            filtered_tools = {}
            for name, wrapper in all_tools.items():
                # 安全默认值：如果工具未注册 _toolset，默认为需要权限（不允许访问）
                # 这样可以防止未正确注册的工具被意外暴露
                tool_toolset = tool_toolsets.get(name)
                if tool_toolset is None:
                    # 工具未注册 _toolset，记录警告并跳过（不允许访问）
                    logger.warning(
                        f"工具 {name} 未注册 _toolset 属性，跳过（安全默认值）"
                    )
                    continue
                if tool_toolset == '__always_available__' or tool_toolset in user_toolsets:
                    filtered_tools[name] = wrapper

            # 记录过滤结果（便于调试）
            filtered_count = len(all_tools) - len(filtered_tools)
            if filtered_count > 0:
                filtered_names = [n for n in all_tools if n not in filtered_tools]
                logger.debug(
                    f"Code Mode 工具权限过滤: user_id={user_id}, "
                    f"过滤 {filtered_count} 个工具: {filtered_names}"
                )

            tools = filtered_tools
        except Exception as e:
            # 权限检查失败时，不授予任何工具（fail-closed）
            logger.warning(f"Code Mode 权限检查失败，因此本次不授予任何工具: {e}")
            tools = {}
    else:
        # user_id 为 None 时，无法确定用户身份，不授予任何工具（fail-closed）
        tools = {}

    return {**tools, "__builtins__": dict(SAFE_BUILTINS)}


# ──────────────────────────────────────────────────────────────
# 工具签名注册表（用于错误消息中的「可用工具提示」）
# ──────────────────────────────────────────────────────────────

_TOOL_SIGNATURES_CACHE: Optional[dict] = None


def _build_tool_signatures() -> dict:
    """构建工具签名表，用于错误消息中的「可用工具提示」。

    缓存结果（工具列表在运行时不变），格式：
      {"knowledge_search": "knowledge_search(query, top_k=5)", ...}
    """
    global _TOOL_SIGNATURES_CACHE
    if _TOOL_SIGNATURES_CACHE is not None:
        return _TOOL_SIGNATURES_CACHE

    sigs = {}
    for name, wrapper in _get_tool_functions().items():
        func = getattr(wrapper, '_tool_func', None)
        if func is None:
            sigs[name] = f"{name}(...)"
            continue
        try:
            # StructuredTool 的真实函数在 .func 属性中
            real_func = getattr(func, 'func', None) or func
            sig = inspect.signature(real_func)
            params = []
            for pname, param in sig.parameters.items():
                # 跳过内部注入参数（RunnableConfig 等）
                if pname in ('self', 'config', 'cls'):
                    continue
                # 跳过 RunnableConfig 类型
                annotation = param.annotation
                if annotation is not inspect.Parameter.empty:
                    ann_str = getattr(annotation, '__name__', str(annotation))
                    if 'RunnableConfig' in ann_str:
                        continue
                if param.default is not inspect.Parameter.empty:
                    params.append(f"{pname}={param.default!r}")
                else:
                    params.append(pname)
            sigs[name] = f"{name}({', '.join(params)})"
        except Exception:
            sigs[name] = f"{name}(...)"

    _TOOL_SIGNATURES_CACHE = sigs
    return sigs


def _format_tool_signatures_text() -> str:
    """格式化工具签名为可读文本（用于错误消息）。"""
    sigs = _build_tool_signatures()
    if not sigs:
        return "（无可用工具）"
    lines = ["可用工具签名："]
    for name, sig in sigs.items():
        lines.append(f"  - {sig}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# 错误分类系统
# ──────────────────────────────────────────────────────────────

class ErrorCategory(Enum):
    """代码执行错误分类。

    用于决定重试策略：
    - NAME_ERROR / TYPE_ERROR: 可自动修复，重试
    - TOOL_EXECUTION_ERROR: 工具内部错误，可重试
    - TIMEOUT: 增加超时时间后重试
    - SAFETY_VIOLATION: 不可恢复，直接拒绝
    - SYNTAX_ERROR: LLM 语法问题，不重试（自动修复意义不大）
    - RUNTIME_ERROR: 其他错误，不重试
    """
    NAME_ERROR = "name_error"
    TYPE_ERROR = "type_error"
    TOOL_EXECUTION_ERROR = "tool_error"
    TIMEOUT = "timeout"
    SYNTAX_ERROR = "syntax_error"
    SAFETY_VIOLATION = "safety"
    RUNTIME_ERROR = "runtime"
    UNKNOWN = "unknown"


def _extract_error_type(error_msg: str) -> str:
    """从错误消息中提取异常类型名。

    格式: "ExceptionType: message" → "ExceptionType"
    """
    if not error_msg:
        return "Unknown"
    # execute_code 返回格式: "ExceptionType: message"
    parts = error_msg.split(":", 1)
    return parts[0].strip() if parts else "Unknown"


def classify_error(error_msg: str, error_type: str) -> ErrorCategory:
    """将执行错误分类为 ErrorCategory。

    Args:
        error_msg: 完整错误消息（如 "NameError: name 'foo' is not defined"）
        error_type: 提取的异常类型名（如 "NameError"）

    Returns:
        ErrorCategory 枚举值
    """
    error_msg = error_msg or ""
    error_type = error_type or "Unknown"

    if "安全检查失败" in error_msg:
        return ErrorCategory.SAFETY_VIOLATION
    if error_type == "TimeoutError" or "超时" in error_msg:
        return ErrorCategory.TIMEOUT
    if error_type == "NameError":
        return ErrorCategory.NAME_ERROR
    if error_type == "TypeError":
        return ErrorCategory.TYPE_ERROR
    if error_type == "SyntaxError":
        return ErrorCategory.SYNTAX_ERROR

    # 检查是否是工具内部错误（工具函数被实际调用时出现在错误消息中）
    # 要求匹配 tool_name( 模式，避免误匹配（如变量名包含工具名子串）
    tool_names = set(_get_tool_functions().keys())
    for tool_name in tool_names:
        if f"{tool_name}(" in error_msg:
            return ErrorCategory.TOOL_EXECUTION_ERROR

    return ErrorCategory.RUNTIME_ERROR


# ──────────────────────────────────────────────────────────────
# 自动修复引擎
# ──────────────────────────────────────────────────────────────

def _edit_distance(s1: str, s2: str) -> int:
    """Levenshtein 编辑距离（动态规划）。

    用于工具名拼写纠错：计算用户写的名字与可用工具名的相似度。
    """
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def _find_closest_name(name: str, candidates: list, max_distance: int = 3) -> str:
    """基于编辑距离查找最接近的名称。

    Args:
        name: 用户写的名称（可能有拼写错误）
        candidates: 可用名称列表
        max_distance: 最大允许编辑距离（超过则认为不匹配）

    Returns:
        最接近的名称，如果距离超过 max_distance 则返回原名
    """
    best, best_dist = None, max_distance + 1
    for c in candidates:
        d = _edit_distance(name.lower(), c.lower())
        if d < best_dist:
            best, best_dist = c, d
    return best if best_dist <= max_distance else name


def _fix_name_error(code: str, error_msg: str) -> tuple:
    """修复工具名拼写错误（基于编辑距离）。

    从 NameError 消息中提取未定义的名称，在可用工具名中查找最接近的匹配。
    例如: "name 'knowlege_search' is not defined" → 修正为 "knowledge_search"

    Returns:
        (fixed_code, fix_description) 元组
    """
    match = re.search(r"name '(\w+)' is not defined", error_msg)
    if not match:
        return code, ""
    wrong_name = match.group(1)

    available_names = list(_get_tool_functions().keys())
    best_match = _find_closest_name(wrong_name, available_names)
    if best_match and best_match != wrong_name:
        # 使用单词边界正则替换，避免子字符串误替换
        # 例如 wrong_name="todo_ge" 不会误替换已有的 "todo_get"
        fixed = re.sub(rf"\b{re.escape(wrong_name)}\b", best_match, code)
        return fixed, f"自动修正: {wrong_name} → {best_match}"
    return code, ""


def _fix_type_error(code: str, error_msg: str) -> tuple:
    """修复 TypeError（参数签名不匹配）。

    策略：不修改代码，而是在代码头部注入参数签名提示注释，
    让 LLM 下次重试时能看到正确的参数名。

    Returns:
        (fixed_code, fix_description) 元组
    """
    # 从 TypeError 消息中提取函数名
    # 格式: "func_name() got an unexpected keyword argument 'xxx'"
    # 或:   "func_name() takes N positional arguments but M were given"
    match = re.search(r"(\w+)\(\)", error_msg)
    if not match:
        return code, ""
    func_name = match.group(1)

    sigs = _build_tool_signatures()
    if func_name in sigs:
        # 在代码头部注入签名提示（不影响执行，只是注释）
        hint_marker = f"# 💡 提示: {func_name}"
        # 检查是否已有该函数的提示注释（避免重复添加，但允许不同函数的提示）
        if hint_marker not in code:
            hint = f"{hint_marker} 的正确签名是 {sigs[func_name]}\n"
            return hint + code, f"注入参数签名提示: {sigs[func_name]}"

    return code, ""


def _fix_tool_error(code: str, error_msg: str) -> tuple:
    """修复工具内部执行错误。

    策略：在代码头部注入错误上下文提示，让 LLM 下次重试时能看到具体错误。
    不直接修改代码逻辑（避免引入新错误）。

    Returns:
        (fixed_code, fix_description) 元组
    """
    # 截取错误消息的关键部分（最多 200 字符）
    error_preview = error_msg[:200].replace('\n', ' ')
    hint = f"# 💡 上次执行此工具时报错: {error_preview}\n"
    if "# 💡 上次执行此工具时报错:" not in code:
        return hint + code, f"注入工具错误上下文"
    return code, ""


def _auto_fix_code(code: str, error_msg: str, category: ErrorCategory) -> tuple:
    """尝试自动修复代码。

    根据错误类型选择修复策略：
    - NameError: 工具名拼写纠错（编辑距离）
    - TypeError: 在代码头部注入参数签名提示
    - ToolExecutionError: 在代码头部注入错误上下文
    - 其他: 不修复

    Args:
        code: 原始代码
        error_msg: 错误消息
        category: 错误分类

    Returns:
        (fixed_code, fix_description) 元组，如果无法修复则返回原代码
    """
    if category == ErrorCategory.NAME_ERROR:
        return _fix_name_error(code, error_msg)
    if category == ErrorCategory.TYPE_ERROR:
        return _fix_type_error(code, error_msg)
    if category == ErrorCategory.TOOL_EXECUTION_ERROR:
        return _fix_tool_error(code, error_msg)
    return code, ""


# ──────────────────────────────────────────────────────────────
# 带重试的代码执行
# ──────────────────────────────────────────────────────────────

def execute_code_with_retry(code: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """带自动修复重试的代码执行。

    流程：
    1. 首次执行
    2. 失败 → 分类错误 → 自动修复 → 重试（最多 MAX_AUTO_RETRIES 次）
    3. 返回最终结果 + 执行历史

    Args:
        code: 要执行的 Python 代码
        timeout: 超时时间（秒）

    Returns:
        {
            "success": bool,
            "output": str,
            "error": str|None,
            "duration_ms": float,
            "execution_history": [...],  # 每次尝试的记录
            "auto_fixed": bool,          # 是否经过自动修复后成功
        }
    """
    execution_history = []
    current_code = code
    current_timeout = timeout
    total_start = time.perf_counter()

    for attempt in range(MAX_AUTO_RETRIES + 1):
        result = execute_code(current_code, timeout=current_timeout)

        history_entry = {
            "attempt": attempt + 1,
            "code_preview": current_code[:200].replace('\n', ' '),
            "success": result["success"],
            "error": result.get("error"),
            "duration_ms": result["duration_ms"],
        }

        if result["success"]:
            history_entry["fix"] = None
            execution_history.append(history_entry)
            total_duration_ms = (time.perf_counter() - total_start) * 1000
            return {
                **result,
                "duration_ms": total_duration_ms,  # 总耗时（含重试）
                "execution_history": execution_history,
                "auto_fixed": attempt > 0,
            }

        execution_history.append(history_entry)

        # 最后一次尝试失败，不再修复
        if attempt >= MAX_AUTO_RETRIES:
            break

        # 分类错误
        error_type = _extract_error_type(result["error"])
        category = classify_error(result["error"], error_type)
        history_entry["error_category"] = category.value

        # 不可恢复错误，直接放弃
        if category in (ErrorCategory.SAFETY_VIOLATION, ErrorCategory.SYNTAX_ERROR):
            break

        # 超时重试：增加 50% 超时时间（最多重试 1 次超时）
        if category == ErrorCategory.TIMEOUT:
            if attempt == 0:  # 只增加一次超时
                current_timeout = min(int(current_timeout * 1.5), 30)  # 上限 30s
                history_entry["fix"] = f"增加超时时间到 {current_timeout}s"
            else:
                break
            continue

        # 尝试自动修复
        fixed_code, fix_desc = _auto_fix_code(
            current_code, result["error"] or "", category
        )
        if fixed_code == current_code or not fix_desc:
            break  # 无法修复
        history_entry["fix"] = fix_desc
        current_code = fixed_code

    total_duration_ms = (time.perf_counter() - total_start) * 1000
    return {
        **result,
        "duration_ms": total_duration_ms,
        "execution_history": execution_history,
        "auto_fixed": False,
    }


def _build_error_message(result: dict) -> str:
    """构建面向 LLM 的错误消息（包含修复建议和工具签名）。

    当代码执行最终失败时，返回结构化的错误信息，帮助 LLM 理解问题并修正。
    """
    error = result.get("error", "未知错误")
    history = result.get("execution_history", [])
    attempt_count = len(history)

    parts = []

    # 头部
    if attempt_count > 1:
        parts.append(f"❌ 代码执行失败（自动修复 {attempt_count - 1} 次后仍失败）")
    else:
        parts.append(f"❌ 代码执行失败")

    # 修复历史摘要
    fixes = [h.get("fix", "") for h in history if h.get("fix")]
    if fixes:
        parts.append("\n已尝试的修复：")
        for i, fix in enumerate(fixes, 1):
            parts.append(f"  {i}. {fix}")

    # 最后一次错误
    parts.append(f"\n最后一次错误: {error}")

    # 工具签名提示（帮助 LLM 修正参数）
    error_type = _extract_error_type(error)
    category = classify_error(error, error_type)
    if category in (ErrorCategory.TYPE_ERROR, ErrorCategory.NAME_ERROR,
                    ErrorCategory.TOOL_EXECUTION_ERROR):
        parts.append(f"\n{_format_tool_signatures_text()}")
        parts.append("\n请检查工具名称和参数后重试。")

    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────
# 代码执行
# ──────────────────────────────────────────────────────────────

def execute_code(code: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """在受限环境中执行代码。

    Args:
        code: 要执行的 Python 代码
        timeout: 超时时间（秒）

    Returns:
        {"success": bool, "output": str, "error": str|None, "duration_ms": float, "log_file": str|None}
    """
    output_buffer = io.StringIO()
    start_time = time.perf_counter()

    # 获取当前用户 ID 和 thread_id（用于权限过滤和日志文件命名）
    user_id = None
    thread_id = None
    try:
        from backend.hermes_adapter import _CURRENT_USER_ID_CTX, _THREAD_ID_CTX
        user_id = _CURRENT_USER_ID_CTX.get()
        thread_id = _THREAD_ID_CTX.get()
    except Exception as e:
        logger.debug(f"获取 user_id/thread_id 失败（可能非对话上下文）: {e}")

    # 构建执行环境（根据用户权限过滤工具）
    safe_globals = build_safe_globals(user_id=user_id)

    # 创建共享的字符计数器（用于截断保护）
    total_chars_ref = [0]
    capture_session = get_capture_session()
    capture_sink = capture_session.new_attempt() if capture_session is not None else None

    # 创建日志函数（关键节点日志 vs 详细日志）
    log, log_debug, log_file_path = create_log_functions(
        output_buffer=output_buffer,
        user_id=user_id,
        thread_id=thread_id,
        total_chars_ref=total_chars_ref,
        capture_sink=capture_sink,
    )

    # 注入函数到执行环境
    safe_globals["print"] = create_safe_print(output_buffer, total_chars_ref, capture_sink)
    safe_globals["log"] = log
    safe_globals["log_debug"] = log_debug

    # 获取当前上下文（用于传递到执行线程）
    ctx = contextvars.copy_context()
    capture_reason = "cancelled"

    try:
        # 在线程池中执行代码（读取时加锁，避免与退役重建竞争）
        with _POOL_LOCK:
            _pool = _executor
        future = _pool.submit(ctx.run, exec, code, safe_globals, {})
        future.result(timeout=timeout)
        success = True
        error = None
        capture_reason = "completed"
    except FuturesTimeoutError:
        success = False
        error = f"代码执行超时（{timeout}s）"
        capture_reason = "timeout"
        # Freeze capture before retiring the pool: the old worker may keep
        # running, but late writes cannot alter this attempt or a retry.
        if capture_sink is not None:
            capture_sink.close("timeout")
        # 执行中的线程无法被强杀；cancel() 只对"尚未开始执行"的任务有效
        # （例如排在 8 个跑飞任务后面的任务），这里仍有意义。
        future.cancel()
        # 跑飞的代码会永久占住一个 worker —— 退役并重建池，否则 8 次超时之后
        # Code Mode 会对所有用户永久失效（实测可复现）。
        _retire_poisoned_executor()
        # 记录警告，便于监控和排查
        code_preview = code[:80].replace('\n', ' ')
        logger.warning(f"Code Mode 超时: timeout={timeout}s, code_preview={code_preview}")
    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {e}"
        capture_reason = "error"
    finally:
        if capture_sink is not None:
            capture_sink.close(capture_reason)

    duration_ms = (time.perf_counter() - start_time) * 1000

    # 获取输出，应用总输出限制
    output = output_buffer.getvalue()
    if len(output) > MAX_TOTAL_OUTPUT:
        output = output[:MAX_TOTAL_OUTPUT] + "\n\n[TOTAL OUTPUT TRUNCATED]..."

    return {
        "success": success,
        "output": output,
        "error": error,
        "duration_ms": duration_ms,
        "log_file": log_file_path,  # 详细日志文件路径
    }


# ──────────────────────────────────────────────────────────────
# Pydantic Schema
# ──────────────────────────────────────────────────────────────

class CodeExecutionInput(BaseModel):
    """run_python 工具的输入参数"""
    code: str = Field(description="要执行的 Python 代码")
    timeout: int = Field(default=15, description="执行超时时间（秒），默认 15")


# ──────────────────────────────────────────────────────────────
# run_python 工具定义
# ──────────────────────────────────────────────────────────────

@tool(args_schema=CodeExecutionInput)
def run_python(code: str, timeout: int = 15) -> str:
    """执行 Python 代码来组合调用工具函数。

    适用场景：
      - 需要多次调用工具并汇总结果
      - 需要对数据做简单处理
      - 需要条件判断或循环处理

    可用函数：
      - knowledge_search(query, top_k=5) -> str (格式化文本)
      - sql_query(query) -> str (格式化表格，只允许 SELECT)
      - get_current_time(format="%Y-%m-%d %H:%M:%S") -> str
      - todo_add(title, description) -> str
      - todo_update(task_id, status) -> str
      - todo_get() -> str
      - cronjob_create(name, prompt, ...) -> str
      - list_delivery_configs() -> str
      - when_resolve(phrase) -> str
      - read_file(path, offset=1, limit=500) -> str (读取文件内容，带行号)
      - search_files(pattern, target="content", path=".", file_glob=None, limit=50) -> str (搜索文件或内容)
      - log(message, level="info") -> None (记录关键节点日志，返回给 Agent)
      - log_debug(message) -> None (记录详细调试日志，写入文件)

    日志最佳实践：
      ⚠️ 重要：请在代码中使用 log() 和 log_debug() 函数记录执行过程！

      - log(msg, level="info"): 记录**关键节点**，会返回给你（进入上下文）
        适用：任务开始/完成、重要决策、错误、结果摘要

      - log_debug(msg): 记录**详细过程**，写入文件（不进上下文）
        适用：循环内日志、中间数据、性能计时、调试信息

      示例：
        log("开始检索知识库...", level="info")
        for i, query in enumerate(queries):
            result = knowledge_search(query)
            log_debug(f"查询 {i+1}: {query}, 结果长度: {len(result)}")
        log("✅ 检索完成，共处理 3 个查询", level="success")

    示例：
      # 直接输出工具结果（工具返回格式化文本）
      result = knowledge_search("主机告警")
      print(result[:2000])  # 输出前 2000 字符

      # 多次调用并记录日志
      log("开始查询", level="info")
      for i in range(3):
          t = get_current_time()
          log_debug(f"第 {i+1} 次: {t}")
      log("✅ 查询完成", level="success")

      # 读取多个文件
      files = ["backend/tools/code_executor.py", "backend/tools/tools_decorator.py"]
      for f in files:
          content = read_file(f, limit=100)
          log_debug(f"读取 {f}, 行数: {len(content.split(chr(10)))}")

      # 搜索并汇总
      patterns = ["milvus", "vector", "embedding"]
      for p in patterns:
          results = search_files(p, target="content", file_glob="*.py")
          log_debug(f"搜索 '{p}': {len(results.split(chr(10)))} 处匹配")

    注意：
      - 工具返回的是**格式化文本**，直接 print 即可
      - 代码无法 import 模块或访问文件系统
      - 只有 print() 和 log() 的输出会返回给你
      - 单次 print 最大 16K 字符，总输出最大 32K 字符
      - 如果代码出错，系统会自动尝试修复并重试（最多 2 次）
      - 默认超时 15 秒，可通过 timeout 参数调整
    """
    # 1. 入口日志
    code_preview = code[:100].replace('\n', ' ')
    logger.info(f"🔧 [Code Mode] 开始执行: timeout={timeout}s, code_preview={code_preview}...")
    
    # 2. AST 安全检查
    is_safe, error_msg = check_ast_safety(code)
    if not is_safe:
        logger.warning(f"Code Mode 安全检查失败: {error_msg}, code_preview={code[:100]}")
        _stats.record_safety_rejection()
        return f"❌ 代码安全检查失败: {error_msg}"

    # 3. 带自动修复重试的代码执行
    result = execute_code_with_retry(code, timeout=timeout)

    # 4. 统计记录
    _stats.record_call(result["success"], result["duration_ms"])
    # 精确判断是否有实际的代码修复尝试（history 中有 "fix" 字段且不是超时调整）
    has_fix_attempt = any(
        h.get("fix") and not h["fix"].startswith("增加超时时间")
        for h in result.get("execution_history", [])
    )
    if result.get("auto_fixed"):
        _stats.record_auto_fix(success=True)
    elif has_fix_attempt:
        _stats.record_auto_fix(success=False)

    # 5. 结构化日志（P4 可观测性 — 便于日志采集系统解析）
    code_preview = code[:100].replace('\n', ' ')
    auto_fix_info = ""
    if result.get("auto_fixed"):
        auto_fix_info = " auto_fixed=true"
    elif result.get("execution_history") and len(result["execution_history"]) > 1:
        auto_fix_info = " auto_fix_failed=true"
    _code_mode_logger.info(
        f"code_mode_complete | success={result['success']} "
        f"output_len={len(result['output'])} duration={result['duration_ms']:.1f}ms "
        f"attempts={len(result.get('execution_history', []))}"
        f"{auto_fix_info} code_preview={code_preview}"
    )
    logger.info(
        f"✅ [Code Mode] 执行完成: success={result['success']}, "
        f"output_len={len(result['output'])}, duration={result['duration_ms']:.1f}ms, "
        f"attempts={len(result.get('execution_history', []))}{auto_fix_info}"
    )

    # 6. Trace span 记录（P4 — 接入可观测性面板）
    try:
        from backend.hermes_adapter import _CURRENT_USER_ID_CTX
        from backend.observer.trace_observer import _registered_observers
        user_id = _CURRENT_USER_ID_CTX.get()
        observer = _registered_observers.get(int(user_id)) if user_id else None
        if observer:
            trace_id = observer._find_current_trace()
            if trace_id:
                from backend.service.trace import write as trace_service
                span_status = 1 if result["success"] else 2
                err_msg = "" if result["success"] else (result.get("error") or "")[:500]
                trace_service.record_span(
                    trace_id=trace_id,
                    tool_name="run_python",
                    duration_ms=int(result["duration_ms"]),
                    status=span_status,
                    error_message=err_msg,
                    span_type="code_mode",
                )
    except Exception as e:
        logger.debug(f"Code Mode trace span 记录失败（不影响功能）: {e}")

    # 7. 返回结果
    if result["success"]:
        output = result["output"]

        # 添加日志文件路径提示
        log_file = result.get("log_file")
        log_hint = ""
        if log_file:
            # 获取相对路径（更友好）
            try:
                import os
                rel_path = os.path.relpath(log_file, _get_project_root())
                log_hint = f"\n\n📝 详细日志: {rel_path}"
            except Exception:
                log_hint = f"\n\n📝 详细日志: {log_file}"

        if result.get("auto_fixed"):
            # 附加自动修复摘要（帮助 LLM 了解发生了什么）
            history = result.get("execution_history", [])
            fixes = [h.get("fix", "") for h in history if h.get("fix")]
            if fixes:
                fix_summary = "（经自动修正: " + "; ".join(fixes) + "）"
                base = f"{output}\n\n{fix_summary}" if output else f"✅ 代码执行成功（无输出）\n\n{fix_summary}"
                return base + log_hint
        return (output if output else "✅ 代码执行成功（无输出）") + log_hint
    else:
        return _build_error_message(result)


# Code Mode 工具，所有用户可用
run_python._toolset = "__always_available__"
