"""
知识库服务单元测试

- 解析器（builtin PDF/文本/GBK、扫描版检测）
- 切分（chunk 元数据/页码/overlap）
- MinerU 响应解析
- 名称净化 / 参数归一化
- 服务层 CRUD + 用户隔离（需 MySQL 可用，否则自动跳过）
"""
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path（兼容 pytest 与 python -m pytest 两种运行方式）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


# ════════════════════════════════════════════════════════════
# 工具 fixture
# ════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_pdf(tmp_path):
    """生成 3 页带文本的测试 PDF。"""

    def _make(pages=3, with_text=True) -> Path:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=False)
        for i in range(1, pages + 1):
            pdf.add_page()
            if with_text:
                pdf.set_font("helvetica", size=12)
                pdf.multi_cell(
                    0, 8,
                    f"Page {i} heading. " * 4
                    + f"This is the content of page {i}. " * 12,
                )
        path = tmp_path / f"test_{pages}p_{with_text}.pdf"
        pdf.output(str(path))
        return path

    return _make


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


# ════════════════════════════════════════════════════════════
# 解析器测试
# ════════════════════════════════════════════════════════════

class TestBuiltinParserPdf:
    def test_parse_pdf_extracts_pages(self, tmp_pdf):
        from backend.service.kb.kb_parsers import BuiltinParser

        path = tmp_pdf(pages=3, with_text=True)
        doc = BuiltinParser().parse(str(path))

        assert doc.parser == "builtin"
        assert len(doc.pages) == 3
        assert doc.scanned is False
        assert doc.pages[0].page_no == 1
        assert "Page 1 heading" in doc.pages[0].text
        assert "content of page 3" in doc.pages[2].text
        assert doc.text  # 全文拼接非空

    def test_parse_pdf_empty_detects_scanned(self, tmp_pdf):
        from backend.service.kb.kb_parsers import BuiltinParser

        path = tmp_pdf(pages=2, with_text=False)
        doc = BuiltinParser().parse(str(path))

        assert doc.scanned is True
        assert len(doc.pages) == 2
        assert any("扫描版" in w for w in doc.warnings)

    def test_parse_pdf_mostly_blank_detects_scanned(self, tmp_path):
        """页数≥5 且有效文本页占比 <20% → 扫描版。"""
        from backend.service.kb.kb_parsers import BuiltinParser
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=False)
        for i in range(1, 7):  # 6 页，仅 1 页有文字
            pdf.add_page()
            if i == 1:
                pdf.set_font("helvetica", size=12)
                pdf.cell(0, 8, "Only text page")
        path = tmp_path / "mostly_blank.pdf"
        pdf.output(str(path))

        doc = BuiltinParser().parse(str(path))
        assert doc.scanned is True


class TestBuiltinParserText:
    def test_parse_md_utf8(self, tmp_path):
        from backend.service.kb.kb_parsers import BuiltinParser

        path = tmp_path / "note.md"
        path.write_text("# 标题\n\n正文内容 hello", encoding="utf-8")
        doc = BuiltinParser().parse(str(path))

        assert doc.parser == "builtin"
        assert len(doc.pages) == 1
        assert doc.pages[0].page_no is None
        assert "# 标题" in doc.text

    def test_parse_txt_gbk_fallback(self, tmp_path):
        from backend.service.kb.kb_parsers import BuiltinParser

        path = tmp_path / "gbk.txt"
        path.write_bytes("中文内容 GBK 编码".encode("gbk"))
        doc = BuiltinParser().parse(str(path))

        assert "中文内容 GBK 编码" in doc.text
        assert not doc.warnings  # gbk 命中不应有警告

    def test_parse_missing_file_raises(self, tmp_path):
        from backend.service.kb.kb_parsers import BuiltinParser

        with pytest.raises(Exception):
            BuiltinParser().parse(str(tmp_path / "nope.md"))


# ════════════════════════════════════════════════════════════
# 回退链测试
# ════════════════════════════════════════════════════════════

class TestParseWithFallback:
    def test_mineru_unconfigured_falls_back_to_builtin(self, tmp_path):
        import os
        from backend.service.kb.kb_parsers import parse_with_fallback

        path = tmp_path / "a.md"
        path.write_text("hello fallback", encoding="utf-8")

        os.environ.pop("MINERU_API_URL", None)
        os.environ["KB_PARSER"] = "mineru_http"
        try:
            doc = parse_with_fallback(str(path), preference="mineru_http")
        finally:
            os.environ.pop("KB_PARSER", None)

        assert doc.parser == "builtin"
        assert "hello fallback" in doc.text

    def test_mineru_failure_degrades_with_warning(self, tmp_path, monkeypatch):
        import os
        from backend.service.kb.kb_parsers import parse_with_fallback

        path = tmp_path / "b.md"
        path.write_text("degrade me", encoding="utf-8")

        monkeypatch.setenv("KB_PARSER", "mineru_http")
        monkeypatch.setenv("MINERU_API_URL", "http://127.0.0.1:1")  # 必然连接失败
        monkeypatch.setenv("MINERU_TIMEOUT", "1")

        doc = parse_with_fallback(str(path), preference="mineru_http")
        assert doc.parser == "builtin"
        assert "degrade me" in doc.text
        assert any("降级" in w for w in doc.warnings)


