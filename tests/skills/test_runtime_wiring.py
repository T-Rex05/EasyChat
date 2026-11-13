"""WP-C 技能运行接线回归：激活快照进入实际 RuntimeRequest、版本切换、owner 隔离。"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.modules.skills.api import SkillService
from backend.modules.skills.contracts import SOURCE_WEB
from backend.shared.context import Principal
from tests.support.rig import make_rig


def _user(rig, username: str) -> Principal:
    result = rig.access.register(username, "password6")
    principal = rig.access.snapshot_principal(result["user_id"])
    rig.access.repo.set_user_permission(result["user_id"], "skill.create", True)
    rig.access.invalidate_all()
    return principal


def _skills(rig) -> SkillService:
    return SkillService(rig.db, access=rig.access, content_root=rig.tmp_path / "skills")


async def _request_for(rig, principal: Principal):
    session_id = await rig.assistant.create_session(principal, source="wechat")
    receipt = await rig.assistant.submit(RunCommand(
        principal=principal, session_id=session_id, source="wechat",
        client_message_id=f"msg-{uuid.uuid4().hex[:6]}", text="你好",
    ))
    run = rig.assistant.repo.get_run(receipt.run_id)
    return rig.assistant.dispatcher._build_request(run)


@pytest.mark.asyncio
async def test_active_skill_snapshot_enters_request(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    ready.attach_assistant()
    skills = _skills(ready)
    ready.assistant.dispatcher.skills = skills
    alice = _user(ready, f"alice_{uuid.uuid4().hex[:6]}")

    view = skills.propose(alice, "structured-summary", "内容 v1：按固定字段输出摘要。", source=SOURCE_WEB)
    active = skills.activate(alice, view.skill_id, view.version_id, None)
    assert active.active_version_id == view.version_id

    request = await _request_for(ready, alice)
    assert "内容 v1" in request.system_context
    assert ("structured-summary", "1") in request.skill_versions


@pytest.mark.asyncio
async def test_version_switch_affects_next_round_only(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    ready.attach_assistant()
    skills = _skills(ready)
    ready.assistant.dispatcher.skills = skills
    bob = _user(ready, f"bob_{uuid.uuid4().hex[:6]}")

    v1 = skills.propose(bob, "digest", "摘要规程 v1", source=SOURCE_WEB)
    skills.activate(bob, v1.skill_id, v1.version_id, None)
    r1 = await _request_for(ready, bob)
    assert "摘要规程 v1" in r1.system_context and ("digest", "1") in r1.skill_versions

    v2 = skills.propose(bob, "digest", "摘要规程 v2", source=SOURCE_WEB)
    skills.activate(bob, v2.skill_id, v2.version_id, v1.version_id)
    r2 = await _request_for(ready, bob)
    assert "摘要规程 v2" in r2.system_context and "摘要规程 v1" not in r2.system_context
    assert ("digest", "2") in r2.skill_versions


@pytest.mark.asyncio
async def test_cross_owner_skills_not_injected(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    ready.attach_assistant()
    skills = _skills(ready)
    ready.assistant.dispatcher.skills = skills
    owner = _user(ready, f"own_{uuid.uuid4().hex[:6]}")
    other = _user(ready, f"oth_{uuid.uuid4().hex[:6]}")

    v = skills.propose(owner, "private-skill", "机密技能正文", source=SOURCE_WEB)
    skills.activate(owner, v.skill_id, v.version_id, None)

    r_owner = await _request_for(ready, owner)
    assert "机密技能正文" in r_owner.system_context
    r_other = await _request_for(ready, other)
    assert r_other.system_context == "" and r_other.skill_versions == ()


@pytest.mark.asyncio
async def test_archived_skill_excluded(rig) -> None:
    ready = make_rig(rig.tmp_path, seed_access=True, clock=rig.clock)
    ready.attach_assistant()
    skills = _skills(ready)
    ready.assistant.dispatcher.skills = skills
    carol = _user(ready, f"carol_{uuid.uuid4().hex[:6]}")

    v = skills.propose(carol, "old-skill", "旧内容", source=SOURCE_WEB)
    skills.activate(carol, v.skill_id, v.version_id, None)
    skills.archive(carol, v.skill_id)
    request = await _request_for(ready, carol)
    assert "旧内容" not in request.system_context and request.skill_versions == ()
