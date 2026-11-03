"""个人邮箱 API — 多邮箱 CRUD + 切换"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.service.auth.auth_middleware import get_current_user
import os

router = APIRouter(prefix="/api/personal-emails", tags=["personal-emails"])


class PersonalEmailCreate(BaseModel):
    email: str


def _get_conn():
    from backend.db.connection_pool import get_pool_connection
    return get_pool_connection()


@router.get("")
async def list_personal_emails(user: dict = Depends(get_current_user)):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, is_current, created_at "
            "FROM personal_emails WHERE user_id = %s ORDER BY is_current DESC, created_at DESC",
            (user["user_id"],),
        )
        return {"emails": cur.fetchall()}
    finally: conn.close()


@router.post("")
async def add_personal_email(req: PersonalEmailCreate, user: dict = Depends(get_current_user)):
    email = req.email.strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱地址格式不正确")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        # 去重
        cur.execute("SELECT id, is_current FROM personal_emails WHERE user_id=%s AND email=%s", (user["user_id"], email))
        existing = cur.fetchone()
        if existing:
            if not existing["is_current"]:
                cur.execute("UPDATE personal_emails SET is_current=0 WHERE user_id=%s", (user["user_id"],))
                cur.execute("UPDATE personal_emails SET is_current=1 WHERE id=%s", (existing["id"],))
            return {"ok": True, "id": existing["id"], "duplicate": True}

        is_first = not cur.execute("SELECT 1 FROM personal_emails WHERE user_id=%s LIMIT 1", (user["user_id"],))
        cur.execute(
            "INSERT INTO personal_emails (user_id, email, is_current) VALUES (%s, %s, %s)",
            (user["user_id"], email, 1 if is_first else 0),
        )
        return {"ok": True, "id": cur.lastrowid}
    finally: conn.close()


@router.put("/{email_id}/active")
async def set_active_personal_email(email_id: int, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM personal_emails WHERE id=%s AND user_id=%s", (email_id, user["user_id"]))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="邮箱不存在")
        cur.execute("UPDATE personal_emails SET is_current=0 WHERE user_id=%s", (user["user_id"],))
        cur.execute("UPDATE personal_emails SET is_current=1, updated_at=NOW() WHERE id=%s", (email_id,))
        return {"ok": True}
    finally: conn.close()


@router.delete("/{email_id}")
async def delete_personal_email(email_id: int, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, is_current FROM personal_emails WHERE id=%s AND user_id=%s", (email_id, user["user_id"]))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="邮箱不存在")
        cur.execute("DELETE FROM personal_emails WHERE id=%s", (email_id,))
        # 如果删除的是当前激活的，把最新的设为激活
        if row["is_current"]:
            cur.execute("SELECT id FROM personal_emails WHERE user_id=%s ORDER BY created_at DESC LIMIT 1", (user["user_id"],))
            latest = cur.fetchone()
            if latest:
                cur.execute("UPDATE personal_emails SET is_current=1 WHERE id=%s", (latest["id"],))
        return {"ok": True}
    finally: conn.close()
