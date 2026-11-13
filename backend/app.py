"""FastAPI 应用工厂（架构 §12.2：import 与 create_app 无副作用）。

create_app 只构建路由与中间件：不连数据库、不运行迁移、不读 .env、
不启动任何监听器或后台线程。真实启动在 ASGI lifespan 中调用
bootstrap.run_startup / run_shutdown。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.bootstrap import AppSettings, ModuleRegistry, default_settings, run_shutdown, run_startup
from backend.shared.errors import AppError, CapabilityUnavailableError
from backend.utils.rate_limit import AuthRateLimiter, make_auth_rate_limit_middleware


class SPAStaticFiles(StaticFiles):
    """Vue history 路由回退：非 API/静态资源 404 时返回 index.html。

    `/login`、`/schedules` 等前端路由在刷新或直接打开时不能落到 FastAPI 的
    JSON 404；`/api/*` 与带扩展名的缺失资源仍保持真实 404。
    """

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if (
                exc.status_code != 404
                or self._is_api_scope(scope)
                or not self._is_spa_path(path)
            ):
                raise
            return await super().get_response("index.html", scope)

    @staticmethod
    def _is_api_scope(scope) -> bool:
        request_path = str(scope.get("path") or "")
        return request_path == "/api" or request_path.startswith("/api/")

    @staticmethod
    def _is_spa_path(path: str) -> bool:
        if path == "api" or path.startswith("api/"):
            return False
        return "." not in path.rsplit("/", 1)[-1]


class _LazyModule:
    """请求期解析 bootstrap 构造的模块；未就绪时明确 503，不在工厂期连库。"""

    def __init__(self, registry: ModuleRegistry, name: str) -> None:
        self._registry = registry
        self._name = name

    def __getattr__(self, item: str):
        service = getattr(self._registry, self._name, None)
        if service is None:
            raise CapabilityUnavailableError(f"模块未就绪: {self._name}")
        return getattr(service, item)


def _authenticate(registry: ModuleRegistry):
    def authenticate(token: str):
        access = registry.access
        if access is None:
            raise CapabilityUnavailableError("认证模块未就绪")
        return access.authenticate_token(token)

    return authenticate


def _authenticate_ticket(registry: ModuleRegistry):
    def authenticate_ticket(ticket: str):
        access = registry.access
        if access is None:
            raise CapabilityUnavailableError("认证模块未就绪")
        return access.consume_sse_ticket(ticket)

    return authenticate_ticket


def _register_explicit_routers(app: FastAPI, registry: ModuleRegistry) -> None:
    """Task 15：显式注册新模块路由，不扫描 backend/controller。"""
    from backend.modules.access.routes import build_access_router
    from backend.modules.assistant.routes import build_web_chat_router
    from backend.modules.assistant.compat import build_assistant_compat_router
    from backend.modules.channels.routes import build_channels_router
    from backend.modules.delivery.routes import build_delivery_router
    from backend.modules.delivery.smtp import build_email_compat_router, build_email_router
    from backend.modules.evolution.routes import build_evolution_router
    from backend.modules.files.routes import build_files_router
    from backend.modules.inbox.routes import build_inbox_router
    from backend.modules.ledger.routes import build_ledger_router
    from backend.modules.memory.routes import build_memory_router
    from backend.modules.models.routes import build_models_router
    from backend.modules.profiles.routes import build_profiles_router
    from backend.modules.scheduling.routes import build_scheduling_router
    from backend.modules.skills.routes import build_skills_router
    from backend.modules.mcp.routes import build_mcp_router
    from backend.modules.superagent.routes import build_superagent_router
    from backend.modules.usage.routes import build_usage_router

    authenticate = _authenticate(registry)
    authenticate_ticket = _authenticate_ticket(registry)
    app.include_router(build_access_router(_LazyModule(registry, "access")))
    app.include_router(build_usage_router(_LazyModule(registry, "usage"), authenticate))
    app.include_router(build_models_router(_LazyModule(registry, "models"), authenticate))
    app.include_router(build_web_chat_router(_LazyModule(registry, "assistant"), authenticate, authenticate_ticket))
    app.include_router(build_assistant_compat_router(
        authenticate, _LazyModule(registry, "assistant"), _LazyModule(registry, "files"),
    ))
    app.include_router(build_channels_router(_LazyModule(registry, "channels"), authenticate))
    app.include_router(build_files_router(_LazyModule(registry, "files"), authenticate))
    app.include_router(build_ledger_router(_LazyModule(registry, "ledger"), authenticate))
    app.include_router(build_profiles_router(_LazyModule(registry, "profiles"), authenticate))
    app.include_router(build_inbox_router(_LazyModule(registry, "inbox"), authenticate))
    app.include_router(build_scheduling_router(
        _LazyModule(registry, "scheduling"), _LazyModule(registry, "channels"), authenticate,
    ))
    app.include_router(build_delivery_router(_LazyModule(registry, "delivery"), authenticate))
    app.include_router(build_email_router(_LazyModule(registry, "email"), authenticate))
    app.include_router(build_email_compat_router(_LazyModule(registry, "email"), authenticate))
    app.include_router(build_memory_router(_LazyModule(registry, "memory"), authenticate))
    app.include_router(build_skills_router(_LazyModule(registry, "skills"), authenticate))
    app.include_router(build_mcp_router(_LazyModule(registry, "mcp"), authenticate))
    app.include_router(build_superagent_router(_LazyModule(registry, "superagent"), authenticate))
    # GitHub webhook：验签保护（无 JWT）；模块未就绪时 503 由 _LazyModule 兜底
    from backend.modules.superagent.webhooks import build_superagent_webhook_router

    app.include_router(build_superagent_webhook_router(_LazyModule(registry, "superagent_webhooks")))
    app.include_router(build_evolution_router(
        _LazyModule(registry, "evolution"), _LazyModule(registry, "adoption"), authenticate,
    ))


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
    # 登录/注册限流（审计 #5）：生产配置默认开启；测试工厂缺省关闭
    app.state.auth_rate_limiter = AuthRateLimiter()
    if settings.auth_rate_limit_enabled:
        app.middleware("http")(
            make_auth_rate_limit_middleware(app.state.auth_rate_limiter)
        )
    _register_explicit_routers(app, registry)

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

    # 生产镜像把前端 dist 放到 /app/static；API 路由已先注册，挂载在最后不吞接口。
    static_dir = Path(__file__).resolve().parents[1] / "static"
    if (static_dir / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="spa")

    return app
