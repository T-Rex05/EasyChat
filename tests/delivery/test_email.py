"""邮件能力测试（Task 14）：配置加密、RBAC、默认关闭、假 SMTP 分类。"""
from __future__ import annotations

import smtplib
import socket
import uuid

import pytest

from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.delivery.smtp import EmailService, SmtpEmailSender
from backend.shared.errors import ForbiddenError
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig

TARGET = DeliveryTarget(kind="email", ref="dest@example.com")


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    behavior = "ok"

    def __init__(self, host, port, timeout=0):
        self.host, self.port, self.timeout = host, port, timeout
        self.started_tls = False
        self.login_args = None
        self.messages = []
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        if FakeSMTP.behavior == "auth":
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        self.login_args = (username, password)

    def send_message(self, message):
        if FakeSMTP.behavior == "timeout":
            raise socket.timeout("timed out")
        if FakeSMTP.behavior == "uncertain":
            raise smtplib.SMTPException("connection dropped after DATA")
        self.messages.append(message)

    def quit(self):
        self.quit_called = True


@pytest.fixture
def env(tmp_path, monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.behavior = "ok"
    monkeypatch.setattr("backend.modules.delivery.smtp.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("backend.modules.delivery.smtp.smtplib.SMTP_SSL", FakeSMTP)
    rig = make_rig(tmp_path, seed_access=True)
    service = EmailService(rig.db, access=rig.access, encryption_secret=TEST_ENCRYPTION_SECRET)
    sender = SmtpEmailSender(service)
    admin = rig.seed_user(role="super_admin", username=f"mail_{uuid.uuid4().hex[:6]}")
    user = rig.seed_user(role="user", username=f"mailu_{uuid.uuid4().hex[:6]}")
    yield rig, service, sender, admin, user
    rig.db.close()


def _enable(service, admin):
    service.save_config(
        admin, host="smtp.example.com", port=587, username="bot@example.com",
        password="smtp-secret", sender_email="bot@example.com",
        sender_name="EasyChat", use_tls=True, enabled=True,
    )


def test_config_password_encrypted_and_masked(env):
    rig, service, _, admin, _ = env
    view = service.save_config(
        admin, host="smtp.example.com", port=587, username="bot@example.com",
        password="smtp-secret", sender_email="bot@example.com",
        sender_name="EasyChat", use_tls=True, enabled=True,
    )
    assert "smtp-secret" not in view.password_masked
    row = rig.db.connect()
    try:
        raw = row.execute("SELECT password_cipher FROM email_configs WHERE id=1").fetchone()
    finally:
        row.close()
    assert raw["password_cipher"] and "smtp-secret" not in raw["password_cipher"]


def test_config_requires_system_config(env):
    _, service, _, _, user = env
    with pytest.raises(ForbiddenError):
        service.get_config(user)
    with pytest.raises(ForbiddenError):
        service.save_config(
            user, host="h", port=587, username="", password="", sender_email="a@b.c",
            sender_name="x", use_tls=True, enabled=True,
        )


async def test_disabled_smtp_does_not_connect(env):
    _, service, sender, _, _ = env
    assert await sender.can_deliver(TARGET) is False
    result = await sender.send_text(TARGET, "hello")
    assert result.ok is False
    assert FakeSMTP.instances == []  # 未启用不建立连接


async def test_fake_smtp_sends_text(env):
    _, service, sender, admin, _ = env
    _enable(service, admin)
    assert await sender.can_deliver(TARGET) is True
    result = await sender.send_text(TARGET, "提醒内容")
    assert result.ok is True
    smtp = FakeSMTP.instances[0]
    assert smtp.started_tls and smtp.login_args == ("bot@example.com", "smtp-secret")
    assert smtp.messages[0]["To"] == "dest@example.com"
    assert "提醒内容" in smtp.messages[0].get_content()
    assert smtp.quit_called


async def test_smtp_failure_classification(env):
    _, service, sender, admin, _ = env
    _enable(service, admin)

    FakeSMTP.behavior = "timeout"
    assert (await sender.send_text(TARGET, "x")).retryable is True

    FakeSMTP.behavior = "auth"
    assert (await sender.send_text(TARGET, "x")).ok is False

    FakeSMTP.behavior = "uncertain"
    assert (await sender.send_text(TARGET, "x")).uncertain is True


async def test_send_artifact_attaches_pdf(env, tmp_path):
    _, service, sender, admin, _ = env
    _enable(service, admin)
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    result = await sender.send_artifact(TARGET, str(pdf), subject="日报", body="见附件")
    assert result.ok is True
    message = FakeSMTP.instances[0].messages[0]
    assert message["Subject"] == "日报"
    assert any(part.get_filename() == "report.pdf" for part in message.iter_attachments())


async def test_missing_artifact_fails_without_smtp(env):
    _, service, sender, admin, _ = env
    _enable(service, admin)
    result = await sender.send_artifact(TARGET, "/no/such/report.pdf", subject="x")
    assert result.ok is False
    assert FakeSMTP.instances == []


def test_recipients_permissions_and_deactivate(env):
    _, service, _, admin, user = env
    mine = service.add_recipient(user, name="自己", address="self@example.com")
    assert service.list_recipients(user)[0]["address"] == "self@example.com"
    with pytest.raises(ForbiddenError):
        service.list_recipients(user, owner_id=admin.user_id)
    service.deactivate(user, mine["id"])
    assert service.list_recipients(user)[0]["active"] == 0
