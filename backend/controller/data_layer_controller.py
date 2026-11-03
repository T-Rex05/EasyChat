"""
数据层级管理 API — 层级 CRUD + 用户层级分配 + KB 层级查询。

路由前缀: /api/data-layers
权限:
  - 层级 CRUD / 用户层级分配: admin / super_admin 或 system.manage 权限
  - KB 层级查询: 任何登录用户
  - 当前用户层级查询: 任何登录用户（查自己无需管理员权限）
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.service.auth.auth_middleware import get_current_user
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/data-layers", tags=["data-layers"])


# ── 请求体模型 ──


class CreateLayerRequest(BaseModel):
    name: str
    description: str = ""
    sort_order: int = 0


class UpdateLayerRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class SetUserLayersRequest(BaseModel):
    layer_ids: List[int]


class SetKbLayersRequest(BaseModel):
    layer_ids: List[int]


# ── 权限检查 ──


def _require_admin(user: dict):
    """要求拥有 system.manage 权限（可在角色编辑里勾选）。"""
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    if "system.manage" not in perms:
        raise HTTPException(status_code=403, detail="需要管理员权限: system.manage")


# ════════════════════════════════════════════════════════════
# 层级 CRUD（管理员）
# ════════════════════════════════════════════════════════════


@router.get("")
async def list_layers(user: dict = Depends(get_current_user)):
    """列出所有数据层级（含引用计数）。"""
    from backend.service.auth.data_layer_service import list_layers as _list
    try:
        return {"ok": True, "data": _list()}
    except Exception as e:
        logger.error(f"[DataLayer] 列出层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_layer(req: CreateLayerRequest, user: dict = Depends(get_current_user)):
    """创建新数据层级。"""
    _require_admin(user)
    from backend.service.auth.data_layer_service import create_layer as _create
    try:
        layer = _create(name=req.name, description=req.description, sort_order=req.sort_order)
        return {"ok": True, "data": layer}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DataLayer] 创建层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{layer_id}")
async def update_layer(layer_id: int, req: UpdateLayerRequest, user: dict = Depends(get_current_user)):
    """更新层级名称/描述/排序。"""
    _require_admin(user)
    from backend.service.auth.data_layer_service import update_layer as _update
    try:
        layer = _update(layer_id, name=req.name, description=req.description, sort_order=req.sort_order)
        return {"ok": True, "data": layer}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DataLayer] 更新层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{layer_id}/info")
async def get_layer_info(layer_id: int, user: dict = Depends(get_current_user)):
    """获取层级详情 + 引用计数（删除前弹窗展示用）。"""
    _require_admin(user)
    from backend.service.auth.data_layer_service import get_delete_info
    try:
        info = get_delete_info(layer_id)
        return {"ok": True, "data": info}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[DataLayer] 获取层级信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{layer_id}")
async def delete_layer(layer_id: int, user: dict = Depends(get_current_user)):
    """删除数据层级（有引用时拒绝并返回引用计数）。"""
    _require_admin(user)
    from backend.service.auth.data_layer_service import delete_layer as _delete
    try:
        result = _delete(layer_id)
        return {"ok": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DataLayer] 删除层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# 用户层级分配（管理员操作）
# ════════════════════════════════════════════════════════════


@router.get("/user/{user_id}")
async def get_user_layers(user_id: int, user: dict = Depends(get_current_user)):
    """获取指定用户的可见层级列表（管理员操作；查自己无需管理员权限）。"""
    requesting_user_id = user.get("user_id", 0)
    # 查自己不需要管理员权限
    if requesting_user_id != user_id:
        _require_admin(user)
    from backend.service.auth.data_layer_service import get_user_layers as _get
    try:
        layer_ids = _get(user_id)
        return {"ok": True, "user_id": user_id, "layer_ids": layer_ids}
    except Exception as e:
        logger.error(f"[DataLayer] 获取用户层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/user/{user_id}")
async def set_user_layers(user_id: int, req: SetUserLayersRequest, user: dict = Depends(get_current_user)):
    """设置指定用户的可见层级。"""
    _require_admin(user)
    from backend.service.auth.data_layer_service import set_user_layers as _set
    try:
        result = _set(user_id, req.layer_ids)
        return {"ok": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DataLayer] 设置用户层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# 当前用户层级（任何登录用户可查）
# ════════════════════════════════════════════════════════════


@router.get("/my")
async def get_my_layers(user: dict = Depends(get_current_user)):
    """获取当前登录用户的可见层级列表。"""
    user_id = user.get("user_id", 0)
    from backend.service.auth.data_layer_service import get_user_layers as _get
    try:
        layer_ids = _get(user_id)
        return {"ok": True, "user_id": user_id, "layer_ids": layer_ids}
    except Exception as e:
        logger.error(f"[DataLayer] 获取当前用户层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# KB 层级（任何登录用户可查，管理员可改）
# ════════════════════════════════════════════════════════════


@router.get("/kb/{kb_id}")
async def get_kb_layers(kb_id: int, user: dict = Depends(get_current_user)):
    """获取知识库关联的数据层级。"""
    from backend.service.auth.data_layer_service import get_kb_layers as _get
    try:
        layer_ids = _get(kb_id)
        return {"ok": True, "kb_id": kb_id, "layer_ids": layer_ids}
    except Exception as e:
        logger.error(f"[DataLayer] 获取 KB 层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/kb/{kb_id}")
async def set_kb_layers(kb_id: int, req: SetKbLayersRequest, user: dict = Depends(get_current_user)):
    """设置知识库关联的数据层级（管理员）。"""
    _require_admin(user)
    from backend.service.auth.data_layer_service import set_kb_layers as _set
    try:
        result = _set(kb_id, req.layer_ids)
        return {"ok": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DataLayer] 设置 KB 层级失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
