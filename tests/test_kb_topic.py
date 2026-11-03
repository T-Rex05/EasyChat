"""
主题切分策略测试

- 主题识别：MD 标题 / PDF 书签目录 / DOCX 标题样式 / 无结构降级
- 切分：topic 模式基础块（章节边界）+ 主题节点块（长度受限、页码引用）
- 检索 kind 过滤（BM25 / 向量）
- 服务层 topic 策略上传/重解析/列表过滤（需 MySQL）
- 评测运行 chunk_kind 传参（mock）
"""
import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


def _mysql_available() -> bool:
    try:
        from backend.db.connection_pool import get_pool_connection
        conn = get_pool_connection()
        conn.close()
        return True
    except Exception:
        return False


requires_mysql = pytest.mark.skipif(
    not _mysql_available(), reason="MySQL 不可用，跳过 DB 集成测试"
)


def _make_pdf_with_outline(path: Path, chapters=2) -> Path:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    for i in range(1, chapters + 1):
        pdf.add_page()
        pdf.start_section(f"Chapter {i} Topic {i}", level=0)
        pdf.set_font("helvetica", size=12)
        pdf.multi_cell(0, 8, f"Content of chapter {i}. " * 12)
    pdf.output(str(path))
    return path


def _make_docx_with_headings(path: Path) -> Path:
    from docx import Document

    doc = Document()
    doc.add_heading("第一章 缓存", level=1)
    doc.add_paragraph("缓存雪崩是指大量缓存同时失效。")
    doc.add_heading("第二章 JWT", level=1)
    doc.add_paragraph("JWT 是无状态令牌。")
    doc.save(str(path))
    return path


def _make_pages(texts):
    from backend.service.kb.kb_parsers import KbPage
    return [KbPage(page_no=i + 1, text=t) for i, t in enumerate(texts)]


# ════════════════════════════════════════════════════════════
# 主题识别（纯单元）
# ════════════════════════════════════════════════════════════

