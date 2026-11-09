"""Offline upload compatibility with managed files and owned run attachments."""
import base64

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.modules.assistant.compat import build_assistant_compat_router
from backend.modules.assistant.routes import build_web_chat_router
from backend.runtime.contracts import RuntimeEvent
from backend.shared.errors import AppError
from tests.support.rig import make_rig


@pytest.fixture
async def uploads(tmp_path):
    rig = make_rig(tmp_path, seed_access=True)
    rig.attach_files()
    rig.attach_assistant()
    await rig.start_assistant()
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle(_, exc):
        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(build_assistant_compat_router(
        rig.access.authenticate_token, rig.assistant, rig.files,
    ))
    app.include_router(build_web_chat_router(rig.assistant, rig.access.authenticate_token))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield rig, client
    await rig.aclose()


def auth(rig, user):
    return {"Authorization": "Bearer " + rig.access.create_token(user.user_id, "offline", user.role)}


async def test_file_upload_is_registered_and_sent_as_owned_attachment(uploads):
    rig, client = uploads
    user = rig.seed_user(username="upload_owner")
    headers = auth(rig, user)
    response = await client.post("/api/chat/upload-files", headers=headers,
                                 files={"files": ("note.txt", b"offline note", "text/plain")})
    assert response.status_code == 200
    uploaded = response.json()["files"][0]
    attachment = await rig.assistant.get_attachment(user, uploaded["attachment_id"])
    assert attachment["stored_file_id"] == uploaded["file_id"]
    assert rig.files.get(user, uploaded["file_id"]).size_bytes == 12
    rig.runtime.script_events([RuntimeEvent("completed", {"result": {"final_response": "saved"}})])
    sent = await client.post("/chat/stream", headers=headers, json={
        "message": "", "thread_id": f"{user.user_id}_123", "client_msg_id": "upload-run",
        "attachment_ids": [uploaded["attachment_id"]],
    })
    assert sent.status_code == 200
    assert rig.runtime.requests[-1].attachment_ids == (uploaded["attachment_id"],)
    assert uploaded["file_id"] in rig.runtime.requests[-1].context_prefix
    other = rig.seed_user(username="upload_other")
    denied = await client.post("/chat/stream", headers=auth(rig, other), json={
        "message": "read", "thread_id": f"{other.user_id}_123",
        "attachment_ids": [uploaded["attachment_id"]],
    })
    assert denied.status_code == 404


async def test_image_upload_validates_content_and_preserves_preview(uploads):
    rig, client = uploads
    user = rig.seed_user(username="image_owner")
    headers = auth(rig, user)
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9X8AAAAASUVORK5CYII=")
    response = await client.post("/api/chat/upload-images", headers=headers,
                                 files={"files": ("test.png", png, "image/png")})
    assert response.status_code == 200
    image = response.json()["images"][0]
    assert image["data_url"] == "data:image/png;base64," + base64.b64encode(png).decode()
    assert image["attachment_id"]
    invalid = await client.post("/api/chat/upload-images", headers=headers,
                                files={"files": ("fake.png", b"plain text", "image/png")})
    assert invalid.status_code == 422
    rig.files.store.max_bytes = 4
    oversized = await client.post("/api/chat/upload-files", headers=headers,
                                  files={"files": ("big.txt", b"too large", "text/plain")})
    assert oversized.status_code == 422
    assert (await client.post("/api/chat/upload-files", files={"files": ("x.txt", b"x")})).status_code == 401
