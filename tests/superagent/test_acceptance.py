"""工作包四后端回归：验收轮次、覆盖门、打回返工闭环与访问控制。

用真实 SQLite + AccessService（rig），worker 不参与——打回联动的是任务账本
（inputs/requeue/事件），与执行无关；终态用与 worker 相同的 transition CAS 构造。
"""
from __future__ import annotations

import uuid

import pytest

from backend.modules.superagent.api import SuperagentService
from backend.shared.errors import ForbiddenError, InvalidInputError
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig

REPO_URL = "https://github.com/foo/bar.git"


async def _env(rig):
    ready = rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)
    rig.db, rig.access = ready.db, ready.access
    service = SuperagentService(ready.db, access=ready.access)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    admin = ready.seed_user(role="super_admin", username=f"a_{uuid.uuid4().hex[:6]}")
    owner = ready.seed_user(role="user", grants=("superagent.view", "superagent.create"))
    other = ready.seed_user(role="user", grants=("superagent.view", "superagent.create"))
    service.update_settings(admin, enabled=True, repo_url=REPO_URL, base_branch="main",
                            github_token="ghp_t_1234567890")
    return service, admin, owner, other


async def _succeeded_task(service, owner):
    task = service.create_task(owner, title="UI 修复", requirement="把间距调对")
    claimed = service.repo.claim_next_task()
    assert claimed is not None
    _t, attempt = claimed
    ok = service.repo.transition_task(
        task.task_id, from_statuses={"running"}, to_status="succeeded",
        pr_url="https://github.com/foo/bar/pull/1", pr_number=1, pr_state="draft",
    )
    assert ok
    return task, attempt


ROUND1 = {
    "requirement": "任务页间距验收",
    "provenance": {"commit": "deadbeef", "tree": "abc123", "build": "vite-1", "viewport": "1440x900"},
    "checks": [
        {"item_id": "c1", "title": "间距正确", "status": "pass", "required_evidence": ["screenshot"],
         "evidence": [{"path": "assets/c1.png", "type": "screenshot", "description": "1440 宽截图"}]},
        {"item_id": "c2", "title": "缺证据项", "status": "pass", "required_evidence": ["video"],
         "evidence": []},
    ],
}


@pytest.mark.asyncio
async def test_round_coverage_gate_and_verdict(rig) -> None:
    service, admin, owner, _ = await _env(rig)
    task, attempt = await _succeeded_task(service, owner)
    result = service.submit_acceptance_round(owner, task.task_id, attempt_id=attempt.attempt_id,
                                             **ROUND1)
    assert result["round_no"] == 1
    assert result["verdict"] == "partial"  # c2 被覆盖门降为 blocked
    rounds = service.acceptance_for_task(owner, task.task_id)
    checks = {c["item_id"]: c for c in rounds[0]["checks"]}
    assert checks["c2"]["status"] == "blocked"
    assert checks["c1"]["status"] == "pass"
    assert rounds[0]["provenance_json"].count("deadbeef") == 1


@pytest.mark.asyncio
async def test_reject_reworks_original_task_and_keeps_history(rig) -> None:
    service, admin, owner, _ = await _env(rig)
    task, attempt = await _succeeded_task(service, owner)
    r = service.submit_acceptance_round(owner, task.task_id, attempt_id=attempt.attempt_id, **ROUND1)
    rounds = service.acceptance_for_task(owner, task.task_id)
    c1 = [c for c in rounds[0]["checks"] if c["item_id"] == "c1"][0]

    # 打回:首次 rejected → 输入追加 + succeeded CAS 回队
    d = service.decide_acceptance_check(owner, c1["id"], decision="rejected", note="间距仍偏大")
    assert d["first_reject"] is True and d["requeued"] is True
    fresh = service.task(task.task_id)
    assert fresh.status == "queued"
    inputs = service.repo.unconsumed_inputs(task.task_id)
    assert any("验收打回 c1" in i.text for i in inputs)

    # 重复打回幂等:不再二次入队
    d2 = service.decide_acceptance_check(owner, c1["id"], decision="rejected", note="重复点击")
    assert d2["first_reject"] is False and d2["requeued"] is False
    assert len(service.repo.unconsumed_inputs(task.task_id)) == 1

    # 返工后新一轮:round_no=2,旧轮保留
    service.repo.claim_next_task()
    service.repo.transition_task(task.task_id, from_statuses={"running"}, to_status="succeeded")
    r2 = service.submit_acceptance_round(
        owner, task.task_id, requirement="复验",
        checks=[{"item_id": "c1", "title": "间距正确", "status": "pass",
                 "required_evidence": ["screenshot"],
                 "evidence": [{"path": "assets/x.png", "type": "screenshot", "description": "复验截图"}]}],
    )
    assert r2["round_no"] == 2
    all_rounds = service.acceptance_for_task(owner, task.task_id)
    assert [x["round_no"] for x in all_rounds] == [2, 1]  # 历史可追溯


@pytest.mark.asyncio
async def test_accept_access_control(rig) -> None:
    service, admin, owner, other = await _env(rig)
    task, attempt = await _succeeded_task(service, owner)
    service.submit_acceptance_round(owner, task.task_id, attempt_id=attempt.attempt_id, **ROUND1)
    rounds = service.acceptance_for_task(owner, task.task_id)
    c1 = [c for c in rounds[0]["checks"] if c["item_id"] == "c1"][0]

    with pytest.raises(ForbiddenError):
        service.acceptance_for_task(other, task.task_id)  # 跨用户读拒绝
    with pytest.raises(ForbiddenError):
        service.decide_acceptance_check(other, c1["id"], decision="rejected")  # 跨用户决定拒绝

    # accepted 后改判 rejected 允许且触发返工(首次 rejected)
    service.decide_acceptance_check(owner, c1["id"], decision="accepted")
    d = service.decide_acceptance_check(owner, c1["id"], decision="rejected", note="再想想")
    assert d["first_reject"] is True

    # 空 checks 与非法状态拒绝
    with pytest.raises(InvalidInputError):
        service.submit_acceptance_round(owner, task.task_id, requirement="x", checks=[])
    with pytest.raises(InvalidInputError):
        service.submit_acceptance_round(owner, task.task_id, requirement="x", checks=[
            {"item_id": "z", "title": "t", "status": "banana", "evidence": []}])
