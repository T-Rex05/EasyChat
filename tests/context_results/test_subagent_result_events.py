"""Exercise the real child progress relay without providers or app startup."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def delegate_module(monkeypatch):
    """Stub unrelated import dependencies, then load the actual delegate module."""
    root = Path(__file__).resolve().parents[2]

    def module(name, **members):
        stub = ModuleType(name)
        stub.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, stub)
        return stub

    file_state = module("tools.file_state")
    module("tools", __path__=[str(root / "backend/hermes/tools")], file_state=file_state)
    module("toolsets", TOOLSETS={})
    module("tools.terminal_tool", set_approval_callback=lambda *args: None)
    module("tools.registry", registry=SimpleNamespace(register=lambda **kwargs: None),
           tool_error=lambda message: {"error": message})
    module("utils", base_url_hostname=lambda value: value, is_truthy_value=bool)
    spec = importlib.util.spec_from_file_location(
        "_context_results_delegate_relay", root / "backend/hermes/tools/delegate_tool.py",
    )
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, loaded)
    spec.loader.exec_module(loaded)
    return loaded


def child_callback(delegate_module, events):
    def parent_callback(event_type, tool_name=None, preview=None, args=None, **kwargs):
        events.append({
            "event_type": event_type, "tool_name": tool_name,
            "preview": preview, "args": args, **kwargs,
        })

    delegate_module._active_subagents["child-1"] = {}
    return delegate_module._build_child_progress_callback(
        0, "inspect evidence", SimpleNamespace(tool_progress_callback=parent_callback),
        subagent_id="child-1", parent_id="parent-1", depth=1,
        session_ref={"session_id": "child-session"},
    )


@pytest.mark.parametrize("event_style", ["legacy", "delegate", "enum"])
def test_completed_result_metadata_reaches_real_parent_callback(delegate_module, event_style):
    events = []
    callback = child_callback(delegate_module, events)
    event_types = {
        "legacy": ("tool.started", "tool.completed"),
        "delegate": ("delegate.tool_started", "delegate.tool_completed"),
        "enum": (delegate_module.DelegateEvent.TASK_TOOL_STARTED,
                 delegate_module.DelegateEvent.TASK_TOOL_COMPLETED),
    }
    started, completed = event_types[event_style]
    view = {"managed": True, "view_id": "view-1", "artifact_id": "artifact-1"}
    callback(started, "query", "query arguments", {"query": "fixture"}, tool_call_id="call-1")
    callback(completed, "query", "exact model content", {"query": "fixture"},
             tool_call_id="call-1", context_result=view, status="completed")

    assert len(events) == 2
    assert [item["event_type"] for item in events] == ["subagent.tool", "subagent.tool"]
    assert [item["stage"] for item in events] == ["started", "completed"]
    assert [item["tool_call_id"] for item in events] == ["call-1", "call-1"]
    assert events[1]["context_result"] is view
    assert events[1]["preview"] == "exact model content"
    assert events[1]["args"] == {"query": "fixture"}
    assert events[1]["status"] == "completed"
    assert all(item["subagent_id"] == "child-1" for item in events)
    assert all(item["child_session_id"] == "child-session" for item in events)
    assert [item["tool_count"] for item in events] == [1, 1]
    assert delegate_module._active_subagents["child-1"]["tool_count"] == 1


def test_completion_neither_counts_nor_batches_a_second_tool(delegate_module):
    events = []
    callback = child_callback(delegate_module, events)
    for index in range(5):
        name = f"tool-{index}"
        callback("tool.started", name, tool_call_id=f"call-{index}")
        callback("tool.completed", name, context_result={"view_id": f"view-{index}"},
                 tool_call_id=f"call-{index}")
    callback._flush()

    tools = [event for event in events if event["event_type"] == "subagent.tool"]
    progress = [event for event in events if event["event_type"] == "subagent.progress"]
    assert len(tools) == 10
    assert [event["tool_count"] for event in tools] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert len(progress) == 1
    assert progress[0]["preview"] == "🔀 tool-0, tool-1, tool-2, tool-3, tool-4"


def test_stage_is_derived_from_event_and_completion_without_start_is_not_counted(delegate_module):
    events = []
    callback = child_callback(delegate_module, events)
    callback("tool.completed", "query", stage="started", tool_call_id="call-1")
    assert len(events) == 1
    assert events[0]["stage"] == "completed"
    assert events[0]["tool_count"] == 0
    callback("tool.started", "next-query", stage="completed", tool_call_id="call-2")
    assert events[-1]["stage"] == "started"
    assert events[-1]["tool_count"] == 1


def test_no_display_channel_keeps_callback_disabled(delegate_module):
    assert delegate_module._build_child_progress_callback(
        0, "inspect evidence", SimpleNamespace(),
    ) is None
