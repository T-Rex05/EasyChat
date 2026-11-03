"""平台配置 API — 微信/飞书/邮箱的平台级配置

端点：
- GET    /api/platform-config/{platform}            获取平台配置
- PUT    /api/platform-config/{platform}            保存/更新平台配置（超级管理员）
- GET    /api/platform-config/{platform}/bindings   获取平台绑定列表
- POST   /api/platform-config/wechat/qr/start      发起微信扫码绑定
- GET    /api/platform-config/wechat/qr/{sid}/status 查询扫码状态（只读内存，不调 iLink）
- POST   /api/platform-config/wechat/qr/{sid}/bind  确认绑定
"""
import asyncio
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.service.auth.auth_middleware import get_current_user, require_super_admin
from backend.service.auth.permission_service import has_permission
from backend.utils.log_utils import log
import json
import os
import time
import uuid
import threading
import base64
from io import BytesIO

logger = log
router = APIRouter(prefix="/api/platform-config", tags=["platform-config"])


def _get_conn():
    from backend.db.connection_pool import get_pool_connection
    return get_pool_connection()


class PlatformConfigSave(BaseModel):
    config_json: dict = Field(description="平台配置 JSON")
    enabled: bool = Field(default=False)


# ── 微信 QR 扫码会话管理 ──

_qr_sessions: dict = {}          # session_id → {status, qrcode_value, qr_image, credentials, ...}
_qr_tasks: dict[str, asyncio.Task] = {}  # session_id → 后台轮询任务
_qr_lock = threading.Lock()

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
QR_TIMEOUT = 300  # 二维码有效期 5 分钟
QR_POLL_INTERVAL = 3  # 后台轮询间隔（秒）


def _sync_http_get_json(url: str, timeout: int = 15) -> dict:
    import urllib.request
    import ssl
    ctx = ssl.create_default_context() if hasattr(ssl, "create_default_context") else None
    kwargs = {"timeout": timeout}
    if ctx:
        kwargs["context"] = ctx
    req = urllib.request.Request(url, headers={
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
    })
    with urllib.request.urlopen(req, **kwargs) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _http_get_json(url: str, timeout: int = 15) -> dict:
    return await asyncio.to_thread(_sync_http_get_json, url, timeout)


