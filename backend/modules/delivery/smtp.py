"""SMTP 配置/收件人与邮件发送 Adapter（Task 14）。默认关闭，未启用不建立连接。"""
from __future__ import annotations

import asyncio
import smtplib
import socket
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header
from pydantic import BaseModel

from backend.modules.delivery.contracts import DeliveryTarget, SendResult
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.context import Principal
from backend.shared.crypto import decrypt_secret, encrypt_secret, mask_secret
from backend.shared.errors import InvalidInputError, NotFoundError


@dataclass(frozen=True, slots=True)
class EmailConfigView:
    host: str
    port: int
    username: str
    password_masked: str
    sender_email: str
    sender_name: str
    use_tls: bool
    enabled: bool
    updated_at: str


class EmailConfigBody(BaseModel):
    host: str
    port: int = 587
    username: str = ""
    password: str | None = None
    sender_email: str
    sender_name: str = "EasyChat"
    use_tls: bool = True
    enabled: bool = False


class EmailRecipientBody(BaseModel):
    name: str = ""
    address: str
    owner_id: int | None = None


class EmailRepository:
    def __init__(self, db: Database, *, encryption_secret: str) -> None:
        self.db = db
        self._secret = encryption_secret

    # ---- 配置 ------------------------------------------------------------------

    def raw_config(self) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM email_configs WHERE id=1").fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def view(self) -> EmailConfigView:
        row = self.raw_config()
        if not row:
            return EmailConfigView("", 587, "", "", "", "EasyChat", True, False, "")
        password = ""
        if row.get("password_cipher"):
            try:
                password = decrypt_secret(str(row["password_cipher"]), self._secret)
            except Exception:  # noqa: BLE001  解密失败不泄露
                password = ""
        return EmailConfigView(
            host=str(row.get("host") or ""), port=int(row.get("port") or 587),
            username=str(row.get("username") or ""), password_masked=mask_secret(password),
            sender_email=str(row.get("sender_email") or ""),
            sender_name=str(row.get("sender_name") or "EasyChat"),
            use_tls=bool(row.get("use_tls", 1)), enabled=bool(row.get("enabled", 0)),
            updated_at=str(row.get("updated_at") or ""),
        )

    def save(
        self, *, host: str, port: int, username: str, password: str | None,
        sender_email: str, sender_name: str, use_tls: bool, enabled: bool,
    ) -> EmailConfigView:
        if not host or not sender_email:
            raise InvalidInputError("SMTP host 与发件邮箱不能为空")
        if not (0 < int(port) < 65536):
            raise InvalidInputError("SMTP 端口不合法")
        current = self.raw_config()
        cipher = str(current.get("password_cipher") or "")
        if password:
            cipher = encrypt_secret(password, self._secret)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO email_configs(id, host, port, username, password_cipher, sender_email, "
                "sender_name, use_tls, enabled, updated_at) VALUES(1,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET host=excluded.host, port=excluded.port, "
                "username=excluded.username, password_cipher=excluded.password_cipher, "
                "sender_email=excluded.sender_email, sender_name=excluded.sender_name, "
                "use_tls=excluded.use_tls, enabled=excluded.enabled, updated_at=excluded.updated_at",
                (host, int(port), username, cipher, sender_email, sender_name,
                 1 if use_tls else 0, 1 if enabled else 0, utc_now_iso()),
            )
        return self.view()

    def resolved_password(self) -> str:
        row = self.raw_config()
        if not row or not row.get("password_cipher"):
            return ""
        return decrypt_secret(str(row["password_cipher"]), self._secret)

    # ---- 收件人 ------------------------------------------------------------------

    def add_recipient(self, *, owner_id: int, name: str, address: str) -> dict[str, Any]:
        email = address.strip()
        if "@" not in email or len(email) > 254:
            raise InvalidInputError("收件人邮箱不合法")
        recipient_id = f"rcp_{uuid.uuid4().hex}"
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO email_recipients(id, owner_id, name, address, active, created_at) "
                "VALUES(?,?,?,?,1,?) ON CONFLICT(owner_id, address) DO UPDATE SET "
                "name=excluded.name, active=1",
                (recipient_id, owner_id, name[:100], email, utc_now_iso()),
            )
            row = conn.execute(
                "SELECT * FROM email_recipients WHERE owner_id=? AND address=?",
                (owner_id, email),
            ).fetchone()
            return dict(row)

    def list_recipients(self, owner_id: int) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM email_recipients WHERE owner_id=? ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def deactivate_recipient(self, owner_id: int, recipient_id: str) -> None:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE email_recipients SET active=0 WHERE id=? AND owner_id=?",
                (recipient_id, owner_id),
            )
            if cur.rowcount != 1:
                raise NotFoundError("收件人不存在")


