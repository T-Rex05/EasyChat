"""微信监听器 - 文本处理"""
import re

# 微信消息长度限制
_WEIXIN_MAX_CHARS = 1800
_FENCE_RE = re.compile(r"^```([^\n`]*)\s*$")


def _strip_md(text: str) -> str:
    """
    微信 ClawBot MD 兼容转换 - 保守策略
    
    ClawBot 能渲染 **bold**、*italic*、~~strike~~、[link](url)、>quote、
    列表、```代码块```。这些原样保留不处理。
    
    只转换 ClawBot 不支持或显示不佳的：
    - # 标题 → 【标题】
    - ##+ 标题 → **标题** (触发加粗)
    - 表格 → - key: value
    - 任务列表 → ☑/☐
    - --- 分隔线 → ──────── (全角)
    """
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    in_table = False
    table_headers: list[str] = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # ── 代码块：原样保留（ClawBot 可渲染）──
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                if out and out[-1] != "":
                    out.append("")
                out.append(line)
            else:
                out.append(line)
                out.append("")
                in_code = False
            continue
        
        if in_code:
            out.append(line)
            continue
        
        if not stripped:
            out.append("")
            in_table = False
            continue
        
        # ── 任务列表 [-*+] [xX] → ☑/☐ ──
        tm = re.match(r"^[\s]*[-*+]\s+\[([ xX])\]\s+(.*)", stripped)
        if tm:
            check = "☑" if tm.group(1).lower() == "x" else "☐"
            out.append(f"{check} {tm.group(2)}")
            continue
        
        # ── 表格检测 ──
        is_table_line = stripped.count("|") >= 2
        if is_table_line:
            is_sep = bool(re.match(r"^[\s\|:\-]+$", stripped))
            if is_sep:
                continue  # 跳过分隔行 |---|---|
            # 看下一行是不是分隔行
            next_is_sep = (i + 1 < len(lines) and
                          lines[i + 1].strip().count("|") >= 1 and
                          bool(re.match(r"^[\s\|:\-]+$", lines[i + 1].strip())))
            if next_is_sep:
                # 当前行是表头
                table_headers = [c.strip() for c in stripped.split("|") if c.strip()]
                in_table = True
                continue
            if in_table:
                # 数据行
                cells = [c.strip() for c in stripped.split("|") if c.strip()]
                for h, d in zip(table_headers, cells):
                    out.append(f"- {h}: {d}")
                continue
            # 孤立的含|行，直接展开
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            if len(cells) >= 2:
                out.append(" · ".join(cells))
            continue
        in_table = False
        
        # ── 一级标题 → 【标题】──
        m1 = re.match(r"^# ([^#].*)$", stripped)
        if m1:
            out.append("【" + m1.group(1) + "】")
            continue
        
        # ── 二级及以上标题 → **标题** ──
        m2 = re.match(r"^#{2,}\s+(.*)$", stripped)
        if m2:
            out.append("**" + m2.group(1) + "**")
            continue
        
        # ── 分隔线 ──
        if re.match(r"^[-*_]{3,}$", stripped):
            out.append("─" * 16)
            continue
        
        # ── 其他：原样保留（**bold**, *italic*, ~~strike~~, [link](url), >quote, 列表等）──
        out.append(line)
    
    # 合并多余空行
    result: list[str] = []
    prev_empty = False
    for ln in out:
        if ln == "":
            if not prev_empty:
                result.append(ln)
                prev_empty = True
        else:
            prev_empty = False
            result.append(ln)
    return "\n".join(result).strip()


def _split_markdown_blocks(content: str) -> list[str]:
    """按空行拆分，代码块保持完整"""
    if not content:
        return []
    blocks: list[str] = []
    lines = content.splitlines()
    current: list[str] = []
    in_code = False
    for raw in lines:
        line = raw.rstrip()
        if _FENCE_RE.match(line.strip()):
            if not in_code and current:
                blocks.append("\n".join(current).strip())
                current = []
            current.append(line)
            in_code = not in_code
            if not in_code:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if in_code:
            current.append(line)
            continue
        if not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [b for b in blocks if b]


def _split_text_for_weixin(content: str, max_length: int = _WEIXIN_MAX_CHARS) -> list[str]:
    """将长文本按段落+代码块边界拆分为多条微信消息"""
    if len(content) <= max_length:
        return [content]
    packed: list[str] = []
    current = ""
    for block in _split_markdown_blocks(content):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            packed.append(current)
            current = ""
        if len(block) <= max_length:
            current = block
            continue
        # 单个超大块：硬截断
        while len(block) > max_length:
            split_at = block.rfind("\n", 0, max_length)
            if split_at < max_length // 2:
                split_at = max_length
            packed.append(block[:split_at].strip())
            block = block[split_at:].lstrip("\n")
        if block:
            current = block
    if current:
        packed.append(current)
    return packed or [content]
