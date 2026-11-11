"""逐项验收账本（工作包四）：轮次写入、检查项评审决定与返工联动。

为什么现有 reports 不够（执行方案 §7 前置要求）：reports 是任务级文本摘要，
无检查项粒度状态、无轮次不可改写语义、无逐项评审决定与打回返工的幂等关联；
验收证据需绑定 task/attempt/轮次/版本并可追溯历史轮次，故独立两张表。

规则（对应方案验收要求）：
- 轮次单调递增、不可改写：同 (task, round_no) 重复提交拒绝；返工后提交新一轮，旧轮保留。
- 检查项决定幂等：同项重复同决定不二次入队；打回进入原任务（append_input +
  succeeded/awaiting_review CAS 回队），跨用户拒绝由 service 层 owner 校验。
- 证据 requiredEvidence 覆盖门：required 缺失该 mediums 时 pass 降级为 blocked
  （缺规定证据标记待验证，Acceptance skill 同一契约）。
"""
from __future__ import annotations

import json
from typing import Any

from backend.modules.superagent.contracts import (
    TASK_AWAITING_REVIEW,
    TASK_SUCCEEDED,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import ConflictError, InvalidInputError, NotFoundError
from backend.shared.identifiers import new_acceptance_round_id

CHECK_STATUSES = frozenset({"pass", "fail", "blocked", "skipped"})
VERDICTS = frozenset({"pass", "fail", "partial"})
_DECISIONS = frozenset({"accepted", "rejected"})


def apply_coverage_gate(check: dict[str, Any]) -> dict[str, Any]:
    """required 证据缺失时 pass→blocked（纯函数，返回规范化后的检查项）。"""
    raw_required = check.get("required_evidence") or []
    if isinstance(raw_required, str):  # JSON 存储读回后的形态
        raw_required = json.loads(raw_required or "[]")
    required = {str(x) for x in raw_required}
    raw_evidence = check.get("evidence") or []
    if isinstance(raw_evidence, str):
        raw_evidence = json.loads(raw_evidence or "[]")
    have = {str(e.get("type") or "") for e in raw_evidence}
    status = str(check.get("status") or "")
    if status == "pass" and required - have:
        status = "blocked"
    return {
        "item_id": str(check["item_id"]),
        "title": str(check.get("title") or "")[:200],
        "category": str(check.get("category") or "")[:80],
        "status": status,
        "required_evidence": json.dumps(sorted(required), ensure_ascii=False),
        "observation": str(check.get("observation") or "")[:2000],
        "evidence_json": json.dumps(raw_evidence, ensure_ascii=False)[:60000],
    }


def summarize(checks: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    counts = {"total": len(checks)}
    for s in ("pass", "fail", "blocked", "skipped"):
        counts[s] = sum(1 for c in checks if c["status"] == s)
    if counts["fail"]:
        verdict = "fail"
    elif counts["pass"] == counts["total"] and counts["total"] > 0:
        verdict = "pass"
    else:
        verdict = "partial"
    return verdict, counts


class AcceptanceRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_round(
        self, *, task_id: str, attempt_id: str, requirement: str,
        provenance: dict[str, Any], checks: list[dict[str, Any]], created_by: int,
    ) -> tuple[str, int, str]:
        """写入新一轮；返回 (round_id, round_no, verdict)。同轮次重复提交拒绝。"""
        normalized = [apply_coverage_gate(c) for c in checks]
        if not normalized:
            raise InvalidInputError("验收轮至少需要一个检查项")
        bad = [c for c in normalized if c["status"] not in CHECK_STATUSES]
        if bad:
            raise InvalidInputError(f"检查项状态非法: {sorted({c['status'] for c in bad})}")
        verdict, counts = summarize(normalized)
        now = utc_now_iso()
        round_id = new_acceptance_round_id()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT MAX(round_no) AS m FROM acceptance_rounds WHERE task_id=?", (task_id,),
            ).fetchone()
            round_no = int(row["m"] or 0) + 1
            conn.execute(
                "INSERT INTO acceptance_rounds(id, task_id, attempt_id, round_no, requirement,"
                " verdict, summary_json, provenance_json, created_by, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (round_id, task_id, attempt_id, round_no, requirement[:500], verdict,
                 json.dumps(counts, ensure_ascii=False),
                 json.dumps(provenance, ensure_ascii=False)[:4000], created_by, now),
            )
            for c in normalized:
                conn.execute(
                    "INSERT INTO acceptance_checks(round_id, item_id, title, category, status,"
                    " required_evidence, observation, evidence_json)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (round_id, c["item_id"], c["title"], c["category"], c["status"],
                     c["required_evidence"], c["observation"], c["evidence_json"]),
                )
        return round_id, round_no, verdict

    def list_rounds(self, task_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rounds = [dict(r) for r in conn.execute(
                "SELECT * FROM acceptance_rounds WHERE task_id=? ORDER BY round_no DESC LIMIT ?",
                (task_id, limit),
            ).fetchall()]
            for r in rounds:
                r["checks"] = [
                    dict(c) for c in conn.execute(
                        "SELECT * FROM acceptance_checks WHERE round_id=? ORDER BY id", (r["id"],),
                    ).fetchall()
                ]
            return rounds
        finally:
            conn.close()

    def get_check(self, check_id: int) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT c.*, r.task_id, r.round_no FROM acceptance_checks c"
                " JOIN acceptance_rounds r ON r.id=c.round_id WHERE c.id=?", (check_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def set_decision(
        self, *, check_id: int, decision: str, note: str, actor_id: int,
    ) -> tuple[dict[str, Any], bool]:
        """设置评审决定；返回 (check 行, 是否首次打回)。

        幂等：同项同决定重复提交不改状态、不算首次；改判(accepted↔rejected)允许，
        但“首次 rejected”才返回 True（由 service 层联动返工，避免重复入队）。
        """
        if decision not in _DECISIONS:
            raise InvalidInputError(f"非法评审决定: {decision}")
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT c.*, r.task_id FROM acceptance_checks c"
                " JOIN acceptance_rounds r ON r.id=c.round_id WHERE c.id=?",
                (check_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("验收检查项不存在")
            was_rejected = str(row["decision"] or "") == "rejected"
            conn.execute(
                "UPDATE acceptance_checks SET decision=?, decided_by=?, decided_at=?,"
                " decision_note=? WHERE id=?",
                (decision, actor_id, now, note[:2000], check_id),
            )
            out = dict(row)
            out["decision"] = decision
            out["task_id"] = str(row["task_id"])
        return out, (decision == "rejected" and not was_rejected)

    def requeue_after_reject(self, task_id: str) -> bool:
        """打回返工：succeeded/awaiting_review 回 queued（与自动修复同白名单同 CAS）。"""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE superagent_tasks SET status=?, phase='', version=version+1,"
                " updated_at=?, error='', result_summary='', run_id='', finished_at=''"
                " WHERE id=? AND status IN (?,?)",
                ("queued", utc_now_iso(), task_id, TASK_SUCCEEDED, TASK_AWAITING_REVIEW),
            )
            return cur.rowcount == 1
