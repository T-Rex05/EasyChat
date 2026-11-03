"""持久提醒测试（Task 8）：一次性、间隔、每日、错过收敛、重启不重复。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.scheduling.api import SchedulingService
from backend.shared.errors import ForbiddenError
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock, make_rig


def _user(rig, grants=("cron.create",)):
    return rig.seed_user(role="user", grants=grants, username=f"u_{uuid.uuid4().hex[:6]}")


def _services(rig, clock):
    sender = FakeSender()
    delivery = DeliveryService(rig.db, sender=sender, clock=clock, retry_delays=(30.0,))
    scheduling = SchedulingService(
        rig.db, delivery=delivery, access=rig.access, clock=clock, timezone_name="UTC",
    )
    return delivery, scheduling, sender


@pytest.fixture
def env(tmp_path):
    clock = FakeClock(datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp())
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    delivery, scheduling, sender = _services(rig, clock)
    yield rig, delivery, scheduling, sender, clock
    rig.db.close()


TARGET = DeliveryTarget(kind="wechat", ref="wx_reminder", channel_account_id="acct-1")


def test_once_due_exactly_once(env):
    rig, delivery, scheduling, _, clock = env
    user = _user(rig)
    at = datetime.fromtimestamp(clock() + 60, tz=timezone.utc).isoformat()
    schedule = scheduling.create(
        user, title="喝水", text="该喝水了", target=TARGET, at=at,
    )
    assert schedule.next_run_at == pytest.approx(clock() + 60, abs=0.01)

    assert scheduling.tick(now=clock() + 30) == []
    created = scheduling.tick(now=clock() + 61)
    assert len(created) == 1
    refreshed = scheduling.repo.get(schedule.schedule_id)
    assert refreshed.enabled is False  # 一次性执行后停用
    occurrences = scheduling.occurrences(user, schedule.schedule_id)
    assert len(occurrences) == 1
    assert occurrences[0].state == "queued"
    assert occurrences[0].delivery_id == created[0]

    assert scheduling.tick(now=clock() + 61) == []  # 同刻重复 tick 不再生成
    assert delivery.repo.get(created[0])["content_text"] == "该喝水了"


def test_interval_catches_up_latest_only(env):
    rig, _, scheduling, _, clock = env
    user = _user(rig)
    schedule = scheduling.create(
        user, title="巡检", text="巡检提醒", target=TARGET, every_seconds=60,
    )
    first = scheduling.tick(now=clock() + 60)
    assert len(first) == 1
    # 错过 3 个周期：只生成最新一个实例，并记录 missed=3
    later = scheduling.tick(now=clock() + 300)
    assert len(later) == 1
    occurrences = scheduling.occurrences(user, schedule.schedule_id)
    assert occurrences[0].missed == 3
    assert len(occurrences) == 2
    assert scheduling.repo.get(schedule.schedule_id).next_run_at == pytest.approx(clock() + 360, abs=0.01)


def test_daily_catches_up_latest_slot(env):
    rig, _, scheduling, _, clock = env
    user = _user(rig)
    schedule = scheduling.create(
        user, title="日报", text="每日九点提醒", target=TARGET, daily_at="09:00",
    )
    # 今天 10:00 创建 → 下一次是明天 09:00
    expected = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc).timestamp()
    assert schedule.next_run_at == pytest.approx(expected, abs=0.01)

    jan5_10 = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc).timestamp()
    created = scheduling.tick(now=jan5_10)
    assert len(created) == 1
    occurrence = scheduling.occurrences(user, schedule.schedule_id)[0]
    assert occurrence.scheduled_at.startswith("2026-01-05T09:00:00")
    assert occurrence.missed == 3  # 1/2、1/3、1/4 被跳过，只处理 1/5
    assert scheduling.repo.get(schedule.schedule_id).next_run_at == pytest.approx(
        datetime(2026, 1, 6, 9, 0, tzinfo=timezone.utc).timestamp(), abs=0.01
    )


def test_disabled_schedule_does_not_fire(env):
    rig, _, scheduling, _, clock = env
    user = _user(rig)
    schedule = scheduling.create(
        user, title="暂停", text="不该发", target=TARGET, every_seconds=60,
    )
    scheduling.set_enabled(user, schedule.schedule_id, False)
    assert scheduling.tick(now=clock() + 3600) == []


def test_restart_does_not_duplicate_occurrence(env):
    rig, delivery, scheduling, sender, clock = env
    user = _user(rig)
    schedule = scheduling.create(
        user, title="重启", text="只发一次", target=TARGET, every_seconds=60,
    )
    first = scheduling.tick(now=clock() + 60)
    assert len(first) == 1

    # 模拟进程重启：同一 DB 上重建服务，同一时刻 tick
    _, restarted, _ = _services(rig, clock)
    assert restarted.tick(now=clock() + 60) == []
    assert len(restarted.occurrences(user, schedule.schedule_id)) == 1


def test_owner_isolation_and_permissions(env):
    rig, _, scheduling, _, _ = env
    owner = _user(rig)
    other = _user(rig)
    no_perm = rig.seed_user(
        role="user", revokes=("cron.create",), username=f"u_{uuid.uuid4().hex[:6]}"
    )
    schedule = scheduling.create(
        owner, title="私有", text="只给自己", target=TARGET, every_seconds=60,
    )
    assert scheduling.list(other) == []
    with pytest.raises(ForbiddenError):
        scheduling.set_enabled(other, schedule.schedule_id, False)
    with pytest.raises(ForbiddenError):
        scheduling.create(no_perm, title="x", text="y", target=TARGET, every_seconds=60)


def test_invalid_schedule_inputs_rejected(env):
    rig, _, scheduling, _, _ = env
    user = _user(rig)
    from backend.shared.errors import InvalidInputError

    with pytest.raises(InvalidInputError):
        scheduling.create(user, title="x", text="", target=TARGET, every_seconds=60)
    with pytest.raises(InvalidInputError):
        scheduling.create(user, title="x", text="y", target=TARGET, every_seconds=10)
    with pytest.raises(InvalidInputError):
        scheduling.create(user, title="x", text="y", target=TARGET, at="not-a-date")
    with pytest.raises(InvalidInputError):
        scheduling.create(user, title="x", text="y", target=TARGET, every_seconds=60, daily_at="09:00")
