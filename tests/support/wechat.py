"""Task 7 测试替身：FakeTransport/FakeMediaFetcher + 渠道消息构造器。

只替换外部网络 Seam（iLink HTTP / CDN），不模拟本地 SQL 与去重规则。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.modules.channels.contracts import MAX_MEDIA_BYTES, MediaRef
from backend.modules.channels.wechat.account import TransportError
from backend.modules.channels.wechat.media import FetchedMedia
from tests.support.rig import TestRig, make_rig


class FakeTransport:
    """按脚本回放 getupdates/QR 响应，记录发出的消息。"""

    def __init__(self) -> None:
        self.updates: list[Any] = []
        self.qr_start: list[dict[str, Any]] = []
        self.qr_status: list[dict[str, Any]] = []
        self.posts: list[dict[str, Any]] = []
        self.sent: list[str] = []
        self.downloads: dict[str, bytes] = {}
        self.download_calls: list[str] = []
        self.closed = False

    def script_updates(self, *responses: Any) -> None:
        self.updates.extend(responses)

    def script_qr(self, start: dict[str, Any], *statuses: dict[str, Any]) -> None:
        self.qr_start.append(start)
        self.qr_status.extend(statuses)

    async def get_json(self, url: str, *, timeout: float = 15.0) -> dict[str, Any]:
        if "get_bot_qrcode" in url:
            if not self.qr_start:
                raise TransportError("没有预置二维码响应")
            return self.qr_start.pop(0)
        if "get_qrcode_status" in url:
            if not self.qr_status:
                raise TransportError("没有预置扫码状态")
            return self.qr_status.pop(0)
        raise TransportError(f"未预置 GET: {url}")

    async def post_json(
        self, url: str, payload: dict[str, Any], *, token: str = "", timeout: float = 15.0
    ) -> dict[str, Any]:
        self.posts.append({"url": url, "payload": payload, "token": token})
        if url.endswith("/ilink/bot/getupdates"):
            if not self.updates:
                return {"ret": 0, "errcode": 0, "msgs": [], "get_updates_buf": ""}
            item = self.updates.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if url.endswith("/ilink/bot/sendmessage"):
            text = payload["msg"]["item_list"][0]["text_item"]["text"]
            self.sent.append(text)
            return {"ret": 0}
        return {"ret": 0}

    async def download_to(
        self, url: str, dest_path: Path, *, max_bytes: int, timeout: float = 60.0,
        allowed_hosts=None,
    ) -> int:
        self.download_calls.append(url)
        data = self.downloads.get(url)
        if data is None:
            raise TransportError(f"没有预置下载内容: {url}")
        if len(data) > max_bytes:
            raise TransportError("下载超过上限")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(data)
        return len(data)

    async def aclose(self) -> None:
        self.closed = True


class FakeMediaFetcher:
    """把媒体引用写成固定小文件（默认按声明扩展名），验证引用→附件链路。"""

    def __init__(self, payload: bytes = b"\x89PNG\r\n\x1a\nfake-image") -> None:
        self.payload = payload
        self.calls: list[MediaRef] = []
        self.fail_next = False

    async def fetch(
        self, ref: MediaRef, dest_dir: Path, *, max_bytes: int = MAX_MEDIA_BYTES
    ) -> FetchedMedia:
        self.calls.append(ref)
        if self.fail_next:
            from backend.modules.channels.wechat.media import MediaFetchError

            raise MediaFetchError("测试注入的下载失败")
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = Path(ref.file_name or "").name or f"{ref.kind}.png"
        path = dest_dir / f"{len(self.calls)}_{name}"
        path.write_bytes(self.payload)
        return FetchedMedia(
            path=path,
            size=len(self.payload),
            sha256=hashlib.sha256(self.payload).hexdigest(),
            mime="image/png",
            file_name=name,
        )


def make_channel_rig(tmp_path: Path, *, clock=None, media_fetcher: bool = True):
    """独立渠道测试环境：真实临时 SQLite + FakeRuntime + FakeTransport。

    同时装配 files（增量 F3）：渠道媒体保存走统一文件权威。
    """
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    rig.attach_assistant()
    rig.attach_files()
    transport = FakeTransport()
    fetcher = FakeMediaFetcher() if media_fetcher else None
    rig.attach_channels(
        transport=transport, media_fetcher=fetcher, media_dir=tmp_path / "media",
    )
    return rig, transport, fetcher


def text_message(
    text: str,
    *,
    message_id: str = "",
    from_user: str = "wx_ext_1",
    chat_id: str = "",
    context_token: str = "ctx-1",
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "from_user_id": from_user,
        "item_list": [{"type": 1, "text_item": {"text": text}}],
        "context_token": context_token,
    }
    if message_id:
        msg["message_id"] = message_id
    if chat_id:
        msg["chat_id"] = chat_id
    return msg


def image_message(
    *,
    url: str = "https://cdn.example/a.png",
    file_name: str = "a.png",
    aes_key: str = "",
    message_id: str = "",
    from_user: str = "wx_ext_1",
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "from_user_id": from_user,
        "item_list": [
            {
                "type": 2,
                "image_item": {"url": url, "file_name": file_name, "aeskey": aes_key},
            }
        ],
    }
    if message_id:
        msg["message_id"] = message_id
    return msg


def inbound(rig: TestRig, account, msg: dict[str, Any], *, now: float | None = None):
    from backend.modules.channels.wechat.parser import parse_inbound

    return parse_inbound(account, msg, now=rig.clock() if now is None else now)
