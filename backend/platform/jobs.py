"""小型持久任务队列（架构 §5.3 jobs 状态机、§10）。

只承担持久调度：claim/lease/幂等/重试。业务 handler 与重试条件留在各模块。
状态机：pending → leased → succeeded / retry_wait / failed / cancelled；
重启后仅重新认领 lease 过期且可重试的任务；进程内写串行化只覆盖本进程，
SQLite busy_timeout 与短事务仍必需。
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import StorageUnavailableError
from backend.shared.identifiers import new_job_id

JOB_PENDING = "pending"
JOB_LEASED = "leased"
JOB_SUCCEEDED = "succeeded"
JOB_RETRY_WAIT = "retry_wait"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"

# 可被认领的状态（retry_wait 到期后重新可认领）
CLAIMABLE_STATES = (JOB_PENDING, JOB_RETRY_WAIT)


@dataclass(frozen=True, slots=True)
class Lease:
    job_id: str
    kind: str
    owner_id: int | None
    payload_version: int
    payload: str
    attempts: int
    max_attempts: int
    lease_until: float
    lease_owner: str

    def payload_json(self) -> dict[str, Any]:
        return json.loads(self.payload)


class JobQueue:
    def __init__(
        self,
        db: Database,
        *,
        clock: Callable[[], float] = time.time,
        lease_seconds: float = 300.0,
    ) -> None:
        self.db = db
        self.clock = clock
        self.lease_seconds = lease_seconds

    # ---- 入队 ----------------------------------------------------------------

    def enqueue(
        self,
        *,
        kind: str,
        dedup_key: str,
        payload: Mapping[str, Any],
        owner_id: int | None = None,
        payload_version: int = 1,
        delay_seconds: float = 0.0,
        max_attempts: int = 5,
    ) -> str:
        """幂等入队：同 dedup_key 的任务（任意状态）直接复用，不产生第二条。

        dedup_key 按业务唯一（架构 §5.2）；同一业务信号（如同一反馈事件）
        重复入队永不重跑。新信号必须使用携带新事件 ID 的 dedup_key。
        """
        payload_json = json.dumps(dict(payload), ensure_ascii=False)
        now = self.clock()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM jobs WHERE dedup_key=?", (dedup_key,)).fetchone()
            if row is not None:
                return str(row["id"])
            job_id = new_job_id()
            conn.execute(
                """INSERT INTO jobs(id, kind, dedup_key, owner_id, payload_version, payload,
                    state, available_at, created_at, updated_at, max_attempts)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, kind, dedup_key, owner_id, payload_version, payload_json,
                    JOB_PENDING, now + delay_seconds, utc_now_iso(), utc_now_iso(), max_attempts,
                ),
            )
            return job_id

    def enqueue_tx(
        self,
        conn: Any,
        *,
        kind: str,
        dedup_key: str,
        payload: Mapping[str, Any],
        owner_id: int | None = None,
        payload_version: int = 1,
        delay_seconds: float = 0.0,
        max_attempts: int = 5,
    ) -> str:
        """在调用方事务内幂等入队（run 终态/调度发生与 job 同事务）。"""
        payload_json = json.dumps(dict(payload), ensure_ascii=False)
        row = conn.execute("SELECT id FROM jobs WHERE dedup_key=?", (dedup_key,)).fetchone()
        if row is not None:
            return str(row["id"])
        job_id = new_job_id()
        now = self.clock()
        conn.execute(
            """INSERT INTO jobs(id, kind, dedup_key, owner_id, payload_version, payload,
                state, available_at, created_at, updated_at, max_attempts)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id, kind, dedup_key, owner_id, payload_version, payload_json,
                JOB_PENDING, now + delay_seconds, utc_now_iso(), utc_now_iso(), max_attempts,
            ),
        )
        return job_id

    def count_for_owner(
        self, *, kind: str, owner_id: int, payload_field: str, payload_value: str
    ) -> int:
        """按 kind+owner+JSON 字段计数（用于每日采样上限等业务约束）。"""
        if not payload_field.isalnum():
            raise ValueError("payload_field 必须是简单字段名")
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT count(*) AS c FROM jobs WHERE kind=? AND owner_id=? "
                f"AND json_extract(payload, '$.{payload_field}')=?",
                (kind, owner_id, payload_value),
            ).fetchone()
            return int(row["c"]) if row else 0
        finally:
            conn.close()

    # ---- 认领与完成 ------------------------------------------------------------

    def claim(self, worker_id: str, *, kinds: Sequence[str] | None = None) -> Lease | None:
        """短事务认领一个到期任务。两个认领者不会得到同一任务。"""
        now = self.clock()
        with self.db.transaction() as conn:
            sql = (
                "SELECT * FROM jobs WHERE state IN (?,?) AND available_at<=? "
                "AND (lease_until IS NULL OR lease_until<=?)"
            )
            params: list[Any] = [JOB_PENDING, JOB_RETRY_WAIT, now, now]
            if kinds:
                sql += f" AND kind IN ({','.join('?' * len(kinds))})"
                params.extend(kinds)
            sql += " ORDER BY available_at LIMIT 1"
            row = conn.execute(sql, params).fetchone()
            if row is None:
                return None
            lease_until = now + self.lease_seconds
            cur = conn.execute(
                """UPDATE jobs SET state=?, lease_until=?, lease_owner=?, attempts=attempts+1, updated_at=?
                   WHERE id=? AND state IN (?,?) AND available_at<=?""",
                (JOB_LEASED, lease_until, worker_id, utc_now_iso(), row["id"], JOB_PENDING, JOB_RETRY_WAIT, now),
            )
            if cur.rowcount != 1:
                return None  # 理论上不可达（IMMEDIATE 串行），防御并发实现变更
            return Lease(
                job_id=str(row["id"]),
                kind=str(row["kind"]),
                owner_id=row["owner_id"],
                payload_version=int(row["payload_version"]),
                payload=str(row["payload"]),
                attempts=int(row["attempts"]) + 1,
                max_attempts=int(row["max_attempts"]),
                lease_until=lease_until,
                lease_owner=worker_id,
            )

    def purge_payloads(self, owner_id: int, kind: str) -> int:
        """删除未完成同类任务，并清空终态任务的敏感 payload。

        未完成任务若只清空 payload，worker 会拿到 owner=0 的脏任务；直接删除。
        已领取的 lease 持有旧快照，业务层仍需自行校验 opt-in。
        """
        now = utc_now_iso()
        with self.db.transaction() as conn:
            deleted = conn.execute(
                "DELETE FROM jobs WHERE owner_id=? AND kind=? AND state IN (?,?)",
                (int(owner_id), kind, JOB_PENDING, JOB_RETRY_WAIT),
            ).rowcount
            updated = conn.execute(
                "UPDATE jobs SET payload='{}', updated_at=? WHERE owner_id=? AND kind=? "
                "AND state IN (?,?,?)",
                (now, int(owner_id), kind, JOB_SUCCEEDED, JOB_FAILED, JOB_CANCELLED),
            ).rowcount
            return int(deleted) + int(updated)

    def complete(self, lease: Lease) -> None:
        self._transition(lease, JOB_SUCCEEDED)

    def fail(
        self,
        lease: Lease,
        error: str,
        *,
        retryable: bool = True,
        retry_delay_seconds: float = 60.0,
    ) -> None:
        """失败处理：不可重试或超过 max_attempts → failed；否则 retry_wait 定时重试。"""
        with self.db.transaction() as conn:
            now_iso = utc_now_iso()
            if not retryable or lease.attempts >= lease.max_attempts:
                state = JOB_FAILED
                cur = conn.execute(
                    "UPDATE jobs SET state=?, last_error=?, lease_until=NULL, lease_owner=NULL, updated_at=? "
                    "WHERE id=? AND state=? AND lease_owner=?",
                    (state, error, now_iso, lease.job_id, JOB_LEASED, lease.lease_owner),
                )
            else:
                state = JOB_RETRY_WAIT
                cur = conn.execute(
                    "UPDATE jobs SET state=?, last_error=?, available_at=?, lease_until=NULL, lease_owner=NULL, updated_at=? "
                    "WHERE id=? AND state=? AND lease_owner=?",
                    (state, error, self.clock() + retry_delay_seconds, now_iso, lease.job_id, JOB_LEASED, lease.lease_owner),
                )
            if cur.rowcount != 1:
                raise StorageUnavailableError("任务状态更新失败（lease 已失效）")

    def cancel(self, job_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE jobs SET state=?, updated_at=? WHERE id=? AND state IN (?,?)",
                (JOB_CANCELLED, utc_now_iso(), job_id, JOB_PENDING, JOB_RETRY_WAIT),
            )
            return cur.rowcount == 1

    # ---- 恢复 ------------------------------------------------------------------

    def recover_expired_leases(self) -> list[str]:
        """把 lease 过期的任务退回 pending（attempts 已计入，不重置）。返回任务ID列表。"""
        now = self.clock()
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, attempts, max_attempts FROM jobs "
                "WHERE state=? AND lease_until IS NOT NULL AND lease_until<=?",
                (JOB_LEASED, now),
            ).fetchall()
            if not rows:
                return []
            ids = [str(r["id"]) for r in rows]
            retryable = [
                str(r["id"]) for r in rows
                if int(r["attempts"]) < int(r["max_attempts"])
            ]
            exhausted = [
                str(r["id"]) for r in rows
                if int(r["attempts"]) >= int(r["max_attempts"])
            ]
            if retryable:
                conn.executemany(
                    "UPDATE jobs SET state=?, lease_until=NULL, lease_owner=NULL, "
                    "updated_at=? WHERE id=?",
                    [(JOB_PENDING, utc_now_iso(), jid) for jid in retryable],
                )
            if exhausted:
                conn.executemany(
                    "UPDATE jobs SET state=?, lease_until=NULL, lease_owner=NULL, "
                    "last_error=?, updated_at=? WHERE id=?",
                    [
                        (
                            JOB_FAILED, "lease 过期且重试次数耗尽", utc_now_iso(), jid,
                        )
                        for jid in exhausted
                    ],
                )
            return ids

    # ---- 查询 ------------------------------------------------------------------

    def get(self, job_id: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _transition(self, lease: Lease, to_state: str) -> None:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE jobs SET state=?, lease_until=NULL, lease_owner=NULL, updated_at=? "
                "WHERE id=? AND state=? AND lease_owner=?",
                (to_state, utc_now_iso(), lease.job_id, JOB_LEASED, lease.lease_owner),
            )
            if cur.rowcount != 1:
                raise StorageUnavailableError(f"任务 {lease.job_id} 状态更新失败（lease 已失效）")
