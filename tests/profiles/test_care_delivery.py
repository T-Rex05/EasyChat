"""C3 关怀投递：只有实际发送成功才写 last_care_at / mood_care_log。"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import SendResult
from backend.modules.delivery.worker import DeliveryWorker
from backend.modules.profiles.api import ProfilesService
from backend.modules.profiles.worker import CARE_JOB_KIND, MoodWorker
from backend.platform.jobs import JobQueue
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock, make_rig

BASE = 1762300800.0  # 2026-11-05 08:00 +08


class FakeChannels:
    def delivery_target_for_owner(self, owner_id):
        from backend.modules.channels.contracts import ChannelTarget

        return ChannelTarget(
            kind="wechat", ref="wx_care", channel_account_id="acct"
        )


def _care_key(owner_id: int) -> str:
    day = datetime.fromtimestamp(BASE, ZoneInfo("Asia/Shanghai")).date().isoformat()
    return f"mood-care:{owner_id}:{day}"


def _setup(tmp_path):
    clock = FakeClock(BASE)
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user()
    queue = JobQueue(rig.db, clock=clock)
    service = ProfilesService(
        rig.db, access=rig.access, clock=clock, queue=queue
    )
    service.set_mood_enabled(user, True)
    sender = FakeSender()

    def on_sent(info):
        if info.get("source") == "care":
            service.mark_care_sent(
                int(info["owner_id"]),
                care_key=str(info.get("dedup_key") or ""),
                delivery_created_at=str(info.get("created_at") or ""),
            )

    delivery = DeliveryService(
        rig.db, sender=sender, clock=clock, on_sent=on_sent,
    )
    service.care_canceller = lambda owner_id: delivery.cancel_unsent(
        owner_id, source="care",
        reason="用户删除/关闭情绪或降低主动性，取消关怀",
    )
    worker = MoodWorker(service, queue)
    worker.delivery = delivery
    worker.channels = FakeChannels()
    return rig, service, user, clock, queue, sender, delivery, worker


def _enqueue_care(queue, user, *, job_key: str) -> None:
    queue.enqueue(
        kind=CARE_JOB_KIND,
        dedup_key=job_key,
        payload={
            "owner_id": user.user_id,
            "date": datetime.fromtimestamp(BASE, ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "message": "这两天看起来不太轻松。不用马上回，我在。",
        },
        owner_id=user.user_id,
    )


def _care_logs(rig, owner_id: int) -> int:
    conn = rig.db.connect()
    try:
        row = conn.execute(
            "SELECT count(*) AS c FROM mood_care_log WHERE owner_id=?", (owner_id,)
        ).fetchone()
    finally:
        conn.close()
    return int(row["c"])


def test_failed_delivery_does_not_mark_care_and_failed_dedup_is_not_success(tmp_path) -> None:
    rig, service, user, _clock, queue, sender, delivery, worker = _setup(tmp_path)
    _enqueue_care(queue, user, job_key="care-job:failed")

    asyncio.run(worker.tick())
    assert service.get(user).last_care_at is None
    assert _care_logs(rig, user.user_id) == 0
    assert delivery.list_for_owner(user.user_id)[0].status == "pending"

    sender.script(SendResult.failed("微信发送失败"))
    asyncio.run(DeliveryWorker(delivery).tick())
    assert delivery.list_for_owner(user.user_id)[0].status == "failed"
    assert service.get(user).last_care_at is None
    assert _care_logs(rig, user.user_id) == 0

    # 同 dedup_key 的 failed delivery 被复用，不能再被当成成功标记。
    _enqueue_care(queue, user, job_key="care-job:failed-2")
    asyncio.run(worker.tick())
    assert len(delivery.list_for_owner(user.user_id)) == 1
    assert len(sender.sent) == 1
    assert service.get(user).last_care_at is None
    assert _care_logs(rig, user.user_id) == 0


def test_delete_mood_cancels_pending_care_and_blocks_late_callback(tmp_path) -> None:
    rig, service, user, _clock, queue, sender, delivery, worker = _setup(tmp_path)
    key = _care_key(user.user_id)
    _enqueue_care(queue, user, job_key="care-job:delete-pending")

    asyncio.run(worker.tick())
    pending = delivery.list_for_owner(user.user_id)[0]
    assert pending.status == "pending"

    service.delete_mood(user)

    cancelled = delivery.list_for_owner(user.user_id)[0]
    assert cancelled.status == "cancelled"
    assert cancelled.error
    assert service.get(user).mood_opt_in is False
    assert service.get(user).last_care_at is None
    assert _care_logs(rig, user.user_id) == 0

    # 已取消的 delivery 不会被 worker 认领，也不会有微信发送。
    asyncio.run(DeliveryWorker(delivery).tick())
    assert sender.sent == []
    assert _care_logs(rig, user.user_id) == 0

    # 即使外部/旧代码迟到回调，也不能复活日志或 last_care_at。
    delivery.on_sent({
        "delivery_id": pending.delivery_id,
        "owner_id": user.user_id,
        "source": "care",
        "dedup_key": key,
        "created_at": pending.created_at,
    })
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None


def test_close_mood_cancels_pending_care_and_blocks_late_callback(tmp_path) -> None:
    rig, service, user, _clock, queue, sender, delivery, worker = _setup(tmp_path)
    key = _care_key(user.user_id)
    _enqueue_care(queue, user, job_key="care-job:close-pending")

    asyncio.run(worker.tick())
    pending = delivery.list_for_owner(user.user_id)[0]
    assert pending.status == "pending"

    service.set_mood_enabled(user, False)

    cancelled = delivery.list_for_owner(user.user_id)[0]
    assert cancelled.status == "cancelled"
    assert service.get(user).last_care_at is None
    asyncio.run(DeliveryWorker(delivery).tick())
    assert sender.sent == []
    assert _care_logs(rig, user.user_id) == 0

    delivery.on_sent({
        "delivery_id": pending.delivery_id,
        "owner_id": user.user_id,
        "source": "care",
        "dedup_key": key,
        "created_at": pending.created_at,
    })
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None


def test_callback_arriving_after_delete_cannot_mark_already_sent_care(tmp_path) -> None:
    rig, service, user, _clock, queue, _sender, delivery, worker = _setup(tmp_path)
    key = _care_key(user.user_id)
    _enqueue_care(queue, user, job_key="care-job:late-callback-after-delete")

    asyncio.run(worker.tick())
    pending = delivery.list_for_owner(user.user_id)[0]
    # 模拟外部已发送成功、但 on_sent 回调尚未执行。
    with rig.db.transaction() as conn:
        conn.execute(
            "UPDATE deliveries SET status='sent', sent_at='2026-11-05T00:00:01+00:00' "
            "WHERE id=?",
            (pending.delivery_id,),
        )

    service.delete_mood(user)
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None

    delivery.on_sent({
        "delivery_id": pending.delivery_id,
        "owner_id": user.user_id,
        "source": "care",
        "dedup_key": key,
        "created_at": pending.created_at,
    })
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None


def test_callback_after_delete_cannot_revive_an_already_sent_care(tmp_path) -> None:
    rig, service, user, _clock, queue, sender, delivery, worker = _setup(tmp_path)
    key = _care_key(user.user_id)
    _enqueue_care(queue, user, job_key="care-job:delete-after-sent")

    asyncio.run(worker.tick())
    sender.script(SendResult.sent("wx-ext-delete"))
    asyncio.run(DeliveryWorker(delivery).tick())
    sent = delivery.list_for_owner(user.user_id)[0]
    assert sent.status == "sent"
    assert _care_logs(rig, user.user_id) == 1

    service.delete_mood(user)
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None

    # 删除后重复/迟到回调不能把已删掉的 care 历史带回来。
    delivery.on_sent({
        "delivery_id": sent.delivery_id,
        "owner_id": user.user_id,
        "source": "care",
        "dedup_key": key,
        "created_at": sent.created_at,
    })
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None


def test_close_mood_purges_pending_care_job_before_delivery(tmp_path) -> None:
    _rig, service, user, _clock, queue, _sender, delivery, worker = _setup(tmp_path)
    _enqueue_care(queue, user, job_key="care-job:close-before-worker")

    service.set_mood_enabled(user, False)

    assert asyncio.run(worker.tick()) == 0
    assert delivery.list_for_owner(user.user_id) == []


def test_delete_mood_purges_pending_care_job_before_delivery(tmp_path) -> None:
    _rig, service, user, _clock, queue, _sender, delivery, worker = _setup(tmp_path)
    _enqueue_care(queue, user, job_key="care-job:delete-before-worker")

    service.delete_mood(user)

    assert asyncio.run(worker.tick()) == 0
    assert delivery.list_for_owner(user.user_id) == []


def test_sent_delivery_marks_once_and_duplicate_callback_is_idempotent(tmp_path) -> None:
    rig, service, user, _clock, queue, sender, delivery, worker = _setup(tmp_path)
    key = _care_key(user.user_id)
    _enqueue_care(queue, user, job_key="care-job:sent")

    asyncio.run(worker.tick())
    assert service.get(user).last_care_at is None
    sender.script(SendResult.sent("wx-ext-1"))
    asyncio.run(DeliveryWorker(delivery).tick())

    assert delivery.list_for_owner(user.user_id)[0].status == "sent"
    assert service.get(user).last_care_at is not None
    assert _care_logs(rig, user.user_id) == 1

    # 回调重复执行不能重复写日志，也不能再次推进 last_care_at。
    before = service.get(user).last_care_at
    delivery.on_sent({
        "delivery_id": delivery.list_for_owner(user.user_id)[0].delivery_id,
        "owner_id": user.user_id,
        "source": "care",
        "dedup_key": key,
    })
    assert _care_logs(rig, user.user_id) == 1
    assert service.get(user).last_care_at == before

    # 已有 sent delivery 被同 dedup_key 复用时也不能再发一轮或重复计数。
    _enqueue_care(queue, user, job_key="care-job:sent-2")
    asyncio.run(worker.tick())
    assert len(sender.sent) == 1


def test_unrelated_profile_update_does_not_drop_care_log(tmp_path) -> None:
    """普通资料变更不能复用删除代际，否则会出现“已发送但没记 care”。"""
    rig, service, user, _clock, queue, sender, delivery, worker = _setup(tmp_path)
    _enqueue_care(queue, user, job_key="care-job:profile-update")
    asyncio.run(worker.tick())

    service.update(user, max_chars=100)
    sender.script(SendResult.sent("wx-ext-profile"))
    asyncio.run(DeliveryWorker(delivery).tick())

    assert delivery.list_for_owner(user.user_id)[0].status == "sent"
    assert _care_logs(rig, user.user_id) == 1
    assert service.get(user).last_care_at is not None


def test_low_proactivity_cancels_pending_care_and_stale_callback(tmp_path) -> None:
    """主动性降低后，已入队 care 不应再发；旧回调也不能重新记账。"""
    rig, service, user, _clock, queue, sender, delivery, worker = _setup(tmp_path)
    key = _care_key(user.user_id)
    _enqueue_care(queue, user, job_key="care-job:proactivity-low")
    asyncio.run(worker.tick())
    pending = delivery.list_for_owner(user.user_id)[0]

    service.update(user, proactivity="low")
    cancelled = delivery.list_for_owner(user.user_id)[0]
    assert cancelled.status == "cancelled"
    assert "主动性" in cancelled.error

    asyncio.run(DeliveryWorker(delivery).tick())
    assert sender.sent == []
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None

    delivery.on_sent({
        "delivery_id": pending.delivery_id,
        "owner_id": user.user_id,
        "source": "care",
        "dedup_key": key,
        "created_at": pending.created_at,
    })
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None


def test_re_enable_mood_does_not_revive_old_callback_epoch(tmp_path) -> None:
    """删除后重新开启，旧 delivery 仍必须被 care 代际拒绝。"""
    rig, service, user, _clock, queue, _sender, delivery, worker = _setup(tmp_path)
    key = _care_key(user.user_id)
    _enqueue_care(queue, user, job_key="care-job:re-enable")
    asyncio.run(worker.tick())
    pending = delivery.list_for_owner(user.user_id)[0]

    service.delete_mood(user)
    service.set_mood_enabled(user, True)

    delivery.on_sent({
        "delivery_id": pending.delivery_id,
        "owner_id": user.user_id,
        "source": "care",
        "dedup_key": key,
        "created_at": pending.created_at,
    })
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None


def test_callback_racing_delete_is_atomic_and_does_not_resurrect(
    tmp_path, monkeypatch
) -> None:
    """在 repo 写入前插入 delete，原子校验必须拒绝迟到的 callback。"""
    rig, service, user, _clock, queue, _sender, delivery, worker = _setup(tmp_path)
    key = _care_key(user.user_id)
    _enqueue_care(queue, user, job_key="care-job:race-delete")
    asyncio.run(worker.tick())
    pending = delivery.list_for_owner(user.user_id)[0]

    original = service.repo.mark_care_sent
    entered = threading.Event()
    release = threading.Event()

    def paused(owner_id, at_iso, *, care_key="", delivery_created_at=""):
        entered.set()
        assert release.wait(5)
        return original(
            owner_id, at_iso, care_key=care_key,
            delivery_created_at=delivery_created_at,
        )

    monkeypatch.setattr(service.repo, "mark_care_sent", paused)
    result: dict[str, bool] = {}

    def callback() -> None:
        result["ok"] = service.mark_care_sent(
            user.user_id,
            at_iso="2026-11-05T00:00:00+00:00",
            care_key=key,
            delivery_created_at=pending.created_at,
        )

    thread = threading.Thread(target=callback)
    thread.start()
    assert entered.wait(5)
    service.delete_mood(user)
    release.set()
    thread.join(5)

    assert result["ok"] is False
    assert _care_logs(rig, user.user_id) == 0
    assert service.get(user).last_care_at is None
