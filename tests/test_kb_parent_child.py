"""
父子分片（Parent-Child Chunking）— 主题结构感知版 测试

- 结构边界检测：【主题】标记 / 普通 ## 二级标题（对齐 Eyes only_level=2）/ 无结构降级
- 主题章节 → 父片：整段 ≤ 上限即父片；超长主题三级降级（### 标题 → 段落 → 字符）
- 父子 metadata：table_refs / heading_path 提取与子片继承
- 父片内容「来源路径」前缀（对齐 Eyes _contextual_content）
- 基础切分：父片包含子片、parent_index 关联正确
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


def _make_pages(texts):
    from backend.service.kb.kb_parsers import KbPage
    return [KbPage(page_no=i + 1, text=t) for i, t in enumerate(texts)]


def _make_sections(*texts):
    """构造 TopicSection 列表（title=t1, text=t2...）。"""
    from backend.service.kb.kb_topic_splitter import TopicSection
    return [
        TopicSection(title=f"主题{i+1}", text=t, source="structure")
        for i, t in enumerate(texts)
    ]


# ════════════════════════════════════════════════════════════
# 结构边界检测（纯单元，无 sections 回退路径）
# ════════════════════════════════════════════════════════════

class TestDetectStructureBoundaries:
    def test_topic_markers_priority(self):
        from backend.service.kb.kb_parent_child_splitter import _detect_structure_boundaries

        text = "引言。\n## 【主题：用户管理】\n内容一。\n## 【主题：可观测性】\n内容二。"
        boundaries = _detect_structure_boundaries(text)
        # 引言单独成段 + 两个主题
        assert len(boundaries) == 3
        assert "引言" in text[boundaries[0][0]:boundaries[0][1]]
        assert "用户管理" in text[boundaries[1][0]:boundaries[1][1]]
        assert "可观测性" in text[boundaries[2][0]:boundaries[2][1]]

    def test_plain_level2_headings_fallback(self):
        """无【主题】标记时，回退到普通 ## 二级标题切分（对齐 Eyes only_level=2）"""
        from backend.service.kb.kb_parent_child_splitter import _detect_structure_boundaries

        text = "## 用户管理\n创建用户。\n## 权限管理\n分配权限。\n### 子节\n不触发。"
        boundaries = _detect_structure_boundaries(text)
        assert len(boundaries) == 2
        assert "用户管理" in text[boundaries[0][0]:boundaries[0][1]]
        assert "权限管理" in text[boundaries[1][0]:boundaries[1][1]]

    def test_level1_or_level3_headings_ignored(self):
        """# 与 ### 不触发切分（only_level=2）"""
        from backend.service.kb.kb_parent_child_splitter import _detect_structure_boundaries

        text = "# 一级标题\n内容。\n### 三级标题\n内容。\n## 二级标题\n内容。"
        boundaries = _detect_structure_boundaries(text)
        assert len(boundaries) == 2  # 引言 + 二级标题段
        intro = text[boundaries[0][0]:boundaries[0][1]]
        assert "一级标题" in intro

    def test_leading_text_unnamed_segment(self):
        from backend.service.kb.kb_parent_child_splitter import _detect_structure_boundaries

        text = "前言。\n## 用户管理\n内容。"
        boundaries = _detect_structure_boundaries(text)
        assert len(boundaries) == 2
        assert "前言" in text[boundaries[0][0]:boundaries[0][1]]

    def test_no_structure_returns_empty(self):
        from backend.service.kb.kb_parent_child_splitter import _detect_structure_boundaries

        assert _detect_structure_boundaries("纯文本没有标题。") == []


# ════════════════════════════════════════════════════════════
# 超长主题三级降级
# ════════════════════════════════════════════════════════════

