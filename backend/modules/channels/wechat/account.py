"""iLink 协议 Adapter：HTTP 传输、扫码登录、文本发送。

网络 I/O 全部通过注入的 IlinkTransport；测试用 FakeTransport，不触网。
扫码状态由每次 poll 的真实响应决定，不设假的 running 标志。
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from backend.modules.channels.contracts import (
    ChannelTransportError,
    QR_CONFIRMED,
    QR_EXPIRED,
    QR_SCANNED,
    QR_WAIT,
    QrSessionView,
)
from backend.modules.channels.wechat.urlpolicy import MAX_REDIRECT_HOPS
from backend.shared.text import split_text  # noqa: F401  渠道发送与投递共用切分规则

logger = logging.getLogger(__name__)

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"

EP_GET_UPDATES = "/ilink/bot/getupdates"
EP_SEND_MESSAGE = "/ilink/bot/sendmessage"
EP_GET_QRCODE = "/ilink/bot/get_bot_qrcode"
EP_QRCODE_STATUS = "/ilink/bot/get_qrcode_status"

DEFAULT_QR_TTL_SECONDS = 300.0
DEFAULT_QR_REFRESH_LIMIT = 3
DEFAULT_MAX_QR_SESSIONS = 32
DEFAULT_TEXT_CHUNK = 1800
CHANNEL_VERSION = "2.2.0"


class TransportError(ChannelTransportError):
    """兼容旧名；实际异常类型由 channels.contracts 统一提供。"""


def ilink_headers(token: str = "", body_len: int = 0) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
        "X-WECHAT-UIN": str(int(time.time()))[:10],
    }
    if token:
        headers["AuthorizationType"] = "ilink_bot_token"
        headers["Authorization"] = f"Bearer {token}"
    if body_len:
        headers["Content-Length"] = str(body_len)
    return headers


def _host_allowed(url: str, allowed_hosts: Sequence[str]) -> bool:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.lower()
    return any(host == item or host.endswith(f".{item}") for item in allowed_hosts)


class IlinkTransport(Protocol):
    """测试替身只需实现这三个方法；默认实现见 AiohttpTransport。"""

    async def get_json(self, url: str, *, timeout: float = 15.0) -> dict[str, Any]: ...

    async def post_json(
        self, url: str, payload: Mapping[str, Any], *, token: str = "", timeout: float = 15.0
    ) -> dict[str, Any]: ...

    async def download_to(
        self, url: str, dest_path: Path, *, max_bytes: int, timeout: float = 60.0,
        allowed_hosts: Sequence[str] | None = None,
    ) -> int: ...


class AiohttpTransport:
    """默认 HTTP 实现；aiohttp 延迟导入，import 本模块不建立连接。"""

    def __init__(self) -> None:
        self._session: Any = None

    async def _get_session(self) -> Any:
        if self._session is None:
            import aiohttp

            self._session = aiohttp.ClientSession()
        return self._session

    async def aclose(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def get_json(self, url: str, *, timeout: float = 15.0) -> dict[str, Any]:
        import aiohttp

        session = await self._get_session()
        try:
            async with session.get(url, headers=ilink_headers(), timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise TransportError(
                        f"GET {url} HTTP {resp.status}: {text[:200]}",
                        status=resp.status,
                    )
                data = json.loads(text)
                return data if isinstance(data, dict) else {}
        except TransportError:
            raise
        except Exception as exc:  # noqa: BLE001  网络/JSON 错误统一映射
            raise TransportError(f"GET {url} 失败: {exc}") from exc

    async def post_json(
        self, url: str, payload: Mapping[str, Any], *, token: str = "", timeout: float = 15.0
    ) -> dict[str, Any]:
        import aiohttp

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        session = await self._get_session()
        try:
            async with session.post(
                url, data=body, headers=ilink_headers(token, len(body)),
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise TransportError(
                        f"POST {url} HTTP {resp.status}: {text[:200]}",
                        status=resp.status,
                    )
                data = json.loads(text)
                return data if isinstance(data, dict) else {}
        except TransportError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TransportError(f"POST {url} 失败: {exc}") from exc

    async def download_to(
        self, url: str, dest_path: Path, *, max_bytes: int, timeout: float = 60.0,
        allowed_hosts: Sequence[str] | None = None,
    ) -> int:
        """流式落盘并限制最大字节，避免把大文件整体读进内存。

        审计 #6：禁用 aiohttp 隐式重定向（默认跟随最多 10 跳到任意主机）；
        给出 allowed_hosts 时逐跳校验重定向目标域名，任何不命中白名单的
        跳都立即失败且不落盘。
        """
        import aiohttp

        session = await self._get_session()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            current = url
            for _hop in range(MAX_REDIRECT_HOPS + 1):
                async with session.get(
                    current, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=False,
                ) as resp:
                    if resp.status in (301, 302, 303, 307, 308):
                        location = (resp.headers.get("Location") or "").strip()
                        if not location:
                            raise TransportError(f"下载 {current[:120]} 重定向缺少 Location")
                        from urllib.parse import urljoin

                        target = urljoin(current, location)
                        if allowed_hosts is not None and not _host_allowed(target, allowed_hosts):
                            raise TransportError("重定向目标不是微信 CDN 域名，已拒绝（防 SSRF）")
                        current = target
                        continue
                    if resp.status != 200:
                        raise TransportError(
                            f"下载 {current[:120]} HTTP {resp.status}", status=resp.status
                        )
                    with dest_path.open("wb") as fh:
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            total += len(chunk)
                            if total > max_bytes:
                                raise TransportError(f"下载超过上限 {max_bytes} bytes")
                            fh.write(chunk)
                    return total
            raise TransportError(f"下载重定向超过 {MAX_REDIRECT_HOPS} 跳")
        except TransportError:
            dest_path.unlink(missing_ok=True)
            raise
        except Exception as exc:  # noqa: BLE001
            dest_path.unlink(missing_ok=True)
            raise TransportError(f"下载失败: {exc}") from exc


# ── 扫码登录 ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _QrSession:
    id: str
    status: str
    created_at: float
    expires_at: float
    qrcode_value: str
    qr_content: str
    qr_image: str
    base_url: str
    refresh_count: int = 0
    credentials: dict[str, str] | None = None


def _render_qr_data_url(content: str) -> str:
    """可选依赖 qrcode/Pillow；任何渲染失败都返回空串，由前端展示 qr_content。"""
    if not content:
        return ""
    try:
        import qrcode  # 可选依赖
        from io import BytesIO

        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001  qrcode 存在但 Pillow 缺失/编码失败
        return ""


class QrLoginManager:
    """iLink 扫码状态机（内存有界）。status 每次由真实 poll 结果更新。"""

    def __init__(
        self,
        transport: IlinkTransport,
        *,
        clock=time.time,
        ttl: float = DEFAULT_QR_TTL_SECONDS,
        refresh_limit: int = DEFAULT_QR_REFRESH_LIMIT,
        max_sessions: int = DEFAULT_MAX_QR_SESSIONS,
        base_url: str = ILINK_BASE_URL,
    ) -> None:
        self.transport = transport
        self.clock = clock
        self.ttl = ttl
        self.refresh_limit = refresh_limit
        self.max_sessions = max_sessions
        self.base_url = base_url.rstrip("/")
        self._sessions: dict[str, _QrSession] = {}

    def _purge(self) -> None:
        now = self.clock()
        for sid in [s for s, v in self._sessions.items() if now >= v.expires_at]:
            self._sessions.pop(sid, None)
        while len(self._sessions) >= self.max_sessions:
            oldest = min(self._sessions.values(), key=lambda s: s.created_at)
            self._sessions.pop(oldest.id, None)

    async def _fetch_qr(self, base_url: str, bot_type: str = "3") -> tuple[str, str]:
        data = await self.transport.get_json(f"{base_url}{EP_GET_QRCODE}?bot_type={bot_type}")
        value = str(data.get("qrcode") or "")
        content = str(data.get("qrcode_img_content") or "") or value
        if not value:
            raise TransportError("iLink 返回空二维码")
        return value, content

    async def start(self, *, bot_type: str = "3") -> QrSessionView:
        self._purge()
        value, content = await self._fetch_qr(self.base_url, bot_type)
        now = self.clock()
        session = _QrSession(
            id=uuid.uuid4().hex[:16],
            status=QR_WAIT,
            created_at=now,
            expires_at=now + self.ttl,
            qrcode_value=value,
            qr_content=content,
            qr_image=_render_qr_data_url(content),
            base_url=self.base_url,
        )
        self._sessions[session.id] = session
        return self._view(session)

    async def poll(self, session_id: str) -> QrSessionView:
        session = self._sessions.get(session_id)
        if session is None:
            return QrSessionView(session_id=session_id, status=QR_EXPIRED)
        if self.clock() >= session.expires_at and session.status != QR_CONFIRMED:
            session.status = QR_EXPIRED
            return self._view(session)
        if session.status in (QR_CONFIRMED, QR_EXPIRED):
            return self._view(session)

        try:
            data = await self.transport.get_json(
                f"{session.base_url}{EP_QRCODE_STATUS}?qrcode={session.qrcode_value}"
            )
        except TransportError:
            # 扫码端每 1-2 秒轮询一次；iLink 偶发超时不应把整个绑定流程打成 500。
            logger.warning("二维码状态轮询失败，保留当前状态 session=%s", session.id)
            return self._view(session)
        status = str(data.get("status") or QR_WAIT)
        if status == "scaned_but_redirect":
            redirect_host = str(data.get("redirect_host") or "")
            if redirect_host:
                session.base_url = f"https://{redirect_host}"
            session.status = QR_SCANNED
        elif status == "confirmed":
            account_id = str(data.get("ilink_bot_id") or "")
            token = str(data.get("bot_token") or "")
            if account_id and token:
                session.status = QR_CONFIRMED
                session.credentials = {
                    "account_id": account_id,
                    "token": token,
                    "base_url": str(data.get("baseurl") or session.base_url or self.base_url),
                    "bot_user_id": str(data.get("ilink_user_id") or ""),
                }
            else:
                session.status = QR_EXPIRED
        elif status == "expired":
            await self._refresh(session)
        elif status in ("wait", "scaned", "scanned"):
            session.status = QR_SCANNED if status != "wait" else QR_WAIT
        else:
            session.status = QR_WAIT
        return self._view(session)

    async def _refresh(self, session: _QrSession) -> None:
        if session.refresh_count >= self.refresh_limit:
            session.status = QR_EXPIRED
            return
        session.refresh_count += 1
        try:
            value, content = await self._fetch_qr(self.base_url)
        except TransportError:
            session.status = QR_EXPIRED
            return
        session.qrcode_value = value
        session.qr_content = content
        session.qr_image = _render_qr_data_url(content)
        session.base_url = self.base_url
        session.status = QR_WAIT

    def take_credentials(self, session_id: str) -> dict[str, str] | None:
        session = self._sessions.get(session_id)
        if session is None or session.status != QR_CONFIRMED or not session.credentials:
            return None
        return dict(session.credentials)

    def discard(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _view(self, session: _QrSession) -> QrSessionView:
        return QrSessionView(
            session_id=session.id,
            status=session.status,
            qr_image=session.qr_image if session.status in (QR_WAIT, QR_SCANNED) else "",
            qr_content=session.qr_content,
            expires_at=session.expires_at,
            account_id=(session.credentials or {}).get("account_id", ""),
            base_url=(session.credentials or {}).get("base_url", session.base_url),
        )


# ── 发送 ─────────────────────────────────────────────────────────────────────


async def send_text(
    transport: IlinkTransport,
    *,
    base_url: str,
    token: str,
    to_user_id: str,
    text: str,
    context_token: str = "",
    chunk_delay: float = 1.2,
) -> int:
    """发送文本；返回成功发出的块数。失败抛 TransportError，由调用方记录。"""
    sent = 0
    for index, chunk in enumerate(split_text(text)):
        if index and chunk_delay:
            await asyncio.sleep(chunk_delay)
        message: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": uuid.uuid4().hex[:16],
            "message_type": 2,
            "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": chunk}}],
        }
        if context_token:
            message["context_token"] = context_token
        data = await transport.post_json(
            f"{base_url.rstrip('/')}{EP_SEND_MESSAGE}",
            {"msg": message, "base_info": {"channel_version": CHANNEL_VERSION}},
            token=token,
            timeout=15.0,
        )
        ret = data.get("ret", 0)
        if ret not in (0, None):
            raise TransportError(
                f"微信发送失败 ret={ret} errcode={data.get('errcode')} "
                f"errmsg={data.get('errmsg') or ''}",
                ret=int(ret) if isinstance(ret, int) else None,
            )
        sent += 1
    return sent
