"""
技能管理 API — RESTful 端点（含权限控制）
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os

from backend.service import skill_service
from backend.service.auth.auth_middleware import get_current_user, optional_user, require_perm
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.put("/{name}/toggle")
async def toggle_skill(name: str, user: dict = Depends(get_current_user)):
    """启用/禁用技能（需要 skill.manage 权限，可在角色编辑里勾选）。"""
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    if "skill.manage" not in perms:
        raise HTTPException(status_code=403, detail="需要 skill.manage 权限")
    from backend.service.skill_service import toggle_item_status
    enabled = toggle_item_status("skill", name)
    return {"name": name, "enabled": enabled}


# ── Models ──

class SkillCreateRequest(BaseModel):
    name: str = Field(description="技能名称")
    content: str = Field(description="技能内容（Markdown）")
    description: str = Field(default="", description="简短描述")
    category: Optional[str] = Field(default=None, description="分类目录")


class SkillUpdateRequest(BaseModel):
    content: str = Field(description="新的完整 SKILL.md 内容")
    category: Optional[str] = Field(default=None, description="分类目录")
    description: Optional[str] = Field(default=None, description="简短描述")


class SkillFileWriteRequest(BaseModel):
    content: str = Field(description="文件内容")


class CategoryCreateRequest(BaseModel):
    name: str = Field(description="分类名称")


class CategoryRenameRequest(BaseModel):
    new_name: str = Field(description="新分类名称")


class SkillSummary(BaseModel):
    name: str
    description: str
    author: str = ""
    category: str = "其他"
    path: str
    format: str = "directory"
    version: str = ""
    enabled: bool = True
    has_references: bool = False
    status: str = "approved"
    locked: bool = False
    owner_id: int = 1


class SkillDetail(BaseModel):
    name: str
    description: str
    author: str = ""
    category: str = ""
    version: str = ""
    content: str
    body: str = ""
    frontmatter: Dict[str, Any] = {}
    files: List[str] = []
    format: str = "directory"
    status: str = "approved"
    locked: bool = False
    owner_id: int = 1


# ── Endpoints ──

@router.get("")
async def list_skills(user: dict = Depends(get_current_user)):
    try:
        uid = user.get("user_id", 1)
        return skill_service.list_skills(user_id=uid, role=user.get("role"))
    except Exception as e:
        logger.error(f"列出技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def list_categories(user: dict = Depends(get_current_user)):
    try:
        return skill_service.list_categories(user_role=user.get("role"))
    except Exception as e:
        logger.error(f"列出分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/categories", status_code=201)
async def create_category(req: CategoryCreateRequest, user: dict = Depends(require_perm("skill.manage"))):
    try:
        result = skill_service.create_category(req.name)
        logger.info(f"API 创建分类: {req.name}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/categories/{name}/rename")
async def rename_category(name: str, req: CategoryRenameRequest, user: dict = Depends(require_perm("skill.manage"))):
    try:
        result = skill_service.rename_category(name, req.new_name)
        logger.info(f"API 重命名分类: {name} → {req.new_name}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"分类不存在: {name}")
    except Exception as e:
        logger.error(f"重命名分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/categories/{name}")
async def delete_category(name: str, user: dict = Depends(require_perm("skill.manage"))):
    try:
        result = skill_service.delete_category(name)
        logger.info(f"API 删除分类: {name}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"分类不存在: {name}")
    except Exception as e:
        logger.error(f"删除分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 用户自定义分类（必须在 /{name} 路由之前，避免被路径参数遮蔽） ──

class UserCategoryRequest(BaseModel):
    category: str = Field(description="分类名称")


class RenameUserCategoryRequest(BaseModel):
    new_name: str = Field(description="新分类名称")


@router.get("/my-categories")
async def list_my_categories(user: dict = Depends(get_current_user)):
    """获取当前用户的自定义分类列表。"""
    try:
        return skill_service.get_user_categories(user["user_id"])
    except Exception as e:
        logger.error(f"列出用户分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/my-categories", status_code=201)
async def create_my_category(req: UserCategoryRequest, user: dict = Depends(get_current_user)):
    """创建用户自定义分类。"""
    try:
        result = skill_service.create_user_category(user["user_id"], req.category)
        logger.info(f"用户 {user['username']} 创建分类: {req.category}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建用户分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/my-categories/{name}/rename")
async def rename_my_category(name: str, req: RenameUserCategoryRequest, user: dict = Depends(get_current_user)):
    """重命名用户自定义分类。"""
    try:
        result = skill_service.rename_user_category(user["user_id"], name, req.new_name)
        logger.info(f"用户 {user['username']} 重命名分类: {name} → {req.new_name}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"重命名用户分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/my-categories/{name}")
async def delete_my_category(name: str, user: dict = Depends(get_current_user)):
    """删除用户自定义分类。"""
    try:
        result = skill_service.delete_user_category(user["user_id"], name)
        logger.info(f"用户 {user['username']} 删除分类: {name}")
        return result
    except Exception as e:
        logger.error(f"删除用户分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{name}/category")
async def set_skill_category(name: str, req: UserCategoryRequest, user: dict = Depends(get_current_user)):
    """设置技能的分类（用户自己的技能）。"""
    try:
        result = skill_service.set_skill_category(user["user_id"], name, req.category)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"技能不存在: {name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"设置技能分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Pool 端点（必须在 /{name} 路由之前，避免路径冲突）──

@router.get("/pool")
async def list_pool(user: dict = Depends(get_current_user)):
    """浏览内容池中的 active 技能。"""
    try:
        uid = user.get("user_id", 1)
        return skill_service.list_pool(content_type="skill", user_id=uid)
    except Exception as e:
        logger.error(f"列出技能池失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pool/{name}/install")
async def install_from_pool(name: str, user: dict = Depends(get_current_user)):
    """从池中安装技能到用户账号。"""
    try:
        uid = user.get("user_id", 1)
        result = skill_service.install_from_pool(content_type="skill", content_name=name, user_id=uid)
        logger.info(f"API 安装池技能: {name} (user={uid})")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"安装池技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pool/{name}/install")
async def uninstall_from_pool(name: str, user: dict = Depends(get_current_user)):
    """卸载用户从池中安装的技能。"""
    try:
        uid = user.get("user_id", 1)
        result = skill_service.uninstall_from_pool(content_type="skill", content_name=name, user_id=uid)
        logger.info(f"API 卸载池技能: {name} (user={uid})")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"未安装该技能: {name}")
    except Exception as e:
        logger.error(f"卸载池技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{name}/lock")
async def lock_skill(name: str, user: dict = Depends(get_current_user)):
    """锁定技能（需要 skill.manage 权限，可在角色编辑里勾选）。"""
    try:
        perms = user.get("permissions") or set()
        if isinstance(perms, list):
            perms = set(perms)
        if "skill.manage" not in perms:
            raise HTTPException(status_code=403, detail="需要 skill.manage 权限")
        return skill_service.lock_skill(name)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"锁定失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{name}/unlock")
async def unlock_skill(name: str, user: dict = Depends(get_current_user)):
    """解锁技能（需要 skill.manage 权限，可在角色编辑里勾选）。"""
    try:
        perms = user.get("permissions") or set()
        if isinstance(perms, list):
            perms = set(perms)
        if "skill.manage" not in perms:
            raise HTTPException(status_code=403, detail="需要 skill.manage 权限")
        return skill_service.unlock_skill(name)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解锁失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/publish")
async def publish_skill(name: str, user: dict = Depends(get_current_user)):
    """将技能发布到内容池。"""
    try:
        uid = user.get("user_id", 1)
        result = skill_service.publish_to_pool(content_type="skill", content_name=name, user_id=uid)
        logger.info(f"API 发布技能到池: {name} (user={uid})")
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"技能不存在: {name}")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"发布技能到池失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}", response_model=SkillDetail)
async def get_skill(name: str, user: dict = Depends(get_current_user)):
    try:
        return skill_service.get_skill(name, user_id=user.get("user_id"), role=user.get("role"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"技能不存在: {name}")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"获取技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/files/{file_path:path}")
async def get_skill_file(name: str, file_path: str, user: dict = Depends(get_current_user)):
    if not skill_service.can_access_skill(name, user.get("user_id"), user.get("role")):
        raise HTTPException(status_code=403, detail="无权访问此技能")
    try:
        content = skill_service.get_skill_file(name, file_path)
        return {"name": name, "file_path": file_path, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {name}/{file_path}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取技能文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201)
async def create_skill(req: SkillCreateRequest, user: dict = Depends(get_current_user)):
    try:
        result = skill_service.create_skill(
            name=req.name, content=req.content,
            description=req.description, category=req.category,
            author=user.get("username", ""), user_id=user.get("user_id"), role=user.get("role"),
        )
        logger.info(f"API 创建技能: {req.name}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"技能已存在: {req.name}")
    except Exception as e:
        logger.error(f"创建技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{name}")
async def update_skill(name: str, req: SkillUpdateRequest, user: dict = Depends(get_current_user)):
    try:
        result = skill_service.update_skill(
            name=name, content=req.content, category=req.category, description=req.description,
            user_id=user.get("user_id"), role=user.get("role")
        )
        logger.info(f"API 更新技能: {name}")
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"技能不存在: {name}")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"更新技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}")
async def delete_skill(name: str, user: dict = Depends(get_current_user)):
    try:
        skill_service.delete_skill(name, user_id=user.get("user_id"), role=user.get("role"))
        logger.info(f"API 删除技能: {name}")
        return {"ok": True, "name": name}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"技能不存在: {name}")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"删除技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{name}/files/{file_path:path}")
async def write_skill_file(name: str, file_path: str, req: SkillFileWriteRequest, user: dict = Depends(get_current_user)):
    if not skill_service.can_access_skill(name, user.get("user_id"), user.get("role")):
        raise HTTPException(status_code=403, detail="无权修改此技能")
    try:
        result = skill_service.write_skill_file(name=name, file_path=file_path, content=req.content)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"技能不存在: {name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"写入技能文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}/files/{file_path:path}")
async def delete_skill_file(name: str, file_path: str, user: dict = Depends(get_current_user)):
    if not skill_service.can_access_skill(name, user.get("user_id"), user.get("role")):
        raise HTTPException(status_code=403, detail="无权修改此技能")
    try:
        result = skill_service.delete_skill_file(name=name, file_path=file_path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除技能文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/files/upload")
async def upload_skill_files(
    name: str,
    files: List[UploadFile] = File(...),
    target_dir: str = Form(default="references"),
    user: dict = Depends(get_current_user),
):
    """批量上传文件到技能目录（支持二进制文件如 PDF、图片等）"""
    if not skill_service.can_access_skill(name, user.get("user_id"), user.get("role")):
        raise HTTPException(status_code=403, detail="无权修改此技能")
    
    # 验证 target_dir
    if not target_dir or target_dir in (".", ".."):
        target_dir = "references"
    # 只允许常见的子目录
    allowed_dirs = {"references", "templates", "scripts", "assets"}
    if target_dir not in allowed_dirs:
        raise HTTPException(status_code=400, detail=f"目标目录必须是: {', '.join(allowed_dirs)}")
    
    uploaded = []
    errors = []
    max_size = 10 * 1024 * 1024  # 10MB
    
    for file in files:
        try:
            content = await file.read()
            if len(content) > max_size:
                errors.append(f"{file.filename}: 文件过大（超过 10MB）")
                continue
            
            file_path = f"{target_dir}/{file.filename}"
            result = skill_service.save_skill_file_binary(name, file_path, content)
            uploaded.append(result)
        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")
    
    logger.info(f"上传文件到技能 {name}: 成功 {len(uploaded)}, 失败 {len(errors)}")
    return {
        "name": name,
        "uploaded": uploaded,
        "errors": errors,
    }


@router.get("/{name}/files/{file_path:path}/raw")
async def download_skill_file_raw(name: str, file_path: str, user: dict = Depends(get_current_user)):
    """下载技能附属文件（支持二进制文件）"""
    if not skill_service.can_access_skill(name, user.get("user_id"), user.get("role")):
        raise HTTPException(status_code=403, detail="无权访问此技能")
    try:
        abs_path = skill_service.get_skill_file_path(name, file_path)
        filename = os.path.basename(file_path)
        return FileResponse(abs_path, filename=filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"下载技能文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/files/mkdir")
async def create_skill_subdir(
    name: str,
    dir_path: str = Form(...),
    user: dict = Depends(get_current_user),
):
    """在技能目录下创建子目录"""
    if not skill_service.can_access_skill(name, user.get("user_id"), user.get("role")):
        raise HTTPException(status_code=403, detail="无权修改此技能")
    try:
        result = skill_service.create_skill_dir(name, dir_path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建技能子目录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))



