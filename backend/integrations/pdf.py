"""PDF 能力 Adapter：默认关闭；未启用/未安装依赖时明确不可用，不 import 渲染栈。

真实渲染在独立 Python 子进程中执行，超时硬终止；便于以后替换为容器/远程渲染。
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any, Protocol

from backend.shared.errors import CapabilityUnavailableError

DEFAULT_RENDER_TIMEOUT = 60.0


class PdfRenderer(Protocol):
    capability: str

    async def render(self, html: str, dest: Path, *, timeout: float = DEFAULT_RENDER_TIMEOUT) -> Path: ...


class DisabledPdfRenderer:
    capability = "disabled"

    async def render(self, html: str, dest: Path, *, timeout: float = DEFAULT_RENDER_TIMEOUT) -> Path:
        raise CapabilityUnavailableError("PDF 能力未启用或渲染依赖缺失")


class SubprocessPdfRenderer:
    """独立子进程渲染；不把 weasyprint/字体依赖带进主进程。"""

    capability = "weasyprint-subprocess"
    _SCRIPT = (
        "import sys\n"
        "from weasyprint import HTML\n"
        "HTML(filename=sys.argv[1]).write_pdf(sys.argv[2])\n"
    )

    async def render(self, html: str, dest: Path, *, timeout: float = DEFAULT_RENDER_TIMEOUT) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        html_path = dest.with_suffix(f".{uuid.uuid4().hex[:8]}.html")
        html_path.write_text(html, encoding="utf-8")
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", self._SCRIPT, str(html_path), str(dest),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise CapabilityUnavailableError("PDF 渲染超时，已终止渲染进程")
            if process.returncode != 0:
                raise CapabilityUnavailableError(
                    f"PDF 渲染失败: {stderr[-500:].decode('utf-8', 'replace')}"
                )
            if not dest.is_file() or dest.stat().st_size == 0:
                raise CapabilityUnavailableError("PDF 渲染未产生有效文件")
            return dest
        finally:
            html_path.unlink(missing_ok=True)


def build_pdf_renderer(settings: Any) -> PdfRenderer:
    if not getattr(settings, "pdf_enabled", False):
        return DisabledPdfRenderer()
    if importlib.util.find_spec("weasyprint") is None:
        return DisabledPdfRenderer()
    return SubprocessPdfRenderer()
