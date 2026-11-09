"""scheduling weekly / briefing：时区日历、任务入队、重复 tick 幂等。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import json
import pytest

from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.scheduling.api import SchedulingService, _next_weekly
from backend.platform.jobs import JobQueue
from backend.shared.errors import InvalidInputError
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock, make_rig

TZ = ZoneInfo("Asia/Shanghai")


def _service(rig, queue=None):
    return SchedulingService(
        rig.db,
        delivery=DeliveryService(rig.db, sender=FakeSender(), clock=rig.clock),
        access=rig.access,
        clock=rig.clock,
        timezone_name="UTC",  # 故意与用户时区不同，验证参数确实生效
        queue=queue,
    )


def _epoch(y, m, d, hh, mm) -> float:
    return datetime(y, m, d, hh, mm, tzinfo=TZ).timestamp()


def test_next_weekly_uses_calendar_and_timezone() -> None:
    # 2026-11-05 周四 12:00 → 下周一 09:00
    start = _epoch(2026, 11, 5, 12, 0)
    nxt = _next_weekly(start, "09:00", 0, "Asia/Shanghai")
    assert datetime.fromtimestamp(nxt, TZ) == datetime(2026, 11, 9, 9, 0, tzinfo=TZ)
    # 周一 10:00 已过 09:00 → 下周一
    start = _epoch(2026, 11, 9, 10, 0)
    nxt = _next_weekly(start, "09:00", 0, "Asia/Shanghai")
    assert datetime.fromtimestamp(nxt, TZ) == datetime(2026, 11, 16, 9, 0, tzinfo=TZ)


def test_upcoming_can_filter_content_kind(rig) -> None:
    rig = make_rig(rig.tmp_path, clock=FakeClock(_epoch(2026, 11, 5, 12, 0)), seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig, queue=JobQueue(rig.db))
    target = DeliveryTarget(kind="wechat", ref="u")
    reminder = service.create(
        user, title="提醒", text="交周报", target=target,
        daily_at="09:00",
    )
    briefing = service.create(
        user, title="早报", text="", target=target,
        daily_at="08:00", content_kind="briefing", briefing_kind="morning",
    )
    until = _epoch(2026, 11, 12, 0, 0)
    all_items = service.upcoming(user, until)
    text_items = service.upcoming(user, until, content_kind="text")
    assert {item.schedule_id for item in all_items} == {
        reminder.schedule_id, briefing.schedule_id,
    }
    assert [item.schedule_id for item in text_items] == [reminder.schedule_id]


def test_ai_news_can_be_created_as_daily_briefing(rig) -> None:
    rig = make_rig(rig.tmp_path, clock=FakeClock(_epoch(2026, 11, 5, 12, 0)), seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig, queue=JobQueue(rig.db))
    schedule = service.create(
        user, title="AI 前沿日报", text="",
        target=DeliveryTarget(kind="wechat", ref="u"),
        daily_at="08:00", content_kind="briefing", briefing_kind="ai_news",
    )
    assert schedule.content_kind == "briefing"
    assert schedule.briefing_kind == "ai_news"
    clock = rig.clock
    clock.now = schedule.next_run_at
    created = service.tick()
    assert len(created) == 1
    lease = service.queue.claim("test-worker", kinds=("briefing.build",))
    assert lease is not None
    payload = json.loads(lease.payload)
    assert payload["kind"] == "ai_news"
    assert payload["target_kind"] == "wechat"
    assert payload["target_ref"] == "u"


def test_create_weekly_requires_weekday(rig) -> None:
    rig = make_rig(rig.tmp_path, clock=FakeClock(_epoch(2026, 11, 5, 12, 0)), seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig)
    with pytest.raises(InvalidInputError):
        service.create(
            user, title="周报", text="写周报",
            target=DeliveryTarget(kind="wechat", ref="u"),
            weekly_at="09:00", weekday=None,
        )
    with pytest.raises(InvalidInputError):
        service.create(
            user, title="周报", text="写周报",
            target=DeliveryTarget(kind="wechat", ref="u"),
            weekly_at="09:00", weekday=7,
        )


def test_cancelled_schedule_does_not_block_recreate(rig) -> None:
    rig = make_rig(rig.tmp_path, clock=FakeClock(_epoch(2026, 11, 5, 12, 0)), seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig)
    kwargs = dict(
        title="喝水", text="喝水", target=DeliveryTarget(kind="wechat", ref="u"),
        daily_at="09:00",
    )
    first = service.create(user, **kwargs)
    service.cancel(user, first.schedule_id)
    second = service.create(user, **kwargs)
    assert second.schedule_id != first.schedule_id
    assert second.enabled is True


def test_weekly_schedule_lands_on_next_monday(rig) -> None:
    rig = make_rig(rig.tmp_path, clock=FakeClock(_epoch(2026, 11, 5, 12, 0)), seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig)
    schedule = service.create(
        user, title="周报", text="写周报",
        target=DeliveryTarget(kind="wechat", ref="u"),
        weekly_at="09:00", weekday=0, timezone="Asia/Shanghai",
    )
    assert schedule.kind == "weekly"
    assert schedule.weekday == 0
    assert datetime.fromtimestamp(schedule.next_run_at, TZ) == datetime(
        2026, 11, 9, 9, 0, tzinfo=TZ
    )
    assert schedule.timezone == "Asia/Shanghai"


def test_briefing_tick_enqueues_job_once_with_occurrence_job_id(rig) -> None:
    clock = FakeClock(_epoch(2026, 11, 5, 12, 0))
    rig = make_rig(rig.tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    queue = JobQueue(rig.db, clock=clock)
    service = _service(rig, queue)
    schedule = service.create(
        user, title="早报", text="",
        target=DeliveryTarget(kind="wechat", ref="u"),
        daily_at="08:00", timezone="Asia/Shanghai",
        content_kind="briefing", briefing_kind="morning",
    )
    clock.now = schedule.next_run_at
    created = service.tick()
    assert len(created) == 1
    assert created[0].startswith("job_")
    lease = queue.claim("test-worker", kinds=("briefing.build",))
    assert lease is not None
    payload = lease.payload_json()
    assert payload["kind"] == "morning"
    assert payload["date"] == "2026-11-06"
    assert service.repo.occurrences(schedule.schedule_id)[0].job_id == created[0]

    created_again = service.tick()
    assert created_again == []
    assert service.repo.occurrences(schedule.schedule_id)[0].job_id == created[0]


def test_briefing_creation_rejected_when_worker_not_configured(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = SchedulingService(
        rig.db, delivery=DeliveryService(rig.db, sender=FakeSender(), clock=rig.clock),
        access=rig.access, clock=rig.clock, briefing_enabled=False,
    )
    with pytest.raises(InvalidInputError, match="简报功能未启用"):
        service.create(
            user, title="早报", text="",
            target=DeliveryTarget(kind="wechat", ref="u"),
            daily_at="08:00", timezone="Asia/Shanghai",
            content_kind="briefing", briefing_kind="morning",
        )


def test_changed_briefing_schedule_is_not_blocked_by_same_day_old_job(rig) -> None:
    clock = FakeClock(_epoch(2026, 11, 5, 12, 0))
    rig = make_rig(rig.tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    queue = JobQueue(rig.db, clock=clock)
    service = _service(rig, queue)
    old = service.create(
        user, title="早报", text="",
        target=DeliveryTarget(kind="wechat", ref="u"),
        daily_at="08:00", timezone="Asia/Shanghai",
        content_kind="briefing", briefing_kind="morning",
    )
    clock.now = old.next_run_at
    first = service.tick()
    assert len(first) == 1
    old_lease = queue.claim("test-worker", kinds=("briefing.build",))
    assert old_lease is not None
    queue.complete(old_lease)
    service.set_enabled(user, old.schedule_id, False)

    changed = service.create(
        user, title="早报", text="",
        target=DeliveryTarget(kind="wechat", ref="u"),
        daily_at="10:00", timezone="Asia/Shanghai",
        content_kind="briefing", briefing_kind="morning",
    )
    clock.now = changed.next_run_at
    second = service.tick()
    assert len(second) == 1 and second[0] != first[0]
    lease = queue.claim("test-worker", kinds=("briefing.build",))
    assert lease is not None
    assert lease.payload_json()["schedule_id"] == changed.schedule_id


def test_text_schedule_still_enqueues_delivery(rig) -> None:
    clock = FakeClock(_epoch(2026, 11, 5, 12, 0))
    rig = make_rig(rig.tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig)
    schedule = service.create(
        user, title="喝水", text="喝水",
        target=DeliveryTarget(kind="wechat", ref="u"),
        at="2026-11-05T13:00:00+08:00",
    )
    clock.now = schedule.next_run_at
    created = service.tick()
    assert len(created) == 1
    assert created[0].startswith("dlv_")


def test_past_or_too_far_rejected(rig) -> None:
    rig = make_rig(rig.tmp_path, clock=FakeClock(_epoch(2026, 11, 5, 12, 0)), seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig)
    target = DeliveryTarget(kind="wechat", ref="u")
    with pytest.raises(InvalidInputError):
        service.create(user, title="过去", text="x", target=target, at="2026-11-05T11:00:00+08:00")
    with pytest.raises(InvalidInputError):
        service.create(user, title="太远", text="x", target=target, at="2029-11-05T11:00:00+08:00")
    with pytest.raises(InvalidInputError):
        service.create(
            user, title="空", text="  ", target=target,
            at="2026-11-06T11:00:00+08:00",
        )


def test_delivered_between_uses_actual_sent_time_across_midnight(rig) -> None:
    clock = FakeClock(_epoch(2026, 11, 5, 23, 45))
    rig = make_rig(rig.tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig)
    schedule = service.create(
        user, title="提醒", text="提醒",
        target=DeliveryTarget(kind="wechat", ref="u"),
        at="2026-11-05T23:50:00+08:00",
    )
    clock.now = schedule.next_run_at
    service.tick()
    occurrence = service.occurrences(user, schedule.schedule_id, limit=1)[0]
    with rig.db.transaction() as conn:
        conn.execute(
            "UPDATE deliveries SET status='sent', sent_at=? WHERE id=?",
            ("2026-11-06T00:10:00+08:00", occurrence.delivery_id),
        )
    assert service.delivered_between(
        user, "2026-11-05T00:00:00+08:00", "2026-11-06T00:00:00+08:00"
    ) == 0
    assert service.delivered_between(
        user, "2026-11-06T00:00:00+08:00", "2026-11-07T00:00:00+08:00"
    ) == 1


def test_delivered_between_ignores_non_reminder_deliveries(rig) -> None:
    """投递计数归 delivery 模块；care/简报不能算成提醒。"""
    clock = FakeClock(_epoch(2026, 11, 5, 12, 0))
    rig = make_rig(rig.tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig)
    schedule = service.create(
        user, title="提醒", text="提醒",
        target=DeliveryTarget(kind="wechat", ref="u"),
        at="2026-11-05T13:00:00+08:00",
    )
    clock.now = schedule.next_run_at
    service.tick()
    occurrence = service.occurrences(user, schedule.schedule_id, limit=1)[0]
    delivery = DeliveryService(rig.db, sender=FakeSender(), clock=rig.clock)
    care_id = delivery.enqueue_text(
        owner_id=user.user_id,
        target=DeliveryTarget(kind="wechat", ref="u"),
        text="关怀",
        dedup_key=f"mood-care:{user.user_id}:2026-11-05",
        source="care",
    )
    with rig.db.transaction() as conn:
        conn.execute(
            "UPDATE deliveries SET status='sent', sent_at=? WHERE id IN (?,?)",
            ("2026-11-05T13:00:00+08:00", occurrence.delivery_id, care_id),
        )
    assert delivery.count_sent_reminders(
        user.user_id,
        "2026-11-05T00:00:00+08:00",
        "2026-11-06T00:00:00+08:00",
    ) == 1
    assert service.delivered_between(
        user, "2026-11-05T00:00:00+08:00", "2026-11-06T00:00:00+08:00"
    ) == 1

    clock = FakeClock(_epoch(2026, 11, 5, 12, 0))
    rig = make_rig(rig.tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = _service(rig)
    schedule = service.create(
        user, title="提醒", text="提醒",
        target=DeliveryTarget(kind="wechat", ref="u"),
        at="2026-11-05T13:00:00+08:00",
    )
    clock.now = schedule.next_run_at
    service.tick()
    occurrence = service.occurrences(user, schedule.schedule_id, limit=1)[0]
    with rig.db.transaction() as conn:
        conn.execute(
            "UPDATE deliveries SET status='sent', sent_at=? WHERE id=?",
            ("2026-11-05T13:00:00+08:00", occurrence.delivery_id),
        )
    count = service.delivered_between(
        user, "2026-11-05T00:00:00+08:00", "2026-11-06T00:00:00+08:00"
    )
    assert count == 1
    with rig.db.transaction() as conn:
        conn.execute(
            "UPDATE deliveries SET status='failed' WHERE id=?", (occurrence.delivery_id,)
        )
    assert service.delivered_between(
        user, "2026-11-05T00:00:00+08:00", "2026-11-06T00:00:00+08:00"
    ) == 0
