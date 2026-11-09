"""工厂契约测试（Task 1）。

import/create_app 不连网络、不读真实.env、不运行迁移、不启动监听器；
lifespan 才显式启动依赖。错误映射走统一边界。
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import SPAStaticFiles, create_app, error_to_response
from backend.bootstrap import AppSettings, default_settings
from backend.shared.context import ExecutionContext, Principal
from backend.shared.errors import (
    AppError,
    BusyError,
    ErrorCode,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    UnauthenticatedError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# 所有 ErrorCode → HTTP 状态映射（架构 §11）
EXPECTED_STATUS = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.INVALID_INPUT: 422,
    ErrorCode.BUSY: 429,
    ErrorCode.CAPABILITY_UNAVAILABLE: 503,
    ErrorCode.DEPENDENCY_TIMEOUT: 504,
    ErrorCode.STORAGE_UNAVAILABLE: 503,
    ErrorCode.INTERRUPTED: 500,
}


def _tmp_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        data_db_path=data_dir / "app.db",
        state_db_path=data_dir / "state.db",
        artifacts_dir=data_dir / "artifacts",
    )


# ---- import 纯净性：子进程内禁网并断言 dotenv 未加载 --------------------------


def test_import_backend_app_is_offline_and_dotenv_free():
    code = (
        "import socket\n"
        "class _NoNet(socket.socket):\n"
        "    def __init__(self, *a, **k):\n"
        "        raise AssertionError('network activity during import')\n"
        "socket.socket = _NoNet\n"
        "socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(AssertionError('network'))\n"
        "import backend.app\n"
        "import backend.bootstrap\n"
        "import sys\n"
        "assert 'dotenv' not in sys.modules, 'dotenv loaded at import time'\n"
        "print('OFFLINE_OK')\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MYSQL", "REDIS", "NEO4J", "MILVUS"))}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"import 不纯净:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
    assert "OFFLINE_OK" in proc.stdout


def test_factory_run_is_offline(tmp_path):
    """拦截出站连接原语后，create_app + lifespan + 请求正常完成（无真实网络）。

    不替换 socket.socket 本身——asyncio 事件循环内部需要创建自用 socket；
    这里只拦截面向外部的连接入口。lifespan 用 tmp 路径，不污染仓库目录。
    """
    import socket

    def _no_create_connection(*a, **k):
        raise AssertionError("create_app/lifespan 期间出现出站网络连接")

    async def _no_open_connection(*a, **k):
        raise AssertionError("create_app/lifespan 期间出现出站网络连接(asyncio)")

    real_cc, real_oc = socket.create_connection, asyncio.open_connection
    socket.create_connection = _no_create_connection
    asyncio.open_connection = _no_open_connection
    try:
        app = create_app(_tmp_settings(tmp_path))
        with TestClient(app) as client:
            assert client.get("/healthz").json() == {"status": "ok"}
            assert client.get("/readyz").json() == {"status": "ready"}
        assert app.state.ready is False  # 关闭后回落
    finally:
        socket.create_connection = real_cc
        asyncio.open_connection = real_oc


def test_create_app_has_no_side_effects(tmp_path):
    """create_app 不创建文件、不读真实 .env、不运行迁移、不泄漏线程。"""
    env_probe = "EASYCHAT_PROBE_SHOULD_NOT_EXIST"
    assert env_probe not in os.environ

    baseline_threads = threading.active_count()
    settings = _tmp_settings(tmp_path)
    app = create_app(settings)
    data_dir = tmp_path / "data"
    # 未运行迁移：数据目录未被创建
    assert not data_dir.exists()
    # 未启动监听线程
    assert threading.active_count() == baseline_threads
    del app


def test_readyz_503_before_lifespan():
    client = TestClient(create_app(default_settings()), raise_server_exceptions=False)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "starting"}


def test_error_mapping_table_complete():
    for code, expected in EXPECTED_STATUS.items():
        exc = AppError(code, "x")
        assert exc.http_status == expected
        status, payload = error_to_response(exc)
        assert status == expected
        assert payload["error"] == code.value


@pytest.mark.parametrize(
    "exc_cls,expected",
    [
        (UnauthenticatedError, 401),
        (ForbiddenError, 403),
        (NotFoundError, 404),
        (InvalidInputError, 422),
        (BusyError, 429),
    ],
)
def test_typed_errors_raise_and_map(exc_cls, expected):
    exc = exc_cls("msg")
    assert isinstance(exc, AppError)
    assert exc.http_status == expected


def test_app_error_handler_maps_to_http(tmp_path):
    """在工厂产物上注册一个抛领域错误的探针路由，验证异常处理器生效。"""
    app = create_app(_tmp_settings(tmp_path))

    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/_test/forbidden")
    async def probe_forbidden() -> dict:
        raise ForbiddenError("探针")

    app.include_router(router)
    with TestClient(app) as client:
        resp = client.get("/_test/forbidden")
        assert resp.status_code == 403
        assert resp.json() == {"error": "forbidden", "message": "探针"}


def test_lifespan_idempotent_shutdown(tmp_path):
    """shutdown 可重复调用（幂等），不抛异常。"""
    app = create_app(_tmp_settings(tmp_path))
    with TestClient(app):
        pass
    # 再次进入 lifespan（重启场景）
    with TestClient(app):
        pass


def test_spa_history_routes_fall_back_to_index(tmp_path):
    """直接打开 /login 等 history 路由不能返回 FastAPI JSON 404。"""
    from fastapi import FastAPI

    (tmp_path / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=tmp_path, html=True), name="spa")
    with TestClient(app) as client:
        assert client.get("/").text == "<html>spa</html>"
        assert client.get("/login").text == "<html>spa</html>"
        assert client.get("/schedules").text == "<html>spa</html>"
        assert client.get("/api/missing").status_code == 404
        assert client.get("/assets/missing.js").status_code == 404


def test_execution_context_values_are_frozen():
    p = Principal(user_id=1, role="user", permission_revision=0)
    ctx = ExecutionContext(
        run_id="run_" + "0" * 32,
        session_id="sess_" + "1" * 32,
        principal=p,
        source="web",
        channel_account_id=None,
        model_profile_id="default",
        policy_revision=1,
    )
    with pytest.raises(Exception):
        ctx.run_id = "other"  # type: ignore[misc]
    with pytest.raises(Exception):
        p.user_id = 2  # type: ignore[misc]
