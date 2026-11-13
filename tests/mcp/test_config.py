"""P4 MCP 配置服务回归：持久化、凭据加密与保留、探测状态、启用注册、授权门控。"""
from __future__ import annotations

import pytest

from backend.modules.mcp.api import McpService
from backend.modules.mcp.contracts import McpCheckResult
from tests.support.rig import make_rig

SECRET = "unit-test-secret"


class _Adapter:
    def __init__(self):
        self.registered: list = []

    def register(self, configs):
        self.registered.append(list(configs))
        return self

    def health(self):
        return {}


def _service(rig, *, adapter=None, probe=None):
    return McpService(
        rig.db, access=rig.access, encryption_secret=SECRET,
        adapter=adapter or _Adapter(),
        probe=probe or (lambda config: McpCheckResult(ok=True, tools=("t1",))),
    )


def _admin(rig):
    return rig.seed_user(role="super_admin", username="mcp_admin")


def _plain(rig):
    return rig.seed_user(role="user", username="mcp_plain", grants=("chat.use",))


def test_create_persists_credential_encrypted_and_disabled_by_default(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    admin = _admin(ready)
    service = _service(ready)
    view = service.create(
        admin, name="weknora", url="https://mcp.test/mcp", credential="sk-super-secret-123",
    )
    assert view.enabled is False
    assert view.credential_set is True
    conn = ready.db.connect()
    try:
        row = conn.execute("SELECT credential_enc FROM mcp_servers WHERE id=?", (view.id,)).fetchone()
    finally:
        conn.close()
    assert str(row["credential_enc"]).startswith("enc:v1:")
    assert "sk-super-secret-123" not in str(row["credential_enc"])
    # 视图对象绝不含明文字段
    assert not hasattr(view, "credential_value")


def test_update_keeps_credential_unless_explicit_clear(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    admin = _admin(ready)
    service = _service(ready)
    view = service.create(admin, name="keep", url="https://a.test/x", credential="first-secret")
    conn = ready.db.connect()
    try:
        before = str(conn.execute("SELECT credential_enc FROM mcp_servers").fetchone()[0])
    finally:
        conn.close()

    updated = service.update(admin, view.id, url="https://b.test/y")
    conn = ready.db.connect()
    try:
        after = str(conn.execute("SELECT credential_enc FROM mcp_servers").fetchone()[0])
    finally:
        conn.close()
    assert after == before, "缺省凭据必须保留既有密文"
    assert updated.url == "https://b.test/y"

    cleared = service.update(admin, view.id, clear_credential=True)
    assert cleared.credential_set is False


def test_name_and_url_validation(rig) -> None:
    from backend.shared.errors import ConflictError, InvalidInputError

    ready = make_rig(rig.tmp_path, seed_access=True)
    admin = _admin(ready)
    service = _service(ready)
    with pytest.raises(InvalidInputError):
        service.create(admin, name="Bad Name!", url="https://a.test/x")
    with pytest.raises(InvalidInputError):
        service.create(admin, name="ok-name", url="ftp://a.test/x")
    with pytest.raises(InvalidInputError):
        service.create(admin, name="ok2", url="https://user:pa***@a.test/x")
    service.create(admin, name="dup", url="https://a.test/x")
    with pytest.raises(ConflictError):
        service.create(admin, name="dup", url="https://b.test/y")


def test_enable_registers_with_decrypted_credential(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    admin = _admin(ready)
    adapter = _Adapter()
    service = _service(ready, adapter=adapter)
    view = service.create(admin, name="dec", url="https://m.test/mcp", credential="plain-value-42")
    service.set_enabled(admin, view.id, True)
    assert adapter.registered
    config = adapter.registered[-1][0]
    assert config.credential_value == "plain-value-42"  # 内存内解密（不落库不进日志）
    assert config.name == "dec"


def test_probe_result_persisted_with_classification(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    admin = _admin(ready)
    results = [McpCheckResult(ok=False, error_kind="auth_failed", error_message="HTTP 401")]
    service = _service(ready, probe=lambda config: results.pop(0))
    view = service.create(admin, name="probe", url="https://p.test/mcp")
    out = service.test(admin, view.id)
    assert out["ok"] is False and out["state"] == "failed"
    again = service.list(admin)[0]
    assert again.last_check_state == "failed"
    assert "401" in again.last_check_error


def test_granted_toolsets_audience_gating(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True)
    admin, plain = _admin(ready), _plain(ready)
    service = _service(ready)
    v1 = service.create(ready.seed_user(role="super_admin", username="adm2"),
                        name="cfgonly", url="https://a.test/x", audience="config_admin")
    v2 = service.create(admin, name="everyone", url="https://b.test/y", audience="all")
    service.set_enabled(admin, v1.id, True)
    service.set_enabled(admin, v2.id, True)

    from backend.modules.mcp.api import McpService as _S  # noqa: F401

    admin_principal = ready.access.snapshot_principal(admin.user_id)
    plain_principal = ready.access.snapshot_principal(plain.user_id)
    assert service.granted_toolsets(admin_principal) == ("mcp-cfgonly", "mcp-everyone")
    assert service.granted_toolsets(plain_principal) == ("mcp-everyone",)
    # 禁用后不授予
    service.set_enabled(admin, v2.id, False)
    assert "mcp-everyone" not in service.granted_toolsets(plain_principal)


def test_write_requires_system_config(rig) -> None:
    from backend.shared.errors import ForbiddenError

    ready = make_rig(rig.tmp_path, seed_access=True)
    plain = _plain(ready)
    service = _service(ready)
    with pytest.raises(ForbiddenError):
        service.create(plain, name="nope", url="https://a.test/x")
