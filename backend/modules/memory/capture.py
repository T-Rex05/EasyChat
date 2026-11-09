"""显式记忆捕获：LLM 候选提取 + 无模型时的确定性降级。

模型只提取用户明确表达的事实/偏好；用户原文是事实来源，助手回复仅用于
消解指代。候选仍经过 `candidate_from_payload` 校验，并强制
source_type=user_confirmed。模型失败/非法 JSON/证据不落地时丢弃，不猜。
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from backend.modules.memory.contracts import MemoryCandidate, SourceRef
from backend.modules.memory.extractor import (
    ExtractionError,
    candidate_from_payload,
)

TRIGGER_RE = re.compile(r"^\s*(?:请|帮我|麻烦)?(?:记住|记一下|别忘(?:了)?)")
# 更宽的产品触发词只用于决定是否入队；LLM 仍会判断是否真的明确。
_NATURAL_TRIGGER_RE = re.compile(
    r"(?:^|[，。！？；、\s])(?:我?以后都|我喜欢|我讨厌|我习惯|我对[^。！？；\n]{1,40}?过敏)"
)
_PREFIX_RE = re.compile(
    r"^\s*(?:请|帮我|麻烦)?(?:记住|记一下|别忘(?:了)?)\s*[：:,，、\-—]?\s*",
    re.IGNORECASE,
)
_PREFERENCE_HINTS = ("喜欢", "偏好", "不喜欢", "爱喝", "爱吃", "习惯")
MAX_CAPTURE_CHARS = 200
MAX_MODEL_CONTENT_CHARS = 200
MAX_EVIDENCE_CHARS = 200


def should_capture(text: str) -> bool:
    """确定性降级只支持句首的旧触发词。"""
    return bool(TRIGGER_RE.search(text or ""))


def should_extract(text: str) -> bool:
    """是否需要尝试提取：覆盖设计列出的显式表达，交给 LLM 判断。"""
    value = text or ""
    return bool(TRIGGER_RE.search(value) or _NATURAL_TRIGGER_RE.search(value))


def extract_content(text: str) -> str:
    content = _PREFIX_RE.sub("", (text or "").strip(), count=1).strip()
    content = " ".join(content.split())
    return content[:MAX_CAPTURE_CHARS]


def candidate_from_user_message(*, run_id: str, text: str) -> MemoryCandidate | None:
    if not should_capture(text):
        return None
    content = extract_content(text)
    if len(content) < 2:
        return None
    kind = "preference" if any(hint in content for hint in _PREFERENCE_HINTS) else "fact"
    return MemoryCandidate(
        kind=kind,
        content=content,
        source_refs=(SourceRef(kind="message", ref=run_id, quote=text.strip()[:200]),),
        scope="user",
        confidence=1.0,
        source_type="user_confirmed",
        tags=("explicit",),
    )


def candidate_from_model_payload(
    payload: Mapping[str, object], *, run_id: str, user_text: str
) -> MemoryCandidate | None:
    """把模型 JSON 收敛成受控候选；`skip` 表示没有可写的明确事实。

    `evidence` 必须逐字来自用户消息（允许空白差异），助手回复不能成为来源。
    """
    if not isinstance(payload, Mapping):
        raise ExtractionError("模型输出不是 JSON 对象")
    if payload.get("skip") is True:
        return None

    kind = str(payload.get("kind") or "").strip()
    content = str(payload.get("content") or "").strip()
    evidence = str(payload.get("evidence") or "").strip()
    if not content or not evidence:
        raise ExtractionError("候选缺少 content/evidence")
    if len(content) > MAX_MODEL_CONTENT_CHARS:
        raise ExtractionError("记忆内容过长")
    if len(evidence) > MAX_EVIDENCE_CHARS:
        raise ExtractionError("证据过长")
    normalized_user = " ".join((user_text or "").split())
    normalized_evidence = " ".join(evidence.split())
    if not normalized_evidence or normalized_evidence not in normalized_user:
        raise ExtractionError("证据不是用户原文子串")

    candidate = candidate_from_payload({
        "kind": kind,
        "content": content,
        "source_refs": [{
            "kind": "message", "ref": run_id, "quote": evidence,
        }],
        "source_type": "user_confirmed",
        "confidence": 1.0,
        "scope": "user",
        "tags": ["explicit", "llm"],
    })
    return candidate
