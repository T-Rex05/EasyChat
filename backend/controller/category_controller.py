"""技能分类管理 API"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from backend.db.schema import get_conn
from backend.service.auth.auth_middleware import get_current_user, require_perm
from backend.utils.log_utils import log

logger = log
router = APIRouter(prefix="/api/categories", tags=["categories"])


class CreateCategoryRequest(BaseModel):
    name: str = Field(description="分类名称")
    slug: str = Field(default="", description="标识")
    description: str = Field(default="", description="描述")


@router.get("")
async def list_categories():
    """列出所有分类（公开）。"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM categories ORDER BY sort_order, id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("")
async def create_category(req: CreateCategoryRequest, user: dict = Depends(get_current_user)):
    """创建新分类（需登录）。"""
    slug = req.slug or req.name.strip().lower().replace(" ", "_")
    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM categories WHERE slug = %s", (slug,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="分类已存在")
        cur = conn.execute(
            "INSERT INTO categories (name, slug, description) VALUES (%s, %s, %s)",
            (req.name, slug, req.description),
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": req.name, "slug": slug}
    finally:
        conn.close()


@router.delete("/{cat_id}")
async def delete_category(cat_id: int, user: dict = Depends(require_perm("system.manage"))):
    """删除分类（仅管理员）。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM categories WHERE id = %s", (cat_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
