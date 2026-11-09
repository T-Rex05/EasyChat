"""Hermes 可选搜索 Provider 的装配桥。

Hermes 的 ``ddgs`` Provider 位于 ``plugins/web/ddgs``，但该目录没有
``plugin.yaml``，因此不会被插件发现机制自动注册；只安装 ``ddgs`` 包时
``web_search`` 仍会报 "No web search provider configured"。

这里在 Hermes 环境初始化后显式注册它，把“包可用”真正接到
``web_search`` 工具上。未安装 ``ddgs`` 时保持无操作。
"""
from __future__ import annotations

import base64
import binascii
import logging
from typing import Any
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)

BING_SEARCH_URL = "https://www.bing.com/search"


def _bing_fallback_result(
    base_result: dict[str, Any], query: str, limit: int
) -> dict[str, Any]:
    if base_result.get("success"):
        return base_result
    fallback = _bing_search(query, limit)
    if fallback:
        logger.info("DDGS 搜索失败，Bing 兜底返回 %d 条: %r", len(fallback), query)
        return {"success": True, "data": {"web": fallback}}
    return base_result


def ensure_ddgs_provider() -> bool:
    """Register Hermes's bundled DDGS provider when importable.

    Returns True only when a provider is registered after the call; repeated
    calls are idempotent. Import failures are expected in stripped test
    environments and stay silent at warning level.
    """
    try:
        import importlib.util

        if importlib.util.find_spec("ddgs") is None:
            return False
        from agent import web_search_registry
        from plugins.web.ddgs.provider import DDGSWebSearchProvider
    except (ImportError, ModuleNotFoundError):
        return False
    existing = web_search_registry.get_provider("ddgs")
    if existing is not None:
        return True
    try:
        class BingFallbackProvider(DDGSWebSearchProvider):
            def search(self, query: str, limit: int = 5) -> dict[str, Any]:
                return _bing_fallback_result(super().search(query, limit), query, limit)

        web_search_registry.register_provider(BingFallbackProvider())
    except Exception:  # noqa: BLE001 注册失败不能阻塞整个应用启动
        logger.exception("注册 Hermes DDGS 搜索 Provider 失败")
        return False
    logger.info("已注册 Hermes DDGS 搜索 Provider（含 Bing 兜底）")
    return True


def _bing_search(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        import httpx
        from lxml import html
    except ImportError:
        return []
    try:
        response = httpx.get(
            BING_SEARCH_URL,
            params={"q": query},
            timeout=10.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        response.raise_for_status()
        document = html.fromstring(response.text)
    except Exception as exc:  # noqa: BLE001 搜索兜底失败保留原错误
        logger.info("Bing 搜索兜底失败: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    for node in document.xpath("//li[contains(@class,'b_algo')]"):
        links = node.xpath(".//h2/a")
        if not links:
            continue
        link = links[0]
        title = " ".join(link.text_content().split())
        href = _unwrap_bing_url(str(link.get("href") or ""))
        if not title or not href:
            continue
        paragraphs = node.xpath(".//p")
        description = (
            " ".join(paragraphs[0].text_content().split()) if paragraphs else ""
        )
        results.append(
            {
                "title": title,
                "url": href,
                "description": description,
                "position": len(results) + 1,
            }
        )
        if len(results) >= max(1, int(limit)):
            break
    return results


def _unwrap_bing_url(href: str) -> str:
    """解掉 Bing 的 ``/ck/a?u=a1...`` 跳转；失败时返回原链接。"""
    try:
        parts = urlsplit(href)
        if "bing.com" not in parts.netloc or parts.path != "/ck/a":
            return href
        encoded = parse_qs(parts.query).get("u", [""])[0]
        if not encoded.startswith("a1"):
            return href
        payload = encoded[2:]
        payload += "=" * (-len(payload) % 4)
        return base64.urlsafe_b64decode(payload).decode("utf-8", "replace")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return href

