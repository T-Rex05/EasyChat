"""
管理后台 API — 用户管理 / 角色管理 / 权限树 / 内容池审核

端点：
    GET    /api/admin/users              — 列出所有用户
    PUT    /api/admin/users/{id}/role    — 修改用户角色
    GET    /api/admin/users/{id}/perms   — 查看用户权限
    PUT    /api/admin/users/{id}/perms   — 设置用户权限
    PUT    /api/admin/users/{id}/status  — 启用/禁用用户
    GET    /api/admin/permissions        — 权限分组树
    GET    /api/admin/roles              — 列出所有角色
    POST   /api/admin/roles              — 创建角色
    PUT    /api/admin/roles/{id}         — 更新角色
    DELETE /api/admin/roles/{id}         — 删除角色
    GET    /api/admin/pool/pending       — 待审核内容池
    POST   /api/admin/pool/{id}/approve  — 审核通过
    POST   /api/admin/pool/{id}/reject   — 审核拒绝
    POST   /api/admin/pool/force-publish — 管理员强制发布
    DELETE /api/admin/pool/{name}        — 下架池中内容
"""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.service.auth.auth_middleware import get_current_user, require_perm
from backend.service.auth.auth_service import AuthService
from backend.service.auth.permission_service import (
    get_user_role, set_user_role, get_user_permissions,
    set_user_permission, get_user_perm_overrides,
)
from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/admin", tags=["admin"])
auth = AuthService()


# ── 请求模型 ──

class SetRoleRequest(BaseModel):
    role: str = Field(description="新角色: super_admin / admin / user")


class SetPermsRequest(BaseModel):
    permissions: List[dict] = Field(description="权限列表 [{permission, granted}]")


class SetStatusRequest(BaseModel):
    status: int = Field(description="1=启用 0=禁用")


# ── 端点 ──

@router.get("/users")
async def list_users(user: dict = Depends(require_perm("system.manage"))):
    """列出所有用户（含角色和权限概要）。"""
    users = auth.list_users()
    result = []
    for u in users:
        perms = get_user_permissions(u["id"])
        overrides = get_user_perm_overrides(u["id"])
        result.append({
            **u,
            "permissions": sorted(perms),
            "perm_overrides": overrides,
        })
    return result


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    req: SetRoleRequest,
    admin: dict = Depends(require_perm("system.manage")),
):
    """修改用户角色（仅超级管理员）。"""
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")

    try:
        set_user_role(user_id, req.role)
        return {"ok": True, "user_id": user_id, "new_role": req.role}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users/{user_id}/perms")
async def get_user_perms(
    user_id: int,
    admin: dict = Depends(require_perm("system.manage")),
):
    """查看用户的有效权限（角色默认 + 自定义覆盖）。"""
    role = get_user_role(user_id)
    perms = get_user_permissions(user_id)
    overrides = get_user_perm_overrides(user_id)
    return {
        "user_id": user_id,
        "role": role,
        "effective_permissions": sorted(perms),
        "overrides": overrides,
    }


@router.put("/users/{user_id}/perms")
async def update_user_perms(
    user_id: int,
    req: SetPermsRequest,
    admin: dict = Depends(require_perm("system.manage")),
):
    """批量设置用户权限覆盖。"""
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="不能修改自己的权限")

    for item in req.permissions:
        perm = item.get("permission", "")
        granted = item.get("granted", True)
        if perm:
            set_user_permission(user_id, perm, granted)

    return {"ok": True, "user_id": user_id}


@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    req: SetStatusRequest,
    admin: dict = Depends(require_perm("system.manage")),
):
    """启用/禁用用户。"""
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET status = %s, updated_at = NOW() WHERE id = %s",
            (req.status, user_id),
        )
        conn.commit()
        return {"ok": True, "user_id": user_id, "status": req.status}
    finally:
        conn.close()


@router.get("/permissions")
async def list_all_permissions(admin: dict = Depends(get_current_user)):
    """返回权限分组树结构。"""
    from backend.permission.registry import get_permission_tree
    return get_permission_tree()


@router.get("/toolsets")
async def list_toolset_definitions(admin: dict = Depends(require_perm("system.manage"))):
    """返回全部 toolset 定义（角色管理的「AI 对话工具」选项，单一数据源）。"""
    from backend.permission.builtin import TOOLSET_DEFINITIONS
    return TOOLSET_DEFINITIONS


# ── 角色管理（超级管理员专用） ──

class CreateRoleRequest(BaseModel):
    name: str = Field(description="角色标识（如 ops_engineer）")
    display_name: str = Field(description="显示名称（如 运维工程师）")
    description: str = Field(default="", description="角色描述")
    permissions: list = Field(default_factory=list, description="权限列表")
    hermes_tools: list = Field(default_factory=list, description="Hermes 工具集")


class UpdateRoleRequest(BaseModel):
    name: str = Field(default=None)
    display_name: str = Field(default=None)
    description: str = Field(default=None)
    permissions: list = Field(default=None)
    hermes_tools: list = Field(default=None)


@router.get("/roles")
async def list_roles_handler(admin: dict = Depends(require_perm("system.manage"))):
    """列出所有自定义角色（含权限）。"""
    from backend.service.auth.permission_service import list_roles
    return list_roles()


