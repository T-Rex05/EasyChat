"""记忆候选提取：只做结构化校验与保守过滤，不调用模型编造内容。

普通聊天只产生候选；明确“记住”才写入。假设/转述在模型推断来源下不写成用户事实。
"""
from __future__ import annotations

from typing import Any, Mapping

from backend.modules.memory.contracts import (
    SOURCE_MODEL_INFERRED,
    SOURCE_USER_CONFIRMED,
    VALID_KINDS,
    MemoryCandidate,
    SourceRef,
)

MAX_CONTENT_CHARS = 2000
_HYPOTHETICAL_MARKERS = ("如果", "假设", "假如", "要是", "别人说", "据说", "听说", "转述")


class ExtractionError(ValueError):
    """候选不满足写入规则（来源缺失/假设/超长等）。"""


def validate_candidate(candidate: MemoryCandidate) -> None:
    """公开写入也必须过的规则（防止绕过 extractor 直接构造候选）。"""
    if candidate.kind not in VALID_KINDS:
        raise ExtractionError(f"未知记忆类型: {candidate.kind}")
    content = candidate.content.strip()
    if len(content) < 2:
        raise ExtractionError("记忆内容过短")
    if len(content) > MAX_CONTENT_CHARS:
        raise ExtractionError("记忆内容过长")
    if not candidate.source_refs or not any(ref.ref for ref in candidate.source_refs):
        raise ExtractionError("缺少来源，不能补造经历")
    if candidate.source_type not in (SOURCE_USER_CONFIRMED, SOURCE_MODEL_INFERRED):
        raise ExtractionError(f"未知来源类型: {candidate.source_type}")
    if candidate.source_type == SOURCE_MODEL_INFERRED and any(
        marker in content for marker in _HYPOTHETICAL_MARKERS
    ):
        raise ExtractionError("假设/转述内容不能写成用户事实")


def candidate_from_payload(payload: Mapping[str, Any]) -> MemoryCandidate:
    kind = str(payload.get("kind") or "").strip()
    if kind not in VALID_KINDS:
        raise ExtractionError(f"未知记忆类型: {kind}")
    content = str(payload.get("content") or "").strip()
    if len(content) < 2:
        raise ExtractionError("记忆内容过短")
    if len(content) > MAX_CONTENT_CHARS:
        raise ExtractionError("记忆内容过长")

    raw_refs = payload.get("source_refs") or []
    refs: list[SourceRef] = []
    for item in raw_refs if isinstance(raw_refs, list) else []:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("ref") or "").strip()
        if ref:
            refs.append(SourceRef(
                kind=str(item.get("kind") or "message"),
                ref=ref[:500],
                quote=str(item.get("quote") or "")[:300],
            ))
    if not refs:
        raise ExtractionError("缺少来源，不能补造经历")

    source_type = str(payload.get("source_type") or SOURCE_MODEL_INFERRED)
    if source_type not in (SOURCE_USER_CONFIRMED, SOURCE_MODEL_INFERRED):
        raise ExtractionError(f"未知来源类型: {source_type}")
    if source_type == SOURCE_MODEL_INFERRED and any(m in content for m in _HYPOTHETICAL_MARKERS):
        raise ExtractionError("假设/转述内容不能写成用户事实")

    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError) as exc:
        raise ExtractionError("confidence 不是数字") from exc
    confidence = min(1.0, max(0.0, confidence))

    tags = payload.get("tags") or []
    tag_tuple = tuple(str(t).strip()[:60] for t in tags if str(t).strip()) if isinstance(tags, list) else ()
    event_at = payload.get("event_at")
    candidate = MemoryCandidate(
        kind=kind,
        content=content,
        source_refs=tuple(refs),
        scope=str(payload.get("scope") or "user")[:40],
        event_at=str(event_at) if event_at else None,
        confidence=confidence,
        source_type=source_type,
        tags=tag_tuple,
        supersedes=str(payload["supersedes"]) if payload.get("supersedes") else None,
        pinned=bool(payload.get("pinned", False)),
    )
    validate_candidate(candidate)
    return candidate