class TestLongSectionDegradation:
    def test_short_section_is_single_parent(self):
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        sections = _make_sections("短内容。" * 10)
        result = build_parent_child_chunks([], sections=sections)
        assert len(result["parents"]) == 1

    def test_level3_headings_split(self):
        """① 超长主题按 ### 三级标题切分（子段仍超长则继续降级）"""
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        sub1 = "子结构一。" * 30
        sub2 = "子结构二。" * 30
        long_text = f"### 概述\n{sub1}\n\n### 详述\n{sub2}"
        result = build_parent_child_chunks([], sections=_make_sections(long_text), parent_chunk_size=100)
        # ### 子段各自成为父片（可能继续按段落/字符降级），每片正文 ≤ 上限
        assert len(result["parents"]) >= 2
        prefix_len = len("来源路径：主题1\n\n")
        for p in result["parents"]:
            assert p["char_count"] - prefix_len <= 100
        # 所有父片共享 heading_path
        assert all(p["heading_path"] == "主题1" for p in result["parents"])

    def test_paragraph_aggregation(self):
        """② 无 ### 标题 → 按空行段落聚合，每父片 ≤ 上限"""
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        paragraphs = "\n\n".join(f"段落{i}内容。" * 10 for i in range(10))
        result = build_parent_child_chunks([], sections=_make_sections(paragraphs), parent_chunk_size=200)
        assert len(result["parents"]) >= 2
        prefix_len = len("来源路径：主题1\n\n")
        for p in result["parents"]:
            assert p["char_count"] - prefix_len <= 200

    def test_char_fallback(self):
        """③ 单个超长段落 → 字符切分兜底"""
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        one_para = "无边界长内容。" * 100
        result = build_parent_child_chunks([], sections=_make_sections(one_para), parent_chunk_size=200)
        assert len(result["parents"]) >= 2

    def test_all_sub_parents_share_metadata(self):
        """超长主题切出的所有子父片共享 heading_path + table_refs"""
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks
        from backend.service.kb.kb_topic_splitter import TopicSection

        long_text = "\n\n".join(f"段落{i}内容。" * 15 for i in range(8))
        section = TopicSection(
            title="大主题", text=long_text, source="structure",
            table_refs=["users", "roles"], heading_path="手册.md / 大主题",
        )
        result = build_parent_child_chunks([], sections=[section], parent_chunk_size=100)
        assert len(result["parents"]) >= 3
        for p in result["parents"]:
            assert p["heading_path"] == "手册.md / 大主题"
            assert p["table_refs"] == ["users", "roles"]


# ════════════════════════════════════════════════════════════
# 基础切分（纯单元）
# ════════════════════════════════════════════════════════════

class TestBasicSplit:
    def test_parent_child_relationship(self):
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        text = "## 用户管理\n" + "创建用户的方法是调用 create_user。\n" * 5
        result = build_parent_child_chunks(_make_pages([text]), child_chunk_size=100, child_overlap=20)
        assert len(result["parents"]) == 1
        assert len(result["children"]) >= 1
        for c in result["children"]:
            assert c["parent_index"] == 0
            # 子片内容包含在父片正文中（父片带来源路径前缀）
            assert c["content"] in result["parents"][0]["content"]

    def test_empty_pages(self):
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        result = build_parent_child_chunks([])
        assert result == {"parents": [], "children": []}


# ════════════════════════════════════════════════════════════
# metadata 提取与继承
# ════════════════════════════════════════════════════════════

class TestMetadataInheritance:
    def test_table_refs_inherited(self):
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        doc = (
            "## 【主题：用户管理】\n\n"
            "### 一、【功能】\n用户账号管理。\n\n"
            "### 六、【数据库表关联】\n\n"
            "| 表名 | 说明 |\n|------|------|\n| users | 用户表 |\n| roles | 角色表 |\n\n"
            "## 【主题：可观测性】\n\n"
            "### 一、【功能】\nToken 统计。\n\n"
            "### 六、【数据库表关联】\n\n"
            "| 表名 | 说明 |\n|------|------|\n| traces | 链路表 |\n"
        )
        result = build_parent_child_chunks(_make_pages([doc]))
        assert len(result["parents"]) == 2
        # 父片提取表关联
        p0_refs = result["parents"][0].get("table_refs") or []
        assert "users" in p0_refs
        assert "roles" in p0_refs
        p1_refs = result["parents"][1].get("table_refs") or []
        assert "traces" in p1_refs
        # 子片不继承父片 metadata（检索时通过 _enrich_with_parent_content 从父片获取）
        # 子片只需要 parent_index 关联父片即可
        for c in result["children"]:
            assert "parent_index" in c
            assert c.get("table_refs") is None  # 子片不存储 table_refs

    def test_heading_path_inherited(self):
        """测试父片有 heading_path，子片通过 parent_index 关联父片"""
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        doc = "## 用户管理\n创建用户。\n## 权限管理\n分配权限。"
        result = build_parent_child_chunks(_make_pages([doc]))
        assert len(result["parents"]) == 2
        assert result["parents"][0].get("heading_path") == "用户管理"
        assert result["parents"][1].get("heading_path") == "权限管理"
        # 子片不继承 heading_path，通过 parent_index 关联父片
        for c in result["children"]:
            assert "parent_index" in c
            assert c.get("heading_path") is None  # 子片不存储 heading_path

    def test_parent_content_has_source_path_prefix(self):
        """父片内容带「来源路径」前缀（对齐 Eyes _contextual_content）"""
        from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks

        doc = "## 用户管理\n创建用户。"
        result = build_parent_child_chunks(_make_pages([doc]))
        assert result["parents"][0]["content"].startswith("来源路径：用户管理\n")
