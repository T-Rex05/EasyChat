"""本地磁盘文件存储 Adapter（设计 §4）。

- 所有路径从显式配置的 root 派生，数据库只存相对 `storage_key`；
- 原始文件名不参与路径（只用于展示），随机 file_id 防同名覆盖；
- 写入顺序：staging 分块写 + 计算 hash → flush/fsync → 同文件系统原子 rename
  → 父目录 fsync（平台支持时）→ 再由服务层提交 SQLite ready 元数据；
- 文件系统与 SQLite 没有共享事务：中断由 `reconcile` 对账，不假装原子。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import AsyncIterable, BinaryIO, Iterable

from backend.modules.files.contracts import (
    DEFAULT_MAX_FILE_BYTES,
    KIND_DOCUMENT,
    KIND_IMAGE,
    KIND_SPREADSHEET,
    FileRecord,
)
from backend.shared.errors import InvalidInputError, StorageUnavailableError

_KEY_RE = re.compile(r"^(uploads|derived|reports)/[0-9A-Za-z_./-]+$")
_MAX_KEY_LENGTH = 400
_HEAD_BYTES = 4096

# 内容签名优先于扩展名（类型伪装按实际内容判定）
_MIME_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
)

_EXT_BY_MIME: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/zip": ".zip",
    "application/json": ".json",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/octet-stream": ".bin",
}

_TEXT_EXTENSIONS = frozenset({".csv", ".txt", ".md", ".json", ".tsv"})
_TABLE_EXTENSIONS = frozenset({".csv", ".tsv", ".xlsx"})


def kind_for(mime: str, extension: str, *, declared: str = "") -> str:
    if declared:
        return declared
    if mime.startswith("image/"):
        return KIND_IMAGE
    if extension in _TABLE_EXTENSIONS:
        return KIND_SPREADSHEET
    if mime.startswith("text/") or mime in {"application/pdf", "application/json"}:
        return KIND_DOCUMENT
    return KIND_DOCUMENT if mime != "application/octet-stream" else "other"


def detect_content_mime(head: bytes, original_name: str) -> str:
    """按内容签名判定 MIME；文本按可解码性判定。返回最可信的 verified_mime。"""
    suffix = Path(original_name or "").suffix.lower()
    for signature, mime in _MIME_SIGNATURES:
        if head.startswith(signature):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"PK\x03\x04":
        if suffix == ".xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if suffix == ".docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return "application/zip"
    if suffix in _TEXT_EXTENSIONS:
        sample = head[:4096]
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                sample.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return "application/octet-stream"
        if suffix in (".csv", ".tsv"):
            return "text/csv"
        if suffix == ".json":
            return "application/json"
        if suffix == ".md":
            return "text/markdown"
        return "text/plain"
    return "application/octet-stream"


def verified_extension(verified_mime: str, original_name: str) -> str:
    """最终落盘扩展名由 verified mime 决定；未知类型统一 .bin（不沿用可疑后缀）。"""
    return _EXT_BY_MIME.get(verified_mime, ".bin")


class LocalFileStore:
    """本地磁盘具体实现；不预建对象存储平台。"""

    SUBDIRS = ("uploads", "derived", "reports", "staging")

    def __init__(self, root: Path, *, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None:
        self.root = Path(root)
        self.max_bytes = int(max_bytes)
        for name in self.SUBDIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    # ---- 路径 ------------------------------------------------------------------

    def build_key(
        self, *, owner_id: int, file_id: str, extension: str, now: datetime, prefix: str = "uploads"
    ) -> str:
        if prefix not in ("uploads", "derived", "reports"):
            raise InvalidInputError(f"非法存储前缀: {prefix}")
        ext = extension if extension.startswith(".") else f".{extension}"
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", ext):
            ext = ".bin"
        return f"{prefix}/{int(owner_id)}/{now:%Y}/{now:%m}/{file_id}{ext}"

    def absolute_path(self, storage_key: str) -> Path:
        """校验并解析相对 key；拒绝穿越、绝对路径与符号链接逃逸。"""
        if not isinstance(storage_key, str) or not storage_key or len(storage_key) > _MAX_KEY_LENGTH:
            raise InvalidInputError("非法存储键")
        if not _KEY_RE.match(storage_key) or ".." in storage_key.split("/"):
            raise InvalidInputError("非法存储键")
        candidate = (self.root / storage_key).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise InvalidInputError("存储键越界")
        return candidate

    def staging_path(self, upload_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-z_]{1,64}", upload_id):
            raise InvalidInputError("非法暂存标识")
        return self.root / "staging" / f"{upload_id}.part"

    # ---- 写入 ------------------------------------------------------------------

    async def write_chunks(
        self,
        chunks: AsyncIterable[bytes] | Iterable[bytes],
        *,
        staging_path: Path,
        max_bytes: int | None = None,
    ) -> tuple[int, str, bytes]:
        """分块写 staging 并计算 sha256；返回 (size, sha256, 前4KiB内容)。

        超限/写失败清理半成品，不返回“已保存”。
        """
        limit = int(max_bytes if max_bytes is not None else self.max_bytes)
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        head = b""
        handle = None

        def _fail(message: str, exc: BaseException) -> StorageUnavailableError:
            _close_quietly(handle)
            _safe_unlink(staging_path)
            return StorageUnavailableError(f"{message}: {exc}")

        try:
            handle = staging_path.open("wb")
        except OSError as exc:
            raise _fail("创建暂存文件失败", exc) from exc
        try:
            async for chunk in _aiter_chunks(chunks):
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise InvalidInputError("文件流必须是字节块")
                data = bytes(chunk)
                size += len(data)
                if size > limit:
                    raise InvalidInputError(f"文件超过上限（{size} > {limit} 字节）")
                if len(head) < _HEAD_BYTES:
                    head += data[: _HEAD_BYTES - len(head)]
                digest.update(data)
                try:
                    handle.write(data)
                except OSError as exc:
                    raise _fail("写入文件失败", exc) from exc
            try:
                handle.flush()
                os.fsync(handle.fileno())
            except OSError as exc:
                raise _fail("刷新文件失败", exc) from exc
            return size, digest.hexdigest(), head
        except BaseException:
            # 含超限/上游流中断/取消：都不留半成品，也不返回“已保存”
            _close_quietly(handle)
            _safe_unlink(staging_path)
            raise
        finally:
            _close_quietly(handle)

    def finalize(self, staging_path: Path, storage_key: str) -> Path:
        """原子移动到最终位置（同文件系统 rename），并尽力 fsync 父目录。"""
        destination = self.absolute_path(storage_key)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging_path, destination)
        except OSError as exc:
            _safe_unlink(staging_path)
            raise StorageUnavailableError(f"文件落盘失败: {exc}") from exc
        _fsync_dir(destination.parent)
        return destination

    def copy_into(self, source: Path, storage_key: str) -> Path:
        """把已有文件（如派生物/报告）复制到受管位置；源文件不被修改。"""
        destination = self.absolute_path(storage_key)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
        except OSError as exc:
            _safe_unlink(destination)
            raise StorageUnavailableError(f"复制文件失败: {exc}") from exc
        _fsync_dir(destination.parent)
        return destination

    def delete(self, storage_key: str) -> bool:
        path = self.absolute_path(storage_key)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise StorageUnavailableError(f"删除文件失败: {exc}") from exc

    # ---- 读取 ------------------------------------------------------------------

    def open_read(self, storage_key: str) -> BinaryIO:
        path = self.absolute_path(storage_key)
        if not path.is_file():
            raise StorageUnavailableError("文件不存在或不可读")
        try:
            return path.open("rb")
        except OSError as exc:
            raise StorageUnavailableError(f"打开文件失败: {exc}") from exc

    def read_head(self, storage_key: str, limit: int = 4096) -> bytes:
        with self.open_read(storage_key) as handle:
            return handle.read(max(1, int(limit)))

    def stat(self, storage_key: str) -> os.stat_result | None:
        try:
            path = self.absolute_path(storage_key)
        except InvalidInputError:
            return None
        try:
            return path.stat()
        except OSError:
            return None

    def sha256_of(self, storage_key: str) -> str | None:
        try:
            handle = self.open_read(storage_key)
        except StorageUnavailableError:
            return None
        digest = hashlib.sha256()
        with handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # ---- 配额/水位 ---------------------------------------------------------------

    def disk_free_bytes(self) -> int:
        try:
            return int(shutil.disk_usage(self.root).free)
        except OSError:
            return 0

    def usage_bytes(self, owner_id: int | None = None) -> int:
        base = self.root / "uploads"
        if owner_id is not None:
            base = base / str(int(owner_id))
        total = 0
        if not base.exists():
            return 0
        for path in base.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total


def _aiter_chunks(chunks):
    """同时支持同步/异步可迭代字节流；不把整个文件读进内存。"""
    if hasattr(chunks, "__aiter__"):
        return chunks
    return _SyncChunks(chunks)


class _SyncChunks:
    def __init__(self, iterable: Iterable[bytes]) -> None:
        self._iterable = iterable

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for chunk in self._iterable:
            yield chunk


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _close_quietly(handle) -> None:
    if handle is None:
        return
    try:
        handle.close()
    except OSError:
        pass


def _fsync_dir(path: Path) -> None:
    """父目录 fsync（仅 POSIX 有意义）；Windows/不支持时静默跳过并在运维文档注明。"""
    if os.name != "posix":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def file_record_from_row(row) -> FileRecord:
    return FileRecord(
        file_id=str(row["id"]),
        owner_id=int(row["owner_id"]),
        original_name=str(row["original_name"]),
        verified_mime=str(row["verified_mime"]),
        size_bytes=int(row["size_bytes"]),
        sha256=str(row["sha256"]),
        status=str(row["status"]),
        kind=str(row["kind"]),
        source=str(row["source"]),
        retention_policy=str(row["retention_policy"]),
        created_at=str(row["created_at"]),
        deleted_at=row["deleted_at"],
        error=row["error"],
    )
