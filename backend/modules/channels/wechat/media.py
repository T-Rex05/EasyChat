"""媒体引用 → 受限本地文件 + 附件元数据的下载/解密 Adapter。

只处理 iLink 的 CDN 下载与 AES-128-ECB 解密；下载流式落盘并限制大小，
不在内存里保留图片/文件副本。测试注入 FakeMediaFetcher，不触网。
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from backend.modules.channels.contracts import MAX_MEDIA_BYTES, MediaRef
from backend.modules.channels.wechat.account import CDN_BASE_URL, IlinkTransport, TransportError
from backend.modules.channels.wechat.urlpolicy import ALLOWED_MEDIA_HOSTS, is_allowed_media_url

# 与旧实现保持一致的文件接收白名单（空扩展名沿用旧行为放行）
ALLOWED_FILE_EXTENSIONS = frozenset({
    ".pdf", ".md", ".txt", ".docx", ".xlsx", ".pptx",
    ".zip", ".json", ".csv", ".py", ".js", ".html", ".css",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".mp3", ".m4a", ".wav", ".ogg", ".opus", ".amr", ".silk", ".aac", ".webm",
})
ALLOWED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})


class MediaFetchError(RuntimeError):
    """下载/解密/白名单校验失败；调用方记录并继续（不阻塞文字消息）。"""


@dataclass(frozen=True, slots=True)
class FetchedMedia:
    path: Path
    size: int
    sha256: str
    mime: str
    file_name: str


class MediaFetcher(Protocol):
    async def fetch(
        self, ref: MediaRef, dest_dir: Path, *, max_bytes: int = MAX_MEDIA_BYTES
    ) -> FetchedMedia: ...


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        return data
    if data.endswith(bytes([pad_len]) * pad_len):
        return data[:-pad_len]
    return data


def _parse_aes_key(aes_key_b64: str) -> bytes:
    """兼容两种 iLink 密钥编码：base64(raw16) 或 base64(hex32)。"""
    if not aes_key_b64:
        raise MediaFetchError("aes_key 为空")
    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        text = decoded.decode("ascii", errors="ignore")
        if all(ch in "0123456789abcdefABCDEF" for ch in text):
            return bytes.fromhex(text)
    return decoded


def decrypt_aes128_ecb(ciphertext: bytes, aes_key_b64: str) -> bytes:
    from Crypto.Cipher import AES  # pycryptodome，可选依赖

    key = _parse_aes_key(aes_key_b64)
    return _pkcs7_unpad(AES.new(key, AES.MODE_ECB).decrypt(ciphertext))


# 允许下载的微信媒体域名（防 SSRF）：策略唯一来源是 urlpolicy，初始 URL
# 与每一跳重定向都要命中（审计 #6）。旧名保留为别名兼容既有引用。
_ALLOWED_URL_HOSTS = ALLOWED_MEDIA_HOSTS
_is_allowed_media_url = is_allowed_media_url


def _download_url(ref: MediaRef) -> str:
    if ref.encrypt_query_param:
        return (
            f"{CDN_BASE_URL.rstrip('/')}/download?"
            f"encrypted_query_param={quote(ref.encrypt_query_param, safe='')}"
        )
    if ref.url:
        if not _is_allowed_media_url(ref.url):
            raise MediaFetchError("媒体下载地址不是微信 CDN 域名，已拒绝（防 SSRF）")
        return ref.url
    raise MediaFetchError("媒体引用没有下载地址")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HttpMediaFetcher:
    """真实下载 Adapter；可选依赖缺失/超限/白名单不通过均明确失败。"""

    def __init__(self, transport: IlinkTransport) -> None:
        self.transport = transport

    async def fetch(
        self, ref: MediaRef, dest_dir: Path, *, max_bytes: int = MAX_MEDIA_BYTES
    ) -> FetchedMedia:
        safe_name = Path(ref.file_name or "").name
        suffix = Path(safe_name).suffix.lower()
        allowed = ALLOWED_IMAGE_EXTENSIONS if ref.kind == "image" else ALLOWED_FILE_EXTENSIONS
        if suffix and suffix not in allowed:
            raise MediaFetchError(f"不接收的文件类型: {suffix}")
        if ref.size and ref.size > max_bytes:
            raise MediaFetchError(f"媒体超过上限: {ref.size} > {max_bytes}")
        if not safe_name:
            safe_name = f"{ref.kind}_{uuid.uuid4().hex[:12]}{suffix}"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{uuid.uuid4().hex[:12]}_{safe_name}"
        try:
            size = await self.transport.download_to(
                _download_url(ref), dest, max_bytes=max_bytes,
                allowed_hosts=ALLOWED_MEDIA_HOSTS,
            )
        except TransportError as exc:
            raise MediaFetchError(str(exc)) from exc

        if ref.aes_key:
            try:
                plaintext = decrypt_aes128_ecb(dest.read_bytes(), ref.aes_key)
            except Exception as exc:  # noqa: BLE001  解密失败不落半成品
                dest.unlink(missing_ok=True)
                raise MediaFetchError(f"AES 解密失败: {exc}") from exc
            if len(plaintext) > max_bytes:
                dest.unlink(missing_ok=True)
                raise MediaFetchError("解密后媒体超过上限")
            dest.write_bytes(plaintext)
            size = len(plaintext)

        digest = _sha256_file(dest)
        mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        return FetchedMedia(path=dest, size=size, sha256=digest, mime=mime, file_name=safe_name)
