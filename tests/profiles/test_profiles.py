"""profiles：默认值、人格渲染、安静时段、情绪平均与删除。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.shared.errors import InvalidInputError
from tests.support.rig import make_rig


def _service(rig):
    from backend.modules.profiles.api import ProfilesService

    return ProfilesService(rig.db, access=rig.access, clock=rig.clock)


def test_default_profile_is_warm_and_mood_off(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = rig.seed_user()
    profiles = _service(rig)
    profile = profiles.get(user)
    assert profile.persona_preset == "warm"
    assert profile.max_chars == 120
    assert profile.timezone == "Asia/Shanghai"
    assert profile.mood_opt_in is False


def test_render_wechat_has_length_but_web_does_not(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = rig.seed_user()
    profiles = _service(rig)
    wechat = profiles.render_persona(user.user_id, "wechat")
    web = profiles.render_persona(user.user_id, "web")
    assert "最多 120 字" in wechat
    assert "不要标题、表格、代码块" in wechat
    assert "最多 120 字" not in web
    profiles.update(user, proactivity="high")
    assert "每周" not in profiles.render_persona(user.user_id, "wechat")
    assert "每周" not in profiles.render_persona(user.user_id, "web")


def test_custom_instruction_limit_and_bad_preset(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = rig.seed_user()
    profiles = _service(rig)
    with pytest.raises(InvalidInputError):
        profiles.update(user, custom_instruction="x" * 501)
    with pytest.raises(InvalidInputError):
        profiles.update(user, persona_preset="unknown")
    profile = profiles.update(user, persona_preset="custom", custom_instruction="像老朋友一样")
    assert "像老朋友一样" in profiles.render_persona(profile.owner_id, "web")


def test_quiet_hours_cross_midnight_and_end_epoch(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = rig.seed_user()
    profiles = _service(rig)
    tz = ZoneInfo("Asia/Shanghai")
    # 2026-11-05 23:30 Asia/Shanghai
    rig.clock.now = datetime(2026, 11, 5, 23, 30, tzinfo=tz).timestamp()
    quiet = profiles.quiet_window(user.user_id)
    assert quiet.active
    end = datetime.fromtimestamp(quiet.end_epoch, tz)
    assert end.hour == 7 and end.minute == 30
    assert end.day == 6

    rig.clock.now = datetime(2026, 11, 5, 12, 0, tzinfo=tz).timestamp()
    assert not profiles.quiet_window(user.user_id).active


def test_mood_off_writes_nothing(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = rig.seed_user()
    profiles = _service(rig)
    assert profiles.record_mood_for_owner(
        user.user_id, entry_date="2026-11-05", score=-1, labels=("加班",), evidence=("加班",),
    ) is None
    assert profiles.list_mood(user) == []


def test_same_day_samples_use_arithmetic_average(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = rig.seed_user()
    profiles = _service(rig)
    profiles.enable_mood_for_owner(user.user_id, True)
    for score, label in ((-2, "加班"), (1, "开心"), (1, "平静")):
        profiles.record_mood_for_owner(
            user.user_id, entry_date="2026-11-05", score=score,
            labels=(label,), evidence=(label,),
        )
    entry = profiles.repo.get_mood(user.user_id, "2026-11-05")
    assert entry is not None
    assert entry.score == 0  # (-2 + 1 + 1) / 3 = 0
    assert len(entry.evidence) <= 3


def test_bad_labels_and_long_evidence_rejected(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = rig.seed_user()
    profiles = _service(rig)
    profiles.enable_mood_for_owner(user.user_id, True)
    with pytest.raises(InvalidInputError):
        profiles.record_mood_for_owner(
            user.user_id, entry_date="2026-11-05", score=1, labels=("诊断",), evidence=(),
        )
    with pytest.raises(InvalidInputError):
        profiles.record_mood_for_owner(
            user.user_id, entry_date="2026-11-05", score=1,
            labels=("开心",), evidence=("x" * 61,),
        )


def test_delete_mood_removes_all(rig) -> None:
    rig = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = rig.seed_user()
    profiles = _service(rig)
    profiles.enable_mood_for_owner(user.user_id, True)
    profiles.record_mood_for_owner(
        user.user_id, entry_date="2026-11-05", score=-1, labels=("疲惫",), evidence=("累",),
    )
    assert profiles.delete_mood(user).deleted == 1
    assert profiles.list_mood(user) == []