class TestTopicDetection:
    def test_md_headings(self):
        from backend.service.kb.kb_topic_splitter import _from_md_headings

        # 对齐 Eyes：只按二级标题（##）切分，其它 # 号不触发切分
        text = "# 主题A\n内容A一。\n## 主题A子节\n内容A二。\n# 主题B\n内容B。"
        sections = _from_md_headings(text, only_level=2)
        # ## 之前是引言（未命名），## 之后到文末是一个 section（无更多 ##）
        assert len(sections) == 2
        assert sections[0].title == "（未命名）"
        assert "内容A一" in sections[0].text
        assert sections[1].title == "主题A子节"
        assert "内容A二" in sections[1].text

    def test_md_heading_path(self):
        from backend.service.kb.kb_topic_splitter import _from_md_headings

        # 验证层级路径 heading_path（对齐 Eyes）
        text = "## 用户管理\n### 创建用户\n内容。\n## 权限管理\n内容。"
        sections = _from_md_headings(text, only_level=2, source_tag="手册.md")
        assert len(sections) == 2
        assert sections[0].title == "用户管理"
        assert "手册.md / 用户管理" in sections[0].heading_path
        # 子标题归入父主题，内容保留 3 级标题
        assert "创建用户" in sections[0].text
        assert sections[1].title == "权限管理"

    def test_md_leading_text_unnamed(self):
        from backend.service.kb.kb_topic_splitter import _from_md_headings

        sections = _from_md_headings("前言内容。\n# 正文\n正文内容。")
        assert sections[0].title == "（未命名）"
        assert sections[1].title == "正文"

    def test_pdf_outline(self, tmp_path):
        from backend.service.kb.kb_topic_splitter import _from_pdf_outline

        path = _make_pdf_with_outline(tmp_path / "outline.pdf", chapters=2)
        pages = _make_pages([f"page{i} text" for i in range(1, 3)])
        sections = _from_pdf_outline(str(path), pages)
        assert len(sections) >= 2
        titles = [s.title for s in sections]
        assert any("Chapter 1" in t for t in titles)
        assert any("Chapter 2" in t for t in titles)
        # 页码范围正确
        ch1 = next(s for s in sections if "Chapter 1" in s.title)
        assert ch1.page_start == 1
        assert ch1.page_end == 1

    def test_pdf_no_outline_returns_empty(self, tmp_path):
        from backend.service.kb.kb_topic_splitter import _from_pdf_outline
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", size=12)
        pdf.multi_cell(0, 8, "No outline here. " * 5)
        path = tmp_path / "no_outline.pdf"
        pdf.output(str(path))
        assert _from_pdf_outline(str(path), _make_pages(["text"])) == []

    def test_docx_headings(self, tmp_path):
        from backend.service.kb.kb_topic_splitter import _from_docx_headings

        path = _make_docx_with_headings(tmp_path / "doc.docx")
        sections = _from_docx_headings(str(path))
        assert len(sections) == 2
        assert sections[0].title == "第一章 缓存"
        assert "缓存雪崩" in sections[0].text
        assert sections[1].title == "第二章 JWT"

    def test_detect_fallback_when_no_structure_no_embedding(self, tmp_path, monkeypatch):
        """txt 无结构 + 嵌入不可用 → 返回空 sections + warning。"""
        from backend.service.kb.kb_topic_splitter import detect_topic_sections

        monkeypatch.setattr(
            "backend.service.kb.kb_topic_splitter._cluster_pages",
            lambda pages, threshold=0.55: ([], ["嵌入聚类不可用"]),
        )
        sections, warnings = detect_topic_sections(
            ".txt", str(tmp_path / "x.txt"), "plain text", _make_pages(["plain text"])
        )
        assert sections == []
        assert warnings

    def test_cluster_pages(self, monkeypatch):
        """嵌入聚类：相似页面归组，差异页面开新主题。"""
        from backend.service.kb.kb_topic_splitter import _cluster_pages

        class FakeEmb:
            def embed_documents(self, texts):
                # 前两页相似向量，第三页正交
                return [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]

        monkeypatch.setattr(
            "backend.service.kb.kb_retriever._build_embeddings", lambda: FakeEmb()
        )
        pages = _make_pages(["缓存雪崩内容", "缓存雪崩续篇", "JWT 令牌原理"])
        sections, warnings = _cluster_pages(pages, threshold=0.5)
        assert len(sections) == 2
        assert sections[0].page_start == 1 and sections[0].page_end == 2
        assert sections[1].page_start == 3 and sections[1].page_end == 3
        assert sections[0].source == "cluster"
        assert warnings


# ════════════════════════════════════════════════════════════
# 切分（topic 旧名 → parent_child 合并策略）
# ════════════════════════════════════════════════════════════

