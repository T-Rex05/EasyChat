"""候选验证测试（Task 12）：固定顺序、回归判定、原版更好不采用、无副作用回放。"""
from __future__ import annotations

import json
from pathlib import Path

from backend.modules.evolution.validation import RegressionCase, validate_candidate
from tests.skills.helpers import make_skill_rig, make_user

CASES = Path(__file__).resolve().parents[1] / "fixtures" / "evolution" / "regression.json"


def _cases() -> list[RegressionCase]:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    return [RegressionCase(**item) for item in data]


def _replayer(content: str, query: str) -> str:
    if query == "deploy the service":
        return "backup then deploy" if "FIX" in content else "deploy directly"
    if query == "check health":
        return "ok"
    if query == "rollback the release":
        return "safe rollback"
    return "plain answer"


def _setup(tmp_path, candidate_content="FIX"):
    rig, skills, root = make_skill_rig(tmp_path)
    user = make_user(rig, grants=("evolution.view",), tag="validator")
    baseline = skills.propose(user, "deploy-skill", "BASE version", source="user")
    skill = skills.activate(user, baseline.skill_id, baseline.version_id, None)
    candidate = skills.propose(user, "deploy-skill", candidate_content, source="user")
    return rig, skills, user, skill, baseline, candidate


def test_candidate_passes_required_and_improves(tmp_path):
    rig, skills, user, skill, baseline, candidate = _setup(tmp_path)
    report = validate_candidate(
        skills, user, skill_id=skill.skill_id,
        candidate_version_id=candidate.version_id,
        cases=_cases(), replayer=_replayer,
    )
    assert report.schema_ok
    assert report.required_ok
    assert report.no_regression
    assert report.improvement == 1
    assert report.passed is True
    assert report.baseline_version_id == baseline.version_id
    rig.db.close()


def test_original_better_is_not_adopted(tmp_path):
    rig, skills, user, skill, _, candidate = _setup(tmp_path, candidate_content="BROKEN")
    report = validate_candidate(
        skills, user, skill_id=skill.skill_id,
        candidate_version_id=candidate.version_id,
        cases=_cases(), replayer=_replayer,
    )
    assert report.passed is False
    assert "必需用例" in report.reason or "改善" in report.reason
    rig.db.close()


def test_no_improvement_not_adopted(tmp_path):
    rig, skills, user, skill, _, _ = _setup(tmp_path)
    # 候选与基线相同内容
    same = skills.propose(user, "deploy-skill", "BASE version", source="user")
    report = validate_candidate(
        skills, user, skill_id=skill.skill_id,
        candidate_version_id=same.version_id, cases=_cases(), replayer=_replayer,
    )
    assert report.passed is False
    assert report.improvement == 0
    rig.db.close()


def test_new_skill_without_baseline_cannot_prove_no_regression(tmp_path):
    rig, skills, user, _, _, _ = _setup(tmp_path)
    new = skills.propose(user, "brand-new", "FIX candidate", source="user")
    report = validate_candidate(
        skills, user, skill_id=new.skill_id,
        candidate_version_id=new.version_id, cases=_cases(), replayer=_replayer,
    )
    assert report.passed is False
    assert report.baseline_version_id == ""
    rig.db.close()


def test_replay_has_no_delivery_side_effects(tmp_path):
    rig, skills, user, skill, _, candidate = _setup(tmp_path)
    validate_candidate(
        skills, user, skill_id=skill.skill_id,
        candidate_version_id=candidate.version_id, cases=_cases(), replayer=_replayer,
    )
    conn = rig.db.connect()
    try:
        assert conn.execute("SELECT count(*) AS c FROM deliveries").fetchone()["c"] == 0
        assert conn.execute("SELECT count(*) AS c FROM runs").fetchone()["c"] == 0
    finally:
        conn.close()
    rig.db.close()
