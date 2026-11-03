"""
图片安全处理模块

融合了 Hermes vision_tools.py 中的安全层逻辑：
  - Magic-byte MIME 检测（不信任扩展名）
  - 格式归一化（BMP/TIFF/SVG → PNG）
  - SVG 栅格化
  - 文件大小上限检查

AgentForge 的图片来源（前端粘贴/上传、微信下载）本身不涉及 URL 下载，
因此 SSRF 防护和网络重试不在本模块中。
"""
import base64
import logging
import io
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 多模态模型支持的图片格式
SUPPORTED_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})

# 单张图片最大 50MB
MAX_IMAGE_BYTES = 50 * 1024 * 1024


def detect_image_mime_type(data: bytes) -> Optional[str]:
    """基于 magic bytes 检测图片格式，不信任文件名/扩展名。
    
    返回 MIME type 字符串，无法识别时返回 None。
    """
    header = data[:64]
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"BM"):
        return "image/bmp"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    # SVG: 没有 magic bytes，扫描开头是否包含 <svg
    text_head = ""
    try:
        text_head = data[:1024].decode("utf-8", errors="ignore").lower()
    except Exception:
        pass
    if "<svg" in text_head:
        return "image/svg+xml"
    return None


def validate_image_size(data: bytes) -> Optional[str]:
    """检查图片大小是否超限。返回错误消息或 None（通过）。"""
    if len(data) > MAX_IMAGE_BYTES:
        size_mb = len(data) / (1024 * 1024)
        return f"图片过大（{size_mb:.1f}MB，上限 {MAX_IMAGE_BYTES // (1024*1024)}MB）"
    return None


def _rasterize_svg_to_png(data: bytes) -> Optional[bytes]:
    """SVG → PNG 栅格化（best-effort，优先 cairosvg）。"""
    import tempfile

    # 1) cairosvg
    try:
        import cairosvg
        return cairosvg.svg2png(bytestring=data)
    except Exception:
        pass

    # 2) 写入临时文件用 rsvg-convert / inkscape
    try:
        import subprocess
        import shutil
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as svg_tmp:
            svg_tmp.write(data)
            svg_path = svg_tmp.name
        png_path = svg_path.replace(".svg", ".png")
        for cmd in (
            ["rsvg-convert", "-o", png_path, svg_path],
            ["inkscape", svg_path, "--export-type=png", f"--export-filename={png_path}"],
        ):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=30,
                                   stdin=subprocess.DEVNULL)
                    png_file = Path(png_path)
                    if png_file.exists() and png_file.stat().st_size > 0:
                        result = png_file.read_bytes()
                        png_file.unlink(missing_ok=True)
                        Path(svg_path).unlink(missing_ok=True)
                        return result
                except Exception:
                    continue
        Path(svg_path).unlink(missing_ok=True)
        Path(png_path).unlink(missing_ok=True)
    except Exception:
        pass

    return None


def _reencode_to_png(data: bytes, source_mime: str) -> Optional[bytes]:
    """用 Pillow 将任意格式重新编码为 PNG。"""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception as e:
        logger.debug(f"Pillow 重新编码失败 ({source_mime}): {e}")
    return None


def normalize_image(data: bytes, mime: str) -> Tuple[bytes, str, Optional[str]]:
    """确保图片格式在 SUPPORTED_MEDIA_TYPES 范围内。
    
    返回 (normalized_bytes, normalized_mime, error_message)。
    error_message 为 None 表示成功。
    """
    if mime in SUPPORTED_MEDIA_TYPES:
        return data, mime, None

    # SVG → PNG
    if mime == "image/svg+xml":
        png = _rasterize_svg_to_png(data)
        if png:
            return png, "image/png", None
        return data, mime, (
            "SVG 图片需要栅格化，但未安装 cairosvg/rsvg-convert/inkscape。"
            "请转换为 PNG/JPEG 后重试，或运行 pip install cairosvg。"
        )

    # 其他非标准格式（BMP、TIFF 等）→ PNG
    png = _reencode_to_png(data, mime)
    if png:
        return png, "image/png", None
    return data, mime, (
        f"图片格式 {mime!r} 不被多模态模型支持，且无法自动转换为 PNG。"
        "请转换为 PNG/JPEG/GIF/WebP 后重试。"
    )


def process_image_safe(data: bytes, source_mime: str = "") -> Tuple[Optional[str], Optional[str]]:
    """安全处理图片：检测类型 → 检查大小 → 归一化格式 → 返回 (data_url, error)。

    Args:
        data: 原始图片字节
        source_mime: 来源声称的 MIME type（可能不可信，仅作参考）

    Returns:
        (data_url, error_message)：成功时 error 为 None，data_url 为
        "data:image/xxx;base64,..."；失败时 data_url 为 None。
    """
    # 1. 检测真实 MIME
    mime = detect_image_mime_type(data)
    if not mime:
        return None, "无法识别图片格式，请使用 PNG/JPEG/GIF/WebP 格式"

    # 2. 大小检查
    size_err = validate_image_size(data)
    if size_err:
        return None, size_err

    # 3. 格式归一化
    norm_data, norm_mime, norm_err = normalize_image(data, mime)
    if norm_err:
        return None, norm_err

    # 4. 编码为 data URL
    b64 = base64.b64encode(norm_data).decode("ascii")
    data_url = f"data:{norm_mime};base64,{b64}"
    return data_url, None