class TestChunkDocument:
    def _sections(self):
        from backend.service.kb.kb_topic_splitter import TopicSection
        return [
            TopicSection(title="主题A", text="A内容。" * 30, source="structure"),
            TopicSection(title="主题B", text="B内容。" * 30, source="structure"),
        ]

    def test_topic_alias_routes_to_parent_child(self):
        """topic 策略名合并到父子切片：主题段即父片 + 子片，无主题节点块。"""
        from backend.service.kb.kb_service import _chunk_document

        chunks, topic = _chunk_document(
            _make_pages([""]), chunk_size=100, chunk_overlap=0,
            strategy="topic", sections=self._sections(),
        )
        assert topic == []
        kinds = {c["kind"] for c in chunks}
        assert kinds == {"parent", "child"}
        parents = [c for c in chunks if c["kind"] == "parent"]
        assert len(parents) == 2
        assert parents[0]["heading_path"] == "主题A"
        assert parents[1]["heading_path"] == "主题B"
        children = [c for c in chunks if c["kind"] == "child"]
        assert children and all(c["parent_index"] in (0, 1) for c in children)

    def test_topic_mode_with_pages(self):
        """有页码章节（PDF 目录）→ 父片携带页码范围。"""
        from backend.service.kb.kb_service import _chunk_document
        from backend.service.kb.kb_topic_splitter import TopicSection

        sections = [
            TopicSection(title="Ch1", text="c1内容。" * 10, page_start=1, page_end=1),
            TopicSection(title="Ch2", text="c2内容。" * 10, page_start=2, page_end=2),
        ]
        chunks, topic = _chunk_document(
            _make_pages(["第一页内容" * 20, "第二页内容" * 20]),
            chunk_size=50, chunk_overlap=0, strategy="parent_child", sections=sections,
        )
        assert topic == []
        parents = [c for c in chunks if c["kind"] == "parent"]
        assert len(parents) == 2
        assert parents[0]["page_start"] == 1
        assert parents[1]["page_start"] == 2

    def test_no_sections_falls_back_to_char_split(self):
        """无主题结构 → 回退字符切分父片（仍是父子切片，不降级为 fixed）。"""
        from backend.service.kb.kb_service import _chunk_document

        chunks, topic = _chunk_document(
            _make_pages(["文本内容" * 10]), chunk_size=100, chunk_overlap=0,
            strategy="topic", sections=[],
        )
        assert topic == []
        kinds = {c["kind"] for c in chunks}
        assert kinds == {"parent", "child"}

    def test_fixed_mode_unchanged(self):
        from backend.service.kb.kb_service import _chunk_document

        base, topic = _chunk_document(
            _make_pages(["文本内容" * 10]), chunk_size=100, chunk_overlap=0,
            strategy="fixed", sections=[],
        )
        assert topic == []
        assert base
        assert all(b.get("topic_index") is None for b in base)


# ════════════════════════════════════════════════════════════
# 服务层（需 MySQL）
# ════════════════════════════════════════════════════════════

MD_TOPIC_TEXT = (
    "# 缓存\n缓存雪崩是指大量缓存同时失效导致数据库压力激增。解决方案包括过期时间加随机值。\n\n"
    "# JWT\nJWT 是无状态令牌，服务端不保存会话信息，适合分布式系统认证。\n\n"
    "# Kafka\nKafka 通过 Partition 内顺序写入保证单分区消息有序消费。"
)


@requires_mysql
class TestKbServiceTopic:
    @pytest.fixture(autouse=True)
    def _init(self):
        from backend.db.schema import init_db
        init_db()

    def _upload_md(self, user_id, strategy):
        from backend.service.kb import kb_service
        return asyncio.run(kb_service.create_document(
            user_id=user_id, filename="topic.md",
            content=MD_TOPIC_TEXT.encode("utf-8"),
            chunk_size=200, chunk_overlap=0, chunk_strategy=strategy,
        ))

    def test_topic_upload_creates_parent_child_chunks(self):
        from backend.service.kb import kb_service

        doc = self._upload_md(940, "topic")  # 旧策略名 → 归一化为 parent_child
        try:
            assert doc["chunk_strategy"] == "parent_child"
            assert doc["topic_count"] == 3
            chunks = kb_service.list_chunks(940, doc["id"], set(), page_size=200)
            kinds = {c["kind"] for c in chunks["items"]}
            assert kinds == {"parent", "child"}
            parents = [c for c in chunks["items"] if c["kind"] == "parent"]
            assert len(parents) == 3
            assert any("缓存" in p["content"] for p in parents)
        finally:
            kb_service.delete_document(940, doc["id"], set())

    def test_list_chunks_kind_filter(self):
        from backend.service.kb import kb_service

        doc = self._upload_md(941, "parent_child")
        try:
            only_parent = kb_service.list_chunks(941, doc["id"], set(), page_size=200, kind="parent")
            assert only_parent["total"] == 3
            assert all(c["kind"] == "parent" for c in only_parent["items"])
            only_child = kb_service.list_chunks(941, doc["id"], set(), page_size=200, kind="child")
            assert only_child["total"] >= 3
            assert all(c["kind"] == "child" for c in only_child["items"])
        finally:
            kb_service.delete_document(941, doc["id"], set())

    def test_reprocess_switch_strategy(self):
        from backend.service.kb import kb_service

        doc = self._upload_md(942, "fixed")
        try:
            assert doc["chunk_strategy"] == "fixed"
            updated = asyncio.run(kb_service.reprocess_document(
                942, doc["id"], set(), chunk_strategy="topic",  # 旧名归一化
            ))
            assert updated["chunk_strategy"] == "parent_child"
            chunks = kb_service.list_chunks(942, doc["id"], set(), page_size=200)
            assert any(c["kind"] == "parent" for c in chunks["items"])
        finally:
            kb_service.delete_document(942, doc["id"], set())

    def test_delete_cleans_topics(self):
        from backend.service.kb import kb_service
        from backend.db.schema import get_conn

        doc = self._upload_md(943, "parent_child")
        kb_service.delete_document(943, doc["id"], set())
        conn = get_conn()
        try:
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_topics WHERE document_id = ?", (doc["id"],))
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            assert rows[0]["cnt"] == 0
        finally:
            conn.close()


