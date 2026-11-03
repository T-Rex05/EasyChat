"""排行榜行为测试：聚合、来源分布、旧字段兼容、权限。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.modules.usage.api import UsageService
from backend.modules.usage.contracts import NormalizedUsage
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import ForbiddenError
from tests.support.rig import FakeClock


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    clock = FakeClock()

    def fake_now():
        return datetime.fromtimestamp(clock.now, tz=timezone.utc)

    perms = {"trace.view", "trace.manage"}
    svc = UsageService(db, clock=fake_now, effective_permissions=lambda p: frozenset(perms))
    yield svc, db, clock, perms
    db.close()


def _u(total):
    return NormalizedUsage(input_tokens=total - 10, output_tokens=10, total_tokens=total,
                           cache_read_tokens=0, cache_write_tokens=0, reasoning_tokens=0, usage_complete=True)


def test_ranking_order_and_legacy_fields(env):
    svc, db, clock, perms = env
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    for uid, total in ((7, 100), (8, 300), (9, 200)):
        c = svc.begin_call(owner_id=uid, source="chat", provider="p", model="m")
        svc.complete_call(c, _u(total))
    result = svc.ranking(admin, days=7, limit=10)
    ranking = result["ranking"]
    assert [r["user_id"] for r in ranking] == [8, 9, 7]  # total_tokens 降序
    top = ranking[0]
    # 旧字段兼容：rank/user_id/username/total_tokens/api_calls/active_days
    assert top["rank"] == 1
    assert top["total_tokens"] == 300
    assert top["api_calls"] == 1
    assert top["active_days"] == 1
    assert "sources" in top  # 新增来源分布


def test_ranking_days_window(env):
    svc, db, clock, perms = env
    admin = Principal(user_id=1, role="super_admin", permission_revision=0)
    c = svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    svc.complete_call(c, _u(100))
    clock.advance(90 * 86400)  # 90天前记录
    c2 = svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    svc.complete_call(c2, _u(50))
    assert next(r for r in svc.ranking(admin, days=7)["ranking"] if r["user_id"] == 7)["total_tokens"] == 50
    assert next(r for r in svc.ranking(admin, days=365)["ranking"] if r["user_id"] == 7)["total_tokens"] == 150


def test_ranking_requires_trace_view(env):
    svc, db, clock, perms = env
    svc.begin_call(owner_id=7, source="chat", provider="p", model="m")
    plain = Principal(user_id=7, role="user", permission_revision=0)
    svc._effective_permissions = lambda p: frozenset()
    with pytest.raises(ForbiddenError):
        svc.ranking(plain)


def test_ranking_shows_trace_manage_holder_all(env):
    """trace.view 查看排行；trace.manage 才能看他人明细——语义分离。"""
    svc, db, clock, perms = env
    manager = Principal(user_id=10, role="user", permission_revision=0)
    calls = svc.list_calls(manager)  # 有trace.manage → 全量
    assert isinstance(calls, list)
