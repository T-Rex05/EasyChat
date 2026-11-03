"""经验形成（Task 11）：把可追溯反馈整理为经验；Task 12 再生成技能候选。

默认 learner 不调用模型，只做确定性整理；真实模型 learner 由后续任务注入。
"""
from __future__ import annotations

from backend.modules.evolution.contracts import (
    LearningEvidence,
    LearningResult,
    EvolutionTaskView,
)


def default_learner(task: EvolutionTaskView, evidence: LearningEvidence) -> LearningResult:
    outcome = "成功" if evidence.success else ("失败" if evidence.success is False else "未知")
    parts = [f"任务({evidence.task_kind or task.source}) {outcome}"]
    if evidence.user_feedback:
        parts.append(f"用户反馈: {evidence.user_feedback[:300]}")
    if evidence.notes:
        parts.append(f"观察: {evidence.notes[:300]}")
    if evidence.counterexample:
        parts.append(f"反例: {evidence.counterexample[:300]}")
    return LearningResult(
        content="；".join(parts),
        tokens_used=0,
        usage_known=True,
        conditions=evidence.task_kind,
        counterexample=evidence.counterexample,
        confidence=0.7 if evidence.user_confirmed else 0.4,
    )
