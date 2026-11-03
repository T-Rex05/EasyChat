"""jobs 认领/lease/幂等/重试行为测试。时间用注入clock固定，不sleep。"""
from __future__ import annotations

from threading import Thread

import pytest

from backend.platform.jobs import (
    JOB_CANCELLED,
    JOB_FAILED,
    JOB_LEASED,
    JOB_PENDING,
    JOB_RETRY_WAIT,
    JOB_SUCCEEDED,
    JobQueue,
)
from backend.platform.sqlite import Database
from backend.shared.errors import StorageUnavailableError


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def queue(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    clock = FakeClock()
    yield JobQueue(db, clock=clock, lease_seconds=300.0), db, clock
    db.close()


def _payload(queue: JobQueue, **kw) -> dict:
    return dict(kw)


def test_enqueue_dedup_same_key_returns_same_job(queue):
    jq, _db, _clock = queue
    jid1 = jq.enqueue(kind="learn", dedup_key="feedback:e1", payload={"a": 1})
    jid2 = jq.enqueue(kind="learn", dedup_key="feedback:e1", payload={"a": 2})
    assert jid1 == jid2
    row = jq.get(jid1)
    assert row["state"] == JOB_PENDING
    assert row["payload"] == '{"a": 1}'  # 保留首入payload


def test_two_claimers_each_get_distinct_jobs_once(queue):
    jq, _db, _clock = queue
    ids = {jq.enqueue(kind="k", dedup_key=f"d{i}", payload={}) for i in range(4)}
    got: list[str] = []

    def claimer(name: str) -> None:
        while len(got) < 4:
            lease = jq.claim(name)
            if lease is None:
                break
            got.append(lease.job_id)

    threads = [Thread(target=claimer, args=(f"w{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    # 4个任务被认领且互不重复（短事务串行认领）
    assert len(got) == 4
    assert len(set(got)) == 4
    assert set(got) == ids


def test_claim_empty_queue_returns_none(queue):
    jq, _db, _clock = queue
    assert jq.claim("w1") is None


def test_complete_transitions_to_succeeded(queue):
    jq, _db, _clock = queue
    jid = jq.enqueue(kind="k", dedup_key="d", payload={})
    lease = jq.claim("w1")
    assert lease is not None and lease.job_id == jid
    assert lease.attempts == 1
    jq.complete(lease)
    assert jq.get(jid)["state"] == JOB_SUCCEEDED
    assert jq.claim("w1") is None  # 已完成不再认领


def test_fail_retryable_waits_until_available(queue):
    jq, _db, clock = queue
    jid = jq.enqueue(kind="k", dedup_key="d", payload={})
    lease = jq.claim("w1")
    jq.fail(lease, error="网络失败", retryable=True, retry_delay_seconds=60)
    row = jq.get(jid)
    assert row["state"] == JOB_RETRY_WAIT
    # 未到期不可认领
    assert jq.claim("w2") is None
    clock.advance(61)
    lease2 = jq.claim("w2")
    assert lease2 is not None and lease2.job_id == jid
    assert lease2.attempts == 2


def test_fail_non_retryable_never_reexecuted(queue):
    jq, _db, clock = queue
    jid = jq.enqueue(kind="k", dedup_key="d", payload={})
    lease = jq.claim("w1")
    jq.fail(lease, error="参数非法", retryable=False)
    assert jq.get(jid)["state"] == JOB_FAILED
    clock.advance(10_000)
    assert jq.claim("w2") is None


def test_attempts_exhausted_marks_failed(queue):
    jq, _db, clock = queue
    jid = jq.enqueue(kind="k", dedup_key="d", payload={}, max_attempts=2)
    lease = jq.claim("w1")
    jq.fail(lease, "e1")  # attempts=1 < 2 → retry
    clock.advance(61)
    lease2 = jq.claim("w2")
    assert lease2.attempts == 2
    jq.fail(lease2, "e2")  # attempts=2 >= max → failed
    assert jq.get(jid)["state"] == JOB_FAILED
    clock.advance(10_000)
    assert jq.claim("w3") is None


def test_lease_expiry_recovered_and_reclaimed(queue):
    """lease过期恢复：同任务可被另一worker重新认领，attempts保留。"""
    jq, _db, clock = queue
    jid = jq.enqueue(kind="k", dedup_key="d", payload={})
    assert jq.claim("w1") is not None
    assert jq.get(jid)["state"] == JOB_LEASED
    # lease 未过期时不可重复认领
    assert jq.claim("w2") is None
    clock.advance(301)
    recovered = jq.recover_expired_leases()
    assert recovered == [jid]
    assert jq.get(jid)["state"] == JOB_PENDING
    lease2 = jq.claim("w2")
    assert lease2 is not None and lease2.job_id == jid
    assert lease2.attempts == 2


def test_complete_with_stale_lease_fails(queue):
    """过期lease不能完成——条件更新失败抛错（进程内串行仍需条件保护）。"""
    jq, _db, clock = queue
    jid = jq.enqueue(kind="k", dedup_key="d", payload={})
    lease = jq.claim("w1")
    clock.advance(301)
    jq.recover_expired_leases()
    lease2 = jq.claim("w2")
    with pytest.raises(StorageUnavailableError):
        jq.complete(lease)  # 旧lease已被回收，条件不匹配
    jq.complete(lease2)
    assert jq.get(jid)["state"] == JOB_SUCCEEDED


def test_cancel_pending_job(queue):
    jq, _db, clock = queue
    jid = jq.enqueue(kind="k", dedup_key="d", payload={})
    assert jq.cancel(jid) is True
    assert jq.get(jid)["state"] == JOB_CANCELLED
    clock.advance(1000)
    assert jq.claim("w1") is None


def test_enqueue_after_success_with_same_key_reuses_history(queue):
    """同 dedup_key 已 succeeded：不创建新任务，也不重跑（语义：同信号只学一次）。"""
    jq, _db, _clock = queue
    jid = jq.enqueue(kind="k", dedup_key="d", payload={})
    lease = jq.claim("w1")
    jq.complete(lease)
    again = jq.enqueue(kind="k", dedup_key="d", payload={})
    assert again == jid
    assert jq.get(jid)["state"] == JOB_SUCCEEDED
