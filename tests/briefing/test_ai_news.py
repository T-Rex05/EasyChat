"""AI 前沿日报：源抓取、去重排序、LLM 摘要回退与简报接线。"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.integrations.news import NewsItem, NewsService, NewsSource
from backend.modules.briefing.api import BriefingService
from backend.modules.briefing.contracts import BRIEFING_AI_NEWS
from tests.support.rig import make_rig


def _rss(items: list[tuple[str, str, str]]) -> str:
    rows = "".join(
        f"<item><title>{title}</title><link>{url}</link>"
        f"<description>{summary}</description>"
        f"<pubDate>{published}</pubDate></item>"
        for title, url, summary, published in items
    )
    return f"""<?xml version="1.0"?><rss version="2.0"><channel>
    <title>test</title><link>https://example.com</link>{rows}</channel></rss>"""


def _atom(items: list[tuple[str, str, str]]) -> str:
    rows = "".join(
        f"<entry><title>{title}</title><link href=\"{url}\"/>"
        f"<summary>{summary}</summary><updated>{published}</updated></entry>"
        for title, url, summary, published in items
    )
    return f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
    <title>test</title>{rows}</feed>"""


class FakeFetcher:
    def __init__(self, documents: dict[str, str], errors: set[str] | None = None):
        self.documents = documents
        self.errors = errors or set()
        self.urls: list[str] = []

    async def fetch(self, url: str) -> str:
        self.urls.append(url)
        if url in self.errors:
            raise RuntimeError(f"feed unavailable: {url}")
        return self.documents[url]


class FakeGenerator:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0
        self.users: list[str] = []

    async def generate(self, system, user, *, owner_id=0, max_chars=300):
        self.calls += 1
        self.users.append(user)
        return self.text


def _service(*, fetcher, generator=None, sources):
    return NewsService(
        fetcher=fetcher,
        generator=generator,
        sources=sources,
        clock=lambda: 1793865600.0,  # 2026-11-05 08:00 +08
        max_items=10,
        per_source_limit=2,
    )


@pytest.mark.asyncio
async def test_rss_and_atom_are_parsed_and_ranked_fresh_first() -> None:
    sources = (
        NewsSource("官方", "https://a.example/feed", weight=3),
        NewsSource("媒体", "https://b.example/feed", weight=2),
    )
    fetcher = FakeFetcher({
        sources[0].url: _rss([
            ("旧官方消息", "https://a.example/old", "old", "Mon, 02 Nov 2026 00:00:00 GMT"),
            ("新官方消息", "https://a.example/new", "new", "Thu, 05 Nov 2026 00:00:00 GMT"),
        ]),
        sources[1].url: _atom([
            ("媒体消息", "https://b.example/one", "media", "2026-11-04T00:00:00Z"),
        ]),
    })
    digest = await _service(fetcher=fetcher, sources=sources).build()
    assert [item.title for item in digest.items][:3] == [
        "新官方消息", "媒体消息", "旧官方消息",
    ]
    assert digest.items[0].url == "https://a.example/new"


@pytest.mark.asyncio
async def test_duplicate_urls_and_titles_are_removed() -> None:
    sources = (NewsSource("源", "https://a.example/feed", weight=1),)
    fetcher = FakeFetcher({
        sources[0].url: _rss([
            ("同一条新闻", "https://a.example/1", "first", "Thu, 05 Nov 2026 00:00:00 GMT"),
            ("同一条新闻", "https://a.example/2", "duplicate title", "Thu, 05 Nov 2026 01:00:00 GMT"),
            ("另一条", "https://a.example/1", "duplicate url", "Thu, 05 Nov 2026 02:00:00 GMT"),
        ]),
    })
    digest = await _service(fetcher=fetcher, sources=sources).build()
    assert [item.title for item in digest.items] == ["同一条新闻"]


@pytest.mark.asyncio
async def test_source_cap_and_top_ten_keep_source_diversity() -> None:
    sources = tuple(
        NewsSource(f"源{i}", f"https://{i}.example/feed", weight=1)
        for i in range(5)
    )
    fetcher = FakeFetcher({
        source.url: _rss([
            (f"{source.name}-{n}", f"https://{source.name}.example/{n}", "body",
             f"Thu, 05 Nov 2026 0{n}:00:00 GMT")
            for n in range(5)
        ])
        for source in sources
    })
    digest = await _service(fetcher=fetcher, sources=sources).build()
    assert len(digest.items) == 10
    counts: dict[str, int] = {}
    for item in digest.items:
        counts[item.source] = counts.get(item.source, 0) + 1
    assert max(counts.values()) <= 2


@pytest.mark.asyncio
async def test_feed_failure_is_skipped_and_other_feeds_still_build() -> None:
    sources = (
        NewsSource("坏源", "https://bad.example/feed"),
        NewsSource("好源", "https://good.example/feed"),
    )
    fetcher = FakeFetcher({
        sources[1].url: _rss([
            ("可用消息", "https://good.example/1", "body", "Thu, 05 Nov 2026 00:00:00 GMT"),
        ]),
    }, errors={sources[0].url})
    digest = await _service(fetcher=fetcher, sources=sources).build()
    assert [item.title for item in digest.items] == ["可用消息"]
    assert digest.errors and "bad.example" in digest.errors[0]


@pytest.mark.asyncio
async def test_llm_batch_summary_is_applied_to_all_items() -> None:
    sources = tuple(
        NewsSource(f"源{n}", f"https://a{n}.example/feed")
        for n in range(3)
    )
    fetcher = FakeFetcher({
        source.url: _rss([
            (f"标题{n}", f"https://a{n}.example/1", "body",
             f"Thu, 05 Nov 2026 0{n}:00:00 GMT")
        ])
        for n, source in enumerate(sources)
    })
    generator = FakeGenerator(json.dumps([
        "中文摘要一", "中文摘要二", "中文摘要三",
    ], ensure_ascii=False))
    digest = await _service(fetcher=fetcher, generator=generator, sources=sources).build()
    assert generator.calls == 1
    assert [item.cn_summary for item in digest.items] == [
        "中文摘要一", "中文摘要二", "中文摘要三",
    ]
    assert "中文摘要一" in digest.text


@pytest.mark.asyncio
async def test_invalid_llm_output_falls_back_to_original_titles() -> None:
    sources = (NewsSource("源", "https://a.example/feed"),)
    fetcher = FakeFetcher({
        sources[0].url: _rss([
            ("Original title", "https://a.example/1", "short body",
             "Thu, 05 Nov 2026 00:00:00 GMT"),
        ]),
    })
    digest = await _service(
        fetcher=fetcher, generator=FakeGenerator("not-json"), sources=sources
    ).build()
    assert digest.items[0].cn_summary == ""
    assert "Original title" in digest.text


@pytest.mark.asyncio
async def test_empty_feeds_return_empty_text() -> None:
    sources = (NewsSource("空源", "https://empty.example/feed"),)
    fetcher = FakeFetcher({sources[0].url: _rss([])})
    digest = await _service(fetcher=fetcher, sources=sources).build()
    assert digest.items == ()
    assert digest.text == ""


class FakeNews:
    def __init__(self):
        self.owner_ids: list[int] = []

    async def build(self, owner_id: int):
        self.owner_ids.append(owner_id)
        return SimpleNamespace(
            text="AI 前沿\n1. 新模型发布\n2. 新论文",
            items=(NewsItem(title="新模型发布", url="https://a/1", source="源"),),
            errors=(),
        )


@pytest.mark.asyncio
async def test_briefing_ai_news_delegates_to_news_service(rig) -> None:
    if rig.access is None:
        rig = make_rig(rig.tmp_path, seed_access=True)
    user = rig.seed_user()
    news = FakeNews()
    service = BriefingService(
        access=rig.access, scheduling=SimpleNamespace(), profiles=SimpleNamespace(),
        news=news, clock=lambda: 1793865600.0,
    )
    result = await service.build(user.user_id, BRIEFING_AI_NEWS)
    assert result.text.startswith("AI 前沿")
    assert result.kind == BRIEFING_AI_NEWS
    assert news.owner_ids == [user.user_id]
