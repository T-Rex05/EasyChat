"""报告文件命名规范（借鉴 Eyes report_naming）

统一命名：{安全任务名}_{时间戳}.{ext} —— 同任务多次执行不互相覆盖，按时间可排序。
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def _convert_box_drawing(text: str) -> str:
    """将 Unicode box-drawing 字符转换为 ASCII 等效字符。"""
    box_chars = {
        '\u2500': '-', '\u2501': '=', '\u2502': '|', '\u2503': '|',
        '\u250c': '+', '\u250d': '+', '\u250e': '+', '\u250f': '+',
        '\u2510': '+', '\u2511': '+', '\u2512': '+', '\u2513': '+',
        '\u2514': '+', '\u2515': '+', '\u2516': '+', '\u2517': '+',
        '\u2518': '+', '\u2519': '+', '\u251a': '+', '\u251b': '+',
        '\u251c': '+', '\u251d': '+', '\u251e': '+', '\u251f': '+',
        '\u2520': '+', '\u2521': '+', '\u2522': '+', '\u2523': '+',
        '\u2524': '+', '\u2525': '+', '\u2526': '+', '\u2527': '+',
        '\u2528': '+', '\u2529': '+', '\u252a': '+', '\u252b': '+',
        '\u253c': '+', '\u253d': '+', '\u253e': '+', '\u253f': '+',
        '\u2540': '+', '\u2541': '+', '\u2542': '+', '\u2543': '+',
        '\u2544': '+', '\u2545': '+', '\u2546': '+', '\u2547': '+',
        '\u2548': '+', '\u2549': '+', '\u254a': '+', '\u254b': '+',
        '\u2550': '=', '\u2551': '|',
        '\u2554': '+', '\u2555': '+', '\u2556': '+', '\u2557': '+',
        '\u2558': '+', '\u2559': '+', '\u255a': '+', '\u255b': '+',
        '\u255c': '+', '\u255d': '+', '\u255e': '+', '\u255f': '+',
        '\u2560': '+', '\u2561': '+', '\u2562': '+', '\u2563': '+',
        '\u2564': '+', '\u2565': '+', '\u2566': '+', '\u2567': '+',
        '\u2568': '+', '\u2569': '+', '\u256a': '+', '\u256b': '+',
        '\u256c': '+',
        '\u256d': '+', '\u256e': '+', '\u256f': '+', '\u2570': '+',
        '\u2571': '/', '\u2572': '\\', '\u2573': 'X',
    }
    result = text
    for box, ascii_char in box_chars.items():
        result = result.replace(box, ascii_char)
    return result


def safe_task_name(name: str) -> str:
    """任务名 → 安全文件名片段。

    - 移除控制字符和特殊字符
    - 转换 box-drawing 字符
    - 移除 emoji
    - 限制长度
    """
    safe = str(name or "")
    # 移除控制字符
    safe = re.sub(r'[\x00-\x1f\x7f]', '', safe)
    # 替换不允许的文件名字符
    safe = re.sub(r'[\\/:*?"<>|]', '_', safe)
    # 移除 emoji 和其他辅助平面字符
    safe = re.sub(r'[\U00010000-\U0010ffff]', '', safe)
    # 转换 box-drawing 字符
    safe = _convert_box_drawing(safe)
    # 清理空白和点
    safe = safe.strip().rstrip(".") or "report"
    # 压缩多个下划线
    safe = re.sub(r'_+', '_', safe)
    return safe[:80]


def build_report_filename(task_name: str, timestamp: Optional[datetime] = None, ext: str = ".md") -> str:
    """构造统一报告文件名：{任务名}_{YYYYMMDD_HHMMSS}{ext}。"""
    ts = timestamp or datetime.now()
    stem = safe_task_name(task_name)
    ext = ext if ext.startswith(".") else f".{ext}"
    return f"{stem}_{ts.strftime('%Y%m%d_%H%M%S')}{ext}"


def build_report_path(report_dir: Path, task_name: str, timestamp: Optional[datetime] = None, ext: str = ".md") -> Path:
    """在报告目录下构造统一命名路径（自动建目录）。"""
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / build_report_filename(task_name, timestamp, ext)