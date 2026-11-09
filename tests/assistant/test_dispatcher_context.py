"""RunDispatcher：可信 Principal、人格/时间/附件/记忆上下文与持久 system prompt 隔离。"""
from __future__ import annotations


import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.modules.profiles.api import ProfilesService
from backend.shared.errors import ForbiddenError
from tests.support.rig import make_rig


async def _run_for(rig, principal, text: str = "你好", source: str = "wechat"):
    session_id = await rig.assistant.create_session(principal, source=source)
    receipt = await rig.assistant.submit(
        RunCommand(
            principal=principal,
            session_id=session_id,
            source=source,
            client_message_id=f"msg-{text}",
            text=text,
        )
    )
    return rig.assistant.repo.get_run(receipt.run_id)


@pytest.mark.asyncio
async def test_build_request_uses_snapshot_principal_for_each_role(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    for role in ("user", "admin"):
        principal = rig.seed_user(role=role)
        run = await _run_for(rig, principal)
        request = rig.assistant.dispatcher._build_request(run)
        assert request.context.principal.user_id == principal.user_id
        assert request.context.principal.role == role
        assert request.persist_user_message == "你好"


@pytest.mark.asyncio
async def test_disabled_user_is_rejected_not_defaulted(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()
    run = await _run_for(rig, principal)
    with rig.db.transaction() as conn:
        conn.execute("UPDATE users SET status=0 WHERE id=?", (principal.user_id,))
    rig.access.invalidate_all()
    with pytest.raises(ForbiddenError):
        rig.assistant.dispatcher._build_request(run)


@pytest.mark.asyncio
async def test_persona_time_attachment_and_memory_prefix(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    profiles = ProfilesService(rig.db, access=rig.access, clock=rig.clock)
    rig.assistant.dispatcher.profiles = profiles
    principal = rig.seed_user()
    await rig.assistant.create_session(principal, source="wechat")
    run = await _run_for(rig, principal, source="wechat")

    profiles.update(principal, persona_preset="concise", address_form="您")
    request = rig.assistant.dispatcher._build_request(run)
    assert "直接给结论" in request.persona_context
    assert "称呼用户为「您」" in request.persona_context
    assert "【当前】" in request.context_prefix
    assert "Asia/Shanghai" in request.context_prefix


@pytest.mark.asyncio
async def test_memory_recall_failure_does_not_block_request(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()

    class BrokenMemory:
        def recall(self, *args, **kwargs):
            raise RuntimeError("db down")

    rig.assistant.dispatcher.memory = BrokenMemory()
    run = await _run_for(rig, principal)
    request = rig.assistant.dispatcher._build_request(run)
    assert request.text == "你好"
    assert "记忆" not in request.context_prefix


@pytest.mark.asyncio
async def test_attachment_metadata_uses_stored_file_id_only_when_present(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    rig.attach_assistant()
    principal = rig.seed_user()
    session_id = await rig.assistant.create_session(principal, source="wechat")
    att1 = await rig.assistant.register_attachment(
        principal, file_name="账单.xlsx", file_path="/tmp/a", stored_file_id="fil_" + "a" * 32,
    )
    att2 = await rig.assistant.register_attachment(
        principal, file_name="旧附件.pdf", file_path="/tmp/b",
    )
    receipt = await rig.assistant.submit(
        RunCommand(
            principal=principal, session_id=session_id, source="wechat",
            client_message_id="att-msg", text="看文件", attachment_ids=(att1, att2),
        )
    )
    run = rig.assistant.repo.get_run(receipt.run_id)
    request = rig.assistant.dispatcher._build_request(run)
    assert f"attachment_id={att1}" in request.context_prefix
    assert f"file_id=fil_{'a' * 32}" in request.context_prefix
    assert att2 in request.context_prefix
    assert request.context_prefix.count("file_id=") == 1
