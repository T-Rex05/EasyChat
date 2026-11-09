"""安全审计修复回归（audit run-1，findings #1-#10）。

每条用例对应 REPORT.md 一个编号；命名保持 fingerprint 可追溯。
"""
from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import httpx
import pytest

from backend.app import create_app
from backend.modules.access.api import AccessService, validate_deployment_secret
from backend.modules.channels.wechat.urlpolicy import is_allowed_media_url
from backend.modules.delivery.smtp import validate_single_address
from backend.modules.ledger.parsers.base import ParseOptions
from backend.modules.ledger.parsers.wechat_csv import parse_csv_text
from backend.shared.errors import InvalidInputError
from backend.utils.rate_limit import AUTH_LIMITS, AuthRateLimiter


# ---- #1 / #9：占位密钥与部署密钥熵下限 ------------------------------------------


def _access_service(tmp_path, *, jwt_secret: str, **kwargs) -> AccessService:
    from backend.platform.sqlite import Database

    db = Database(tmp_path / "secret_probe.db")
    return AccessService(db, jwt_secret=jwt_secret, **kwargs)


def _seeded_service(tmp_path, **kwargs) -> AccessService:
    """带迁移与种子的实例：ticket 消费要查 users/roles 表。"""
    from backend.platform.sqlite import Database

    db = Database(tmp_path / "seeded_probe.db")
    db.migrate()
    svc = AccessService(db, jwt_secret=jwt_for_probe(), **kwargs)
    svc.seed()
    return svc


def jwt_for_probe() -> str:
    return secrets.token_hex(32)


def test_jwt_placeholder_secret_refused_at_construction(tmp_path):
    """审计 #1：仓库曾发布的占位值必须被 _validate_secret 拒绝。"""
    with pytest.raises(InvalidInputError):
        _access_service(tmp_path, jwt_secret="please-change-to-a-random-64-char-secret")


def test_deployment_secret_entropy_floor():
    """审计 #9：加密密钥与 JWT 密钥同一套下限；弱值/占位值/过短拒绝。"""
    with pytest.raises(InvalidInputError):
        validate_deployment_secret("please-change-it-too-00000000000000000000", kind="EASYCHAT_ENCRYPTION_SECRET")
    with pytest.raises(InvalidInputError):
        validate_deployment_secret("changeme-000000000000000000000000000000", kind="EASYCHAT_ENCRYPTION_SECRET")
    with pytest.raises(InvalidInputError):
        validate_deployment_secret("short", kind="EASYCHAT_ENCRYPTION_SECRET")
    assert validate_deployment_secret(secrets.token_hex(32), kind="EASYCHAT_ENCRYPTION_SECRET")


def test_weak_secret_still_allowed_explicitly(tmp_path):
    """allow_weak=True（测试注入路径）保持可用，不影响既有测试设施。"""
    svc = _access_service(tmp_path, jwt_secret="change-me", allow_weak_secret=True)
    assert svc.jwt_secret == "change-me"


# ---- #3：SSE ticket 一次性与过期 ------------------------------------------------


def test_sse_ticket_single_use_and_expiry(tmp_path):
    rig_clock = {"now": 1000.0}
    svc = _seeded_service(tmp_path, clock=lambda: rig_clock["now"])
    user_id = svc.repo.create_user("ticket_probe", "not-a-real-hash", "")
    ticket = svc.issue_sse_ticket(user_id)
    principal = svc.consume_sse_ticket(ticket)
    assert principal.user_id == user_id
    with pytest.raises(Exception):  # noqa: B017  单次消费后必须失效
        svc.consume_sse_ticket(ticket)
    expired = svc.issue_sse_ticket(user_id)
    rig_clock["now"] += 3600
    with pytest.raises(Exception):  # noqa: B017  过期 ticket 必须失效
        svc.consume_sse_ticket(expired)


# ---- #5：登录/注册限流 -----------------------------------------------------------


def test_auth_rate_limiter_window():
    limiter = AuthRateLimiter(clock=lambda: 0.0)
    route = "/api/auth/login"
    limit, _window = AUTH_LIMITS[route]
    assert all(limiter.allow("1.2.3.4", route) for _ in range(limit))
    assert not limiter.allow("1.2.3.4", route)
    assert limiter.allow("5.6.7.8", route)  # 其他 IP 不受影响


def test_login_rate_limit_returns_429(tmp_path):
    """中间件在生产配置（auth_rate_limit_enabled=True）下生效。"""
    from backend.platform.settings import AppSettings

    data_dir = tmp_path / "data"
    settings = AppSettings(
        data_db_path=data_dir / "app.db",
        state_db_path=data_dir / "state.db",
        artifacts_dir=data_dir / "artifacts",
        auth_rate_limit_enabled=True,
    )
    app = create_app(settings)

    async def main():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                statuses = []
                for _ in range(AUTH_LIMITS["/api/auth/login"][0] + 1):
                    resp = await client.post(
                        "/api/auth/login",
                        json={"username": "nobody-here", "password": "wrong-pass-1"},
                    )
                    statuses.append(resp.status_code)
        return statuses

    statuses = asyncio.run(main())
    limit = AUTH_LIMITS["/api/auth/login"][0]
    assert all(code in (401,) for code in statuses[:limit])
    assert statuses[limit] == 429


# ---- #6：微信媒体重定向逐跳复查 ---------------------------------------------------


