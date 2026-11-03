"""delivery 模块数据访问：artifacts / deliveries / delivery_parts。

投递账本只由本模块写；助手完成回调通过同一个 SQLite 事务调用
`enqueue_in_transaction`，避免“run 完成但投递请求丢失”。
"""
from __future__ import annotations

import json
from typing import Any

from backend.modules.delivery.contracts import (
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_RETRY_WAIT,
    DELIVERY_SENDING,
    DELIVERY_SENT,
    DELIVERY_UNCERTAIN,
    PART_FAILED,
    PART_PENDING,
    PART_SENT,
    DeliveryLease,
    DeliveryTarget,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import NotFoundError
from backend.shared.identifiers import new_artifact_id, new_delivery_id, new_part_id


def _lease_from_row(row: Any, attempts: int) -> DeliveryLease:
    d = dict(row)
    return DeliveryLease(
        delivery_id=str(d["id"]),
        owner_id=int(d["owner_id"]),
        run_id=str(d.get("run_id") or ""),
        source=str(d.get("source") or ""),
        target=DeliveryTarget(
            kind=str(d["target_kind"]),
            ref=str(d["target_ref"]),
            channel_account_id=str(d.get("channel_account_id") or ""),
            context_token=str(d.get("context_token") or ""),
        ),
        content_text=str(d.get("content_text") or ""),
        artifact_id=str(d.get("artifact_id") or ""),
        attempts=attempts,
        max_attempts=int(d.get("max_attempts") or 5),
    )


class DeliveryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- 入队 ------------------------------------------------------------------

    def enqueue(
        self,
        *,
        owner_id: int,
        target: DeliveryTarget,
        content_text: str,
        dedup_key: str,
        source: str = "wechat",
        run_id: str = "",
        artifact_id: str = "",
        delay_seconds: float = 0.0,
        now: float = 0.0,
    ) -> str:
        with self.db.transaction() as conn:
            return self.enqueue_in_transaction(
                conn,
                owner_id=owner_id, target=target, content_text=content_text,
                dedup_key=dedup_key, source=source, run_id=run_id,
                artifact_id=artifact_id, delay_seconds=delay_seconds, now=now,
            )

    def enqueue_in_transaction(
        self,
        conn: Any,
        *,
        owner_id: int,
        target: DeliveryTarget,
        content_text: str,
        dedup_key: str,
        source: str = "wechat",
        run_id: str = "",
        artifact_id: str = "",
        delay_seconds: float = 0.0,
        now: float = 0.0,
    ) -> str:
        """在调用方事务中入队；同 dedup_key 返回既有 id，不建第二条。"""
        existing = conn.execute(
            "SELECT id FROM deliveries WHERE dedup_key=?", (dedup_key,)
        ).fetchone()
        if existing is not None:
            return str(existing["id"])
        delivery_id = new_delivery_id()
        now_iso = utc_now_iso()
        conn.execute(
            "INSERT INTO deliveries(id, owner_id, run_id, source, target_kind, target_ref, "
            "channel_account_id, context_token, content_text, artifact_id, dedup_key, status, "
            "attempts, next_attempt_at, error, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?)",
            (
                delivery_id, owner_id, run_id or None, source, target.kind, target.ref,
                target.channel_account_id, target.context_token, content_text, artifact_id or None,
                dedup_key, DELIVERY_PENDING, max(0.0, now) + delay_seconds, "", now_iso, now_iso,
            ),
        )
        return delivery_id

    # ---- 认领与完成 --------------------------------------------------------------

    def claim_due(self, worker_id: str, *, now: float, max_attempts: int = 5) -> DeliveryLease | None:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM deliveries WHERE status IN (?,?) AND next_attempt_at<=? "
                "ORDER BY next_attempt_at, created_at LIMIT 1",
                (DELIVERY_PENDING, DELIVERY_RETRY_WAIT, now),
            ).fetchone()
            if row is None:
                return None
            attempts = int(row["attempts"]) + 1
            cur = conn.execute(
                "UPDATE deliveries SET status=?, attempts=?, updated_at=? "
                "WHERE id=? AND status IN (?,?)",
                (DELIVERY_SENDING, attempts, utc_now_iso(), row["id"],
                 DELIVERY_PENDING, DELIVERY_RETRY_WAIT),
            )
            if cur.rowcount != 1:
                return None
            lease = _lease_from_row(row, attempts)
            return DeliveryLease(
                delivery_id=lease.delivery_id, owner_id=lease.owner_id, run_id=lease.run_id,
                source=lease.source, target=lease.target, content_text=lease.content_text,
                artifact_id=lease.artifact_id, attempts=attempts, max_attempts=max_attempts,
            )

    def finish(
        self, delivery_id: str, *, status: str, error: str = "", sent_at: bool = False
    ) -> bool:
        if status not in (DELIVERY_SENT, DELIVERY_FAILED, DELIVERY_UNCERTAIN):
            raise ValueError(f"非法投递终态: {status}")
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE deliveries SET status=?, error=?, sent_at=?, updated_at=? "
                "WHERE id=? AND status=?",
                (status, error[:500], now if sent_at else None, now, delivery_id, DELIVERY_SENDING),
            )
            return cur.rowcount == 1

    def set_retry(self, delivery_id: str, *, next_attempt_at: float, error: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE deliveries SET status=?, next_attempt_at=?, error=?, updated_at=? "
                "WHERE id=? AND status=?",
                (DELIVERY_RETRY_WAIT, next_attempt_at, error[:500], utc_now_iso(),
                 delivery_id, DELIVERY_SENDING),
            )
            return cur.rowcount == 1

    def recover_inflight(self) -> int:
        """进程重启时仍在 sending 的投递：外部结果未知，进入 uncertain，不盲目重发。"""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE deliveries SET status=?, error=?, updated_at=? WHERE status=?",
                (DELIVERY_UNCERTAIN, "进程重启，发送结果未知", utc_now_iso(), DELIVERY_SENDING),
            )
            return int(cur.rowcount)

    # ---- 分块 ------------------------------------------------------------------

    def ensure_parts(self, delivery_id: str, chunks: list[str]) -> list[dict[str, Any]]:
        with self.db.transaction() as conn:
            for seq, content in enumerate(chunks):
                conn.execute(
                    "INSERT INTO delivery_parts(id, delivery_id, seq, content, status) "
                    "VALUES(?,?,?,?,?) ON CONFLICT(delivery_id, seq) DO NOTHING",
                    (new_part_id(), delivery_id, seq, content, PART_PENDING),
                )
            rows = conn.execute(
                "SELECT * FROM delivery_parts WHERE delivery_id=? ORDER BY seq", (delivery_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_part_sent(self, delivery_id: str, seq: int, external_id: str = "") -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE delivery_parts SET status=?, external_id=?, error='', sent_at=? "
                "WHERE delivery_id=? AND seq=?",
                (PART_SENT, external_id[:200], utc_now_iso(), delivery_id, seq),
            )

    def mark_part_failed(self, delivery_id: str, seq: int, error: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE delivery_parts SET status=?, error=? WHERE delivery_id=? AND seq=?",
                (PART_FAILED, error[:500], delivery_id, seq),
            )

    def parts(self, delivery_id: str) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM delivery_parts WHERE delivery_id=? ORDER BY seq", (delivery_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 查询 ------------------------------------------------------------------

    def get(self, delivery_id: str) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"投递不存在: {delivery_id}")
            return dict(row)
        finally:
            conn.close()

    def list_for_owner(self, owner_id: int, limit: int = 50) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM deliveries WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 产物（Task 14 PDF 复用） ------------------------------------------------

    def create_artifact(
        self,
        *,
        owner_id: int,
        kind: str,
        file_path: str,
        sha256: str,
        file_size: int,
        mime: str,
        run_id: str = "",
        expires_at: str | None = None,
    ) -> str:
        artifact_id = new_artifact_id()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO artifacts(id, owner_id, run_id, kind, file_path, sha256, file_size, "
                "mime, created_at, expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (artifact_id, owner_id, run_id or None, kind, file_path, sha256,
                 int(file_size), mime, utc_now_iso(), expires_at),
            )
        return artifact_id

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"产物不存在: {artifact_id}")
            return dict(row)
        finally:
            conn.close()


def target_to_json(target: DeliveryTarget) -> str:
    return json.dumps(
        {"kind": target.kind, "ref": target.ref,
         "channel_account_id": target.channel_account_id,
         "context_token": target.context_token},
        ensure_ascii=False,
    )
