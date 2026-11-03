"""
API 限流配置 — 基于 slowapi

全局默认限流宽松（120/分钟），敏感端点单独加严：
  - /api/auth/login      5/分钟    （防暴力破解）
  - /api/auth/register   3/分钟    （防批量注册）
  - /chat/stream         60/分钟   （正常对话足够）

用法（在端点函数上装饰）：
    from backend.utils.rate_limit import limiter

    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(...):
        ...
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# 全局 limiter 单例，跨 controller 共享
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    headers_enabled=False,  # 关闭响应头注入 — 避免与无 response 参数的端点冲突
)
