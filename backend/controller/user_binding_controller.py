"""用户绑定 API — 管理用户与平台（微信/飞书）的绑定关系

端点：
- GET    /api/user-bindings           获取当前用户绑定列表
- POST   /api/user-bindings           添加绑定
- DELETE /api/user-bindings/{id}      删除绑定
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.service.auth.auth_middleware import get_current_user
from backend.utils.log_utils import log
import asyncio
import os

logger = log
router = APIRouter(prefix="/api/user-bindings", tags=["user-bindings"])


def _get_conn():
    from backend.db.connection_pool import get_pool_connection
    return get_pool_connection()


class BindingCreate(BaseModel):
    platform: str = Field(description="平台: wechat / feishu")
    open_id: str = Field(description="平台用户标识（微信ID/飞书open_id）")
    nickname: str = Field(default="", description="对方昵称（可选）")


@router.get("")
async def list_bindings(user: dict = Depends(get_current_user)):
    """获取当前用户的平台绑定列表。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, platform, open_id, nickname, enabled, created_at FROM user_bindings WHERE user_id = %s",
            (user["user_id"],),
        )
        return {"bindings": cur.fetchall()}
    finally:
        conn.close()


@router.post("")
async def create_binding(req: BindingCreate, user: dict = Depends(get_current_user)):
    """绑定一个平台账号到当前用户。一个用户在一个平台只能绑定一个账号。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()

        # 检查该平台是否已绑定
        cur.execute(
            "SELECT id FROM user_bindings WHERE user_id = %s AND platform = %s",
            (user["user_id"], req.platform),
        )
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"该用户已绑定{req.platform}账号，请先解绑")

        # 检查该 open_id 是否已被其他用户绑定
        cur.execute(
            "SELECT id, user_id FROM user_bindings WHERE platform = %s AND open_id = %s",
            (req.platform, req.open_id),
        )
        existing = cur.fetchone()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"该{req.platform}账号已被用户 {existing['user_id']} 绑定",
            )

        cur.execute(
            "INSERT INTO user_bindings (user_id, platform, open_id, nickname) VALUES (%s, %s, %s, %s)",
            (user["user_id"], req.platform, req.open_id, req.nickname or ""),
        )
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()


@router.delete("/{binding_id}")
async def delete_binding(binding_id: int, user: dict = Depends(get_current_user)):
    """删除绑定。普通用户只能删自己的，超管可以删任意。
    解绑微信时同步更新 platform_config.enabled = 0 并重启监听器。
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, platform FROM user_bindings WHERE id = %s", (binding_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="绑定不存在")

        is_super = user.get("role") == "super_admin"
        if not is_super and row["user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权删除他人绑定")

        platform = row["platform"]
        cur.execute("DELETE FROM user_bindings WHERE id = %s", (binding_id,))

        # 超管解绑微信 → 停用 platform_config，通知监听器
        if platform == "wechat" and is_super:
            cur.execute("UPDATE platform_config SET enabled = 0 WHERE platform = 'wechat'")

        return {"ok": True, "deleted": binding_id}
    finally:
        conn.close()
        # 解绑后重启监听器（会检测到没有凭证自动停止）
        # 用 to_thread：restart_wechat_listener 内部有 time.sleep(1) + 同步 MySQL，
        # 直接在事件循环里调会把**整个进程**卡住 1 秒（保持其同步签名不变）。
        if platform == "wechat":
            try:
                from backend.controller.wechat_listener import restart_wechat_listener
                await asyncio.to_thread(restart_wechat_listener)
            except ImportError:
                pass
