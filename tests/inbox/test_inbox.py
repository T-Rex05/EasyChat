"""收件箱：去重更新、owner 隔离、搜索/归档、SSRF 与富化、工具身份。"""
from __future__ import annotations

import httpx
import pytest

from backend.modules.inbox.api import InboxService
from backend.modules.inbox.enrich import LinkEnricher, UnsafeUrl, is_public_url
from backend.shared.errors import NotFoundError
from backend.shared.tool_context import ToolContext, config_with
from backend.tools.business.inbox_tools import build_inbox_tools
from tests.support.rig import make_rig


def _rig(rig):
    return rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)


def _service(rig):
    ready = _rig(rig)
    rig.db, rig.access = ready.db, ready.access
    return InboxService(rig.db, access=rig.access), rig.seed_user()


def test_same_url_updates_note_and_tags(rig) -> None:
    service, user = _service(rig)
    first = service.save(user, url="https://example.com/a", note="先看", tags=["工作"])
    second = service.save(
        user, url="https://example.com/a", note="改天看", tags=["稍后"]
    )
    assert first.item_id == second.item_id
    assert second.note == "改天看"
    assert set(second.tags) == {"工作", "稍后"}
    assert len(service.list(user)) == 1


def test_daily_enrich_limit_saves_but_does_not_fetch_after_twenty(rig) -> None:
    from backend.modules.inbox.api import ENRICH_DAILY_LIMIT
    from backend.platform.jobs import JobQueue

    ready = _rig(rig)
    user = ready.seed_user()
    queue = JobQueue(ready.db, clock=ready.clock)
    service = InboxService(
        ready.db, access=ready.access, queue=queue, clock=ready.clock
    )
    items = []
    for index in range(ENRICH_DAILY_LIMIT + 1):
        items.append(service.save(
            user, url=f"https://example.com/{index}", title=f"link-{index}"
        ))
    from datetime import datetime
    from zoneinfo import ZoneInfo

    local_date = datetime.fromtimestamp(
        ready.clock(), ZoneInfo("Asia/Shanghai")
    ).date().isoformat()
    assert queue.count_for_owner(
        kind="inbox.enrich", owner_id=user.user_id,
        payload_field="date", payload_value=local_date,
    ) == ENRICH_DAILY_LIMIT
    assert items[-1].enrich_state == "skipped"
    assert service.repo.get(user.user_id, items[-1].item_id).summary == ""


def test_owner_isolation_and_not_found(rig) -> None:
    service, user = _service(rig)
    other = rig.seed_user()
    item = service.save(user, url="https://example.com/private")
    assert service.list(other) == []
    with pytest.raises(NotFoundError):
        service.archive(other, item.item_id)


def test_search_and_archive(rig) -> None:
    service, user = _service(rig)
    item = service.save(user, url="https://example.com/a", title="账单教程", tags=["账本"])
    assert service.search(user, "账本")[0].item_id == item.item_id
    archived = service.archive(user, item.item_id)
    assert archived.status == "archived"
    assert service.list(user, status="unread") == []


def test_enrich_does_not_overwrite_user_title_with_empty_page_title(rig) -> None:
    service, user = _service(rig)
    item = service.save(user, url="https://example.com/a", title="我的标题")
    enriched = service.enrich(item.item_id, lambda url: ("页面标题", "摘要"))
    assert enriched.title == "我的标题"
    assert enriched.summary == "摘要"
    assert enriched.enrich_state == "ready"


def test_search_treats_like_wildcards_as_literal(rig) -> None:
    service, user = _service(rig)
    service.save(user, url="https://example.com/percent", title="折扣 100%")
    assert service.search(user, "100%")[0].title == "折扣 100%"
    assert service.search(user, "_") == []


def test_http_link_saved_but_not_enriched(rig) -> None:
    from backend.platform.jobs import JobQueue

    ready = _rig(rig)
    user = ready.seed_user()
    queue = JobQueue(ready.db, clock=ready.clock)
    service = InboxService(
        ready.db, access=ready.access, queue=queue, clock=ready.clock
    )
    item = service.save(user, url="http://example.com/plain", title="明文链接")
    assert item.enrich_state == "skipped"
    conn = ready.db.connect()
    try:
        count = conn.execute(
            "SELECT count(*) FROM jobs WHERE kind='inbox.enrich'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 0
    called = []
    enriched = service.enrich(
        item.item_id, lambda url: called.append(url) or ("标题", "摘要")
    )
    assert enriched.enrich_state == "skipped"
    assert called == []


def test_enricher_rejects_http_before_network() -> None:
    calls = []

    def resolver(host):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="<title>不应抓取</title>")

    enricher = LinkEnricher(transport=httpx.MockTransport(handler), resolver=resolver)
    with pytest.raises(UnsafeUrl, match="https"):
        enricher.fetch("http://example.com/a")
    assert calls == []


def test_enricher_enforces_two_mib_stream_limit() -> None:
    from backend.modules.inbox.enrich import MAX_BYTES

    def resolver(host):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"x" * (MAX_BYTES + 1),
        )

    enricher = LinkEnricher(transport=httpx.MockTransport(handler), resolver=resolver)
    with pytest.raises(UnsafeUrl, match="2 MB"):
        enricher.fetch("https://example.com/big")


def test_bad_url_scheme_rejected(rig) -> None:
    service, user = _service(rig)
    with pytest.raises(Exception):
        service.save(user, url="file:///etc/passwd")


def test_url_with_embedded_credentials_rejected(rig) -> None:
    service, user = _service(rig)
    with pytest.raises(Exception):
        service.save(user, url="https://user:secret@example.com/a")


def test_ssrf_private_and_metadata_rejected() -> None:
    def private(host):
        return [(2, 1, 6, "", ("127.0.0.1", 443))]

    assert not is_public_url("http://evil.test/a", private)
    assert not is_public_url("http://169.254.169.254/latest/meta-data")
    assert not is_public_url("file:///etc/passwd")
    assert not is_public_url("http://localhost/a")


def test_enricher_follows_public_page_and_parses() -> None:
    def resolver(host):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"},
            text="<html><head><title>标题</title></head><body><p>正文摘要</p></body></html>",
        )

    enricher = LinkEnricher(
        transport=httpx.MockTransport(handler), resolver=resolver
    )
    title, summary = enricher.fetch("https://example.com/a")
    assert title == "标题"
    assert "正文摘要" in summary


def test_enricher_rejects_redirect_to_private() -> None:
    def resolver(host):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    enricher = LinkEnricher(
        transport=httpx.MockTransport(handler), resolver=resolver
    )
    with pytest.raises(UnsafeUrl):
        enricher.fetch("https://example.com/a")


@pytest.mark.asyncio
async def test_tools_go_through_tool_context(rig) -> None:
    service, user = _service(rig)
    tools = {item.name: item for item in build_inbox_tools(inbox=service)}
    context = ToolContext(principal=user, source="wechat")
    saved = await tools["inbox_save"].ainvoke(
        {"url": "https://example.com/tool"}, config=config_with(context)
    )
    assert "已存" in saved
    listed = await tools["inbox_list"].ainvoke({}, config=config_with(context))
    assert "example.com" in listed
    missing = await tools["inbox_list"].ainvoke({})
    assert "身份" in missing
