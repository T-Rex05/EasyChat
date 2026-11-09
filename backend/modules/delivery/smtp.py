"""SMTP 配置/收件人与邮件发送 Adapter（Task 14）。默认关闭，未启用不建立连接。

审计 #4/#7：收件人注册不等于可信——登记的地址必须逐个确认所有权
（verified=1）才能投递；且每一行只允许一个合法邮箱地址（逗号分隔/
控制字符在注册与投递两处都 fail-closed），防止单行扇出为多个信封收件人。
"""
from __future__ import annotations

import asyncio
import secrets
import smtplib
import socket
import uuid
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel

from backend.modules.delivery.contracts import DeliveryTarget, SendResult
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.context import Principal
from backend.shared.crypto import decrypt_secret, encrypt_secret, mask_secret
from backend.shared.errors import InvalidInputError, NotFoundError

CONFIRM_TOKEN_TTL_HOURS = 24


def _token_expiry_iso() -> str:
    """确认令牌过期时间（ISO，与 utc_now_iso 同格式，可安全字符串比较）。"""
    from datetime import datetime, timedelta, timezone

    return (
        datetime.now(timezone.utc) + timedelta(hours=CONFIRM_TOKEN_TTL_HOURS)
    ).isoformat(timespec="milliseconds")


def validate_single_address(address: str) -> str:
    """强制单合法邮箱地址（审计 #7）：拒绝逗号/控制字符/非 addr-spec 值，
    返回规整后的地址。这是注册与投递共用的唯一格式契约。"""
    value = (address or "").strip()
    if not value or len(value) > 254:
        raise InvalidInputError("收件人必须是单个合法邮箱地址")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise InvalidInputError("收件人必须是单个合法邮箱地址")
    if any(ch in ",<>" for ch in value):
        raise InvalidInputError("收件人必须是单个合法邮箱地址（不允许逗号/尖括号）")
    try:
        parsed = Address(addr_spec=value)
    except (ValueError, IndexError) as exc:
        raise InvalidInputError("收件人必须是单个合法邮箱地址") from exc
    if str(parsed).lower() != value.lower():
        raise InvalidInputError("收件人必须是单个合法邮箱地址")
    return value


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
        # 审计 #4：注册只创建"待确认"行（verified=0），所有权由确认链接证明；
        # 审计 #7：地址必须是单个合法邮箱，逗号列表/控制字符在此拒绝。
        email = validate_single_address(address)
        recipient_id = f"rcp_{uuid.uuid4().hex}"
        token = secrets.token_urlsafe(24)
        expires = _token_expiry_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO email_recipients(id, owner_id, name, address, active, verified, "
                "confirm_token, token_expires_at, created_at) VALUES(?,?,?,?,1,0,?,?,?) "
                "ON CONFLICT(owner_id, address) DO UPDATE SET name=excluded.name, active=1, "
                "verified=0, confirm_token=excluded.confirm_token, "
                "token_expires_at=excluded.token_expires_at",
                (recipient_id, owner_id, name[:100], email, token, expires, utc_now_iso()),
            )
            row = conn.execute(
                "SELECT * FROM email_recipients WHERE owner_id=? AND address=?",
                (owner_id, email),
            ).fetchone()
            result = dict(row)
        result.pop("confirm_token", None)  # token 只经确认邮件送达，不出现在 API 响应
        return result

    def confirm_recipient(self, token: str) -> dict[str, Any]:
        """一次性确认：命中且未过期的 token 将对应行置为 verified=1。"""
        value = (token or "").strip()
        if not value:
            raise InvalidInputError("确认令牌为空")
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM email_recipients WHERE confirm_token=?", (value,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise NotFoundError("确认令牌无效")
        if str(row["token_expires_at"] or "") < utc_now_iso():
            raise InvalidInputError("确认令牌已过期，请重新登记收件人")
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE email_recipients SET verified=1, confirm_token='', token_expires_at='' "
                "WHERE id=?",
                (str(row["id"]),),
            )
        return {"id": str(row["id"]), "address": str(row["address"]), "verified": True}

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
        # 所有权确认邮件的发送器；bootstrap 在 SmtpEmailSender 构造后装配（审计 #4）
        self.confirmation_sender: Any = None

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

    async def send_confirmation(self, owner_id: int, address: str) -> bool:
        """所有权确认邮件（审计 #4，best-effort）：SMTP 未启用或发送失败不
        阻断注册，但收件人在确认前不可投递。"""
        try:
            normalized = validate_single_address(address).lower()
        except InvalidInputError:
            return False
        row = next(
            (r for r in self.repo.list_recipients(int(owner_id))
             if str(r.get("address") or "").strip().lower() == normalized),
            None,
        )
        token = str(row.get("confirm_token") or "") if row else ""
        if not token:
            return False
        sender = self.confirmation_sender
        if sender is None:
            return False  # bootstrap 未装配发送器（SMTP 能力关闭）
        target = DeliveryTarget(kind="email", ref=normalized)
        body = (
            "请确认将该邮箱加入 EasyChat 收件人（链接 24 小时内有效，且只能使用一次）：\n\n"
            f"/api/email/recipients/confirm?token={token}\n\n"
            "在部署主机上打开示例：\n"
            f"curl 'http://127.0.0.1:8001/api/email/recipients/confirm?token={token}'\n\n"
            "如果这不是你的操作，请忽略本邮件。"
        )
        try:
            result = await sender.send_text(
                target, body, subject="EasyChat 收件人确认",
            )
        except Exception:  # noqa: BLE001  确认邮件失败不影响注册结果
            return False
        return bool(result and getattr(result, "ok", False))

    def is_recipient_allowed(self, owner_id: int, address: str) -> bool:
        """投递前校验：owner 自己登记、active 且 **已完成所有权确认** 的单个地址。

        审计 #4：verified=0 的行（含全部存量行）fail-closed；审计 #7：目标与
        存量值都不是单个合法邮箱时一律拒绝（防逗号列表扇出）。
        """
        try:
            target = validate_single_address(address).lower()
        except InvalidInputError:
            return False
        for row in self.repo.list_recipients(int(owner_id)):
            if not bool(row.get("active")) or not bool(row.get("verified")):
                continue
            stored = str(row.get("address") or "")
            try:
                if validate_single_address(stored).lower() == target:
                    return True
            except InvalidInputError:
                continue  # 存量脏数据 fail-closed
        return False

    def confirm_recipient(self, token: str) -> dict[str, Any]:
        """所有权确认（无需登录：token 本身即凭证，一次性）。"""
        return self.repo.confirm_recipient(token)

    def list_recipients(self, actor: Principal, owner_id: int | None = None) -> list[dict[str, Any]]:
        principal = self.access.validate_principal(actor)
        target = owner_id or principal.user_id
        if target != principal.user_id:
            self.access.require_permission(principal, "system.manage")
        rows = self.repo.list_recipients(target)
        for row in rows:
            row.pop("confirm_token", None)  # token 只经邮件送达
            row.pop("token_expires_at", None)
        return rows

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

    async def send_text(
        self, target: DeliveryTarget, text: str, *, context_token: str = "",
        subject: str = "EasyChat 提醒",
    ) -> SendResult:
        return await self._send(target, subject=subject, body=text, attachment=None)

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
            to_address = validate_single_address(target.ref)
        except InvalidInputError as exc:
            # 审计 #7：信封收件人必须是单个合法地址，多地址/脏值在发送前拒绝。
            return SendResult.failed(str(exc))
        try:
            await asyncio.to_thread(
                self._sync_send, config, self.email.repo.resolved_password(), to_address,
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
            message["To"] = Address(addr_spec=to_address)  # 单地址对象，绝不再解析出多个信封收件人
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
        principal = _principal(authorization)
        row = service.add_recipient(
            principal, name=body.name, address=body.address,
            owner_id=body.owner_id,
        )
        confirmed = await service.send_confirmation(int(row["owner_id"]), str(row["address"]))
        return {"recipient": row, "confirmation_sent": confirmed}

    @router.get("/recipients/confirm")
    async def confirm_recipient(token: str = Query(default="")):
        # 无需登录：token 即所有权凭证，一次性且 24 小时过期（审计 #4）
        from backend.shared.errors import UnauthenticatedError as _U

        if not token.strip():
            raise _U("缺少确认令牌")
        return {"ok": True, **service.confirm_recipient(token)}

    @router.delete("/recipients/{recipient_id}")
    async def delete_recipient(recipient_id: str, owner_id: int | None = None,
                               authorization: Annotated[str | None, Header()] = None):
        service.deactivate(_principal(authorization), recipient_id, owner_id=owner_id)
        return {"ok": True}

    return router


def build_email_compat_router(service: EmailService, authenticate: Any) -> APIRouter:
    """旧邮件配置/个人邮箱/平台测试路径的兼容层，全部落到新 EmailService。"""
    from backend.shared.errors import CapabilityUnavailableError, UnauthenticatedError

    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    def _config_payload(view: EmailConfigView) -> dict[str, Any]:
        return {
            "id": 1, "config_name": view.sender_name or "默认邮箱",
            "host": view.host, "port": str(view.port), "sender_email": view.sender_email,
            "sender_name": view.sender_name, "password": view.password_masked,
            "is_current": 1, "enabled": 1 if view.enabled else 0,
            "created_at": view.updated_at, "updated_at": view.updated_at,
        }

    def _save_body(body: dict[str, Any], principal) -> EmailConfigView:
        current = service.get_config(principal)
        enabled = bool(body.get("enabled", True))
        if body.get("_disable"):
            enabled = False
        return service.save_config(
            principal,
            host=str(body.get("host") or current.host),
            port=int(body.get("port") or current.port),
            username=str(body.get("username") or current.username),
            password=str(body.get("password") or "") or None,
            sender_email=str(body.get("sender_email") or current.sender_email),
            sender_name=str(body.get("sender_name") or current.sender_name),
            use_tls=bool(body.get("use_tls", current.use_tls)),
            enabled=enabled,
        )

    router = APIRouter(tags=["email-compat"])

    @router.get("/api/email-configs")
    async def list_configs(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        return {"configs": [_config_payload(service.get_config(principal))]}

    @router.post("/api/email-configs")
    async def create_config(body: dict[str, Any],
                            authorization: Annotated[str | None, Header()] = None):
        _save_body(body, _principal(authorization))
        return {"ok": True, "id": 1}

    @router.put("/api/email-configs/{config_id}")
    async def update_config(config_id: int, body: dict[str, Any],
                            authorization: Annotated[str | None, Header()] = None):
        _save_body(body, _principal(authorization))
        return {"ok": True}

    @router.put("/api/email-configs/{config_id}/active")
    async def set_active(config_id: int,
                         authorization: Annotated[str | None, Header()] = None):
        _principal(authorization)
        return {"ok": True}

    @router.delete("/api/email-configs/{config_id}")
    async def delete_config(config_id: int,
                            authorization: Annotated[str | None, Header()] = None):
        _save_body({"_disable": True}, _principal(authorization))
        return {"ok": True}

    @router.post("/api/email-configs/{config_id}/test")
    async def test_config(config_id: int,
                          authorization: Annotated[str | None, Header()] = None):
        _principal(authorization)
        raise CapabilityUnavailableError("真实 SMTP 测试需外部网络，离线环境不启用")

    @router.get("/api/personal-emails")
    async def list_personal(authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        rows = service.list_recipients(principal)
        return {"emails": [{
            "id": r["id"], "email": r["address"], "is_current": 1 if r.get("active") else 0,
            "created_at": r.get("created_at"),
        } for r in rows if r.get("active")]}

    @router.post("/api/personal-emails")
    async def add_personal(body: dict[str, Any],
                           authorization: Annotated[str | None, Header()] = None):
        principal = _principal(authorization)
        email = str(body.get("email") or "")
        row = service.add_recipient(principal, name="", address=email)
        await service.send_confirmation(int(row["owner_id"]), str(row["address"]))
        return {"ok": True, "id": row["id"]}

    @router.put("/api/personal-emails/{email_id}/active")
    async def set_personal_active(email_id: str,
                                  authorization: Annotated[str | None, Header()] = None):
        _principal(authorization)
        return {"ok": True}

    @router.delete("/api/personal-emails/{email_id}")
    async def delete_personal(email_id: str,
                              authorization: Annotated[str | None, Header()] = None):
        service.deactivate(_principal(authorization), email_id)
        return {"ok": True}

    @router.post("/api/platform-config/email/test")
    async def platform_email_test(authorization: Annotated[str | None, Header()] = None):
        _principal(authorization)
        raise CapabilityUnavailableError("真实 SMTP 测试需外部网络，离线环境不启用")

    return router