@router.post("/roles")
async def create_role_handler(req: CreateRoleRequest, admin: dict = Depends(require_perm("system.manage"))):
    """创建自定义角色。"""
    from backend.service.auth.permission_service import create_role
    try:
        return create_role(req.name, req.display_name, req.description, req.permissions, req.hermes_tools)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/roles/{role_id}")
async def update_role_handler(role_id: int, req: UpdateRoleRequest, admin: dict = Depends(require_perm("system.manage"))):
    """更新角色（名称、显示名、权限）。"""
    from backend.service.auth.permission_service import update_role
    try:
        update_role(
            role_id,
            name=req.name,
            display_name=req.display_name,
            description=req.description,
            permissions=req.permissions,
            hermes_tools=req.hermes_tools,
        )
        return {"ok": True, "role_id": role_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/roles/{role_id}")
async def delete_role_handler(role_id: int, admin: dict = Depends(require_perm("system.manage"))):
    """删除自定义角色（内置角色不可删）。"""
    from backend.service.auth.permission_service import delete_role
    try:
        delete_role(role_id)
        return {"ok": True, "role_id": role_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 内容池审核（管理员） ──

class PoolApproveRequest(BaseModel):
    comment: str = Field(default="")


def _can_review(user: dict, content_type: str = None) -> bool:
    """内容池审核权限：**只认 `skill.pool.review`**（可在角色编辑里勾选）。

    此前写成「`skill.pool.review` **或** `skill.manage`」，会让「技能池审核」这个
    勾选框失去唯一性 —— 取消勾选后只要还留着「管理全部技能」，菜单与接口照样放行，
    与已修复的 `kb.eval` 属同一类问题。审核是独立能力，应由它自己的权限决定。

    注：`skill.manage` 仍是「管理全部技能」与「发布时免审」的依据（见
    `skill_service._can_skip_review`），两处语义不同，不要混。
    """
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    # 记忆分享已移除，仅保留技能审核
    if content_type in (None, "", "skill") and "skill.pool.review" in perms:
        return True
    return False


def _require_review(user: dict, content_type: str = None):
    if not _can_review(user, content_type):
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=403, detail="需要技能池审核权限（skill.pool.review）")


class ForcePublishRequest(BaseModel):
    content_type: str = Field(description="skill")
    content_name: str = Field(description="内容名称")
    owner_id: int = Field(description="所有者 user_id")


@router.get("/pool/pending")
async def list_pending_items(type: str = None, user: dict = Depends(get_current_user)):
    """列出待审核的内容池提交（skill/tool 来自 content_pool）。"""
    _require_review(user, type)
    conn = get_conn()
    try:
        query = """SELECT cp.*, u.username as owner_name
                   FROM content_pool cp JOIN users u ON cp.owner_id = u.id
                   WHERE cp.status = 'pending'"""
        params = []
        if type:
            query += " AND cp.content_type = %s"
            params.append(type)
        query += " ORDER BY cp.created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/pool/{pool_id}/approve")
async def approve_pool_item(pool_id: int, user: dict = Depends(get_current_user)):
    """审核通过。"""
    conn = get_conn()
    try:
        # 获取池记录信息
        row = conn.execute(
            "SELECT content_type, content_name FROM content_pool WHERE id = %s",
            (pool_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="审核记录不存在")
        
        content_type = row["content_type"] if row else None
        _require_review(user, content_type)

        conn.execute(
            """UPDATE content_pool
               SET status = 'active', reviewed_by = %s, reviewed_at = NOW()
               WHERE id = %s""",
            (user["user_id"], pool_id),
        )
        conn.commit()

        return {"ok": True, "status": "active"}
    finally:
        conn.close()


@router.post("/pool/{pool_id}/reject")
async def reject_pool_item(pool_id: int, req: PoolApproveRequest, user: dict = Depends(get_current_user)):
    """审核拒绝。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT content_type FROM content_pool WHERE id = %s",
            (pool_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="审核记录不存在")
        _require_review(user, row["content_type"] if row else None)
        conn.execute(
            """UPDATE content_pool
               SET status = 'rejected', reviewed_by = %s, reviewed_at = NOW(),
                   reject_reason = %s
               WHERE id = %s""",
            (user["user_id"], req.comment, pool_id),
        )
        conn.commit()
        return {"ok": True, "status": "rejected"}
    finally:
        conn.close()


@router.post("/pool/force-publish")
async def force_publish(req: ForcePublishRequest, user: dict = Depends(get_current_user)):
    """管理员强制发布内容到池子（跳过审核）。"""
    _require_review(user, req.content_type)
    conn = get_conn()
    try:
        conn.execute(
            """REPLACE INTO content_pool
               (content_type, content_name, owner_id, submitted_by, status, reviewed_by, reviewed_at, created_at)
               VALUES (%s, %s, %s, %s, 'active', %s, NOW(), NOW())""",
            (req.content_type, req.content_name, req.owner_id, user["user_id"], user["user_id"]),
        )
        conn.commit()
        return {"ok": True, "status": "active"}
    finally:
        conn.close()


@router.delete("/pool/{pool_name}")
async def remove_from_pool(pool_name: str, content_type: str = "skill", user: dict = Depends(get_current_user)):
    """管理员下架池中内容。"""
    _require_review(user, content_type)
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE content_pool SET status = 'removed' WHERE content_name = %s AND content_type = %s AND status = 'active'",
            (pool_name, content_type),
        )
        conn.commit()
        return {"ok": True, "status": "removed"}
    finally:
        conn.close()
