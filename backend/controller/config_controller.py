"""系统配置 API — 读写模型参数到数据库"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.service.auth.auth_middleware import get_current_user, require_perm
from backend.service.auth.permission_service import has_permission
from backend.utils.log_utils import log
import os

logger = log
router = APIRouter(prefix="/api/config", tags=["config"])


class SaveConfigRequest(BaseModel):
    key: str = Field(description="配置键")
    value: str = Field(default="", description="配置值")


def _get_mysql():
    """获取 MySQL 连接（走统一连接池）。"""
    from backend.db.connection_pool import get_pool_connection
    return get_pool_connection()


@router.get("")
async def get_config(user: dict = Depends(get_current_user)):
    """获取当前用户的系统配置（api_key 脱敏显示）。"""
    from backend.utils.crypto_utils import decrypt
    conn = _get_mysql()
    try:
        cur = conn.cursor()
        cur.execute("SELECT config_key, config_val FROM user_configs WHERE user_id = %s", (user["user_id"],))
        result = {}
        for r in cur.fetchall():
            val = r["config_val"]
            if r["config_key"] == "llm_api_key" and val:
                try:
                    decrypted = decrypt(val)
                    val = "****" + decrypted[-4:] if len(decrypted) > 4 else "****"
                except Exception:
                    val = "****"
            result[r["config_key"]] = val
        return result
    finally:
        conn.close()


@router.post("")
async def save_config(req: SaveConfigRequest, user: dict = Depends(get_current_user)):
    """保存配置项到数据库（api_key 自动加密）。
    personal_email 允许所有登录用户保存，其他 key 需要 system.config 权限。"""
    # 非 personal_email 需要 system.config 权限
    if req.key != "personal_email" and not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="需要 system.config 权限")

    val = req.value
    if req.key in ("llm_api_key",) and val:
        from backend.utils.crypto_utils import encrypt
        val = encrypt(val)
    conn = _get_mysql()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user_configs (user_id, config_key, config_val) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE config_val = VALUES(config_val)",
            (user["user_id"], req.key, val),
        )
        conn.commit()
        return {"ok": True, "key": req.key}
    finally:
        conn.close()
