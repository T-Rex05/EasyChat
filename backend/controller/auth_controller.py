"""
认证 API — 用户注册/登录/信息查询

端点：
    POST   /api/auth/register     — 用户注册
    POST   /api/auth/login        — 用户登录
    GET    /api/auth/me           — 获取当前用户信息（需 Token）
    GET    /api/auth/users        — 列出所有用户（管理员）
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field
from typing import Optional

from backend.service.auth.auth_middleware import get_current_user, require_perm
from backend.service.auth.auth_service import AuthService, renew_token, verify_token
from backend.utils.log_utils import log
from backend.utils.rate_limit import limiter

logger = log

router = APIRouter(prefix="/api/auth", tags=["auth"])
auth = AuthService()


# ── 请求模型 ──

class RegisterRequest(BaseModel):
    username: str = Field(description="用户名（至少 2 字符）")
    password: str = Field(description="密码（至少 6 字符）")
    email: str = Field(default="", description="邮箱（可选）")


class LoginRequest(BaseModel):
    username: str = Field(description="用户名")
    password: str = Field(description="密码")


# ── 端点 ──

@router.post("/register")
@limiter.limit("3/minute")
async def register(request: Request, req: RegisterRequest):
    """注册新用户。"""
    try:
        result = auth.register(req.username, req.password, req.email)
        from backend.service.auth.permission_service import get_user_permissions
        result["permissions"] = sorted(get_user_permissions(result["user_id"]))
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, req: LoginRequest):
    """用户登录。"""
    try:
        result = auth.login(req.username, req.password)
        # 附加权限集合 + hermes 工具集
        from backend.service.auth.permission_service import get_user_permissions, get_user_hermes_tools
        result["permissions"] = sorted(get_user_permissions(result["user_id"]))
        result["hermes_tools"] = get_user_hermes_tools(result["user_id"])
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息（含权限列表）。"""
    user_detail = auth.get_user(user["user_id"])
    if not user_detail:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 附加权限集合 + hermes 工具集
    from backend.service.auth.permission_service import get_user_permissions, get_user_hermes_tools
    user_detail["permissions"] = sorted(get_user_permissions(user["user_id"]))
    user_detail["hermes_tools"] = get_user_hermes_tools(user["user_id"])
    return user_detail


@router.post("/refresh")
async def refresh_token(request: Request, authorization: Optional[str] = Header(None)):
    """刷新即将过期或已过期的 Token（宽限期内免登录）。

    - Token 未过期但在续期窗口内 → 刷新成功
    - Token 已过期但在宽限期内（默认 7 天）→ 刷新成功
    - Token 过期超出宽限期 / 签名无效 → 401，需重新登录
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少 Token，请重新登录")

    token = authorization.replace("Bearer ", "").strip()

    # 先尝试正常验证（未过期但在续期窗口内）
    from backend.service.auth.auth_service import check_token_renewal
    new_token = check_token_renewal(token)

    # 如果未触发滑动窗口续期，再尝试过期宽限期刷新
    if not new_token:
        new_token = renew_token(token)

    if not new_token:
        raise HTTPException(status_code=401, detail="Token 已失效，请重新登录")

    # 解析新 token 返回用户信息
    user_info = verify_token(new_token)
    if not user_info:
        raise HTTPException(status_code=401, detail="Token 刷新异常，请重新登录")

    from backend.service.auth.permission_service import get_user_permissions, get_user_hermes_tools
    return {
        "ok": True,
        "token": new_token,
        "user_id": user_info["user_id"],
        "username": user_info["username"],
        "role": user_info["role"],
        "permissions": sorted(get_user_permissions(user_info["user_id"])),
        "hermes_tools": get_user_hermes_tools(user_info["user_id"]),
    }


@router.get("/users")
async def list_users(user: dict = Depends(require_perm("system.manage"))):
    """列出所有用户（需要 system.manage 权限，可在角色编辑里勾选）。"""
    return auth.list_users()