class EmailService:
    """配置/收件人公开接口；权限与加密集中在这里。"""

    def __init__(self, db: Database, *, access: Any, encryption_secret: str) -> None:
        self.repo = EmailRepository(db, encryption_secret=encryption_secret)
        self.access = access

    def get_config(self, actor: Principal) -> EmailConfigView:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "system.config")
        return self.repo.view()

    def save_config(self, actor: Principal, **fields: Any) -> EmailConfigView:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "system.config")
        return self.repo.save(**fields)

    def add_recipient(self, actor: Principal, *, name: str, address: str, owner_id: int | None = None) -> dict[str, Any]:
        principal = self.access.validate_principal(actor)
        target = owner_id or principal.user_id
        if target != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        return self.repo.add_recipient(owner_id=target, name=name, address=address)

    def list_recipients(self, actor: Principal, owner_id: int | None = None) -> list[dict[str, Any]]:
        principal = self.access.validate_principal(actor)
        target = owner_id or principal.user_id
        if target != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        return self.repo.list_recipients(target)

    def deactivate(self, actor: Principal, recipient_id: str, owner_id: int | None = None) -> None:
        principal = self.access.validate_principal(actor)
        target = owner_id or principal.user_id
        if target != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        self.repo.deactivate_recipient(target, recipient_id)


class SmtpEmailSender:
    """DeliverySender 的邮件实现；发送在受控线程，失败分类明确。"""

    def __init__(self, email: EmailService, *, timeout: float = 15.0) -> None:
        self.email = email
        self.timeout = timeout

    async def can_deliver(self, target: DeliveryTarget) -> bool:
        if target.kind != "email" or "@" not in target.ref:
            return False
        config = self.email.repo.view()
        return bool(config.enabled and config.host and config.sender_email)

    async def send_text(self, target: DeliveryTarget, text: str, *, context_token: str = "") -> SendResult:
        return await self._send(target, subject="EasyChat 提醒", body=text, attachment=None)

    async def send_artifact(
        self, target: DeliveryTarget, artifact_path: str, *, subject: str, body: str = ""
    ) -> SendResult:
        path = Path(artifact_path)
        if not path.is_file():
            return SendResult.failed("报告文件缺失")
        if path.stat().st_size > 25 * 1024 * 1024:
            return SendResult.failed("附件超过 25MB")
        return await self._send(target, subject=subject, body=body or "见附件。", attachment=path)

    async def _send(
        self, target: DeliveryTarget, *, subject: str, body: str, attachment: Path | None
    ) -> SendResult:
        config = self.email.repo.view()
        if not (config.enabled and config.host and config.sender_email):
            return SendResult.failed("SMTP 未启用或配置不完整")
        try:
            await asyncio.to_thread(
                self._sync_send, config, self.email.repo.resolved_password(), target.ref,
                subject, body, attachment,
            )
            return SendResult.sent()
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as exc:
            return SendResult.failed(f"SMTP 认证/收件人失败: {exc}")
        except (TimeoutError, socket.timeout, ConnectionError) as exc:
            return SendResult.retry(f"SMTP 连接失败: {exc}")
        except Exception as exc:  # noqa: BLE001  连接后结果不确定
            return SendResult.unsure(f"SMTP 发送结果不确定: {exc}")

    def _sync_send(
        self, config: EmailConfigView, password: str, to_address: str,
        subject: str, body: str, attachment: Path | None,
    ) -> None:
        if config.port == 465:
            server: Any = smtplib.SMTP_SSL(config.host, config.port, timeout=self.timeout)
        else:
            server = smtplib.SMTP(config.host, config.port, timeout=self.timeout)
        try:
            if config.use_tls and config.port != 465:
                server.starttls()
            if config.username:
                server.login(config.username, password)
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = f"{config.sender_name} <{config.sender_email}>"
            message["To"] = to_address
            message.set_content(body)
            if attachment is not None:
                message.add_attachment(
                    attachment.read_bytes(), maintype="application", subtype="pdf",
                    filename=attachment.name,
                )
            server.send_message(message)
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass


def build_email_router(service: EmailService, authenticate: Any) -> APIRouter:
    """邮件配置/收件人 HTTP 路由；不返回密码明文。"""
    from backend.shared.errors import UnauthenticatedError

    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    def _view(view: EmailConfigView) -> dict[str, Any]:
        return {
            "host": view.host, "port": view.port, "username": view.username,
            "password_masked": view.password_masked, "sender_email": view.sender_email,
            "sender_name": view.sender_name, "use_tls": view.use_tls,
            "enabled": view.enabled, "updated_at": view.updated_at,
        }

    router = APIRouter(prefix="/api/email", tags=["email"])

    @router.get("/config")
    async def get_config(authorization: Annotated[str | None, Header()] = None):
        return _view(service.get_config(_principal(authorization)))

    @router.put("/config")
    async def save_config(body: EmailConfigBody,
                          authorization: Annotated[str | None, Header()] = None):
        return _view(service.save_config(_principal(authorization), **body.model_dump()))

    @router.get("/recipients")
    async def list_recipients(owner_id: int | None = None,
                              authorization: Annotated[str | None, Header()] = None):
        return {"recipients": service.list_recipients(
            _principal(authorization), owner_id=owner_id,
        )}

    @router.post("/recipients")
    async def add_recipient(body: EmailRecipientBody,
                            authorization: Annotated[str | None, Header()] = None):
        return {"recipient": service.add_recipient(
            _principal(authorization), name=body.name, address=body.address,
            owner_id=body.owner_id,
        )}

    @router.delete("/recipients/{recipient_id}")
    async def delete_recipient(recipient_id: str, owner_id: int | None = None,
                               authorization: Annotated[str | None, Header()] = None):
        service.deactivate(_principal(authorization), recipient_id, owner_id=owner_id)
        return {"ok": True}

    return router
