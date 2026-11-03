"""候选采用测试（Task 12）：CAS 陈旧指针、pin 保护、回滚、证据记录。"""
from __future__ import annotations

import pytest

from backend.modules.evolution.adoption import AdoptionService
from backend.modules.evolution.validation import RegressionCase, validate_candidate
from backend.shared.errors import ConflictError
from tests.skills.helpers import make_skill_rig, make_user

CASES = [
    RegressionCase("deploy", "deploy the service", "backup", required=True, target=True),
    RegressionCase("health", "check health", "ok", required=True),
]


def _replayer(content: str, query: str) -> str:
    if query == "deploy the service":
        return "backup then deploy" if "FIX" in content else "deploy directly"
    return "ok"


def _setup(tmp_path):
    rig, skills, root = make_skill_rig(tmp_path)
    user = make_user(rig, grants=("evolution.view",), tag="adopter")
    v1 = skills.propose(user, "deploy-skill", "BASE", source="user")
    skill = skills.activate(user, v1.skill_id, v1.version_id, None)
    v2 = skills.propose(user, "deploy-skill", "FIX candidate", source="user")
    report = validate_candidate(
        skills, user, skill_id=skill.skill_id, candidate_version_id=v2.version_id,
        cases=CASES, replayer=_replayer,
    )
    adoption = AdoptionService(rig.db, skills)
    validation_id = adoption.record_validation(owner_id=user.user_id, task_id="evo-1", report=report)
    return rig, skills, user, skill, v1, v2, report, adoption, validation_id


def test_adopt_switches_pointer_and_rollback_restores(tmp_path):
    rig, skills, user, skill, v1, v2, report, adoption, validation_id = _setup(tmp_path)
    assert report.passed is True
    activated = adoption.adopt(user, report=report, validation_id=validation_id)
    assert activated is not None
    assert activated.active_version_id == v2.version_id
    assert skills.read_active_content(user, skill.skill_id) == "FIX candidate"

    rolled = adoption.rollback(
        user, skill_id=skill.skill_id, target_version_id=v1.version_id,
        validation_id=validation_id, reason="observed regression",
    )
    assert rolled.active_version_id == v1.version_id
    assert skills.read_active_content(user, skill.skill_id) == "BASE"

    conn = rig.db.connect()
    try:
        actions = [r["action"] for r in conn.execute(
            "SELECT action FROM evolution_adoptions ORDER BY created_at"
        ).fetchall()]
    finally:
        conn.close()
    assert actions == ["adopt", "rollback"]
    rig.db.close()


def test_failed_report_keeps_original(tmp_path):
    rig, skills, user, skill, v1, v2, report, adoption, validation_id = _setup(tmp_path)
    from backend.modules.evolution.validation import ValidationReport

    failed = ValidationReport(
        skill_id=report.skill_id, candidate_version_id=report.candidate_version_id,
        baseline_version_id=report.baseline_version_id, schema_ok=True,
        required_ok=False, no_regression=False, improvement=0, passed=False,
        reason="必需用例未通过",
    )
    assert adoption.adopt(user, report=failed, validation_id=validation_id) is None
    assert skills.get(user, skill.skill_id).active_version_id == v1.version_id
    rig.db.close()


def test_pinned_skill_is_not_auto_adopted(tmp_path):
    rig, skills, user, skill, v1, v2, report, adoption, validation_id = _setup(tmp_path)
    skills.set_pinned(user, skill.skill_id, True)
    assert adoption.adopt(user, report=report, validation_id=validation_id) is None
    assert skills.get(user, skill.skill_id).active_version_id == v1.version_id
    rig.db.close()


def test_stale_expected_pointer_conflict(tmp_path):
    rig, skills, user, skill, v1, v2, report, adoption, validation_id = _setup(tmp_path)
    # 先把基线切到不含修复的新版本，确保 v3 相对它有目标改善
    v2b = skills.propose(user, "deploy-skill", "BASE v2", source="user")
    skills.activate(user, skill.skill_id, v2b.version_id, v1.version_id)
    v3 = skills.propose(user, "deploy-skill", "FIX candidate v3", source="user")
    report3 = validate_candidate(
        skills, user, skill_id=skill.skill_id, candidate_version_id=v3.version_id,
        cases=CASES, replayer=_replayer,
    )
    assert report3.passed is True
    with pytest.raises(ConflictError):
        adoption.adopt(
            user, report=report3, validation_id=validation_id,
            expected_active_version_id=v1.version_id,
        )
    assert skills.get(user, skill.skill_id).active_version_id == v2b.version_id
    rig.db.close()
