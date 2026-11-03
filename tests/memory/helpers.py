"""memory 测试辅助：加载 20 条脱敏用例并在真实临时 SQLite 上播种。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from backend.modules.memory.api import MemoryService
from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from tests.support.rig import make_rig

CASES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "memory" / "cases.json"


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def make_memory_rig(tmp_path: Path):
    rig = make_rig(tmp_path, seed_access=True)
    service = MemoryService(rig.db, access=rig.access)
    return rig, service


def owner_a(rig):
    return rig.seed_user(role="user", grants=("memory.view", "memory.edit"),
                         username=f"mem_a_{uuid.uuid4().hex[:6]}")


def owner_b(rig):
    return rig.seed_user(role="user", grants=("memory.view", "memory.edit"),
                         username=f"mem_b_{uuid.uuid4().hex[:6]}")


def candidate_from_case(case: dict) -> MemoryCandidate:
    return MemoryCandidate(
        kind=case["kind"],
        content=case["content"],
        source_refs=tuple(
            SourceRef(kind=item.get("kind", "message"), ref=item["ref"])
            for item in case.get("source_refs", [])
        ),
        tags=tuple(case.get("tags", ())),
        event_at=case.get("event_at"),
        confidence=case.get("confidence", 0.8),
        source_type=case.get("source_type", "user_confirmed"),
    )


def seed_case(service: MemoryService, principal, case: dict):
    candidate = candidate_from_case(case)
    if case.get("status") == "archived":
        return service.repo.create_memory(
            owner_id=principal.user_id, candidate=candidate, status="archived",
        )
    return service.remember(principal, candidate)


def seed_all(service: MemoryService, principal, cases: list[dict]) -> dict[str, str]:
    """播种除错误/他人用例之外的全部记忆；返回 case_id → memory_id。"""
    seeded: dict[str, str] = {}
    for case in cases:
        if case.get("expect") == "error" or case.get("owner") == "b":
            continue
        record = seed_case(service, principal, case)
        seeded[case["id"]] = record.memory_id
    return seeded
