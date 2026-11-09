"""run 终态 → 情绪采样入队：只 completed、日期用完成时间。"""
from __future__ import annotations

import pytest

from backend.bootstrap import ModuleRegistry, _make_run_finished
from backend.modules.profiles.api import ProfilesService
from backend.platform.jobs import JobQueue
from tests.support.rig import make_rig


def _profile(rig):
    user = rig.seed_user()
    rig.attach_assistant()
    service = ProfilesService(rig.db, access=rig.access, clock=rig.clock)
    service.set_mood_enabled(user, True)
    return user, service


def _insert_user_message(rig, user_id: int, run_id: str, text: str, created_at: str) -> None:
    with rig.db.transaction() as conn:
        conn.execute(
            "INSERT INTO conversations(session_id, owner_id, run_id, role, content, status, "
            "chat_mode, source, seq, created_at, updated_at) "
            "VALUES(?,?,?,?,?,1,'normal','wechat',0,?,?)",
            ("sess_mood_finish", user_id, run_id, "user", text, created_at, created_at),
        )


def _fire(rig, service, queue, run):
    registry = ModuleRegistry(
        settings=rig.settings, db=rig.db, profiles=service, job_queue=queue,
        assistant=rig.assistant,
    )
    callback = _make_run_finished(registry)
    with rig.db.transaction() as conn:
        callback(conn, run)


def _jobs(rig) -> list:
    conn = rig.db.connect()
    try:
        return conn.execute(
            "SELECT kind, payload FROM jobs WHERE kind='mood.sample' ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()


@pytest.mark.parametrize("status", ["failed", "cancelled", "timed_out"])
def test_non_completed_run_does_not_enqueue_mood(rig, status) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user, service = _profile(rig)
    queue = JobQueue(rig.db, clock=rig.clock)
    _insert_user_message(
        rig, user.user_id, "run_bad", "今天很累", "2026-11-04T15:30:00+00:00"
    )
    _fire(rig, service, queue, {
        "id": "run_bad", "owner_id": user.user_id, "source": "wechat",
        "status": status, "created_at": "2026-11-04T15:30:00+00:00",
        "finished_at": "2026-11-04T16:30:00+00:00",
    })
    assert _jobs(rig) == []


def test_mood_date_uses_finished_at_local_date(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user, service = _profile(rig)
    queue = JobQueue(rig.db, clock=rig.clock)
    _insert_user_message(
        rig, user.user_id, "run_midnight", "今天很累", "2026-11-04T15:30:00+00:00"
    )
    _fire(rig, service, queue, {
        "id": "run_midnight", "owner_id": user.user_id, "source": "wechat",
        "status": "completed", "created_at": "2026-11-04T15:30:00+00:00",
        "finished_at": "2026-11-04T16:30:00+00:00",  # 次日 00:30 +08
    })
    jobs = _jobs(rig)
    assert len(jobs) == 1
    assert '"date": "2026-11-05"' in jobs[0]["payload"]


def test_completed_run_with_empty_text_is_not_enqueued(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user, service = _profile(rig)
    queue = JobQueue(rig.db, clock=rig.clock)
    _insert_user_message(
        rig, user.user_id, "run_empty", "   ", "2026-11-04T15:30:00+00:00"
    )
    _fire(rig, service, queue, {
        "id": "run_empty", "owner_id": user.user_id, "source": "wechat",
        "status": "completed", "created_at": "2026-11-04T15:30:00+00:00",
        "finished_at": "2026-11-04T15:31:00+00:00",
    })
    assert _jobs(rig) == []
