"""
认证中间件 — FastAPI 依赖注入

用法：
    from fastapi import Depends
    from backend.service.auth.auth_middleware import get_current_user, require_perm

    # 必须登录
    @router.get("/api/protected")
    async def protected(user: dict = Depends(get_current_user)):
        return {"hello": user["username"]}

    # 需要特定权限
    @router.get("/api/review")
    async def review(user: dict = Depends(require_perm("review.view"))):
        return {"review": True}

    # 仅超级管理员
    @router.post("/api/admin/users")
    async def manage_users(user: dict = Depends(require_perm("system.manage"))):
        return {"managed": True}
"""
from fastapi import Depends, HTTPException, Header, Response
from typing import Optional

from backend.service.auth.auth_service import verify_token, check_token_renewal


async def get_current_user(
    authorization: Optional[str] = Header(None),
    response: Response = None,
) -> dict:
    """必须登录才能访问。返回用户信息（含 permissions 集合 + hermes_tools）。

    滑动窗口续期：当 token 剩余有效期 < 阈值时，自动签发新 token
    并通过 X-New-Token 响应头返回给前端。
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="请先登录")

    token = authorization.replace("Bearer ", "").strip()
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token 无效或已过期，请重新登录")

    # 滑动窗口续期：检查是否需要签发新 token
    if response is not None:
        new_token = check_token_renewal(token)
        if new_token:
            response.headers["X-New-Token"] = new_token

    # 附加权限集合 + Hermes 工具集
    from backend.permission.checker import get_user_permissions, get_user_hermes_tools
    user["permissions"] = get_user_permissions(user["user_id"])
    user["hermes_tools"] = get_user_hermes_tools(user["user_id"])
    return user


def require_perm(permission: str):
    """需要特定权限才能访问。返回 FastAPI 依赖函数。"""
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if permission not in user.get("permissions", set()):
            raise HTTPException(
                status_code=403,
                detail=f"缺少权限: {permission}",
            )
        return user
    return _check


async def require_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    """必须管理员角色（admin 或 super_admin）。"""
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def require_super_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    """必须超级管理员角色。"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return user


async def optional_user(
    authorization: Optional[str] = Header(None),
) -> Optional[dict]:
    """可选认证 — 有 Token 就解析，没有也不报错。"""
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    user = verify_token(token)
    if user:
        from backend.permission.checker import get_user_permissions, get_user_hermes_tools
        user["permissions"] = get_user_permissions(user["user_id"])
        user["hermes_tools"] = get_user_hermes_tools(user["user_id"])
    return user
