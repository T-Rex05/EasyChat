"""
主题识别 — 主题标记优先 + 结构识别 + 嵌入聚类降级

识别优先级（零/低成本优先）：
1. 【主题：xxx】标记（Eyes 风格：文档使用 `## 【主题：xxx】` 切分，含【数据库表关联】区块）
2. MD 标题（# / ## / ###）
3. PDF 书签目录（pypdf outline，含页码）
4. DOCX 标题样式（Heading 1-9）
5. 嵌入聚类（页面级贪婪聚类，需 embedding 服务）
6. 全部失败 → 返回空（调用方回退到字符切分）

本模块产出 TopicSection 章节（供父子切片策略作为父片边界）。
主题内若含【数据库表关联】区块，提取表名供 text2sql 使用（table_refs）。
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from backend.utils.log_utils import log

logger = log

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.MULTILINE)

# Eyes 风格主题标记：## 【主题：xxx】 或 # 【主题：xxx】
_TOPIC_MARKER_RE = re.compile(
    r"^#{1,6}\s*【主题[:：]\s*(.+?)】\s*$", re.MULTILINE
)

# 【数据库表关联】区块标题（Eyes 文档用 ### 六、【数据库表关联】等编号，支持中文数字+顿号）
# 兼容 TextToSQL 参考示例的「涉及表」标题（### 涉及表 / ### 表关联关系）
_TABLE_REF_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:[一二三四五六七八九十\d]+[、.．]?\s*【数据库表关联】|涉及表|表关联关系|关联分析)\s*$",
    re.MULTILINE,
)

# 【约束条件】区块标题
_CONSTRAINTS_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:[一二三四五六七八九十\d]+[、.．]?\s*【约束条件】|约束条件|注意事项)\s*$",
    re.MULTILINE,
)

# 【表选择原则】区块标题
_KEY_RULES_HEADING_RE = re.compile(
    r"^\*{0,2}(?:重要[：:]?\s*)?表选择原则\*{0,2}\s*$",
    re.MULTILINE,
)

# Markdown 表格行：| 表名 | 说明 | ... |（首列是表名）
_MD_TABLE_ROW_RE = re.compile(r"^\|\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\|", re.MULTILINE)


@dataclass
class TopicSection:
    """识别出的主题章节"""
    title: str
    text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    source: str = "structure"    # marker | structure | cluster
    table_refs: List[str] = field(default_factory=list)  # 主题内关联的数据库表名
    heading_path: str = ""       # 层级路径（来源 / 标题1 / 标题2，对齐 Eyes）
    constraints: List[str] = field(default_factory=list)  # 约束条件（全局共享）
    key_rules: List[str] = field(default_factory=list)    # 表选择原则（全局共享）


def detect_topic_sections(
    ext: str,
    file_path: str,
    doc_text: str,
    pages: List,
) -> Tuple[List[TopicSection], List[str]]:
    """
    识别文档主题章节。

    Args:
        ext: 文件扩展名（.md/.pdf/.docx...）
        file_path: 原始文件路径（PDF outline / DOCX 样式需要）
        doc_text: 解析出的全文
        pages: ParsedDocument.pages（KbPage 列表）

    Returns:
        (sections, warnings)
    """
    warnings: List[str] = []

    # ① 主题标记优先（Eyes 风格）：## 【主题：xxx】
    if ext in (".md", ".markdown"):
        sections = _from_md_topic_markers(doc_text)
        if sections:
            return sections, warnings

    if ext in (".md", ".markdown"):
        sections = _from_md_headings(doc_text)
        if sections:
            return sections, warnings

    if ext == ".pdf":
        sections = _from_pdf_outline(file_path, pages)
        if sections:
            return sections, warnings
        warnings.append("PDF 无书签目录，尝试嵌入聚类识别主题")

    if ext in (".docx", ".doc"):
        sections = _from_docx_headings(file_path)
        if sections:
            return sections, warnings
        warnings.append("DOCX 无标题样式，尝试嵌入聚类识别主题")

    # ── 嵌入聚类降级 ──
    sections, cluster_warnings = _cluster_pages(pages)
    warnings.extend(cluster_warnings)
    return sections, warnings


# ════════════════════════════════════════════════════════════
# Eyes 风格主题标记识别
# ════════════════════════════════════════════════════════════

def _from_md_topic_markers(doc_text: str) -> List[TopicSection]:
    """按 Eyes 风格【主题：xxx】标记切分章节（MD 文档）。

    示例：
        ## 【主题：产品简介-系统功能概述】
        ### 一、【产品定位】...
        ### 六、【数据库表关联】
        | map_config_msg | 业务MAP图配置表 | 业务级别 |
        ---
        ## 【主题：登录与退出】
        ...

    主题间以 `---` 分隔（可选），每个主题从标记开始到下一个标记结束。
    主题内若含【数据库表关联】区块，提取其中的表名存入 table_refs。
    """
    markers = list(_TOPIC_MARKER_RE.finditer(doc_text))
    if not markers:
        return []

    sections: List[TopicSection] = []
    for i, m in enumerate(markers):
        title = m.group(1).strip()
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(doc_text)
        body = doc_text[start:end].strip()

        # 去掉尾部分隔符 `---`
        body = re.sub(r"^---+\s*$", "", body, flags=re.MULTILINE).strip()

        # 提取【数据库表关联】区块内的表名
        table_refs = _extract_table_refs_from_section(body)
        
        # 提取【约束条件】区块内的约束信息（Metadata 全局共享）
        constraints = _extract_constraints_from_section(body)
        
        # 提取【表选择原则】区块内的规则信息（Metadata 全局共享）
        key_rules = _extract_key_rules_from_section(body)

        sections.append(TopicSection(
            title=title, text=body, source="marker",
            table_refs=table_refs,
            constraints=constraints,
            key_rules=key_rules,
        ))

    if sections:
        logger.info(f"[KB-Topic] 主题标记识别出 {len(sections)} 个主题（source=marker）")

    return sections


def _extract_table_refs_from_section(body: str) -> List[str]:
    """从主题文本中提取【数据库表关联】区块的表名。

    策略：
    1. 定位【数据库表关联】标题
    2. 取其后的表格行（| 表名 | 说明 |）首列作为表名
    3. 也兼容"#### MySQL表 / #### ClickHouse表"下的表
    4. 去重保序
    """
    heading_matches = list(_TABLE_REF_HEADING_RE.finditer(body))
    if not heading_matches:
        return []

    table_refs: List[str] = []
    seen = set()

    for hm in heading_matches:
        # 从标题后开始扫描，直到下一个同级别标题或主题结束
        seg_start = hm.end()
        # 找到下一段的分隔（下一个 ### / ## 标题，含【】标题、涉及表等）
        next_heading = re.search(
            r"^#{1,6}\s*(?:[一二三四五六七八九十\d]*[、.．]?\s*【[^】]+】|涉及表|表关联关系|关联分析|生成SQL|SQL说明)\s*$",
            body[seg_start:],
            re.MULTILINE,
        )
        seg_end = seg_start + next_heading.start() if next_heading else len(body)
        segment = body[seg_start:seg_end]

        # 只取"表名 | 说明"格式的表格行（排除表头 `| 表名 | 说明 |` 和分隔行）
        for row_m in _MD_TABLE_ROW_RE.finditer(segment):
            table_name = row_m.group(1).strip()
            # 跳过表头（表名/说明/数据维度等）
            if table_name in ("表名", "说明", "数据维度", "MySQL表", "ClickHouse表"):
                continue
            if table_name not in seen:
                seen.add(table_name)
                table_refs.append(table_name)

    return table_refs


def _extract_constraints_from_section(body: str) -> List[str]:
    """从主题文本中提取【约束条件】区块的约束信息。

    策略：
    1. 定位【约束条件】或"注意事项"标题
    2. 提取标题后的列表项（- 开头）或段落
    3. 去重保序
    """
    heading_matches = list(_CONSTRAINTS_HEADING_RE.finditer(body))
    if not heading_matches:
        return []

    constraints: List[str] = []
    seen = set()

    for hm in heading_matches:
        # 从标题后开始扫描，直到下一个同级别标题或主题结束
        seg_start = hm.end()
        next_heading = re.search(
            r"^#{1,6}\s*(?:[一二三四五六七八九十\d]*[、.．]?\s*【[^】]+】|检索关键词|补充说明)\s*$",
            body[seg_start:],
            re.MULTILINE,
        )
        seg_end = seg_start + next_heading.start() if next_heading else len(body)
        segment = body[seg_start:seg_end]

        # 首先尝试提取列表项（- 开头）
        list_items = []
        for line_m in re.finditer(r"^[-*]\s+(.+?)$", segment, re.MULTILINE):
            constraint = line_m.group(1).strip()
            # 清理 markdown 格式
            constraint = re.sub(r"\*\*([^*]+)\*\*", r"\1", constraint)  # 去掉 **bold**
            constraint = re.sub(r"`([^`]+)`", r"\1", constraint)  # 去掉 `code`
            constraint = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", constraint)  # 去掉 [link](url)
            
            if constraint and constraint not in seen:
                seen.add(constraint)
                list_items.append(constraint)
        
        if list_items:
            constraints.extend(list_items)
        else:
            # 如果没有列表项，提取段落内容（非空行、非代码块的内容）
            lines = segment.split('\n')
            current_paragraph = []
            
            for line in lines:
                line = line.strip()
                # 跳过空行
                if not line:
                    if current_paragraph:
                        paragraph = ' '.join(current_paragraph)
                        # 清理 markdown 格式
                        paragraph = re.sub(r"\*\*([^*]+)\*\*", r"\1", paragraph)
                        paragraph = re.sub(r"`([^`]+)`", r"\1", paragraph)
                        paragraph = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", paragraph)
                        
                        if paragraph and paragraph not in seen:
                            seen.add(paragraph)
                            constraints.append(paragraph)
                        current_paragraph = []
                    continue
                
                # 跳过代码块标记
                if line.startswith('```'):
                    continue
                
                # 跳过标题行
                if line.startswith('#'):
                    continue
                
                # 跳过表格行
                if line.startswith('|') and line.endswith('|'):
                    continue
                
                current_paragraph.append(line)
            
            # 处理最后一个段落
            if current_paragraph:
                paragraph = ' '.join(current_paragraph)
                paragraph = re.sub(r"\*\*([^*]+)\*\*", r"\1", paragraph)
                paragraph = re.sub(r"`([^`]+)`", r"\1", paragraph)
                paragraph = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", paragraph)
                
                if paragraph and paragraph not in seen:
                    seen.add(paragraph)
                    constraints.append(paragraph)

    return constraints


def _extract_key_rules_from_section(body: str) -> List[str]:
    """从主题文本中提取【表选择原则】区块的规则信息。

    策略：
    1. 定位"表选择原则"标题（可能在【数据库表关联】区块内）
    2. 提取标题后的列表项（- 开头）
    3. 去重保序
    """
    heading_matches = list(_KEY_RULES_HEADING_RE.finditer(body))
    if not heading_matches:
        return []

    key_rules: List[str] = []
    seen = set()

    for hm in heading_matches:
        # 从标题后开始扫描，直到下一个同级别标题或主题结束
        seg_start = hm.end()
        next_heading = re.search(
            r"^(?:#{1,6}\s+|[-*]{2,}|\|)",
            body[seg_start:],
            re.MULTILINE,
        )
        seg_end = seg_start + next_heading.start() if next_heading else len(body)
        segment = body[seg_start:seg_end]

        # 提取列表项（- 开头）
        for line_m in re.finditer(r"^[-*]\s+(.+?)$", segment, re.MULTILINE):
            rule = line_m.group(1).strip()
            # 清理 markdown 格式
            rule = re.sub(r"\*\*([^*]+)\*\*", r"\1", rule)  # 去掉 **bold**
            rule = re.sub(r"`([^`]+)`", r"\1", rule)  # 去掉 `code`
            rule = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", rule)  # 去掉 [link](url)
            
            if rule and rule not in seen:
                seen.add(rule)
                key_rules.append(rule)

    return key_rules


# ════════════════════════════════════════════════════════════
# 结构识别（对齐 Eyes _markdown_sections）
# ════════════════════════════════════════════════════════════

# 步骤/编号标题（Eyes _looks_like_manual_step_heading 同款）：
# "步骤 1 xxx" / "第一步 xxx" / "一、xxx" / "1. xxx" 等作为额外切分点
_STEP_HEADING_RE = re.compile(
    r"^(步骤\s*\d+|第[一二三四五六七八九十0-9]+步|[一二三四五六七八九十]+[、.]|\d+[、.])\s*.+"
)


def _clean_heading(value: str) -> str:
    """标题清洗：压缩空白、去掉 # 号（对齐 Eyes _clean_heading）。"""
    return re.sub(r"\s+", " ", (value or "").strip().strip("#")).strip()


