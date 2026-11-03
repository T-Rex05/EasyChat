"""
父子分片（Parent-Child Chunking）— 主题结构感知版（融合主题聚合）

核心思路：
- 父片（Parent Chunk）：主题级大粒度，保留完整主题上下文，存储在关系型数据库
- 子片（Child Chunk）：小粒度，用于向量/BM25 检索，存储在向量库
- 检索时命中子片 → 取出父片 ID → 返回父片内容给 LLM

主题结构感知（对齐 Eyes 主题切分）：
- 优先用 detect_topic_sections 识别出的主题章节作为父片边界：
  【主题：xxx】标记 → MD ## 标题 → PDF 书签 → DOCX 标题 → 嵌入聚类
- 主题段 ≤ parent_chunk_size → 整段即父片（上下文完整）
- 主题段超长 → 三级降级再切（所有子父片共享 heading_path + table_refs）：
    ① 按 ### 三级标题切（保留主题内子结构）
    ② 仍超长 → 按空行段落聚合（每个父片 ≤ 上限）
    ③ 仍超长（单段无边界）→ 字符切分兜底
- 无 sections（未识别出结构）→ 回退：【主题】标记 / ## 标题边界 → 字符切分

父片内容前缀「来源路径：heading_path」（对齐 Eyes _contextual_content），
让 LLM 在生成时明确知道该父片属于哪个主题层级。

优势：
- 检索精度：子片语义聚焦，与用户查询更对齐
- 生成质量：父片上下文完整（主题级），LLM 有足够信息生成准确回答
- 避免"信号稀释"：大分片向量是"平均语义"，检索相关性被稀释
- 表关联准确：主题内【数据库表关联】区块与内容同片，table_refs 提取准确
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from backend.utils.log_utils import log

logger = log

# 默认参数（经 scripts/chunk_param_sweep.py 参数扫描实测调优）
_DEFAULT_PARENT_CHUNK_SIZE = 2000  # 父片最大字符数（主题完整性上限，覆盖 78/79 Eyes 真实主题段）
_DEFAULT_CHILD_CHUNK_SIZE = 600    # 子片最大字符数（语义聚焦单元，实测 Recall@5 最优）
_DEFAULT_CHILD_OVERLAP = 120       # 子片重叠字符数（子片的 20%，防边界截断）


@dataclass
class ParentChunk:
    """父片数据结构"""
    index: int              # 父片在文档中的序号
    content: str            # 父片完整内容
    char_count: int         # 字符数
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    heading_path: str = ""              # 层级路径（对齐主题分片）
    table_refs: List[str] = field(default_factory=list)  # 关联数据库表名
    constraints: List[str] = field(default_factory=list)  # 约束条件（全局共享）
    key_rules: List[str] = field(default_factory=list)    # 表选择原则（全局共享）


@dataclass
class ChildChunk:
    """子片数据结构"""
    index: int              # 子片在文档中的序号（全局唯一）
    parent_index: int       # 所属父片的 index
    content: str            # 子片内容
    char_count: int         # 字符数
    page_start: Optional[int] = None
    page_end: Optional[int] = None


# 主题/示例结构标记（无 sections 时的回退父片边界）
_STRUCTURE_MARKER_RE = re.compile(
    r"^#{1,6}\s*【(?:主题[:：]\s*.+?|示例\s*\d+[^】]*)】\s*$",
    re.MULTILINE,
)

# 普通 Markdown 二级标题（对齐 Eyes only_level=2）
_LEVEL2_HEADING_RE = re.compile(r"^##(?!#)\s+.{1,120}$", re.MULTILINE)

# 三级标题（超长主题一级降级切分边界）
_LEVEL3_HEADING_RE = re.compile(r"^###(?!#)\s+.{1,120}$", re.MULTILINE)

# 章回体小说回目标题（如红楼梦、西游记、三国演义等）
# 格式1：第X回/章　标题（标准格式，如"第一回　甄士隐梦幻识通灵"、"第1章 宴桃园豪杰三结义"）
# 格式2：第X回/章 后跟换行+分隔线+标题（部分版本格式）
# 排除：句子中的"第X回中..."、"第X回里..."、"第X回已..."等
_CHAPTER_HEADING_RE = re.compile(
    r"^第[一二三四五六七八九十百零○\d]+[回章]"
    r"(?:"
        r"[　\s]{1,4}.{4,50}"  # 标准格式：第X回　标题
        r"|"
        r"\s*$"  # 仅回号，标题在下一部分（后续合并处理）
    r")$",
    re.MULTILINE,
)

# 简单的章回匹配（用于确定边界，排除句子中的匹配）
_SIMPLE_CHAPTER_RE = re.compile(
    r"^第[一二三四五六七八九十百零○\d]+[回章](?![中里后将已])",
    re.MULTILINE,
)


def _contextual_content(content: str, heading_path: str) -> str:
    """父片内容加「来源路径」前缀（对齐 Eyes _contextual_content）。"""
    content = (content or "").strip()
    heading_path = (heading_path or "").strip()
    if not heading_path or content.startswith(heading_path):
        return content
    return f"来源路径：{heading_path}\n\n{content}"


# ════════════════════════════════════════════════════════════
# 超长主题三级降级切分
# ════════════════════════════════════════════════════════════

def _sub_split_long_section(text: str, parent_chunk_size: int) -> List[str]:
    """超长主题段三级降级切分：
    ① ### 三级标题边界 → ② 空行段落聚合 → ③ 字符兜底。
    保证返回的每段 ≤ parent_chunk_size。
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= parent_chunk_size:
        return [text]

    # ① 三级标题边界
    headings = list(_LEVEL3_HEADING_RE.finditer(text))
    if headings:
        segs: List[str] = []
        if headings[0].start() > 0:
            segs.append(text[:headings[0].start()].strip())
        for i, m in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            segs.append(text[m.start():end].strip())
        segs = [s for s in segs if s]
        # 全部子段都 ≤ 上限 → 直接返回
        if all(len(s) <= parent_chunk_size for s in segs):
            return segs
        # 仍有超长子段 → 递归降级到段落
        result: List[str] = []
        for s in segs:
            result.extend(_sub_split_by_paragraphs(s, parent_chunk_size))
        return result

    return _sub_split_by_paragraphs(text, parent_chunk_size)


