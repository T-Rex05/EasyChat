"""情绪保留期：care 日志随 mood_retention_days 回收，删除立即清空。"""
from __future__ import annotations

from backend.modules.profiles.api import ProfilesService
from tests.support.rig import FakeClock, make_rig

BASE = 1762300800.0  # 2026-11-05 08:00 +08


def _setup(tmp_path):
    clock = FakeClock(BASE)
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user()
    service = ProfilesService(rig.db, access=rig.access, clock=clock)
    service.set_mood_enabled(user, True)
    return rig, service, user


def _care_rows(rig, owner_id: int) -> list[str]:
    conn = rig.db.connect()
    try:
        rows = conn.execute(
            "SELECT id FROM mood_care_log WHERE owner_id=? ORDER BY cared_at",
            (owner_id,),
        ).fetchall()
    finally:
        conn.close()
    return [str(row["id"]) for row in rows]


def test_expired_care_log_is_purged_after_retention_even_if_mood_disabled(tmp_path) -> None:
    rig, service, user = _setup(tmp_path)
    service.update(user, mood_retention_days=1)
    assert service.get(user).mood_retention_days == 1
    service.mark_care_sent(user.user_id, "2025-11-01T00:00:00+00:00", care_key="old")
    service.mark_care_sent(user.user_id, "2025-11-05T00:00:00+00:00", care_key="new")

    # 关闭情绪保留历史（不清空），但保留期仍必须回收过期 care 日志。
    service.set_mood_enabled(user, False)
    service.purge_expired_mood()

    rows = _care_rows(rig, user.user_id)
    assert len(rows) == 1
    assert rows[0].startswith("mcl_")


def test_delete_mood_clears_care_logs_immediately(tmp_path) -> None:
    rig, service, user = _setup(tmp_path)
    service.mark_care_sent(user.user_id, care_key="delete-me")
    assert len(_care_rows(rig, user.user_id)) == 1

    service.delete_mood(user)
    assert _care_rows(rig, user.user_id) == []
