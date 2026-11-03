"""邮箱配置 API — 多条 SMTP 配置的 CRUD + 切换 + 测试

仿照 model_config_controller 模式。
需要 system.config 权限（可在角色编辑里勾选）。
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.service.auth.auth_middleware import get_current_user
from backend.service.auth.permission_service import has_permission
from backend.utils.log_utils import log
import json, os

logger = log
router = APIRouter(prefix="/api/email-configs", tags=["email-configs"])


class EmailConfigCreate(BaseModel):
    config_name: str = ""
    host: str = "smtp.qq.com"
    port: str = "587"
    sender_email: str = ""
    sender_name: str = "AgentForge"
    password: str = ""


class EmailConfigUpdate(BaseModel):
    config_name: str = ""
    host: str = ""
    port: str = ""
    sender_email: str = ""
    sender_name: str = ""
    password: str = ""


def _get_conn():
    from backend.db.connection_pool import get_pool_connection
    return get_pool_connection()


@router.get("")
async def list_email_configs(user: dict = Depends(get_current_user)):
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="需要 system.config 权限")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, config_name, host, port, sender_email, sender_name, "
            "CASE WHEN password != '' THEN '***已配置***' ELSE '' END as password, "
            "is_current, enabled, created_at, updated_at "
            "FROM email_configs WHERE enabled = 1 ORDER BY is_current DESC, updated_at DESC"
        )
        return {"configs": cur.fetchall()}
    finally: conn.close()


@router.post("")
async def create_email_config(req: EmailConfigCreate, user: dict = Depends(get_current_user)):
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="需要 system.config 权限")
    if not req.host or not req.sender_email:
        raise HTTPException(status_code=400, detail="SMTP 服务器和发件人邮箱不能为空")

    password = req.password
    if password:
        from backend.utils.crypto_utils import encrypt
        password = encrypt(password)

    conn = _get_conn()
    try:
        cur = conn.cursor()
        # 检查是否已有配置，没有则自动设为当前
        cur.execute("SELECT COUNT(*) as cnt FROM email_configs WHERE enabled = 1")
        is_first = cur.fetchone()["cnt"] == 0

        cur.execute(
            "INSERT INTO email_configs (config_name, host, port, sender_email, sender_name, password, is_current) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (req.config_name or f"邮箱_{req.sender_email}", req.host, req.port,
             req.sender_email, req.sender_name, password, 1 if is_first else 0),
        )
        return {"ok": True, "id": cur.lastrowid}
    finally: conn.close()


@router.put("/{config_id}")
async def update_email_config(config_id: int, req: EmailConfigUpdate, user: dict = Depends(get_current_user)):
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="需要 system.config 权限")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM email_configs WHERE id = %s", (config_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="配置不存在")

        sets = []
        params = []
        if req.config_name: sets.append("config_name=%s"); params.append(req.config_name)
        if req.host: sets.append("host=%s"); params.append(req.host)
        if req.port: sets.append("port=%s"); params.append(req.port)
        if req.sender_email: sets.append("sender_email=%s"); params.append(req.sender_email)
        if req.sender_name: sets.append("sender_name=%s"); params.append(req.sender_name)
        if req.password:
            from backend.utils.crypto_utils import encrypt
            sets.append("password=%s"); params.append(encrypt(req.password))
        if not sets:
            raise HTTPException(status_code=400, detail="无修改内容")

        params.append(config_id)
        cur.execute(f"UPDATE email_configs SET {', '.join(sets)} WHERE id = %s", params)
        conn.commit()
        return {"ok": True}
    finally: conn.close()


@router.put("/{config_id}/active")
async def set_active_email_config(config_id: int, user: dict = Depends(get_current_user)):
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="需要 system.config 权限")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM email_configs WHERE id = %s AND enabled = 1", (config_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="配置不存在")
        cur.execute("UPDATE email_configs SET is_current = 0")
        cur.execute("UPDATE email_configs SET is_current = 1, updated_at = NOW() WHERE id = %s", (config_id,))
        conn.commit()
        return {"ok": True}
    finally: conn.close()


@router.delete("/{config_id}")
async def delete_email_config(config_id: int, user: dict = Depends(get_current_user)):
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="需要 system.config 权限")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE email_configs SET enabled = 0 WHERE id = %s", (config_id,))
        return {"ok": True, "deleted": cur.rowcount}
    finally: conn.close()


@router.post("/{config_id}/test")
async def test_email_config(config_id: int, user: dict = Depends(get_current_user)):
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="需要 system.config 权限")
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT host, port, sender_email, sender_name, password FROM email_configs WHERE id = %s AND enabled = 1",
            (config_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="配置不存在")
    finally: conn.close()

    host, port_str, sender_email, sender_name, password = row["host"], row["port"], row["sender_email"], row["sender_name"], row["password"]
    if not host or not sender_email:
        raise HTTPException(status_code=400, detail="SMTP 服务器和发件人邮箱不能为空")

    if password:
        from backend.utils.crypto_utils import decrypt
        password = decrypt(password)

    port = int(port_str) if port_str else 587
    use_ssl = port == 465

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        if password:
            server.login(sender_email, password)

        msg = MIMEText("这是一封来自 AgentForge 的 SMTP 测试邮件。\n如果你能收到这封邮件，说明邮箱配置正确。", "plain", "utf-8")
        msg["Subject"] = Header("[AgentForge] SMTP 连接测试", "utf-8")
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = sender_email
        server.sendmail(sender_email, [sender_email], msg.as_string())
        server.quit()

        # 更新时间
        conn2 = _get_conn()
        try:
            cur2 = conn2.cursor()
            cur2.execute("UPDATE email_configs SET last_test_status='ok', last_test_message='连接成功', last_test_time=NOW() WHERE id = %s", (config_id,))
        finally: conn2.close()

        return {"ok": True, "message": f"✅ 测试邮件已发送到 {sender_email}，请检查收件箱"}
    except Exception as e:
        return {"ok": False, "message": f"❌ {e}"}
