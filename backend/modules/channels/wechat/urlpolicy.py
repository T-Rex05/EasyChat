"""微信媒体下载的出网白名单（防 SSRF，审计 #6）。

初始 URL 与每一跳重定向目标都必须命中微信 CDN 域名；下载器与 HTTP
传输层共用本模块，避免两处策略漂移。
"""
from __future__ import annotations

from urllib.parse import urlsplit

ALLOWED_MEDIA_HOSTS: tuple[str, ...] = ("weixin.qq.com", "wechat.com", "qpic.cn")

# 重定向手动追逐的上限（与浏览器/aiohttp 默认一致）
MAX_REDIRECT_HOPS = 10


def is_allowed_media_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_MEDIA_HOSTS)
