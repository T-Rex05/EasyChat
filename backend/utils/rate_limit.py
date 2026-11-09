"""无凭据端点的进程内限流（登录/注册），零外部依赖。

只保护未认证端点：固定窗口按客户端 IP 计数，超限返回 429。
- /api/auth/login    5 次/分钟（防暴力破解）
- /api/auth/register 3 次/分钟（防批量注册）

单 worker 部署（SQLite + 进程内调度）进程内即全局；多副本部署必须由
外层网关限流。默认关闭（default_settings 供测试/工厂使用），生产入口
settings_from_environment 开启（EASYCHAT_AUTH_RATE_LIMIT 可显式关闭）。
"""
from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

# route -> (窗口内最大次数, 窗口秒数)
AUTH_LIMITS: dict[str, tuple[int, float]] = {
    "/api/auth/login": (5, 60.0),
    "/api/auth/register": (3, 60.0),
}


class AuthRateLimiter:
    """固定窗口计数器；线程安全（中间件可能在任意事件循环线程触发）。"""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, client: str, route: str) -> bool:
        max_hits, window = AUTH_LIMITS[route]
        now = self._clock()
        bucket = (client, route)
        with self._lock:
            recent = [t for t in self._hits.get(bucket, ()) if now - t < window]
            if len(recent) >= max_hits:
                self._hits[bucket] = recent
                return False
            recent.append(now)
            self._hits[bucket] = recent
            # 有界：窗口滑出后条目自然失效；这里顺手清理已空桶防止键堆积。
            if not recent:
                self._hits.pop(bucket, None)
            return True


def client_key(request: Request) -> str:
    """直连部署取直连地址；反代部署应配置并转发 X-Forwarded-For。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def make_auth_rate_limit_middleware(limiter: AuthRateLimiter) -> Any:
    async def auth_rate_limit_middleware(request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        route = request.url.path
        if request.method == "POST" and route in AUTH_LIMITS:
            if not limiter.allow(client_key(request), route):
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limited", "message": "请求过于频繁，请稍后再试"},
                )
        return await call_next(request)

    return auth_rate_limit_middleware
