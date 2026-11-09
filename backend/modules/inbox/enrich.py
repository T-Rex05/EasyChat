"""链接富化：只抓 http/https 公网页面；拒绝内网/环回/元数据地址与重定向绕过。"""
from __future__ import annotations

import ipaddress
import socket
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


class UnsafeUrl(ValueError):
    pass


def _default_resolver(host: str):
    return socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)


def is_public_url(url: str, resolver=_default_resolver) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if parts.port not in (None, 80, 443):
        return False
    host = parts.hostname.strip("[]").lower()
    if host in ("localhost", "metadata.google.internal") or host.endswith(".local"):
        return False
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return literal.is_global
    try:
        infos = resolver(host)
    except OSError:
        return False
    addresses = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except (IndexError, ValueError):
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.in_skip = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in ("script", "style", "noscript", "svg"):
            self.in_skip += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in ("script", "style", "noscript", "svg") and self.in_skip:
            self.in_skip -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        elif not self.in_skip:
            self.text_parts.append(data)


def parse_html(content: str) -> tuple[str, str]:
    parser = _TextParser()
    try:
        parser.feed(content)
    except Exception:  # noqa: BLE001  坏 HTML 也要尽量提取
        pass
    title = " ".join("".join(parser.title_parts).split())[:200]
    text = unescape(" ".join("".join(parser.text_parts).split()))
    return title, text[:1000]


class LinkEnricher:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        resolver=_default_resolver,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.transport = transport
        self.resolver = resolver
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> tuple[str, str]:
        current = url
        with httpx.Client(
            timeout=self.timeout_seconds, transport=self.transport,
            follow_redirects=False, trust_env=False,
            headers={"User-Agent": "EasyChatInbox/1.0"},
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                if urlsplit(current).scheme.lower() != "https":
                    raise UnsafeUrl("只富化 https 链接")
                if not is_public_url(current, self.resolver):
                    raise UnsafeUrl("链接指向非公网地址")
                # 必须流式读取：普通 get() 会先把整个响应读进内存，2 MB 上限失效。
                with client.stream("GET", current) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location", "")
                        if not location:
                            raise UnsafeUrl("重定向缺少目标")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";")[0].strip()
                    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                        raise UnsafeUrl("只富化文本网页")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise UnsafeUrl("页面超过 2 MB")
                    encoding = response.encoding or "utf-8"
                    return parse_html(bytes(data).decode(encoding, errors="replace"))
        raise UnsafeUrl("重定向次数过多")
