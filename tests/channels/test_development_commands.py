"""T5 /开发 命令族：受理幂等、短号解析歧义、补充/取消/重试、回执目标快照。"""
from __future__ import annotations

import uuid


from backend.modules.channels.commands import CommandServices, WeChatCommands
from backend.modules.channels.contracts import InboundMessage
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.superagent.api import SuperagentService
from backend.modules.superagent.intake import SuperagentIntake
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig

REPO_URL = "https://github.com/foo/bar.git"


def _admin(rig):
    return rig.seed_user(role="super_admin", username=f"admin_{uuid.uuid4().hex[:6]}")


def _user(rig, grants=None, revokes=()):
    return rig.seed_user(
        role="user",
        grants=grants if grants is not None else ("superagent.view", "superagent.create", "chat.use"),
        revokes=revokes,
        username=f"u_{uuid.uuid4().hex[:6]}",
    )


def _msg(event_id: str, text: str) -> InboundMessage:
    return InboundMessage(
        platform="wechat", account_pk="chn_acc_1", external_account_id="bot",
        external_user_id="wx_u1", external_chat_id="chat1",
        external_event_id=event_id, text=text, context_token="ctx-9",
    )


def _commands(service: SuperagentService) -> WeChatCommands:
    return WeChatCommands(CommandServices(superagent=SuperagentIntake(service)))


async def _ask(commands, principal, message, session_id="sess1") -> str | None:
    """WeChatCommands.handle 返回 (reply, session_id)；测试只关心回复文本。"""
    result = await commands.handle(principal, message, session_id)
    if result is None:
        return None
    reply, _session = result
    return reply


async def _rig_with_service(rig, *, user_grants=None, user_revokes=()):
    ready = rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)
    rig.db, rig.access = ready.db, ready.access
    service = SuperagentService(ready.db, access=ready.access)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    service.runner_ready = True
    admin = _admin(ready)
    user = _user(ready, grants=user_grants, revokes=user_revokes)
    service.update_settings(admin, enabled=True, repo_url=REPO_URL, base_branch="main",
                            github_token="ghp_t_1234567890123456")
    return service, admin, user


async def test_dev_command_creates_task_with_source_snapshot(rig) -> None:
    service, admin, user = await _rig_with_service(rig)
    commands = _commands(service)
    reply = await _ask(commands, user, _msg("msg:wx_u1:100", "/开发 修复导出 CSV 中文乱码，加回归测试"), "sess1")
    assert reply is not None and "已受理" in reply
    assert "任务号 sag_" in reply
    task = service.list_tasks(user, limit=1)[0]
    assert task.source == "wechat"
    # 回执目标快照：发命令的微信地址
    assert task.source_ref == "wx_u1"
    assert task.source_kind == "wechat"
    assert task.source_channel_account_id == "chn_acc_1"
    assert "修复导出 CSV 中文乱码" in task.requirement


async def test_dev_command_redelivery_is_idempotent(rig) -> None:
    """验收矩阵 2：同一来源事件重复到达，生成一个逻辑任务。"""
    service, admin, user = await _rig_with_service(rig)
    commands = _commands(service)
    first = await _ask(commands, user, _msg("msg:wx_u1:200", "/开发 加个功能"), "sess1")
    second = await _ask(commands, user, _msg("msg:wx_u1:200", "/开发 加个功能"), "sess1")
    assert first == second
    assert len(service.list_tasks(user, limit=10)) == 1


async def test_dev_command_without_permission_rejected(rig) -> None:
    service, admin, user = await _rig_with_service(
        rig, user_grants=("superagent.view", "chat.use"), user_revokes=("superagent.create",),
    )
    commands = _commands(service)
    reply = await _ask(commands, user, _msg("msg:wx_u1:300", "/开发 试试"), "sess1")
    assert "受理失败" in reply


async def test_task_list_and_detail_and_short_id_resolution(rig) -> None:
    service, admin, user = await _rig_with_service(rig)
    commands = _commands(service)
    await _ask(commands, user, _msg("msg:wx_u1:1", "/开发 任务A需求"), "s")
    await _ask(commands, user, _msg("msg:wx_u1:2", "/开发 任务B需求"), "s")
    listing = await _ask(commands, user, _msg("msg:wx_u1:3", "/任务"), "s")
    assert "任务A需求" in listing and "任务B需求" in listing
    task = service.list_tasks(user, limit=1)[0]
    detail = await _ask(commands, user, _msg("msg:wx_u1:4", f"/任务 {task.task_id[-6:]}"), "s")
    assert "状态：排队中" in detail
    assert task.branch in detail


