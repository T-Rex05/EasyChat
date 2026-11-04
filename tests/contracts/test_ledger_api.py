"""F6/F8：账本 HTTP 契约（鉴权、导入、提交、统计、图片候选、退款链接）。

服务装配真实临时 SQLite + 临时文件目录；视觉用测试内 FakeVision，不联网。
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.modules.ledger.routes import build_ledger_router
from backend.shared.errors import AppError
from tests.ledger.helpers import make_ledger_rig, upload_bill
from tests.support.ledger_fixtures import (
    fake_vision_payload,
    standard_scenario,
    write_png,
    write_wechat_xlsx,
)


class FakeVision:
    def __init__(self, payload: dict[str, Any] | None = None):
        self.payload = fake_vision_payload() if payload is None else payload
        self.calls: list[str] = []

    async def extract(self, path, *, prompt: str = "") -> dict[str, Any]:
        self.calls.append(str(path))
        return self.payload


def _client(rig) -> httpx.AsyncClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle(_: object, exc: AppError):
        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    app.include_router(
        build_ledger_router(_LazyLedger(rig), rig.access.authenticate_token)
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


class _LazyLedger:
    """路由只用到 LedgerService 的公开方法，测试里直接给装配好的实例。"""

    def __init__(self, rig) -> None:
        self._rig = rig

    def __getattr__(self, name: str):
        return getattr(self._rig.ledger, name)


def _auth(rig, user) -> dict[str, str]:
    token = rig.access.create_token(user.user_id, f"user{user.user_id}", user.role)
    return {"Authorization": f"Bearer {token}"}


async def test_endpoints_require_token(tmp_path):
    rig, _user = make_ledger_rig(tmp_path)
    try:
        async with _client(rig) as client:
            for method, path in (
                ("get", "/api/ledger/imports"),
                ("get", "/api/ledger/transactions"),
                ("get", "/api/ledger/categories"),
            ):
                response = await getattr(client, method)(path)
                assert response.status_code == 401, (path, response.text)
    finally:
        await rig.aclose()


async def test_permission_denied_without_ledger_view(tmp_path):
    rig, user = make_ledger_rig(tmp_path, revokes=("ledger.view",))
    try:
        async with _client(rig) as client:
            response = await client.get(
                "/api/ledger/imports", headers=_auth(rig, user),
            )
        assert response.status_code == 403
    finally:
        await rig.aclose()


async def test_import_commit_analyze_over_http(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "http.xlsx", standard_scenario())
        saved = await upload_bill(rig, user, path)
        headers = _auth(rig, user)
        async with _client(rig) as client:
            registered = await client.post(
                "/api/ledger/imports",
                json={"file_id": saved.file.file_id},
                headers=headers,
            )
            assert registered.status_code == 200, registered.text
            import_id = registered.json()["import"]["import_id"]
            parsed = await client.post(
                f"/api/ledger/imports/{import_id}/parse", headers=headers,
            )
            assert parsed.status_code == 200, parsed.text
            assert parsed.json()["import"]["state"] in ("validated", "needs_review")

            rows = await client.get(
                f"/api/ledger/imports/{import_id}/rows", headers=headers,
            )
            assert rows.status_code == 200
            assert len(rows.json()["rows"]) == 4

            summary = await client.get(
                f"/api/ledger/imports/{import_id}/summary", headers=headers,
            )
            assert summary.status_code == 200
            assert summary.json()["totals"]["expense_minor"] == 15000

            committed = await client.post(
                f"/api/ledger/imports/{import_id}/commit",
                json={"request_id": "http-1"}, headers=headers,
            )
            assert committed.status_code == 200, committed.text
            assert committed.json()["inserted"] == 4

            transactions = await client.get(
                "/api/ledger/transactions", headers=headers,
            )
            assert transactions.status_code == 200
            assert len(transactions.json()["transactions"]) == 4
            assert "storage_key" not in transactions.text
            assert str(tmp_path) not in transactions.text

            analyzed = await client.post(
                "/api/ledger/analyze",
                json={
                    "plan": {
                        "version": 1, "basis": "consumption_net",
                        "metrics": ["expense", "net"],
                        "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
                        "output": "summary",
                    },
                },
                headers=headers,
            )
            assert analyzed.status_code == 200, analyzed.text
            body = analyzed.json()
            metrics = {item["name"]: item["amount_minor"] for item in body["metrics"]}
            assert metrics["expense"] == 12000
            assert body["analysis_id"].startswith("lan_")
    finally:
        await rig.aclose()


async def test_analyze_rejects_model_sql_over_http(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        async with _client(rig) as client:
            response = await client.post(
                "/api/ledger/analyze",
                json={
                    "plan": {
                        "version": 1, "basis": "statement_flow", "metrics": ["expense"],
                        "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
                        "sql": "SELECT * FROM ledger_transactions",
                    },
                },
                headers=_auth(rig, user),
            )
        assert response.status_code == 422, response.text
    finally:
        await rig.aclose()


async def test_image_candidate_without_vision_is_explicit_error(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        png = write_png(tmp_path / "shot.png")
        saved = await upload_bill(rig, user, png, name="shot.png")
        async with _client(rig) as client:
            response = await client.post(
                f"/api/ledger/images/{saved.file.file_id}/candidates",
                headers=_auth(rig, user),
            )
        assert response.status_code == 422
        assert "未配置图片识别服务" in response.text
    finally:
        await rig.aclose()


async def test_image_candidate_flow_over_http(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        rig.ledger.vision = FakeVision()
        png = write_png(tmp_path / "shot2.png")
        saved = await upload_bill(rig, user, png, name="shot2.png")
        headers = _auth(rig, user)
        async with _client(rig) as client:
            created = await client.post(
                f"/api/ledger/images/{saved.file.file_id}/candidates", headers=headers,
            )
            assert created.status_code == 200, created.text
            candidate = created.json()
            assert candidate["amount_minor"] == 2350
            assert candidate["fields"]["amount"]["confidence"] >= 0.9
            assert candidate["needs_review"] is False

            confirmed = await client.post(
                f"/api/ledger/candidates/{candidate['extraction_id']}/confirm",
                json={}, headers=headers,
            )
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["transaction"]["verification"] == "confirmed"
    finally:
        await rig.aclose()


async def test_low_confidence_candidate_needs_corrections(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        rig.ledger.vision = FakeVision(fake_vision_payload(amount=None))
        png = write_png(tmp_path / "shot3.png")
        saved = await upload_bill(rig, user, png, name="shot3.png")
        headers = _auth(rig, user)
        async with _client(rig) as client:
            created = await client.post(
                f"/api/ledger/images/{saved.file.file_id}/candidates", headers=headers,
            )
            candidate = created.json()
            assert "amount" in candidate["missing_fields"]
            rejected = await client.post(
                f"/api/ledger/candidates/{candidate['extraction_id']}/confirm",
                json={}, headers=headers,
            )
            assert rejected.status_code == 422
            fixed = await client.post(
                f"/api/ledger/candidates/{candidate['extraction_id']}/confirm",
                json={"corrections": {"amount": "23.50"}}, headers=headers,
            )
            assert fixed.status_code == 200, fixed.text
    finally:
        await rig.aclose()


async def test_refund_links_over_http(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "refund.xlsx", standard_scenario())
        saved = await upload_bill(rig, user, path)
        headers = _auth(rig, user)
        async with _client(rig) as client:
            registered = await client.post(
                "/api/ledger/imports", json={"file_id": saved.file.file_id}, headers=headers,
            )
            import_id = registered.json()["import"]["import_id"]
            await client.post(
                f"/api/ledger/imports/{import_id}/parse", headers=headers,
            )
            await client.post(
                f"/api/ledger/imports/{import_id}/commit", json={}, headers=headers,
            )
            refunds = await client.get("/api/ledger/refunds", headers=headers)
            assert refunds.status_code == 200
            links = refunds.json()["links"]
            assert len(links) == 1
            assert links[0]["link"]["confirmation"] == "confirmed"
            assert links[0]["remaining_minor"] == 7000
            suggestions = await client.get(
                "/api/ledger/refunds/suggestions", headers=headers,
            )
            assert suggestions.status_code == 200
    finally:
        await rig.aclose()


async def test_delete_import_over_http_requires_import_permission(tmp_path):
    rig, user = make_ledger_rig(tmp_path, revokes=("ledger.import",))
    try:
        # 用另一个有权限的 owner 造批次，再确认无权限者拿不到 404/403 之外的细节
        owner = rig.seed_user(role="user")
        path = write_wechat_xlsx(tmp_path / "bills" / "私.xlsx", standard_scenario())
        saved = await upload_bill(rig, owner, path)
        view = await rig.ledger.register_import(owner, saved.file.file_id)
        async with _client(rig) as client:
            response = await client.delete(
                f"/api/ledger/imports/{view.import_id}", headers=_auth(rig, user),
            )
        assert response.status_code == 403
    finally:
        await rig.aclose()


@pytest.mark.parametrize("field", ["sql", "python", "code"])
async def test_unknown_plan_keys_are_rejected(tmp_path, field):
    rig, user = make_ledger_rig(tmp_path)
    try:
        async with _client(rig) as client:
            response = await client.post(
                "/api/ledger/analyze",
                json={
                    "plan": {
                        "version": 1, "basis": "statement_flow", "metrics": ["expense"],
                        "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
                        field: "x",
                    },
                },
                headers=_auth(rig, user),
            )
        assert response.status_code == 422
    finally:
        await rig.aclose()
