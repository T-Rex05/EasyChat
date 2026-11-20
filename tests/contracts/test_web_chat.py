"""Web 聊天兼容契约测试：旧 /chat/stream 契约 → 统一 Assistant（单循环 httpx ASGI）。"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from backend.modules.assistant.contracts import RunCommand
from backend.modules.assistant.routes import build_web_chat_router
from backend.modules.memory.api import MemoryService
from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.modules.profiles.api import ProfilesService
from backend.shared.errors import AppError
from backend.runtime.contracts import RuntimeEvent
from tests.support.rig import make_rig


def _e(kind, payload):
    return RuntimeEvent(kind=kind, payload=payload)


@pytest.fixture
async def rig(tmp_path):
    r = make_rig(tmp_path, seed_access=True)
    r.attach_assistant()
    await r.start_assistant()
    yield r
    await r.aclose()


def _client(rig) -> httpx.AsyncClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle(_: object, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(
        build_web_chat_router(rig.assistant, rig.access.authenticate_token, rig.access.consume_sse_ticket)
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                             base_url="http://test")


def _auth_headers(rig, user) -> dict:
    return {"Authorization": f"Bearer {_token(rig, user)}"}


def _token(rig, user) -> str:
    return rig.access.create_token(user.user_id, f"user{user.user_id}", user.role)


async def _read_sse(rig, client: httpx.AsyncClient, params: dict, headers: dict | None = None) -> tuple[int, str]:
    async with client.stream("GET", "/chat/stream", params=params, headers=headers or {}) as response:
        chunks = [chunk async for chunk in response.aiter_text()]
        return response.status_code, "".join(chunks)


async def test_run_memory_reports_injected_versions_only_to_owner(rig, monkeypatch):
    grants = ("chat.use", "memory.view", "memory.edit")
    owner = rig.seed_user(grants=grants)
    other = rig.seed_user(grants=grants)
    without_memory = rig.seed_user(grants=("chat.use",), revokes=("memory.view",))
    service = MemoryService(rig.db, access=rig.access)
    rig.assistant.dispatcher.memory = service
    rig.runtime.script_events([
        _e("completed", {"result": {"final_response": "好的", "completed": True}}),
    ])
    memory = service.remember(owner, MemoryCandidate(
        kind="preference", content="喜欢无糖豆浆",
        source_refs=(SourceRef(kind="manual", ref="synthetic"),),
    ))
    session = await rig.seed_session(owner)
    run = await rig.assistant.submit(RunCommand(
        principal=owner, source="web", session_id=session,
        client_message_id="recall-reference", text="无糖豆浆",
    ))
    async for event in rig.assistant.iter_events(owner, run.run_id):
        if event.kind == "completed":
            break
    assert "喜欢无糖豆浆" in rig.runtime.requests[0].context_prefix

    service.revise(owner, memory.memory_id, memory.version, content="改喝温水")
    from backend.bootstrap import make_memory_confirm

    make_memory_confirm(rig.db)(owner.user_id, run.run_id, "已记住")
    url = f"/api/assistant/runs/{run.run_id}/memory"
    async with _client(rig) as client:
        history = await client.get(f"/api/history/{session}", headers=_auth_headers(rig, owner))
        assert [(item["role"], item["run_id"]) for item in history.json()["messages"]] == [
            ("user", run.run_id), ("assistant", run.run_id), ("assistant", None),
        ]
        monkeypatch.setattr(rig.assistant.events, "_ttl", 0)
        assert rig.assistant.events.sweep() == 1
        status, body = await _read_sse(rig, client, {
            "thread_id": session, "client_msg_id": "recall-reference", "message": "无糖豆浆",
        }, headers=_auth_headers(rig, owner))
        assert status == 200 and "stream_reset" in body
        assert "好的" in body and "已记住" not in body
        assert rig.runtime.execute_count == 1
        response = await client.get(url, headers=_auth_headers(rig, owner))
        assert response.status_code == 200
        data = response.json()
        assert data["recorded"] is True
        assert data["items"] == [{
            "memory_id": memory.memory_id, "version": 1, "current_version": 2,
            "kind": "preference", "summary": "改喝温水",
        }]
        assert (await client.get(url, headers=_auth_headers(rig, other))).status_code == 404
        assert (await client.get(url, headers=_auth_headers(rig, without_memory))).status_code == 403
        assert rig.assistant.memory_recall_for_session(owner, session) == data
        service.forget(owner, memory_id=memory.memory_id)
        after = await client.get(url, headers=_auth_headers(rig, owner))
        assert after.json() == {"recorded": True, "items": []}

        empty_session = await rig.seed_session(owner)
        assert rig.assistant.memory_recall_for_session(owner, empty_session) == {
            "recorded": False, "items": [],
        }
        empty_run = await rig.assistant.submit(RunCommand(
            principal=owner, source="web", session_id=empty_session,
            client_message_id="empty-recall", text="无关文字",
        ))
        async for event in rig.assistant.iter_events(owner, empty_run.run_id):
            if event.kind == "completed":
                break
        empty = await client.get(
            f"/api/assistant/runs/{empty_run.run_id}/memory", headers=_auth_headers(rig, owner),
        )
        assert empty.json() == {"recorded": True, "items": []}
        assert (await client.get("/api/assistant/runs/unknown/memory")).status_code == 401


async def test_run_memory_follows_role_and_current_sharing(rig):
    owner = rig.seed_user(grants=("chat.use", "memory.view", "memory.edit"))
    profiles = ProfilesService(rig.db, access=rig.access)
    editor = profiles.create_persona(owner, name="编辑", instruction="检查表达")
    teacher = profiles.create_persona(owner, name="老师", instruction="逐步讲解")
    memory = MemoryService(rig.db, access=rig.access)
    rig.assistant.dispatcher.memory = memory
    rig.runtime.script_events([
        _e("completed", {"result": {"final_response": "好的", "completed": True}}),
    ])
    private = memory.remember(
        owner, MemoryCandidate(kind="preference", content="咖啡只在编辑会话谈论",
                               source_refs=(SourceRef(kind="manual", ref="one"),)),
        persona_id=editor["id"],
    )
    shared = memory.remember(
        owner, MemoryCandidate(kind="preference", content="咖啡不要加糖",
                               source_refs=(SourceRef(kind="manual", ref="two"),)),
        persona_id=teacher["id"], is_shared=True,
    )
    session = await rig.assistant.create_session(owner, persona_id=editor["id"])
    other_session = await rig.assistant.create_session(owner, persona_id=teacher["id"])
    runs = []
    for session_id in (session, other_session):
        run = await rig.assistant.submit(RunCommand(
            principal=owner, source="web", session_id=session_id,
            client_message_id="role-memory", text="咖啡",
        ))
        async for event in rig.assistant.iter_events(owner, run.run_id):
            if event.kind == "completed":
                break
        runs.append(run)

    assert private.content in rig.runtime.requests[0].context_prefix
    assert private.content not in rig.runtime.requests[1].context_prefix
    assert all(shared.content in request.context_prefix for request in rig.runtime.requests)
    memory.set_sharing(owner, shared.memory_id, is_shared=False)
    first = rig.assistant.memory_recall_for_run(owner, runs[0].run_id)
    second = rig.assistant.memory_recall_for_run(owner, runs[1].run_id)
    assert [item["memory_id"] for item in first["items"]] == [private.memory_id]
    assert [item["memory_id"] for item in second["items"]] == [shared.memory_id]


async def test_stream_legacy_thread_id_full_flow(rig):
    user = rig.seed_user(role="user", grants=("chat.use",), username="web_flow")
    rig.runtime.script_events([
        _e("token", {"text": "你好"}),
        _e("token", {"text": "，世界"}),
        _e("completed", {"result": {"final_response": "你好，世界", "completed": True}}),
    ])
    async with _client(rig) as client:
        status, body = await _read_sse(rig, client, {
            "message": "打个招呼", "thread_id": f"{user.user_id}_1700000000",
            "client_msg_id": "web-1",
        }, headers=_auth_headers(rig, user))
    assert status == 200
    assert '"type": "start"' in body
    assert '"type": "token"' in body
    assert '"type": "chat_complete"' in body
    assert "你好，世界" in body  # final_content
    assert "id: " in body  # SSE 续传锚点
    assert "retry: 86400000" in body  # 完成后抑制自动重连
    # 旧 thread_id 已映射为会话（同 id 再提交不新建会话）
    sessions = await rig.assistant.list_sessions(user)
    assert len(sessions) == 1


async def test_busy_conflict_409(rig):
    user = rig.seed_user(role="user", grants=("chat.use",), username="busy409")
    rig.assistant.wait_capacity = 0
    async with _client(rig) as client:
        resp = await client.get("/chat/stream", params={
            "message": "hi", "thread_id": f"{user.user_id}_1", "client_msg_id": "b1",
        }, headers=_auth_headers(rig, user))
    assert resp.status_code == 409
    assert "error" in resp.json()


async def test_cancel_endpoint_marks_cancelled(rig):
    user = rig.seed_user(role="user", grants=("chat.use",), username="cancelweb")
    gate = asyncio.Event()

    async def slow(request):
        yield _e("token", {"text": "x"})
        await gate.wait()
        yield _e("completed", {"result": {"final_response": "", "completed": True}})

    rig.runtime.execute = slow
    session = await rig.assistant.create_session(user, external_chat_id=f"{user.user_id}_9")
    receipt = await rig.assistant.submit(RunCommand(
        principal=user, session_id=session, source="web", client_message_id="c9", text="慢慢来"))
    async with _client(rig) as client:
        resp = await client.post("/chat/cancel", params={
            "thread_id": f"{user.user_id}_9", "client_msg_id": "c9",
        }, headers=_auth_headers(rig, user))
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    gate.set()
    await rig.drain_runs()
    status = await rig.assistant.run_status(user, receipt.run_id)
    assert status["status"] == "cancelled"


async def test_history_endpoints(rig):
    user = rig.seed_user(role="user", grants=("chat.use",), username="hist")
    token = _token(rig, user)
    session = await rig.assistant.create_session(user, external_chat_id=f"{user.user_id}_h", title="标题")
    async with _client(rig) as client:
        headers = {"Authorization": f"Bearer {token}"}
        lst = await client.get("/api/history", headers=headers)
        assert lst.status_code == 200
        assert "sessions" in lst.json() and len(lst.json()["sessions"]) >= 1

        renamed = await client.put(f"/api/history/{session}", json={"title": "新标题"}, headers=headers)
        assert renamed.status_code == 200

        detail = await client.get(f"/api/history/{session}", headers=headers)
        assert detail.status_code == 200
        assert "messages" in detail.json()

        deleted = await client.delete(f"/api/history/{session}", headers=headers)
        assert deleted.status_code == 200

        other = rig.seed_user(role="user", grants=("chat.use",), username="hist2")
        hidden = await client.get(f"/api/history/{session}",
                                  headers={"Authorization": f"Bearer {_token(rig, other)}"})
        assert hidden.status_code in (403, 404)


async def test_unauthenticated_stream_rejected(rig):
    async with _client(rig) as client:
        resp = await client.get("/chat/stream", params={"message": "hi", "thread_id": "1_1"})
    assert resp.status_code == 401


async def test_stream_ticket_flow_single_use(rig):
    """审计 #3：URL 上只允许秒级一次性 ticket；单次消费，重放 401。"""
    user = rig.seed_user(role="user", grants=("chat.use",), username="ticket_flow")
    rig.runtime.script_events([
        _e("completed", {"result": {"final_response": "完成", "completed": True}}),
    ])
    ticket = rig.access.issue_sse_ticket(user.user_id)
    async with _client(rig) as client:
        status, body = await _read_sse(rig, client, {
            "message": "hi", "thread_id": f"{user.user_id}_2001", "client_msg_id": "tk1",
            "ticket": ticket,
        })
        assert status == 200
        assert '"type": "chat_complete"' in body
        # 同一 ticket 已被消费：重放必须 401
        status, _ = await _read_sse(rig, client, {
            "message": "hi", "thread_id": f"{user.user_id}_2001", "ticket": ticket,
        })
        assert status == 401


