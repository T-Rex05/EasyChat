"""AI 前沿资讯：多源 RSS/Atom 抓取、确定性排序与可选中文摘要。

新闻选择不交给模型：来源、时间、去重和每源上限都是确定性规则；模型只把
已抓到的标题/摘要改写成中文一句话。模型不可用或输出不合法时，保留原始
标题与摘要，日报仍然可用。
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

MAX_FEED_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MAX_ITEMS = 10
DEFAULT_PER_SOURCE_LIMIT = 2
SUMMARY_MAX_CHARS = 90

_STRIP_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_TRACKING_QUERY = re.compile(
    r"(?:^|&)(?:utm_[^=&]+|fbclid|gclid|mc_cid|mc_eid|ref|source)=[^&]*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NewsSource:
    name: str
    url: str
    weight: int = 1


DEFAULT_SOURCES: tuple[NewsSource, ...] = (
    NewsSource("OpenAI", "https://openai.com/news/rss.xml", 3),
    NewsSource("Google DeepMind", "https://deepmind.google/blog/rss.xml", 3),
    NewsSource(
        "TechCrunch AI",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        2,
    ),
    NewsSource(
        "The Verge AI",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        2,
    ),
    NewsSource(
        "MIT Technology Review AI",
        "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        2,
    ),
    NewsSource("arXiv cs.AI", "https://export.arxiv.org/rss/cs.AI", 1),
)


@dataclass(frozen=True, slots=True)
class NewsItem:
    title: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str = ""
    weight: int = 0
    score: float = 0.0
    cn_summary: str = ""


@dataclass(frozen=True, slots=True)
class NewsDigest:
    text: str
    items: tuple[NewsItem, ...] = ()
    sources_used: tuple[str, ...] = ()
    fetched_count: int = 0
    errors: tuple[str, ...] = ()


class FeedFetcher(Protocol):
    async def fetch(self, url: str) -> str: ...


class HttpxFeedFetcher:
    """受限 HTTP 抓取：只读、超时、限制大小，不跟随非 HTTP(S)。"""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    async def fetch(self, url: str) -> str:
        import httpx

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "EasyChat-AINews/1.0 (+https://github.com/)",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            body = response.content
            if len(body) > MAX_FEED_BYTES:
                raise ValueError(f"feed too large: {len(body)} bytes")
            return body.decode(response.encoding or "utf-8", errors="replace")


class NewsService:
    def __init__(
        self,
        *,
        generator: Any = None,
        fetcher: FeedFetcher | None = None,
        sources: tuple[NewsSource, ...] | None = None,
        clock=time.time,
        max_items: int = DEFAULT_MAX_ITEMS,
        per_source_limit: int = DEFAULT_PER_SOURCE_LIMIT,
        display_timezone: str = "Asia/Shanghai",
    ) -> None:
        self.generator = generator
        self.fetcher = fetcher or HttpxFeedFetcher()
        self.sources = tuple(sources or DEFAULT_SOURCES)
        self.clock = clock
        self.max_items = max(1, int(max_items))
        self.per_source_limit = max(1, int(per_source_limit))
        self.display_timezone = display_timezone

    async def build(self, owner_id: int = 0) -> NewsDigest:
        if not self.sources:
            return NewsDigest("", errors=("没有配置新闻源",))
        results = await asyncio.gather(
            *(self._fetch_one(source) for source in self.sources),
            return_exceptions=True,
        )
        items: list[NewsItem] = []
        errors: list[str] = []
        sources_used: list[str] = []
        for source, result in zip(self.sources, results):
            if isinstance(result, Exception):
                message = f"{source.name}: {result}"
                errors.append(message)
                logger.info("AI 新闻源抓取失败 %s: %s", source.name, result)
                continue
            if not result:
                continue
            sources_used.append(source.name)
            for item in result:
                items.append(item)

        items = _dedupe(items)
        items = _rank(items, now=datetime.fromtimestamp(self.clock(), timezone.utc))
        items = _diverse_top(items, self.max_items, self.per_source_limit)
        if not items:
            return NewsDigest("", errors=tuple(errors))

        items = await self._summarize(items, owner_id=owner_id)
        text = _format(items, now=datetime.fromtimestamp(self.clock(), timezone.utc), timezone_name=self.display_timezone)
        return NewsDigest(
            text=text,
            items=tuple(items),
            sources_used=tuple(dict.fromkeys(sources_used)),
            fetched_count=len(items),
            errors=tuple(errors),
        )

    async def _fetch_one(self, source: NewsSource) -> list[NewsItem]:
        raw = await self.fetcher.fetch(source.url)
        return parse_feed(raw, source=source)

    async def _summarize(self, items: list[NewsItem], *, owner_id: int) -> list[NewsItem]:
        if self.generator is None or not items:
            return items
        payload = [
            {
                "title": item.title,
                "source": item.source,
                "snippet": item.summary[:220],
            }
            for item in items
        ]
        system = (
            "你是 AI 资讯编辑。只根据用户给出的标题和摘要，为每条资讯写一句中文摘要。"
            "不得补充事实、数字、评价或预测；保留模型名、公司名等专有名词；"
            "每条不超过 50 个汉字。只输出 JSON 字符串数组，长度与输入条数相同。"
        )
        user = json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            raw = await self.generator.generate(
                system, user, owner_id=owner_id, max_chars=1200
            )
        except Exception:  # noqa: BLE001 摘要失败不影响原始日报
            logger.exception("AI 新闻摘要生成失败，回退原始标题")
            return items
        summaries = _parse_summaries(raw, expected=len(items))
        if not summaries:
            return items
        return [
            NewsItem(
                title=item.title,
                url=item.url,
                source=item.source,
                published_at=item.published_at,
                summary=item.summary,
                weight=item.weight,
                score=item.score,
                cn_summary=_clean_summary(summaries[index]),
            )
            for index, item in enumerate(items)
        ]


def parse_feed(raw: str, *, source: NewsSource) -> list[NewsItem]:
    """解析 RSS 2.0 / Atom；单条坏节点跳过，整份坏 XML 抛 ValueError。"""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"非法 XML: {exc}") from exc

    nodes = [node for node in root.iter() if _local(node.tag) in ("item", "entry")]
    items: list[NewsItem] = []
    for node in nodes:
        title = _text(_child(node, "title"))
        link = _link(node)
        if not title or not link:
            continue
        summary = _text(_first_child(node, ("description", "summary", "content")))
        published = _parse_date(
            _text(_child(node, "pubDate"))
            or _text(_child(node, "published"))
            or _text(_child(node, "updated"))
        )
        items.append(
            NewsItem(
                title=title[:200],
                url=link,
                source=source.name,
                published_at=published,
                summary=summary[:240],
                weight=source.weight,
            )
        )
    return items


def _local(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1].lower()


def _child(node: ET.Element, name: str) -> ET.Element | None:
    wanted = name.lower()
    for child in node:
        if _local(child.tag) == wanted:
            return child
    return None


def _first_child(node: ET.Element, names: tuple[str, ...]) -> ET.Element | None:
    for name in names:
        child = _child(node, name)
        if child is not None:
            return child
    return None


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return _clean_text("".join(node.itertext()))


def _clean_text(value: str) -> str:
    value = _STRIP_TAGS.sub(" ", value or "")
    value = html.unescape(value)
    return _SPACES.sub(" ", value).strip()


def _link(node: ET.Element) -> str:
    link = _child(node, "link")
    if link is not None:
        href = str(link.get("href") or "").strip()
        if href:
            return _normalize_url(href)
        text = _clean_text("".join(link.itertext()))
        if text:
            return _normalize_url(text)
    # Atom 的 link 常带 rel/type 属性；取第一个 http(s) link 也可接受。
    for child in node:
        if _local(child.tag) != "link":
            continue
        href = str(child.get("href") or "").strip()
        if href:
            return _normalize_url(href)
    return ""


def _parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query = _TRACKING_QUERY.sub("", parts.query).strip("&")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[NewsItem] = []
    for item in items:
        url_key = _normalize_url(item.url)
        title_key = _SPACES.sub("", item.title).lower()
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        result.append(item)
    return result


def _rank(items: list[NewsItem], *, now: datetime) -> list[NewsItem]:
    def score(item: NewsItem) -> float:
        freshness = 0.0
        if item.published_at is not None:
            age_hours = max(0.0, (now - item.published_at).total_seconds() / 3600.0)
            freshness = max(0.0, 1.0 - age_hours / 72.0) * 100.0
        return freshness + item.weight * 5.0

    return sorted(
        (
            NewsItem(
                title=item.title, url=item.url, source=item.source,
                published_at=item.published_at, summary=item.summary,
                weight=item.weight, score=score(item),
            )
            for item in items
        ),
        key=lambda item: (
            item.score,
            item.published_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )


def _diverse_top(items: list[NewsItem], limit: int, per_source: int) -> list[NewsItem]:
    counts: dict[str, int] = {}
    chosen: list[NewsItem] = []
    for item in items:
        if counts.get(item.source, 0) >= per_source:
            continue
        counts[item.source] = counts.get(item.source, 0) + 1
        chosen.append(item)
        if len(chosen) >= limit:
            break
    return chosen


def _parse_summaries(raw: str, *, expected: int) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    candidates: list[Any] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            candidates = parsed
        elif isinstance(parsed, dict):
            value = parsed.get("summaries") or parsed.get("items")
            if isinstance(value, list):
                candidates = value
    except json.JSONDecodeError:
        lines = [line for line in text.splitlines() if line.strip()]
        if not all(re.match(r"^\s*(?:\d+[.、)]|[-*])\s+", line) for line in lines):
            return []
        candidates = [
            re.sub(r"^\s*(?:\d+[.、)]|[-*])\s*", "", line).strip()
            for line in lines
        ]
    if len(candidates) != expected:
        return []
    return [str(value).strip() for value in candidates]


def _clean_summary(value: str) -> str:
    value = _SPACES.sub(" ", _STRIP_TAGS.sub("", str(value or ""))).strip()
    return value[:SUMMARY_MAX_CHARS]


def _format(items: list[NewsItem], *, now: datetime, timezone_name: str) -> str:
    try:
        display_tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        display_tz = timezone.utc
    local_now = now.astimezone(display_tz)
    lines = [f"AI 前沿 · {local_now.strftime('%m-%d')}", ""]
    for index, item in enumerate(items, start=1):
        summary = item.cn_summary or _clip(item.summary, 120)
        lines.append(f"{index}. {item.title}")
        meta = item.source
        if item.published_at is not None:
            meta += f" · {item.published_at.astimezone(display_tz).strftime('%m-%d')}"
        if summary:
            lines.append(f"   {summary}")
        lines.append(f"   {meta}  {item.url}")
        lines.append("")
    lines.append(f"共 {len(items)} 条，按新鲜度与来源权重排序。")
    return "\n".join(lines).strip()


def _clip(value: str, limit: int) -> str:
    value = (value or "").strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"
