"""简报：模板事实、数字护栏、情绪跳过/care、安静时段延迟。"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend.modules.briefing.api import BriefingService
from backend.modules.briefing.contracts import (
    BRIEFING_EVENING,
    BRIEFING_MOOD_WEEKLY,
    BRIEFING_MORNING,
    BRIEFING_WEEKLY,
)
from backend.modules.briefing.worker import BriefingWorker
from backend.modules.delivery.contracts import DeliveryTarget
from tests.support.rig import make_rig


def _ready(rig):
    if rig.access is None:
        rig = make_rig(rig.tmp_path, seed_access=True)
    return rig


class FakeScheduling:
    def __init__(self, items, delivered=0):
        self.items = items
        self.delivered = delivered
        self.ranges = []
        self.content_kinds: list[str] = []
        self.starts: list[float | None] = []

    def upcoming(self, principal, until, limit=50, content_kind="", start=None):
        self.content_kinds.append(content_kind)
        self.starts.append(start)
        items = list(self.items)
        if content_kind:
            items = [item for item in items if item.content_kind == content_kind]
        if start is not None:
            items = [item for item in items if item.next_run_at >= start]
        if until is not None:
            items = [item for item in items if item.next_run_at <= until]
        return items[:limit]

    def delivered_between(self, principal, start, end):
        self.ranges.append((start, end))
        return self.delivered


class FakeProfiles:
    def __init__(self, *, mood=False, week=None, quiet=None):
        self.mood = mood
        self.week = week or SimpleNamespace(
            sufficient=False, average=0, days=(), label_counts=(), low_days=0,
            missing_days=7, consecutive_low_days=0,
        )
        self.quiet = quiet or SimpleNamespace(active=False, end_epoch=0)

    def timezone_for(self, owner_id):
        return "Asia/Shanghai"

    def get(self, principal):
        return SimpleNamespace(mood_opt_in=1 if self.mood else 0)

    def weekly_mood_for_owner(self, owner_id, today=None):
        return self.week

    def quiet_window(self, owner_id, now=None):
        return self.quiet


class FakeGenerator:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    async def generate(self, system, user, *, owner_id=0, max_chars=300):
        self.calls += 1
        return self.text


def _service(rig, *, items=(), delivered=0, profiles=None, generator=None):
    rig = _ready(rig)
    user = rig.seed_user()
    return (
        BriefingService(
            access=rig.access, scheduling=FakeScheduling(items, delivered),
            profiles=profiles or FakeProfiles(),
            generator=generator, clock=lambda: 1762300800.0,  # 2026-11-05 08:00 +08
        ),
        user,
    )


def _item(hour, minute, text, *, day=5, content_kind="text"):
    return SimpleNamespace(
        next_run_at=datetime(
            2026, 11, day, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai")
        ).timestamp(),
        text=text, title=text, content_kind=content_kind,
    )


@pytest.mark.asyncio
async def test_morning_uses_exact_times_and_counts(rig) -> None:
    service, user = _service(rig, items=(_item(9, 0, "交周报"), _item(14, 30, "开会")))
    result = await service.build(user.user_id, BRIEFING_MORNING, local_date="2026-11-05")
    assert result.text
    assert "09:00 交周报" in result.text
    assert "14:30 开会" in result.text
    assert "11 月 5 日" in result.text


@pytest.mark.asyncio
async def test_evening_delivered_and_tomorrow(rig) -> None:
    service, user = _service(
        rig, items=(_item(9, 0, "交周报", day=6),), delivered=3
    )
    result = await service.build(user.user_id, BRIEFING_EVENING, local_date="2026-11-05")
    assert "已送达 3 条" in result.text
    assert "明天最早 09:00：交周报" in result.text


@pytest.mark.asyncio
async def test_weekly_summary(rig) -> None:
    service, user = _service(rig, items=(_item(9, 0, "交周报"),), delivered=5)
    result = await service.build(user.user_id, BRIEFING_WEEKLY, local_date="2026-11-01")
    assert "本周回顾" in result.text
    assert "已送达 5 条" in result.text
    assert "下周 1 条" in result.text
    # 统计的是截止当天的过去 7 天，不是未来一周。
    assert service.scheduling.ranges == [
        ("2026-10-26T00:00:00+08:00", "2026-11-02T00:00:00+08:00"),
    ]


@pytest.mark.asyncio
async def test_weekly_next_week_starts_tomorrow_and_excludes_today(rig) -> None:
    items = (
        _item(21, 0, "今晚跑步"),
        _item(9, 0, "明天交周报", day=6),
        _item(20, 30, "周报-不应出现", content_kind="briefing"),
    )
    service, user = _service(rig, items=items, delivered=1)
    result = await service.build(user.user_id, BRIEFING_WEEKLY, local_date="2026-11-05")
    assert "21:00" not in result.text
    assert "今晚跑步" not in result.text
    assert "09:00：明天交周报" in result.text
    assert "下周 1 条" in result.text
    assert "周报-不应出现" not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [BRIEFING_MORNING, BRIEFING_EVENING, BRIEFING_WEEKLY])
async def test_briefing_filters_out_briefing_entries_and_itself(rig, kind) -> None:
    day = 5 if kind == BRIEFING_MORNING else 6
    items = (
        _item(9, 0, "提醒-牙医", day=day),
        _item(20, 0, "简报-不应出现", day=day, content_kind="briefing"),
        _item(20, 30, "周报-不应出现", day=day, content_kind="briefing"),
    )
    service, user = _service(rig, items=items)
    result = await service.build(user.user_id, kind, local_date="2026-11-05")
    assert "提醒-牙医" in result.text
    assert "简报-不应出现" not in result.text
    assert "周报-不应出现" not in result.text
    assert service.scheduling.content_kinds and all(
        value == "text" for value in service.scheduling.content_kinds
    )


@pytest.mark.asyncio
async def test_model_invented_number_falls_back_to_template(rig) -> None:
    bad = FakeGenerator("今天有 99 条提醒，09:00 交周报")
    service, user = _service(rig, items=(_item(9, 0, "交周报"),), generator=bad)
    result = await service.build(user.user_id, BRIEFING_MORNING, local_date="2026-11-05")
    assert bad.calls == 1
    assert "99" not in result.text
    assert "09:00 交周报" in result.text


@pytest.mark.asyncio
async def test_model_allowed_output_used(rig) -> None:
    good = FakeGenerator("早上好。09:00 交周报；今天 1 条提醒。")
    service, user = _service(rig, items=(_item(9, 0, "交周报"),), generator=good)
    result = await service.build(user.user_id, BRIEFING_MORNING, local_date="2026-11-05")
    assert result.text.startswith("早上好")


@pytest.mark.asyncio
async def test_mood_care_is_not_triggered_by_always_true_average(rig) -> None:
    normal = SimpleNamespace(
        sufficient=True, average=2.0, days=(object(),) * 7, label_counts=(("开心", 7),),
        low_days=0, missing_days=0, consecutive_low_days=0,
    )
    service, user = _service(rig, profiles=FakeProfiles(mood=True, week=normal))
    result = await service.build(
        user.user_id, BRIEFING_MOOD_WEEKLY, local_date="2026-11-01"
    )
    assert "这几周有些天" not in result.text

    low = SimpleNamespace(
        sufficient=True, average=2.0, days=(object(),) * 7, label_counts=(("加班", 3),),
        low_days=3, missing_days=0, consecutive_low_days=3,
    )
    service, user = _service(rig, profiles=FakeProfiles(mood=True, week=low))
    result = await service.build(
        user.user_id, BRIEFING_MOOD_WEEKLY, local_date="2026-11-01"
    )
    assert "这几周有些天" in result.text


@pytest.mark.asyncio
async def test_mood_insufficient_skips_even_with_generator(rig) -> None:
    generator = FakeGenerator("编点情绪")
    service, user = _service(
        rig, profiles=FakeProfiles(mood=True), generator=generator
    )
    result = await service.build(user.user_id, BRIEFING_MOOD_WEEKLY, local_date="2026-11-01")
    assert result.text == ""
    assert result.skipped_reason == "mood_insufficient"
    assert generator.calls == 0


@pytest.mark.asyncio
async def test_mood_care_copy_has_no_diagnosis(rig) -> None:
    week = SimpleNamespace(
        sufficient=True, average=1.5, days=(object(),) * 5,
        label_counts=(("低落", 4),),
        low_days=4, missing_days=2, consecutive_low_days=3,
    )
    service, user = _service(rig, profiles=FakeProfiles(mood=True, week=week))
    result = await service.build(user.user_id, BRIEFING_MOOD_WEEKLY, local_date="2026-11-01")
    assert "不太轻松" in result.text
    assert "抑郁" not in result.text and "诊断" not in result.text
    assert "/情绪 关闭" in result.text


def test_worker_delays_in_quiet_hours_and_dedups(rig) -> None:
    rig = _ready(rig)
    user = rig.seed_user()
    captured = {}

    class FakeDelivery:
        def enqueue_text(self, **kwargs):
            captured.update(kwargs)
            return "dlv_1"

    quiet = SimpleNamespace(active=True, end_epoch=1000.0)
    worker = BriefingWorker(
        service=object(), queue=object(), delivery=FakeDelivery(),
        access=rig.access, channels=object(), profiles=FakeProfiles(quiet=quiet),
        clock=lambda: 400.0,
    )
    result = SimpleNamespace(text="早上好", owner_id=user.user_id, kind="morning")

    class FakeChannels:
        def delivery_target_for_owner(self, owner_id):
            from backend.modules.channels.contracts import ChannelTarget

            return ChannelTarget(kind="wechat", ref="bot@u")

    worker.channels = FakeChannels()
    import asyncio

    asyncio.run(worker._deliver(result, schedule_id="sch_1", local_date="1970-01-01"))
    assert captured["delay_seconds"] == 600.0
    assert captured["dedup_key"] == "briefing:1:morning:1970-01-01:sch_1"


def test_worker_uses_explicit_schedule_target_without_channel_binding(rig) -> None:
    rig = _ready(rig)
    user = rig.seed_user()
    captured = {}

    class FakeDelivery:
        def enqueue_text(self, **kwargs):
            captured.update(kwargs)
            return "dlv_email"

    class NoBindingChannels:
        def delivery_target_for_owner(self, owner_id):
            return None

    worker = BriefingWorker(
        service=object(), queue=object(), delivery=FakeDelivery(),
        access=rig.access, channels=NoBindingChannels(),
        profiles=FakeProfiles(), clock=lambda: 400.0,
    )
    result = SimpleNamespace(text="AI 前沿日报", owner_id=user.user_id, kind="ai_news")
    import asyncio

    asyncio.run(
        worker._deliver(
            result,
            schedule_id="sch_ai",
            local_date="2026-11-05",
            target=DeliveryTarget(kind="email", ref="reader@example.com"),
        )
    )
    assert captured["target"].kind == "email"
    assert captured["target"].ref == "reader@example.com"
    assert captured["text"] == "AI 前沿日报"


def test_worker_rebuilds_next_day_copy_when_quiet_delay_crosses_midnight(rig) -> None:
    rig = _ready(rig)
    user = rig.seed_user()
    captured = {}
    built_dates = []

    class FakeDelivery:
        def enqueue_text(self, **kwargs):
            captured.update(kwargs)
            return "dlv_2"

    class FakeChannels:
        def delivery_target_for_owner(self, owner_id):
            from backend.modules.channels.contracts import ChannelTarget

            return ChannelTarget(kind="wechat", ref="bot@u")

    class FakeService:
        async def build(self, owner_id, kind, *, local_date=""):
            built_dates.append(local_date)
            return SimpleNamespace(
                text=f"{local_date} 早上好", owner_id=owner_id, kind=kind
            )

    quiet_end = datetime(2026, 11, 6, 7, 30, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
    quiet = SimpleNamespace(active=True, end_epoch=quiet_end)
    worker = BriefingWorker(
        service=FakeService(), queue=object(), delivery=FakeDelivery(),
        access=rig.access, channels=FakeChannels(),
        profiles=FakeProfiles(quiet=quiet),
        clock=lambda: datetime(
            2026, 11, 5, 23, 50, tzinfo=ZoneInfo("Asia/Shanghai")
        ).timestamp(),
    )
    result = SimpleNamespace(text="2026-11-05 晚上好", owner_id=user.user_id, kind="evening")
    import asyncio

    asyncio.run(worker._deliver(result, schedule_id="sch_2", local_date="2026-11-05"))
    assert built_dates == ["2026-11-06"]
    assert captured["text"] == "2026-11-06 早上好"
    assert captured["delay_seconds"] == pytest.approx(7 * 3600 + 40 * 60)
