"""
现代化 PDF 报告生成器 - WeasyPrint + HTML/CSS

基于 WeasyPrint 实现的 PDF 生成器，使用 HTML/CSS 模板生成专业美观的报告。
支持 Markdown 内容解析、中文排版、图表嵌入。

优势：
- 现代化设计：使用完整 CSS3 特性（Flexbox、Grid、渐变、阴影等）
- 中文支持：使用系统字体，自动回退
- 高可定制：HTML/CSS 模板易于修改
- 响应式布局：自动分页、页眉页脚
"""
import os
import platform
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from backend.utils.log_utils import log


def _init_gtk_dll_path():
    """初始化 GTK DLL 搜索路径（Windows 需要）。"""
    if platform.system() != "Windows":
        return
    
    # 常见 GTK 安装路径
    gtk_paths = [
        os.environ.get("GTK3_RUNTIME") or "",
        "E:\\Coding_Tool\\GTK3-Runtime Win64\\bin",
        "C:\\Program Files\\GTK3-Runtime\\bin",
        "C:\\Program Files (x86)\\GTK3-Runtime\\bin",
    ]
    
    for gtk_path in gtk_paths:
        if gtk_path and os.path.isdir(gtk_path):
            # Python 3.8+ 使用 add_dll_directory
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(gtk_path)
                log.debug(f"[PDF] Added DLL directory: {gtk_path}")
            # 也添加到 PATH
            if gtk_path not in os.environ.get("PATH", ""):
                os.environ["PATH"] = gtk_path + os.pathsep + os.environ.get("PATH", "")
            break


# 在模块加载时初始化 GTK 路径
_init_gtk_dll_path()


def _convert_box_drawing(text: str) -> str:
    """将 Unicode box-drawing 字符转换为 ASCII 等效字符。

    这些字符在 PDF 中可能无法正确渲染，转换为 ASCII 确保可读性。
    """
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


def _markdown_to_html(markdown_text: str) -> str:
    """将 Markdown 文本转换为 HTML。

    支持的特性：
    - 标题 (h1-h4)
    - 列表 (有序/无序)
    - 代码块 (带语法高亮标记)
    - 表格
    - 引用块
    - 图片引用
    - 粗体/斜体
    """
    from xml.sax.saxutils import escape as html_escape

    text = str(markdown_text or "")
    text = _convert_box_drawing(text)

    lines = text.split('\n')
    html_parts = []
    i = 0

    def process_inline(line: str) -> str:
        """处理行内 Markdown 元素（先转义 HTML 防 XSS）"""
        # 先转义 HTML 特殊字符，防止 XSS 注入
        line = html_escape(line)
        # 代码
        line = re.sub(r'`([^`]+)`', r'<code>\1</code>', line)
        # 粗体
        line = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', line)
        # 斜体
        line = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', line)
        line = re.sub(r'_([^_]+)_', r'<em>\1</em>', line)
        return line

    while i < len(lines):
        line = lines[i]

        # 代码块
        if line.startswith('```'):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code_lines.append(html_escape(lines[i]))
                i += 1
            code_html = '\n'.join(code_lines)
            html_parts.append(f'<pre><code class="language-{lang}">{code_html}</code></pre>')
            i += 1
            continue

        # 表格
        if '|' in line and i + 1 < len(lines) and re.match(r'^\s*\|?\s*[:-]+\s*\|', lines[i + 1]):
            table_rows = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and '|' in lines[i]:
                table_rows.append(lines[i])
                i += 1

            # 解析表格
            html_table = ['<table><thead><tr>']
            for idx, row in enumerate(table_rows):
                if idx == 1:  # 分隔行
                    continue
                cells = [c.strip() for c in row.strip('|').split('|')]
                if idx == 0:
                    for cell in cells:
                        html_table.append(f'<th>{process_inline(cell)}</th>')
                    html_table.append('</tr></thead><tbody>')
                else:
                    html_table.append('<tr>')
                    for cell in cells:
                        html_table.append(f'<td>{process_inline(cell)}</td>')
                    html_table.append('</tr>')
            html_table.append('</tbody></table>')
            html_parts.append(''.join(html_table))
            continue

        # 标题
        heading_match = re.match(r'^(#{1,4})\s+(.+)$', line)
        if heading_match:
            level = len(heading_match.group(1))
            content = process_inline(heading_match.group(2))
            html_parts.append(f'<h{level}>{content}</h{level}>')
            i += 1
            continue

        # 引用块
        if line.startswith('>'):
            content = process_inline(line.lstrip('> ').strip())
            html_parts.append(f'<blockquote>{content}</blockquote>')
            i += 1
            continue

        # 无序列表
        if re.match(r'^[\-\*]\s+', line):
            content = process_inline(re.sub(r'^[\-\*]\s+', '', line))
            html_parts.append(f'<ul><li>{content}</li></ul>')
            i += 1
            continue

        # 有序列表
        ordered_match = re.match(r'^(\d+)[\.\、]\s+(.+)$', line)
        if ordered_match:
            content = process_inline(ordered_match.group(2))
            html_parts.append(f'<ol><li>{content}</li></ol>')
            i += 1
            continue

        # 分隔线
        if re.match(r'^[-]{3,}$', line.strip()):
            html_parts.append('<hr>')
            i += 1
            continue

        # 空行
        if not line.strip():
            html_parts.append('')
            i += 1
            continue

        # 普通段落
        html_parts.append(f'<p>{process_inline(line)}</p>')
        i += 1

    # 合并相邻的同类列表
    result = '\n'.join(html_parts)
    result = re.sub(r'</ul>\s*<ul>', '', result)
    result = re.sub(r'</ol>\s*<ol>', '', result)

    return result


