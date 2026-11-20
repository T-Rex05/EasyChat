"""持久提醒测试（Task 8）：一次性、间隔、每日、错过收敛、重启不重复。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.scheduling.api import SchedulingService
from backend.modules.scheduling.routes import build_scheduling_router
from backend.shared.errors import ForbiddenError, InvalidInputError
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


def test_edit_keeps_schedule_history_and_uses_new_timing_and_destination(env):
    rig, delivery, scheduling, _, clock = env
    user = _user(rig)
    schedule = scheduling.create(user, title="Before", text="Old text", target=TARGET, every_seconds=60)
    clock.advance(60)
    first_delivery, = scheduling.tick()
    first_occurrence, = scheduling.occurrences(user, schedule.schedule_id)
    new_target = DeliveryTarget(kind="email", ref="reminder@example.com")

    edited = scheduling.update(
        user, schedule.schedule_id, title="After", text="New text", target=new_target,
        weekly_at="09:30", weekday=4, timezone="Asia/Shanghai",
    )
    assert edited.schedule_id == schedule.schedule_id
    assert edited.created_at == schedule.created_at
    assert edited.last_run_at == first_occurrence.scheduled_at
    assert edited.enabled is True
    assert (edited.kind, edited.weekday, edited.at_time) == ("weekly", 4, "09:30")
    assert edited.next_run_at == datetime(2026, 1, 2, 1, 30, tzinfo=timezone.utc).timestamp()
    assert scheduling.occurrences(user, schedule.schedule_id) == [first_occurrence]
    assert scheduling.tick(now=clock() + 60) == []
    next_delivery, = scheduling.tick(now=edited.next_run_at)
    assert delivery.repo.get(first_delivery)["content_text"] == "Old text"
    assert delivery.repo.get(next_delivery)["content_text"] == "New text"
    assert delivery.repo.get(next_delivery)["target_ref"] == new_target.ref


def test_edit_metadata_preserves_interval_anchor_and_paused_state(env):
    rig, _, scheduling, _, clock = env
    user = _user(rig)
    schedule = scheduling.create(user, title="Before", text="Old text", target=TARGET, every_seconds=60)
    scheduling.cancel(user, schedule.schedule_id)
    clock.advance(30)

    edited = scheduling.update(user, schedule.schedule_id, title="After", every_seconds=60)

    assert edited.title == "After"
    assert edited.text == "Old text"
    assert edited.next_run_at == schedule.next_run_at
    assert edited.enabled is False


def test_completed_once_can_be_edited_and_rescheduled_without_losing_history(env):
    rig, delivery, scheduling, _, clock = env
    user = _user(rig)
    first_at = datetime.fromtimestamp(clock() + 60, tz=timezone.utc)
    schedule = scheduling.create(user, title="Once", text="Old text", target=TARGET, at=first_at.isoformat())
    clock.advance(60)
    assert len(scheduling.tick()) == 1
    first_occurrence, = scheduling.occurrences(user, schedule.schedule_id)

    renamed = scheduling.update(user, schedule.schedule_id, title="Renamed")
    assert renamed.next_run_at == schedule.next_run_at
    assert renamed.enabled is False

    next_at = datetime.fromtimestamp(clock() + 60, tz=timezone.utc)
    edited = scheduling.update(user, schedule.schedule_id, text="New text", at=next_at.isoformat())
    assert edited.next_run_at == next_at.timestamp()
    assert edited.enabled is False
    assert scheduling.occurrences(user, schedule.schedule_id) == [first_occurrence]
    assert scheduling.tick(now=edited.next_run_at) == []

    scheduling.set_enabled(user, schedule.schedule_id, True)
    delivery_id, = scheduling.tick(now=edited.next_run_at)
    assert delivery.repo.get(delivery_id)["content_text"] == "New text"
    assert len(scheduling.occurrences(user, schedule.schedule_id)) == 2


async def test_edit_to_wechat_resolves_schedule_owners_binding(env):
    rig, _, scheduling, _, _ = env
    owner = _user(rig)
    manager = _user(rig, grants=("cron.create", "system.manage"))
    schedule = scheduling.create(
        owner, title="Remind", text="Reminder", every_seconds=60,
        target=DeliveryTarget(kind="email", ref="original@example.com"),
    )
    targets = {
        owner.user_id: TARGET,
        manager.user_id: DeliveryTarget(kind="wechat", ref="wrong_account", channel_account_id="acct-2"),
    }
    channels = SimpleNamespace(delivery_target_for_owner=targets.get)
    app = FastAPI()
    app.include_router(build_scheduling_router(scheduling, channels, lambda _: manager))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/schedules/{schedule.schedule_id}", json={"target_kind": "wechat"},
            headers={"Authorization": "Bearer manager"},
        )
    assert response.status_code == 200
    assert response.json()["schedule"]["target"] == {
        "kind": TARGET.kind, "ref": TARGET.ref, "channel_account_id": TARGET.channel_account_id,
    }
    assert scheduling.get(owner, schedule.schedule_id).target == TARGET


def test_invalid_or_unauthorized_schedule_edit_is_atomic(env):
    rig, _, scheduling, _, _ = env
    owner = _user(rig)
    stranger = _user(rig)
    schedule = scheduling.create(owner, title="Before", text="Old text", target=TARGET, daily_at="09:00")
    with pytest.raises(InvalidInputError):
        scheduling.update(owner, schedule.schedule_id, title="Invalid", weekly_at="09:30", weekday=7)
    with pytest.raises(ForbiddenError):
        scheduling.update(stranger, schedule.schedule_id, title="Forbidden")
    rig.access.repo.set_user_permission(owner.user_id, "cron.create", False)
    rig.access.invalidate_all()
    with pytest.raises(ForbiddenError):
        scheduling.update(owner, schedule.schedule_id, title="Revoked")
    assert scheduling.repo.get(schedule.schedule_id) == schedule


@pytest.mark.parametrize("reschedule", [False, True])
def test_tick_rechecks_due_schedule_after_edit(env, monkeypatch, reschedule):
    rig, delivery, scheduling, _, clock = env
    user = _user(rig)
    schedule = scheduling.create(user, title="Race", text="Old text", target=TARGET, every_seconds=60)
    clock.advance(60)
    load_due = scheduling.repo.due

    def edit_after_due_read(now):
        due = load_due(now)
        timing = {"daily_at": "11:00"} if reschedule else {}
        scheduling.update(user, schedule.schedule_id, text="New text", **timing)
        return due

    monkeypatch.setattr(scheduling.repo, "due", edit_after_due_read)

    deliveries = scheduling.tick()
    if reschedule:
        assert deliveries == []
        assert scheduling.occurrences(user, schedule.schedule_id) == []
        assert scheduling.get(user, schedule.schedule_id).next_run_at == clock() + 59 * 60
    else:
        delivery_id, = deliveries
        assert delivery.repo.get(delivery_id)["content_text"] == "New text"
        assert scheduling.get(user, schedule.schedule_id).next_run_at == clock() + 60


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

    with pytest.raises(InvalidInputError):
        scheduling.create(user, title="x", text="", target=TARGET, every_seconds=60)
    with pytest.raises(InvalidInputError):
        scheduling.create(user, title="x", text="y", target=TARGET, every_seconds=10)
    with pytest.raises(InvalidInputError):
        scheduling.create(user, title="x", text="y", target=TARGET, at="not-a-date")
    with pytest.raises(InvalidInputError):
        scheduling.create(user, title="x", text="y", target=TARGET, every_seconds=60, daily_at="09:00")