@requires_mysql
class TestBM25KindFilter:
    def test_kind_filter(self):
        from backend.service.kb import kb_service, kb_retriever

        doc = asyncio.run(kb_service.create_document(
            user_id=944, filename="kind.md",
            content=MD_TOPIC_TEXT.encode("utf-8"),
            chunk_size=200, chunk_overlap=0, chunk_strategy="parent_child",
        ))
        try:
            r_all = kb_retriever.BM25Retriever(944, kind="all").retrieve("缓存雪崩", top_k=10)
            r_child = kb_retriever.BM25Retriever(944, kind="child").retrieve("缓存雪崩", top_k=10)
            r_base = kb_retriever.BM25Retriever(944, kind="base").retrieve("缓存雪崩", top_k=10)
            # 命中子片 → 增强为父片内容（kind=parent, is_child=True）
            assert any(c["kind"] == "parent" for c in r_all)
            assert r_child and all(c.get("is_child") for c in r_child)
            assert r_base == []  # 父子切片策略无 base 块
        finally:
            kb_service.delete_document(944, doc["id"], set())


# ════════════════════════════════════════════════════════════
# 评测 chunk_kind 传参（mock）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestEvalChunkKind:
    def test_run_passes_chunk_kind(self, monkeypatch):
        from backend.db.schema import init_db
        init_db()

        from backend.service.kb import kb_eval_service as svc

        captured = {}

        class FakeRetriever:
            name = "fake"

            def retrieve(self, query, top_k=5):
                return [{"chunk_id": 1, "content": "x", "score": 1.0, "is_gt": False}]

        def fake_get_retriever(user_id, mode="auto", kind="all"):
            captured["kind"] = kind
            return FakeRetriever(), []

        monkeypatch.setattr("backend.service.kb.kb_retriever.get_retriever", fake_get_retriever)
        monkeypatch.setattr(svc, "_get_model_config", lambda uid: None)  # 跳过生成/裁判

        set_id = svc.create_eval_set(945, "kind 测试")["id"]
        try:
            # 构造一个合法 chunk 作为 GT
            from backend.service.kb import kb_service
            doc = asyncio.run(kb_service.create_document(
                user_id=945, filename="k.txt", content="kind测试内容".encode("utf-8"),
                chunk_size=200, chunk_overlap=0,
            ))
            chunks = kb_service.list_chunks(945, doc["id"], set(), page_size=50)
            svc.add_item(945, set_id, set(), "问题", [chunks["items"][0]["id"]])

            async def _run():
                res = await svc.run_eval_set(
                    945, set_id, set(), top_k=5,
                    generate_answer=False, judge_enabled=False,
                    chunk_kind="topic",
                )
                for _ in range(200):
                    await asyncio.sleep(0.05)
                    run = svc.get_run(945, res["run_id"], set())
                    if run["status"] != "running":
                        return run
                raise AssertionError("run 超时")

            run = asyncio.run(_run())
            assert run["status"] == "done"
            assert captured.get("kind") == "topic"
            assert run["config"]["chunk_kind"] == "topic"
            kb_service.delete_document(945, doc["id"], set())
        finally:
            svc.delete_eval_set(945, set_id, set())