def test_media_url_policy():
    assert is_allowed_media_url("https://weixin.qq.com/a")
    assert is_allowed_media_url("https://x.qpic.cn/b")
    assert not is_allowed_media_url("http://weixin.qq.com/a")  # 非 https
    assert not is_allowed_media_url("https://evil.com/a")
    assert not is_allowed_media_url("https://attacker-weixin.qq.com.evil.com/a")


def test_aiohttp_download_rejects_non_allowlisted_redirect(tmp_path):
    """审计 #6：302 到非白名单主机必须失败且不落盘（本地回环服务器）。"""
    pytest.importorskip("aiohttp")
    from aiohttp import web

    from backend.modules.channels.wechat.account import AiohttpTransport

    outer_host, outer_port = "127.0.0.1", 49001
    inner_host, inner_port = "127.0.0.1", 49002

    async def redirect(_request):
        raise web.HTTPFound(f"http://{inner_host}:{inner_port}/secret")

    async def secret(_request):
        return web.Response(body=b"leaked")

    async def serve():
        outer = web.Application()
        outer.router.add_get("/media", redirect)
        inner = web.Application()
        inner.router.add_get("/secret", secret)
        runner_outer = web.AppRunner(outer)
        runner_inner = web.AppRunner(inner)
        await runner_outer.setup()
        await runner_inner.setup()
        site_outer = web.TCPSite(runner_outer, outer_host, outer_port)
        site_inner = web.TCPSite(runner_inner, inner_host, inner_port)
        await site_outer.start()
        await site_inner.start()
        return runner_outer, runner_inner

    async def main():
        runners = await serve()
        dest = tmp_path / "out.bin"
        transport = AiohttpTransport()
        try:
            # 初始 URL 指向白名单外的本地服务器——download_to 不做初始校验
            # （那是 media.py 的职责），但 302 跳到另一个非白名单主机必须被拒。
            with pytest.raises(Exception, match="微信 CDN|重定向"):
                await transport.download_to(
                    f"http://{outer_host}:{outer_port}/media",
                    dest, max_bytes=1024,
                    allowed_hosts=("weixin.qq.com", "qpic.cn"),
                )
            assert not dest.exists()
        finally:
            await transport.aclose()
            for runner in runners:
                await runner.cleanup()

    asyncio.run(main())


# ---- #7：单合法邮箱地址 ----------------------------------------------------------


def test_single_address_validation_rejects_lists_and_controls():
    """审计 #7：逗号列表/CRLF/尖括号在注册边界拒绝。"""
    with pytest.raises(InvalidInputError):
        validate_single_address("me@example.com, victim@example.net")
    with pytest.raises(InvalidInputError):
        validate_single_address("me@example.com\r\nBcc: victim@example.net")
    with pytest.raises(InvalidInputError):
        validate_single_address("<me@example.com>")
    with pytest.raises(InvalidInputError):
        validate_single_address("not-an-address")
    assert validate_single_address("  User@Example.COM ") == "User@Example.COM".strip()


# ---- #8：账单解析控制行上限 -------------------------------------------------------


def _write_csv(tmp_path: Path, control_line_count: int) -> Path:
    path = tmp_path / "bill.csv"
    header = "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注"
    lines = [header, "2026-01-01 10:00:00,商户消费,某商户,商品,支出,10.00,零钱,支付成功,NO1,NO1,/"]
    lines.extend(["共"] * control_line_count)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_parse_caps_control_lines(tmp_path):
    """审计 #8：控制行保留量有硬上限，超帽丢弃并告警，解析本身不失败。"""
    path = _write_csv(tmp_path, control_line_count=6000)
    statement = parse_csv_text(
        path, ParseOptions(), text=path.read_text(encoding="utf-8"),
        delimiter=",", parser_name="wechat_csv",
    )
    assert len(statement.rows) == 1
    assert any("控制行超过上限" in w for w in statement.warnings)


def test_parse_under_control_cap_has_no_warning(tmp_path):
    path = _write_csv(tmp_path, control_line_count=10)
    statement = parse_csv_text(
        path, ParseOptions(), text=path.read_text(encoding="utf-8"),
        delimiter=",", parser_name="wechat_csv",
    )
    assert len(statement.rows) == 1
    assert not any("控制行超过上限" in w for w in statement.warnings)


# ---- #10：退款侧镜像上限（真实账单流） -------------------------------------------


async def test_refund_link_mirror_cap_across_originals(tmp_path):
    """审计 #10：单笔退款累计关联不得超过退款金额——第二笔原消费被拒。"""
    from tests.ledger.helpers import import_bill, make_ledger_rig
    from tests.support.ledger_fixtures import standard_scenario, write_wechat_xlsx

    rig, principal = make_ledger_rig(tmp_path)
    try:
        path = write_wechat_xlsx(tmp_path / "bills" / "镜像上限.xlsx", standard_scenario())
        view, _ = await import_bill(rig, principal, path)
        rig.ledger.commit_import(principal, view.import_id)
        conn = rig.db.connect()
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM ledger_transactions").fetchall()]
        finally:
            conn.close()
        refund = next(t for t in rows if t["event_role"] == "refund")
        second_original = next(
            t for t in rows
            if t["event_role"] == "payment" and int(t["amount_minor"]) == 5000
        )
        # 标准场景里退款 3000 已确认关联到 9 月原支付；再关联到另一笔原支付
        # 即便金额远小于其容量，也必须被退款侧镜像上限拒绝。
        with pytest.raises(InvalidInputError, match="退款交易金额"):
            rig.ledger.link_refund(
                principal, refund_transaction_id=refund["id"],
                original_transaction_id=second_original["id"], amount_minor=100,
            )
    finally:
        await rig.aclose()
