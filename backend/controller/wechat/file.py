"""微信监听器 - 文件处理"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agentforge.wechat_listener")

# 可读文本文件扩展名
_TEXT_READABLE_EXTS = frozenset({
    ".md", ".txt", ".py", ".js", ".ts", ".json", ".csv",
    ".html", ".css", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".sql", ".log"
})
_PDF_EXT = ".pdf"


def _read_file_content(file_path: str) -> Optional[str]:
    """
    读取文件内容供 LLM 使用。支持文本文件 + PDF。
    
    Office/PDF 用流式解析库，不设大小限制
    纯文本文件限制 500KB 防止 Token 爆炸
    """
    ext = Path(file_path).suffix.lower()
    try:
        size = os.path.getsize(file_path)
    except Exception:
        return None
    
    text_size_limit = 500 * 1024
    
    # ── Office 文件（不设大小限制，库流式读取）──
    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(file_path)
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paras) if paras else "(DOCX 无可提取的文本内容)"
        except ImportError:
            return "(需要安装 python-docx: pip install python-docx)"
        except Exception as e:
            return f"(DOCX 读取失败: {e})"
    
    if ext == ".pptx":
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            slides = []
            for i, slide in enumerate(prs.slides, 1):
                texts = []
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            t = para.text.strip()
                            if t:
                                texts.append(t)
                if texts:
                    slides.append(f"--- 第{i}页 ---\n" + "\n".join(texts))
            return "\n\n".join(slides) if slides else "(PPTX 无可提取的文本内容)"
        except ImportError:
            return "(需要安装 python-pptx: pip install python-pptx)"
        except Exception as e:
            return f"(PPTX 读取失败: {e})"
    
    if ext == ".xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            sheets = []
            for name in wb.sheetnames:
                ws = wb[name]
                rows = []
                for row in ws.iter_rows(max_row=100, values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    rows.append(" | ".join(cells))
                if rows:
                    sheets.append(f"--- Sheet: {name} ---\n" + "\n".join(rows))
            wb.close()
            return "\n\n".join(sheets) if sheets else "(XLSX 无可提取的内容)"
        except ImportError:
            return "(需要安装 openpyxl: pip install openpyxl)"
        except Exception as e:
            return f"(XLSX 读取失败: {e})"
    
    # ── PDF ──
    if ext == _PDF_EXT:
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
            return "\n\n".join(pages) if pages else "(PDF 无可提取的文本内容)"
        except ImportError:
            return "(需要安装 pypdf 才能读取 PDF 内容: pip install pypdf)"
        except Exception as e:
            return f"(PDF 读取失败: {e})"
    
    # ── 文本文件（限制 500KB，防 Token 爆炸）──
    if ext not in _TEXT_READABLE_EXTS:
        return None
    if size > text_size_limit:
        return f"(文件过大 {size//1024}KB，请登录服务器查看)"
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return None
