"""Web 聊天兼容契约测试：旧 /chat/stream 契约 → 统一 Assistant（单循环 httpx ASGI）。"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from backend.modules.assistant.contracts import RunCommand
from backend.modules.assistant.routes import build_web_chat_router
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
