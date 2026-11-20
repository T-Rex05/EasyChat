from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.modules.channels.commands import CommandServices, WeChatCommands
from backend.modules.channels.contracts import InboundMessage
from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.modules.memory.routes import build_memory_router
from backend.modules.memory.worker import MemoryWorker
from backend.modules.profiles.api import ProfilesService
from backend.platform.jobs import JobQueue
from backend.shared.errors import AppError
from tests.memory.helpers import make_memory_rig, owner_a, owner_b


@pytest.fixture
def env(tmp_path):
    rig, service = make_memory_rig(tmp_path)
    user = owner_a(rig)
    yield rig, service, user
    rig.db.close()


def _candidate(text):
    return MemoryCandidate(kind="fact", content=text, source_refs=(SourceRef("message", "original"),))


async def test_memory_detail_and_revisions_http_are_owner_scoped(env):
    rig, service, user = env
    other = owner_b(rig)
    no_view = rig.seed_user(
        role="user", grants=("memory.edit",), revokes=("memory.view",), username="memory_no_view",
    )
    hidden = service.remember(no_view, _candidate("无阅读权限的记录"))
    record = service.remember(user, _candidate("原始信息"))
    service.revise(user, record.memory_id, 1, content="修订信息")
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle(_, exc):
        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(build_memory_router(service, rig.access.authenticate_token))

    def headers(principal):
        token = rig.access.create_token(principal.user_id, f"u{principal.user_id}", principal.role)
        return {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/memory/{record.memory_id[:12]}"
        response = await client.get(path, headers=headers(user))
        assert response.status_code == 200
        assert response.json()["memory"]["content"] == "修订信息"
        response = await client.get(f"{path}/revisions?limit=1&offset=1", headers=headers(user))
        assert response.status_code == 200
        assert [item["version"] for item in response.json()["revisions"]] == [2]
        assert (await client.get(path, headers=headers(other))).status_code == 404
        assert (await client.get(f"{path}/revisions", headers=headers(no_view))).status_code == 403
        update = await client.put(f"/api/memory/{hidden.memory_id}", headers=headers(no_view), json={
            "expected_version": 1, "content": "试图读取来源",
        })
        assert update.status_code == 403
        create = await client.post("/api/memory/remember", headers=headers(no_view), json={
            "kind": "fact", "content": hidden.content,
            "source_refs": [{"ref": "original"}],
        })
        assert create.status_code == 403
        service.forget(user, memory_id=record.memory_id)
        assert (await client.get(path, headers=headers(user))).status_code == 404
        assert (await client.get(f"{path}/revisions", headers=headers(user))).status_code == 404


async def test_wechat_revision_replays_original_receipt_and_preserves_multiline_content(env):
    rig, service, user = env
    record = service.remember(user, _candidate("旧偏好"))
    short = record.memory_id[:12]

    async def send(text, event_id):
        message = InboundMessage("wechat", "account", "bot", "user", "chat", event_id, text=text)
        commands = WeChatCommands(CommandServices(memory=service))
        result = await commands.handle(user, message, "session", event_id=event_id)
        assert result is not None
        return result[0]

    assert "旧偏好" in await send(f"/记忆 {short}", "evt-read")
    assert f"/纠正 {short}@1" in await send(f"/纠正 {short}", "evt-help")
    correction = f"/纠正 {short}@1 第一行  保留空格\n第二行"
    receipt = await send(correction, "evt-revise")
    assert "已纠正" in receipt and "2" in receipt
    assert "版本已变化" in await send(f"/纠正 {short}@1 独立事件", "evt-stale")
    assert service.repo.get(record.memory_id).content == "第一行  保留空格\n第二行"
    service.revise(user, record.memory_id, 2, content="第三版")
    commands = WeChatCommands(CommandServices(memory=service))
    assert commands.previous_memory_correction(user, "evt-revise", persona_id=None) == receipt
    assert commands.previous_memory_correction(owner_b(rig), "evt-revise", persona_id=None) is None
    assert await send(correction, "evt-revise") == receipt
    assert [r["version"] for r in service.repo.revisions(record.memory_id)] == [1, 2, 3]
    service.forget(user, memory_id=record.memory_id)
    assert commands.previous_memory_correction(user, "evt-revise", persona_id=None) is None
    replay_after_forget = await send(correction, "evt-revise")
    assert "不存在" in replay_after_forget and "第一行" not in replay_after_forget

def test_namespaces_isolate_writes_recall_and_supersession(env):
    rig, service, user = env
    profile = ProfilesService(rig.db, access=rig.access)
    persona_id = profile.create_persona(user, name="角色", instruction="记忆偏好")["id"]
    default = service.remember(user, _candidate("共用字词 默认或角色"))
    role = service.remember(user, _candidate("共用字词 默认或角色"), persona_id=persona_id)
    shared = service.remember(user, _candidate("共用字词 共享"), is_shared=True)
    assert role.memory_id != default.memory_id
    assert {item.memory.memory_id for item in service.recall(user, "共用字词").items} == {
        default.memory_id, shared.memory_id,
    }
    assert {item.memory.memory_id for item in service.recall(user, "共用字词", persona_id=persona_id).items} == {
        role.memory_id, shared.memory_id,
    }
    with pytest.raises(AppError) as exc:
        service.remember(user, MemoryCandidate(
            kind="fact", content="跨角色替代", source_refs=(SourceRef("message", "new"),),
            supersedes=default.memory_id,
        ), persona_id=persona_id)
    assert exc.value.http_status == 404
    assert service.repo.get(default.memory_id).status == "active"

async def test_capture_uses_run_persona_and_stops_after_archive(env):
    rig, service, user = env
    profiles = ProfilesService(rig.db, access=rig.access)
    persona_id = profiles.create_persona(user, name="健身", instruction="记录运动偏好")["id"]
    texts = {"run-one": "记住：我喜欢游泳", "run-two": "记住：我喜欢远足"}
    worker = MemoryWorker(
        service, JobQueue(rig.db),
        message_loader=lambda owner, run_id: [{"role": "user", "content": texts[run_id]}],
    )

    def enqueue(run_id):
        with rig.db.transaction() as conn:
            return worker.enqueue_capture_tx(conn, {
                "id": run_id, "owner_id": user.user_id, "source": "web",
                "status": "completed", "persona_id": persona_id,
            })

    assert enqueue("run-one")
    assert await worker.tick() == 1
    assert service.list(user, all_personas=False) == []
    records = service.list(user, persona_id=persona_id, all_personas=False)
    assert [record.content for record in records] == ["我喜欢游泳"]

    assert enqueue("run-two")
    profiles.update_persona(user, persona_id, active=False)
    assert await worker.tick() == 1
    assert [record.content for record in service.list(user)] == ["我喜欢游泳"]
    assert service.list(user, persona_id=persona_id, all_personas=False) == []
