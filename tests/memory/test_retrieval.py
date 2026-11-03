"""记忆召回测试（Task 9）：20 条脱敏用例、中文短词/同义、预算、来源与权限。"""
from __future__ import annotations

import pytest

from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.modules.memory.extractor import ExtractionError, candidate_from_payload
from tests.memory.helpers import (
    load_cases,
    make_memory_rig,
    owner_a,
    owner_b,
    seed_all,
    seed_case,
)


@pytest.fixture
def env(tmp_path):
    rig, service = make_memory_rig(tmp_path)
    cases = load_cases()
    user_a = owner_a(rig)
    user_b = owner_b(rig)
    seeded = seed_all(service, user_a, cases)
    # 权限隔离用例：B 的私密记忆
    for case in cases:
        if case.get("owner") == "b":
            seed_case(service, user_b, case)
    yield rig, service, user_a, user_b, cases, seeded
    rig.db.close()


def test_fixture_has_twenty_cases_and_required_categories():
    cases = load_cases()
    assert len(cases) == 20
    categories = {c["category"] for c in cases}
    assert {"worry", "alias", "time", "similar_event", "short_term", "long_term",
            "archived", "permission", "missing_source", "hypothetical"} <= categories
    assert sum(1 for c in cases if c.get("regression")) >= 3


def test_hit_cases_recall_with_sources(env):
    _, service, user_a, _, cases, _ = env
    for case in cases:
        if case.get("expect") != "hit" or case.get("owner") == "b":
            continue
        result = service.recall(user_a, case["query"])
        assert result.items, f"{case['id']} 未召回"
        contents = [item.memory.content for item in result.items]
        assert case["content"] in contents, f"{case['id']} 未命中期望内容: {contents}"
        for item in result.items:
            assert item.memory.source_refs, "召回结果必须带来源"
            assert item.score > 0


def test_similar_events_rank_the_relevant_one_first(env):
    _, service, user_a, _, _, _ = env
    result = service.recall(user_a, "直播准备")
    assert result.items
    assert "第二次直播" in result.items[0].memory.content


def test_no_result_cases_are_explicit(env):
    _, service, user_a, _, cases, _ = env
    for case in cases:
        if case.get("expect") != "no_result":
            continue
        result = service.recall(user_a, case["query"])
        assert result.no_result, f"{case['id']} 不应召回"
        assert "无相关记忆" in result.reason
        assert result.items == ()


def test_archived_requires_old_memory_hint(env):
    _, service, user_a, _, _, _ = env
    assert service.recall(user_a, "杭州").no_result is True
    old = service.recall(user_a, "以前在杭州住过吗")
    assert old.include_archived is True
    assert any("杭州" in item.memory.content for item in old.items)


def test_missing_source_and_hypothetical_rejected():
    with pytest.raises(ExtractionError):
        candidate_from_payload({
            "kind": "fact", "content": "用户可能喜欢爬山", "source_refs": [],
        })
    with pytest.raises(ExtractionError):
        candidate_from_payload({
            "kind": "preference", "content": "如果明年去日本想看樱花",
            "source_refs": [{"kind": "message", "ref": "msg-1"}],
            "source_type": "model_inferred",
        })


def test_chinese_synonym_expansion(env):
    _, service, user_a, _, _, _ = env
    service.remember(user_a, MemoryCandidate(
        kind="event", content="对直播流量很焦虑", confidence=0.9,
        source_refs=(SourceRef(kind="message", ref="msg-syn"),),
    ))
    result = service.recall(user_a, "担心")
    assert any("焦虑" in item.memory.content for item in result.items)


def test_top_k_and_token_budget_bounded(env):
    _, service, user_a, _, _, _ = env
    for index in range(10):
        service.remember(user_a, MemoryCandidate(
            kind="fact", content=f"关于预算的第 {index} 条备注 " + "细节" * 50,
            confidence=0.7,
            source_refs=(SourceRef(kind="message", ref=f"msg-budget-{index}"),),
        ))
    result = service.recall(user_a, "预算", top_k=5)
    assert len(result.items) <= 5
    assert result.estimated_tokens <= 2000
    # 小预算时允许截断，但不能超预算
    small = service.recall(user_a, "预算", top_k=5, token_budget=80)
    assert small.estimated_tokens <= 80
    assert small.items


def test_permission_isolation(env):
    _, service, user_a, user_b, _, _ = env
    result = service.recall(user_a, "私密偏好")
    assert all(item.memory.owner_id == user_a.user_id for item in result.items)
    # B 自己可以召回自己的记忆
    own = service.recall(user_b, "私密偏好")
    assert own.items and all(item.memory.owner_id == user_b.user_id for item in own.items)
