"""缺陷②回归：failed/cancelled/排队取消/重启中断/完成空回复的终态回执必须
经真实 dispatcher 状态推进接入（此前只有 completed 分支调用 on_finish 回调，
其余分支只迁移状态——微信用户对这些 run 永远无回应）。

测试穿过真实业务入口：渠道受理(handle_inbound)→dispatcher 终态推进→
bootstrap._make_run_finished 真回调→delivery 账本。
"""
from __future__ import annotations

import uuid

import pytest

from backend.bootstrap import ModuleRegistry, _make_run_finished
from backend.modules.delivery.api import DeliveryService
from backend.platform.settings import default_settings
from backend.runtime.contracts import RuntimeEvent
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock
from tests.support.wechat import make_channel_rig, text_message


def _admin(rig):
    return rig.seed_user(role="super_admin", username=f"admin_{uuid.uuid4().hex[:6]}")


def _user(rig):
    return rig.seed_user(role="user", grants=("chat.use",), username=f"u_{uuid.uuid4().hex[:6]}")


async def _setup(rig, events: list[RuntimeEvent], *, start: bool = True):
    """真实渠道 rig + 真实 DeliveryService + 真 _make_run_finished 回调。

    start=False 时不启动 dispatcher worker（排队取消/中断对账用例）。
    """
    clock = FakeClock(1_000_000.0)
    channel_rig, _, _ = make_channel_rig(rig.tmp_path, clock=clock)
    admin, user = _admin(channel_rig), _user(channel_rig)
    view = channel_rig.channels.register_account(
        admin, account_id="bot_1", token="t", base_url="https://ilink.test",
        bot_user_id="botuser_1",
    )
    account = channel_rig.channels.repo.get_account(view.id)
    channel_rig.channels.bind_user(
        admin, platform="wechat", account_id=account.account_id,
        external_user_id="wx_ext_1", user_id=user.user_id, account_pk=account.id,
    )
    service = DeliveryService(
        channel_rig.db, sender=FakeSender(), clock=clock, retry_delays=(30.0,),
    )
    reg = ModuleRegistry(settings=default_settings())
    reg.delivery = service
    reg.channels = channel_rig.channels
    channel_rig.assistant.dispatcher.on_run_finished = _make_run_finished(reg)
    channel_rig.runtime.script_events(events)
    if start:
        await channel_rig.start_assistant()
    return channel_rig, service, user, account


async def _inbound(channel_rig, account, text: str, msg_id: str):
    from backend.modules.channels.wechat.parser import parse_inbound

    outcome = await channel_rig.channels.handle_inbound(
        parse_inbound(account, text_message(text, message_id=msg_id, from_user="wx_ext_1"),
                      now=1_000_000.0)
    )
    assert outcome.accepted
    return outcome


def _delivery_texts(rig, owner_id: int) -> list[str]:
    conn = rig.db.connect()
    try:
        return [str(r["content_text"]) for r in conn.execute(
            "SELECT content_text FROM deliveries WHERE owner_id=? ORDER BY id",
            (owner_id,),
        ).fetchall()]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_failed_run_delivers_readable_receipt_via_dispatcher(rig) -> None:
    channel_rig, service, user, account = await _setup(
        rig, [RuntimeEvent(kind="failed", payload={"error": "模型超时"})]
    )
    await _inbound(channel_rig, account, "帮我总结今天安排", "m-f")
    await channel_rig.drain_runs()

    conn = channel_rig.db.connect()
    try:
        status = str(conn.execute("SELECT status FROM runs").fetchone()["status"])
    finally:
        conn.close()
    assert status == "failed"
    texts = _delivery_texts(channel_rig, user.user_id)
    assert len(texts) == 1, "缺陷②:此前 failed 分支不调回调→零回执"
    assert "没有完成" in texts[0] and "模型超时" in texts[0]


@pytest.mark.asyncio
async def test_repeated_terminal_produces_single_receipt(rig) -> None:
    """重复终态幂等：已 failed 的 run 再走中断对账不产生第二条回执。"""
    channel_rig, service, user, account = await _setup(
        rig, [RuntimeEvent(kind="failed", payload={"error": "网络错误"})]
    )
    await _inbound(channel_rig, account, "测试重复终态", "m-dup")
    await channel_rig.drain_runs()
    assert len(_delivery_texts(channel_rig, user.user_id)) == 1
    # 模拟重启对账/竞态重复推进：条件 UPDATE 失败 → 回调不触发
    await channel_rig.assistant.dispatcher.recover_interrupted()
    assert len(_delivery_texts(channel_rig, user.user_id)) == 1


@pytest.mark.asyncio
async def test_queued_cancel_delivers_receipt(rig) -> None:
    """排队取消：dispatcher 未消费前取消，同样有可读回执。"""
    channel_rig, service, user, account = await _setup(
        rig, [RuntimeEvent(kind="completed", payload={"result": {"final_response": "hi", "completed": True}})],
        start=False,
    )
    await _inbound(channel_rig, account, "先别跑了", "m-q")
    conn = channel_rig.db.connect()
    try:
        run_id = str(conn.execute("SELECT id FROM runs").fetchone()["id"])
    finally:
        conn.close()

    done = await channel_rig.assistant.cancel(user, run_id)
    assert done
    texts = _delivery_texts(channel_rig, user.user_id)
    assert len(texts) == 1, "缺陷②:此前 queued→cancelled 无回调"
    assert "停止" in texts[0]
    assert channel_rig.runtime.execute_count == 0, "取消的排队 run 不得被执行"


@pytest.mark.asyncio
async def test_restart_interrupted_run_delivers_receipt(rig) -> None:
    """崩溃恢复：遗留 running run 经真实 recover_interrupted 标 interrupted 并回执。"""
    channel_rig, service, user, account = await _setup(rig, [], start=False)
    await _inbound(channel_rig, account, "长任务", "m-i")
    conn = channel_rig.db.connect()
    try:
        run_id = str(conn.execute("SELECT id FROM runs").fetchone()["id"])
    finally:
        conn.close()
    # 模拟上一进程崩溃时该 run 正在执行
    with channel_rig.db.transaction() as tx:
        tx.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))

    assert await channel_rig.assistant.dispatcher.recover_interrupted() == 1
    texts = _delivery_texts(channel_rig, user.user_id)
    assert len(texts) == 1 and "服务中断" in texts[0]


@pytest.mark.asyncio
async def test_completed_empty_reply_delivers_hint(rig) -> None:
    """completed 但空回复：给出可重试提示（对照分支，此前已接通）。"""
    channel_rig, service, user, account = await _setup(
        rig, [RuntimeEvent(kind="completed", payload={"result": {"final_response": "", "completed": True}})]
    )
    await _inbound(channel_rig, account, "说点什么", "m-e")
    await channel_rig.drain_runs()
    texts = _delivery_texts(channel_rig, user.user_id)
    assert len(texts) == 1 and "没有产生可发送的回复" in texts[0]