def _looks_like_step_heading(line: str) -> bool:
    value = (line or "").strip()
    if len(value) > 80:
        return False
    return bool(_STEP_HEADING_RE.match(value))


def _from_md_headings(
    doc_text: str,
    only_level: Optional[int] = 2,
    source_tag: str = "",
    split_steps: bool = True,
) -> List[TopicSection]:
    """按 Markdown 标题切分章节（对齐 Eyes _markdown_sections）。

    - heading_stack 标题栈：维护嵌套层级，生成层级路径 heading_path
    - only_level=2：默认只按二级标题（##）切分，其它 # 号不触发切分
      （除非文档没有二级标题，自动降级为全部标题切分）
    - 步骤/编号标题（"步骤1"、"一、"、"1."）作为额外切分点
    - 内容保留最近 3 级标题作为 section 头部

    Args:
        doc_text: Markdown 全文
        only_level: 只按指定级别标题切分（None=所有级别）
        source_tag: 来源标签（文档名），拼进 heading_path
        split_steps: 是否识别步骤标题作为额外切分点
    """
    lines = doc_text.splitlines()
    sections: List[TopicSection] = []
    heading_stack: List[str] = []
    buffer: List[str] = []

    # 判断是否有目标级别的标题；没有则降级为全部标题
    target_level = only_level
    if target_level is not None:
        has_target = any(
            re.match(rf"^#{{{target_level}}}(?!#)\s+", line.strip())
            for line in lines
        )
        if not has_target:
            target_level = None  # 无二级标题 → 所有级别都切

    heading_pattern = (
        re.compile(rf"^#{{{target_level}}}(?!#)\s+(.{{1,120}})$")
        if target_level
        else re.compile(r"^(#{1,6})\s+(.{1,120})$")
    )

    def flush():
        nonlocal buffer
        if not buffer:
            return
        heading_path = " / ".join(part for part in [source_tag, *heading_stack] if part)
        title = heading_stack[-1] if heading_stack else "（未命名）"
        # 内容 = 最近 3 级标题 + 正文
        heading_text = "\n".join(
            f"{'#' * min(index + 1, 6)} {t}" for index, t in enumerate(heading_stack[-3:])
        )
        body = "\n".join(buffer).strip()
        content = "\n\n".join(part for part in [heading_text, body] if part)
        sections.append(TopicSection(
            title=title,
            text=content,
            source="structure",
            heading_path=heading_path,
        ))
        buffer = []

    for raw_line in lines:
        line = raw_line.rstrip()
        heading_match = heading_pattern.match(line.strip())
        if heading_match:
            flush()
            if target_level:
                title = _clean_heading(heading_match.group(1))
                heading_stack = [title]
            else:
                level = len(heading_match.group(1))
                title = _clean_heading(heading_match.group(2))
                heading_stack = heading_stack[:level - 1] + [title]
            continue
        if split_steps and _looks_like_step_heading(line):
            flush()
            title = _clean_heading(line)
            heading_stack = heading_stack[:2] + [title]
            continue
        buffer.append(line)
    flush()

    if sections:
        return sections
    # 无任何标题 → 整体作为一个 section
    return [TopicSection(title="全文", text=doc_text.strip(), source="structure")]


