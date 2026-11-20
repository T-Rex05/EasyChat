"""角色目录、Web 开聊、微信切换及在途运行的行为契约。"""
from __future__ import annotations

import json

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.modules.assistant.contracts import RunCommand
from backend.modules.assistant.routes import build_web_chat_router
from backend.modules.memory.api import MemoryService
from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.modules.profiles.api import ProfilesService
from backend.modules.profiles.routes import build_profiles_router
from backend.runtime.contracts import RuntimeEvent
from backend.shared.errors import AppError
from tests.support.wechat import inbound, make_channel_rig, text_message


async def test_web_persona_catalog_and_session_ownership(tmp_path):
    rig, _, _ = make_channel_rig(tmp_path)
    try:
        owner = rig.seed_user(grants=("chat.use",))
        other = rig.seed_user(grants=("chat.use",))
        profiles = ProfilesService(rig.db, access=rig.access)
        app = FastAPI()

        @app.exception_handler(AppError)
        async def handle_error(_, exc):
            return JSONResponse(exc.to_payload(), status_code=exc.http_status)

        app.include_router(build_profiles_router(profiles, rig.access.authenticate_token))
        app.include_router(build_web_chat_router(rig.assistant, rig.access.authenticate_token))

        def authorization(actor):
            token = rig.access.create_token(actor.user_id, "test", actor.role)
            return {"Authorization": f"Bearer {token}"}

        owner_headers = authorization(owner)
        other_headers = authorization(other)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            catalog = await client.get("/api/profile/personas", headers=owner_headers)
            assert catalog.status_code == 200
            assert [(p["id"], p["name"]) for p in catalog.json()["personas"]] == [(None, "默认角色")]

            created = await client.post("/api/profile/personas", headers=owner_headers, json={
                "name": "编辑", "instruction": "每次说明修改理由",
            })
            assert created.status_code == 200
            persona = created.json()
            assert persona["version"] == 1
            assert persona["active"] is True

            collision = await client.post("/api/profile/personas", headers=owner_headers, json={
                "name": " 编辑 ", "instruction": "重复角色",
            })
            assert collision.status_code == 409

            hidden = await client.post("/api/history", headers=other_headers, json={"persona_id": persona["id"]})
            assert hidden.status_code == 404
            forbidden_edit = await client.patch(
                f"/api/profile/personas/{persona['id']}", headers=other_headers, json={"active": False},
            )
            assert forbidden_edit.status_code == 404

            default = await client.post("/api/history", headers=owner_headers, json={})
            session = await client.post("/api/history", headers=owner_headers, json={"persona_id": persona["id"]})
            assert session.status_code == 200
            assert session.json()["session_id"] != default.json()["session_id"]
            history = await client.get("/api/history", headers=owner_headers)
            assert {row["persona_id"] for row in history.json()["sessions"]} == {None, persona["id"]}

            # 角色编辑与归档不可改变已入队的提示快照。
            queued = await rig.assistant.submit(RunCommand(
                principal=owner, source="web", session_id=session.json()["session_id"],
                client_message_id="queued", text="请评阅这段文字",
            ))
            edited = await client.patch(
                f"/api/profile/personas/{persona['id']}", headers=owner_headers,
                json={"instruction": "指出一句话的主题"},
            )
            assert edited.json()["version"] == 2
            archived = await client.patch(
                f"/api/profile/personas/{persona['id']}", headers=owner_headers, json={"active": False},
            )
            assert archived.json()["active"] is False
            rejected = await client.post("/api/history", headers=owner_headers, json={"persona_id": persona["id"]})
            assert rejected.status_code == 409
            rejected = await client.post("/chat/stream", headers=owner_headers, json={
                "thread_id": session.json()["session_id"], "client_msg_id": "next", "message": "下一轮",
            })
            assert rejected.status_code == 409

            await rig.start_assistant()
            await rig.drain_runs()
            assert rig.runtime.requests[0].context.run_id == queued.run_id
            assert "每次说明修改理由" in rig.runtime.requests[0].persona_context
            assert "指出一句话的主题" not in rig.runtime.requests[0].persona_context
    finally:
        await rig.aclose()


