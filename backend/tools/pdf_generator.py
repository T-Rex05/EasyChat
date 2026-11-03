"""
通用数据分析报告 PDF 生成工具
对齐 eyes-agent 的 canvas 封面 + 绿色系配色 + LongTable + 宽表格转卡片 + 统计图插入方案。
支持 markdown 内容解析（标题/列表/代码块/表格/引用/图表引用）。
"""
import os
import platform
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.utils.log_utils import log


def _runtime_project_root() -> str:
    """解析项目根目录（用于把 /static/charts/*.png 转为绝对路径）。"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _safe_report_filename(title: str, extension: str = "pdf") -> str:
    """生成安全的报告文件名。"""
    base = str(title or "数据分析报告").replace("\r", " ").replace("\n", " ").strip()
    base = re.sub(r'[\U00010000-\U0010ffff]', '', base)
    base = re.sub(r'[\\/:*?"<>|｜#`]+', '_', base)
    base = re.sub(r'\s+', '_', base).strip('._ ')
    if not base:
        base = "数据分析报告"
    if len(base) > 80:
        base = base[:80].rstrip('._ ')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:6]
    return f"{base}_{timestamp}_{unique}.{extension.lstrip('.')}"


def _resolve_base_font() -> str:
    """按平台解析中文字体。"""
    system = platform.system()
    if system == "Windows":
        font_candidates = [
            ('C:\\Windows\\Fonts\\msyh.ttc', 'MicrosoftYaHei'),
            ('C:\\Windows\\Fonts\\simhei.ttf', 'SimHei'),
            ('C:\\Windows\\Fonts\\simsun.ttc', 'SimSun'),
        ]
    elif system == "Darwin":
        font_candidates = [
            ('/System/Library/Fonts/PingFang.ttc', 'PingFang'),
            ('/System/Library/Fonts/STHeiti Light.ttc', 'STHeiti'),
        ]
    else:
        font_candidates = [
            ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 'WenQuanYiZenHei'),
            ('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', 'WenQuanYiMicroHei'),
            ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'DejaVuSans'),
        ]

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    base_font = 'Helvetica'
    for font_path, font_name in font_candidates:
        try:
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                base_font = font_name
                log.debug(f"[PDF] 已注册字体: {font_name}")
                break
        except Exception as exc:
            log.debug(f"[PDF] 字体注册失败: {font_name}, {exc}")

    if base_font == 'Helvetica':
        log.warning("[PDF] 未找到中文字体，中文可能显示异常")
    return base_font


def _wrap_canvas_text(text: str, font_name: str, font_size: float, max_width: float, max_lines: int) -> list:
    """Canvas 文本自动换行。"""
    from reportlab.pdfbase import pdfmetrics

    tokens = re.findall(r'[A-Za-z0-9_./:%+-]+|\s+|.', text)
    lines = []
    current = ""
    for token in tokens:
        if token.isspace():
            token = " "
        probe = current + token
        if current and pdfmetrics.stringWidth(probe, font_name, font_size) > max_width:
            lines.append(current.rstrip())
            current = token.lstrip()
            if len(lines) >= max_lines:
                break
        else:
            current = probe
    if len(lines) < max_lines and current.strip():
        lines.append(current.strip())
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    rendered = "".join(lines)
    if len(rendered) < len(text.strip()) and lines:
        last = lines[-1].rstrip(" .。")
        while pdfmetrics.stringWidth(last + "...", font_name, font_size) > max_width and last:
            last = last[:-1]
        lines[-1] = last + "..."
    return lines or ["报告"]


def _convert_box_drawing(text: str) -> str:
    """将 Unicode box-drawing 字符转换为 ASCII 等效字符。

    这些字符（如 │, ┌, ─, ┐, ├, ┤, └, ┘）在 PDF 的 Courier 字体中无法正确渲染，
    转换为 ASCII 字符（|, +, -）确保可读性。
    """
    box_chars = {
        '\u2500': '-', '\u2501': '=',  # horizontal
        '\u2502': '|', '\u2503': '|',  # vertical
        '\u250c': '+', '\u250d': '+', '\u250e': '+', '\u250f': '+',  # corners
        '\u2510': '+', '\u2511': '+', '\u2512': '+', '\u2513': '+',
        '\u2514': '+', '\u2515': '+', '\u2516': '+', '\u2517': '+',
        '\u2518': '+', '\u2519': '+', '\u251a': '+', '\u251b': '+',
        '\u251c': '+', '\u251d': '+', '\u251e': '+', '\u251f': '+',  # T-junctions
        '\u2520': '+', '\u2521': '+', '\u2522': '+', '\u2523': '+',
        '\u2524': '+', '\u2525': '+', '\u2526': '+', '\u2527': '+',
        '\u2528': '+', '\u2529': '+', '\u252a': '+', '\u252b': '+',
        '\u253c': '+', '\u253d': '+', '\u253e': '+', '\u253f': '+',  # crosses
        '\u2540': '+', '\u2541': '+', '\u2542': '+', '\u2543': '+',
        '\u2544': '+', '\u2545': '+', '\u2546': '+', '\u2547': '+',
        '\u2548': '+', '\u2549': '+', '\u254a': '+', '\u254b': '+',
        '\u2550': '=', '\u2551': '|',  # double lines
        '\u2554': '+', '\u2555': '+', '\u2556': '+', '\u2557': '+',
        '\u2558': '+', '\u2559': '+', '\u255a': '+', '\u255b': '+',
        '\u255c': '+', '\u255d': '+', '\u255e': '+', '\u255f': '+',
        '\u2560': '+', '\u2561': '+', '\u2562': '+', '\u2563': '+',
        '\u2564': '+', '\u2565': '+', '\u2566': '+', '\u2567': '+',
        '\u2568': '+', '\u2569': '+', '\u256a': '+', '\u256b': '+',
        '\u256c': '+',
        '\u256d': '+', '\u256e': '+', '\u256f': '+', '\u2570': '+',  # rounded
        '\u2571': '/', '\u2572': '\\', '\u2573': 'X',
    }
    result = text
    for box, ascii_char in box_chars.items():
        result = result.replace(box, ascii_char)
    return result


def _normalize_text(value: str, default: str = "") -> str:
    """清理文本内容。"""
    text = str(value or default)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = _convert_box_drawing(text)
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _inline_markdown(text: str, code_font: str = None) -> str:
    """行内 markdown 转 reportlab XML。
    
    Args:
        text: 要转换的文本
        code_font: 行内代码使用的字体，默认使用中文字体避免乱码
    """
    from xml.sax.saxutils import escape as xml_escape
    safe = xml_escape(str(text or ""))
    # 行内代码：使用指定字体或中文字体（避免中文乱码）
    font_name = code_font or "MicrosoftYaHei"
    safe = re.sub(r'`([^`]+)`', rf'<font name="{font_name}">\1</font>', safe)
    safe = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', safe)
    return safe


def _split_markdown_row(row: str) -> list:
    """分割 markdown 表格行。"""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip().replace(r"\|", "|") for cell in row.split("|")]


def _visual_len(value: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in str(value or ""))


def _table_widths(column_count: int, doc_width: float, headers: list = None) -> list:
    """计算表格列宽（含表头语义智能分配，对齐 eyes-agent）。"""
    if column_count == 1:
        return [doc_width]
    if column_count == 2:
        return [doc_width * 0.30, doc_width * 0.70]
    if column_count == 3:
        return [doc_width * 0.24, doc_width * 0.25, doc_width * 0.51]
    if column_count == 4:
        return [doc_width * 0.22, doc_width * 0.18, doc_width * 0.22, doc_width * 0.38]
    if headers and len(headers) == column_count:
        weights = []
        for header in headers:
            text = str(header or "")
            weight = max(0.9, min(2.8, _visual_len(text) / 5.0))
            if re.search(r"说明|详情|建议|动作|确认|验收|依据|证据|来源|缺口|路径|线索", text):
                weight += 1.3
            if re.search(r"数量|次数|占比|排名|ID$|IP$", text, flags=re.I):
                weight = min(weight, 1.0)
            weights.append(weight)
        total = sum(weights) or column_count
        return [doc_width * weight / total for weight in weights]
    return [doc_width / column_count] * column_count


def generate_report_pdf(subject: str, body: str, output_path: str = None,
                        charts: Optional[list] = None) -> Optional[bytes]:
    """
    生成通用数据分析报告 PDF（对齐 eyes-agent 的正式报告版式）。

    Args:
        subject: 报告标题
        body: markdown 格式的正文内容（可内联 ![](/static/charts/*.png) 图表引用）
        output_path: 输出文件路径（可选，不指定则返回 bytes）
        charts: 额外的图表文件路径列表（可选，作为"可视化图表"章节追加）

    Returns:
        如果 output_path 为 None，返回 PDF bytes；否则返回 None
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.platypus import (
            HRFlowable, Image, LongTable, PageBreak, Paragraph,
            SimpleDocTemplate, Spacer, TableStyle,
        )
    except ImportError:
        log.error("[PDF] reportlab 未安装: pip install reportlab")
        return None

    try:
        # ── 字体 / 日期 / 标题 ──
        base_font = _resolve_base_font()
        generated_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        report_title = _normalize_text(subject, "数据分析报告")
        project_root = _runtime_project_root()

        # ── 绿色系配色（优化可读性）──
        palette = {
            "ink":       colors.HexColor("#0f766e"),  # 深绿色（标题）- 更醒目
            "body":      colors.HexColor("#334155"),  # 正文灰
            "muted":     colors.HexColor("#64748b"),  # 次要文字
            "line":      colors.HexColor("#dbe4ef"),  # 分隔线
            "soft":      colors.HexColor("#f6f8fb"),  # 浅灰背景
            "soft_green": colors.HexColor("#ecfdf5"), # 浅绿背景
            "dark":      colors.HexColor("#134e4a"),  # 封面背景 - 深绿色
            "cyan":      colors.HexColor("#00d992"),  # 强调色
            "green":     colors.HexColor("#10b981"),  # 主绿色
        }

        page_width, page_height = A4

        # ── 样式 ──
        styles = getSampleStyleSheet()

        normal_style = ParagraphStyle(
            'RptNormal', parent=styles['Normal'],
            fontName=base_font, fontSize=10, leading=14.5,
            spaceBefore=1, spaceAfter=4,
            textColor=palette["body"], wordWrap='CJK',
        )
        h1_style = ParagraphStyle(
            'RptH1', parent=normal_style,
            fontSize=15, leading=20, spaceBefore=12, spaceAfter=6,
            textColor=palette["ink"],
        )
        h2_style = ParagraphStyle(
            'RptH2', parent=normal_style,
            fontSize=12, leading=16, spaceBefore=8, spaceAfter=4,
            textColor=palette["ink"],
        )
        h3_style = ParagraphStyle(
            'RptH3', parent=normal_style,
            fontSize=11, leading=15, spaceBefore=6, spaceAfter=3,
            textColor=palette["ink"],
        )
        h4_style = ParagraphStyle(
            'RptH4', parent=normal_style,
            fontSize=10.5, leading=14.5, spaceBefore=5, spaceAfter=3,
            textColor=palette["ink"],
        )
        bullet_style = ParagraphStyle(
            'RptBullet', parent=normal_style,
            leftIndent=14, firstLineIndent=-8, spaceAfter=3,
        )
        note_style = ParagraphStyle(
            'RptNote', parent=normal_style,
            leftIndent=8, rightIndent=8,
            borderColor=palette["line"], borderWidth=0.8, borderPadding=8,
            backColor=palette["soft"],
            textColor=colors.HexColor("#475569"),
        )
        code_style = ParagraphStyle(
            'RptCode', parent=normal_style,
            fontName=base_font, fontSize=8.5, leading=12,
            leftIndent=8, rightIndent=8,
            backColor=colors.HexColor("#f5f5f5"),
            textColor=colors.HexColor("#1e1e1e"),
        )
        th_style = ParagraphStyle(
            'RptTH', parent=normal_style,
            fontSize=8.7, leading=12.6,
            textColor=palette["ink"], wordWrap='CJK',
        )
        td_style = ParagraphStyle(
            'RptTD', parent=normal_style,
            fontSize=8.3, leading=12.2, wordWrap='CJK',
        )
        small_style = ParagraphStyle(
            'RptSmall', parent=normal_style,
            fontSize=8, leading=11, textColor=palette["muted"],
        )
        card_title_style = ParagraphStyle(
            'RptCardTitle', parent=normal_style,
            fontSize=9.6, leading=13.8,
            textColor=palette["ink"], wordWrap='CJK',
        )
        card_label_style = ParagraphStyle(
            'RptCardLabel', parent=normal_style,
            fontSize=8.1, leading=11.8,
            textColor=palette["muted"], wordWrap='CJK',
        )
        card_value_style = ParagraphStyle(
            'RptCardValue', parent=normal_style,
            fontSize=8.8, leading=12.8,
            textColor=palette["body"], wordWrap='CJK',
        )

        # ── 文档 ──
        temp_path = os.path.join(tempfile.gettempdir(), _safe_report_filename(subject))
        doc = SimpleDocTemplate(
            temp_path, pagesize=A4,
            leftMargin=22 * mm, rightMargin=22 * mm,
            topMargin=18 * mm, bottomMargin=18 * mm,
            title=report_title, author='AgentForge',
        )

        story = [PageBreak()]  # 第一页留给 canvas 封面

        # ── 图表正则（解析 /static/charts/*.png）──
        markdown_table_separator = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$')
        markdown_image_pattern = re.compile(
            r'!\[[^\]]*\]\((?:file:/+)?(/static/charts/[^)]+?\.(?:png|jpg|jpeg|gif|webp))\)',
            re.IGNORECASE,
        )
        chart_pattern = re.compile(
            r'(?:file:/+)?(/static/charts/[^\s\]\)<>"\']+?\.(?:png|jpg|jpeg|gif|webp))',
            re.IGNORECASE,
        )
        added_charts = set()

        def _clean_chart_path(path: str) -> str:
            return str(path or "").strip().rstrip("，。；;,.")

        def _resolve_chart_path(path: str) -> str:
            cleaned = _clean_chart_path(path)
            if cleaned.startswith("/static/"):
                return os.path.join(project_root, cleaned.lstrip("/"))
            if os.path.isabs(cleaned):
                return cleaned
            return os.path.join(project_root, cleaned)

        def _add_chart(path: str):
            cleaned = _clean_chart_path(path)
            if not cleaned or cleaned in added_charts:
                return
            abs_path = _resolve_chart_path(cleaned)
            if not os.path.exists(abs_path):
                log.warning(f"[PDF] 图表文件不存在，跳过: {cleaned} -> {abs_path}")
                return
            try:
                img = Image(abs_path)
                image_width = float(getattr(img, "imageWidth", doc.width) or doc.width)
                image_height = float(getattr(img, "imageHeight", 1) or 1)
                scale = min((doc.width * 0.94) / image_width, (95 * mm) / image_height, 1.0)
                img.drawWidth = image_width * scale
                img.drawHeight = image_height * scale
                img.hAlign = "CENTER"
                story.append(Spacer(1, 8))
                story.append(img)
                story.append(Spacer(1, 12))
                added_charts.add(cleaned)
            except Exception as exc:
                log.warning(f"[PDF] 添加图表失败: {abs_path}, 错误: {exc}")

        # ── 宽表格转卡片 ──
        def _wide_table_as_cards(headers: list) -> bool:
            header_text = " ".join(str(h or "") for h in headers)
            if len(headers) >= 8:
                return True
            return len(headers) >= 6 and bool(re.search(
                r"说明|详情|建议|动作|确认|验收|依据|证据|来源|缺口|路径|线索|下一步",
                header_text,
            ))

        def _card_title(headers: list, row: list, index: int) -> str:
            preferred = ("模型", "业务", "告警类型", "处置优先级", "风险等级", "对象", "层面", "类别", "来源")
            values = []
            for key in preferred:
                if key in headers:
                    value = str(row[headers.index(key)] or "").strip()
                    if value and value != "-" and value not in values:
                        values.append(value)
            if not values:
                for value in row[:3]:
                    text = str(value or "").strip()
                    if text and text != "-" and text not in values:
                        values.append(text)
            return " · ".join(values[:3]) or f"明细 {index}"

        def _add_record_cards(headers: list, data_rows: list):
            if not data_rows:
                return
            for record_index, raw_row in enumerate(data_rows, 1):
                row = [str(cell or "").strip() for cell in raw_row]
                while len(row) < len(headers):
                    row.append("")
                title = _card_title(headers, row, record_index)
                detail_rows = [[
                    Paragraph(_inline_markdown(f"{record_index}. {title}"), card_title_style),
                    Paragraph("", card_title_style),
                ]]
                for header, value in zip(headers, row):
                    if not str(value or "").strip():
                        continue
                    detail_rows.append([
                        Paragraph(_inline_markdown(str(header or "-")), card_label_style),
                        Paragraph(_inline_markdown(str(value or "-")), card_value_style),
                    ])
                if len(detail_rows) == 1:
                    continue
                card = LongTable(
                    detail_rows,
                    colWidths=[doc.width * 0.24, doc.width * 0.76],
                    hAlign="LEFT", splitByRow=1,
                )
                card.setStyle(TableStyle([
                    ("SPAN", (0, 0), (-1, 0)),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eefbf5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), palette["ink"]),
                    ("FONTNAME", (0, 0), (-1, -1), base_font),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), 0.55, colors.HexColor("#c9d7e3")),
                    ("INNERGRID", (0, 1), (-1, -1), 0.3, colors.HexColor("#e1e8f0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(card)
                story.append(Spacer(1, 8))
            story.append(Spacer(1, 6))

        def _add_table(rows: list):
            if not rows:
                return
            max_cols = max(len(row) for row in rows)
            headers = [str(cell or "").strip() for cell in rows[0]] if rows else []
            if headers and _wide_table_as_cards(headers):
                _add_record_cards(headers, rows[1:])
                return
            normalized_rows = []
            for ri, row in enumerate(rows):
                style = th_style if ri == 0 else td_style
                normalized = [Paragraph(_inline_markdown(cell), style) for cell in row]
                while len(normalized) < max_cols:
                    normalized.append(Paragraph("", td_style))
                normalized_rows.append(normalized)
            tbl = LongTable(
                normalized_rows,
                colWidths=_table_widths(max_cols, doc.width, rows[0] if rows else None),
                repeatRows=1, hAlign='LEFT', splitByRow=1,
            )
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#eaf7f1")),
                ('TEXTCOLOR',  (0, 0), (-1, 0), palette["ink"]),
                ('FONTNAME',   (0, 0), (-1, -1), base_font),
                ('VALIGN',     (0, 0), (-1, -1), 'TOP'),
                ('LINEABOVE',  (0, 0), (-1, 0), 0.8, colors.HexColor("#8fd7b5")),
                ('LINEBELOW',  (0, 0), (-1, 0), 0.8, colors.HexColor("#8fd7b5")),
                ('BOX',        (0, 0), (-1, -1), 0.55, colors.HexColor("#c9d7e3")),
                ('INNERGRID',  (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe4ef")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ('LEFTPADDING',  (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING',   (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 14))

        def _add_paragraph(raw_line: str):
            raw = str(raw_line or "").strip()
            if not raw:
                story.append(Spacer(1, 5))
                return
            if re.fullmatch(r'[-=]{3,}', raw):
                story.append(Spacer(1, 3))
                story.append(HRFlowable(width="100%", thickness=0.6, color=palette["line"]))
                story.append(Spacer(1, 8))
                return
            heading = re.match(r'^(#{1,6})\s+(.+)$', raw)
            if heading:
                level = len(heading.group(1))
                text = heading.group(2).strip()
                style = (h1_style if level == 1 else
                         h2_style if level == 2 else
                         h3_style if level == 3 else h4_style)
                story.append(Paragraph(_inline_markdown(text), style))
                return
            if raw.startswith(">"):
                story.append(Paragraph(_inline_markdown(raw.lstrip("> ").strip()), note_style))
                story.append(Spacer(1, 5))
                return
            # 处理无序列表（支持嵌套）
            bullet_match = re.match(r'^(\s*)([-*])\s+(.+)$', raw_line)
            if bullet_match:
                indent = len(bullet_match.group(1))
                text = bullet_match.group(3).strip()
                # 根据缩进级别调整样式
                indent_level = min(indent // 2, 3)
                indent_mm = 14 + indent_level * 8
                bullet_text = "  " * indent_level + "• " + _inline_markdown(text)
                list_style = ParagraphStyle(
                    'RptBulletIndent', parent=bullet_style,
                    leftIndent=indent_mm, firstLineIndent=-8,
                )
                story.append(Paragraph(bullet_text, list_style))
                return
            if re.match(r'^\d+[\.、]\s+', raw):
                story.append(Paragraph(_inline_markdown(raw), bullet_style))
                return
            story.append(Paragraph(_inline_markdown(raw), normal_style))

        # ── 渲染正文 ──
        lines = _normalize_text(body).splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()

            # 表格
            if "|" in line and i + 1 < len(lines) and markdown_table_separator.match(lines[i + 1]):
                table_lines = [line, lines[i + 1]]
                i += 2
                while i < len(lines) and "|" in lines[i].strip():
                    table_lines.append(lines[i].rstrip())
                    i += 1
                rows = []
                for idx, table_line in enumerate(table_lines):
                    if idx == 1 and markdown_table_separator.match(table_line):
                        continue
                    cells = _split_markdown_row(table_line)
                    if cells:
                        rows.append(cells)
                _add_table(rows)
                continue

            # 代码块
            if line.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if code_lines:
                    code_text = "\n".join(code_lines)
                    story.append(Paragraph(code_text.replace("<", "&lt;").replace(">", "&gt;"), code_style))
                    story.append(Spacer(1, 6))
                i += 1
                continue

            # 图表引用（内联在正文里）
            chart_paths = markdown_image_pattern.findall(line) + chart_pattern.findall(line)
            cleaned_line = markdown_image_pattern.sub("", line)
            cleaned_line = chart_pattern.sub("", cleaned_line).strip()
            if cleaned_line:
                _add_paragraph(cleaned_line)
            elif not chart_paths:
                _add_paragraph(cleaned_line)
            for chart_path in chart_paths:
                _add_chart(chart_path)

            i += 1

        # ── 追加 charts 参数里的图表（"可视化图表"章节）──
        if charts:
            renderable = []
            for chart_item in charts:
                path = ""
                if isinstance(chart_item, dict):
                    path = chart_item.get("path") or chart_item.get("url") or chart_item.get("src") or ""
                elif isinstance(chart_item, str):
                    path = chart_item
                path = _clean_chart_path(path)
                if path and path not in added_charts:
                    abs_path = _resolve_chart_path(path)
                    if os.path.exists(abs_path):
                        renderable.append(path)
            if renderable:
                story.append(Paragraph("可视化图表", h1_style))
                for path in renderable:
                    _add_chart(path)

        # ── 页脚说明 ──
        story.append(Spacer(1, 15 * mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=palette["line"]))
        story.append(Paragraph(
            f"本报告由 AgentForge 自动生成 | {generated_at}",
            small_style,
        ))

        # ── 封面（3 字段 + 完整标题）──
        def _draw_cover(canvas, _doc):
            canvas.saveState()
            canvas.setFillColor(colors.white)
            canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)

            canvas.setFillColor(palette["dark"])
            canvas.rect(0, page_height - 24 * mm, page_width, 24 * mm, stroke=0, fill=1)
            canvas.setFillColor(palette["cyan"])
            canvas.rect(0, page_height - 25 * mm, page_width * 0.42, 2.2 * mm, stroke=0, fill=1)

            canvas.setFillColor(colors.white)
            canvas.setFont(base_font, 12)
            canvas.drawString(22 * mm, page_height - 15 * mm, "AgentForge")
            canvas.setFont(base_font, 8)
            canvas.drawRightString(page_width - 22 * mm, page_height - 15 * mm, "自动分析报告")

            # 主标题（自动换行，最多 3 行）
            title_font_size = 24
            title_lines = _wrap_canvas_text(report_title, base_font, title_font_size, page_width - 44 * mm, 3)
            title_top = page_height - 58 * mm
            canvas.setFillColor(palette["ink"])
            canvas.setFont(base_font, title_font_size)
            for line_no, line in enumerate(title_lines):
                line_width = pdfmetrics.stringWidth(line, base_font, title_font_size)
                canvas.drawString((page_width - line_width) / 2, title_top - line_no * 10 * mm, line)

            # 副标题
            subtitle = "业务态势、数据洞察与优化建议"
            canvas.setFillColor(palette["muted"])
            canvas.setFont(base_font, 11)
            subtitle_width = pdfmetrics.stringWidth(subtitle, base_font, 11)
            canvas.drawString((page_width - subtitle_width) / 2, title_top - (len(title_lines) + 1) * 10 * mm, subtitle)

            # 信息卡片（3 字段）
            card_x = 28 * mm
            card_y = 72 * mm
            card_w = page_width - 56 * mm
            card_h = 44 * mm
            canvas.setFillColor(palette["soft"])
            canvas.roundRect(card_x, card_y, card_w, card_h, 5 * mm, stroke=0, fill=1)
            canvas.setStrokeColor(colors.HexColor("#bbf7d0"))
            canvas.roundRect(card_x, card_y, card_w, card_h, 5 * mm, stroke=1, fill=0)

            canvas.setFillColor(palette["muted"])
            canvas.setFont(base_font, 9)
            canvas.drawString(card_x + 10 * mm, card_y + 28 * mm, "生成时间")
            canvas.drawString(card_x + 66 * mm, card_y + 28 * mm, "报告来源")
            canvas.drawString(card_x + 122 * mm, card_y + 28 * mm, "输出格式")
            canvas.setFillColor(palette["ink"])
            canvas.setFont(base_font, 10.5)
            canvas.drawString(card_x + 10 * mm, card_y + 17 * mm, generated_at)
            canvas.drawString(card_x + 66 * mm, card_y + 17 * mm, "智能分析任务")
            canvas.drawString(card_x + 122 * mm, card_y + 17 * mm, "PDF 附件")

            canvas.setFillColor(palette["muted"])
            canvas.setFont(base_font, 8)
            full_lines = _wrap_canvas_text("完整标题：" + report_title, base_font, 8, card_w - 20 * mm, 2)
            for idx, line in enumerate(full_lines):
                canvas.drawString(card_x + 10 * mm, card_y + 7 * mm - idx * 4 * mm, line)

            canvas.setStrokeColor(palette["cyan"])
            canvas.setLineWidth(1.2)
            canvas.line(28 * mm, 46 * mm, page_width - 28 * mm, 46 * mm)
            canvas.restoreState()

        def _draw_footer(canvas, doc_obj):
            canvas.saveState()
            if doc_obj.page > 1:
                canvas.setStrokeColor(colors.HexColor("#d1fae5"))
                canvas.setLineWidth(0.5)
                canvas.line(doc.leftMargin, 12 * mm, page_width - doc.rightMargin, 12 * mm)
                canvas.setFillColor(colors.HexColor("#94a3b8"))
                canvas.setFont(base_font, 8)
                canvas.drawString(doc.leftMargin, 7 * mm, report_title[:40])
                canvas.drawRightString(page_width - doc.rightMargin, 7 * mm, f"第 {doc_obj.page - 1} 页")
            canvas.restoreState()

        # 构建 PDF 到临时文件
        doc.build(story, onFirstPage=_draw_cover, onLaterPages=_draw_footer)

        # 返回结果
        if output_path:
            import shutil
            shutil.copy2(temp_path, output_path)
            try:
                os.remove(temp_path)
            except OSError:
                pass
            log.info(f"[PDF] 报告已生成: {output_path}")
            return None
        else:
            with open(temp_path, 'rb') as f:
                pdf_bytes = f.read()
            try:
                os.remove(temp_path)
            except OSError:
                pass
            log.info(f"[PDF] 报告已生成，大小: {len(pdf_bytes)} bytes")
            return pdf_bytes

    except Exception as e:
        log.opt(exception=True).error(f"[PDF] 生成失败: {e}")
        return None
