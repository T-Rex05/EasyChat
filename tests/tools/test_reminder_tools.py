"""提醒工具：ToolContext 身份、无绑定拒绝、创建/列表/取消/稍后。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo


from backend.modules.delivery.api import DeliveryService
from backend.modules.scheduling.api import SchedulingService
from backend.shared.tool_context import ToolContext, config_with
from backend.tools.business.reminder_tools import build_reminder_tools
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock, make_rig

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=TZ).timestamp()


class _Channels:
    def __init__(self, target=True) -> None:
        self.target = target

    def delivery_target_for_owner(self, owner_id: int):
        if not self.target:
            return None
        from backend.modules.channels.contracts import ChannelTarget

        return ChannelTarget(
            kind="wechat", ref=f"wx-{owner_id}", channel_account_id="chn_1"
        )


class _Profiles:
    def timezone_for(self, owner_id: int) -> str:
        return "Asia/Shanghai"


def _setup(rig, *, target=True):
    clock = FakeClock(NOW)
    rig = make_rig(rig.tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))
    service = SchedulingService(
        rig.db, delivery=DeliveryService(rig.db, sender=FakeSender(), clock=clock),
        access=rig.access, clock=clock, queue=None,
    )
    tools = {
        item.name: item
        for item in build_reminder_tools(
            scheduling=service, channels=_Channels(target), profiles=_Profiles()
        )
    }
    context = ToolContext(
        principal=user, run_id="run_" + "a" * 32, session_id="sess_" + "b" * 32,
        source="wechat", channel_account_id="chn_1",
    )
    return rig, user, service, tools, context


def _invoke(tool, args, context):
    return tool.invoke(args, config=config_with(context))


def test_create_uses_context_and_returns_readable_id(rig) -> None:
    rig, user, service, tools, context = _setup(rig)
    result = _invoke(
        tools["reminder_create"],
        {"text": "交周报", "weekly_at": "09:00", "weekday": 0},
        context,
    )
    assert "已设置" in result
    assert "交周报" in result
    schedules = service.list(user)
    assert len(schedules) == 1
    assert schedules[0].owner_id == user.user_id
    assert schedules[0].weekday == 0


def test_no_binding_does_not_create_orphan(rig) -> None:
    rig, user, service, tools, context = _setup(rig, target=False)
    result = _invoke(
        tools["reminder_create"], {"text": "喝水", "daily_at": "09:00"}, context
    )
    assert "还没绑定微信" in result
    assert service.list(user) == []


def test_missing_identity_is_rejected(rig) -> None:
    rig, _user, _service, tools, _context = _setup(rig)
    result = tools["reminder_create"].invoke({"text": "x", "daily_at": "09:00"})
    assert "缺少可信用户身份" in result


def test_cancel_and_snooze_keep_original(rig) -> None:
    rig, user, service, tools, context = _setup(rig)
    created = _invoke(
        tools["reminder_create"],
        {"text": "牙医", "at": "2026-11-06T09:00:00+08:00"},
        context,
    )
    schedule = service.list(user)[0]
    listed = _invoke(tools["reminder_list"], {}, context)
    assert "牙医" in listed and schedule.schedule_id.split("_")[1][:6] in listed
    snoozed = _invoke(
        tools["reminder_snooze"],
        {"schedule_id": schedule.schedule_id, "minutes": 30},
        context,
    )
    assert "再提醒你" in snoozed
    assert len(service.list(user)) == 2
    _invoke(tools["reminder_cancel"], {"schedule_id": schedule.schedule_id}, context)
    assert service.get(user, schedule.schedule_id).enabled is False
    assert "已设置" in created


def test_duplicate_create_within_10_minutes_returns_existing(rig) -> None:
    rig, user, service, tools, context = _setup(rig)
    first = _invoke(
        tools["reminder_create"],
        {"text": "开会", "at": "2026-11-06T09:00:00+08:00"},
        context,
    )
    second = _invoke(
        tools["reminder_create"],
        {"text": "开会", "at": "2026-11-06T09:00:00+08:00"},
        context,
    )
    assert len(service.list(user)) == 1
    id1 = _invoke(tools["reminder_list"], {}, context).split("ID ")[1].split("）")[0]
    assert id1 in first and id1 in second


def test_owner_isolation_cannot_cancel_other_users(rig) -> None:
    rig, user, service, tools, context = _setup(rig)
    _invoke(tools["reminder_create"], {"text": "我的", "daily_at": "09:00"}, context)
    other = rig.seed_user(grants=("cron.create",))
    other_ctx = ToolContext(principal=other, source="wechat")
    schedule = service.list(user)[0]
    result = _invoke(
        tools["reminder_cancel"], {"schedule_id": schedule.schedule_id}, other_ctx
    )
    assert "失败" in result
    assert service.get(user, schedule.schedule_id).enabled is True


def test_reminder_e2e_create_due_delivers(rig) -> None:
    """WP-E 端到端:工具创建→未到期不触发→到期投递到绑定微信。"""
    rig, user, service, tools, context = _setup(rig)
    sender = service.delivery.sender

    out = _invoke(tools["reminder_create"],
                  {"text": "喝水", "at": "2026-11-05T14:30:00+08:00"}, context)
    assert "已设置" in out and "14:30" in out

    # NOW=12:00 未到:不触发不投递
    assert service.tick() == []
    assert sender.sent == []

    # 14:31:到期触发,投递引用原文本
    rig.clock.advance((14 * 3600 + 31 * 60) - (12 * 3600))
    fired = service.tick()
    assert fired, "到期应触发"

    async def _drain() -> None:
        # tick 只入队；真实发送由投递队列消费（与 worker 同一条 process_next 路径）
        while await service.delivery.process_next():
            pass

    asyncio.run(_drain())
    assert len(sender.sent) == 1
    assert "喝水" in str(sender.sent[0]["text"])


def _drain(delivery) -> int:
    async def _pump() -> int:
        n = 0
        while await delivery.process_next():
            n += 1
        return n

    return asyncio.run(_pump())


def _delivery_rows(rig, owner_id: int):
    conn = rig.db.connect()
    try:
        return [
            dict(r) for r in conn.execute(
                "SELECT status, error, content_text FROM deliveries"
                " WHERE owner_id=? ORDER BY id", (owner_id,)
            ).fetchall()
        ]
    finally:
        conn.close()


def test_due_occurrence_single_delivery_across_repeat_tick_and_restart(rig) -> None:
    """验收场景：服务重启与重复 tick——该 occurrence 仅形成一次逻辑投递。"""
    rig, user, service, tools, context = _setup(rig)
    _invoke(tools["reminder_create"],
            {"text": "交周报", "at": "2026-11-05T14:30:00+08:00"}, context)
    rig.clock.advance((14 * 3600 + 31 * 60) - (12 * 3600))
    assert service.tick()
    assert service.tick() == [], "一次性提醒到期后不应重复触发"

    # 服务重启：全新 SchedulingService 接同一 db，对账后仍不重复
    restarted = SchedulingService(
        rig.db, delivery=service.delivery, access=rig.access,
        clock=rig.clock, queue=None,
    )
    assert restarted.tick() == []
    assert len(_delivery_rows(rig, user.user_id)) == 1


def test_cancelled_schedule_delivers_nothing(rig) -> None:
    """验收场景：暂停(取消)后的提醒到期不投递，历史可解释。"""
    rig, user, service, tools, context = _setup(rig)
    out = _invoke(tools["reminder_create"],
                  {"text": "已被取消", "at": "2026-11-05T14:30:00+08:00"}, context)
    import re

    schedule_id = re.search(r"ID (\S+?)）", out).group(1)
    assert "已取消" in _invoke(tools["reminder_cancel"],
                               {"schedule_id": schedule_id}, context)
    rig.clock.advance((14 * 3600 + 31 * 60) - (12 * 3600))
    assert service.tick() == []
    assert _delivery_rows(rig, user.user_id) == []


def test_unbound_before_due_rejects_with_reason(rig) -> None:
    """验收场景：创建后、到期前解绑——不静默外发，账本留可读拒投原因。"""
    rig, user, service, tools, context = _setup(rig)
    sender: FakeSender = service.delivery.sender
    _invoke(tools["reminder_create"],
            {"text": "解绑测试", "at": "2026-11-05T14:30:00+08:00"}, context)
    rig.clock.advance((14 * 3600 + 31 * 60) - (12 * 3600))
    assert service.tick()
    sender.deliverable = False  # 到期投递时绑定已撤销
    _drain(service.delivery)

    rows = _delivery_rows(rig, user.user_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert "不可用" in str(rows[0]["error"])
    assert sender.sent == [], "解绑后不得有真实外发"


def test_stale_token_pauses_account_and_retry_is_bounded(rig) -> None:
    """验收场景：凭据失效(errcode -14)——账号上报暂停、投递保留可重试、
    恢复后重投成功；重试有界由 max_attempts 保证。走真实 WeChatTextSender。"""
    from backend.modules.delivery.wechat import WeChatTextSender

    clock = FakeClock(NOW)
    rig = make_rig(rig.tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user(grants=("cron.create",))

    class _WechatChannels:
        def __init__(self) -> None:
            self.reported: list[str] = []
            self.fail = True

        def is_delivery_binding_active(self, account_pk: str, ext: str) -> bool:
            return True

        async def send_wechat_text(self, *, account_pk, external_user_id, text,
                                   context_token=""):
            if self.fail:
                from backend.modules.channels.wechat.account import TransportError

                exc = TransportError("invalid bot token")
                exc.ret = -14
                raise exc
            self.sent_text = text

        def report_stale_token(self, account_pk: str) -> None:
            self.reported.append(account_pk)

    channels = _WechatChannels()
    delivery = DeliveryService(
        rig.db, sender=WeChatTextSender(channels), clock=clock,
        retry_delays=(30.0,), max_attempts=3,
    )
    service = SchedulingService(
        rig.db, delivery=delivery, access=rig.access, clock=clock, queue=None,
    )
    tools = {
        item.name: item for item in build_reminder_tools(
            scheduling=service,
            channels=_Channels(), profiles=_Profiles(),
        )
    }
    context = ToolContext(
        principal=user, run_id="run_" + "c" * 32, session_id="sess_" + "d" * 32,
        source="wechat", channel_account_id="chn_1",
    )
    _invoke(tools["reminder_create"],
            {"text": "喝水", "at": "2026-11-05T14:30:00+08:00"}, context)
    rig.clock.advance((14 * 3600 + 31 * 60) - (12 * 3600))
    assert service.tick()

    _drain(delivery)
    assert channels.reported == ["chn_1"], "-14 必须上报账号暂停(session-guard)"
    rows = _delivery_rows(rig, user.user_id)
    assert rows[0]["status"] == "retry_wait", "凭据失效不得丢消息或误报成功"

    # 暂停期(1h)后恢复：bot token 换新 → 重试成功且只发一次
    channels.fail = False
    rig.clock.advance(31)
    _drain(delivery)
    assert _delivery_rows(rig, user.user_id)[0]["status"] == "sent"
    assert "喝水" in channels.sent_text