def _sub_split_by_paragraphs(text: str, parent_chunk_size: int) -> List[str]:
    """按空行段落聚合（②），仍超长的单段字符兜底（③）。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    segs: List[str] = []
    cur = ""
    for p in paragraphs:
        if cur and len(cur) + len(p) + 2 > parent_chunk_size:
            segs.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        segs.append(cur)

    # ③ 单段仍超长 → 字符切分兜底
    result: List[str] = []
    for s in segs:
        while len(s) > parent_chunk_size:
            result.append(s[:parent_chunk_size])
            s = s[parent_chunk_size:]
        if s:
            result.append(s)
    return result


# ════════════════════════════════════════════════════════════
# 主题章节 → 父片
# ════════════════════════════════════════════════════════════

def _parents_from_sections(sections: List, parent_chunk_size: int) -> List[ParentChunk]:
    """主题章节即父片（超长主题三级降级）。所有子父片共享 heading_path / table_refs / constraints / key_rules。"""
    parents: List[ParentChunk] = []
    for s in sections:
        text = (s.text or "").strip()
        if not text:
            continue
        heading_path = (getattr(s, "heading_path", "") or "").strip() or (s.title or "").strip()
        table_refs = list(getattr(s, "table_refs", None) or [])
        constraints = list(getattr(s, "constraints", None) or [])
        key_rules = list(getattr(s, "key_rules", None) or [])
        page_start = getattr(s, "page_start", None)
        page_end = getattr(s, "page_end", None)

        segs = _sub_split_long_section(text, parent_chunk_size)
        for seg in segs:
            parents.append(ParentChunk(
                index=len(parents),
                content=seg,
                char_count=len(seg),
                page_start=page_start,
                page_end=page_end,
                heading_path=heading_path,
                table_refs=table_refs,
                constraints=constraints,
                key_rules=key_rules,
            ))
    return parents


def _detect_structure_boundaries(full_text: str) -> List[Tuple[int, int]]:
    """无 sections 时的回退父片边界检测，优先级：
    1. 【主题：xxx】/【示例xx】标记
    2. 普通 ## 二级标题（对齐 Eyes only_level=2）
    3. 章回体小说回目标题（第X回）
    4. 无结构 → 空列表（调用方回退到字符切分）
    """
    markers = list(_STRUCTURE_MARKER_RE.finditer(full_text))
    if markers:
        boundaries: List[Tuple[int, int]] = []
        if markers[0].start() > 0:
            boundaries.append((0, markers[0].start()))
        for i, m in enumerate(markers):
            end = markers[i + 1].start() if i + 1 < len(markers) else len(full_text)
            boundaries.append((m.start(), end))
        return boundaries

    headings = list(_LEVEL2_HEADING_RE.finditer(full_text))
    if headings:
        boundaries = []
        if headings[0].start() > 0:
            boundaries.append((0, headings[0].start()))
        for i, m in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(full_text)
            boundaries.append((m.start(), end))
        return boundaries

    # 章回体小说回目标题（如红楼梦"第X回"）
    chapters = list(_CHAPTER_HEADING_RE.finditer(full_text))
    if chapters:
        # 特殊处理：章回体小说，每回一个父片
        # 使用简单正则匹配（排除"第X回中..."等误匹配）
        simple_matches = list(_SIMPLE_CHAPTER_RE.finditer(full_text))
        
        if simple_matches:
            boundaries = []
            # 第一个回目之前的内容（可能是版权信息等）
            if simple_matches[0].start() > 0:
                boundaries.append((0, simple_matches[0].start()))
            # 每回从"第X回"开始，到下一个"第X回"之前
            for i, m in enumerate(simple_matches):
                end = simple_matches[i + 1].start() if i + 1 < len(simple_matches) else len(full_text)
                boundaries.append((m.start(), end))
            return boundaries

    return []


def _extract_heading_path_from_text(text: str) -> str:
    """取文本第一个标题行作为层级路径（无 sections 回退路径用）。"""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("##") or stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


# ════════════════════════════════════════════════════════════
# 主切分流程
# ════════════════════════════════════════════════════════════

def split_into_parent_child_chunks(
    pages: List,
    parent_chunk_size: int = _DEFAULT_PARENT_CHUNK_SIZE,
    child_chunk_size: int = _DEFAULT_CHILD_CHUNK_SIZE,
    child_overlap: int = _DEFAULT_CHILD_OVERLAP,
    sections: Optional[List] = None,
) -> Tuple[List[ParentChunk], List[ChildChunk]]:
    """
    主题结构感知的父子切分。

    流程：
    1. sections（detect_topic_sections 结果）→ 主题段即父片，超长主题三级降级
    2. 无 sections → 【主题】标记 / ## 标题边界 → 字符切分回退
    3. 每个父片按 child_chunk_size 切分为子片（语义聚焦）
    4. 子片记录 parent_index，建立父子关系

    Args:
        pages: 解析出的页面列表（KbPage 对象或字典）
        parent_chunk_size: 父片最大字符数（默认 2000）
        child_chunk_size: 子片最大字符数（默认 600）
        child_overlap: 子片重叠字符数（默认 120）
        sections: detect_topic_sections 识别的主题章节（可选）

    Returns:
        (parent_chunks, child_chunks)
    """
    if not pages and not sections:
        return [], []

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # ── 步骤 1：主题章节 → 父片 ──
    if sections:
        parent_chunks = _parents_from_sections(sections, parent_chunk_size)
    else:
        # 拼接全文 + 页码映射
        full_text = ""
        char_to_page = {}
        for page in pages:
            if hasattr(page, 'text'):
                text = (page.text or "").strip()
                page_no = page.page_no
            else:
                text = (page.get("text") or "").strip()
                page_no = page.get("page_no")
            if not text:
                continue
            start_pos = len(full_text)
            full_text += text + "\n\n"
            end_pos = len(full_text)
            for pos in range(start_pos, end_pos):
                char_to_page[pos] = page_no

        if not full_text:
            return [], []

        structure_boundaries = _detect_structure_boundaries(full_text)
        if structure_boundaries:
            parent_texts = [
                full_text[start:end].strip()
                for start, end in structure_boundaries
                if full_text[start:end].strip()
            ]
        else:
            parent_splitter = RecursiveCharacterTextSplitter(
                chunk_size=parent_chunk_size,
                chunk_overlap=min(200, parent_chunk_size // 5),
                length_function=len,
                separators=["\n\n", "\n", "。", ".", "；", ";", " ", ""],
            )
            parent_texts = parent_splitter.split_text(full_text)

        parent_chunks: List[ParentChunk] = []
        current_pos = 0
        for p_text in parent_texts:
            start_idx = full_text.find(p_text, current_pos)
            if start_idx == -1:
                start_idx = current_pos
            end_idx = start_idx + len(p_text)
            current_pos = end_idx
            page_start = char_to_page.get(start_idx)
            page_end = char_to_page.get(end_idx - 1) or page_start
            parent_chunks.append(ParentChunk(
                index=len(parent_chunks),
                content=p_text,
                char_count=len(p_text),
                page_start=page_start,
                page_end=page_end,
                heading_path=_extract_heading_path_from_text(p_text),
            ))

    if not parent_chunks:
        return [], []

    # ── 步骤 2：每个父片切分为子片 ──
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=child_chunk_size,
        chunk_overlap=child_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", ".", "；", ";", " ", ""],
    )

    child_chunks: List[ChildChunk] = []
    for parent_idx, parent_chunk in enumerate(parent_chunks):
        child_texts = child_splitter.split_text(parent_chunk.content)
        current_pos_in_parent = 0
        for c_text in child_texts:
            start_in_parent = parent_chunk.content.find(c_text, current_pos_in_parent)
            if start_in_parent == -1:
                start_in_parent = current_pos_in_parent
            end_in_parent = start_in_parent + len(c_text)
            current_pos_in_parent = end_in_parent
            child_chunks.append(ChildChunk(
                index=len(child_chunks),
                parent_index=parent_idx,
                content=c_text,
                char_count=len(c_text),
                page_start=parent_chunk.page_start,
                page_end=parent_chunk.page_end,
            ))

    logger.info(
        f"[ParentChild] 生成 {len(parent_chunks)} 个父片, {len(child_chunks)} 个子片"
        f"（{'主题结构感知' if sections else '回退边界检测'}）"
    )
    return parent_chunks, child_chunks


# ════════════════════════════════════════════════════════════
# 构建函数（供 kb_service 调用）
# ════════════════════════════════════════════════════════════

def build_parent_child_chunks(
    pages: List,
    parent_chunk_size: int = _DEFAULT_PARENT_CHUNK_SIZE,
    child_chunk_size: int = _DEFAULT_CHILD_CHUNK_SIZE,
    child_overlap: int = _DEFAULT_CHILD_OVERLAP,
    sections: Optional[List] = None,
    doc_name: str = "",
) -> dict:
    """
    构建父子分片（供 kb_service 调用）。

    Args:
        pages: 解析出的页面列表（KbPage 对象或字典）
        parent_chunk_size: 父片最大字符数
        child_chunk_size: 子片最大字符数
        child_overlap: 子片重叠字符数
        sections: detect_topic_sections 识别的主题章节（可选）
        doc_name: 文档名称（用于来源路径前缀）

    Returns:
        {
            "parents": [{"content", "char_count", "page_start", "page_end", "kind": "parent",
                         "heading_path", "table_refs"}, ...],
            "children": [{"content", "char_count", "page_start", "page_end", "kind": "child",
                          "parent_index": int, "heading_path", "table_refs"}, ...],
        }
    """
    parent_chunks, child_chunks = split_into_parent_child_chunks(
        pages, parent_chunk_size, child_chunk_size, child_overlap, sections=sections
    )

    # ── 父片：内容加「来源路径」前缀 + metadata（先算 meta 供子片继承）──
    parents = []
    parent_meta: List[dict] = []
    for p in parent_chunks:
        # 来源路径：文件名 + 章节路径
        full_path = f"{doc_name} / {p.heading_path}" if doc_name and p.heading_path else (doc_name or p.heading_path)
        final_content = _contextual_content(p.content, full_path)
        table_refs = list(p.table_refs)
        constraints = list(p.constraints)
        key_rules = list(p.key_rules)
        if not table_refs:
            # 回退路径（无 sections）→ 从父片内容扫描【数据库表关联】区块
            try:
                from backend.service.kb.kb_topic_splitter import _extract_table_refs_from_section
                table_refs = _extract_table_refs_from_section(p.content)
            except Exception:
                table_refs = []
        if not constraints:
            # 回退路径（无 sections）→ 从父片内容扫描【约束条件】区块
            try:
                from backend.service.kb.kb_topic_splitter import _extract_constraints_from_section
                constraints = _extract_constraints_from_section(p.content)
            except Exception:
                constraints = []
        if not key_rules:
            # 回退路径（无 sections）→ 从父片内容扫描【表选择原则】区块
            try:
                from backend.service.kb.kb_topic_splitter import _extract_key_rules_from_section
                key_rules = _extract_key_rules_from_section(p.content)
            except Exception:
                key_rules = []
        parents.append({
            "content": final_content,
            "char_count": len(final_content),
            "page_start": p.page_start,
            "page_end": p.page_end,
            "kind": "parent",
            "topic_index": None,
        })
        meta: dict = {}
        if p.heading_path:
            parents[-1]["heading_path"] = p.heading_path
            meta["heading_path"] = p.heading_path
        if table_refs:
            parents[-1]["table_refs"] = table_refs
            meta["table_refs"] = table_refs
        if constraints:
            parents[-1]["constraints"] = constraints
            meta["constraints"] = constraints
        if key_rules:
            parents[-1]["key_rules"] = key_rules
            meta["key_rules"] = key_rules
        parent_meta.append(meta)

    # ── 子片：只存储 parent_index 关联父片，metadata 从父片获取（避免冗余）──
    children = []
    for c in child_chunks:
        item = {
            "content": c.content,
            "char_count": c.char_count,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "kind": "child",
            "topic_index": None,
            "parent_index": c.parent_index,  # 用于建立父子关系
        }
        # 子片不继承 metadata（heading_path / table_refs / constraints / key_rules）
        # 检索时通过 _enrich_with_parent_content 从父片获取，避免冗余存储
        children.append(item)

    return {"parents": parents, "children": children}