def _from_pdf_outline(file_path: str, pages: List) -> List[TopicSection]:
    """按 PDF 书签目录切分章节（含页码范围）。"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        outline = reader.outline
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[KB-Topic] PDF outline 读取失败: {e}")
        return []

    entries: List[Tuple[str, int]] = []

    def walk(items, prefix=""):
        for item in items:
            try:
                title = str(getattr(item, "title", "")).strip()
                page_no = None
                try:
                    page_no = reader.get_destination_page_number(item) + 1
                except Exception:
                    pass
                if title and page_no is not None:
                    entries.append((f"{prefix}{title}", page_no))
            except Exception:
                continue
            try:
                children = list(item)
                if children:
                    walk(children, prefix=prefix + title + " / ")
            except Exception:
                continue

    try:
        walk(outline)
    except Exception:
        return []

    if not entries:
        return []

    total_pages = len(pages)
    sections: List[TopicSection] = []
    # 书签前的内容归「前言」
    if entries[0][1] > 1:
        preface_text = "\n".join(
            p.text for p in pages[: entries[0][1] - 1] if p.text.strip()
        )
        if preface_text.strip():
            sections.append(TopicSection(
                title="前言", text=preface_text, page_start=1,
                page_end=entries[0][1] - 1, source="structure",
            ))

    for i, (title, page_no) in enumerate(entries):
        end_page = entries[i + 1][1] - 1 if i + 1 < len(entries) else total_pages
        start_page = max(page_no, 1)
        end_page = min(end_page, total_pages)
        text = "\n\n".join(
            f"（第 {p.page_no} 页）{p.text}" for p in pages[start_page - 1:end_page]
            if p.text.strip()
        )
        sections.append(TopicSection(
            title=title, text=text, page_start=start_page,
            page_end=end_page, source="structure",
        ))
    return sections


def _from_docx_headings(file_path: str) -> List[TopicSection]:
    """按 DOCX 标题样式切分章节。"""
    try:
        from docx import Document
        doc = Document(file_path)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[KB-Topic] DOCX 读取失败: {e}")
        return []

    sections: List[TopicSection] = []
    current_title = ""
    current_body: List[str] = []

    def flush():
        nonlocal current_title, current_body
        text = "\n".join(current_body).strip()
        if text or current_title:
            sections.append(TopicSection(
                title=current_title or "（未命名）", text=text, source="structure",
            ))
        current_body = []

    for para in doc.paragraphs:
        style = (para.style.name or "") if para.style else ""
        if style.startswith("Heading"):
            flush()
            current_title = para.text.strip() or f"（{style}）"
        else:
            if para.text.strip():
                current_body.append(para.text)
    # 表格内容附加到最后一个章节
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                current_body.append(" | ".join(cells))
    flush()
    return sections


# ════════════════════════════════════════════════════════════
# 嵌入聚类降级（无结构时）
# ════════════════════════════════════════════════════════════

def _cluster_pages(pages: List, threshold: float = 0.55) -> Tuple[List[TopicSection], List[str]]:
    """
    页面级贪婪聚类：按顺序遍历页面，与已有主题质心余弦相似度 ≥ 阈值则并入，
    否则开新主题（保持文档顺序 → 主题按出现顺序编号）。
    """
    warnings: List[str] = []
    valid = [(p.page_no, p.text) for p in pages if p.text.strip()]
    if len(valid) < 2:
        warnings.append("页面过少/无文本，无法聚类识别主题")
        return [], warnings

    try:
        import numpy as np
        from backend.service.kb.kb_retriever import _build_embeddings

        embeddings = _build_embeddings()
        vectors = np.array(embeddings.embed_documents([t for _, t in valid]), dtype=float)
    except Exception as e:  # noqa: BLE001
        warnings.append(f"嵌入聚类不可用（未配置 embedding 服务）: {e}")
        return [], warnings

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    unit = vectors / norms

    clusters: List[dict] = []  # {page_nos, texts, centroid}
    for idx, (page_no, text) in enumerate(valid):
        vec = unit[idx]
        best = -1.0
        best_cluster = None
        for c in clusters:
            sim = float(np.dot(c["centroid"], vec))
            if sim > best:
                best, best_cluster = sim, c
        if best_cluster is not None and best >= threshold:
            best_cluster["page_nos"].append(page_no)
            best_cluster["texts"].append(text)
            # 质心 = 均值向量再归一
            old_n = len(best_cluster["page_nos"]) - 1
            best_cluster["centroid"] = (
                best_cluster["centroid"] * old_n + vec
            ) / (old_n + 1)
            best_cluster["centroid"] /= max(np.linalg.norm(best_cluster["centroid"]), 1e-8)
        else:
            clusters.append({
                "page_nos": [page_no], "texts": [text], "centroid": vec,
            })

    sections: List[TopicSection] = []
    for i, c in enumerate(clusters, 1):
        joined = "\n\n".join(
            f"（第 {pn} 页）{t}" for pn, t in zip(c["page_nos"], c["texts"])
        )
        title = c["texts"][0].strip().replace("\n", " ")[:30] or f"主题 {i}"
        sections.append(TopicSection(
            title=title, text=joined,
            page_start=min(c["page_nos"]), page_end=max(c["page_nos"]),
            source="cluster",
        ))
    warnings.append(f"嵌入聚类识别出 {len(sections)} 个主题（source=cluster）")
    return sections, warnings
