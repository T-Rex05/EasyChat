"""
工具输出守卫 —— 即时截断 + 溢出到文件 + Agent 引导 + 溢出文件 TTL 清理

解决的问题：
  工具调用（cat 大文件、SQL 万行返回等）可能产生 200K+ 字符的输出，
  直接进入上下文会导致：
    1. 单轮 token 暴涨（10K → 300K+）
    2. KV Cache 前缀失效（上下文突变，后续所有对话缓存作废）
    3. LLM 迷失（上下文被工具输出填满，忘记用户问题）
    4. 成本失控（后续每轮重复发送超长历史）

设计思路（参考 Claude Code 三层压缩 Tier 1）：
  零 ZLM 成本的即时截断——不让大输出进入上下文：
    1. 即时截断：head+tail 策略（保留开头 40% + 结尾 60%），默认 16K 字符上限
    2. 溢出到文件：完整输出写入 data/tool_outputs/，LLM 可按需 read_file
    3. Agent 引导：附加提示告诉 LLM 完整内容路径和读取方法
    4. TTL 清理：溢出文件 24 小时后自动删除（懒清理 + 显式接口）

集成方式：
  在 hermes_adapter.py 的 _make_project_tool_handler() 中统一包装所有工具返回值，
  不修改 Hermes 源码，对所有工具（含 Hermes 内建工具）生效。
"""

import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 默认配置
# ──────────────────────────────────────────────────────────────

# 单工具输出最大字符数（超出即截断）。
# 16K 字符 ≈ 4K tokens，留足上下文空间给对话历史和系统提示词。
DEFAULT_MAX_CHARS = 16_000

# head+tail 截断比例：保留开头 40%、结尾 60%。
# 开头通常包含结构化数据标题/表头，结尾包含最终结果/统计，
# 中间大段往往是重复性的数据行。
HEAD_RATIO = 0.4

# 溢出文件保存目录（相对于项目 data 目录）
SPILL_SUBDIR = "tool_outputs"

# 溢出文件保留时长（小时）。超过此时间的文件在懒清理中被删除。
SPILL_FILE_TTL_HOURS = 24

# 每 N 次截断触发一次懒清理（避免每次截断都扫描目录）。
_LAZY_CLEANUP_INTERVAL = 50

# 懒清理计数器（线程安全）
_cleanup_counter = 0
_cleanup_counter_lock = threading.Lock()

# 豁免截断的工具名（这些工具的输出需要完整传递给 LLM/前端）
BYPASS_TOOLS = frozenset({
    "todo_add", "todo_update", "todo_get",  # 前端需要完整数据渲染任务面板
    "run_python",  # Code Mode: safe_print 已有独立截断保护（16K 单次 + 32K 总计），无需二次截断
})

# 截断提示模板
_TRUNCATION_HINT = (
    "\n\n[OUTPUT TRUNCATED] 输出已从 {original_len:,} 字符截断至 {truncated_len:,} 字符，"
    "省略了中间 {omitted:,} 字符。\n"
    "完整输出已保存至文件：{spill_path}\n"
    "如需查看特定部分，请使用 read_file 工具读取该路径。"
)


# ──────────────────────────────────────────────────────────────
# 公共接口
# ──────────────────────────────────────────────────────────────

def should_truncate(result: str, tool_name: str) -> bool:
    """判断工具输出是否需要截断。

    Args:
        result: 工具返回的字符串
        tool_name: 工具名称

    Returns:
        True 表示需要截断
    """
    if tool_name in BYPASS_TOOLS:
        return False
    return len(result) > DEFAULT_MAX_CHARS


def truncate_tool_output(
    result: str,
    tool_name: str,
    max_chars: Optional[int] = None,
) -> str:
    """截断超长工具输出，完整内容溢出到文件。

    结构感知截断：
      - JSON 输出：在完整行边界截断，避免切在 key/value 中间
      - CSV/表格：在完整行边界截断
      - 其他：head+tail 字符截断（默认）

    Args:
        result: 工具返回的原始字符串
        tool_name: 工具名称（用于文件名和日志）
        max_chars: 自定义截断阈值（默认使用 DEFAULT_MAX_CHARS）

    Returns:
        截断后的字符串（含溢出文件路径提示），或原始字符串（无需截断时）
    """
    limit = max_chars or DEFAULT_MAX_CHARS
    original_len = len(result)

    if original_len <= limit:
        return result

    # 豁免工具不截断
    if tool_name in BYPASS_TOOLS:
        return result

    # 1. 完整输出溢出到文件
    spill_path = _save_spill_file(result, tool_name)

    # 2. 结构感知截断
    head_size = int(limit * HEAD_RATIO)
    tail_size = limit - head_size

    # 检测格式并尝试结构边界截断
    head, tail = _smart_head_tail(result, head_size, tail_size)
    omitted = original_len - len(head) - len(tail)

    truncated = (
        f"{head}"
        f"\n\n... [{omitted:,} chars omitted] ...\n\n"
        f"{tail}"
    )

    # 3. 附加 Agent 引导提示
    hint = _TRUNCATION_HINT.format(
        original_len=original_len,
        truncated_len=len(truncated),
        omitted=omitted,
        spill_path=spill_path,
    )
    result_with_hint = truncated + hint

    logger.info(
        f"⚡ 工具输出截断 {tool_name}: {original_len:,} → {len(result_with_hint):,} 字符"
        f"（省略 {omitted:,} 字符，完整内容 → {spill_path}）"
    )

    return result_with_hint


# ──────────────────────────────────────────────────────────────
# 内部方法
# ──────────────────────────────────────────────────────────────

