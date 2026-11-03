"""记忆召回：有限候选、相关性排序、token 预算与来源。

纯函数实现，便于用固定用例回归；不调用模型、不补充不存在的来源。
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone

from backend.modules.memory.contracts import (
    DEFAULT_TOKEN_BUDGET,
    DEFAULT_TOP_K,
    OLD_MEMORY_HINTS,
    SYNONYMS,
    MemoryRecord,
    RecallItem,
    RecallResult,
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(query: str) -> tuple[str, ...]:
    """中文按 2-gram（单字查询保留单字），ASCII 按词；短词不会因分词失败丢召回。"""
    text = (query or "").strip().lower()
    terms: list[str] = []
    for chunk in _CJK_RE.findall(text):
        if len(chunk) == 1:
            terms.append(chunk)
        else:
            terms.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
    terms.extend(word for word in _WORD_RE.findall(text) if len(word) > 1)
    # 去重但保持顺序
    seen: set[str] = set()
    ordered = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return tuple(ordered)


def expand_terms(query: str) -> tuple[str, ...]:
    terms = list(tokenize(query))
    low = (query or "").lower()
    for key, synonyms in SYNONYMS.items():
        if key in low or any(s in low for s in synonyms):
            terms.append(key)
            terms.extend(synonyms)
    seen: set[str] = set()
    out = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            out.append(term)
    return tuple(out)


def wants_old_memories(query: str) -> bool:
    low = (query or "").lower()
    return any(hint in low for hint in OLD_MEMORY_HINTS)


def estimate_tokens(text: str) -> int:
    """保守估算：中文约 2 字符/token；仅用于预算上限，不精确计量。"""
    return max(1, len(text) // 2 + 4)


def _recency_bonus(recorded_at: str, now: datetime) -> float:
    try:
        moment = datetime.fromisoformat(recorded_at)
    except ValueError:
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - moment).total_seconds() / 86400.0)
    if days <= 7:
        return 1.5
    if days <= 30:
        return 1.0
    return 0.0


def recall(
    memories: list[MemoryRecord],
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    now: datetime | None = None,
    include_archived: bool | None = None,
) -> RecallResult:
    current = now or datetime.now(timezone.utc)
    old_query = wants_old_memories(query)
    if include_archived is None:
        include_archived = old_query
    terms = expand_terms(query)
    if not terms:
        return RecallResult(reason="查询为空，未召回", include_archived=bool(include_archived))

    scored: list[RecallItem] = []
    for memory in memories:
        if memory.status == "deleted":
            continue
        if memory.status == "archived" and not include_archived:
            continue
        content = memory.content.lower()
        matched: list[str] = []
        score = 0.0
        for term in terms:
            hits = content.count(term)
            if hits:
                matched.append(term)
                score += min(hits, 3) * 3.0
            if any(term == tag.lower() or term in tag.lower() for tag in memory.tags):
                score += 2.0
        if score <= 0:
            continue
        score += memory.confidence * 2.0
        if memory.pinned:
            score += 2.0
        score += _recency_bonus(memory.recorded_at, current)
        if memory.status == "archived":
            score -= 1.0
        scored.append(RecallItem(memory=memory, score=round(score, 3), matched_terms=tuple(matched)))

    if not scored:
        return RecallResult(
            candidate_count=len(memories), reason="无相关记忆（不调用模型编造）",
            include_archived=bool(include_archived),
        )

    scored.sort(key=lambda item: (item.score, item.memory.recorded_at), reverse=True)
    selected: list[RecallItem] = []
    used = 0
    truncated = False
    for item in scored[: max(1, top_k)]:
        cost = estimate_tokens(item.memory.content)
        if selected and used + cost > token_budget:
            truncated = True
            break
        if not selected and cost > token_budget:
            # 单条超预算：按预算截断内容，仍保留来源
            max_chars = max(20, (token_budget - 4) * 2)
            shortened = replace(item.memory, content=item.memory.content[:max_chars] + "…")
            item = replace(item, memory=shortened)
            cost = estimate_tokens(shortened.content)
            truncated = True
        selected.append(item)
        used += cost
    reason = "按预算截断" if truncated else ""
    return RecallResult(
        items=tuple(selected), candidate_count=len(memories), estimated_tokens=used,
        reason=reason, include_archived=bool(include_archived),
    )
