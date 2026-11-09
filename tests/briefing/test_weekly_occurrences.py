"""周报“下周”：真实 SchedulingService + SQLite，重复计划必须展开到下一次 occurrence。"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend.modules.briefing.api import BriefingService
from backend.modules.briefing.contracts import BRIEFING_WEEKLY
from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.scheduling.api import SchedulingService
from backend.platform.jobs import JobQueue
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock, make_rig

TZ = ZoneInfo("Asia/Shanghai")
NOV5_20 = datetime(2026, 11, 5, 20, 0, tzinfo=TZ).timestamp()
NOV6_00 = datetime(2026, 11, 6, 0, 0, tzinfo=TZ).timestamp()


class FakeProfiles:
    def timezone_for(self, owner_id):
        return "Asia/Shanghai"

    def get(self, principal):
        return SimpleNamespace(mood_opt_in=0)


def _setup(tmp_path):
    clock = FakeClock(NOV5_20)
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    queue = JobQueue(rig.db, clock=clock)
    delivery = DeliveryService(rig.db, sender=FakeSender(), clock=clock)
    scheduling = SchedulingService(
        rig.db,
        delivery=delivery,
        access=rig.access,
        clock=clock,
        timezone_name="Asia/Shanghai",
        queue=queue,
    )
    briefing = BriefingService(
        access=rig.access,
        scheduling=scheduling,
        profiles=FakeProfiles(),
        clock=clock,
    )
    return rig, user, scheduling, briefing


def _target() -> DeliveryTarget:
    return DeliveryTarget(kind="wechat", ref="wx_weekly")


def _at(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, TZ)


@pytest.mark.asyncio
async def test_daily_2100_at_2000_moves_to_tomorrow_and_count_is_one(tmp_path) -> None:
    _rig, user, scheduling, briefing = _setup(tmp_path)
    schedule = scheduling.create(
        user, title="每日提醒", text="每日提醒", target=_target(), daily_at="21:00"
    )

    items = scheduling.upcoming(
        user, until=NOV6_00 + timedelta(days=7).total_seconds(),
        start=NOV6_00, content_kind="text",
    )
    assert [item.schedule_id for item in items] == [schedule.schedule_id]
    assert _at(items[0].next_run_at) == datetime(2026, 11, 6, 21, 0, tzinfo=TZ)
    # 投影只用于简报展示，不能把数据库里的 next_run_at 推走。
    assert _at(scheduling.get(user, schedule.schedule_id).next_run_at) == datetime(
        2026, 11, 5, 21, 0, tzinfo=TZ
    )

    result = await briefing.build(user.user_id, BRIEFING_WEEKLY, local_date="2026-11-05")
    assert "下周 1 条，最早 21:00：每日提醒" in result.text
    assert "下周没有排定的提醒" not in result.text


@pytest.mark.asyncio
async def test_weekly_monday_from_thursday_moves_to_next_monday(tmp_path) -> None:
    _rig, user, scheduling, briefing = _setup(tmp_path)
    schedule = scheduling.create(
        user, title="周会", text="周会", target=_target(),
        weekly_at="09:00", weekday=0,
    )

    items = scheduling.upcoming(
        user, until=NOV6_00 + timedelta(days=7).total_seconds(),
        start=NOV6_00, content_kind="text",
    )
    assert [item.schedule_id for item in items] == [schedule.schedule_id]
    assert _at(items[0].next_run_at) == datetime(2026, 11, 9, 9, 0, tzinfo=TZ)

    result = await briefing.build(user.user_id, BRIEFING_WEEKLY, local_date="2026-11-05")
    assert "下周 1 条，最早 09:00：周会" in result.text


@pytest.mark.asyncio
async def test_once_tonight_is_not_part_of_next_week(tmp_path) -> None:
    _rig, user, scheduling, briefing = _setup(tmp_path)
    scheduling.create(
        user, title="今晚一次性", text="今晚一次性", target=_target(),
        at="2026-11-05T21:00:00+08:00",
    )

    items = scheduling.upcoming(
        user, until=NOV6_00 + timedelta(days=7).total_seconds(),
        start=NOV6_00, content_kind="text",
    )
    assert items == []

    result = await briefing.build(user.user_id, BRIEFING_WEEKLY, local_date="2026-11-05")
    assert "下周没有排定的提醒" in result.text


@pytest.mark.asyncio
async def test_briefing_schedule_is_excluded_from_weekly_text(tmp_path) -> None:
    _rig, user, scheduling, briefing = _setup(tmp_path)
    scheduling.create(
        user, title="早报", text="", target=_target(), daily_at="21:00",
        content_kind="briefing", briefing_kind="morning",
    )

    items = scheduling.upcoming(
        user, until=NOV6_00 + timedelta(days=7).total_seconds(),
        start=NOV6_00, content_kind="text",
    )
    assert items == []

    result = await briefing.build(user.user_id, BRIEFING_WEEKLY, local_date="2026-11-05")
    assert "下周没有排定的提醒" in result.text


@pytest.mark.asyncio
async def test_start_equal_to_occurrence_counts_exactly_once(tmp_path) -> None:
    _rig, user, scheduling, briefing = _setup(tmp_path)
    schedule = scheduling.create(
        user, title="零点", text="零点", target=_target(), daily_at="00:00"
    )

    items = scheduling.upcoming(
        user, until=NOV6_00 + timedelta(days=7).total_seconds(),
        start=NOV6_00, content_kind="text",
    )
    assert [item.schedule_id for item in items] == [schedule.schedule_id]
    assert items[0].next_run_at == NOV6_00

    result = await briefing.build(user.user_id, BRIEFING_WEEKLY, local_date="2026-11-05")
    assert "下周 1 条，最早 00:00：零点" in result.text


def test_interval_occurrence_is_advanced_to_start(tmp_path) -> None:
    _rig, user, scheduling, _briefing = _setup(tmp_path)
    schedule = scheduling.create(
        user, title="每小时", text="每小时", target=_target(), every_seconds=3600
    )

    items = scheduling.upcoming(
        user, until=NOV6_00 + timedelta(days=7).total_seconds(),
        start=NOV6_00, content_kind="text",
    )
    assert [item.schedule_id for item in items] == [schedule.schedule_id]
    assert _at(items[0].next_run_at) == datetime(2026, 11, 6, 0, 0, tzinfo=TZ)


def test_fractional_start_does_not_include_occurrence_before_start(tmp_path) -> None:
    _rig, user, scheduling, _briefing = _setup(tmp_path)
    schedule = scheduling.create(
        user, title="零点", text="零点", target=_target(), daily_at="00:00"
    )

    items = scheduling.upcoming(
        user, until=NOV6_00 + timedelta(days=8).total_seconds(),
        start=NOV6_00 + 0.5, content_kind="text",
    )
    assert [item.schedule_id for item in items] == [schedule.schedule_id]
    assert _at(items[0].next_run_at) == datetime(2026, 11, 7, 0, 0, tzinfo=TZ)


def test_limit_is_applied_after_occurrence_expansion(tmp_path) -> None:
    _rig, user, scheduling, _briefing = _setup(tmp_path)
    for index in range(50):
        scheduling.create(
            user, title=f"晚间 {index}", text=f"晚间 {index}", target=_target(),
            daily_at="21:00",
        )
    earliest = scheduling.create(
        user, title="零点最早", text="零点最早", target=_target(), daily_at="00:00"
    )

    items = scheduling.upcoming(
        user, until=NOV6_00 + timedelta(days=7).total_seconds(),
        start=NOV6_00, content_kind="text", limit=50,
    )
    assert len(items) == 50
    assert items[0].schedule_id == earliest.schedule_id
    assert _at(items[0].next_run_at) == datetime(2026, 11, 6, 0, 0, tzinfo=TZ)
