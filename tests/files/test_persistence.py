"""F2：流式保存、受限读取与内容校验（路径穿越/类型/压缩/像素）。"""
from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

import pytest

from backend.modules.files.api import FileService
from backend.modules.files.contracts import FILE_FINALIZING, SaveMetadata
from backend.modules.files.local_store import LocalFileStore
from backend.shared.errors import InvalidInputError, NotFoundError, StorageUnavailableError
from tests.files.helpers import async_chunks_of, chunks_of, make_files_rig
from tests.support.ledger_fixtures import write_png


# ---- 保存失败不留“已保存” ---------------------------------------------------------


async def test_interrupted_stream_then_retry_succeeds(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        payload = b"a,b\n1,2\n"

        def broken():
            yield payload[:3]
            raise ConnectionError("下载中断")

        with pytest.raises(ConnectionError):
            await rig.files.save_stream(
                principal, broken(), SaveMetadata(original_name="bill.csv"), request_id="retry-1",
            )
        conn = rig.db.connect()
        try:
            receipt = dict(conn.execute("SELECT * FROM upload_receipts").fetchone())
            files = conn.execute("SELECT count(*) FROM stored_files").fetchone()[0]
        finally:
            conn.close()
        assert receipt["state"] == "failed"
        assert files == 0
        assert list((rig.settings.files_root / "staging").glob("*.part")) == []

        # 同 request_id 重试：不新增收据，最终成功
        result = await rig.files.save_stream(
            principal, chunks_of(payload), SaveMetadata(original_name="bill.csv"),
            request_id="retry-1",
        )
        assert result.file.status == "ready"
        with rig.files.open_read(principal, result.file.file_id) as handle:
            assert handle.read() == payload
    finally:
        await rig.aclose()


async def test_size_limit_rejected_and_partial_removed(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        with pytest.raises(InvalidInputError):
            await rig.files.save_stream(
                principal, chunks_of(b"x" * 4096),
                SaveMetadata(original_name="big.csv", max_bytes=1024), request_id="too-big",
            )
        assert list((rig.settings.files_root / "staging").glob("*.part")) == []
        conn = rig.db.connect()
        try:
            assert conn.execute("SELECT count(*) FROM stored_files").fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        await rig.aclose()


async def test_hash_mismatch_after_move_fails_without_ready(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        original_finalize = rig.files.store.finalize

        def corrupt(staging, storage_key):
            destination = original_finalize(staging, storage_key)
            destination.write_bytes(destination.read_bytes() + b"tampered")
            return destination

        rig.files.store.finalize = corrupt
        with pytest.raises(StorageUnavailableError):
            await rig.files.save_stream(
                principal, [b"payload"], SaveMetadata(original_name="a.csv"), request_id="hash-1",
            )
        rig.files.store.finalize = original_finalize
        conn = rig.db.connect()
        try:
            row = dict(conn.execute("SELECT * FROM stored_files").fetchone())
            receipt = dict(conn.execute("SELECT * FROM upload_receipts").fetchone())
        finally:
            conn.close()
        assert row["status"] == "failed"
        assert receipt["state"] == "failed"
        assert "hash" in str(row["error"])
        assert not (rig.settings.files_root / str(row["storage_key"])).exists()
    finally:
        await rig.aclose()


# ---- 读取边界 -------------------------------------------------------------------


async def test_only_ready_file_is_readable(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        row_id = rig.files.repo.create_file(
            file_id="fil_" + "1" * 32, owner_id=principal.user_id,
            storage_key=f"uploads/{principal.user_id}/2026/11/fil_{'1' * 32}.csv",
            original_name="pending.csv", declared_mime="text/csv",
            verified_mime="text/csv", size_bytes=3, sha256="abc",
            kind="spreadsheet", status=FILE_FINALIZING, source="web",
        )
        record = rig.files.get(principal, row_id)
        assert record.status == FILE_FINALIZING
        with pytest.raises(InvalidInputError):
            rig.files.open_read(principal, row_id)
    finally:
        await rig.aclose()


async def test_path_traversal_and_absolute_paths_rejected(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        store = rig.files.store
        for key in (
            "uploads/../secret.txt",
            "../../etc/passwd",
            "/etc/passwd",
            "C:/Windows/win.ini",
            "uploads/./../../x",
            "",
            "staging/abc.part",
        ):
            with pytest.raises(InvalidInputError):
                store.absolute_path(key)
    finally:
        await rig.aclose()


async def test_symlink_escape_rejected(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret", encoding="utf-8")
        link = rig.settings.files_root / "uploads" / "link"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            pytest.skip("当前环境不允许创建符号链接")
        with pytest.raises(InvalidInputError):
            rig.files.store.absolute_path("uploads/link/secret.txt")
    finally:
        await rig.aclose()


# ---- 内容校验 -------------------------------------------------------------------


async def test_oversized_image_rejected(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        service = FileService(
            rig.db, access=rig.access, store=rig.files.store, max_image_pixels=100,
        )
        png = write_png(tmp_path / "big.png", width=40, height=40)  # 1600 > 100
        with pytest.raises(InvalidInputError):
            await service.save_stream(
                principal, [png.read_bytes()], SaveMetadata(original_name="big.png"),
            )
        assert list((rig.settings.files_root / "staging").glob("*.part")) == []
    finally:
        await rig.aclose()


async def test_zip_path_traversal_entry_rejected(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        bomb = tmp_path / "evil.xlsx"
        with zipfile.ZipFile(bomb, "w") as archive:
            archive.writestr("xl/workbook.xml", "<workbook/>")
            archive.writestr("../evil.txt", "escape")
        with pytest.raises(InvalidInputError):
            await rig.files.save_stream(
                principal, [bomb.read_bytes()], SaveMetadata(original_name="evil.xlsx"),
            )
        conn = rig.db.connect()
        try:
            assert conn.execute("SELECT count(*) FROM stored_files").fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        await rig.aclose()


async def test_zip_entry_count_limit(tmp_path):
    from backend.modules.files.validation import inspect_zip

    path = tmp_path / "many.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(4):
            archive.writestr(f"entry-{index}.txt", "x")
    info = inspect_zip(path, max_entries=10)
    assert info.entries == 4
    with pytest.raises(InvalidInputError):
        inspect_zip(path, max_entries=2)
    with pytest.raises(InvalidInputError):
        inspect_zip(path, max_uncompressed=2)


# ---- 恢复 ----------------------------------------------------------------------


async def test_move_succeeded_but_db_failed_recovered_by_reconcile(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        original_commit = rig.files.repo.commit_ready

        def failing_commit(**kwargs):
            raise RuntimeError("SQLite 短事务失败（模拟进程中断）")

        rig.files.repo.commit_ready = failing_commit
        with pytest.raises(RuntimeError):
            await rig.files.save_stream(
                principal, [b"recover-me"], SaveMetadata(original_name="r.csv"),
                request_id="recover-1",
            )
        rig.files.repo.commit_ready = original_commit

        conn = rig.db.connect()
        try:
            row = dict(conn.execute("SELECT * FROM stored_files").fetchone())
            receipt = dict(conn.execute("SELECT * FROM upload_receipts").fetchone())
        finally:
            conn.close()
        assert row["status"] == FILE_FINALIZING
        assert receipt["state"] == "finalizing"
        key = str(row["storage_key"])
        assert (rig.settings.files_root / key).is_file()

        report = rig.files.reconcile()
        assert report.recovered >= 1
        record = rig.files.get(principal, row["id"])
        assert record.status == "ready"
        with rig.files.open_read(principal, row["id"]) as handle:
            assert handle.read() == b"recover-me"
        # 原件 hash 未因对账改变
        assert rig.files.store.sha256_of(key) == row["sha256"]
    finally:
        await rig.aclose()


async def test_physical_file_missing_marked_missing(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        result = await rig.files.save_stream(
            principal, [b"vanish"], SaveMetadata(original_name="v.csv"),
        )
        row = rig.files.repo.get_file(result.file.file_id)
        assert row is not None
        (rig.settings.files_root / str(row["storage_key"])).unlink()
        report = rig.files.reconcile()
        assert report.marked_missing >= 1
        assert rig.files.get(principal, result.file.file_id).status == "missing"
        with pytest.raises(NotFoundError):
            rig.files.open_read(principal, result.file.file_id)
    finally:
        await rig.aclose()


async def test_orphan_file_reported_but_not_deleted(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        orphan = (
            rig.settings.files_root / "uploads" / str(principal.user_id)
            / "2026" / "01" / "fil_deadbeef.csv"
        )
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_bytes(b"orphan")
        old = 1_600_000_000
        os.utime(orphan, (old, old))
        report = rig.files.reconcile(grace_hours=0)
        assert any("fil_deadbeef" in item for item in report.orphans)
        assert orphan.exists()  # 只报告，不删除
    finally:
        await rig.aclose()


async def test_staging_only_receipt_failed_by_reconcile(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        # 模拟“写入中进程退出”：收据 receiving + 半成品 .part，没有任何文件元数据
        receipt_id, _ = rig.files.repo.create_receipt(
            owner_id=principal.user_id, request_id="crash-1", original_name="c.csv",
        )
        staging = rig.files.store.staging_path(receipt_id)
        staging.write_bytes(b"half")
        report = rig.files.reconcile()
        assert report.marked_failed >= 1
        receipt = rig.files.repo.get_receipt(receipt_id)
        assert receipt is not None and receipt["state"] == "failed"
        assert not staging.exists()
    finally:
        await rig.aclose()


async def test_store_helpers_do_not_mutate_content(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        payload = b"original-bytes"
        result = await rig.files.save_stream(
            principal, [payload], SaveMetadata(original_name="o.csv"),
        )
        row = rig.files.repo.get_file(result.file.file_id)
        key = str(row["storage_key"])
        before = hashlib.sha256(payload).hexdigest()
        assert rig.files.store.sha256_of(key) == before
        rig.files.reconcile()
        assert rig.files.store.sha256_of(key) == before
        assert (rig.settings.files_root / key).read_bytes() == payload
    finally:
        await rig.aclose()


def test_disk_full_on_write_maps_to_storage_unavailable(tmp_path, monkeypatch):
    """真实写盘 ENOSPC → StorageUnavailableError（不返回“已保存”），并清理半成品。"""
    import asyncio

    store = LocalFileStore(tmp_path / "files")
    real_open = Path.open

    class _FailingWrite:
        def __init__(self, handle) -> None:
            self._handle = handle

        def write(self, _data):
            raise OSError(28, "No space left on device")

        def __getattr__(self, item):
            return getattr(self._handle, item)

    def fake_open(self, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        if self.suffix == ".part" and args and "w" in str(args[0]):
            return _FailingWrite(handle)
        return handle

    monkeypatch.setattr(Path, "open", fake_open)
    staging = store.staging_path("upr_diskfull")
    with pytest.raises(StorageUnavailableError):
        asyncio.run(store.write_chunks([b"payload"], staging_path=staging))
    assert not staging.exists()


async def test_local_store_creates_subdirs(tmp_path):
    store = LocalFileStore(tmp_path / "files")
    for name in ("uploads", "derived", "reports", "staging"):
        assert (tmp_path / "files" / name).is_dir()
    assert store.build_key(
        owner_id=7, file_id="fil_x", extension="csv",
        now=__import__("datetime").datetime(2026, 11, 4, tzinfo=__import__("datetime").timezone.utc),
    ) == "uploads/7/2026/11/fil_x.csv"


async def test_async_chunk_iterable_supported(tmp_path):
    rig, principal = make_files_rig(tmp_path)
    try:
        payload = b"async-stream-payload"
        result = await rig.files.save_stream(
            principal, async_chunks_of(payload, 3), SaveMetadata(original_name="a.csv"),
        )
        with rig.files.open_read(principal, result.file.file_id) as handle:
            assert handle.read() == payload
    finally:
        await rig.aclose()
