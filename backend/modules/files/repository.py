"""files 模块数据访问：stored_files / upload_receipts / file_references / file_extractions。

只由 files 模块写入；其他模块通过 `api.py` 调用，不直接使用本类。
返回 dict 只在本模块内部流转；对外一律转换成 FileRecord（无路径）。
"""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

from backend.modules.files.contracts import (
    FILE_DELETED,
    FILE_READY,
    FILE_RECEIVING,
    RETENTION_PERMANENT,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.identifiers import (
    new_extraction_id,
    new_file_reference_id,
    new_upload_receipt_id,
)

_FILE_WRITABLE = frozenset(
    {
        "original_name", "declared_mime", "verified_mime", "size_bytes", "sha256",
        "kind", "status", "source", "retention_policy", "error", "deleted_at",
        "storage_key",
    }
)
_RECEIPT_WRITABLE = frozenset(
    {
        "file_id", "state", "expected_key", "expected_sha256", "expected_size",
        "original_name", "error",
    }
)


class FileRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- 收据 ------------------------------------------------------------------

    def find_receipt(
        self,
        *,
        owner_id: int,
        request_id: str = "",
        channel: str = "",
        account_id: str = "",
        external_event_id: str = "",
        media_index: int = -1,
    ) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            if request_id:
                row = conn.execute(
                    "SELECT * FROM upload_receipts WHERE owner_id=? AND request_id=?",
                    (owner_id, request_id),
                ).fetchone()
                return dict(row) if row else None
            if external_event_id and media_index >= 0:
                row = conn.execute(
                    "SELECT * FROM upload_receipts WHERE channel=? AND account_id=? "
                    "AND external_event_id=? AND media_index=?",
                    (channel, account_id, external_event_id, media_index),
                ).fetchone()
                return dict(row) if row else None
            return None
        finally:
            conn.close()

    def create_receipt(
        self,
        *,
        owner_id: int,
        request_id: str = "",
        channel: str = "",
        account_id: str = "",
        external_event_id: str = "",
        media_index: int = -1,
        original_name: str = "",
        expected_size: int = 0,
    ) -> tuple[str, bool]:
        """插入接收收据；唯一键冲突时返回既有收据（幂等，不产生第二条）。"""
        receipt_id = new_upload_receipt_id()
        now = utc_now_iso()
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO upload_receipts(id, owner_id, request_id, channel, account_id, "
                    "external_event_id, media_index, state, original_name, expected_size, "
                    "received_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        receipt_id, owner_id, request_id, channel, account_id,
                        external_event_id, int(media_index), FILE_RECEIVING,
                        original_name[:255], int(expected_size), now, now,
                    ),
                )
            return receipt_id, True
        except sqlite3.IntegrityError:
            existing = self.find_receipt(
                owner_id=owner_id, request_id=request_id, channel=channel,
                account_id=account_id, external_event_id=external_event_id,
                media_index=media_index,
            )
            if existing is None:  # 唯一索引冲突但查不到：并发窗口，重试一次
                existing = self.find_receipt(
                    owner_id=owner_id, request_id=request_id, channel=channel,
                    account_id=account_id, external_event_id=external_event_id,
                    media_index=media_index,
                )
            if existing is None:
                raise
            return str(existing["id"]), False

    def update_receipt(self, receipt_id: str, **fields: Any) -> None:
        updates = {k: v for k, v in fields.items() if k in _RECEIPT_WRITABLE}
        if not updates:
            return
        assignments = ", ".join(f"{k}=?" for k in updates)
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE upload_receipts SET {assignments}, updated_at=? WHERE id=?",
                (*updates.values(), utc_now_iso(), receipt_id),
            )

    def get_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM upload_receipts WHERE id=?", (receipt_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_receipts(self, *, states: Sequence[str], limit: int = 50) -> list[dict[str, Any]]:
        if not states:
            return []
        placeholders = ",".join("?" * len(states))
        conn = self.db.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM upload_receipts WHERE state IN ({placeholders}) "
                "ORDER BY updated_at LIMIT ?",
                (*states, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 文件 ------------------------------------------------------------------

    def find_by_hash(self, owner_id: int, sha256: str) -> dict[str, Any] | None:
        if not sha256:
            return None
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM stored_files WHERE owner_id=? AND sha256=? AND status<>? "
                "ORDER BY created_at LIMIT 1",
                (owner_id, sha256, FILE_DELETED),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_file(
        self,
        *,
        file_id: str,
        owner_id: int,
        storage_key: str,
        original_name: str,
        declared_mime: str,
        verified_mime: str,
        size_bytes: int,
        sha256: str,
        kind: str,
        status: str,
        source: str,
        retention_policy: str = RETENTION_PERMANENT,
        error: str | None = None,
    ) -> str:
        """登记文件元数据。file_id 由调用方生成（storage_key 依赖它，必须一致）。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO stored_files(id, owner_id, storage_key, original_name, declared_mime, "
                "verified_mime, size_bytes, sha256, kind, status, source, retention_policy, error, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    file_id, owner_id, storage_key, original_name[:255], declared_mime[:200],
                    verified_mime[:200], int(size_bytes), sha256, kind, status, source,
                    retention_policy, error, now, now,
                ),
            )
        return file_id

    def update_file(self, file_id: str, **fields: Any) -> None:
        updates = {k: v for k, v in fields.items() if k in _FILE_WRITABLE}
        if not updates:
            return
        assignments = ", ".join(f"{k}=?" for k in updates)
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE stored_files SET {assignments}, updated_at=? WHERE id=?",
                (*updates.values(), utc_now_iso(), file_id),
            )

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM stored_files WHERE id=?", (file_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_expired(
        self, *, retention_policy: str, before: str, limit: int = 500,
    ) -> list[dict[str, Any]]:
        """按留存策略列出到期文件（供 lifecycle 清理；不跨模块暴露）。"""
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM stored_files WHERE retention_policy=? AND created_at<? "
                "AND status<>'deleted' ORDER BY created_at LIMIT ?",
                (retention_policy, before, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_files(
        self,
        *,
        owner_id: int | None,
        limit: int = 50,
        offset: int = 0,
        kind: str | None = None,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM stored_files WHERE 1=1"
        params: list[Any] = []
        if owner_id is not None:
            sql += " AND owner_id=?"
            params.append(owner_id)
        if not include_deleted:
            sql += " AND status<>?"
            params.append(FILE_DELETED)
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        conn = self.db.connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_by_status(self, *, statuses: Sequence[str], limit: int = 100) -> list[dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ",".join("?" * len(statuses))
        conn = self.db.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM stored_files WHERE status IN ({placeholders}) "
                "ORDER BY updated_at LIMIT ?",
                (*statuses, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def mark_deleted(self, file_id: str) -> None:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE stored_files SET status=?, deleted_at=?, updated_at=? WHERE id=?",
                (FILE_DELETED, now, now, file_id),
            )

    def mark_ready(self, file_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE stored_files SET status=?, error=NULL, updated_at=? WHERE id=?",
                (FILE_READY, utc_now_iso(), file_id),
            )

    def commit_ready(
        self,
        *,
        file_id: str,
        receipt_id: str = "",
        ref_kind: str = "",
        ref_id: str = "",
    ) -> None:
        """移动完成后的一次短事务：文件 ready + 收据 ready + 引用，三者同事务。

        文件系统与 SQLite 没有共享事务：本事务之前崩溃会留下 finalizing 元数据，
        由 reconcile 按 storage_key/hash 对账恢复，不会出现“已保存”假成功。
        """
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE stored_files SET status=?, error=NULL, updated_at=? WHERE id=?",
                (FILE_READY, now, file_id),
            )
            if receipt_id:
                conn.execute(
                    "UPDATE upload_receipts SET state=?, file_id=?, error=NULL, updated_at=? WHERE id=?",
                    (FILE_READY, file_id, now, receipt_id),
                )
            if ref_kind and ref_id:
                conn.execute(
                    "INSERT INTO file_references(id, file_id, owner_id, ref_kind, ref_id, created_at) "
                    "SELECT ?, id, owner_id, ?, ?, ? FROM stored_files WHERE id=? "
                    "ON CONFLICT(file_id, ref_kind, ref_id) DO NOTHING",
                    (new_file_reference_id(), ref_kind, ref_id, now, file_id),
                )

    def mark_failed(
        self, *, file_id: str = "", receipt_id: str = "", error: str = ""
    ) -> None:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            if file_id:
                conn.execute(
                    "UPDATE stored_files SET status=?, error=?, updated_at=? WHERE id=?",
                    ("failed", error[:500], now, file_id),
                )
            if receipt_id:
                conn.execute(
                    "UPDATE upload_receipts SET state=?, error=?, updated_at=? WHERE id=?",
                    ("failed", error[:500], now, receipt_id),
                )

    # ---- 引用 ------------------------------------------------------------------

    def add_reference(
        self, *, file_id: str, owner_id: int, ref_kind: str, ref_id: str
    ) -> bool:
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO file_references(id, file_id, owner_id, ref_kind, ref_id, created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (new_file_reference_id(), file_id, owner_id, ref_kind, ref_id, utc_now_iso()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_reference(self, *, file_id: str, ref_kind: str, ref_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM file_references WHERE file_id=? AND ref_kind=? AND ref_id=?",
                (file_id, ref_kind, ref_id),
            )
            return cur.rowcount > 0

    def reference_counts(self, file_id: str) -> dict[str, int]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT ref_kind, count(*) AS c FROM file_references WHERE file_id=? "
                "GROUP BY ref_kind ORDER BY ref_kind",
                (file_id,),
            ).fetchall()
            return {str(r["ref_kind"]): int(r["c"]) for r in rows}
        finally:
            conn.close()

    def references(self, file_id: str) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM file_references WHERE file_id=? ORDER BY created_at", (file_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def files_for_target(self, ref_kind: str, ref_id: str) -> list[str]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT file_id FROM file_references WHERE ref_kind=? AND ref_id=? "
                "ORDER BY created_at",
                (ref_kind, ref_id),
            ).fetchall()
            return [str(r["file_id"]) for r in rows]
        finally:
            conn.close()

    # ---- 提取记录 ----------------------------------------------------------------

    def upsert_extraction(
        self,
        *,
        file_id: str,
        owner_id: int,
        extractor: str,
        extractor_version: str,
        input_hash: str,
        state: str,
        derived_file_id: str | None = None,
        quality_summary: str = "{}",
        error: str | None = None,
    ) -> str:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM file_extractions WHERE file_id=? AND extractor=? "
                "AND extractor_version=? AND input_hash=?",
                (file_id, extractor, extractor_version, input_hash),
            ).fetchone()
            if row is not None:
                extraction_id = str(row["id"])
                conn.execute(
                    "UPDATE file_extractions SET state=?, derived_file_id=?, quality_summary=?, "
                    "error=?, updated_at=? WHERE id=?",
                    (state, derived_file_id, quality_summary, error, now, extraction_id),
                )
                return extraction_id
            extraction_id = new_extraction_id()
            conn.execute(
                "INSERT INTO file_extractions(id, file_id, owner_id, extractor, extractor_version, "
                "input_hash, state, derived_file_id, quality_summary, error, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    extraction_id, file_id, owner_id, extractor, extractor_version, input_hash,
                    state, derived_file_id, quality_summary, error, now, now,
                ),
            )
            return extraction_id

    def get_extraction(self, extraction_id: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM file_extractions WHERE id=?", (extraction_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def latest_extraction(self, file_id: str, extractor: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM file_extractions WHERE file_id=? AND extractor=? "
                "ORDER BY created_at DESC LIMIT 1",
                (file_id, extractor),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_extractions(self, file_id: str) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM file_extractions WHERE file_id=? ORDER BY created_at", (file_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 旧表桥接（只读检查，不改旧模块业务规则） -----------------------------------

    def attachment_for_stored_file(self, file_id: str) -> Mapping[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM attachments WHERE stored_file_id=? LIMIT 1", (file_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
