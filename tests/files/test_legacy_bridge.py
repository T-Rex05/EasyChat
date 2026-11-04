"""F3：旧 attachment_id/artifact_id 桥接 + 微信媒体走统一文件权威。"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.modules.channels.contracts import MediaRef
from backend.modules.files.contracts import REF_ATTACHMENT, SaveMetadata
from backend.runtime.contracts import RuntimeEvent
from backend.shared.errors import BusyError
from tests.files.helpers import make_files_rig
from tests.support.rig import make_rig
from tests.support.wechat import (
    FakeMediaFetcher,
    image_message,
    inbound,
    make_channel_rig,
    text_message,
)


def _rows(rig, sql: str, params=()):
    conn = rig.db.connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _admin(rig):
    return rig.seed_user(role="super_admin", username=f"admin_{uuid.uuid4().hex[:6]}")


def _user(rig):
    return rig.seed_user(role="user", grants=("chat.use",), username=f"u_{uuid.uuid4().hex[:6]}")


def _register(rig, admin, account_id: str = "bot_1"):
    view = rig.channels.register_account(
        admin, account_id=account_id, token="bot-token",
        base_url="https://ilink.test", bot_user_id=f"botuser_{account_id}",
    )
    return rig.channels.repo.get_account(view.id)


def _bind(rig, admin, account, external_user: str, user):
    return rig.channels.bind_user(
        admin, platform="wechat", account_id=account.account_id,
        external_user_id=external_user, user_id=user.user_id, account_pk=account.id,
    )


# ---- 旧 ID 桥接 ----------------------------------------------------------------


async def test_attachment_keeps_legacy_id_and_links_stored_file(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        rig.attach_assistant()
        result = await rig.files.save_stream(
            principal, [b"legacy-bytes"], SaveMetadata(original_name="old.csv"),
        )
        attachment_id = await rig.assistant.register_attachment(
            principal, file_name="old.csv", file_path="",
            mime=result.file.verified_mime, file_size=result.file.size_bytes,
            sha256=result.file.sha256, stored_file_id=result.file.file_id,
        )
        assert attachment_id.startswith("att_")
        row = await rig.assistant.get_attachment(principal, attachment_id)
        assert row["stored_file_id"] == result.file.file_id
        assert rig.files.link(principal, result.file.file_id, REF_ATTACHMENT, attachment_id)
        assert rig.files.files_for_target(principal, REF_ATTACHMENT, attachment_id) == [
            result.file.file_id
        ]
    finally:
        await rig.aclose()


async def test_legacy_attachment_without_stored_file_still_works(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        rig.attach_assistant()
        legacy_path = tmp_path / "legacy.txt"
        legacy_path.write_text("legacy", encoding="utf-8")
        attachment_id = await rig.assistant.register_attachment(
            principal, file_name="legacy.txt", file_path=str(legacy_path), mime="text/plain",
        )
        row = await rig.assistant.get_attachment(principal, attachment_id)
        assert row["stored_file_id"] is None
        assert row["file_path"] == str(legacy_path)
    finally:
        await rig.aclose()


async def test_artifact_carries_stored_file_id(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        from backend.modules.delivery.api import DeliveryService
        from backend.modules.delivery.wechat import DisabledDeliverySender

        delivery = DeliveryService(rig.db, sender=DisabledDeliverySender())
        result = await rig.files.save_stream(
            principal, [b"%PDF-1.4 fake"], SaveMetadata(original_name="r.pdf", kind="report"),
        )
        artifact_id = delivery.repo.create_artifact(
            owner_id=principal.user_id, kind="report", file_path="/tmp/x.pdf",
            sha256=result.file.sha256, file_size=result.file.size_bytes,
            mime="application/pdf", stored_file_id=result.file.file_id,
        )
        artifact = delivery.repo.get_artifact(artifact_id)
        assert artifact["stored_file_id"] == result.file.file_id
        assert artifact["file_path"] == "/tmp/x.pdf"  # 旧发送路径保持可用
    finally:
        await rig.aclose()


# ---- 微信媒体 ------------------------------------------------------------------


async def _channel_env(tmp_path):
    rig, transport, fetcher = make_channel_rig(tmp_path)
    await rig.start_assistant()
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_ext_1", user)
    return rig, transport, fetcher, admin, user, account


async def test_wechat_image_saved_to_files_with_receipt(tmp_path):
    rig, transport, fetcher, admin, user, account = await _channel_env(tmp_path)
    try:
        outcome = await rig.channels.handle_inbound(
            inbound(rig, account, image_message(message_id="m-media-file-1"))
        )
        assert outcome.accepted is True
        files = _rows(rig, "SELECT * FROM stored_files")
        assert len(files) == 1
        assert files[0]["source"] == "wechat"
        assert files[0]["status"] == "ready"
        receipts = _rows(rig, "SELECT * FROM upload_receipts")
        assert len(receipts) == 1
        assert receipts[0]["channel"] == "wechat"
        assert receipts[0]["external_event_id"] == "msg:wx_ext_1:m-media-file-1"
        assert receipts[0]["media_index"] == 0
        attachments = _rows(rig, "SELECT * FROM attachments")
        assert len(attachments) == 1
        assert attachments[0]["stored_file_id"] == files[0]["id"]
        # 渠道临时目录中的文件已移入受管目录
        assert list((tmp_path / "media").rglob("*.png")) == []
    finally:
        await rig.aclose()


async def test_wechat_redelivery_reuses_receipt_without_new_file(tmp_path):
    rig, transport, fetcher, admin, user, account = await _channel_env(tmp_path)
    try:
        msg = image_message(message_id="m-media-dup")
        first = await rig.channels.handle_inbound(inbound(rig, account, msg))
        assert first.accepted is True
        second = await rig.channels.handle_inbound(inbound(rig, account, msg))
        assert second.duplicate is True
        assert len(_rows(rig, "SELECT * FROM stored_files")) == 1
        assert len(_rows(rig, "SELECT * FROM upload_receipts")) == 1
        assert len(fetcher.calls) == 1  # 不重复下载
    finally:
        await rig.aclose()


async def test_media_only_failure_keeps_text_path_working(tmp_path):
    rig, transport, fetcher, admin, user, account = await _channel_env(tmp_path)
    try:
        fetcher.fail_next = True
        outcome = await rig.channels.handle_inbound(
            inbound(rig, account, text_message("你好", message_id="m-text-after-fail"))
        )
        assert outcome.accepted is True
        assert _rows(rig, "SELECT * FROM stored_files") == []
    finally:
        await rig.aclose()


async def test_file_saved_then_submit_busy_is_recoverable(tmp_path):
    """媒体已持久保存但 Assistant 提交因 Busy 失败：原件/收据仍在，可复用。"""
    rig, transport, fetcher, admin, user, account = await _channel_env(tmp_path)
    try:
        original_submit = rig.assistant.submit
        calls = {"n": 0}

        async def busy_once(command: RunCommand):
            calls["n"] += 1
            raise BusyError("测试注入 Busy")

        rig.assistant.submit = busy_once
        outcome = await rig.channels.handle_inbound(
            inbound(rig, account, image_message(message_id="m-media-busy"))
        )
        assert outcome.accepted is False
        assert outcome.reason == "busy"
        rig.assistant.submit = original_submit

        rows = _rows(rig, "SELECT * FROM stored_files")
        assert len(rows) == 1
        assert rows[0]["status"] == "ready"
        receipts = _rows(rig, "SELECT * FROM upload_receipts")
        assert receipts[0]["state"] == "ready"

        # 恢复：同一媒体重投（同账号/事件/序号）返回原文件，不重复落盘
        principal = rig.access.snapshot_principal(user.user_id)
        result = await rig.files.save_stream(
            principal, [b"should-not-be-written"],
            SaveMetadata(
                original_name="again.png", source="wechat", channel="wechat",
                account_id=account.id, external_event_id="msg:wx_ext_1:m-media-busy",
                media_index=0,
            ),
        )
        assert result.duplicate is True
        assert result.file.file_id == rows[0]["id"]
        assert len(_rows(rig, "SELECT * FROM stored_files")) == 1
    finally:
        await rig.aclose()


async def test_channel_media_fetch_still_rejects_non_wechat_hosts(tmp_path):
    """SSRF 白名单仍由渠道 Adapter 负责，不被 files 绕过。"""
    from backend.modules.channels.wechat.media import HttpMediaFetcher, MediaFetchError

    transport = type("T", (), {"download_to": None})()
    fetcher = HttpMediaFetcher(transport)
    with pytest.raises(MediaFetchError):
        await fetcher.fetch(MediaRef(kind="image", url="http://127.0.0.1/x.png"), tmp_path)