def _get_template_path() -> Path:
    """获取 PDF 模板文件路径"""
    template_dir = Path(__file__).parent.parent / "templates"
    return template_dir / "pdf_report.html"


def generate_report_pdf_weasyprint(
    subject: str,
    body: str,
    output_path: Optional[str] = None,
    subtitle: Optional[str] = None,
    source: str = "智能分析任务",
    charts: Optional[List[str]] = None,
) -> Optional[bytes]:
    """
    使用 WeasyPrint 生成现代化 PDF 报告。

    Args:
        subject: 报告标题
        body: Markdown 格式的正文内容
        output_path: 输出文件路径（可选，不指定则返回 bytes）
        subtitle: 副标题（可选）
        source: 报告来源（默认：智能分析任务）
        charts: 图表文件路径列表（可选，将嵌入报告）

    Returns:
        如果 output_path 为 None，返回 PDF bytes；否则返回 None
    """
    try:
        from weasyprint import HTML, CSS
        from jinja2 import Template
    except ImportError:
        log.error("[PDF] weasyprint 或 jinja2 未安装: pip install weasyprint markdown")
        return None

    try:
        # 读取模板
        template_path = _get_template_path()
        if not template_path.exists():
            log.error(f"[PDF] 模板文件不存在: {template_path}")
            return None

        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        # 转换 Markdown 为 HTML
        content_html = _markdown_to_html(body)

        # 处理图表
        if charts:
            for chart_path in charts:
                if isinstance(chart_path, dict):
                    chart_path = chart_path.get("path") or chart_path.get("url") or ""
                if chart_path and os.path.exists(chart_path):
                    # 将图表转换为 base64 嵌入
                    import base64
                    with open(chart_path, 'rb') as img_file:
                        img_data = base64.b64encode(img_file.read()).decode()
                    img_ext = Path(chart_path).suffix.lstrip('.').lower()
                    img_ext = 'jpeg' if img_ext == 'jpg' else img_ext
                    img_src = f'data:image/{img_ext};base64,{img_data}'
                    content_html += f'\n<figure><img src="{img_src}" alt="图表"><figcaption>统计图表</figcaption></figure>'

        # 渲染模板
        template = Template(template_content)
        html_content = template.render(
            title=subject,
            subtitle=subtitle or "业务态势、数据洞察与优化建议",
            generated_date=datetime.now().strftime("%Y年%m月%d日 %H:%M"),
            source=source,
            content=content_html,
        )

        # 生成 PDF
        html_doc = HTML(string=html_content, base_url=str(template_path.parent))

        if output_path:
            html_doc.write_pdf(output_path)
            log.info(f"[PDF] 报告已生成: {output_path}")
            return None
        else:
            pdf_bytes = html_doc.write_pdf()
            log.info(f"[PDF] 报告已生成，大小: {len(pdf_bytes)} bytes")
            return pdf_bytes

    except Exception as e:
        log.opt(exception=True).error(f"[PDF] WeasyPrint 生成失败: {e}")
        return None


def generate_report_pdf(
    subject: str,
    body: str,
    output_path: Optional[str] = None,
    charts: Optional[list] = None,
) -> Optional[bytes]:
    """
    生成 PDF 报告（智能选择生成器）。

    优先使用 WeasyPrint（更美观），如果不可用则回退到 reportlab。

    Args:
        subject: 报告标题
        body: Markdown 格式的正文内容
        output_path: 输出文件路径（可选）
        charts: 图表文件路径列表（可选）

    Returns:
        如果 output_path 为 None，返回 PDF bytes；否则返回 None
    """
    # 尝试 WeasyPrint
    try:
        from weasyprint import HTML
        return generate_report_pdf_weasyprint(subject, body, output_path, charts=charts)
    except ImportError:
        log.debug("[PDF] WeasyPrint 不可用，使用 reportlab")

    # 回退到 reportlab
    from backend.tools.pdf_generator import generate_report_pdf as _generate_reportlab
    return _generate_reportlab(subject, body, output_path, charts)