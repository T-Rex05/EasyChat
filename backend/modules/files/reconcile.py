"""中断恢复对账（设计 §4）：文件系统与 SQLite 之间没有原子事务。

`reconcile` 只做可幂等的核对与修复：
- 收据停在 receiving/finalizing：按预期 storage_key + sha256 判断文件是否已落盘；
  已落盘 → 补提交 ready；未落盘 → 标 failed（保留收据，可重试）；
- stored_files 停在 finalizing：hash 一致则补 ready，不一致/缺失则 failed；
- ready 但物理文件缺失：标 missing，绝不伪造 ready；
- 孤立文件：只报告（含宽限期判断），删除留给 lifecycle 且要求无引用。

不重跑任何有副作用的业务任务（解析/导入/投递）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.modules.files.contracts import (
    FILE_FAILED,
    FILE_FINALIZING,
    FILE_MISSING,
    FILE_READY,
    FILE_RECEIVING,
    ReconcileReport,
)

logger = logging.getLogger(__name__)


def reconcile_files(service: Any, *, limit: int = 50, grace_hours: int = 24) -> ReconcileReport:
    store = service.store
    repo = service.repo
    recovered = 0
    failed = 0
    missing = 0
    details: list[str] = []

    # 1. 未完成收据
    receipts = repo.list_receipts(states=[FILE_RECEIVING, FILE_FINALIZING], limit=limit)
    for receipt in receipts:
        receipt_id = str(receipt["id"])
        file_id = str(receipt.get("file_id") or "")
        key = str(receipt.get("expected_key") or "")
        expected_sha = str(receipt.get("expected_sha256") or "")
        staging = store.staging_path(receipt_id)
        if key:
            actual = store.sha256_of(key)
            if actual is not None and (not expected_sha or actual == expected_sha):
                if not file_id:
                    file_id = _file_id_for_key(repo, key)
                if file_id:
                    repo.commit_ready(file_id=file_id, receipt_id=receipt_id)
                    recovered += 1
                    details.append(f"recovered receipt {receipt_id}")
                    continue
            repo.mark_failed(
                file_id=file_id, receipt_id=receipt_id,
                error="中断：文件未落盘或 hash 不一致",
            )
            failed += 1
            details.append(f"failed receipt {receipt_id}")
            continue
        # 尚未进入 finalizing：清理暂存半成品，允许平台重投
        try:
            staging.unlink(missing_ok=True)
        except OSError:
            pass
        repo.mark_failed(receipt_id=receipt_id, error="中断：未完成写入")
        failed += 1
        details.append(f"failed receipt {receipt_id}")

    # 2. finalizing 文件
    for row in repo.list_by_status(statuses=[FILE_FINALIZING], limit=limit):
        file_id = str(row["id"])
        key = str(row["storage_key"])
        expected = str(row["sha256"] or "")
        actual = store.sha256_of(key)
        if actual is None:
            repo.update_file(file_id, status=FILE_FAILED, error="中断：目标文件不存在")
            failed += 1
            details.append(f"failed file {file_id}")
        elif expected and actual != expected:
            repo.update_file(file_id, status=FILE_FAILED, error="hash 与登记不一致")
            failed += 1
            details.append(f"hash mismatch file {file_id}")
        else:
            repo.mark_ready(file_id)
            recovered += 1
            details.append(f"recovered file {file_id}")

    # 3. ready 但物理缺失
    for row in repo.list_by_status(statuses=[FILE_READY], limit=limit):
        key = str(row["storage_key"])
        if store.stat(key) is None:
            repo.update_file(str(row["id"]), status=FILE_MISSING, error="物理文件缺失")
            missing += 1
            details.append(f"missing file {row['id']}")

    # 4. 孤立文件（只在磁盘、DB 无记录）：只报告，不删除
    orphans, orphan_details = _find_orphans(repo, store, grace_hours=grace_hours, limit=limit)
    details.extend(orphan_details)
    return ReconcileReport(
        recovered=recovered,
        marked_missing=missing,
        marked_failed=failed,
        orphans=tuple(orphans),
        checked_receipts=len(receipts),
        details=tuple(details),
    )


def _file_id_for_key(repo: Any, storage_key: str) -> str:
    conn = repo.db.connect()
    try:
        row = conn.execute(
            "SELECT id FROM stored_files WHERE storage_key=?", (storage_key,)
        ).fetchone()
        return str(row["id"]) if row else ""
    finally:
        conn.close()


def _find_orphans(
    repo: Any, store: Any, *, grace_hours: int, limit: int
) -> tuple[list[str], list[str]]:
    """上传目录中超过宽限期、且 DB 无记录的文件（只报告）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(0, int(grace_hours)))
    uploads = Path(store.root) / "uploads"
    if not uploads.exists():
        return [], []
    orphans: list[str] = []
    details: list[str] = []
    checked = 0
    for path in sorted(uploads.rglob("*")):
        if not path.is_file():
            continue
        checked += 1
        if checked > 5000:
            break
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime > cutoff:
            continue
        rel = path.relative_to(store.root).as_posix()
        if _file_id_for_key(repo, rel):
            continue
        orphans.append(rel)
        details.append(f"orphan {rel}")
        if len(orphans) >= limit:
            break
    return orphans, details
