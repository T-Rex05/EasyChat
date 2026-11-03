"""usage_bridge：Hermes 真实请求与统一 call_id 关联（架构 §7）。

Hermes 无 per-request usage 回调，用量累计在 agent 实例属性
（session_*_tokens / session_api_calls）。本桥按 run 前后差值计量：
- run 前快照 + begin_call（provider/model 来自 models 选择）；
- run 后差值 → complete_call（一次 run 一个 call_id；一次 run 内
  agent 多次迭代在 raw_usage.api_calls 中记录）。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.modules.usage.api import UsageService
from backend.modules.usage.contracts import NormalizedUsage

logger = logging.getLogger(__name__)

_COUNTER_ATTRS = (
    "session_input_tokens",
    "session_output_tokens",
    "session_cache_read_tokens",
    "session_cache_write_tokens",
    "session_reasoning_tokens",
    "session_total_tokens",
    "session_api_calls",
)


def snapshot(agent: Any) -> dict[str, int]:
    return {attr: int(getattr(agent, attr, 0) or 0) for attr in _COUNTER_ATTRS}


def diff(pre: dict[str, int], post: dict[str, int]) -> dict[str, int]:
    return {k: max(0, post.get(k, 0) - pre.get(k, 0)) for k in _COUNTER_ATTRS}


def begin_for_run(usage: UsageService, *, owner_id: int, source: str, provider: str, model: str, run_id: str, session_id: str | None) -> str | None:
    if usage is None:
        return None
    try:
        return usage.begin_call(owner_id=owner_id, source=source, provider=provider, model=model,
                                run_id=run_id, session_id=session_id)
    except Exception:  # noqa: BLE001  计量失败不阻塞执行，但必须记录
        logger.exception("begin_call 失败")
        return None


def complete_for_run(
    usage: UsageService,
    call_id: str | None,
    *,
    delta: dict[str, int],
    model: str,
    estimated: bool = False,
) -> bool:
    if usage is None or call_id is None:
        return False
    usage_delta = NormalizedUsage(
        input_tokens=delta.get("session_input_tokens"),
        output_tokens=delta.get("session_output_tokens"),
        cache_read_tokens=delta.get("session_cache_read_tokens"),
        cache_write_tokens=delta.get("session_cache_write_tokens"),
        reasoning_tokens=delta.get("session_reasoning_tokens"),
        total_tokens=delta.get("session_total_tokens"),
        usage_complete=True,
    )
    try:
        return usage.complete_call(call_id, usage_delta, estimated=estimated)
    except Exception:  # noqa: BLE001
        logger.exception("complete_call 失败")
        return False


def raw_api_calls(delta: dict[str, int]) -> str:
    """api_calls 不进 NormalizedUsage（不重复加总），保存为受限 JSON 供核对。"""
    return json.dumps({"api_calls": delta.get("session_api_calls", 0)})