async def test_stream_rejects_token_query_and_bad_ticket(rig):
    """审计 #3：长效 JWT 查询参数已移除；伪造/过期 ticket 401。"""
    user = rig.seed_user(role="user", grants=("chat.use",), username="no_url_token")
    token = _token(rig, user)
    async with _client(rig) as client:
        status, _ = await _read_sse(rig, client, {
            "message": "hi", "thread_id": f"{user.user_id}_2002", "token": token,
        })
        assert status == 401
        status, _ = await _read_sse(rig, client, {
            "message": "hi", "thread_id": f"{user.user_id}_2002", "ticket": "bogus",
        })
        assert status == 401


async def test_stream_reconnect_resumes_last_seq_without_rerun(rig):
    """11-14 P1 回归：受控重连=新 ticket+原 client_msg_id+last_seq 游标。

    后端按 client_message_id 幂等命中原 run（不二次执行模型），
    last_seq 表示最后已收 seq——续传从 N+1 开始，不重复回放旧帧。
    """
    user = rig.seed_user(role="user", grants=("chat.use",), username="reconnect_seq")
    rig.runtime.script_events([
        _e("token", {"text": "甲"}),
        _e("token", {"text": "乙"}),
        _e("completed", {"result": {"final_response": "甲乙", "completed": True}}),
    ])
    thread = f"{user.user_id}_2100"
    async with _client(rig) as client:
        t1 = rig.access.issue_sse_ticket(user.user_id)
        status, body = await _read_sse(rig, client, {
            "message": "hi", "thread_id": thread, "client_msg_id": "rcm-1", "ticket": t1,
        })
        assert status == 200
        assert '"type": "chat_complete"' in body
        assert rig.runtime.execute_count == 1

        # 受控重连：新 ticket、同一逻辑请求标识、游标停在第一个 token 之后
        t2 = rig.access.issue_sse_ticket(user.user_id)
        status2, body2 = await _read_sse(rig, client, {
            "message": "hi", "thread_id": thread, "client_msg_id": "rcm-1",
            "ticket": t2, "last_seq": "1",
        })
        assert status2 == 200
        assert rig.runtime.execute_count == 1, "重连不得触发第二次模型执行"
        # 已收的 seq=1 帧（甲）不回放；仅续传其后内容。run 已 completed，
        # 完成帧无 id，续传以持久终态呈现（幂等，不重复执行）。
        assert ("\"content\": \"甲\"" not in body2)
