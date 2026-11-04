"""文件生命周期：派生内容过期清理、容量水位、删除范围协调。

规则（设计 §6/§9）：
- 原始上传默认长期保留，任何清理都不得触碰 `kind in (image, spreadsheet, document)` 且
  `retention_policy=permanent` 的原件；
- 派生/临时内容（`derived_7d`）超过 7 天且**没有任何业务引用**才清理，先标记删除再删 blob，
  中断最多留下孤儿 blob，不会出现“数据库说可用但文件没了”；
- 容量不足时拒绝新保存，绝不删除旧原件腾空间；
- 账本/报告数据的连锁清理由业务模块负责，这里只做文件与引用。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.modules.files.api import FileService
from backend.modules.files.contracts import RETENTION_DERIVED
from backend.modules.files.local_store import LocalFileStore
from backend.shared.errors import InvalidInputError

DERIVED_TTL_DAYS = 7
SAFE_DIRS = ("uploads", "derived", "reports")
ORIGINAL_KINDS = frozenset({"image", "spreadsheet", "document", "other"})


@dataclass(frozen=True, slots=True)
class SweepResult:
    scanned: int
    deleted: int
    kept_referenced: int
    freed_bytes: int
    dry_run: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned, "deleted": self.deleted,
            "kept_referenced": self.kept_referenced,
            "freed_bytes": self.freed_bytes, "dry_run": self.dry_run,
        }


class FileLifecycle:
    def __init__(
        self,
        files: FileService,
        store: LocalFileStore,
        *,
        derived_ttl_days: int = DERIVED_TTL_DAYS,
        quota_bytes: int = 0,
        low_watermark_bytes: int = 0,
        clock=None,
    ) -> None:
        self.files = files
        self.store = store
        self.derived_ttl_days = max(1, int(derived_ttl_days))
        self.quota_bytes = max(0, int(quota_bytes))
        self.low_watermark_bytes = max(0, int(low_watermark_bytes))
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ---- 清理 ------------------------------------------------------------------

    def sweep_derived(self, *, now: datetime | None = None, dry_run: bool = False) -> SweepResult:
        moment = now or self.clock()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        cutoff = (moment - timedelta(days=self.derived_ttl_days)).isoformat()
        rows = self.files.repo.list_expired(
            retention_policy=RETENTION_DERIVED, before=cutoff, limit=500,
        )
        deleted = kept = freed = 0
        for row in rows:
            file_id = str(row["id"])
            if row["status"] != "ready":
                continue
            if self.files.repo.reference_counts(file_id):
                kept += 1
                continue
            if dry_run:
                deleted += 1
                freed += int(row.get("size_bytes") or 0)
                continue
            # 先让数据库进入 deleted，再删 blob；中断的孤儿文件由备份校验/巡检发现
            self.files.repo.mark_deleted(file_id)
            self.store.delete(str(row["storage_key"]))
            deleted += 1
            freed += int(row.get("size_bytes") or 0)
        return SweepResult(
            scanned=len(rows), deleted=deleted, kept_referenced=kept,
            freed_bytes=freed, dry_run=dry_run,
        )

    # ---- 容量 ------------------------------------------------------------------

    def usage(self, owner_id: int | None = None) -> dict[str, int]:
        used = 0
        for name in SAFE_DIRS:
            base = self.store.root / name
            if owner_id is not None and name == "uploads":
                base = base / str(int(owner_id))
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    try:
                        used += path.stat().st_size
                    except OSError:
                        continue
        free = self.store.disk_free_bytes()
        return {"used_bytes": used, "free_bytes": free, "quota_bytes": self.quota_bytes}

    def assert_writable(self, owner_id: int, incoming_bytes: int = 0) -> None:
        """容量/配额不足时明确拒绝，不清理旧原件。"""
        incoming = max(0, int(incoming_bytes))
        usage = self.usage(owner_id)
        if self.quota_bytes and usage["used_bytes"] + incoming > self.quota_bytes:
            raise InvalidInputError(
                f"存储配额不足（已用 {usage['used_bytes']} 字节，配额 {self.quota_bytes} 字节）；"
                "请清理或调整配额，系统不会删除已保存的原始文件"
            )
        if usage["free_bytes"] - incoming < self.low_watermark_bytes:
            raise InvalidInputError(
                f"磁盘空间不足（可用 {usage['free_bytes']} 字节，保留水位 {self.low_watermark_bytes} 字节）"
            )

    def storage_report(self) -> dict[str, Any]:
        usage = self.usage()
        by_kind: dict[str, int] = {}
        conn = self.files.db.connect()
        try:
            rows = conn.execute(
                "SELECT kind, COALESCE(SUM(size_bytes), 0) AS total FROM stored_files "
                "WHERE status='ready' GROUP BY kind"
            ).fetchall()
            for row in rows:
                by_kind[str(row["kind"])] = int(row["total"])
        finally:
            conn.close()
        return {**usage, "by_kind": by_kind, "root": str(Path(self.store.root).name)}


__all__ = ["DERIVED_TTL_DAYS", "FileLifecycle", "SweepResult"]
