"""候选采用/回滚：只切 skills 的 active 指针，记录验证与采用证据。"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from backend.modules.evolution.validation import ValidationReport
from backend.modules.skills.api import SkillService
from backend.modules.skills.contracts import SkillView
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.context import Principal


class AdoptionService:
    def __init__(self, db: Database, skills: SkillService) -> None:
        self.db = db
        self.skills = skills

    # ---- 证据 ------------------------------------------------------------------

    def record_validation(self, *, owner_id: int, task_id: str, report: ValidationReport) -> str:
        validation_id = f"val_{uuid.uuid4().hex}"
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO evolution_validations(id, task_id, owner_id, skill_id, "
                "baseline_version_id, candidate_version_id, report, passed, reason, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    validation_id, task_id or None, owner_id, report.skill_id,
                    report.baseline_version_id, report.candidate_version_id,
                    json.dumps({
                        "passed": report.passed, "reason": report.reason,
                        "schema_ok": report.schema_ok, "required_ok": report.required_ok,
                        "no_regression": report.no_regression,
                        "improvement": report.improvement, "metrics": report.metrics,
                        "outcomes": [asdict(o) for o in report.outcomes],
                    }, ensure_ascii=False),
                    1 if report.passed else 0, report.reason, utc_now_iso(),
                ),
            )
        return validation_id

    def _record_action(
        self, *, validation_id: str, owner_id: int, skill_id: str,
        version_id: str, action: str, reason: str,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO evolution_adoptions(id, validation_id, owner_id, skill_id, version_id, "
                "action, reason, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (f"adp_{uuid.uuid4().hex}", validation_id, owner_id, skill_id, version_id,
                 action, reason[:300], utc_now_iso()),
            )

    # ---- 采用 ------------------------------------------------------------------

    @staticmethod
    def decide(report: ValidationReport) -> bool:
        return report.passed

    def adopt(
        self,
        actor: Principal,
        *,
        report: ValidationReport,
        validation_id: str,
        expected_active_version_id: str | None = None,
        reason: str = "",
    ) -> SkillView | None:
        """验证通过才切换指针；陈旧期望由 skills.activate 抛 Conflict。"""
        skill = self.skills.get(actor, report.skill_id)
        if not self.decide(report):
            self._record_action(
                validation_id=validation_id, owner_id=skill.owner_id,
                skill_id=report.skill_id, version_id=report.candidate_version_id,
                action="keep", reason=report.reason or "validation failed",
            )
            return None
        if skill.pinned:
            # 自动采用不得修改用户 pin 的技能；显式采用由用户走 skills API
            self._record_action(
                validation_id=validation_id, owner_id=skill.owner_id,
                skill_id=report.skill_id, version_id=report.candidate_version_id,
                action="keep", reason="pinned skill is read-only for automated adoption",
            )
            return None
        expected = (
            skill.active_version_id if expected_active_version_id is None
            else expected_active_version_id
        )
        activated = self.skills.activate(
            actor, report.skill_id, report.candidate_version_id, expected,
        )
        self._record_action(
            validation_id=validation_id, owner_id=skill.owner_id,
            skill_id=report.skill_id, version_id=report.candidate_version_id,
            action="adopt", reason=reason or "validation passed",
        )
        return activated

    def rollback(
        self,
        actor: Principal,
        *,
        skill_id: str,
        target_version_id: str,
        validation_id: str = "",
        reason: str = "",
    ) -> SkillView:
        current = self.skills.get(actor, skill_id)
        rolled = self.skills.activate(
            actor, skill_id, target_version_id, current.active_version_id,
        )
        self._record_action(
            validation_id=validation_id or "", owner_id=current.owner_id,
            skill_id=skill_id, version_id=target_version_id,
            action="rollback", reason=reason or "observed failure",
        )
        return rolled
