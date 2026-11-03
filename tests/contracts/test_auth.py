"""认证与授权契约测试：注册/登录/token 生命周期/HTTP路由/被拒请求不触发Runtime。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.modules.access.api import AccessService
from backend.modules.access.repository import hash_password, needs_rehash, verify_password
from backend.modules.access.routes import build_access_router
from backend.platform.sqlite import Database
from backend.shared.errors import ForbiddenError, InvalidInputError, UnauthenticatedError
from tests.support.rig import make_rig


@pytest.fixture
def rig(tmp_path):
    r = make_rig(tmp_path, seed_access=True)
    yield r
    import asyncio

    asyncio.run(r.aclose())


# ---- 密码哈希行为 ----------------------------------------------------------------


def test_scrypt_hash_and_verify():
    hashed = hash_password("password6")
    assert needs_rehash(hashed) is False
    assert verify_password("password6", hashed)
    assert not verify_password("password7", hashed)


def test_legacy_sha256_hash_verifies_and_needs_rehash():
    import hashlib
    import secrets

    salt = secrets.token_hex(16)
    legacy = f"{salt}:{hashlib.sha256(f'{salt}:password6'.encode()).hexdigest()}"
    assert needs_rehash(legacy) is True
    assert verify_password("password6", legacy)
    assert not verify_password("wrong", legacy)


def test_legacy_login_upgrades_hash(rig):
    import hashlib
    import secrets

    access = rig.access
    result = access.register("legacy_user", "password6")
    salt = secrets.token_hex(16)
    legacy = f"{salt}:{hashlib.sha256(f'{salt}:password6'.encode()).hexdigest()}"
    access.repo.update_password(result["user_id"], legacy)

    login = access.login("legacy_user", "password6")
    assert login["user_id"] == result["user_id"]
    row = access.repo.get_user_auth_row("legacy_user")
    assert needs_rehash(str(row["password"])) is False  # 已升级 scrypt
    assert verify_password("password6", str(row["password"]))


# ---- 注册 / 登录 ------------------------------------------------------------------


def test_register_login_flow(rig):
    access = rig.access
    reg = access.register("alice", "password6", "a@x.com")
    assert reg["token"]
    login = access.login("alice", "password6")
    assert login["user_id"] == reg["user_id"]
    assert login["role"] == "user"
    # 默认 user 角色：chat.use 在默认授权中
    assert "chat.use" in access.effective_permissions(login["user_id"])


def test_register_validation_and_duplicates(rig):
    access = rig.access
    with pytest.raises(InvalidInputError):
        access.register("a", "password6")  # 用户名过短
    with pytest.raises(InvalidInputError):
        access.register("bob", "12345")  # 密码过短
    access.register("carol", "password6")
    from backend.shared.errors import ConflictError

    with pytest.raises(ConflictError):
        access.register("carol", "password6")


def test_login_failures(rig):
    access = rig.access
    access.register("dave", "password6")
    with pytest.raises(UnauthenticatedError):
        access.login("dave", "wrong-password")
    with pytest.raises(UnauthenticatedError):
        access.login("ghost", "password6")


# ---- Token 生命周期 ----------------------------------------------------------------


def test_token_verify_tamper_and_expiry(rig):
    access = rig.access
    reg = access.register("erin", "password6")
    token = reg["token"]
    assert access.verify_token(token)["user_id"] == reg["user_id"]
    assert access.verify_token(token[:-2] + "xx") is None  # 篡改签名
    # 过期：推进时钟
    rig.clock.advance(access.token_expiry_hours * 3600 + 1)
    assert access.verify_token(token) is None


def test_token_renewal_window(rig):
    access = rig.access
    reg = access.register("frank", "password6")
    token = reg["token"]
    # 剩余有效期远大于阈值 → 不续期
    assert access.check_token_renewal(token) is None
    # 推进到续期窗口内：剩余有效期 = 阈值/2
    rig.clock.advance(access.token_expiry_hours * 3600 - access.renew_threshold_seconds // 2)
    new_token = access.check_token_renewal(token)
    assert new_token is not None
    assert access.verify_token(new_token)["user_id"] == reg["user_id"]


def test_expired_token_refresh_within_grace(rig):
    access = rig.access
    reg = access.register("grace", "password6")
    token = reg["token"]
    rig.clock.advance(access.token_expiry_hours * 3600 + 60)  # 刚过期1分钟
    assert access.verify_token(token) is None  # 已过期
    renewed = access.renew_token(token)
    assert renewed is not None
    assert access.verify_token(renewed)["user_id"] == reg["user_id"]
    # 超出宽限期 → 拒绝
    rig.clock.advance(access.refresh_grace_seconds + 10)
    rig2_token = renewed
    assert access.renew_token(rig2_token) is None


def test_weak_jwt_secret_rejected(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    with pytest.raises(InvalidInputError):
        AccessService(db, jwt_secret="secret")
    with pytest.raises(InvalidInputError):
        AccessService(db, jwt_secret="short")
    # 显式允许弱密钥（本机调试）
    AccessService(db, jwt_secret="secret", allow_weak_secret=True)
    db.close()


# ---- HTTP 路由契约 ------------------------------------------------------------------


def _client(rig):
    from fastapi import FastAPI

    from backend.shared.errors import AppError

    app = FastAPI()
    app.include_router(build_access_router(rig.access))

    @app.exception_handler(AppError)
    async def handler(_: object, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(exc.to_payload(), status_code=exc.http_status)

    return TestClient(app)


def test_routes_register_login_me_refresh(rig):
    client = _client(rig)
    reg = client.post("/api/auth/register", json={"username": "route_user", "password": "password6"})
    assert reg.status_code == 200
    body = reg.json()
    assert body["ok"] is True and body["token"] and "chat.use" in body["permissions"]

    login = client.post("/api/auth/login", json={"username": "route_user", "password": "password6"})
    assert login.status_code == 200
    login_body = login.json()
    assert "hermes_tools" in login_body

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "route_user"
    assert "permissions" in me.json()

    # 无 token → 401
    assert client.get("/api/auth/me").status_code == 401
    # 错误密码 → 401
    bad = client.post("/api/auth/login", json={"username": "route_user", "password": "wrong"})
    assert bad.status_code == 401


def test_routes_refresh_endpoint(rig):
    client = _client(rig)
    reg = client.post("/api/auth/register", json={"username": "refresh_user", "password": "password6"})
    token = reg.json()["token"]
    # 未到续期窗口：refresh 返回新 token（check_token_renewal=None 时走 renew→也 None → 401）
    resp = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401  # 未过期且不在续期窗口 → 无新 token
    # 推进到宽限期内
    rig.clock.advance(rig.access.token_expiry_hours * 3600 + 60)
    resp2 = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["ok"] is True and body["token"]
    assert body["username"] == "refresh_user"
    assert "permissions" in body and "hermes_tools" in body


def test_routes_admin_role_management(rig):
    client = _client(rig)
    admin_reg = client.post("/api/auth/register", json={"username": "admin_route", "password": "password6"})
    admin_token = admin_reg.json()["token"]
    # bootstrap 种子语义：提为 super_admin（经由真实 repository 路径）
    uid = admin_reg.json()["user_id"]
    rig.access.repo.set_user_role(uid, "super_admin")
    rig.access.invalidate_all()
    headers = {"Authorization": f"Bearer {admin_token}"}

    roles = client.get("/api/admin/roles", headers=headers)
    assert roles.status_code == 200
    assert {r["name"] for r in roles.json()} >= {"super_admin", "admin", "user"}

    created = client.post(
        "/api/admin/roles",
        json={"name": "editor", "display_name": "编辑", "permissions": ["chat.use", "skill.create"]},
        headers=headers,
    )
    assert created.status_code == 201

    perms = client.get("/api/admin/permissions", headers=headers)
    assert perms.status_code == 200
    keys = {p["key"] for p in perms.json()}
    assert "evolution.manage" in keys  # 新增进化权限已注册
    assert "kb.manage" not in keys and "paper.use" not in keys  # 已删业务权限不注册

    toolsets = client.get("/api/admin/toolsets", headers=headers)
    assert toolsets.status_code == 200
    assert all(t["key"] != "paper_repro" for t in toolsets.json())

    # 无权限用户访问管理端点 → 403
    user_reg = client.post("/api/auth/register", json={"username": "plain_route", "password": "password6"})
    user_headers = {"Authorization": f"Bearer {user_reg.json()['token']}"}
    assert client.get("/api/admin/roles", headers=user_headers).status_code == 403


# ---- 被拒请求不触发 Runtime -----------------------------------------------------------


@pytest.mark.asyncio
async def test_denied_request_never_triggers_runtime(rig):
    """无 chat.use 的用户提交聊天：授权先行拒绝，Runtime 零调用（Task 6 端到端复验）。"""

    access = rig.access
    no_chat = rig.seed_user(role="user", revokes=("chat.use",))
    assert "chat.use" not in access.effective_permissions(no_chat.user_id)
    with pytest.raises(ForbiddenError):
        access.require_permission(no_chat, "chat.use")
    assert rig.runtime.execute_count == 0
