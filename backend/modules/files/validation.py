"""受控内容校验：图片像素上限与压缩容器展开上限（设计 §6）。

不执行宏、不计算公式、不访问外链；只读头部与 zip 目录，不解压业务内容。
"""
from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

from backend.modules.files.contracts import (
    DEFAULT_MAX_IMAGE_PIXELS,
    DEFAULT_MAX_XLSX_ENTRIES,
    DEFAULT_MAX_XLSX_UNCOMPRESSED,
)
from backend.shared.errors import InvalidInputError


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """从图片头部解析像素尺寸；无法识别返回 None（不猜测）。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if data.startswith(b"GIF8") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return int(width), int(height)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp_dimensions(data)
    if data.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(data)
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return int(width), int(height)
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return int((bits & 0x3FFF) + 1), int(((bits >> 14) & 0x3FFF) + 1)
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    index = 2
    size = len(data)
    while index + 9 < size:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xD8, 0xD9):
            index += 2
            continue
        segment_length = struct.unpack(">H", data[index + 2: index + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height, width = struct.unpack(">HH", data[index + 5: index + 9])
            return int(width), int(height)
        index += 2 + segment_length
    return None


def validate_image_size(
    data: bytes, *, max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS
) -> tuple[int, int] | None:
    """超过像素上限拒绝分析（原图若已保存仍保留，只标分析受限）。"""
    dims = image_dimensions(data)
    if dims is None:
        return None
    width, height = dims
    if width <= 0 or height <= 0:
        raise InvalidInputError("图片尺寸非法")
    if width * height > int(max_pixels):
        raise InvalidInputError(
            f"图片像素超过上限（{width}x{height} > {max_pixels} 像素）"
        )
    return dims


@dataclass(frozen=True, slots=True)
class ArchiveInfo:
    entries: int
    total_uncompressed: int
    names: tuple[str, ...]


def inspect_zip(
    path: Path,
    *,
    max_entries: int = DEFAULT_MAX_XLSX_ENTRIES,
    max_uncompressed: int = DEFAULT_MAX_XLSX_UNCOMPRESSED,
) -> ArchiveInfo:
    """检查压缩容器：条目数/展开总量/路径穿越；不执行任何内容。"""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise InvalidInputError(f"压缩容器损坏或不可读: {exc}") from exc
    if len(infos) > int(max_entries):
        raise InvalidInputError(f"压缩容器条目过多（{len(infos)} > {max_entries}）")
    total = 0
    names: list[str] = []
    for info in infos:
        name = info.filename
        if name.startswith("/") or ".." in Path(name.replace("\\", "/")).parts:
            raise InvalidInputError(f"压缩容器包含越界路径: {name[:120]}")
        total += int(info.file_size)
        if total > int(max_uncompressed):
            raise InvalidInputError(
                f"压缩容器展开总量超过上限（{total} > {max_uncompressed} 字节）"
            )
        names.append(name)
    return ArchiveInfo(entries=len(infos), total_uncompressed=total, names=tuple(names))