async def test_short_id_ambiguity_lists_candidates(rig) -> None:
    service, admin, user = await _rig_with_service(rig)
    commands = _commands(service)
    await _ask(commands, user, _msg("msg:wx_u1:1", "/开发 X"), "s")
    await _ask(commands, user, _msg("msg:wx_u1:2", "/开发 Y"), "s")
    # 创建足够多的任务，找末位字符真实碰撞的短号（确定性多匹配）
    for n in range(12):
        await _ask(commands, user, _msg(f"msg:wx_u1:{n}", f"/开发 需求{n}"), "s")
    tasks = service.list_tasks(user, limit=50)
    from collections import Counter

    counter = Counter(t.task_id[-1] for t in tasks)
    shared = next((ch for ch, count in counter.items() if count >= 2), None)
    assert shared is not None
    reply = await _ask(commands, user, _msg("msg:wx_u1:99", f"/取消 {shared}"), "s")
    assert "多个匹配" in reply


async def test_supplement_resumes_waiting_input_task(rig) -> None:
    service, admin, user = await _rig_with_service(rig)
    commands = _commands(service)
    await _ask(commands, user, _msg("msg:wx_u1:1", "/开发 需求不明"), "s")
    task = service.list_tasks(user, limit=1)[0]
    service.repo.transition_task(
        task.task_id, from_statuses=frozenset({"queued"}), to_status="waiting_input",
        event_kind="question", event_detail="?",
    )
    reply = await _ask(commands, 
        user, _msg("msg:wx_u1:2", f"/补充 {task.task_id[-6:]} 目标 Python 3.12"), "s",
    )
    assert "已补充" in reply
    assert service.task(task.task_id).status == "queued"
    inputs = service.repo.unconsumed_inputs(task.task_id)
    assert any("3.12" in i.text for i in inputs)
    # 同一事件重放：幂等，不产生第二条补充输入
    await _ask(commands, user, _msg("msg:wx_u1:2", f"/补充 {task.task_id[-6:]} 目标 Python 3.12"), "s")
    supplement_inputs = [i for i in service.repo.unconsumed_inputs(task.task_id)
                         if "3.12" in i.text]
    assert len(supplement_inputs) == 1


async def test_cancel_and_retry_commands(rig) -> None:
    service, admin, user = await _rig_with_service(rig)
    commands = _commands(service)
    await _ask(commands, user, _msg("msg:wx_u1:1", "/开发 要取消的任务"), "s")
    task = service.list_tasks(user, limit=1)[0]
    reply = await _ask(commands, user, _msg("msg:wx_u1:2", f"/取消 {task.task_id[-6:]}"), "s")
    assert "已取消" in reply
    reply = await _ask(commands, user, _msg("msg:wx_u1:3", f"/重试 {task.task_id[-6:]}"), "s")
    assert "重新入队" in reply
    assert service.task(task.task_id).status == "queued"


async def test_non_superagent_command_still_routes(rig) -> None:
    """/开发 族之外的命令不受影响（fallback 到既有命令链）。"""
    service, admin, user = await _rig_with_service(rig)
    commands = _commands(service)
    reply = await _ask(commands, user, _msg("msg:wx_u1:1", "/人设 default"), "s")
    assert reply is not None  # 既有命令正常工作
    unknown = await _ask(commands, user, _msg("msg:wx_u1:2", "/不存在的命令"), "s")
    assert unknown is None


async def test_worker_notifies_persisted_source_address(rig) -> None:
    """多绑定场景：回执发到受理时的来源地址（T5 固定目标）。"""
    from backend.modules.delivery.api import DeliveryService
    from backend.modules.delivery.wechat import DisabledDeliverySender
    from backend.modules.superagent.worker import SuperagentWorker
    from tests.superagent.fakes import FakeGit, FakePRClient, FakeRunner, make_outcome

    ready = rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)
    rig.db, rig.access = ready.db, ready.access
    delivery = DeliveryService(ready.db, sender=DisabledDeliverySender())
    service = SuperagentService(ready.db, access=ready.access, delivery=delivery)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    service.runner_ready = True
    admin = _admin(ready)
    user = _user(ready)
    service.update_settings(admin, enabled=True, repo_url=REPO_URL, base_branch="main",
                            github_token="ghp_t_1234567890123456")
    service.create_task(
        user, title="t", requirement="r", source="wechat",
        idempotency_key="evt-x",
        source_target=DeliveryTarget(kind="wechat", ref="wx_from_cmd", channel_account_id="chn_acc_1"),
    )
    worker = SuperagentWorker(
        service,
        runner=FakeRunner(make_outcome("完成。")),
        delivery=delivery,
        channels_provider=lambda: None,  # 无渠道引用：只能靠任务快照地址
        workspace_root=rig.tmp_path / "ws",
        artifacts_root=rig.tmp_path / "verify",
        pr_client_factory=lambda token: FakePRClient(),
        git_runner=FakeGit(status=" M a.py\n", heads=["a" * 40, "a" * 40, "a" * 40, "c" * 40]),
    )
    worker._helper_path = lambda: str(rig.tmp_path / "helper.py")
    await worker.tick()
    conn = rig.db.connect()
    try:
        rows = conn.execute(
            "SELECT target_ref FROM deliveries WHERE source='superagent'"
        ).fetchall()
    finally:
        conn.close()
    assert [r["target_ref"] for r in rows] == ["wx_from_cmd"]
