# Tool result management — deterministic foundation

This opt-in module saves scoped originals before context trimming, copies selected
exact values into bounded model views, and exposes paged recovery. It does not call
a judge/summarizer model or actively refold old history.

## Enable

Set these variables in the **server process** before starting AgentForge:

~~~powershell
$env:AGENTFORGE_CONTEXT_RESULTS = "rules"
# Optional: choose a private directory outside the source/model workspace.
$env:AGENTFORGE_CONTEXT_RESULTS_DIR = "E:\AgentForgePrivate\tool-results"
~~~

Without the optional path, Windows uses
%LOCALAPPDATA%/AgentForge/tool-results; other platforms use
~/.local/share/AgentForge/tool-results. The directory must be private to the
service account and outside the source workspace and its ancestors. An invalid
directory or initialization failure logs a warning and falls back to legacy
handling. No result is claimed recoverable until its original has been saved.

Use AGENTFORGE_CONTEXT_RESULTS=off (the default) and restart to disable new result
management. Existing originals expire under the same TTL; disabling does not
delete them. Previously sealed rows remain protected from generic history
rewrites when an old conversation is resumed with the switch off.

## Candidate policy and projection ablation

Defaults remain `AGENTFORGE_CONTEXT_POLICY=rules-v1` and
`AGENTFORGE_TASK_STATE_PROJECTION=full`. Candidate settings are explicit:

~~~powershell
$env:AGENTFORGE_CONTEXT_RESULTS = "rules"
$env:AGENTFORGE_CONTEXT_POLICY = "conservative-v1"
$env:AGENTFORGE_TASK_STATE_PROJECTION = "delta"
~~~

`conservative-v1` augments large JSON views with `other_fields`: exact short
scalars not recognized by protected-key rules, each with a source pointer. They
are not relevance predictions and are not promoted into the protected TaskState
ledger. Protected fields are budgeted first. The pool holds at most 64 candidates,
favoring shallow fields then source order; scalar source tokens over 256 characters
are omitted intact. Counts/scan status disclose unsupported, ambiguous or oversized
JSON. Capture-relative fields carry `source=captured_output`, requiring that source
to be read/parsed first. Data missing from the archived tail is never selected.

`full` keeps the existing bounded snapshot projection; `off` suppresses only model
projection, not evidence commits or recovery. `delta` uses retained same-scope
history, requires a full anchor plus a continuous base-version chain, and emits
only unseen complete observations. Lost anchors, ledger recreation or rollback
rebase to full. Expiry, eviction and sync-error transitions remain visible. A
persisted generation token distinguishes clear/recreate from version reuse.
Unknown settings fail explicitly before runtime initialization.

These are experimental alternatives. No post-change model evaluation has proved
lower total tokens/latency. See [ablation preparation](../../../eval/context_budget/README.md).

## Supported behavior

- The shared Hermes boundary covers sequential, concurrent, mixed and inline tools.
  Managed messages bypass earlier lossy guards and later generic content pruning.
  The generic transform_tool_result plugin hook is skipped in this mode; tools
  that require redaction must produce already-redacted results before this boundary.
  Existing execution authorization, pre-tool guards and native risk wrapping remain.
- Small text results stay unchanged. Large results become bounded JSON views with
  artifact_id, exact protected values, source locations, preview and completeness.
- Default model view limit: 8,000 characters, additionally constrained by the
  runtime's per-batch ticket. This is a character budget, not billed token usage.
- Rule-based protected fields include IDs, paths, versions, statuses, error codes,
  timestamps, amounts/units and related suffixed keys. Values are copied, not
  generated. Excess fields are explicitly counted as omitted; rules do not
  guarantee recognition of every task-relevant fact.
- SQLite metadata and original files survive restart. Scope is authenticated
  user + root conversation + logical agent. Root identity survives physical
  session rotation; children are separate identities. Sharing requires an
  explicit persisted per-artifact grant at the host/store API.
- The model view is sealed after native message adaptation. Persisted view hashes,
  message metadata and completion events refer to the same canonical content.
- Existing compression retains a bounded original-reference/field manifest.
  Active task-driven historical folding is a later feature.
- TaskState now commits scoped exact evidence synchronously at tool-batch
  boundaries and projects bounded untrusted data before the next model request.
  See [TaskState evidence](../TASK_EVIDENCE.md) for isolation and retention details.

## Recovery

The model-visible tools do not accept user/thread/agent identity parameters:

~~~python
context_read(artifact_id="ar_...", json_pointer="/job_id")
context_read(artifact_id="ar_...", start_line=10, end_line=20)
context_read(artifact_id="ar_...", cursor="cursor from the preceding page")
context_search(query="receipt_id", artifact_ids=["ar_..."])
~~~