def _generate_qr_image(data: str) -> str:
    import qrcode as qrcode_lib
    qr = qrcode_lib.QRCode(box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


async def _background_qr_poll(sid: str):
    """后台轮询任务 — 每 QR_POLL_INTERVAL 秒轮询 iLink，更新 _qr_sessions。

    前端调 /status 只读内存，不再调 iLink —— 避免长轮询阻塞并发。
    """
    deadline = time.time() + QR_TIMEOUT
    refresh_count = 0
    last_status = "wait"

    while time.time() < deadline:
        with _qr_lock:
            sess = _qr_sessions.get(sid)
            if not sess:
                return
            if sess["status"] in ("confirmed", "bound", "expired"):
                return
            current_base_url = sess.get("current_base_url", ILINK_BASE_URL)
            bot_type = sess.get("bot_type", "3")

        try:
            status_resp = await _http_get_json(
                f"{current_base_url}/ilink/bot/get_qrcode_status?qrcode={sess['qrcode_value']}",
                timeout=15,
            )
        except Exception as e:
            logger.debug(f"QR 后台轮询 [{sid}]: {e}")
            await asyncio.sleep(QR_POLL_INTERVAL)
            continue

        status = str(status_resp.get("status") or "wait")

        with _qr_lock:
            sess = _qr_sessions.get(sid)
            if not sess:
                return

            if status == "scaned_but_redirect":
                redirect_host = str(status_resp.get("redirect_host") or "")
                if redirect_host:
                    sess["current_base_url"] = f"https://{redirect_host}"
                    logger.info(f"QR [{sid[:8]}]: 重定向 → {redirect_host}")
                sess["status"] = "scaned"
                last_status = "scaned"

            elif status == "confirmed":
                account_id = str(status_resp.get("ilink_bot_id") or "")
                token = str(status_resp.get("bot_token") or "")
                base_url = str(status_resp.get("baseurl") or ILINK_BASE_URL)
                user_id = str(status_resp.get("ilink_user_id") or "")
                if account_id and token:
                    sess["status"] = "confirmed"
                    sess["credentials"] = {
                        "account_id": account_id,
                        "token": token,
                        "base_url": base_url,
                        "user_id": user_id,
                    }
                    logger.info(f"QR [{sid[:8]}]: 扫码成功! account_id={account_id[:12]}")
                else:
                    sess["status"] = "expired"
                return

            elif status == "expired":
                if refresh_count < 3:
                    refresh_count += 1
                    try:
                        qr_resp = await _http_get_json(
                            f"{ILINK_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={bot_type}",
                            timeout=10,
                        )
                        sess["qrcode_value"] = str(qr_resp.get("qrcode") or "")
                        qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
                        qr_scan = qrcode_url if qrcode_url else sess["qrcode_value"]
                        sess["current_base_url"] = ILINK_BASE_URL
                        sess["status"] = "wait_refreshed"
                        try:
                            sess["qr_image"] = _generate_qr_image(qr_scan)
                        except Exception:
                            pass
                        logger.info(f"QR [{sid[:8]}]: 过期刷新 ({refresh_count}/3)")
                    except Exception:
                        sess["status"] = "expired"
                        return
                else:
                    sess["status"] = "expired"
                    logger.info(f"QR [{sid[:8]}]: 多次过期，终止")
                    return

            elif status != last_status:
                sess["status"] = status
                last_status = status
                if status != "wait":
                    logger.info(f"QR [{sid[:8]}]: {status}")

        await asyncio.sleep(QR_POLL_INTERVAL)

    # 超时
    with _qr_lock:
        sess = _qr_sessions.get(sid)
        if sess:
            sess["status"] = "expired"
    logger.info(f"QR [{sid[:8]}]: 超时")


# ── API 端点 ──

@router.get("/{platform}")
async def get_platform_config(platform: str, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT platform, config_json, enabled, updated_at FROM platform_config WHERE platform = %s",
            (platform,),
        )
        row = cur.fetchone()
        if not row:
            return {"platform": platform, "config_json": {}, "enabled": False, "configured": False}
        cfg = row["config_json"]
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        display = dict(cfg)
        for secret_key in ("token", "app_secret", "password", "smtp_password", "api_key"):
            if secret_key in display and display[secret_key]:
                val = display[secret_key]
                display[secret_key] = "****" + val[-4:] if len(val) > 4 else "****"
        return {
            "platform": row["platform"], "config_json": display, "raw_config_json": display,
            "enabled": bool(row["enabled"]), "configured": True,
            "updated_at": str(row.get("updated_at", "")),
        }
    finally:
        conn.close()


@router.put("/{platform}")
async def save_platform_config(platform: str, req: PlatformConfigSave, user: dict = Depends(require_super_admin)):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        config_json_str = json.dumps(req.config_json, ensure_ascii=False)
        cur.execute(
            "INSERT INTO platform_config (platform, config_json, enabled) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE config_json = VALUES(config_json), enabled = VALUES(enabled)",
            (platform, config_json_str, 1 if req.enabled else 0),
        )
        return {"ok": True, "platform": platform}
    except Exception as e:
        logger.error(f"保存平台配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")
    finally:
        conn.close()


class SmtpTestRequest(BaseModel):
    host: str = ""
    port: str = "587"
    sender_email: str = ""
    sender_name: str = "AgentForge"
    password: str = ""
    to_email: str = ""  # 为空则发给发件人自身


@router.post("/email/test")
async def test_smtp_connection(req: SmtpTestRequest, user: dict = Depends(get_current_user)):
    """测试 SMTP 连接 — 发送测试邮件到指定收件人。to_email 为空时发给发件人自身。"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="需要 system.config 权限")
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header

    if not req.host or not req.sender_email:
        raise HTTPException(status_code=400, detail="SMTP 服务器和发件人邮箱不能为空")

    to_email = req.to_email.strip() or req.sender_email

    # 如果没填密码，从数据库读取
    password = req.password
    if not password:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_json FROM platform_config WHERE platform = 'email'")
            row = cur.fetchone()
            if row:
                cfg = row["config_json"]
                if isinstance(cfg, str):
                    cfg = json.loads(cfg)
                password = cfg.get("password", "")
        finally:
            conn.close()

    port = int(req.port)
    use_ssl = port == 465

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(req.host, port, timeout=15)
        else:
            server = smtplib.SMTP(req.host, port, timeout=15)
            server.starttls()

        if password:
            server.login(req.sender_email, password)

        msg = MIMEText("这是一封来自 AgentForge 的 SMTP 测试邮件。\n如果你能收到这封邮件，说明邮箱配置正确。", "plain", "utf-8")
        msg["Subject"] = Header("[AgentForge] SMTP 连接测试", "utf-8")
        msg["From"] = f"{req.sender_name} <{req.sender_email}>"
        msg["To"] = to_email

        server.sendmail(req.sender_email, [to_email], msg.as_string())
        server.quit()
        return {"ok": True, "message": f"✅ 测试邮件已发送到 {to_email}，请检查收件箱（含垃圾邮件）"}
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=400, detail="认证失败：请检查授权码/密码是否正确")
    except smtplib.SMTPConnectError:
        raise HTTPException(status_code=400, detail=f"无法连接到 {req.host}:{req.port}，请检查服务器地址和端口")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SMTP 测试失败: {e}")


@router.get("/{platform}/bindings")
async def get_platform_bindings(platform: str, user: dict = Depends(get_current_user)):
    is_super = user.get("role") == "super_admin"
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if is_super:
            cur.execute(
                "SELECT ub.*, u.username FROM user_bindings ub "
                "LEFT JOIN users u ON ub.user_id = u.id WHERE ub.platform = %s ORDER BY ub.created_at DESC",
                (platform,),
            )
        else:
            cur.execute(
                "SELECT * FROM user_bindings WHERE platform = %s AND user_id = %s",
                (platform, user["user_id"]),
            )
        return {"bindings": cur.fetchall()}
    finally:
        conn.close()


# ── 微信 QR 扫码 ──

@router.post("/wechat/qr/start")
async def start_wechat_qr(user: dict = Depends(get_current_user)):
    """获取 iLink 二维码 + 启动后台轮询。前端只需调 /status 读内存状态。"""
    try:
        qr_resp = await _http_get_json(
            f"{ILINK_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type=3", timeout=15,
        )
    except Exception as e:
        logger.error(f"获取微信二维码失败: {e}")
        raise HTTPException(status_code=502, detail=f"微信 iLink API 不可达: {e}")

    qrcode_value = str(qr_resp.get("qrcode") or "")
    qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
    if not qrcode_value:
        raise HTTPException(status_code=502, detail="微信 API 返回了空的二维码")

    qr_scan_data = qrcode_url if qrcode_url else qrcode_value
    try:
        qr_image_b64 = _generate_qr_image(qr_scan_data)
    except Exception:
        qr_image_b64 = ""

    sid = uuid.uuid4().hex[:16]
    with _qr_lock:
        _qr_sessions[sid] = {
            "status": "wait",
            "qrcode_value": qrcode_value,
            "qr_scan_data": qr_scan_data,
            "qr_image": qr_image_b64,
            "current_base_url": ILINK_BASE_URL,
            "bot_type": "3",
            "created_at": time.time(),
            "refresh_count": 0,
            "credentials": None,
        }

    # 启动后台轮询（不 await，后台运行）
    loop = asyncio.get_event_loop()
    task = loop.create_task(_background_qr_poll(sid))
    _qr_tasks[sid] = task
    # 任务结束后自动清理
    task.add_done_callback(lambda _: _qr_tasks.pop(sid, None))

    logger.info(f"QR [{sid[:8]}]: 会话创建，后台轮询已启动")
    return {"session_id": sid, "qr_image": qr_image_b64, "status": "wait"}


@router.get("/wechat/qr/{session_id}/status")
async def check_wechat_qr_status(session_id: str, user: dict = Depends(get_current_user)):
    """只读内存状态，不调 iLink。后台轮询任务持续更新 _qr_sessions。"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可操作微信绑定")
    with _qr_lock:
        sess = _qr_sessions.get(session_id)
        if not sess:
            return {"status": "expired", "error": "会话不存在或已过期"}
        status = sess["status"]
        result = {"status": status}
        if status == "confirmed":
            result["credentials"] = sess.get("credentials")
        elif status == "wait_refreshed":
            result["qr_image"] = sess.get("qr_image", "")
        return result


