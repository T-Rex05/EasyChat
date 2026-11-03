"""Portable provider usage buckets and explicit per-run trace correlation."""
from contextlib import contextmanager
from contextvars import ContextVar

_CONTEXT = ContextVar("agentforge_trace_context", default=None)


def current_trace_context():
    value = _CONTEXT.get()
    return dict(value) if value else None


@contextmanager
def trace_context(run_id, session_id):
    token = _CONTEXT.set({"run_id": run_id, "session_id": session_id, "parent_request_id": ""})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def note_api_request(session_id, request_id):
    context = current_trace_context()
    if context:
        _CONTEXT.set({**context, "parent_request_id": request_id, "model_session_id": session_id})


def _mapping(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return vars(value) if hasattr(value, "__dict__") else {}


def trace_usage(raw):
    """input_tokens means uncached input; prompt_tokens includes all input buckets."""
    data = _mapping(raw)
    unknown = {key: None for key in (
        "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
        "reasoning_tokens", "total_tokens", "prompt_tokens")}
    unknown["usage_complete"] = False
    outgoing = data.get("output_tokens", data.get("completion_tokens"))
    if "cache_read_tokens" in data or "cache_write_tokens" in data:
        incoming = data.get("input_tokens")
        read, write = data.get("cache_read_tokens", 0), data.get("cache_write_tokens", 0)
    elif "cache_read_input_tokens" in data or "cache_creation_input_tokens" in data:
        incoming = data.get("input_tokens")
        read, write = data.get("cache_read_input_tokens", 0), data.get("cache_creation_input_tokens", 0)
    else:
        prompt = data.get("prompt_tokens", data.get("input_tokens"))
        details = _mapping(data.get("prompt_tokens_details", data.get("input_tokens_details")))
        read, write = details.get("cached_tokens", 0), 0
        incoming = prompt - read if type(prompt) is int and type(read) is int else None
    buckets = (incoming, outgoing, read, write)
    if any(type(value) is not int or value < 0 for value in buckets):
        return unknown
    reasoning = data.get("reasoning_tokens")
    if reasoning is None:
        reasoning = _mapping(data.get("completion_tokens_details", data.get("output_tokens_details"))).get("reasoning_tokens", 0)
    total = data.get("total_tokens")
    if total is None:
        total = sum(buckets)
    if type(total) is not int or total < 0 or type(reasoning) is not int or reasoning < 0:
        return unknown
    return {"input_tokens": incoming, "output_tokens": outgoing, "cache_read_tokens": read,
            "cache_write_tokens": write, "reasoning_tokens": reasoning, "total_tokens": total,
            "prompt_tokens": incoming + read + write, "usage_complete": True}
