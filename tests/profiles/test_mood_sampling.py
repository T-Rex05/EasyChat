"""情绪采样：显式 opt-in、确定性词表、同日多采样平均、run 幂等。"""
from __future__ import annotations

from backend.modules.channels.commands import CommandServices, WeChatCommands
from backend.modules.channels.contracts import InboundMessage
from backend.modules.profiles.api import ProfilesService
from backend.platform.jobs import JobQueue
from tests.support.rig import FakeClock, make_rig


def _setup(tmp_path):
    clock = FakeClock(1762300800.0)  # 2026-11-05 08:00 +08
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    user = rig.seed_user()
    service = ProfilesService(rig.db, access=rig.access, clock=clock)
    return rig, service, user


def _msg(text: str) -> InboundMessage:
    return InboundMessage(
        platform="wechat", account_pk="a", external_account_id="bot",
        external_user_id="u", external_chat_id="c", external_event_id="m1", text=text,
    )


def test_opt_out_never_samples(tmp_path) -> None:
    rig, service, user = _setup(tmp_path)
    assert service.sample_run_for_owner(user.user_id, "今天很开心", run_id="run_1") is None
    assert service.list_mood(user, days=7) == []


def test_explicit_negative_and_positive_merge_same_day(tmp_path) -> None:
    _rig, service, user = _setup(tmp_path)
    service.set_mood_enabled(user, True)
    first = service.sample_run_for_owner(
        user.user_id, "今天加班到很晚，好累，有点低落", run_id="run_1"
    )
    assert first is not None and first.score == -1
    assert "疲惫" in first.labels and "加班" in first.labels
    second = service.sample_run_for_owner(
        user.user_id, "不过项目顺利，挺开心的", run_id="run_2"
    )
    assert second is not None and second.score >= 1
    entries = service.list_mood(user, days=7)
    assert len(entries) == 1
    assert entries[0].entry_id == first.entry_id


def test_same_run_is_idempotent(tmp_path) -> None:
    _rig, service, user = _setup(tmp_path)
    service.set_mood_enabled(user, True)
    service.sample_run_for_owner(user.user_id, "今天很开心", run_id="run_1")
    service.sample_run_for_owner(user.user_id, "今天很开心", run_id="run_1")
    entry = service.list_mood(user, days=7)[0]
    conn = service.db.connect()
    try:
        count = conn.execute(
            "SELECT sample_count FROM mood_entries WHERE id=?", (entry.entry_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1


def test_opt_out_purges_stored_mood_text_from_jobs(tmp_path) -> None:
    rig, service, user = _setup(tmp_path)
    queue = JobQueue(rig.db)
    service.queue = queue
    queue.enqueue(
        kind="mood.sample", dedup_key="mood:privacy",
        payload={"text": "我今天很崩溃"}, owner_id=user.user_id,
    )
    lease = queue.claim("test-worker", kinds=("mood.sample",))
    assert lease is not None
    queue.complete(lease)
    service.set_mood_enabled(user, False)
    conn = rig.db.connect()
    try:
        row = conn.execute(
            "SELECT payload FROM jobs WHERE dedup_key='mood:privacy'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row["payload"] == "{}"


def test_same_run_is_not_sampled_twice(tmp_path) -> None:
    _rig, service, user = _setup(tmp_path)
    service.set_mood_enabled(user, True)
    first = service.sample_run_for_owner(user.user_id, "今天很开心", run_id="run_same")
    second = service.sample_run_for_owner(user.user_id, "今天很开心", run_id="run_same")
    assert first is not None and second is not None
    conn = service.db.connect()
    try:
        row = conn.execute(
            "SELECT sample_count FROM mood_entries WHERE id=?", (first.entry_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["sample_count"] == 1


def test_replay_old_run_after_new_run_does_not_double_count(tmp_path) -> None:
    _rig, service, user = _setup(tmp_path)
    service.set_mood_enabled(user, True)
    service.sample_run_for_owner(user.user_id, "今天加班很累", run_id="run_old")
    service.sample_run_for_owner(user.user_id, "今天加班很累", run_id="run_new")
    # 旧任务重放：source_run_id 已被后一次覆盖，不能再次累加平均。
    service.sample_run_for_owner(user.user_id, "今天加班很累", run_id="run_old")
    entry = service.list_mood(user, days=7)[0]
    conn = service.db.connect()
    try:
        row = conn.execute(
            "SELECT sample_count FROM mood_entries WHERE id=?", (entry.entry_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["sample_count"] == 2


def test_daily_sample_cap_is_ten(tmp_path) -> None:
    _rig, service, user = _setup(tmp_path)
    service.set_mood_enabled(user, True)
    for index in range(12):
        service.sample_run_for_owner(user.user_id, "今天很开心", run_id=f"run_{index}")
    entry = service.list_mood(user, days=7)[0]
    conn = service.db.connect()
    try:
        count = conn.execute(
            "SELECT sample_count, score_total FROM mood_entries WHERE id=?",
            (entry.entry_id,),
        ).fetchone()
    finally:
        conn.close()
    assert count["sample_count"] == 10
    assert count["score_total"] == 10


def test_no_emotion_words_does_not_sample(tmp_path) -> None:
    _rig, service, user = _setup(tmp_path)
    service.set_mood_enabled(user, True)
    assert service.sample_run_for_owner(
        user.user_id, "明天九点提醒我交周报", run_id="run_1"
    ) is None


def test_mood_commands_on_view_delete(tmp_path) -> None:
    rig, service, user = _setup(tmp_path)
    commands = WeChatCommands(CommandServices(profiles=service))
    result = __import__("asyncio").run(commands.handle(user, _msg("/情绪 on"), ""))
    assert result is not None and "已开启" in result[0]
    service.sample_run_for_owner(user.user_id, "有点焦虑，压力大", run_id="run_1")
    view = __import__("asyncio").run(commands.handle(user, _msg("/情绪"), ""))
    assert view is not None and "-1 分" in view[0]
    deleted = __import__("asyncio").run(commands.handle(user, _msg("/情绪 删除"), ""))
    assert deleted is not None and "已删除 1 条" in deleted[0]
    conn = service.db.connect()
    try:
        assert conn.execute(
            "SELECT count(*) FROM mood_samples WHERE owner_id=?", (user.user_id,)
        ).fetchone()[0] == 0
    finally:
        conn.close()
