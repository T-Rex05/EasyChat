import copy
import importlib


def managed(content="job_id=J731"):
    return {"role": "tool", "tool_call_id": "c1", "content": content,
            "display_metadata": {"context_result": {
                "managed": True, "artifact_id": "ar_1", "view_id": "v1",
                "protected": [{"pointer": "/job_id", "value": "J731"}]}}}


class AggressiveCompressor:
    def prune_tool_results_only(self, messages, **kwargs):
        result = copy.deepcopy(messages)
        for msg in result:
            if msg["role"] == "tool":
                msg["content"] = "[removed]"
        return result, 999

    def compress(self, messages, **kwargs):
        self.memory_context = kwargs.get("memory_context")
        return [{"role": "assistant", "content": "summary"}]


def test_generic_pruning_cannot_rewrite_managed_tool_content():
    module = importlib.import_module("backend.context.tool_results.compression")
    guard = module.ManagedResultsCompressor(AggressiveCompressor())
    messages = [{"role": "assistant", "tool_calls": [{"id": "c1"}]}, managed()]
    output, _ = guard.prune_tool_results_only(messages)
    assert output[1] == messages[1]
    assert messages[1]["content"] == "job_id=J731"


def test_full_compression_preserves_recoverable_manifest_across_repeated_compaction():
    module = importlib.import_module("backend.context.tool_results.compression")
    inner = AggressiveCompressor()
    guard = module.ManagedResultsCompressor(inner)
    output = guard.compress([managed()])
    assert any("ar_1" in msg["content"] and "J731" in msg["content"] for msg in output)
    assert all(msg["role"] not in {"system", "user"} for msg in output)
    again = guard.compress(output)
    assert any("ar_1" in msg["content"] for msg in again)


def test_no_progress_does_not_append_or_mutate_live_history():
    module = importlib.import_module("backend.context.tool_results.compression")
    class NoProgress:
        def compress(self, messages, **kwargs):
            return messages
    messages = [managed()]
    before = copy.deepcopy(messages)
    output = module.ManagedResultsCompressor(NoProgress()).compress(messages)
    assert output == before
    assert messages == before


def test_compressor_state_writes_reach_the_same_object_as_usage_updates():
    module = importlib.import_module("backend.context.tool_results.compression")
    class Stateful:
        last_prompt_tokens = 100
        awaiting_real_usage_after_compression = False
        def update_from_response(self, value):
            self.last_prompt_tokens = value
            self.awaiting_real_usage_after_compression = False
        def record_completed_compaction(self, *args, **kwargs):
            return "recorded"
    inner = Stateful()
    guard = module.ManagedResultsCompressor(inner)
    guard.last_prompt_tokens = -1
    guard.awaiting_real_usage_after_compression = True
    guard.update_from_response(12000)
    assert guard.last_prompt_tokens == 12000
    assert guard.awaiting_real_usage_after_compression is False
    assert type(guard).record_completed_compaction(guard) == "recorded"


def test_prune_reports_remaining_unmanaged_changes_and_preserves_noop_identity():
    module = importlib.import_module("backend.context.tool_results.compression")
    guard = module.ManagedResultsCompressor(AggressiveCompressor())
    messages = [managed(), {"role": "tool", "tool_call_id": "old", "content": "long original"}]
    output, changed = guard.prune_tool_results_only(messages)
    assert output[0] == messages[0]
    assert output[1]["content"] == "[removed]"
    assert changed > 0
    only_managed = [managed()]
    output, changed = guard.prune_tool_results_only(only_managed)
    assert output is only_managed
    assert changed == 0
