"""F11：派生内容过期清理、配额与磁盘水位、原件保护。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.modules.files.contracts import RETENTION_DERIVED, RETENTION_PERMANENT, SaveMetadata
from backend.modules.files.lifecycle import FileLifecycle
from backend.shared.errors import InvalidInputError
from tests.files.helpers import make_files_rig


async def _derived(rig, user, *, name="tmp.csv", data=b"a,b\n1,2\n"):
    return await rig.files.save_derived(
        user, [data], original_name=name, declared_mime="text/csv",
    )


def _backdate(rig, file_id: str, days: int = 30) -> None:
    old = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with rig.files.db.transaction() as conn:
        conn.execute("UPDATE stored_files SET created_at=? WHERE id=?", (old, file_id))


def _lifecycle(rig, **kwargs):
    return FileLifecycle(rig.files, rig.files.store, **kwargs)


async def test_sweep_deletes_only_expired_unreferenced_derived(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        old = await _derived(rig, user, name="old.csv", data=b"old")
        fresh = await _derived(rig, user, name="fresh.csv", data=b"fresh")
        linked = await _derived(rig, user, name="linked.csv", data=b"linked")
        original = await rig.files.save_bytes(
            user, b"original", SaveMetadata(original_name="bill.csv", declared_mime=""),
        )
        rig.files.link(user, linked.file.file_id, "session", "sess-1")

        _backdate(rig, old.file.file_id)
        _backdate(rig, linked.file.file_id)
        _backdate(rig, original.file.file_id)

        report = _lifecycle(rig).sweep_derived()
        assert report.deleted == 1
        assert report.kept_referenced == 1
        with pytest.raises(Exception):
            rig.files.get(user, old.file.file_id)
        assert rig.files.get(user, fresh.file.file_id).status == "ready"
        assert rig.files.get(user, linked.file.file_id).status == "ready"
        assert rig.files.get(user, original.file.file_id).status == "ready"
        assert rig.files.get(user, linked.file.file_id).retention_policy == RETENTION_DERIVED
    finally:
        await rig.aclose()


async def test_dry_run_reports_without_deleting(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        record = await _derived(rig, user)
        _backdate(rig, record.file.file_id)
        report = _lifecycle(rig).sweep_derived(dry_run=True)
        assert report.deleted == 1 and report.freed_bytes >= 3
        assert rig.files.get(user, record.file.file_id).status == "ready"
    finally:
        await rig.aclose()


async def test_permanent_original_never_swept(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        record = await rig.files.save_bytes(
            user, b"xlsx-bytes", SaveMetadata(original_name="bill.xlsx"),
        )
        assert record.file.retention_policy == RETENTION_PERMANENT
        _backdate(rig, record.file.file_id, 365)
        report = _lifecycle(rig).sweep_derived()
        assert report.deleted == 0
        assert rig.files.get(user, record.file.file_id).status == "ready"
    finally:
        await rig.aclose()


async def test_quota_refuses_new_save_without_deleting_old(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        first = await rig.files.save_bytes(
            user, b"0123456789", SaveMetadata(original_name="a.txt"),
        )
        lifecycle = _lifecycle(rig, quota_bytes=10)
        lifecycle.assert_writable(user.user_id, 0)  # 刚好用满，允许
        with pytest.raises(InvalidInputError, match="配额"):
            lifecycle.assert_writable(user.user_id, 1)
        assert rig.files.get(user, first.file.file_id).status == "ready"
    finally:
        await rig.aclose()


async def test_low_watermark_rejects_and_usage_report_lists_kinds(tmp_path):
    rig, user = make_files_rig(tmp_path)
    try:
        record = await rig.files.save_bytes(
            user, b"12345", SaveMetadata(original_name="a.txt"),
        )
        lifecycle = _lifecycle(rig, low_watermark_bytes=10**15)
        with pytest.raises(InvalidInputError, match="磁盘空间"):
            lifecycle.assert_writable(user.user_id, 1)
        lifecycle.low_watermark_bytes = 0
        report = lifecycle.storage_report()
        assert report["used_bytes"] >= 5
        assert report["by_kind"].get(record.file.kind, 0) >= 5
        assert report["free_bytes"] > 0
    finally:
        await rig.aclose()