# ════════════════════════════════════════════════════════════
# 切分测试
# ════════════════════════════════════════════════════════════

class TestChunkPages:
    def _page(self, no, text):
        from backend.service.kb.kb_parsers import KbPage
        return KbPage(page_no=no, text=text)

    def test_short_text_single_chunk(self):
        from backend.service.kb.kb_service import _chunk_pages

        chunks = _chunk_pages([self._page(1, "短文本")], chunk_size=1000, chunk_overlap=0)
        assert len(chunks) == 1
        assert chunks[0]["content"] == "短文本"
        assert chunks[0]["page_start"] == 1 and chunks[0]["page_end"] == 1

    def test_long_text_splits_with_page_metadata(self):
        from backend.service.kb.kb_service import _chunk_pages

        long_text = "这是测试句子。" * 300  # 约 2100 字 > chunk_size
        chunks = _chunk_pages([self._page(3, long_text)], chunk_size=1000, chunk_overlap=100)

        assert len(chunks) >= 2
        for c in chunks:
            assert c["page_start"] == 3 and c["page_end"] == 3
            assert 0 < c["char_count"] <= 1100  # chunk_size + overlap 内

    def test_overlap_keeps_tail(self):
        from backend.service.kb.kb_service import _chunk_pages

        text = "ABCDEFGHIJ" * 150  # 1500 字符
        chunks = _chunk_pages([self._page(None, text)], chunk_size=600, chunk_overlap=100)
        assert len(chunks) >= 3
        # overlap 生效：后一块开头包含前一块结尾的内容（ABC... 连续性验证）
        prev_tail = chunks[0]["content"][-20:]
        assert prev_tail in chunks[1]["content"]

    def test_empty_pages_skipped(self):
        from backend.service.kb.kb_service import _chunk_pages

        chunks = _chunk_pages(
            [self._page(1, "   "), self._page(2, "有效内容")],
            chunk_size=1000, chunk_overlap=0,
        )
        assert len(chunks) == 1
        assert chunks[0]["page_start"] == 2

    def test_chunk_cap_truncates(self, tmp_path, monkeypatch):
        import backend.service.kb.kb_service as kb_mod
        from backend.service.kb.kb_service import _parse_and_chunk

        monkeypatch.setattr(kb_mod, "_MAX_CHUNKS", 50)

        # 生成远超上限的内容：~150 个 chunk 的量
        big_text = "知识块内容测试。\n" * 2000
        path = tmp_path / "huge.txt"
        path.write_text(big_text, encoding="utf-8")

        result = _parse_and_chunk(str(path), "", chunk_size=100, chunk_overlap=0)
        assert len(result["chunks"]) == 50
        assert result["truncated"] is True
        assert any("截断" in w for w in result["warnings"])


# ════════════════════════════════════════════════════════════
# MinerU 响应解析
# ════════════════════════════════════════════════════════════

class TestMineruExtractMarkdown:
    def _resp(self, body, ctype="application/json"):
        class FakeResp:
            def __init__(self):
                self.text = body if isinstance(body, str) else str(body)
                self.headers = {"content-type": ctype}
                if not isinstance(body, str):
                    import json
                    self._data = body
                else:
                    self._data = None

            def json(self):
                if self._data is None:
                    raise ValueError("not json")
                return self._data

        return FakeResp()

    def test_json_markdown_key(self):
        from backend.service.kb.kb_parsers import MineruHttpParser

        parser = MineruHttpParser(api_url="http://x")
        out = parser._extract_markdown(self._resp({"markdown": "# 标题\n内容"}))
        assert "# 标题" in out

    def test_json_content_key(self):
        from backend.service.kb.kb_parsers import MineruHttpParser

        parser = MineruHttpParser(api_url="http://x")
        out = parser._extract_markdown(self._resp({"content": "纯内容"}))
        assert out == "纯内容"

    def test_plain_text_response(self):
        from backend.service.kb.kb_parsers import MineruHttpParser

        parser = MineruHttpParser(api_url="http://x")
        out = parser._extract_markdown(self._resp("raw markdown", ctype="text/plain"))
        assert out == "raw markdown"


# ════════════════════════════════════════════════════════════
# 名称净化 / 参数归一化
# ════════════════════════════════════════════════════════════

class TestSanitize:
    def test_illegal_chars_replaced(self):
        from backend.service.kb.kb_service import _sanitize_name
        assert _sanitize_name('a<b>c:d*e?f.pdf') == 'a_b_c_d_e_f.pdf'

    def test_path_traversal_stripped(self):
        from backend.service.kb.kb_service import _sanitize_name
        assert _sanitize_name(r'..\..\etc\passwd.pdf') == 'passwd.pdf'

    def test_empty_name(self):
        from backend.service.kb.kb_service import _sanitize_name
        assert _sanitize_name('') == 'unnamed'


