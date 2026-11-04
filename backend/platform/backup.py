"""文件 + SQLite 的一致性备份/校验/恢复（部署运维用，非业务代码）。

约束：
- SQLite 用官方 backup API 取一致性快照，不能直接复制正在写入的 `app.db`；
- 文件按 `stored_files.storage_key` 逐份复制并校验 sha256，`staging/` 不备份；
- 备份先写临时目录，manifest 写成功后再原子改名，半成品不会被当成可用备份；
- 恢复前必须 `verify_backup` 通过，并把现有数据改名保留（不直接覆盖）。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

BACKUP_MANIFEST = "manifest.json"
BACKUP_DB = "app.db"
BACKUP_FILES = "files"
SAFE_FILE_SUBDIRS = ("uploads", "derived", "reports")
_CHUNK = 1024 * 1024


class BackupError(Exception):
    """备份/校验/恢复失败（信息足够运维定位，不吞底层原因）。"""


@dataclass(frozen=True, slots=True)
class BackupInfo:
    path: Path
    db_sha256: str
    files: int
    bytes: int
    created_at: str


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    problems: tuple[str, ...]
    db_rows: int
    files: int

    def raise_if_bad(self) -> None:
        if not self.ok:
            raise BackupError("备份校验失败: " + "; ".join(self.problems[:10]))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _snapshot_sqlite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise BackupError(f"无法只读打开数据库: {exc}") from exc
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        raise BackupError(f"数据库快照失败: {exc}") from exc
    finally:
        src.close()


def _ready_files(db_path: Path) -> list[tuple[str, str, int]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT storage_key, sha256, size_bytes FROM stored_files "
            "WHERE status='ready' ORDER BY storage_key"
        ).fetchall()
    finally:
        conn.close()
    return [(str(r[0]), str(r[1]), int(r[2])) for r in rows]


def create_backup(
    *, db_path: Path, files_root: Path, dest: Path | None = None,
) -> BackupInfo:
    """创建一致性备份；失败不留半成品。"""
    db_path = Path(db_path)
    files_root = Path(files_root)
    if not db_path.is_file():
        raise BackupError(f"数据库不存在: {db_path}")
    target = Path(dest) if dest else db_path.parent / "backups" / f"backup-{_utc_stamp()}"
    if target.exists() and any(target.iterdir()):
        raise BackupError(f"备份目录非空: {target}")
    staging = target.with_name(target.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        _snapshot_sqlite(db_path, staging / BACKUP_DB)
        db_sha = _sha256(staging / BACKUP_DB)
        entries: list[dict[str, Any]] = []
        total_bytes = 0
        for storage_key, sha, size in _ready_files(staging / BACKUP_DB):
            source = files_root / storage_key
            if not source.is_file():
                raise BackupError(f"数据库引用的文件缺失: {storage_key}")
            destination = staging / BACKUP_FILES / storage_key
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied = _sha256(destination)
            if copied != sha:
                raise BackupError(f"复制后校验不一致: {storage_key}")
            entries.append({"key": storage_key, "sha256": sha, "size": size})
            total_bytes += size
        manifest = {
            "format": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "db": {"path": BACKUP_DB, "sha256": db_sha},
            "files_root": str(files_root),
            "files": entries,
        }
        (staging / BACKUP_MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        if target.exists():
            target.rmdir()
        os.replace(staging, target)
        return BackupInfo(
            path=target, db_sha256=db_sha, files=len(entries),
            bytes=total_bytes, created_at=str(manifest["created_at"]),
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _read_manifest(backup_dir: Path) -> dict[str, Any]:
    path = backup_dir / BACKUP_MANIFEST
    if not path.is_file():
        raise BackupError(f"缺少 {BACKUP_MANIFEST}: {backup_dir}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError(f"manifest 不可读: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != 1:
        raise BackupError("manifest 版本不支持")
    return data


def verify_backup(backup_dir: Path) -> VerifyResult:
    backup_dir = Path(backup_dir)
    problems: list[str] = []
    manifest = _read_manifest(backup_dir)
    db_file = backup_dir / str((manifest.get("db") or {}).get("path") or BACKUP_DB)
    if not db_file.is_file():
        return VerifyResult(False, (f"缺少数据库快照: {db_file.name}",), 0, 0)
    if _sha256(db_file) != (manifest.get("db") or {}).get("sha256"):
        problems.append("数据库快照 hash 不一致")
    try:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            check = conn.execute("PRAGMA integrity_check").fetchone()
            if not check or check[0] != "ok":
                problems.append(f"数据库完整性失败: {check}")
            db_rows = int(conn.execute("SELECT count(*) FROM stored_files").fetchone()[0])
            db_keys = {
                str(r[0]) for r in conn.execute(
                    "SELECT storage_key FROM stored_files WHERE status='ready'"
                ).fetchall()
            }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return VerifyResult(False, (f"数据库不可读: {exc}",), 0, 0)
    entries = manifest.get("files") or []
    listed: set[str] = set()
    for entry in entries:
        key = str(entry.get("key") or "")
        listed.add(key)
        path = backup_dir / BACKUP_FILES / key
        if not path.is_file():
            problems.append(f"缺少文件: {key}")
            continue
        if _sha256(path) != entry.get("sha256"):
            problems.append(f"文件 hash 不一致: {key}")
    missing = sorted(db_keys - listed)
    if missing:
        problems.append(f"manifest 缺少 {len(missing)} 个数据库引用文件")
    return VerifyResult(not problems, tuple(problems), db_rows, len(entries))


def restore_backup(
    backup_dir: Path, *, db_path: Path, files_root: Path,
) -> dict[str, Any]:
    """先校验再恢复；现有数据改名保留，失败不回滚已通过校验的备份内容。"""
    backup_dir = Path(backup_dir)
    db_path = Path(db_path)
    files_root = Path(files_root)
    result = verify_backup(backup_dir)
    result.raise_if_bad()
    manifest = _read_manifest(backup_dir)
    stamp = _utc_stamp()
    preserved: list[str] = []
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        keep = db_path.with_name(f"{db_path.name}.pre-restore-{stamp}")
        os.replace(db_path, keep)
        preserved.append(str(keep))
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.exists():
            sidecar.unlink()
    shutil.copyfile(backup_dir / str((manifest["db"]).get("path") or BACKUP_DB), db_path)
    for entry in manifest.get("files") or []:
        key = str(entry["key"])
        source = backup_dir / BACKUP_FILES / key
        destination = files_root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return {
        "db_path": str(db_path),
        "files_root": str(files_root),
        "files_restored": len(manifest.get("files") or []),
        "preserved": preserved,
        "created_at": manifest.get("created_at"),
    }


def iter_backups(directory: Path) -> Iterable[Path]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.iterdir()
         if path.is_dir() and (path / BACKUP_MANIFEST).is_file()),
        key=lambda p: p.name,
    )


__all__ = [
    "BACKUP_MANIFEST",
    "BackupError",
    "BackupInfo",
    "VerifyResult",
    "create_backup",
    "iter_backups",
    "restore_backup",
    "verify_backup",
]
