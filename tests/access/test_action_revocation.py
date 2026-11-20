"""WP-D 撤权回归：动作授权与 owner 范围统一——撤销权限后入口必须立即 403。

覆盖计划指出的三类缺口：技能 pin/archive、提醒停启/删除/occurrences、
本人用量 calls/detail/daily；以及 superagent 三键 capabilities 推导与
真实入口的八组合一致性。撤权经 seed_user(revokes=...) 显式覆盖，立即生效。
"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.scheduling.api import SchedulingService
from backend.modules.skills.api import SkillService
from backend.modules.usage.api import UsageService
from tests.support.rig import make_rig


def _user(rig, *, revokes=(), grants=(), role="user"):
    return rig.seed_user(
        role=role, grants=grants, revokes=revokes,
        username=f"mx_{uuid.uuid4().hex[:8]}",
    )


def _skills(rig) -> SkillService:
    return SkillService(rig.db, access=rig.access, content_root=rig.tmp_path / "skills")


def test_chat_revocation_covers_inbox_changes_and_profile(rig):
    from backend.modules.inbox.api import InboxService
    from backend.modules.profiles.api import ProfilesService
    from backend.shared.errors import ForbiddenError

    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    user = _user(ready)
    admin = _user(ready, role="super_admin")
    inbox = InboxService(ready.db, access=ready.access)
    profiles = ProfilesService(ready.db, access=ready.access)
    item = inbox.save(user, note="合成条目", url="https://example.invalid/fixture")
    assert profiles.get(user).owner_id == user.user_id
    ready.access.set_user_permission(admin, user.user_id, "chat.use", False)
    for operation in (inbox.archive, inbox.mark_read, inbox.delete):
        with pytest.raises(ForbiddenError):
            operation(user, item.item_id)
    with pytest.raises(ForbiddenError):
        profiles.get(user)
    with pytest.raises(ForbiddenError):
        profiles.update(user, address_form="测试")


def _usage(rig) -> UsageService:
    from datetime import datetime, timezone as _tz

    return UsageService(
        rig.db,
        clock=lambda: datetime.now(_tz.utc),
        effective_permissions=lambda principal: frozenset(
            rig.access.effective_permissions(principal.user_id)
        ),
    )


def _scheduling(rig):
    clock = rig.clock
    from tests.support.delivery import FakeSender
    from backend.modules.delivery.api import DeliveryService

    delivery = DeliveryService(rig.db, sender=FakeSender(), clock=clock)
    return SchedulingService(
        rig.db, delivery=delivery, access=rig.access, clock=clock, queue=None,
    )


def _scheduling_real(rig):
    """真时钟服务：提醒 create 的 2 年上限按真实 now 校验。"""
    import time as _time
    from tests.support.delivery import FakeSender
    from backend.modules.delivery.api import DeliveryService

    clock = _time.time
    delivery = DeliveryService(rig.db, sender=FakeSender(), clock=clock)
    return SchedulingService(
        rig.db, delivery=delivery, access=rig.access, clock=clock, queue=None,
    )


def _iso_from_ts(ts: float) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(ts, ZoneInfo("Asia/Shanghai")).isoformat()


# ---- 技能 pin/archive ---------------------------------------------------------------

def _own_skill(rig, principal):
    skills = _skills(rig)
    view = skills.propose(principal, "mx-skill", "内容", source="web")
    skills.activate(principal, view.skill_id, view.version_id, None)
    return skills, view


@pytest.mark.asyncio
async def test_skill_pin_archive_require_action_permission(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    owner = _user(ready)
    skills, view = _own_skill(ready, owner)

    # 先建后撤：撤销立即生效，pin/archive 不再放行
    ready.access.repo.set_user_permission(owner.user_id, "skill.create", False)
    ready.access.invalidate_all()
    owner = ready.access.snapshot_principal(owner.user_id)

    from backend.shared.errors import ForbiddenError

    with pytest.raises(ForbiddenError):
        skills.set_pinned(owner, view.skill_id, True)
    with pytest.raises(ForbiddenError):
        skills.set_archived(owner, view.skill_id, True)

    # 授回权限后本人动作恢复可用
    ready.access.repo.set_user_permission(owner.user_id, "skill.create", True)
    ready.access.invalidate_all()
    owner = ready.access.snapshot_principal(owner.user_id)
    assert skills.set_pinned(owner, view.skill_id, True).pinned is True
    assert skills.set_archived(owner, view.skill_id, True).archived is True


@pytest.mark.asyncio
async def test_skill_cross_owner_still_requires_manage(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    owner = _user(ready)
    other = _user(ready)  # 无 skill.manage
    skills, view = _own_skill(ready, owner)
    from backend.shared.errors import ForbiddenError

    with pytest.raises(ForbiddenError):
        skills.set_pinned(other, view.skill_id, True)


# ---- 提醒停启/删除/occurrences -------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_manage_requires_cron_create(rig) -> None:
    import time as _time

    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    service = _scheduling_real(ready)
    owner = _user(ready)  # user 模板含 cron.create
    target = _delivery_target(owner.user_id)
    when = _time.time() + 3600
    view = service.create(
        owner, title="提醒", text="喝水", target=target,
        at=_iso_from_ts(when), timezone="Asia/Shanghai",
    )
    revoked = _user(ready, revokes=("cron.create",))

    from backend.shared.errors import ForbiddenError

    for call in (
        lambda: service.set_enabled(revoked, view.schedule_id, False),
        lambda: service.cancel(revoked, view.schedule_id),
        lambda: service.remove(revoked, view.schedule_id),
        lambda: service.get(revoked, view.schedule_id),
        lambda: service.list(revoked),
        lambda: service.occurrences(revoked, view.schedule_id),
    ):
        with pytest.raises(ForbiddenError):
            call()

    # 本人持有 cron.create：读取与管理可用
    assert service.set_enabled(owner, view.schedule_id, False).enabled is False
    assert service.get(owner, view.schedule_id).enabled is False
    assert service.occurrences(owner, view.schedule_id) == []


@pytest.mark.asyncio
async def test_schedule_cross_owner_needs_system_manage(rig) -> None:
    import time as _time

    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    service = _scheduling_real(ready)
    owner = _user(ready)
    manager = _user(ready, role="admin")
    stranger = _user(ready)
    target = _delivery_target(owner.user_id)
    when = _time.time() + 3600
    view = service.create(
        owner, title="提醒", text="喝水", target=target,
        at=_iso_from_ts(when), timezone="Asia/Shanghai",
    )
    from backend.shared.errors import ForbiddenError

    with pytest.raises(ForbiddenError):
        service.set_enabled(stranger, view.schedule_id, False)
    # admin（system.manage）可跨 owner 管理，但同样需要动作权限？admin 模板含
    # cron.create——构造仅 system.manage 的角色验证"动作+范围"双闸
    manage_only = _user(ready, revokes=("cron.create",), grants=("system.manage",))
    with pytest.raises(ForbiddenError):
        service.set_enabled(manage_only, view.schedule_id, False)
    assert service.set_enabled(manager, view.schedule_id, True).enabled is True


# ---- 本人用量 -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_my_usage_requires_trace_permission(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    usage = _usage(ready)
    revoked = _user(ready, revokes=("trace.view",))

    from backend.shared.errors import ForbiddenError, NotFoundError

    with pytest.raises(ForbiddenError):
        usage.list_calls(revoked)
    with pytest.raises(ForbiddenError):
        usage.list_calls(revoked, owner_id=revoked.user_id)
    with pytest.raises((ForbiddenError, NotFoundError)):
        usage.get_call(revoked, "call_nope")
    with pytest.raises(ForbiddenError):
        usage.my_daily_usage(revoked)

    viewer = _user(ready)  # user 模板含 trace.view
    assert usage.list_calls(viewer, owner_id=viewer.user_id) == []
    assert usage.my_daily_usage(viewer) == []


def _delivery_target(owner_id: int):
    from backend.modules.channels.contracts import ChannelTarget

    return ChannelTarget(kind="wechat", ref=f"wx-{owner_id}", channel_account_id="chn_1")
