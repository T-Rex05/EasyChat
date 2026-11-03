"""
知识库解析器插件 — 把上传的文档提取为纯文本（含页码信息）

设计目标：
1. 解析器可插拔：内置 BuiltinParser（零配置）+ 远程 MineruHttpParser（高质量解析）
2. 回退链：优先使用指定解析器，失败自动降级 BuiltinParser
3. 扫描版 PDF 检测：无文字层的 PDF 标记 scanned=True（前端提示「需 OCR」）

配置（.env 环境变量）：
    KB_PARSER=auto                  # auto | builtin | mineru_http
    MINERU_API_URL=http://host:8000  # MinerU 服务地址（自建 mineru-api 或官方云端 API）
    MINERU_API_KEY=                  # 可选，API 密钥
    MINERU_TIMEOUT=120               # 请求超时（秒）
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from backend.utils.log_utils import log, rag

logger = log

# 可解析的文本类扩展名（纯文本直接读取）
_TEXT_EXTS = frozenset({
    ".md", ".markdown", ".txt", ".csv", ".json",
    ".html", ".htm", ".log", ".ini", ".cfg", ".yaml", ".yml", ".xml", ".sql",
})
# 知识库白名单扩展名（服务层校验用）
ALLOWED_EXTS = frozenset({
    ".pdf", ".md", ".markdown", ".txt", ".docx", ".doc",
    ".pptx", ".xlsx", ".csv", ".json", ".html", ".htm", ".log",
})


@dataclass
class KbPage:
    """单页/单段文本（带页码）"""
    page_no: Optional[int]  # None 表示无页码概念（md/txt 等）
    text: str


@dataclass
class ParsedDocument:
    """解析结果"""
    text: str = ""                      # 全文（页间以双换行连接）
    pages: List[KbPage] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scanned: bool = False               # 扫描版 PDF（无文字层）
    parser: str = "builtin"             # 实际使用的解析器

    def append_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning(f"[KB] {msg}")


class BaseParser:
    """解析器接口"""

    name = "base"

    def parse(self, file_path: str) -> ParsedDocument:
        raise NotImplementedError


# ════════════════════════════════════════════════════════════
# 内置解析器（零配置）
# ════════════════════════════════════════════════════════════

class BuiltinParser(BaseParser):
    """内置轻量解析器：pypdf + python-docx + 纯文本（GBK 兜底）。"""

    name = "builtin"

    def parse(self, file_path: str) -> ParsedDocument:
        ext = Path(file_path).suffix.lower()
        doc = ParsedDocument(parser=self.name)

        try:
            if ext == ".pdf":
                self._parse_pdf(file_path, doc)
            elif ext in (".docx", ".doc"):
                self._parse_docx(file_path, doc)
            elif ext == ".pptx":
                self._parse_pptx(file_path, doc)
            elif ext == ".xlsx":
                self._parse_xlsx(file_path, doc)
            elif ext in _TEXT_EXTS:
                self._parse_text(file_path, doc)
            else:
                # 白名单外（理论不会走到这里）：尝试纯文本
                self._parse_text(file_path, doc)
        except Exception as e:  # noqa: BLE001 — 解析失败统一标记，由上层决定降级
            doc.append_warning(f"解析失败: {e}")
            raise

        doc.text = "\n\n".join(p.text for p in doc.pages if p.text.strip())
        return doc

    # ── PDF（逐页提取，页码精确）──

    def _parse_pdf(self, file_path: str, doc: ParsedDocument) -> None:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        text_pages = 0
        total_chars = 0
        for i, page in enumerate(reader.pages, start=1):
            try:
                t = (page.extract_text() or "").strip()
            except Exception as e:  # noqa: BLE001 — 单页失败不阻断整篇
                doc.append_warning(f"第 {i} 页提取失败: {e}")
                t = ""
            total_chars += len(t)
            if t:
                text_pages += 1
            doc.pages.append(KbPage(page_no=i, text=t))

        page_count = len(doc.pages)
        # 扫描版检测：完全无文本，或页数较多时有效文本页占比过低
        if total_chars == 0:
            doc.scanned = True
            doc.append_warning("PDF 未提取到任何文本，可能为扫描版（需 OCR）")
        elif page_count >= 5 and text_pages < page_count * 0.2:
            doc.scanned = True
            doc.append_warning(
                f"PDF 仅 {text_pages}/{page_count} 页含文字层，疑似扫描版（需 OCR）"
            )

    # ── DOCX ──

    def _parse_docx(self, file_path: str, doc: ParsedDocument) -> None:
        try:
            from docx import Document
        except ImportError:
            doc.append_warning("需要安装 python-docx 才能解析 DOCX")
            raise

        document = Document(file_path)
        parts: List[str] = []
        for para in document.paragraphs:
            if para.text.strip():
                parts.append(para.text)
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        text = "\n".join(parts)
        if not text:
            doc.append_warning("DOCX 无可提取的文本内容")
        doc.pages.append(KbPage(page_no=None, text=text))

    # ── PPTX（每页幻灯片映射为一个「页」）──

    def _parse_pptx(self, file_path: str, doc: ParsedDocument) -> None:
        try:
            from pptx import Presentation
        except ImportError:
            doc.append_warning("需要安装 python-pptx 才能解析 PPTX")
            raise

        prs = Presentation(file_path)
        for i, slide in enumerate(prs.slides, start=1):
            texts: List[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        t = "".join(run.text for run in para.runs).strip()
                        if not t:
                            t = para.text.strip()
                        if t:
                            texts.append(t)
            doc.pages.append(KbPage(page_no=i, text="\n".join(texts)))
        if not any(p.text for p in doc.pages):
            doc.append_warning("PPTX 无可提取的文本内容")

    # ── XLSX（每个 sheet 映射为一个「页」，最多 1000 行）──

    def _parse_xlsx(self, file_path: str, doc: ParsedDocument) -> None:
        try:
            import openpyxl
        except ImportError:
            doc.append_warning("需要安装 openpyxl 才能解析 XLSX")
            raise

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        try:
            for name in wb.sheetnames:
                ws = wb[name]
                rows: List[str] = []
                for row in ws.iter_rows(max_row=1000, values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    if any(cells):
                        rows.append(" | ".join(cells))
                if rows:
                    doc.pages.append(KbPage(page_no=None, text="\n".join(rows)))
        finally:
            wb.close()
        if not doc.pages:
            doc.append_warning("XLSX 无可提取的内容")

    # ── 纯文本（UTF-8 → GBK 兜底）──

    def _parse_text(self, file_path: str, doc: ParsedDocument) -> None:
        raw = Path(file_path).read_bytes()
        text = None
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if text is None:
            text = raw.decode("utf-8", errors="replace")
            doc.append_warning("文本编码无法识别，已按 UTF-8 替换模式读取")
        doc.pages.append(KbPage(page_no=None, text=text))


# ════════════════════════════════════════════════════════════
# MinerU 远程解析器（高质量 PDF 解析，服务端部署）
# ════════════════════════════════════════════════════════════

class MineruHttpParser(BaseParser):
    """
    通过 HTTP 调用 MinerU 服务解析文档。

    MinerU 本地跑很重（PyTorch + 数 GB 模型），推荐部署为独立服务：
    - 自建：mineru-api（GPU 服务器），暴露 POST /file_parse
    - 或使用 MinerU 官方云端 API（在 MINERU_API_URL 配置其网关地址）

    返回格式兼容：JSON {"markdown": ...} / {"content": ...} / {"text": ...} / 纯文本。
    """

    name = "mineru_http"

    def __init__(self, api_url: str, api_key: str = "", timeout: float = 120.0):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def parse(self, file_path: str) -> ParsedDocument:
        import httpx

        endpoint = f"{self.api_url}/file_parse"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with open(file_path, "rb") as fh:
            files = {"file": (Path(file_path).name, fh, "application/octet-stream")}
            try:
                resp = httpx.post(
                    endpoint, files=files, headers=headers,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise RuntimeError(f"MinerU 服务请求失败: {e}") from e

        text = self._extract_markdown(resp)
        if not text.strip():
            raise RuntimeError("MinerU 返回内容为空")

        doc = ParsedDocument(parser=self.name)
        doc.pages.append(KbPage(page_no=None, text=text))
        return doc

    def _extract_markdown(self, resp) -> str:
        """从 MinerU 响应中提取 markdown 文本（兼容多种返回格式）。"""
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            try:
                data = resp.json()
            except ValueError:
                return resp.text
            if isinstance(data, dict):
                for key in ("markdown", "content", "text", "result"):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return val
                return json.dumps(data, ensure_ascii=False)
            return str(data)
        return resp.text


# ════════════════════════════════════════════════════════════
# 工厂 + 回退链
# ════════════════════════════════════════════════════════════

def get_parser(preference: str = "") -> BaseParser:
    """
    按偏好创建解析器。

    Args:
        preference: builtin | mineru_http | 空（空则读 KB_PARSER 环境变量）

    Returns:
        解析器实例；mineru_http 未配置时回退 builtin 并返回 (parser, note)
    """
    mode = (preference or os.getenv("KB_PARSER", "auto")).strip().lower()
    if mode in ("mineru", "mineru_http", "mineru-api"):
        api_url = os.getenv("MINERU_API_URL", "").strip()
        if api_url:
            return MineruHttpParser(
                api_url=api_url,
                api_key=os.getenv("MINERU_API_KEY", "").strip(),
                timeout=float(os.getenv("MINERU_TIMEOUT", "120")),
            )
        logger.warning("[KB] KB_PARSER=mineru_http 但 MINERU_API_URL 未配置，回退 builtin")
    return BuiltinParser()


def parse_with_fallback(
    file_path: str,
    preference: str = "",
) -> ParsedDocument:
    """
    解析文档（带回退链）。

    指定 mineru_http 时：MinerU 失败/未配置 → 自动降级 BuiltinParser，
    降级原因记录在 doc.warnings 中。
    """
    primary = get_parser(preference)
    try:
        return primary.parse(file_path)
    except Exception as e:  # noqa: BLE001
        if primary.name == "builtin":
            raise
        logger.warning(f"[KB] {primary.name} 解析失败，降级 builtin: {e}")
        fallback = BuiltinParser()
        doc = fallback.parse(file_path)
        doc.parser = fallback.name
        doc.append_warning(f"{primary.name} 解析失败已降级 builtin: {e}")
        return doc