async def test_wechat_persona_switch_restores_history_and_preserves_queued_route(tmp_path):
    rig, _, _ = make_channel_rig(tmp_path)
    try:
        admin = rig.seed_user(role="super_admin")
        owner = rig.seed_user(grants=("chat.use",))
        successor = rig.seed_user(grants=("chat.use",))
        profiles = ProfilesService(rig.db, access=rig.access)
        rig.channels.profiles = profiles
        profiles.create_persona(owner, name="编辑", instruction="说明每次修改的理由")
        profiles.create_persona(owner, name="老师", instruction="请耐心讲解")
        view = rig.channels.register_account(
            admin, account_id="bot", token="synthetic", base_url="https://ilink.test", bot_user_id="bot-user",
        )
        account = rig.channels.repo.get_account(view.id)

        def bind(actor, external_user="wx_ext_1"):
            return rig.channels.bind_user(
                admin, platform="wechat", account_id=account.account_id,
                external_user_id=external_user, user_id=actor.user_id, account_pk=account.id,
            )

        bind(owner)

        async def send(text, event, token="ctx", external_user="wx_ext_1"):
            return await rig.channels.handle_inbound(inbound(rig, account, text_message(
                text, message_id=event, context_token=token, chat_id="chat", from_user=external_user,
            )))

        catalog = await send("/角色", "roles")
        assert catalog.accepted
        assert "默认角色" in catalog.reply_text
        assert "编辑" in catalog.reply_text
        assert "老师" in catalog.reply_text
        rig.access.set_user_permission(admin, owner.user_id, "chat.use", False)
        replay = await send("/角色", "roles")
        assert replay.duplicate and not replay.reply_text and not replay.session_id
        rig.access.set_user_permission(admin, owner.user_id, "chat.use", True)

        editor = await send("/角色 编辑", "pick-editor")
        assert "记忆范围：角色私有记忆和账号共享记忆" in editor.reply_text
        edit_run = await send("评阅", "edit", token="editor-context")
        teacher = await send("/角色 老师", "pick-teacher")
        assert teacher.session_id != editor.session_id == edit_run.session_id

        run = rig.assistant.repo.get_run(edit_run.run_id)
        target = rig.channels.delivery_target_for_run(run)
        assert target is not None
        assert (target.ref, target.context_token) == ("wx_ext_1", "editor-context")

        resumed = await send("/角色 编辑", "resume-editor")
        assert resumed.session_id == editor.session_id
        fresh = await send("/新对话", "new")
        assert fresh.session_id != editor.session_id
        editor_meta = await rig.assistant.get_session(owner, editor.session_id)
        fresh_meta = await rig.assistant.get_session(owner, fresh.session_id)
        assert editor_meta["persona_id"] == fresh_meta["persona_id"] is not None

        bind(owner, "wx_other")
        other = await send("/角色 编辑", "other-editor", external_user="wx_other")
        assert other.session_id not in {editor.session_id, fresh.session_id}
        switched = await send("/角色 默认角色", "pick-default")
        assert switched.session_id == catalog.session_id

        bind(successor)
        assert rig.channels.delivery_target_for_run(run) is None
        rejected = await send("/角色 编辑", "successor-editor")
        assert "不存在" in rejected.reply_text
        assert rejected.session_id != editor.session_id
    finally:
        await rig.aclose()



async def test_wechat_recall_receipt_uses_current_session_and_explicit_run_prefix(tmp_path):
    rig, _, _ = make_channel_rig(tmp_path)
    try:
        admin = rig.seed_user(role="super_admin")
        owner = rig.seed_user(grants=("chat.use", "memory.view", "memory.edit"))
        view = rig.channels.register_account(
            admin, account_id="bot", token="synthetic", base_url="https://ilink.test", bot_user_id="bot-user",
        )
        account = rig.channels.repo.get_account(view.id)
        rig.channels.bind_user(
            admin, platform="wechat", account_id=account.account_id, external_user_id="wx_ext_1",
            user_id=owner.user_id, account_pk=account.id,
        )

        async def send(text, event):
            return await rig.channels.handle_inbound(inbound(rig, account, text_message(text, message_id=event)))

        memory = MemoryService(rig.db, access=rig.access)
        rig.assistant.dispatcher.memory = memory
        saved = memory.remember(owner, MemoryCandidate(
            kind="preference", content="回复使用中文",
            source_refs=(SourceRef(kind="manual", ref="synthetic-persona"),),
        ))
        rig.runtime.script_events([
            RuntimeEvent(kind="completed", payload={"result": {"final_response": "好的", "completed": True}}),
        ])
        await rig.start_assistant()
        original = await send("回复使用中文", "chat")
        assert original.run_id
        await rig.drain_runs()
        memory.revise(owner, saved.memory_id, saved.version, content="回复使用简体中文")

        receipt = await send(f"/本轮记忆 {original.run_id[:12]}", "recall")
        assert receipt.run_id == ""
        assert "加入本轮请求的记忆" in receipt.reply_text
        assert saved.memory_id in receipt.reply_text
        assert "v1" in receipt.reply_text and "当前 v2" in receipt.reply_text
        assert "回复使用简体中文" in receipt.reply_text
        event = rig.channels.repo.get_event(receipt.event_id)
        assert "reply_text" not in json.loads(event["payload"])

        await send("/新对话", "switch")
        outside_session = await send(f"/本轮记忆 {original.run_id}", "outside")
        assert saved.memory_id not in outside_session.reply_text
        memory.forget(owner, memory_id=saved.memory_id)
        repeated = await send(f"/本轮记忆 {original.run_id[:12]}", "recall")
        assert repeated.duplicate and not repeated.reply_text
        graph = await send("/星图", "graph")
        assert graph.run_id == ""
        assert "记忆管理" in graph.reply_text and "星图" in graph.reply_text
    finally:
        await rig.aclose()