Results include status, raw_complete and source/hash information. Read pages
return next_cursor when more content remains; pass the same selector when
continuing. Search uses bounded literal matching with source line positions, not
semantic retrieval. A search result marked truncated may require a narrower
query; search continuation and table-specific selectors are not implemented.
JSON key/scalar matches now include `json_pointer`, `parent_pointer`, `json_type`
and up to eight neighboring pointers/types when `json_location_status=ok`.
For example, searching `alias` in `{"legacy":{"alias":"OLD","version":2}}`
returns `/legacy/alias`; pass that exact pointer to `context_read`. Sibling values
are not copied. `neighbors_omitted` counts omitted neighbors; an empty pointer
selects the root JSON scalar. Keys with `/` or `~` use RFC 6901 escaping.

The locator validates the complete captured JSON document against source token
spans. Duplicate keys, invalid JSON, cross-node literal queries, parser limits or
tight output budgets give explicit `json_location_status` fallbacks and keep the
literal snippet/line positions. It never guesses a parent path. Capture may
still be incomplete: `raw_complete=false` remains authoritative even if the
captured portion happens to parse as JSON. Number tokens outside the reader's
decoder limits/range are not advertised as recoverable selectors.

Parsing work is capped across one store search at 2 Mi source characters and
20,000 nodes (including partial failed parses). Each document also has the
64-level depth and reader's 2,048-byte pointer limits. After the work limit,
literal hits remain available with `limit_exceeded` instead of a guessed path.
Enrichment has a separate capped budget; the
model tool drops neighbors, then shrinks snippets, and can omit structure entirely
to fit its complete encoded envelope. The parser only runs for hash-verified,
authorized literal matches and stops at the match cap. It does not search decoded
string values, reparse JSON embedded inside strings, or persist a structure index.

Cursor selection and source hashes are validated. Expired/unavailable originals
produce explicit states and are never silently recreated by rerunning a tool.

Recovery output is bounded by both the requested page size and the actual tool
call ticket, including its JSON envelope. It is not archived or summarized again.

## CodeMode

Internal tool return values remain complete. Only emitted print/log output is
captured for context management. Captured stdout is archived as JSON:

~~~text
/execution_result   original run_python status/error/output envelope
/captured_output    captured print/log text
/capture           attempt, completeness and byte counts
~~~

Each execution/retry has a separate sink. Timeout/cancellation closes its sink,
and late writes cannot enter the next attempt. This does not terminate an
already-running Python thread. log_debug remains file-only; unprinted Python
locals are not automatically saved. Only the latest attempt stream is archived
by this slice; the execution envelope retains existing retry diagnostics.

## Access boundary and limits

Ordinary CodeMode file reads/searches cannot enter the configured private store,
its resolved aliases, or the former data/tool_results location. Under managed
mode the native terminal/process/read_file/write_file/search_files/patch tools
are rejected before dispatch: they otherwise bypass scoped retrieval by reading
the server filesystem directly. Use the constrained CodeMode file helpers and
context_read/context_search. Disabling managed mode restores the legacy tool
behavior. An isolated host execution environment is required before allowing
unrestricted host tools alongside a shared multi-user raw store.

Application checks are not OS sandboxing. The service operator and anyone already
authorized to execute arbitrary code as the service account can access its data.
Custom tools must also respect the private-store boundary.

Storage defaults:

| Limit | Default |
| --- | --- |
| Captured bytes per original | 8 MiB |
| Original + persisted-view bytes per user | 256 MiB |
| Original + persisted-view bytes globally | 1 GiB |
| Original TTL | 24 hours |
| Tombstone retention | 7 days |

These quotas bound payload/view bytes, not SQLite/index/filesystem allocation.
At the hard cap, raw_complete=false and captured/dropped byte counts disclose
loss. source_hash describes the captured bytes. There is no active-task lease
renewal in this slice. Original files are atomically published, SQLite changes
use transactions, and reconciliation marks missing/corrupt files unavailable
and removes orphaned files; file+SQLite publication is not a cross-resource
atomic transaction.

Multimodal blocks keep the native runtime path without text conversion.
Quota/storage failures use the legacy bounded path and do not rerun business
tools. Such outputs are not claimed recoverable.

## Offline verification

From the repository root:

~~~powershell
python -m pytest --noconftest -q tests/context_results tests/test_task_state.py
python -m ruff check backend/context/tool_results tests/context_results backend/hermes/agent/result_finalizer.py backend/hermes/agent/tool_executor.py backend/hermes/model_tools.py
~~~

The tests use temporary directories, fake tools/providers and explicit runtime
scopes. --noconftest avoids the repository-wide fixture that loads the service
.env. No paid inference or external business database is required.
