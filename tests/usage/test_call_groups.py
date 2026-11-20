"""最近调用按本人会话聚合后分页，并独立分页读取会话内调用。"""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.modules.usage.api import UsageService
from backend.modules.usage.routes import build_usage_router
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import AppError, ForbiddenError


@pytest.mark.asyncio
async def test_groups_and_calls_are_paged_by_owner_and_message_time(tmp_path):
    db = Database(tmp_path / "usage.db")
    db.migrate()
    actor = Principal(user_id=7, role="super_admin", permission_revision=0)
    grants = {"trace.view"}
    service = UsageService(db, effective_permissions=lambda _: frozenset(grants))
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(id,username,password,email,created_at,updated_at) "
            "VALUES(7,'owner','x','owner@example.invalid','2026-11-01','2026-11-01')"
        )
        conn.execute(
            "INSERT INTO sessions(id,owner_id,title,source,created_at,updated_at) "
            "VALUES('b',7,'季度预算','wechat','2026-11-01','2026-12-01'),"
            "('a',7,'','web','2026-11-01','2026-11-01')"
        )
        conn.executemany(
            "INSERT INTO llm_calls(call_id, owner_id, session_id, source, created_at, "
            "prompt_tokens, completion_tokens, total_tokens) VALUES(?,?,?,'chat',?,10,2,12)",
            [(f"c-{i:03}", 7, "a", "2026-11-01") for i in range(52)]
            + [("other-b", 7, "b", "2026-11-12"), ("other-c", 7, "c", "2026-11-11"),
               ("null", 7, None, "2026-11-08"), ("empty", 7, "", "2026-11-08"),
               ("foreign", 8, "a", "2026-12-10")],
        )
        conn.execute(
            "INSERT INTO runs(id,owner_id,session_id,source,client_message_id,created_at) "
            "VALUES('web-reply',7,'b','web','reply','2026-11-12')"
        )
        conn.execute("UPDATE llm_calls SET run_id='web-reply' WHERE call_id='other-b'")
        conn.executemany(
            "INSERT INTO conversations(owner_id,session_id,role,content,status,created_at,updated_at) "
            "VALUES(?,?,'user',?,?,?,'2027-01-01')",
            [(7, "a", "第一份计划", 1, "2026-11-02"), (7, "a", "调整计划", 1, "2026-11-16"),
             (7, "b", "预算", 1, "2026-11-15"), (7, "c", "进度", 1, "2026-11-15"),
             (7, "b", "更早的消息", 1, "2026-11-15T03:00:00+08:00"),
             (7, "b", "隐藏", 0, "2026-12-01"), (8, "b", "private", 1, "2026-12-21")],
        )
    page = service.my_call_groups(actor, limit=2, offset=0)
    assert [g["session_id"] for g in page["groups"]] == ["a", "b"]
    b = page["groups"][1]
    assert (b["title"], b["last_message_at"]) == ("季度预算", "2026-11-15")
    assert b["channel"] == "wechat"
    assert service.my_group_calls(actor, session_id="b", limit=5, offset=0)[0]["channel"] == "web"
    assert page["has_more"]
    a = page["groups"][0]
    assert a["channel"] == "web"
    assert a["preview"] == "调整计划"
    assert (a["title"], a["last_message_at"]) == ("第一份计划", "2026-11-16")
    assert (a["call_count"], a["input_tokens"], a["output_tokens"], a["total_tokens"]) == (52, 520, 104, 624)
    page = service.my_call_groups(actor, limit=2, offset=2)
    assert [g["session_id"] for g in page["groups"]] == ["c", None]
    assert not page["has_more"]
    assert (page["groups"][1]["last_message_at"], page["groups"][1]["call_count"]) == (None, 2)
    rows = service.my_group_calls(actor, session_id="a", limit=50, offset=50)
    assert [r["call_id"] for r in rows] == ["c-001", "c-000"]
    assert {r["call_id"] for r in service.my_group_calls(actor, session_id=None, limit=5, offset=0)} == {"empty", "null"}
    ordinary = Principal(user_id=7, role="user", permission_revision=0)
    assert service.my_call_groups(ordinary, limit=10, offset=0)["groups"]
    grants.clear()
    with pytest.raises(ForbiddenError):
        service.my_call_groups(ordinary, limit=10, offset=0)
    with pytest.raises(ForbiddenError):
        service.my_group_calls(ordinary, session_id="a", limit=10, offset=0)
    grants.add("trace.manage")
    assert service.global_call_groups(ordinary, owner_id=8, limit=10, offset=0)["groups"]
    assert service.global_group_calls(ordinary, owner_id=8, session_id="a", limit=10, offset=0)
    grants.remove("trace.manage")
    grants.add("trace.view")
    with pytest.raises(ForbiddenError):
        service.global_call_groups(ordinary, owner_id=7, limit=10, offset=0)
    with pytest.raises(ForbiddenError):
        service.global_group_calls(ordinary, owner_id=7, session_id="a", limit=10, offset=0)
    global_page = service.global_call_groups(actor, owner_id=None, limit=2, offset=0)
    foreign, own = global_page["groups"]
    assert global_page["has_more"]
    assert (foreign["owner_id"], foreign["session_id"], foreign["channel"], foreign["call_count"]) == (8, "a", None, 1)
    assert foreign["preview"] is None
    assert (own["owner_id"], own["session_id"], own["username"], own["channel"]) == (7, "a", "owner", "web")
    assert [g["owner_id"] for g in service.global_call_groups(actor, owner_id=8, limit=10, offset=0)["groups"]] == [8]
    assert [r["call_id"] for r in service.global_group_calls(actor, owner_id=8, session_id="a", limit=10, offset=0)] == ["foreign"]

    app = FastAPI()
    app.include_router(build_usage_router(service, lambda _: ordinary))

    @app.exception_handler(AppError)
    async def handle_error(_, error: AppError):
        return JSONResponse(error.to_payload(), status_code=error.http_status)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer test"}
        groups_url = "/api/usage/call-groups"
        calls_url = "/api/usage/group-calls"
        params = {"owner_id": 8, "session_id": "a"}
        assert (await client.get(groups_url, headers=headers, params={"owner_id": 8})).status_code == 403
        assert (await client.get(calls_url, headers=headers, params=params)).status_code == 403
        grants.add("trace.manage")
        result = await client.get(groups_url, headers=headers, params={"owner_id": 8})
        assert result.status_code == 200
        assert result.headers["Cache-Control"] == "no-store"
        assert [group["owner_id"] for group in result.json()["groups"]] == [8]
        calls = await client.get(calls_url, headers=headers, params=params)
        assert calls.status_code == 200
        assert [call["call_id"] for call in calls.json()] == ["foreign"]
    db.close()
