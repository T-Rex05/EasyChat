"""主机白名单 + exec 审批记录 API（借鉴 Eyes host_whitelist/exec_approval_recorder）"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from backend.service.auth.auth_middleware import get_current_user
from backend.service import host_whitelist_service
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/admin", tags=["主机白名单"])


async def _require_whitelist_perm(user: dict = Depends(get_current_user)) -> dict:
    """面板/API 权限：需要 system.manage 权限（可在角色编辑里勾选）。"""
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    if "system.manage" in perms:
        return user
    raise HTTPException(status_code=403, detail="需要系统管理权限（system.manage）")


async def _require_audit_perm(user: dict = Depends(get_current_user)) -> dict:
    """审计日志权限：需要 terminal.audit 权限（可在角色编辑里勾选）。"""
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    if "terminal.audit" in perms:
        return user
    raise HTTPException(status_code=403, detail="需要操作审计查看权限（terminal.audit）")


class HostCreateRequest(BaseModel):
    host_identifier: str = Field(..., min_length=1, description="目标主机 IP/主机名")
    access_user: str = Field(default="", description="登录用户名")
    access_port: int = Field(default=22, ge=1, le=65535)
    auth_method: str = Field(default="none", description="认证方式: password / key / none")
    auth_secret: str = Field(default="", description="SSH 密码或私钥路径（AES 加密存储，更新时空串=保持不变）")
    remark: str = Field(default="")


@router.get("/host-whitelist")
async def list_hosts(admin: dict = Depends(_require_whitelist_perm)):
    """列出全部主机白名单。"""
    return host_whitelist_service.list_hosts()


@router.post("/host-whitelist", status_code=201)
async def add_host(req: HostCreateRequest, admin: dict = Depends(_require_whitelist_perm)):
    """新增白名单主机。"""
    try:
        return host_whitelist_service.add_host(
            host_identifier=req.host_identifier, access_user=req.access_user,
            access_port=req.access_port, remark=req.remark,
            auth_method=req.auth_method, auth_secret=req.auth_secret, created_by=admin["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/host-whitelist/{host_id}")
async def update_host(host_id: int, req: HostCreateRequest, admin: dict = Depends(_require_whitelist_perm)):
    """更新白名单主机。"""
    ok = host_whitelist_service.update_host(
        host_id, host_identifier=req.host_identifier, access_user=req.access_user,
        access_port=req.access_port, remark=req.remark,
        auth_method=req.auth_method, auth_secret=req.auth_secret,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True}


@router.delete("/host-whitelist/{host_id}")
async def delete_host(host_id: int, admin: dict = Depends(_require_whitelist_perm)):
    """删除白名单主机。"""
    ok = host_whitelist_service.delete_host(host_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True}


@router.get("/exec-approvals")
async def list_exec_approvals(
    thread_id: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    admin: dict = Depends(_require_audit_perm),
):
    """查询 exec 审批记录（审计）。"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        if thread_id:
            cur = conn.execute(
                "SELECT * FROM exec_approval_logs WHERE thread_id = %s ORDER BY created_at DESC LIMIT %s",
                (thread_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM exec_approval_logs ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [dict(r) for r in rows]
    finally:
        conn.close()


class HostTestRequest(BaseModel):
    host_identifier: str = Field(..., min_length=1, description="目标主机 IP/主机名")
    access_user: str = Field(default="", description="登录用户名")
    access_port: int = Field(default=22, ge=1, le=65535)
    auth_method: str = Field(default="none", description="认证方式: password / key / none")
    auth_secret: str = Field(default="", description="SSH 密码或私钥路径（测试时明文传入）")
    timeout: int = Field(default=10, ge=3, le=30, description="超时秒数")


@router.post("/host-whitelist/test")
async def test_host_connection(req: HostTestRequest, admin: dict = Depends(_require_whitelist_perm)):
    """测试 SSH 主机连通性（不入库，仅测试）。"""
    import asyncio
    from backend.service.host_whitelist_service import test_ssh_connection
    # paramiko 是阻塞调用，放到线程池避免阻塞事件循环
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: test_ssh_connection(
            host_identifier=req.host_identifier,
            access_user=req.access_user,
            access_port=req.access_port,
            auth_method=req.auth_method,
            auth_secret=req.auth_secret,
            timeout=req.timeout,
        ),
    )
    return result


@router.get("/agent-operations")
async def list_agent_operations(
    thread_id: str = Query(default=""),
    user_id: int = Query(default=None),
    target_host: str = Query(default=""),
    operation_type: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    admin: dict = Depends(_require_audit_perm),
):
    """查询 AI 操作审计日志（留痕）。"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        conditions = []
        params = []
        if thread_id:
            conditions.append("thread_id = %s")
            params.append(thread_id)
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        if target_host:
            conditions.append("target_host = %s")
            params.append(target_host)
        if operation_type:
            conditions.append("operation_type = %s")
            params.append(operation_type)
        where = " AND ".join(conditions) if conditions else "1=1"
        cur = conn.execute(
            f"SELECT * FROM agent_operation_logs WHERE {where} ORDER BY created_at DESC LIMIT %s",
            params + [limit],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/sql-operations")
async def list_sql_operations(
    thread_id: str = Query(default=""),
    user_id: int = Query(default=None),
    status: int = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    admin: dict = Depends(_require_audit_perm),
):
    """查询 SQL 操作审计日志（text2sql 留痕）。"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        conditions = []
        params = []
        if thread_id:
            conditions.append("thread_id = %s")
            params.append(thread_id)
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        if status is not None:
            conditions.append("status = %s")
            params.append(status)
        where = " AND ".join(conditions) if conditions else "1=1"
        cur = conn.execute(
            f"SELECT * FROM sql_operation_logs WHERE {where} ORDER BY created_at DESC LIMIT %s",
            params + [limit],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/users-with-whitelist-perm")
async def list_users_with_whitelist_perm(admin: dict = Depends(_require_audit_perm)):
    """获取拥有主机白名单权限的用户列表（用于审计日志筛选）。"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        # 查询所有用户，然后过滤出有 system.manage 权限的
        cur = conn.execute(
            "SELECT u.id, u.username, u.role FROM users u WHERE u.status = 1 ORDER BY u.username"
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        users = [dict(r) for r in rows]

        # 过滤：admin/super_admin 自动有权限，其他用户检查权限
        result = []
        for user in users:
            role = user.get("role", "")
            if role in ("admin", "super_admin"):
                result.append(user)
            else:
                # 检查是否有 system.manage 权限
                try:
                    from backend.service.auth.permission_service import get_user_permissions
                    perms = get_user_permissions(user["id"])
                    if "system.manage" in perms:
                        result.append(user)
                except Exception:
                    pass
        return result
    finally:
        conn.close()


@router.get("/memory-operations")
async def list_memory_operations(
    user_id: int = Query(default=None),
    action: str = Query(default=""),
    memory_id: int = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(_require_audit_perm),
):
    """查询记忆操作审计日志（CRUD/搜索/晋升/恢复/合并）。"""
    from backend.service.memory_audit_service import query_memory_operations
    return query_memory_operations(
        user_id=user_id,
        action=action or None,
        memory_id=memory_id,
        limit=limit,
        offset=offset,
    )


# ── 用户侧 API：获取当前用户可访问的白名单主机 ──

@router.get("/chat-host-whitelist")
async def get_my_accessible_hosts(user: dict = Depends(get_current_user)):
    """获取当前登录用户可访问的白名单主机列表（用于前端展示）。"""
    user_id = user.get("user_id")
    if not user_id:
        return []
    
    from backend.service.host_whitelist_service import get_user_accessible_hosts
    return get_user_accessible_hosts(int(user_id))