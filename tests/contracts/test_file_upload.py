"""F3：Web 上传/下载 HTTP 契约（显式路由 + 鉴权 + 不暴露内部路径）。"""
from __future__ import annotations

import hashlib

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.modules.files.routes import build_files_router
from backend.shared.errors import AppError
from tests.files.helpers import make_files_rig


def _client(rig) -> httpx.AsyncClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle(_: object, exc: AppError):
        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(build_files_router(rig.files, rig.access.authenticate_token))
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
    )


def _auth(rig, user) -> dict[str, str]:
    token = rig.access.create_token(user.user_id, f"user{user.user_id}", user.role)
    return {"Authorization": f"Bearer {token}"}


async def test_upload_download_roundtrip(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        payload = b"date,amount\n2026-10-02,10.00\n"
        async with _client(rig) as client:
            response = await client.post(
                "/api/files",
                files={"file": ("合成 账单.csv", payload, "text/csv")},
                data={"request_id": "web-req-1"},
                headers=_auth(rig, user),
            )
        assert response.status_code == 200, response.text
        body = response.json()
        file_id = body["file"]["file_id"]
        assert body["file"]["sha256"] == hashlib.sha256(payload).hexdigest()
        assert body["file"]["status"] == "ready"
        # 响应不含物理路径/存储键
        assert "storage_key" not in response.text
        assert str(tmp_path) not in response.text

        async with _client(rig) as client:
            meta = await client.get(f"/api/files/{file_id}", headers=_auth(rig, user))
            assert meta.status_code == 200
            assert meta.json()["file"]["original_name"] == "合成 账单.csv"
            download = await client.get(
                f"/api/files/{file_id}/content", headers=_auth(rig, user),
            )
        assert download.status_code == 200
        assert download.content == payload
        assert "filename*=UTF-8''" in download.headers["content-disposition"]
        assert download.headers["x-content-type-options"] == "nosniff"
        assert download.headers["cache-control"] == "private, no-store"
    finally:
        await rig.aclose()


async def test_upload_idempotent_request_id(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        payload = b"a,b\n1,2\n"
        async with _client(rig) as client:
            first = await client.post(
                "/api/files", files={"file": ("x.csv", payload, "text/csv")},
                data={"request_id": "same"}, headers=_auth(rig, user),
            )
            second = await client.post(
                "/api/files", files={"file": ("x.csv", payload, "text/csv")},
                data={"request_id": "same"}, headers=_auth(rig, user),
            )
        assert first.status_code == second.status_code == 200
        assert first.json()["file"]["file_id"] == second.json()["file"]["file_id"]
        assert second.json()["duplicate"] is True
    finally:
        await rig.aclose()


async def test_upload_requires_token(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        async with _client(rig) as client:
            response = await client.post(
                "/api/files", files={"file": ("x.csv", b"a,b\n", "text/csv")},
            )
        assert response.status_code == 401
    finally:
        await rig.aclose()


async def test_cross_owner_guess_returns_404(tmp_path):
    rig, owner = make_files_rig(tmp_path)
    try:
        other = rig.seed_user(role="user")
        async with _client(rig) as client:
            created = await client.post(
                "/api/files", files={"file": ("private.csv", b"secret", "text/csv")},
                headers=_auth(rig, owner),
            )
            file_id = created.json()["file"]["file_id"]
            guessed = await client.get(f"/api/files/{file_id}", headers=_auth(rig, other))
            guessed_download = await client.get(
                f"/api/files/{file_id}/content", headers=_auth(rig, other),
            )
        assert guessed.status_code == 404
        assert guessed_download.status_code == 404
    finally:
        await rig.aclose()


async def test_delete_unlink_keeps_downloadable(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        async with _client(rig) as client:
            created = await client.post(
                "/api/files", files={"file": ("keep.csv", b"keep", "text/csv")},
                headers=_auth(rig, user),
            )
            file_id = created.json()["file"]["file_id"]
            deleted = await client.delete(
                f"/api/files/{file_id}", params={"scope": "unlink"}, headers=_auth(rig, user),
            )
            assert deleted.status_code == 200
            assert deleted.json()["scope"] == "unlink"
            still_there = await client.get(
                f"/api/files/{file_id}/content", headers=_auth(rig, user),
            )
        assert still_there.status_code == 200
        assert still_there.content == b"keep"
    finally:
        await rig.aclose()


async def test_delete_file_only_removes_content(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        async with _client(rig) as client:
            created = await client.post(
                "/api/files", files={"file": ("gone.csv", b"gone", "text/csv")},
                headers=_auth(rig, user),
            )
            file_id = created.json()["file"]["file_id"]
            deleted = await client.delete(
                f"/api/files/{file_id}", params={"scope": "file_only"},
                headers=_auth(rig, user),
            )
            assert deleted.status_code == 200
            after = await client.get(f"/api/files/{file_id}", headers=_auth(rig, user))
        assert after.status_code == 404
    finally:
        await rig.aclose()


async def test_unknown_scope_rejected(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        async with _client(rig) as client:
            created = await client.post(
                "/api/files", files={"file": ("a.csv", b"x", "text/csv")},
                headers=_auth(rig, user),
            )
            file_id = created.json()["file"]["file_id"]
            response = await client.delete(
                f"/api/files/{file_id}", params={"scope": "everything"},
                headers=_auth(rig, user),
            )
        assert response.status_code == 422
    finally:
        await rig.aclose()


async def test_list_only_returns_own_files(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        other = rig.seed_user(role="user")
        async with _client(rig) as client:
            await client.post(
                "/api/files", files={"file": ("mine.csv", b"mine", "text/csv")},
                headers=_auth(rig, user),
            )
            await client.post(
                "/api/files", files={"file": ("theirs.csv", b"theirs", "text/csv")},
                headers=_auth(rig, other),
            )
            mine = await client.get("/api/files", headers=_auth(rig, user))
            all_files = await client.get(
                "/api/files", params={"all_owners": "true"}, headers=_auth(rig, user),
            )
        assert [f["original_name"] for f in mine.json()["files"]] == ["mine.csv"]
        assert all_files.status_code == 403
    finally:
        await rig.aclose()