def _smart_head_tail(text: str, head_size: int, tail_size: int) -> tuple:
    """结构感知的 head+tail 截断。

    检测文本格式（JSON / CSV / 普通文本），在结构边界（行边界、
    JSON 对象边界）截断，避免切在 key/value 中间或行中间。

    Returns:
        (head, tail) — 截断后的头部和尾部文本
    """
    # 快速路径：如果文本没有换行符，退化为纯字符截断
    if "\n" not in text:
        head = text[:head_size]
        tail = text[-tail_size:] if tail_size > 0 else ""
        return head, tail

    # 尝试在行边界截断
    head = _truncate_at_line_boundary(text, head_size, direction="head")
    tail = _truncate_at_line_boundary(text, tail_size, direction="tail")

    return head, tail


def _truncate_at_line_boundary(text: str, target_size: int, direction: str) -> str:
    """在目标位置附近找到最近的行边界截断。

    Args:
        text: 原始文本
        target_size: 目标字符数
        direction: "head" 从头开始，"tail" 从尾开始

    Returns:
        截断后的文本（在行边界处截断）
    """
    if target_size <= 0:
        return ""

    text_len = len(text)
    if target_size >= text_len:
        return text

    if direction == "head":
        # 从头开始，在 target_size 附近找最后一个换行符
        cutoff = text[:target_size]
        last_newline = cutoff.rfind("\n")
        if last_newline > target_size * 0.7:  # 至少保留 70% 的目标大小
            return text[:last_newline]
        # 找不到合适的行边界，用字符截断
        return cutoff
    else:
        # 从尾开始，在 target_size 附近找第一个换行符
        start = text_len - target_size
        if start < 0:
            start = 0
        cutoff = text[start:]
        first_newline = cutoff.find("\n")
        if first_newline >= 0 and first_newline < target_size * 0.3:
            # 行边界很近，从那里开始
            return text[start + first_newline + 1:]
        # 找不到合适的行边界，用字符截断
        return text[-target_size:] if target_size > 0 else ""

def _get_spill_dir() -> Path:
    """获取溢出文件保存目录。

    优先使用项目 data_dir（通过环境变量 AGENTFORGE_DATA_DIR 配置），
    回退到项目根目录下的 data/。
    """
    data_dir = os.environ.get("AGENTFORGE_DATA_DIR")
    if data_dir:
        spill_dir = Path(data_dir) / SPILL_SUBDIR
    else:
        # 回退：项目根目录/data/tool_outputs
        project_root = Path(__file__).resolve().parent.parent.parent
        spill_dir = project_root / "data" / SPILL_SUBDIR

    spill_dir.mkdir(parents=True, exist_ok=True)
    return spill_dir


def _save_spill_file(content: str, tool_name: str) -> str:
    """将完整输出保存到文件，返回文件路径。

    文件名格式：{tool_name}_{timestamp}_{short_uuid}.txt
    - timestamp: 精确到秒，方便按时间查找
    - short_uuid: 4 位随机后缀，防止同一秒多次调用同名工具时冲突
    """
    spill_dir = _get_spill_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:4]
    # 清理工具名中的非法文件名字符
    safe_name = re.sub(r'[^\w\-]', '_', tool_name)
    filename = f"{safe_name}_{timestamp}_{short_id}.txt"
    filepath = spill_dir / filename

    try:
        filepath.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.warning(f"溢出文件写入失败: {e}")
        return f"(写入失败: {e})"

    # 触发懒清理（每 N 次截断扫描一次目录，删除过期文件）
    _maybe_lazy_cleanup()

    return str(filepath)


# ──────────────────────────────────────────────────────────────
# 溢出文件 TTL 清理
# ──────────────────────────────────────────────────────────────

def _maybe_lazy_cleanup() -> None:
    """每 _LAZY_CLEANUP_INTERVAL 次截断触发一次后台清理。

    非阻塞：在后台线程中执行清理，不阻塞截断操作本身。
    """
    global _cleanup_counter
    with _cleanup_counter_lock:
        _cleanup_counter += 1
        if _cleanup_counter < _LAZY_CLEANUP_INTERVAL:
            return
        _cleanup_counter = 0

    # 后台线程清理，避免阻塞主流程
    try:
        t = threading.Thread(
            target=cleanup_spill_files,
            kwargs={"max_age_hours": SPILL_FILE_TTL_HOURS, "_background": True},
            daemon=True,
        )
        t.start()
    except Exception as e:
        logger.debug(f"懒清理线程启动失败: {e}")


def cleanup_spill_files(max_age_hours: float = SPILL_FILE_TTL_HOURS, *, _background: bool = False) -> int:
    """删除超过 max_age_hours 的溢出文件。返回删除的文件数。

    可由外部 cron 任务显式调用，也由懒清理机制自动触发。

    Args:
        max_age_hours: 文件保留时长（小时），默认 24 小时
        _background: 内部标记，True 时异常只记日志不抛出

    Returns:
        删除的文件数量
    """
    try:
        spill_dir = _get_spill_dir()
        if not spill_dir.exists():
            return 0

        cutoff = time.time() - (max_age_hours * 3600)
        deleted = 0

        for f in spill_dir.iterdir():
            if not f.is_file():
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except Exception as e:
                logger.debug(f"溢出文件清理跳过 {f.name}: {e}")

        if deleted > 0:
            logger.info(f"[SpillCleanup] 清理 {deleted} 个过期溢出文件（>{max_age_hours}h）")
        return deleted

    except Exception as e:
        if _background:
            logger.debug(f"[SpillCleanup] 后台清理失败: {e}")
            return 0
        raise