class TestNormalizeChunkParams:
    def test_defaults(self):
        from backend.service.kb.kb_service import _normalize_chunk_params
        assert _normalize_chunk_params(None, None) == (1000, 200)

    def test_clamp(self):
        from backend.service.kb.kb_service import _normalize_chunk_params
        size, overlap = _normalize_chunk_params("99999", "99999")
        assert size == 8000
        assert overlap < size

    def test_invalid_falls_back(self):
        from backend.service.kb.kb_service import _normalize_chunk_params
        assert _normalize_chunk_params("abc", "xyz") == (1000, 200)


# ════════════════════════════════════════════════════════════
# 服务层 DB 集成测试（需 MySQL）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestKbServiceDb:
    @pytest.fixture(autouse=True)
    def _init(self, tmp_pdf):
        from backend.db.schema import init_db
        init_db()  # 幂等：建表 + 权限播种
        self._tmp_pdf = tmp_pdf

    def _upload(self, user_id, name="unit_test.pdf", perms=None, **kw):
        from backend.service.kb import kb_service

        path = self._tmp_pdf(pages=2, with_text=True)
        content = path.read_bytes()
        return asyncio.run(kb_service.create_document(
            user_id=user_id, filename=name, content=content, **kw
        )), content

    def test_create_parses_and_chunks(self):
        doc, _ = self._upload(user_id=1)
        assert doc["status"] == "parsed"
        assert doc["page_count"] == 2
        assert doc["chunk_count"] >= 2
        assert doc["sha256"]

        from backend.service.kb import kb_service
        kb_service.delete_document(1, doc["id"], {"kb.manage"})

    def test_invalid_ext_rejected(self):
        from backend.service.kb import kb_service
        with pytest.raises(kb_service.KbInvalidFile):
            asyncio.run(kb_service.create_document(
                user_id=1, filename="evil.exe", content=b"MZ\x00\x01", 
            ))

    def test_ownership_isolation(self):
        from backend.service.kb import kb_service

        doc, _ = self._upload(user_id=10, name="owner_doc.pdf")
        try:
            # 其他用户（无 kb.manage）→ 404 语义
            with pytest.raises(kb_service.KbNotFound):
                kb_service.get_document(20, doc["id"], set())
            with pytest.raises(kb_service.KbNotFound):
                kb_service.list_chunks(20, doc["id"], set())
            # 管理员（kb.manage）→ 可见
            visible = kb_service.get_document(20, doc["id"], {"kb.manage"})
            assert visible["id"] == doc["id"]
            # 自己的列表能看到
            listing = kb_service.list_documents(10, set(), page_size=100)
            assert any(d["id"] == doc["id"] for d in listing["items"])
            # 别人的列表看不到
            other = kb_service.list_documents(20, set(), page_size=100)
            assert not any(d["id"] == doc["id"] for d in other["items"])
        finally:
            kb_service.delete_document(10, doc["id"], set())

    def test_reprocess_changes_params(self):
        from backend.service.kb import kb_service

        doc, _ = self._upload(user_id=30, name="reprocess_doc.pdf")
        try:
            updated = asyncio.run(kb_service.reprocess_document(
                30, doc["id"], set(), chunk_size=400, chunk_overlap=50,
            ))
            assert updated["chunk_size"] == 400
            assert updated["chunk_overlap"] == 50
            assert updated["chunk_count"] >= doc["chunk_count"]
        finally:
            kb_service.delete_document(30, doc["id"], set())

    def test_delete_removes_rows_and_file(self):
        from backend.service.kb import kb_service

        doc, _ = self._upload(user_id=40, name="delete_doc.pdf")
        result = kb_service.delete_document(40, doc["id"], set())
        assert result["deleted"] is True

        with pytest.raises(kb_service.KbNotFound):
            kb_service.get_document(40, doc["id"], set())
        # 该用户的存储目录已清空（文件随删除移除）
        user_dir = kb_service.kb_root() / "40"
        remaining = list(user_dir.glob("*")) if user_dir.exists() else []
        assert remaining == []

    def test_empty_pdf_marks_needs_ocr(self):
        from backend.service.kb import kb_service

        pdf = self._tmp_pdf(pages=1, with_text=False)
        doc = asyncio.run(kb_service.create_document(
            user_id=50, filename="scanned.pdf", content=pdf.read_bytes(),
        ))
        assert doc["status"] == "needs_ocr"
        assert doc["chunk_count"] == 0
        kb_service.delete_document(50, doc["id"], set())

    def test_get_document_text(self):
        from backend.service.kb import kb_service

        doc, _ = self._upload(user_id=60, name="text_doc.pdf")
        try:
            result = kb_service.get_document_text(60, doc["id"], set())
            assert result["char_count"] > 0
            assert "Page 1 heading" in result["text"]
            assert result["needs_reprocess"] is False
            # 其他用户不可见（404 语义）
            with pytest.raises(kb_service.KbNotFound):
                kb_service.get_document_text(61, doc["id"], set())
        finally:
            kb_service.delete_document(60, doc["id"], set())