async def test_pending_wechat_event_keeps_first_owner_and_original_payload(tmp_path, monkeypatch):
    rig, _, _ = make_channel_rig(tmp_path)
    try:
        admin = rig.seed_user(role="super_admin")
        first = rig.seed_user(grants=("chat.use",))
        next_owner = rig.seed_user(grants=("chat.use",))
        account = rig.channels.register_account(
            admin, account_id="bot", token="synthetic", base_url="https://ilink.test", bot_user_id="bot-user",
        )
        account = rig.channels.repo.get_account(account.id)

        def bind(actor):
            rig.channels.bind_user(
                admin, platform="wechat", account_id="bot", external_user_id="wx_ext_1",
                user_id=actor.user_id, account_pk=account.id,
            )

        async def send(text, event):
            return await rig.channels.handle_inbound(inbound(rig, account, text_message(text, message_id=event)))

        attempts = set()
        process = rig.channels._process_event

        async def fail_first(account, message, event_id):
            if event_id not in attempts:
                attempts.add(event_id)
                raise RuntimeError("interrupt after inbox commit")
            return await process(account, message, event_id)

        monkeypatch.setattr(rig.channels, "_process_event", fail_first)
        bind(first)
        assert (await send("原始消息", "retry")).reason == "internal"
        retried = await send("改写的重投文本", "retry")
        assert retried.run_id
        assert rig.assistant.repo.get_run(retried.run_id)["input_summary"] == "原始消息"

        assert (await send("换绑前的消息", "rebind")).reason == "internal"
        bind(next_owner)
        assert await rig.channels.replay_due_events(now=rig.clock() + 3600) == 1
        duplicate = await send("换绑前的消息", "rebind")
        assert duplicate.duplicate and not duplicate.run_id and not duplicate.reply_text
        assert not await rig.assistant.list_sessions(next_owner)
    finally:
        await rig.aclose()


async def test_replayed_wechat_navigation_does_not_replace_newer_selection(tmp_path, monkeypatch):
    rig, _, _ = make_channel_rig(tmp_path)
    try:
        admin = rig.seed_user(role="super_admin")
        owner = rig.seed_user(grants=("chat.use",))
        profiles = ProfilesService(rig.db, access=rig.access)
        rig.channels.profiles = profiles
        profiles.create_persona(owner, name="编辑", instruction="说明每次修改的理由")
        profiles.create_persona(owner, name="老师", instruction="请耐心讲解")
        view = rig.channels.register_account(
            admin, account_id="bot", token="synthetic", base_url="https://ilink.test", bot_user_id="bot-user",
        )
        account = rig.channels.repo.get_account(view.id)
        rig.channels.bind_user(
            admin, platform="wechat", account_id="bot", external_user_id="wx_ext_1", user_id=owner.user_id,
            account_pk=account.id,
        )

        async def send(text, event):
            return await rig.channels.handle_inbound(inbound(rig, account, text_message(text, message_id=event)))

        await send("/当前", "default")
        def interrupt(*args, **kwargs):
            raise RuntimeError("interrupt after navigation")

        with monkeypatch.context() as patch:
            patch.setattr(rig.channels.repo, "update_event", interrupt)
            assert (await send("/角色 编辑", "older")).reason == "internal"

        newer = await send("/角色 老师", "newer")
        assert newer.accepted
        assert await rig.channels.replay_due_events(now=rig.clock() + 3600) == 1
        current = await send("/当前", "current")
        assert current.session_id == newer.session_id
    finally:
        await rig.aclose()
