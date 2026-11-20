"""投递账本测试（Task 8）：成功、重试、uncertain、分块续发、解绑与 run 完成同事务。"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.modules.delivery.api import CompositeDeliverySender, DeliveryService
from backend.modules.delivery.contracts import (
    DELIVERY_FAILED,
    DELIVERY_RETRY_WAIT,
    DELIVERY_SENT,
    DELIVERY_UNCERTAIN,
    DeliveryTarget,
    SendResult,
)
from backend.modules.delivery.worker import DeliveryWorker
from backend.runtime.contracts import RuntimeEvent
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock, make_rig

TARGET = DeliveryTarget(kind="wechat", ref="wx_target", channel_account_id="acct-1", context_token="ctx-1")


def _completed(text: str = "最终答案") -> list[RuntimeEvent]:
    return [RuntimeEvent(kind="completed", payload={"result": {"final_response": text, "completed": True}})]


def _user(rig):
    return rig.seed_user(role="user", grants=("chat.use",), username=f"u_{uuid.uuid4().hex[:6]}")


def _service(rig, clock, sender=None):
    return DeliveryService(
        rig.db, sender=sender or FakeSender(), clock=clock,
        retry_delays=(30.0,), max_attempts=3,
    )


@pytest.fixture
async def env(tmp_path):
    clock = FakeClock(1_000_000.0)
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    sender = FakeSender()
    service = _service(rig, clock, sender)
    rig.attach_assistant()
    await rig.start_assistant()
    yield rig, service, sender, clock
    await rig.aclose()


async def test_text_delivery_succeeds_once(env):
    rig, service, sender, _ = env
    user = _user(rig)
    delivery_id = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text="你好", dedup_key="dlv-1",
    )
    worker = DeliveryWorker(service)
    assert await worker.tick() == 1
    assert sender.sent[0]["text"] == "你好"
    assert service.status(user.user_id, delivery_id).status == DELIVERY_SENT
    parts = service.repo.parts(delivery_id)
    assert [p["status"] for p in parts] == ["sent"]
    assert await worker.tick() == 0  # 已 sent 不再认领


async def test_retry_resumes_only_unsent_chunks(env):
    rig, service, sender, clock = env
    user = _user(rig)
    text = ("A" * 300) + "\n\n" + ("B" * 300)
    delivery_id = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text=text, dedup_key="dlv-chunk",
    )
    sender.script(SendResult.sent("ext-1"), SendResult.retry("第二块超时"))
    worker = DeliveryWorker(service)
    assert await worker.tick() == 1
    assert len(service.repo.parts(delivery_id)) == 2
    assert service.status(user.user_id, delivery_id).status == DELIVERY_RETRY_WAIT
    assert [p["status"] for p in service.repo.parts(delivery_id)] == ["sent", "failed"]

    clock.advance(31)
    assert await worker.tick() == 1
    assert service.status(user.user_id, delivery_id).status == DELIVERY_SENT
    assert len(sender.sent) == 3  # 第一块只发过一次；第二块失败后重发
    assert sender.sent[1]["text"].startswith("B")
    assert sender.sent[2]["text"].startswith("B")


async def test_uncertain_is_not_auto_resent(env):
    rig, service, sender, clock = env
    user = _user(rig)
    delivery_id = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text="可能已送达", dedup_key="dlv-uncertain",
    )
    sender.script(SendResult.unsure("连接中断"))
    worker = DeliveryWorker(service)
    assert await worker.tick() == 1
    assert service.status(user.user_id, delivery_id).status == DELIVERY_UNCERTAIN
    clock.advance(3600)
    assert await worker.tick() == 0
    assert len(sender.sent) == 1


async def test_composite_channel_check_error_is_uncertain_not_failed(env):
    rig, _ignored, _sender, clock = env
    user = _user(rig)

    class BrokenSender:
        async def can_deliver(self, target):
            raise RuntimeError("数据库繁忙")

        async def send_text(self, target, text, *, context_token=""):
            raise AssertionError("不应调用")

    class NoChannel:
        async def can_deliver(self, target):
            return False

        async def send_text(self, target, text, *, context_token=""):
            raise AssertionError("不应调用")

    service = DeliveryService(
        rig.db,
        sender=CompositeDeliverySender([BrokenSender(), NoChannel()]),
        clock=clock,
    )
    delivery_id = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text="你好", dedup_key="dlv-composite-err",
    )
    assert await DeliveryWorker(service).tick() == 1
    assert service.status(user.user_id, delivery_id).status == DELIVERY_UNCERTAIN


async def test_email_target_must_be_owner_recipient(env):
    rig, _service, sender, clock = env
    user = _user(rig)
    service = DeliveryService(
        rig.db, sender=sender, clock=clock,
        email_recipient_check=lambda owner_id, address: False,
    )
    delivery_id = service.enqueue_text(
        owner_id=user.user_id,
        target=DeliveryTarget(kind="email", ref="attacker@example.com"),
        text=" spam ", dedup_key="dlv-email-open-relay",
    )
    worker = DeliveryWorker(service)
    assert await worker.tick() == 1
    status = service.status(user.user_id, delivery_id)
    assert status.status == DELIVERY_FAILED
    assert "收件人" in (status.error or "")
    assert sender.sent == []


async def test_unexpected_delivery_error_does_not_leave_sending(env):
    rig, service, sender, _ = env
    user = _user(rig)
    sender.can_deliver_error = RuntimeError("模拟数据库繁忙")
    delivery_id = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text="你好", dedup_key="dlv-error",
    )
    worker = DeliveryWorker(service)
    assert await worker.tick() == 1
    status = service.status(user.user_id, delivery_id)
    assert status.status == DELIVERY_UNCERTAIN
    assert "数据库繁忙" in (status.error or "")
    # 已经进入终态，不会再次被认领而重复发送。
    assert await worker.tick() == 0


async def test_unbound_target_stops_delivery(env):
    rig, service, sender, _ = env
    user = _user(rig)
    sender.deliverable = False
    delivery_id = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text="不该发送", dedup_key="dlv-unbound",
    )
    await DeliveryWorker(service).tick()
    assert sender.sent == []
    assert sender.can_deliver_calls == 1  # 一次解析，不再 can/send 双探测
    assert service.status(user.user_id, delivery_id).status == DELIVERY_FAILED


async def test_dedup_key_prevents_duplicate_delivery(env):
    rig, service, sender, _ = env
    user = _user(rig)
    first = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text="只发一次", dedup_key="same-result",
    )
    second = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text="只发一次", dedup_key="same-result",
    )
    assert first == second
    await DeliveryWorker(service).tick()
    assert len(sender.sent) == 1


async def test_recover_inflight_marks_uncertain(env):
    rig, service, sender, _ = env
    user = _user(rig)
    delivery_id = service.enqueue_text(
        owner_id=user.user_id, target=TARGET, text="半途重启", dedup_key="dlv-recover",
    )
    with rig.db.transaction() as conn:
        conn.execute("UPDATE deliveries SET status='sending' WHERE id=?", (delivery_id,))
    assert service.recover_inflight() == 1
    assert service.status(user.user_id, delivery_id).status == DELIVERY_UNCERTAIN
    assert sender.sent == []


async def test_run_completion_enqueues_and_delivers_without_rerun(env):
    rig, service, sender, clock = env
    user = _user(rig)

    def on_finish(conn, run):
        row = conn.execute(
            "SELECT content FROM conversations WHERE run_id=? AND role='assistant' "
            "ORDER BY id DESC LIMIT 1",
            (run["id"],),
        ).fetchone()
        if row is not None:
            service.enqueue_run_in_transaction(conn, run, TARGET, str(row["content"]))

    rig.assistant.dispatcher.on_run_finished = on_finish
    rig.runtime.script_events(_completed("微信最终答案"))
    session = await rig.assistant.create_session(user, source="wechat")
    receipt = await rig.assistant.submit(RunCommand(
        principal=user, session_id=session, source="wechat",
        client_message_id="wx-run-1", text="你好", channel_account_id="acct-1",
    ))
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1

    deliveries = service.list_for_owner(user.user_id)
    assert len(deliveries) == 1
    assert deliveries[0].run_id == receipt.run_id

    # 发送失败重试不重跑 Runtime
    sender.script(SendResult.retry("微信网关超时"))
    worker = DeliveryWorker(service)
    await worker.tick()
    clock.advance(31)
    await worker.tick()
    assert rig.runtime.execute_count == 1
    assert sender.sent[0]["text"] == "微信最终答案"


async def test_delivery_requires_owner_for_status(env):
    rig, service, _, _ = env
    owner = _user(rig)
    other = _user(rig)
    delivery_id = service.enqueue_text(
        owner_id=owner.user_id, target=TARGET, text="私有", dedup_key="dlv-owner",
    )
    from backend.shared.errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.status(other.user_id, delivery_id)


async def test_terminal_state_feedback_without_reply(env) -> None:
    """WP-D:失败/取消/空回复 run 均有可读微信回执(此前静默丢弃=无回应缺陷)。

    直接测 bootstrap 终态回调逻辑需要全量 registry,这里以等价最小装配验证
    _make_run_finished 的文本映射与 run 级 dedup:模拟其分支产出+入队。
    """
    from backend.bootstrap import ModuleRegistry, _make_run_finished
    from backend.platform.settings import default_settings

    rig, service, sender, clock = env
    reg = ModuleRegistry(settings=default_settings())
    reg.delivery = service
    reg.channels = None  # 非 wechat run 不投递的路径由 target 判定,下面用 wechat run 验证
    # 需要 channels.target 解析:构造最小替身
    class _Ch:
        def delivery_target_for_run(self, run):
            return __import__("backend.modules.channels.contracts", fromlist=["ChannelTarget"]).ChannelTarget(
                kind="wechat", ref="wx-term-1", channel_account_id="acct-1")
    reg.channels = _Ch()
    on_finish = _make_run_finished(reg)

    # failed run:无 assistant 消息 → 回执含"没有完成"
    user = _user(rig)
    session = await rig.assistant.create_session(user, source="wechat")
    with rig.db.transaction() as conn:
        conn.execute(
            "INSERT INTO runs(id, owner_id, session_id, client_message_id, source, status, error,"
            " created_at, updated_at, finished_at)"
            " VALUES('run-term-f', ?, ?, 'cm-f', 'wechat', 'failed', '模型超时',"
            " '2026-11-13T00:00:00+00:00', '2026-11-13T00:00:05+00:00', '2026-11-13T00:00:05+00:00')",
            (user.user_id, session),
        )
        run = conn.execute("SELECT * FROM runs WHERE id='run-term-f'").fetchone()
        on_finish(conn, dict(run))
    def _texts():
        conn = rig.db.connect()
        try:
            return [str(r["content_text"]) for r in conn.execute(
                "SELECT content_text FROM deliveries WHERE owner_id=? ORDER BY id",
                (user.user_id,)).fetchall()]
        finally:
            conn.close()

    rows = service.list_for_owner(user.user_id)
    assert len(rows) == 1
    assert "没有完成" in _texts()[0] and "模型超时" in _texts()[0]

    # cancelled run:回执"已按你的要求停止"
    with rig.db.transaction() as conn:
        conn.execute(
            "INSERT INTO runs(id, owner_id, session_id, client_message_id, source, status,"
            " created_at, updated_at)"
            " VALUES('run-term-c', ?, ?, 'cm-c', 'wechat', 'cancelled',"
            " '2026-11-13T00:01:00+00:00', '2026-11-13T00:01:01+00:00')",
            (user.user_id, session),
        )
    with rig.db.transaction() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id='run-term-c'").fetchone()
        on_finish(conn, dict(run))
    assert len(service.list_for_owner(user.user_id)) == 2
    assert any("停止本次回答" in x for x in _texts())

    # 重复终态:run 级 dedup 不双发
    with rig.db.transaction() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id='run-term-c'").fetchone()
        on_finish(conn, dict(run))
    assert len([x for x in _texts() if "停止" in x]) == 1  # run 级 dedup 不双发


async def test_queued_wechat_delivery_revalidates_owner_after_rebind(tmp_path):
    from backend.modules.delivery.wechat import WeChatTextSender
    from tests.support.wechat import make_channel_rig

    rig, transport, _ = make_channel_rig(tmp_path)
    try:
        admin = rig.seed_user(role="super_admin")
        original = _user(rig)
        successor = _user(rig)
        account = rig.channels.register_account(
            admin, account_id="bot", token="synthetic", base_url="https://ilink.test", bot_user_id="bot-user",
        )

        def bind(actor):
            rig.channels.bind_user(
                admin, platform="wechat", account_id="bot", external_user_id="wx_destination",
                user_id=actor.user_id, account_pk=account.id,
            )

        bind(original)
        service = DeliveryService(rig.db, sender=WeChatTextSender(rig.channels))
        target = DeliveryTarget(
            kind="wechat", ref="wx_destination", channel_account_id=account.id, context_token="test-context",
        )
        old_id = service.enqueue_text(owner_id=original.user_id, target=target, text="原用户内容", dedup_key="old")
        bind(successor)
        new_id = service.enqueue_text(owner_id=successor.user_id, target=target, text="现用户内容", dedup_key="new")

        worker = DeliveryWorker(service)
        await worker.tick()
        assert service.status(original.user_id, old_id).status == DELIVERY_FAILED
        assert service.status(successor.user_id, new_id).status == DELIVERY_SENT
        assert transport.sent == ["现用户内容"]
    finally:
        await rig.aclose()


async def test_queued_wechat_chat_and_memory_deliveries_revalidate_permissions(tmp_path):
    from backend.modules.delivery.wechat import WeChatTextSender
    from tests.support.wechat import inbound, make_channel_rig, text_message

    rig, transport, _ = make_channel_rig(tmp_path)
    try:
        admin = rig.seed_user(role="super_admin")
        owner = rig.seed_user(grants=("chat.use", "memory.view"))
        account = rig.channels.register_account(
            admin, account_id="bot", token="synthetic", base_url="https://ilink.test", bot_user_id="bot-user",
        )
        rig.channels.bind_user(
            admin, platform="wechat", account_id="bot", external_user_id="wx_ext_1",
            user_id=owner.user_id, account_pk=account.id,
        )
        event = await rig.channels.handle_inbound(inbound(
            rig, rig.channels.repo.get_account(account.id), text_message("你好", message_id="message-before-revoke"),
        ))
        run = rig.assistant.repo.get_run(event.run_id)
        target = DeliveryTarget(kind="wechat", ref="wx_ext_1", channel_account_id=account.id, context_token="ctx")
        service = DeliveryService(rig.db, sender=WeChatTextSender(rig.channels))
        with rig.db.transaction() as conn:
            answer = service.enqueue_run_in_transaction(conn, run, target, "角色会话答案")
        reminder = service.enqueue_text(
            owner_id=owner.user_id, target=target, text="定时提醒", dedup_key="reminder", source="schedule",
        )
        worker = DeliveryWorker(service)
        rig.access.set_user_permission(admin, owner.user_id, "chat.use", False)
        await worker.tick()
        assert service.status(owner.user_id, answer).status == DELIVERY_FAILED
        assert service.status(owner.user_id, reminder).status == DELIVERY_SENT

        rig.access.set_user_permission(admin, owner.user_id, "chat.use", True)
        confirmation = service.enqueue_text(
            owner_id=owner.user_id, target=target, text="记忆确认", dedup_key="confirm", source="memory",
        )
        rig.access.set_user_permission(admin, owner.user_id, "memory.view", False)
        await worker.tick()
        assert service.status(owner.user_id, confirmation).status == DELIVERY_FAILED
        assert transport.sent == ["定时提醒"]
    finally:
        await rig.aclose()
