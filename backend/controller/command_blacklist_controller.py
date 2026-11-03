"""命令黑名单管理 API"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from backend.service.auth.auth_middleware import get_current_user
from backend.service import command_blacklist_service
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/admin", tags=["命令黑名单"])


async def _require_blacklist_perm(user: dict = Depends(get_current_user)) -> dict:
    """权限检查：需要 system.manage 权限（可在角色编辑里勾选）。"""
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    if "system.manage" in perms:
        return user
    raise HTTPException(status_code=403, detail="需要系统管理权限（system.manage）")


class BlacklistRuleCreateRequest(BaseModel):
    pattern: str = Field(..., min_length=1, description="正则表达式")
    description: str = Field(default="", description="规则描述")
    enabled: bool = Field(default=True, description="是否启用")


class PatternSuggestRequest(BaseModel):
    description: str = Field(..., min_length=1, description="用中文描述想拦截的命令行为")


@router.get("/command-blacklist")
async def list_rules(
    enabled_only: bool = False,
    admin: dict = Depends(_require_blacklist_perm),
):
    """列出所有命令黑名单规则。"""
    return command_blacklist_service.list_rules(enabled_only=enabled_only)


@router.post("/command-blacklist", status_code=201)
async def add_rule(
    req: BlacklistRuleCreateRequest,
    admin: dict = Depends(_require_blacklist_perm),
):
    """添加一条命令黑名单规则。"""
    try:
        return command_blacklist_service.add_rule(
            pattern=req.pattern,
            description=req.description,
            enabled=req.enabled,
            created_by=admin.get("user_id"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/command-blacklist/{rule_id}")
async def update_rule(
    rule_id: int,
    req: BlacklistRuleCreateRequest,
    admin: dict = Depends(_require_blacklist_perm),
):
    """更新一条命令黑名单规则。"""
    ok = command_blacklist_service.update_rule(
        rule_id,
        pattern=req.pattern,
        description=req.description,
        enabled=req.enabled,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="更新失败（正则表达式不合法或规则不存在）")
    return {"ok": True}


@router.delete("/command-blacklist/{rule_id}")
async def delete_rule(
    rule_id: int,
    admin: dict = Depends(_require_blacklist_perm),
):
    """删除一条命令黑名单规则。"""
    ok = command_blacklist_service.delete_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"ok": True}


@router.post("/command-blacklist/test")
async def test_pattern(
    req: BlacklistRuleCreateRequest,
    admin: dict = Depends(_require_blacklist_perm),
):
    """测试正则表达式是否合法（不入库）。"""
    import re
    pattern = (req.pattern or "").strip()
    if not pattern:
        raise HTTPException(status_code=400, detail="正则表达式不能为空")
    
    try:
        re.compile(pattern, re.IGNORECASE)
        return {"ok": True, "message": "正则表达式合法"}
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"正则表达式不合法: {e}")


@router.post("/command-blacklist/ai-suggest")
async def ai_suggest_pattern(
    req: PatternSuggestRequest,
    admin: dict = Depends(_require_blacklist_perm),
):
    """AI 辅助生成正则表达式草稿（不入库）。"""
    from backend.service.command_blacklist_ai import generate_pattern_suggestion
    
    user_id = admin.get("user_id")
    try:
        result = generate_pattern_suggestion(req.description, user_id)
        return result
    except Exception as e:
        logger.error(f"[CommandBlacklist] AI 生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
