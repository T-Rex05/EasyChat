"""FastAPI 应用工厂（架构 §12.2：import 与 create_app 无副作用）。

create_app 只构建路由与中间件：不连数据库、不运行迁移、不读 .env、
不启动任何监听器或后台线程。真实启动在 ASGI lifespan 中调用
bootstrap.run_startup / run_shutdown。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.bootstrap import AppSettings, ModuleRegistry, default_settings, run_shutdown, run_startup
from backend.shared.errors import AppError


def error_to_response(exc: AppError) -> tuple[int, dict]:
    """领域错误 → (HTTP状态码, JSON体)。单一映射点，HTTP边界统一走这里。"""
    return exc.http_status, exc.to_payload()


def create_app(
    settings: AppSettings | None = None,
    registry: ModuleRegistry | None = None,
) -> FastAPI:
    """构建应用实例。settings/registry 缺省时使用显式默认值（无外部依赖）。"""
    if settings is None:
        settings = default_settings()
    if registry is None:
        registry = ModuleRegistry(settings=settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await run_startup(registry)
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await run_shutdown(registry)

    app = FastAPI(title="EasyChat", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.registry = registry
    app.state.ready = False

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        if app.state.ready:
            return JSONResponse({"status": "ready"})
        return JSONResponse({"status": "starting"}, status_code=503)

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        status, payload = error_to_response(exc)
        return JSONResponse(payload, status_code=status)

    return app
