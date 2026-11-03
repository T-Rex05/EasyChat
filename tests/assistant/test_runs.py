"""Assistant run 生命周期测试：幂等/隔离/串行/busy/取消/重启对账（FakeRuntime）。"""
from __future__ import annotations

import asyncio

import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.shared.errors import BusyError, ForbiddenError, InvalidInputError, NotFoundError
from tests.support.rig import make_rig


@pytest.fixture
async def rig(tmp_path):
    r = make_rig(tmp_path, seed_access=True)
    r.attach_assistant()
    await r.start_assistant()
    yield r
    await r.aclose()


def _cmd(principal, session_id, msg_id, text="你好"):
    return RunCommand(principal=principal, session_id=session_id, source="web",
                      client_message_id=msg_id, text=text)


async def test_duplicate_submit_runs_once(rig):
    user = rig.seed_user(role="user", grants=("chat.use",))
    session = await rig.seed_session(user)
    first = await rig.assistant.submit(_cmd(user, session, "msg-1"))
    second = await rig.assistant.submit(_cmd(user, session, "msg-1"))
    assert first.run_id == second.run_id
    assert second.duplicate is True
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1  # 幂等：不重跑


async def test_final_status_and_projection(rig):
    user = rig.seed_user(role="user", grants=("chat.use",))
    session = await rig.seed_session(user)
    rig.runtime.script_events([
        _e("token", {"text": "回复内容"}),
        _e("completed", {"result": {"final_response": "回复内容", "completed": True}}),
    ])
    receipt = await rig.assistant.submit(_cmd(user, session, "m1", "问题"))
    await rig.drain_runs()
    status = await rig.assistant.run_status(user, receipt.run_id)
    assert status["status"] == "completed"
    messages = await rig.assistant.session_messages(user, session)
    roles = [(m["role"], m["content"]) for m in messages]
    assert ("user", "问题") in roles
    assert ("assistant", "回复内容") in roles


def _e(kind, payload):
    from backend.runtime.contracts import RuntimeEvent

    return RuntimeEvent(kind=kind, payload=payload)


async def test_different_user_cannot_access_run(rig):
    alice = rig.seed_user(role="user", grants=("chat.use",), username="alice_r6")
    mallory = rig.seed_user(role="user", grants=("chat.use",), username="mallory_r6")
    session = await rig.seed_session(alice)
    receipt = await rig.assistant.submit(_cmd(alice, session, "secret-msg"))
    with pytest.raises(NotFoundError):
        await rig.assistant.run_status(mallory, receipt.run_id)
    with pytest.raises(NotFoundError):
        rig.assistant.iter_events(mallory, receipt.run_id)
    with pytest.raises(NotFoundError):
        await rig.assistant.cancel(mallory, receipt.run_id)
    await rig.drain_runs()


async def test_same_session_messages_execute_fifo(rig):
    user = rig.seed_user(role="user", grants=("chat.use",))
    session = await rig.seed_session(user)

    async def runner_gen(req):
        rig.runtime.execute_count += 1
        rig.runtime.requests.append(req)
        yield _e("completed", {"result": {"final_response": req.text, "completed": True}})

    # 直接替换 runtime.execute 观察顺序
    order: list[str] = []
    original = rig.runtime.execute

    async def ordered_execute(request):
        order.append(request.text)
        async for evt in original(request):
            yield evt

    rig.runtime.execute = ordered_execute
    await rig.assistant.submit(_cmd(user, session, "m1", "第一条"))
    await rig.assistant.submit(_cmd(user, session, "m2", "第二条"))
    await rig.drain_runs()
    assert order == ["第一条", "第二条"]  # 单worker FIFO，同会话顺序稳定


async def test_queue_full_is_busy(rig):
    user = rig.seed_user(role="user", grants=("chat.use",), username="busy_user")
    session = await rig.seed_session(user)
    rig.assistant.wait_capacity = 0  # 队列容量0：任何提交都busy
    with pytest.raises(BusyError):
        await rig.assistant.submit(_cmd(user, session, "m1"))


