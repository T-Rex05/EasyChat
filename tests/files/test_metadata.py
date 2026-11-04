"""F1：统一文件模型 + 0011 迁移（元数据、归属隔离、内容去重与引用）。"""
from __future__ import annotations

import hashlib

import pytest

from backend.modules.files.contracts import (
    DELETE_SCOPE_FILE_ONLY,
    FILE_DELETED,
    FILE_READY,
    REF_ATTACHMENT,
    REF_SESSION,
    SaveMetadata,
)
from backend.platform.sqlite import Database, load_migrations
from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError
from tests.files.helpers import chunks_of, make_files_rig
from tests.support.rig import make_rig


def _sqlite_column_names(db, table: str) -> set[str]:
    conn = db.connect()
    try:
        return {str(r["name"]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    finally:
        conn.close()


# ---- 迁移 -------------------------------------------------------------------


def test_migration_0011_creates_tables_and_legacy_columns(tmp_path):
    db = Database(tmp_path / "data" / "app.db")
    applied = db.migrate()
    assert "0011" in applied
    assert db.migrate() == []  # 重复启动幂等
    conn = db.connect()
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        checksums = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())
    finally:
        conn.close()
    assert {"stored_files", "upload_receipts", "file_references", "file_extractions"} <= tables
    assert "uq_stored_files_owner_hash" in indexes
    assert "uq_upload_receipt_request" in indexes
    # 已提交迁移没有被改写（按磁盘文件重算 checksum 与登记值比对）
    from pathlib import Path

    expected = dict(load_migrations(Path("backend/platform/migrations")))
    for version in ("0001", "0010", "0011"):
        assert version in checksums
        assert hashlib.sha256(expected[version].encode()).hexdigest() == checksums[version]
    # 旧表追加 stored_file_id，保持旧 ID 可用
    assert "stored_file_id" in _sqlite_column_names(db, "attachments")
    assert "stored_file_id" in _sqlite_column_names(db, "artifacts")


# ---- 保存与读取 ---------------------------------------------------------------


async def test_save_and_get_roundtrip(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        payload = "交易时间,金额\n2026-10-02,10.00\n".encode()
        result = await rig.files.save_stream(
            principal, chunks_of(payload),
            SaveMetadata(original_name="合成账单.csv", declared_mime="text/csv"), request_id="req-1",
        )
        record = result.file
        assert record.status == FILE_READY
        assert record.sha256 == hashlib.sha256(payload).hexdigest()
        assert record.size_bytes == len(payload)
        assert record.verified_mime == "text/csv"
        assert record.kind == "spreadsheet"
        assert record.owner_id == principal.user_id
        # 对外元数据不含绝对路径 / storage_key
        import dataclasses

        for field in dataclasses.fields(record):
            value = getattr(record, field.name)
            if isinstance(value, str):
                assert str(tmp_path) not in value
                assert "uploads/" not in value
        fetched = rig.files.get(principal, record.file_id)
        assert fetched.file_id == record.file_id
        with rig.files.open_read(principal, record.file_id) as handle:
            assert handle.read() == payload
    finally:
        await rig.aclose()


async def test_original_name_sanitized_and_not_used_in_path(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        result = await rig.files.save_stream(
            principal, chunks_of(b"abc,def\n1,2\n"),
            SaveMetadata(original_name="../../evil\nname.csv"),
        )
        assert result.file.original_name == "evilname.csv"
        row = rig.files.repo.get_file(result.file.file_id)
        assert row is not None
        assert "evil" not in str(row["storage_key"])
        assert str(row["storage_key"]).startswith(f"uploads/{principal.user_id}/")
        # 磁盘上确实存在且内容一致
        assert (rig.settings.files_root / str(row["storage_key"])).is_file()
    finally:
        await rig.aclose()


async def test_same_owner_same_content_reuses_file_with_separate_receipts(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        payload = b"date,amount\n2026-10-02,10.00\n"
        first = await rig.files.save_stream(
            principal, [payload], SaveMetadata(original_name="a.csv"), request_id="r-a",
        )
        second = await rig.files.save_stream(
            principal, [payload], SaveMetadata(original_name="b.csv"), request_id="r-b",
        )
        assert second.file.file_id == first.file.file_id
        assert second.reused_content is True
        assert second.receipt_id != first.receipt_id
        conn = rig.db.connect()
        try:
            receipts = conn.execute("SELECT count(*) FROM upload_receipts").fetchone()[0]
            files = conn.execute("SELECT count(*) FROM stored_files").fetchone()[0]
        finally:
            conn.close()
        assert receipts == 2
        assert files == 1
    finally:
        await rig.aclose()


async def test_different_owners_do_not_share_content(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        other = rig.seed_user(role="user")
        payload = b"same bytes"
        mine = await rig.files.save_stream(principal, [payload], SaveMetadata(original_name="x.csv"))
        theirs = await rig.files.save_stream(other, [payload], SaveMetadata(original_name="x.csv"))
        assert mine.file.file_id != theirs.file.file_id
        assert rig.files.get(other, theirs.file.file_id).owner_id == other.user_id
        with pytest.raises(NotFoundError):
            rig.files.get(principal, theirs.file.file_id)
        with pytest.raises(NotFoundError):
            rig.files.open_read(principal, theirs.file.file_id)
    finally:
        await rig.aclose()


async def test_same_name_different_content_not_overwritten(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        first = await rig.files.save_stream(
            principal, [b"v1,data\n"], SaveMetadata(original_name="bill.csv"),
        )
        second = await rig.files.save_stream(
            principal, [b"v2,data\n"], SaveMetadata(original_name="bill.csv"),
        )
        assert first.file.file_id != second.file.file_id
        with rig.files.open_read(principal, first.file.file_id) as handle:
            assert handle.read() == b"v1,data\n"
        with rig.files.open_read(principal, second.file.file_id) as handle:
            assert handle.read() == b"v2,data\n"
    finally:
        await rig.aclose()


async def test_idempotent_request_id_returns_same_file(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        payload = b"idempotent"
        first = await rig.files.save_stream(
            principal, [payload], SaveMetadata(original_name="a.csv"), request_id="same-req",
        )
        second = await rig.files.save_stream(
            principal, [payload], SaveMetadata(original_name="a.csv"), request_id="same-req",
        )
        assert second.file.file_id == first.file.file_id
        assert second.duplicate is True
        conn = rig.db.connect()
        try:
            receipts = conn.execute("SELECT count(*) FROM upload_receipts").fetchone()[0]
        finally:
            conn.close()
        assert receipts == 1
    finally:
        await rig.aclose()


async def test_remove_one_reference_keeps_shared_file(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        result = await rig.files.save_stream(
            principal, [b"shared"], SaveMetadata(original_name="s.csv"),
        )
        file_id = result.file.file_id
        assert rig.files.link(principal, file_id, REF_ATTACHMENT, "att_one")
        assert rig.files.link(principal, file_id, REF_ATTACHMENT, "att_two")
        assert rig.files.reference_counts(principal, file_id) == {REF_ATTACHMENT: 2}
        impact = rig.files.request_delete(
            principal, file_id, "unlink", ref_kind=REF_ATTACHMENT, ref_id="att_one",
        )
        assert impact.allowed
        assert rig.files.reference_counts(principal, file_id) == {REF_ATTACHMENT: 1}
        # 原件仍可读，未被误删
        with rig.files.open_read(principal, file_id) as handle:
            assert handle.read() == b"shared"
        # 未指定具体引用时只撤展示引用，原件保留
        rig.files.request_delete(principal, file_id, "unlink")
        assert rig.files.reference_counts(principal, file_id) == {}
        with rig.files.open_read(principal, file_id) as handle:
            assert handle.read() == b"shared"
    finally:
        await rig.aclose()


async def test_delete_file_only_marks_tombstone(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        result = await rig.files.save_stream(
            principal, [b"to-delete"], SaveMetadata(original_name="d.csv"),
        )
        file_id = result.file.file_id
        rig.files.link(principal, file_id, REF_SESSION, "sess_x")
        impact = rig.files.request_delete(principal, file_id, DELETE_SCOPE_FILE_ONLY)
        assert impact.allowed
        row = rig.files.repo.get_file(file_id)
        assert row is not None
        assert row["status"] == FILE_DELETED
        assert row["deleted_at"]
        with pytest.raises(NotFoundError):
            rig.files.get(principal, file_id)
        assert not (rig.settings.files_root / str(row["storage_key"])).exists()
    finally:
        await rig.aclose()


# ---- 授权/失败 ---------------------------------------------------------------


async def test_read_requires_permission_and_owner(tmp_path):
    rig, reader = make_files_rig(tmp_path)
    try:
        owner = rig.seed_user(role="user")
        result = await rig.files.save_stream(
            owner, [b"secret"], SaveMetadata(original_name="a.csv"),
        )
        # 撤销 file.read 后不能读取
        rig.access.repo.set_user_permission(reader.user_id, "file.read", False)
        rig.access.invalidate_all()
        revoked = rig.access.snapshot_principal(reader.user_id)
        with pytest.raises(ForbiddenError):
            rig.files.get(revoked, result.file.file_id)
        rig.access.repo.set_user_permission(reader.user_id, "file.upload", False)
        rig.access.invalidate_all()
        revoked = rig.access.snapshot_principal(reader.user_id)
        with pytest.raises(ForbiddenError):
            await rig.files.save_stream(revoked, [b"x"], SaveMetadata(original_name="b.csv"))
    finally:
        await rig.aclose()


async def test_write_failure_marks_receipt_failed_without_ready_file(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        def broken():
            yield b"first-part"
            raise OSError(28, "No space left on device")

        # 上游流失败按原异常上抛；收据标 failed，不产生 ready 文件
        with pytest.raises(OSError):
            await rig.files.save_stream(
                principal, broken(), SaveMetadata(original_name="big.csv"), request_id="req-fail",
            )
        conn = rig.db.connect()
        try:
            receipts = [dict(r) for r in conn.execute("SELECT * FROM upload_receipts").fetchall()]
            files = conn.execute("SELECT count(*) FROM stored_files").fetchone()[0]
        finally:
            conn.close()
        assert len(receipts) == 1
        assert receipts[0]["state"] == "failed"
        assert files == 0
        # 半成品 .part 已清理
        assert list((rig.settings.files_root / "staging").glob("*.part")) == []
    finally:
        await rig.aclose()


async def test_type_masquerade_uses_verified_content(tmp_path):
    from tests.support.ledger_fixtures import write_png

    rig, principal = make_files_rig(tmp_path)
    try:
        png = write_png(tmp_path / "shot.png", width=8, height=6)
        result = await rig.files.save_stream(
            principal, chunks_of(png.read_bytes()),
            SaveMetadata(original_name="fake.csv", declared_mime="text/csv"),
        )
        assert result.file.verified_mime == "image/png"
        assert result.file.kind == "image"
        row = rig.files.repo.get_file(result.file.file_id)
        assert str(row["storage_key"]).endswith(".png")
    finally:
        await rig.aclose()


async def test_empty_file_rejected(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        with pytest.raises(InvalidInputError):
            await rig.files.save_stream(
                principal, [], SaveMetadata(original_name="empty.csv"), request_id="empty",
            )
    finally:
        await rig.aclose()
