"""Optional host callbacks at the canonical tool-message boundary.

Storage, presentation policy, and authorization belong to the embedding host.
Hermes only allocates ordered batch tickets and preserves native rendering.
"""

from __future__ import annotations

import copy
import inspect
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import wraps
from typing import Any


_WRAPPER_RESERVE = 512
_batch: ContextVar[Any] = ContextVar("hermes_result_batch", default=None)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Batch:
    agent: Any
    runtime: Any
    tickets: dict[str, int]


def _runtime(agent):
    try:
        from backend.context.tool_results.runtime import current_runtime
    except ImportError:
        return None
    return current_runtime(agent)


def managed_batch(execute):
    """Allocate once for the whole batch, including nested mixed segments."""
    @wraps(execute)
    def wrapped(agent, assistant_message, messages, *args, **kwargs):
        existing = _batch.get()
        if existing is not None and existing.agent is agent:
            return execute(agent, assistant_message, messages, *args, **kwargs)
        runtime = _runtime(agent)
        if runtime is None:
            return execute(agent, assistant_message, messages, *args, **kwargs)
        from agent.tool_executor import _budget_for_agent

        budget = _budget_for_agent(agent)
        calls = assistant_message.tool_calls
        share = max(0, min(budget.default_result_size, budget.turn_budget // max(1, len(calls))))
        state = _Batch(agent, runtime, {call.id: share for call in calls})
        token = _batch.set(state)
        try:
            begin = getattr(runtime, "begin_batch", None)
            if begin:
                begin([call.id for call in calls])
            result = execute(agent, assistant_message, messages, *args, **kwargs)
            # A user message may only follow the complete set of tool replies.
            # Never append a steer marker to an already sealed tool view.
            replied = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
            if state.tickets.keys() <= replied and not getattr(agent, "_incremental_persistence_failed", False):
                drain = getattr(agent, "_drain_pending_steer", None)
                steer = drain() if drain else None
                if steer:
                    messages.append({"role": "user", "content": steer})
                    from agent.tool_executor import _flush_session_db_after_tool_progress
                    _flush_session_db_after_tool_progress(agent, messages, stage="user steer after managed tool batch")
            return result
        finally:
            try:
                end = getattr(runtime, "end_batch", None)
                if end:
                    end()
            finally:
                _batch.reset(token)
    return wrapped


@contextmanager
def tool_context(agent, name, call_id):
    state = _batch.get()
    if state is None or state.agent is not agent:
        yield
        return
    max_chars = max(0, state.tickets.get(call_id, 0) - _WRAPPER_RESERVE)
    with state.runtime.tool_context(name, call_id, max_chars):
        yield


def apply_pending_steer(agent, messages, count):
    state = _batch.get()
    if state is None or state.agent is not agent:
        agent._apply_pending_steer_to_tool_results(messages, count)


def sync_task_snapshot(agent, messages):
    """Append a bounded data-only state projection after complete tool replies."""
    runtime = _runtime(agent)
    project = getattr(runtime, "task_state_message", None) if runtime is not None else None
    if project is None:
        return True
    try:
        message = project(history=messages)
        if message is None:
            return True
        metadata = message["display_metadata"]["task_state_snapshot"]
        for previous in reversed(messages):
            if (previous.get("display_metadata", {}).get("task_state_snapshot") == metadata
                    and previous.get("content") == message["content"]):
                return True
        # Do not introduce an assistant row in the middle of a tool-call group.
        for index in range(len(messages) - 1, -1, -1):
            row = messages[index]
            if row.get("role") == "assistant" and row.get("tool_calls"):
                replied = {item.get("tool_call_id") for item in messages[index + 1:] if item.get("role") == "tool"}
                if any(call.get("id", call.get("call_id")) not in replied for call in row["tool_calls"]):
                    return True
                break
        messages.append(message)
    except Exception:
        logger.warning("Task-state projection unavailable; original tool messages preserved", exc_info=True)
        return True
    from agent.tool_executor import _flush_session_db_after_tool_progress
    return _flush_session_db_after_tool_progress(agent, messages, stage="task evidence snapshot")


def drain_pre_api_steer(agent, messages):
    """Deliver late steering without rewriting a previously sealed result.

    The conversation loop calls this before request construction, including
    for managed rows restored from history when the current feature is off.
    """
    target = next((message for message in reversed(messages)
                   if isinstance(message, dict) and message.get("role") == "tool"), None)
    if target is None:
        return True
    managed = bool(target.get("display_metadata", {}).get("context_result", {}).get("managed"))
    if managed:
        # A user turn must not split an assistant's required tool replies.
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if message.get("role") == "assistant" and message.get("tool_calls"):
                replied = {row.get("tool_call_id") for row in messages[index + 1:] if row.get("role") == "tool"}
                for call in message["tool_calls"]:
                    aliases = {call.get("id"), call.get("call_id")} - {None, ""}
                    if aliases and not aliases & replied:
                        return True
                break
    steer = agent._drain_pending_steer()
    if not steer:
        return True
    if managed:
        messages.append({"role": "user", "content": steer})
        from agent.tool_executor import _flush_session_db_after_tool_progress
        return _flush_session_db_after_tool_progress(agent, messages, stage="pre-API user steer")
    from agent.prompt_builder import format_steer_marker
    marker = format_steer_marker(steer)
    existing = target.get("content", "")
    if isinstance(existing, str):
        target["content"] = existing + marker
    else:
        try:
            blocks = list(existing) if existing else []
            blocks.append({"type": "text", "text": marker})
            target["content"] = blocks
        except Exception:
            pass
    return True


def legacy_turn_budget(messages, budget):
    """Charge sealed text before giving the remaining turn budget to legacy L3.

    Multimodal blocks remain native blocks. Their provider token cost cannot be
    inferred from these character tickets, so they never enter the text rewriter
    in managed mode. Completely legacy batches keep their historical behavior.
    """
    managed = [message for message in messages
               if message.get("display_metadata", {}).get("context_result", {}).get("managed")]
    if not managed and _batch.get() is None:
        return messages, budget
    managed_ids = {id(message) for message in managed}
    legacy = [message for message in messages if id(message) not in managed_ids
              and isinstance(message.get("content", ""), str)]
    used_chars = 0
    for message in managed:
        content = message.get("content", "")
        if isinstance(content, str):
            used_chars += len(content)
        elif isinstance(content, list):
            used_chars += sum(len(block.get("text", "")) for block in content
                              if isinstance(block, dict) and isinstance(block.get("text"), str))
    return legacy, replace(budget, turn_budget=max(0, budget.turn_budget - used_chars))


def completion_metadata(callback, metadata):
    """Preserve older four-argument callbacks while supporting host metadata."""
    if metadata is None:
        return {}
    try:
        parameters = inspect.signature(callback).parameters
    except (TypeError, ValueError):
        return {}
    if "context_result" in parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return {"context_result": metadata}
    return {}


def finalize_tool_result(agent, name, args, call_id, raw, *, legacy_prepare,
                         effect_disposition=None, include_hints=True):
    from agent.tool_dispatch_helpers import (
        _append_subdir_hint_to_multimodal,
        _is_multimodal_tool_result,
        make_tool_result_message,
    )

    state = _batch.get()
    hints = (agent._subdirectory_hints.check_tool_call(name, args) or "") if include_hints else ""
    prepared = None
    if state is not None and state.agent is agent:
        ticket = state.tickets.get(call_id, 0)
        # Context-file hints are additive context, not part of the raw result.
        if len(hints) > max(0, ticket - _WRAPPER_RESERVE):
            hints = ""
        try:
            prepared = state.runtime.prepare(name, call_id, raw, max(0, ticket - _WRAPPER_RESERVE - len(hints)))
        except Exception:
            logger.warning("Host result preparation failed; preserving legacy result", exc_info=True)
    managed = prepared is not None and prepared.managed

    def render(content):
        content = copy.deepcopy(content)
        if hints:
            if _is_multimodal_tool_result(content):
                _append_subdir_hint_to_multimodal(content, hints)
            elif isinstance(content, list):
                content.append({"type": "text", "text": hints})
            else:
                content += hints
        content = agent._tool_result_content_for_active_model(name, content)
        return make_tool_result_message(name, content, call_id, effect_disposition=effect_disposition)

    message = render(prepared.content if managed else legacy_prepare(raw))
    if managed:
        try:
            # Native wrappers and model adaptation must fit BEFORE publication.
            # Ask the host for an explicit pressure receipt; never crop exact facts.
            if isinstance(message["content"], str) and len(message["content"]) > ticket:
                prepared = state.runtime.budget_pressure(prepared, max(0, ticket - _WRAPPER_RESERVE))
                message = make_tool_result_message(name, prepared.content, call_id,
                                                   effect_disposition=effect_disposition)
                if len(message["content"]) > ticket:
                    prepared = state.runtime.budget_pressure(prepared, ticket)
                    # This bounded receipt is authored by the host and contains
                    # no original tool text. Keep the native risk/effect fields,
                    # but do not wrap the receipt in another oversized boundary.
                    message["content"] = prepared.content
                    if not isinstance(prepared.content, str) or len(prepared.content) > ticket:
                        raise ValueError("Host pressure receipt exceeds canonical ticket")
            metadata = state.runtime.seal(prepared, message["content"])
            message.setdefault("display_metadata", {})["context_result"] = metadata
        except Exception:
            logger.warning("Host result sealing failed; preserving legacy result", exc_info=True)
            message = render(legacy_prepare(raw))
    return message


def finalize_skipped_result(agent, name, content, call_id, *, effect_disposition=None):
    """Canonicalize synthetic failure replies without executing a tool."""
    return finalize_tool_result(agent, name, {}, call_id, content, legacy_prepare=lambda value: value,
                                effect_disposition=effect_disposition, include_hints=False)