async def test_cancel_queued_run_never_executes(rig):
    user = rig.seed_user(role="user", grants=("chat.use",), username="cancelq")
    session = await rig.seed_session(user)
    gate = asyncio.Event()

    async def gated_execute(request):
        await gate.wait()
        rig.runtime.execute_count += 1
        yield _e("completed", {"result": {"final_response": "", "completed": True}})

    rig.runtime.execute = gated_execute
    receipt = await rig.assistant.submit(_cmd(user, session, "m1"))
    cancelled = await rig.assistant.cancel(user, receipt.run_id)
    assert cancelled is True
    await rig.drain_runs()
    status = await rig.assistant.run_status(user, receipt.run_id)
    assert status["status"] == "cancelled"
    # gate释放后也不再执行
    gate.set()
    await asyncio.sleep(0.05)
    status_again = await rig.assistant.run_status(user, receipt.run_id)
    assert status_again["status"] == "cancelled"  # cancelled 不被 completed 覆盖


async def test_cancel_running_calls_runtime_cancel(rig):
    user = rig.seed_user(role="user", grants=("chat.use",), username="cancelr")
    session = await rig.seed_session(user)
    release = asyncio.Event()

    async def long_execute(request):
        yield _e("token", {"text": "开始"})
        await release.wait()
        yield _e("completed", {"result": {"final_response": "", "completed": True}})

    rig.runtime.execute = long_execute
    receipt = await rig.assistant.submit(_cmd(user, session, "m1"))
    await asyncio.sleep(0.15)  # 等待进入 running
    cancelled = await rig.assistant.cancel(user, receipt.run_id)
    assert cancelled is True
    assert len(rig.runtime.cancelled) == 1  # runtime.cancel 已调用
    release.set()
    await rig.drain_runs()
    status = await rig.assistant.run_status(user, receipt.run_id)
    assert status["status"] == "cancelled"  # 完成事件在取消后到达也落 cancelled


async def test_restart_recovers_interrupted(rig):
    """进程重启：遗留 running 标 interrupted，事件流收到 interrupted，不重跑。"""
    user = rig.seed_user(role="user", grants=("chat.use",), username="restart")
    session = await rig.seed_session(user)
    now = "2026-01-01T00:00:00Z"
    from backend.modules.assistant.repository import RUN_RUNNING

    with rig.db.transaction() as conn:
        conn.execute(
            "INSERT INTO runs(id, owner_id, session_id, source, channel_account_scope, "
            "client_message_id, status, input_summary, created_at) "
            "VALUES('run_' || replace(hex(randomblob(16)),'',''),?,?, 'web','','legacy-1', ?, '遗留', ?)",
            (user.user_id, session, RUN_RUNNING, now),
        )
    row = rig.db.connect()
    rid = row.execute("SELECT id FROM runs WHERE client_message_id='legacy-1'").fetchone()["id"]
    row.close()

    # 重建 dispatcher（模拟重启）
    await rig.assistant.aclose()
    rig.attach_assistant()
    await rig.start_assistant()
    await rig.drain_runs()
    status = await rig.assistant.run_status(user, rid)
    assert status["status"] == "interrupted"


async def test_submit_validations(rig):
    user = rig.seed_user(role="user", revokes=("chat.use",), username="novchat")  # 显式撤销chat.use
    session = await rig.seed_session(user)
    with pytest.raises(ForbiddenError):
        await rig.assistant.submit(_cmd(user, session, "m1"))
    member = rig.seed_user(role="user", grants=("chat.use",), username="withchat")
    with pytest.raises(NotFoundError):
        await rig.assistant.submit(_cmd(member, session, "m1"))  # 他人会话
    own = await rig.seed_session(member)
    with pytest.raises(InvalidInputError):
        await rig.assistant.submit(_cmd(member, own, "m1", "  "))  # 空消息
    with pytest.raises(InvalidInputError):
        await rig.assistant.submit(_cmd(member, own, ""))  # 缺client_message_id
