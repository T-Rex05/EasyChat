"""F11：文件 + SQLite 备份/校验/恢复（真实临时目录，无外部依赖）。"""
from __future__ import annotations

import json

import pytest

from backend.modules.files.contracts import SaveMetadata
from backend.platform.backup import (
    BackupError,
    create_backup,
    iter_backups,
    restore_backup,
    verify_backup,
)
from tests.ledger.helpers import make_ledger_rig
from tests.support.ledger_fixtures import standard_scenario, write_wechat_xlsx


async def _ready(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    path = write_wechat_xlsx(tmp_path / "bills" / "backup.xlsx", standard_scenario())
    saved = await rig.files.save_stream(
        user, [path.read_bytes()],
        SaveMetadata(original_name="backup.xlsx", declared_mime=""),
    )
    view = await rig.ledger.register_import(user, saved.file.file_id, parse_now=True)
    rig.ledger.commit_import(user, view.import_id)
    return rig, user, saved


async def test_backup_copies_db_and_files_with_manifest(tmp_path):
    rig, _user, saved = await _ready(tmp_path)
    try:
        info = create_backup(
            db_path=rig.settings.data_db_path,
            files_root=rig.settings.files_root,
            dest=tmp_path / "keep" / "one",
        )
        assert info.path.is_dir()
        assert info.files >= 1
        assert info.bytes > 0
        manifest = json.loads((info.path / "manifest.json").read_text("utf-8"))
        keys = {entry["key"] for entry in manifest["files"]}
        storage = rig.files.repo.get_file(saved.file.file_id)["storage_key"]
        assert storage in keys
        assert not (info.path / "files" / "staging").exists()
        result = verify_backup(info.path)
        assert result.ok, result.problems
        assert result.db_rows >= 1
        assert [p.name for p in iter_backups(tmp_path / "keep")] == ["one"]
    finally:
        await rig.aclose()


async def test_backup_refuses_missing_referenced_file(tmp_path):
    rig, _user, saved = await _ready(tmp_path)
    try:
        rig.files.internal_path(_user, saved.file.file_id).unlink()
        with pytest.raises(BackupError, match="缺失"):
            create_backup(
                db_path=rig.settings.data_db_path,
                files_root=rig.settings.files_root,
                dest=tmp_path / "keep" / "broken",
            )
        assert not (tmp_path / "keep" / "broken").exists()
        assert not (tmp_path / "keep" / "broken.partial").exists()
    finally:
        await rig.aclose()


async def test_verify_detects_tampering(tmp_path):
    rig, _user, saved = await _ready(tmp_path)
    try:
        info = create_backup(
            db_path=rig.settings.data_db_path,
            files_root=rig.settings.files_root,
            dest=tmp_path / "keep" / "one",
        )
        storage = rig.files.repo.get_file(saved.file.file_id)["storage_key"]
        (info.path / "files" / storage).write_bytes(b"tampered")
        result = verify_backup(info.path)
        assert result.ok is False
        assert any("hash 不一致" in problem for problem in result.problems)
        with pytest.raises(BackupError):
            restore_backup(
                info.path, db_path=tmp_path / "restored.db",
                files_root=tmp_path / "restored_files",
            )
    finally:
        await rig.aclose()


async def test_restore_rebuilds_working_copy(tmp_path):
    rig, user, saved = await _ready(tmp_path)
    try:
        info = create_backup(
            db_path=rig.settings.data_db_path,
            files_root=rig.settings.files_root,
            dest=tmp_path / "keep" / "one",
        )
        target_db = tmp_path / "restore" / "data" / "app.db"
        target_files = tmp_path / "restore" / "data"
        report = restore_backup(info.path, db_path=target_db, files_root=target_files)
        assert report["files_restored"] >= 1
        assert target_db.is_file()
        assert verify_backup(info.path).ok
        # 恢复后的数据库能独立打开，且文件内容与原始 sha256 一致
        from backend.platform.sqlite import Database

        restored = Database(target_db)
        conn = restored.connect()
        try:
            row = conn.execute(
                "SELECT storage_key, sha256 FROM stored_files WHERE id=?",
                (saved.file.file_id,),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert (target_files / row["storage_key"]).is_file()
    finally:
        await rig.aclose()


async def test_restore_preserves_existing_database(tmp_path):
    rig, _user, _saved = await _ready(tmp_path)
    try:
        info = create_backup(
            db_path=rig.settings.data_db_path,
            files_root=rig.settings.files_root,
            dest=tmp_path / "keep" / "one",
        )
        report = restore_backup(
            info.path, db_path=rig.settings.data_db_path,
            files_root=rig.settings.files_root,
        )
        assert report["preserved"]
        assert all(p for p in report["preserved"])
    finally:
        await rig.aclose()


async def test_backup_rejects_non_empty_destination(tmp_path):
    rig, _user, _saved = await _ready(tmp_path)
    try:
        dest = tmp_path / "keep" / "busy"
        dest.mkdir(parents=True)
        (dest / "x.txt").write_text("x", encoding="utf-8")
        with pytest.raises(BackupError, match="非空"):
            create_backup(
                db_path=rig.settings.data_db_path,
                files_root=rig.settings.files_root,
                dest=dest,
            )
    finally:
        await rig.aclose()
