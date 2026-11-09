"""C3 主动关心：连续 3 个低分自然日、7 天间隔、proactivity、安静时段延迟。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.modules.profiles.api import ProfilesService
from backend.modules.profiles.worker import MOOD_JOB_KIND, MoodWorker
from backend.platform.jobs import JobQueue
from tests.support.rig import FakeClock, make_rig

DAY = 24 * 3600
BASE = 1762300800.0  # 2026-11-05 08:00 +08


def _setup(tmp_path, *, proactivity: str = "normal"):
    clock = FakeClock(BASE)
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user()
    service = ProfilesService(rig.db, access=rig.access, clock=clock)
    service.set_mood_enabled(user, True)
    if proactivity != "normal":
        service.update(user, proactivity=proactivity)
    return rig, service, user, clock


def _low(service, user, day_offset: int, label: str = "加班", score: int = -1) -> None:
    entry_date = datetime.fromtimestamp(
        BASE + day_offset * DAY, tz=ZoneInfo("Asia/Shanghai")
    ).date().isoformat()
    service.record_mood_for_owner(
        user.user_id, entry_date=entry_date, score=score, labels=(label,),
        evidence=("有点累",),
    )


def test_care_due_requires_three_consecutive_low_days(tmp_path) -> None:
    _rig, service, user, clock = _setup(tmp_path)
    _low(service, user, 0)
    _low(service, user, 1)
    assert service.care_due(user.user_id) is None
    _low(service, user, 2)
    clock.now = BASE + 2 * DAY
    decision = service.care_due(user.user_id)
    assert decision is not None
    assert "加班" in decision.message
    assert decision.message.count("。") <= 2


def test_missing_day_breaks_consecutive_streak(tmp_path) -> None:
    _rig, service, user, clock = _setup(tmp_path)
    _low(service, user, 0)
    _low(service, user, 2)
    _low(service, user, 3)
    clock.now = BASE + 3 * DAY
    assert service.care_due(user.user_id) is None


def test_low_proactivity_disables_care(tmp_path) -> None:
    _rig, service, user, clock = _setup(tmp_path, proactivity="low")
    for offset in (0, 1, 2):
        _low(service, user, offset)
    clock.now = BASE + 2 * DAY
    assert service.care_due(user.user_id) is None


def test_care_respects_seven_day_interval(tmp_path) -> None:
    _rig, service, user, clock = _setup(tmp_path)
    for offset in (0, 1, 2):
        _low(service, user, offset)
    clock.now = BASE + 2 * DAY
    decision = service.care_due(user.user_id)
    assert decision is not None
    service.mark_care_sent(user.user_id)
    for offset in (3, 4, 5):
        _low(service, user, offset)
    clock.now = BASE + 5 * DAY
    assert service.care_due(user.user_id) is None
    clock.now = BASE + 9 * DAY
    _low(service, user, 9)
    # 第 7、8 天缺失会中断连续；补第 7、8 天后重新满足。
    _low(service, user, 7)
    _low(service, user, 8)
    assert service.care_due(user.user_id) is not None


class FakeDelivery:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def enqueue_text(self, **kwargs):
        self.calls.append(kwargs)
        return "dlv_care"


class FakeChannels:
    def __init__(self) -> None:
        self.bound = True

    def delivery_target_for_owner(self, owner_id):
        if not self.bound:
            return None
        from backend.modules.channels.contracts import ChannelTarget

        return ChannelTarget(
            kind="wechat", ref="wx_u", channel_account_id="acct"
        )


def _care_worker(rig, service, user, clock):
    queue = JobQueue(rig.db, clock=clock)
    worker = MoodWorker(service, queue)
    delivery = FakeDelivery()
    channels = FakeChannels()
    worker.delivery = delivery
    worker.channels = channels
    queue.enqueue(
        kind=MOOD_JOB_KIND, dedup_key="mood:care-test",
        payload={"owner_id": user.user_id, "run_id": "run_care", "text": "今天很累"},
        owner_id=user.user_id,
    )
    return worker, queue, delivery, channels


def test_worker_enqueues_care_after_quiet_wakeup_without_marking(tmp_path) -> None:
    rig, service, user, clock = _setup(tmp_path)
    for offset in (0, 1, 2):
        _low(service, user, offset)
    clock.now = BASE + 2 * DAY
    service.update(user, quiet_start="23:00", quiet_end="07:30")
    clock.now = BASE + 2 * DAY + 15.5 * 3600
    worker, queue, delivery, _channels = _care_worker(rig, service, user, clock)

    import asyncio

    assert asyncio.run(worker.tick()) >= 1
    assert delivery.calls == []  # 安静时段只排复核任务，不提前记发送成功
    assert service.get(user).last_care_at is None

    clock.advance(8 * 3600)  # 到 07:30
    assert asyncio.run(worker.tick()) >= 1
    assert delivery.calls and delivery.calls[0].get("delay_seconds", 0) == 0
    # 入队成功不代表发送成功；last_care_at 必须等 delivery 终态 sent 回调。
    assert service.get(user).last_care_at is None


def test_care_rechecks_opt_in_before_quiet_wakeup(tmp_path) -> None:
    rig, service, user, clock = _setup(tmp_path)
    for offset in (0, 1, 2):
        _low(service, user, offset)
    clock.now = BASE + 2 * DAY
    service.update(user, quiet_start="23:00", quiet_end="07:30")
    clock.now = BASE + 2 * DAY + 15.5 * 3600
    worker, _queue, delivery, _channels = _care_worker(rig, service, user, clock)

    import asyncio

    asyncio.run(worker.tick())
    service.set_mood_enabled(user, False)
    clock.advance(8 * 3600)
    asyncio.run(worker.tick())
    assert delivery.calls == []
    assert service.get(user).last_care_at is None


def test_care_rechecks_low_proactivity_before_quiet_wakeup(tmp_path) -> None:
    rig, service, user, clock = _setup(tmp_path)
    for offset in (0, 1, 2):
        _low(service, user, offset)
    clock.now = BASE + 2 * DAY
    service.update(user, quiet_start="23:00", quiet_end="07:30")
    clock.now = BASE + 2 * DAY + 15.5 * 3600
    worker, _queue, delivery, _channels = _care_worker(rig, service, user, clock)

    import asyncio

    asyncio.run(worker.tick())
    service.update(user, proactivity="low")
    clock.advance(8 * 3600)
    asyncio.run(worker.tick())
    assert delivery.calls == []
    assert service.get(user).last_care_at is None


def test_care_rechecks_target_before_quiet_wakeup(tmp_path) -> None:
    rig, service, user, clock = _setup(tmp_path)
    for offset in (0, 1, 2):
        _low(service, user, offset)
    clock.now = BASE + 2 * DAY
    service.update(user, quiet_start="23:00", quiet_end="07:30")
    clock.now = BASE + 2 * DAY + 15.5 * 3600
    worker, _queue, delivery, channels = _care_worker(rig, service, user, clock)

    import asyncio

    asyncio.run(worker.tick())
    channels.bound = False
    clock.advance(8 * 3600)
    asyncio.run(worker.tick())
    assert delivery.calls == []
    assert service.get(user).last_care_at is None


def test_high_proactivity_allows_second_care_after_three_days_then_blocks(tmp_path) -> None:
    _rig, service, user, clock = _setup(tmp_path, proactivity="high")
    for offset in (0, 1, 2):
        _low(service, user, offset)
    clock.now = BASE + 2 * DAY
    assert service.care_due(user.user_id) is not None
    service.mark_care_sent(user.user_id)

    for offset in (3, 4, 5):
        _low(service, user, offset)
    clock.now = BASE + 5 * DAY
    assert service.care_due(user.user_id) is not None
    service.mark_care_sent(user.user_id)

    for offset in (6, 7, 8):
        _low(service, user, offset)
    clock.now = BASE + 8 * DAY
    assert service.care_due(user.user_id) is None  # 最近 7 天已 2 次

    for offset in (11, 12, 13):
        _low(service, user, offset)
    clock.now = BASE + 13 * DAY
    assert service.care_due(user.user_id) is not None
