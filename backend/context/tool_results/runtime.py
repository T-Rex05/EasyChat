"""Authenticated per-run binding and per-tool scopes, inherited through copy_context."""
from __future__ import annotations

import contextvars
import copy
import json
import logging
import os
import threading
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from pathlib import Path

from .manager import ResultManager
from .store import ResultStore
from .types import ResultScope
from .options import runtime_options

_BINDING = contextvars.ContextVar("agentforge_result_binding", default=None)
_ACTIVE_TOOL = contextvars.ContextVar("agentforge_result_tool", default=None)
logger = logging.getLogger(__name__)
# These native tools can read the host filesystem without the recovery ACL.
# Managed sessions use the constrained CodeMode file helpers until a genuinely
# isolated execution environment is integrated.
_UNSCOPED_HOST_TOOLS = frozenset({"terminal", "process", "read_file", "write_file", "search_files", "patch"})


def context_results_enabled() -> bool:
    return os.environ.get("AGENTFORGE_CONTEXT_RESULTS", "off").strip().lower() in {"1", "on", "true", "rules"}


def default_store_root() -> Path:
    configured = os.environ.get("AGENTFORGE_CONTEXT_RESULTS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    private_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return private_root / "AgentForge" / "tool-results"


def is_result_store_path(path) -> bool:
    """File tools cannot bypass the scoped recovery API, including custom store roots."""
    target = Path(path).resolve()
    roots = [default_store_root().resolve()]
    binding = _BINDING.get()
    if binding is not None:
        roots.append(binding.manager.store.root)
    return any(target == root or target.is_relative_to(root) for root in roots)


@dataclass(frozen=True)
class ActiveTool:
    runtime: "HostResultRuntime"
    scope: ResultScope
    max_chars: int


def active_tool() -> ActiveTool | None:
    return _ACTIVE_TOOL.get()


def managed_results_active() -> bool:
    return active_tool() is not None


class HostResultRuntime:
    def __init__(self, binding, agent, agent_id):
        self.binding = binding
        self.agent = agent
        self.manager = binding.manager
        self.scope = ResultScope(binding.user_id, binding.thread_id, agent_id,
                                 str(getattr(agent, "session_id", "") or ""), binding.run_id)
        self._captures = {}
        self._lock = threading.Lock()
        self._batch_id = None
        self._batch_snapshot = None
        self._batch_order = []
        self._batch_results = {}
        self._evidence_error = None

    def _snapshot(self):
        try:
            snapshot = self.binding.task_state.get_task_snapshot(
                self.scope, semantic_state=self.binding.semantic_state,
                goal=getattr(self.agent, "_subagent_goal", None))
        except Exception as exc:
            self._evidence_error = type(exc).__name__
            snapshot = {
                "scope": {"user_id": self.scope.user_id, "thread_id": self.scope.thread_id,
                          "agent_id": self.scope.agent_id}, "semantic_state": {},
                "tool_evidence": {"version": None, "results": [], "evicted_results": 0,
                                  "conflicts": [], "unavailable": True}}
        snapshot["evidence_sync_error"] = self._evidence_error
        return snapshot

    def task_snapshot(self):
        with self._lock:
            return copy.deepcopy(self._batch_snapshot) if self._batch_snapshot is not None else self._snapshot()

    def begin_batch(self, call_ids):
        with self._lock:
            if self._batch_id is not None:
                raise RuntimeError("Overlapping batches on the same logical agent")
            self._batch_snapshot = self._snapshot()
            self._batch_id = self.binding.run_id + ":" + uuid.uuid4().hex
            self._batch_order = list(call_ids)
            self._batch_results = {}

    def end_batch(self):
        with self._lock:
            if self._batch_id is None:
                return
            try:
                rows = [self._batch_results[key] for key in self._batch_order if key in self._batch_results]
                if rows:
                    self.binding.task_state.record_tool_batch(self.scope, self._batch_id, rows)
                    self._evidence_error = None
            except Exception as exc:
                self._evidence_error = type(exc).__name__
                logger.warning("Task evidence commit failed (%s); business results preserved", self._evidence_error)
            finally:
                self._batch_id = None
                self._batch_snapshot = None
                self._batch_results = {}
                self._batch_order = []

    def call_scope(self, call_id):
        return replace(self.scope, tool_call_id=str(call_id),
                       session_id=str(getattr(self.agent, "session_id", "") or ""))

    @contextmanager
    def tool_context(self, tool_name, tool_call_id, max_chars):
        if tool_name in _UNSCOPED_HOST_TOOLS:
            raise PermissionError(
                "Managed tool results require scoped file access. Use run_python file helpers "
                "or context_read/context_search; unrestricted host tools are disabled in this mode."
            )
        scope = self.call_scope(tool_call_id)
        token = _ACTIVE_TOOL.set(ActiveTool(self, scope, max(0, int(max_chars))))
        capture = nullcontext(None)
        if tool_name == "run_python":
            from .capture import capture_context
            capture = capture_context()
        try:
            with capture as holder:
                try:
                    yield
                finally:
                    if holder is not None:
                        with self._lock:
                            self._captures[str(tool_call_id)] = holder
        finally:
            _ACTIVE_TOOL.reset(token)

    def prepare(self, tool_name, tool_call_id, raw_result, max_chars):
        with self._lock:
            holder = self._captures.pop(str(tool_call_id), None)
        capture = holder.latest if holder is not None else None
        scope = self.call_scope(tool_call_id)
        if capture is not None:
            scope = replace(scope, attempt_id=str(capture.attempt_id))
        prepared = self.manager.prepare(scope, tool_name, raw_result, max_chars=max_chars, capture=capture)
        prepared.tool_name = tool_name
        prepared.task_state_version = self.task_snapshot()["tool_evidence"]["version"]
        return prepared

    def seal(self, prepared, canonical_content):
        metadata = self.manager.seal(prepared, canonical_content)
        if metadata.get("artifact_id") and prepared.action != "recovery":
            row = {**metadata, "tool_call_id": prepared.scope.tool_call_id,
                   "attempt_id": prepared.scope.attempt_id, "tool_name": prepared.tool_name,
                   "protected": prepared.evidence_protected,
                   "extraction_partial": prepared.evidence_scan_partial,
                   "omitted_protected_fields": 0}
            with self._lock:
                if self._batch_id is not None:
                    self._batch_results.setdefault(prepared.scope.tool_call_id, row)
                else:
                    # Single-call integrations outside the executor still synchronize before return.
                    try:
                        self.binding.task_state.record_tool_batch(
                            self.scope, self.binding.run_id + ":" + prepared.view_id, [row])
                        self._evidence_error = None
                    except Exception as exc:
                        self._evidence_error = type(exc).__name__
        return metadata

    def task_state_message(self, max_chars=4000, *, history=None):
        """Bounded low-authority projection; never shorten an exact value silently."""
        if self.binding.projection_mode == "off":
            return None
        from .projection import evidence_message
        return evidence_message(self.task_snapshot(), self.scope, mode=self.binding.projection_mode,
                                history=history, max_chars=max_chars)

    def budget_pressure(self, prepared, max_chars):
        budget = max(0, int(max_chars))
        content = json.dumps({"status": "budget_pressure", "artifact_id": prepared.artifact_id,
                              "read_with": "context_read"}, separators=(",", ":"))
        if len(content) > budget:
            content = "budget_pressure"[:budget]
        return replace(prepared, content=content, action="budget_pressure", protected=[],
                       omitted_protected_fields=prepared.omitted_protected_fields + len(prepared.protected),
                       presented_other_fields=0,
                       omitted_other_fields=(prepared.omitted_other_fields + prepared.presented_other_fields
                                             if prepared.omitted_other_fields is not None else None),
                       max_chars=budget)


class _RunBinding:
    def __init__(self, root_agent, user_id, thread_id, store, semantic_state=None,
                 result_policy="rules-v1", projection_mode="full"):
        self.root_agent = root_agent
        self.user_id = str(user_id)
        self.thread_id = str(thread_id)
        self.run_id = uuid.uuid4().hex
        self.manager = ResultManager(store, policy=result_policy)
        self.projection_mode = projection_mode
        from backend.context.task_state import TaskStateMaintainer
        from backend.context.task_evidence import EvidenceLedger
        self.task_state = TaskStateMaintainer(
            db_path=store.root / "task-semantic.sqlite3",
            evidence_store=EvidenceLedger(store.root / "task-evidence.sqlite3"))
        self.semantic_state = copy.deepcopy(semantic_state or {})
        self._hosts = {}
        self._lock = threading.RLock()

    def for_agent(self, agent):
        key = id(agent)
        with self._lock:
            if key not in self._hosts:
                if agent is self.root_agent:
                    logical_id = "root"
                else:
                    # Persist across physical session rotation on the same logical child.
                    # Random identity prevents sibling label reuse from granting access.
                    logical_id = getattr(agent, "_context_logical_agent_id", None)
                    if not logical_id:
                        logical_id = "child-" + uuid.uuid4().hex
                        agent._context_logical_agent_id = logical_id
                self._hosts[key] = HostResultRuntime(self, agent, logical_id)
                # Child compressors are created outside the host factory.
                from .compression import install_compression_guard
                install_compression_guard(agent)
            return self._hosts[key]


@contextmanager
def bind_runtime(agent, *, user_id, thread_id, root=None, enabled=None, semantic_state=None,
                 result_policy=None, projection_mode=None):
    # Disabled/fallback runs may still resume previously managed history. Keep
    # sealed rows immutable while letting all unmanaged history use native logic.
    from .compression import install_compression_guard
    install_compression_guard(agent)
    enabled = context_results_enabled() if enabled is None else enabled
    binding = None
    if enabled and user_id and thread_id:
        # Invalid experiment options must not silently disable the access boundary.
        result_policy, projection_mode = runtime_options(result_policy, projection_mode)
        try:
            store_root = (Path(root) if root is not None else default_store_root()).resolve()
            workspace = Path(__file__).resolve().parents[3]
            if store_root == workspace or store_root.is_relative_to(workspace) or workspace.is_relative_to(store_root):
                raise ValueError("Private result storage must be outside the source workspace and its ancestors")
            store = ResultStore(store_root)
            binding = _RunBinding(agent, user_id, thread_id, store, semantic_state, result_policy, projection_mode)
        except Exception as exc:
            logger.warning("Result store initialization failed (%s); using legacy result handling",
                           type(exc).__name__)
    token = _BINDING.set(binding)
    from backend.utils.llm_usage import trace_context
    try:
        with trace_context(binding.run_id if binding else uuid.uuid4().hex, str(thread_id or "")):
            if binding:
                binding.for_agent(agent)
            yield binding
    finally:
        _BINDING.reset(token)


def current_runtime(agent=None):
    if agent is None:
        active = active_tool()
        return active.runtime if active else None
    binding = _BINDING.get()
    return binding.for_agent(agent) if binding else None
