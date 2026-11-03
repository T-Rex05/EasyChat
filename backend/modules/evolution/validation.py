"""候选验证：固定顺序 schema/能力 → baseline+candidate 同环境回放 → 回归判定。

回放器由调用方注入（测试用纯函数；生产必须是无副作用替身），本模块不投递、
不调用真实用户会话、不修改验证器。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from backend.modules.skills.api import SkillService
from backend.shared.context import Principal
from backend.shared.errors import AppError

DEFAULT_MIN_IMPROVEMENT = 1


@dataclass(frozen=True, slots=True)
class RegressionCase:
    case_id: str
    input: str
    expect_contains: str
    required: bool = True
    target: bool = False


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case_id: str
    required: bool
    baseline_passed: bool
    candidate_passed: bool
    baseline_output: str = ""
    candidate_output: str = ""


@dataclass(frozen=True, slots=True)
class ValidationReport:
    skill_id: str
    candidate_version_id: str
    baseline_version_id: str
    schema_ok: bool
    required_ok: bool
    no_regression: bool
    improvement: int
    passed: bool
    reason: str
    outcomes: tuple[CaseOutcome, ...] = ()
    metrics: dict[str, int] = field(default_factory=dict)


def _passes(output: str, case: RegressionCase) -> bool:
    return case.expect_contains in (output or "")


def validate_candidate(
    skills: SkillService,
    actor: Principal,
    *,
    skill_id: str,
    candidate_version_id: str,
    cases: list[RegressionCase],
    replayer: Callable[[str, str], str],
    min_improvement: int = DEFAULT_MIN_IMPROVEMENT,
) -> ValidationReport:
    skill = skills.get(actor, skill_id)
    candidate = skills.get_version(actor, candidate_version_id)
    schema_ok = candidate.skill_id == skill_id and bool(candidate.content_hash)
    try:
        candidate_text = skills.read_version_content(actor, candidate_version_id)
    except AppError:
        schema_ok = False
        candidate_text = ""
    baseline_version_id = skill.active_version_id or ""
    baseline_text = ""
    if baseline_version_id:
        try:
            baseline_text = skills.read_version_content(actor, baseline_version_id)
        except AppError:
            baseline_text = ""  # 基线不可读时不能证明无回归，按未通过处理

    outcomes: list[CaseOutcome] = []
    for case in cases:
        candidate_out = replayer(candidate_text, case.input) if schema_ok else ""
        baseline_out = replayer(baseline_text, case.input) if baseline_text else ""
        outcomes.append(CaseOutcome(
            case_id=case.case_id,
            required=case.required,
            baseline_passed=_passes(baseline_out, case),
            candidate_passed=_passes(candidate_out, case),
            baseline_output=baseline_out[:500],
            candidate_output=candidate_out[:500],
        ))

    required_ok = all(o.candidate_passed for o, c in zip(outcomes, cases) if c.required)
    regressions = [o for o, c in zip(outcomes, cases) if not c.required and o.baseline_passed and not o.candidate_passed]
    no_regression = not regressions and bool(baseline_version_id)
    baseline_passes = sum(1 for o in outcomes if o.baseline_passed)
    candidate_passes = sum(1 for o in outcomes if o.candidate_passed)
    improvement = candidate_passes - baseline_passes
    target_fixed = any(
        c.target and not o.baseline_passed and o.candidate_passed
        for o, c in zip(outcomes, cases)
    )
    passed = schema_ok and required_ok and no_regression and (improvement >= min_improvement or target_fixed)
    reason = ""
    if not schema_ok:
        reason = "schema/版本归属或内容不可读"
    elif not required_ok:
        reason = "必需用例未全部通过"
    elif not baseline_version_id:
        reason = "无基线版本，无法证明无回归"
    elif not no_regression:
        reason = "存在确定性回归"
    elif not (improvement >= min_improvement or target_fixed):
        reason = "没有预先定义的目标改善"
    return ValidationReport(
        skill_id=skill_id,
        candidate_version_id=candidate_version_id,
        baseline_version_id=baseline_version_id,
        schema_ok=schema_ok,
        required_ok=required_ok,
        no_regression=no_regression,
        improvement=improvement,
        passed=passed,
        reason=reason,
        outcomes=tuple(outcomes),
        metrics={"baseline_passes": baseline_passes, "candidate_passes": candidate_passes},
    )
