"""微信纯文本渲染与按目标分块。"""
from __future__ import annotations

from backend.modules.delivery.api import EMAIL_CHUNK_CHARS, WECHAT_CHUNK_CHARS, DeliveryService
from backend.modules.delivery.contracts import DEFAULT_CHUNK_CHARS, DeliveryTarget
from backend.shared.wechat_text import to_wechat_text
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock, make_rig


def test_markdown_is_degraded_to_plain_text() -> None:
    source = "# 标题\n\n**重点** 和 `code`\n\n```python\nprint(1)\n```\n\n- 一\n- 二"
    rendered = to_wechat_text(source)
    assert "#" not in rendered
    assert "**" not in rendered
    assert "```" not in rendered
    assert "重点" in rendered and "code" in rendered
    assert "• 一" in rendered


def test_default_chunk_constant_unchanged() -> None:
    assert DEFAULT_CHUNK_CHARS == 1800
    assert WECHAT_CHUNK_CHARS == 500
    assert EMAIL_CHUNK_CHARS == 1800


async def test_wechat_uses_500_and_email_1800(tmp_path) -> None:
    rig = make_rig(tmp_path, clock=FakeClock(1000.0), seed_access=True)
    sender = FakeSender()
    service = DeliveryService(rig.db, sender=sender, clock=rig.clock)
    owner = rig.seed_user()
    text = "x" * 700
    wx_id = service.enqueue_text(
        owner_id=owner.user_id, target=DeliveryTarget(kind="wechat", ref="u"),
        text=text, dedup_key="wx",
    )
    assert await service.process_next() is True
    wx_parts = service.repo.parts(wx_id)
    assert len(wx_parts) >= 2
    assert all(len(part["content"]) <= 500 for part in wx_parts)

    mail_id = service.enqueue_text(
        owner_id=owner.user_id, target=DeliveryTarget(kind="email", ref="a@b.com"),
        text=text, dedup_key="mail",
    )
    assert await service.process_next() is True
    assert len(service.repo.parts(mail_id)) == 1
    await rig.aclose()