@router.post("/wechat/qr/{session_id}/bind")
async def bind_after_qr(session_id: str, user: dict = Depends(get_current_user)):
    """扫码确认后保存 Bot 凭证和用户绑定。换绑时直接更新。"""
    with _qr_lock:
        sess = _qr_sessions.get(session_id)
        if not sess:
            raise HTTPException(status_code=404, detail="二维码会话不存在或已过期，请重新扫码")
        if sess["status"] not in ("confirmed", "bound"):
            raise HTTPException(status_code=400, detail=f"二维码状态为 {sess['status']}，请等待扫码确认")
        creds = sess.get("credentials")
        if not creds:
            raise HTTPException(status_code=400, detail="凭证数据不完整，请重新扫码")

    conn = _get_conn()
    try:
        cur = conn.cursor()

        # 检查是否已绑定
        cur.execute(
            "SELECT id FROM user_bindings WHERE user_id = %s AND platform = 'wechat'",
            (user["user_id"],),
        )
        existing = cur.fetchone()
        is_rebind = bool(existing)

        # 超管保存 Bot 凭证
        if user.get("role") == "super_admin":
            config_json = json.dumps({
                "account_id": creds["account_id"],
                "token": creds["token"],
                "base_url": creds.get("base_url", ILINK_BASE_URL),
                "bot_user_id": creds.get("user_id", ""),
            }, ensure_ascii=False)
            cur.execute(
                "INSERT INTO platform_config (platform, config_json, enabled) VALUES ('wechat', %s, 1) "
                "ON DUPLICATE KEY UPDATE config_json = VALUES(config_json), enabled = VALUES(enabled)",
                (config_json,),
            )

        wechat_user_id = creds.get("user_id") or creds.get("account_id")
        if not wechat_user_id:
            raise HTTPException(status_code=400, detail="微信 API 未返回用户标识")

        if is_rebind:
            cur.execute(
                "UPDATE user_bindings SET open_id = %s, nickname = %s WHERE id = %s",
                (wechat_user_id, f"微信用户_{wechat_user_id[:8]}", existing["id"]),
            )
        else:
            cur.execute(
                "INSERT INTO user_bindings (user_id, platform, open_id, nickname) VALUES (%s, 'wechat', %s, %s)",
                (user["user_id"], wechat_user_id, f"微信用户_{wechat_user_id[:8]}" if wechat_user_id else ""),
            )

        # 标记为已绑定
        with _qr_lock:
            sess["status"] = "bound"

        # 重启消息监听器
        # 用 to_thread：restart_wechat_listener 内部有 time.sleep(1) + 同步 MySQL，
        # 直接在事件循环里调会把**整个进程**卡住 1 秒（保持其同步签名不变）。
        try:
            from backend.controller.wechat_listener import restart_wechat_listener
            await asyncio.to_thread(restart_wechat_listener)
        except ImportError:
            pass

        return {
            "ok": True, "wechat_user_id": wechat_user_id,
            "bot_configured": user.get("role") == "super_admin", "is_rebind": is_rebind,
        }
    finally:
        conn.close()
