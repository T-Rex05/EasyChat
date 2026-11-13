"""唯一计量入口行为测试（架构 §7 / Task 4 清单）。时间用注入clock固定。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.modules.usage.api import UsageService
from backend.modules.usage.contracts import NormalizedUsage, SYSTEM_OWNER_ID
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import ForbiddenError
from tests.support.rig import FakeClock


@pytest.fixture
def usage(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    clock = FakeClock()

    def fake_now() -> datetime:
        return datetime.fromtimestamp(clock.now, tz=timezone.utc)

    svc = UsageService(db, clock=fake_now, effective_permissions=lambda p: frozenset({"trace.view"}))
    yield svc, db, clock, fake_now
    db.close()


def _u(inp=100, out=50, total=150, complete=True):
    return NormalizedUsage(
        input_tokens=inp, output_tokens=out, total_tokens=total,
        cache_read_tokens=0, cache_write_tokens=0, reasoning_tokens=0,
        usage_complete=complete,
    )


def test_same_callback_twice_counts_once(usage):
    svc, db, clock, now = usage
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    call_id = svc.begin_call(owner_id=7, source="chat", provider="openai", model="gpt")
    assert svc.complete_call(call_id, _u()) is True
    assert svc.complete_call(call_id, _u()) is False  # 重复回调沿用call_id，不产生新计量

    result = svc.ranking(admin, days=7)
    entry = next(r for r in result["ranking"] if r["user_id"] == 7)
    assert entry["total_tokens"] == 150
    assert entry["api_calls"] == 1


def test_late_usage_delta_applied_once(usage):
    """NULL补全：先以未知usage完成（0 tokens），晚到usage补全一次正确加量。"""
    svc, db, clock, now = usage
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    call_id = svc.begin_call(owner_id=7, source="memory", provider="openai", model="gpt")
    svc.complete_call(call_id, NormalizedUsage())  # usage_complete=False，全None

    result = svc.ranking(admin, days=7)
    entry = next(r for r in result["ranking"] if r["user_id"] == 7)
    assert entry["total_tokens"] == 0

    svc.report_usage(call_id, _u(inp=200, out=80, total=280))
    svc.report_usage(call_id, _u(inp=200, out=80, total=280))  # 重复补全差额为0

    refreshed = next(r for r in svc.ranking(admin, days=7)["ranking"] if r["user_id"] == 7)
    assert refreshed["total_tokens"] == 280
    assert refreshed["sources"]["memory"] == 280
    row = svc.repo.get_call(call_id)
    assert row["usage_complete"] == 1
    assert row["total_tokens"] == 280


def test_real_retry_is_two_calls(usage):
    """真实重试是新的call_id：两次计两次。"""
    svc, db, clock, now = usage
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    c1 = svc.begin_call(owner_id=7, source="chat", provider="openai", model="gpt")
    c2 = svc.begin_call(owner_id=7, source="chat", provider="openai", model="gpt")
    assert c1 != c2
    svc.complete_call(c1, _u(total=100))
    svc.complete_call(c2, _u(total=100))
    entry = next(r for r in svc.ranking(admin)["ranking"] if r["user_id"] == 7)
    assert entry["total_tokens"] == 200
    assert entry["api_calls"] == 2


def test_system_task_not_attributed_to_user1(usage):
    """系统任务使用显式system主体（owner_id=0），不猜测user_id=1。"""
    svc, db, clock, now = usage
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    call_id = svc.begin_call(owner_id=SYSTEM_OWNER_ID, source="evolution", provider="openai", model="gpt")
    svc.complete_call(call_id, _u(total=500))
    ranking = svc.ranking(admin)["ranking"]
    by_user = {r["user_id"]: r for r in ranking}
    assert 1 not in by_user  # 不归给user1
    assert by_user[0]["username"] == "系统任务"
    assert by_user[0]["sources"]["evolution"] == 500


def test_shanghai_date_boundary(usage):
    """UTC 17:00 = 上海次日：stat_date 按项目时区切换（上海日期切换正确）。"""
    svc, db, clock, now = usage
    # clock=2026-01-01T17:00Z → 上海 2026-01-02
    clock.now = datetime(2026, 1, 1, 17, 0, tzinfo=timezone.utc).timestamp()
    call_id = svc.begin_call(owner_id=9, source="chat", provider="p", model="m")
    svc.complete_call(call_id, _u(total=10))
    rows = svc.repo.daily_totals(owner_id=9, days=30, today_utc=now())
    assert rows[0]["stat_date"] == "2026-01-02"


def test_cleanup_calls_keeps_daily_stats(usage):
    """删明细不删排行（架构 §7）。"""
    svc, db, clock, now = usage
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    call_id = svc.begin_call(owner_id=8, source="chat", provider="p", model="m")
    svc.complete_call(call_id, _u(total=300))
    # 推进60天后清理30天前明细
    clock.advance(60 * 86400)
    deleted = svc.cleanup_old_calls(admin, days=30)
    assert deleted == 1
    entry = next(r for r in svc.ranking(admin, days=90)["ranking"] if r["user_id"] == 8)
    assert entry["total_tokens"] == 300  # 汇总保留


def test_daily_usage_aggregates_sources_with_input_output(usage):
    """每日卡必须按天聚合多来源，并返回输入/输出/合计，而不是 raw source 行。"""
    svc, db, clock, now = usage
    owner = Principal(user_id=7, role="user", permission_revision=0)
    c1 = svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    svc.complete_call(c1, _u(inp=100, out=20, total=120))
    c2 = svc.begin_call(owner_id=7, source="memory", provider="p", model="m")
    svc.complete_call(c2, _u(inp=30, out=10, total=40))

    rows = svc.my_daily_usage(owner, days=7)
    assert len(rows) == 1
    assert rows[0]["input_tokens"] == 130
    assert rows[0]["output_tokens"] == 30
    assert rows[0]["total_tokens"] == 160
    assert rows[0]["call_count"] == 2


def test_call_list_exposes_legacy_input_output_aliases(usage):
    """前端调用表历史上用 input/output；API 需兼容，不要求前端读 DB 列名。"""
    svc, db, clock, now = usage
    owner = Principal(user_id=7, role="user", permission_revision=0)
    call_id = svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    svc.complete_call(call_id, _u(inp=12, out=8, total=20))

    row = svc.list_calls(owner)[0]
    assert row["input_tokens"] == 12
    assert row["output_tokens"] == 8
    assert svc.get_call(owner, call_id)["input_tokens"] == 12


def test_missing_total_is_derived_from_prompt_and_completion(usage):
    """兼容端点可能不返回 total；不能因此显示 0 token。"""
    svc, db, clock, now = usage
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    call_id = svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    svc.complete_call(call_id, _u(inp=100, out=50, total=None))
    entry = next(r for r in svc.ranking(admin)["ranking"] if r["user_id"] == 7)
    assert entry["total_tokens"] == 150
    assert svc.repo.get_call(call_id)["total_tokens"] == 150


def test_report_usage_before_complete_counts_once(usage):
    """先 report 再 complete 不能双计；report 本身完成这次调用。"""
    svc, db, clock, now = usage
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    call_id = svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    assert svc.report_usage(call_id, _u(inp=100, out=50, total=150)) is True
    assert svc.complete_call(call_id, _u(inp=100, out=50, total=150)) is False
    entry = next(r for r in svc.ranking(admin)["ranking"] if r["user_id"] == 7)
    assert entry["total_tokens"] == 150
    assert entry["call_count"] == 1


def test_late_usage_uses_completion_day_across_midnight(usage):
    """跨午夜补全不能把 tokens 记到创建日，必须跟随首次完成日。"""
    svc, db, clock, now = usage
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    owner = Principal(user_id=7, role="user", permission_revision=0)
    clock.now = datetime(2026, 1, 1, 15, 59, tzinfo=timezone.utc).timestamp()  # 上海 23:59
    call_id = svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    clock.advance(120)  # 上海次日 00:01 完成
    svc.complete_call(call_id, NormalizedUsage())
    svc.report_usage(call_id, _u(inp=100, out=50, total=150))

    rows = svc.my_daily_usage(owner, days=7)
    assert len(rows) == 1
    assert rows[0]["stat_date"] == "2026-01-02"
    assert rows[0]["total_tokens"] == 150
    assert next(r for r in svc.ranking(admin)["ranking"] if r["user_id"] == 7)["total_tokens"] == 150


def test_owner_permission_on_details(usage):
    svc, db, clock, now = usage
    svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    owner = Principal(user_id=7, role="user", permission_revision=0)
    other = Principal(user_id=8, role="user", permission_revision=0)
    # 本人可见
    assert len(svc.list_calls(owner)) == 1
    # 他人不可见（无trace.manage）→ 默认只看自己
    assert svc.list_calls(other) == []
    with pytest.raises(ForbiddenError):
        svc.list_calls(other, owner_id=7)
    with pytest.raises(ForbiddenError):
        svc.get_call(other, svc.repo.list_calls(owner_id=7)[0]["call_id"])


def test_ranking_requires_trace_view(usage):
    svc, db, clock, now = usage
    svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    no_view = Principal(user_id=7, role="user", permission_revision=0)
    svc._effective_permissions = lambda p: frozenset()  # 无trace.view
    with pytest.raises(ForbiddenError):
        svc.ranking(no_view)


def test_user_options_minimal_and_gated(usage):
    """WP-B:全局用量用户选项——trace.manage 才可用、super_admin 可用、
    普通用户 403;返回字段仅 user_id/username/last_call(最小授权)。
    JOIN users 保证只返回真实存在用户(选项与账号表一致)。"""
    svc, db, clock, now = usage
    conn = db.connect()
    for uid in (7, 9):
        conn.execute(
            "INSERT INTO users(id, username, password, email, role, status, created_at, updated_at)"
            " VALUES(?,?,?,?, 'user', 1, '2026-11-13T00:00:00+00:00', '2026-11-13T00:00:00+00:00')",
            (uid, f"u{uid}", "x", f"u{uid}@e.invalid"),
        )
    conn.close()
    svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    svc.begin_call(owner_id=9, source="chat", provider="p", model="m")

    plain = Principal(user_id=7, role="user", permission_revision=0)
    svc._effective_permissions = lambda p: frozenset({"trace.view"})
    with pytest.raises(ForbiddenError):
        svc.user_options(plain)

    admin = Principal(user_id=4, role="user", permission_revision=0)
    svc._effective_permissions = lambda p: (
        frozenset({"trace.view", "trace.manage"}) if p.user_id == 4 else frozenset()
    )
    result = svc.user_options(admin)
    assert result["total"] == 2
    for item in result["users"]:
        assert set(item) == {"user_id", "username", "last_call"}
    ids = {r["user_id"] for r in result["users"]}
    assert ids == {7, 9}

    sup = Principal(user_id=1, role="super_admin", permission_revision=0)
    assert svc.user_options(sup)["total"] == 2
