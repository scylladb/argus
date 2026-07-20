---
status: approved # draft | approved | in_progress | blocked | complete
domain: infrastructure
created: 2026-06-04
last_updated: 2026-07-20
owner: CodeLieutenant
---

# Event Summarization — Design

Refs: [ARGUS-146](https://scylladb.atlassian.net/browse/ARGUS-146) ·
review discussion in [PR #1016](https://github.com/scylladb/argus/pull/1016)

## 1. Problem Statement

SCT ERROR/CRITICAL events are long and noisy: a single event message routinely runs hundreds
to thousands of characters (the frontend already hard-truncates at 600 chars —
`frontend/TestRun/SCT/SctEvent.svelte:30`, `MESSAGE_CUTOFF = 600`).

The primary consumer this hurts is **Zeus**, the AI investigation service. Zeus loads a run's
events into its conversation context at the start of an investigation, and those events are
then **re-read on every subsequent step** — and most runs are investigated by Zeus multiple
times. Every re-read pays the full token cost of the raw event bodies again. Long,
low-signal-to-noise inputs also degrade LLM reasoning quality (hallucination risk).

Summarizing each unique event **once**, with a cheap model, and storing the result turns a
per-read cost into a one-time cost: every later read (by Zeus, and optionally by humans)
consumes the short summary instead of the raw wall of text.

For **humans** the value is contested (see the PR discussion): a summary is easier to scan,
but it is preprocessed information — a triager verifying an LLM's conclusions wants the raw
message, and a misleading summary is worse than a long one. The design therefore treats
human-facing display as **opt-in, configurable per user**: the original message stays the
default, the summary is one click away, and each user can flip which one they see first.

## 2. Current State

**Event pipeline (backend):**

- `argus/backend/plugins/sct/testrun.py:79` — `SCTEvent` model (`sct_event`). PK = partition
  `(run_id, severity)` + clustering `ts` (ASC). Fields incl. `event_id`, `event_type`,
  `message` (required), `duplicate_id`.
- `argus/backend/plugins/sct/testrun.py:108` — `SCTUnprocessedEvent`
  (`sct_unprocessed_events`): the processing queue drained by the argusAI worker.
- `argus/backend/plugins/sct/service.py:478` — `SCTService.submit_event` saves the event and
  (line 512) enqueues an `SCTUnprocessedEvent` for ERROR/CRITICAL severities.
- `argus/backend/plugins/sct/service.py:528` — `SCTService.get_events` delegates to
  `SCTTestRun.get_events_limited` (`testrun.py:372`), which runs `SELECT * FROM sct_event ...`
  and returns raw row dicts — **any new column on `sct_event` is returned automatically**.

**The argusAI worker** (`argusAI/`, same repo — deployed as a separate systemd service):

- `argusAI/event_similarity_processor_v2.py` — standalone worker process. Infinite loop:
  fetch up to 100 queue rows (`_process_batch`), and per event: read message → sanitize
  (`MessageSanitizer`) → generate embedding (local ONNX model, fast) → **duplicate check**
  via ANN search (`_mark_event_is_duplicate`, line 126; short-circuit at line 284-285: a
  duplicate gets `duplicate_id` set on `sct_event` and is dequeued, skipping all remaining
  steps) → store embedding → delete queue row.
- DB access is **raw CQL** via `argusAI/utils/scylla_connection.py` (`ScyllaConnection`,
  prepared-statement cache). The worker never calls `cqlengine.connection.setup()` — CQLEngine
  model methods (`.save()`, `.objects`) would raise in this process. Config comes from
  `Config.load_yaml_config()` (plain dict, no Flask app context).
- Deployed via `argusAI/deployment/argusai_event_similarity_processor.service`.

**Duplicate handling downstream:** the frontend groups duplicates under the canonical event
(`SctEvents.svelte`, `duplicate_id`); the CLI aggregates them too
(`cli/cmd/run_nemeses_events.go:125`, `deduplicateEvents`). Both display surfaces already
show the **canonical** event as the representative.

**Frontend:** `frontend/TestRun/SCT/SctEvent.svelte` renders a single event; it already has a
truncate/expand toggle (`fullMessage` `$state`, line 159; button at line 366).

**CLI (Go):** `argus run events` — `runEventsCmd` in `cli/cmd/run_nemeses_events.go:176`;
the `SCTEvent` struct is `cli/internal/models/runs.go:198`; output goes through
`out.Write(models.SCTEventsResponse{...})` with a response cache.

**Zeus:** external service, reached through the authenticated proxy
`/api/v1/zeus/<path>` (`argus/backend/controller/api.py:628`); it reads run events through
the Argus API.

**Dependencies:** no OpenAI/LLM dependency exists anywhere in the repo today; `openai` is not
in `pyproject.toml`.

## 3. Goals

1. Every **unique** (non-duplicate) ERROR/CRITICAL event gets a stored, model-generated
   summary, best-effort, within the worker's normal processing lag. Duplicates are never
   summarized — the canonical event's summary covers them (this is also where the cost
   saving comes from: duplicates are the bulk of event volume).
2. The summary is **stored once and reused by all investigations** — every Zeus read of the
   run, and every human view, across the event's lifetime.
3. Serving is zero-cost: `get_events` payloads carry a `summary` field with no extra query.
4. **Fail silently:** an event without a summary (not yet processed, summarization failed,
   feature disabled, worker down) renders exactly as today, everywhere — `summary` is `null`
   and consumers fall back to `message`. No errors, no blank states.
5. Human display is **configurable per user**: which body renders first (original vs.
   summary) is a user preference; the other is always one click/flag away. Default:
   **original first** (summaries are opt-in for humans).
6. **Embeddings are never slowed, blocked, or altered by summarization.** The embedding path
   stays byte-for-byte as-is and dequeues on its own schedule; an OpenAI outage has zero
   effect on it.
7. Metrics are defined **up front** (token usage, cost, latency, coverage) so the pilot can
   be priced and the model choice validated with real numbers.

## 4. Non-Goals (decisions from the PR review)

These were in earlier drafts and are **deliberately dropped**:

- **No separate summary table.** The summary is a column on `sct_event`. This removes the
  keying and keyspace questions entirely, and removes the attach-query from serving.
- **No second queue, worker, or systemd unit.** The existing similarity processor is the
  single consumer of the single existing queue; this also eliminates the shared-queue race
  that a second consumer would introduce. No new enqueue in `submit_event`.
- **No batching.** One model call per event. There are several minutes of headroom before
  auto-investigation picks up a run, so per-event latency is fine; batching's
  chunking/char-budget/index-mapping complexity buys little (event tokens cost the same
  either way; prompt caching already discounts the repeated system prompt).
- **No truncation.** Never trim event input before summarizing — the tail of a stack trace
  is exactly the detail a triager needs. Large events are sent as-is.
- **No sanitization of summarizer input.** `MessageSanitizer` strips node names, IPs, and
  paths — right for embedding similarity, wrong for summaries, where those are the details
  worth keeping (see the worked example in the PR discussion, which preserves node name and
  event id). The summarizer receives the raw message.
- **No min-length gate.** Every unique ERROR/CRITICAL event is summarized, full stop.
- **No `status=failed` markers, no retries.** On failure: log, leave `summary` null, move
  on. Null already means "fall back to the original".
- **No live model swap.** Changing the model is a config edit + worker restart.
- **No per-run digest.** Different data model and UI; out of scope.
- **No summarization before embedding.** Embeddings continue to consume the sanitized raw
  message unchanged.

## 5. Design

### 5.1 Data model

Add one nullable column to `SCTEvent` (`argus/backend/plugins/sct/testrun.py:79`):

```python
summary = columns.Text()  # LLM-generated summary; null until/unless summarized
```

No new tables. `flask sync-models` picks up the new column automatically: `SCTEvent` is
already registered in the SCT plugin's `all_models` (`plugins/sct/plugin.py:27`), and
CQLEngine's `sync_table` issues `ALTER TABLE sct_event add summary` for columns missing
from the live schema (verified in `cassandra.cqlengine.management._sync_table`). No
registration changes are needed.

The worker writes it with a raw-CQL upsert, keyed by the event's identity:

```sql
UPDATE sct_event SET summary = ? WHERE run_id = ? AND severity = ? AND ts = ?
```

This is exactly the pattern the worker already uses to set `duplicate_id` on `sct_event`
(`event_similarity_processor_v2.py:152`) — established precedent, not new machinery. A
crash-and-reprocess simply overwrites the same cell — idempotent by construction.

### 5.2 Processing flow — one worker, parallel side-task

Summarization lives **inside `event_similarity_processor_v2.py`** as a background task
dispatched from the existing per-event pipeline. The reconciliation of the two review
requirements ("dispatch in parallel, embedding never waits" and "summarize only
deduplicated events") is the dispatch point: the duplicate verdict requires the embedding,
so summarization is dispatched **immediately after the duplicate check resolves to
"unique"** (i.e., alongside step 4, embedding storage). From that moment the two paths are
fully independent:

```
_process_single_event(run_id, severity, ts):
  read message ─ sanitize ─ embed ─ duplicate?
                                      ├─ yes → mark duplicate_id, dequeue. Done (never summarized)
                                      └─ no  ─┬─ store embedding, dequeue        (main loop, as today)
                                              └─ submit summarization task       (background executor)
                                                    └─ OpenAI call (raw message, no truncation)
                                                         ├─ ok   → UPDATE sct_event SET summary=...
                                                         └─ fail → log; summary stays null
```

- **Bounded concurrency.** Tasks run on a `ThreadPoolExecutor` with a small, configurable
  worker count (`EVENT_SUMMARIZATION_MAX_CONCURRENCY`) to protect OpenAI rate limits. The
  main loop only *submits* — it never joins or waits on the executor, so embedding
  throughput is unaffected by OpenAI latency or outage. If the executor's queue backs up,
  submissions are dropped with a log line (best-effort, never backpressure the main loop).
- **Best-effort semantics.** Queue-row deletion is owned by the embedding path exactly as
  today. A summarization task that fails, or is lost to a worker restart, leaves
  `summary = null` forever — the event is never re-enqueued. Accepted: the fallback is the
  original message, and coverage (not completeness) is the goal.
- **Disabled/keyless mode.** If `EVENT_SUMMARIZATION_ENABLED` is false or `OPENAI_API_KEY`
  is missing, the dispatch is skipped entirely (one log line at startup). The worker
  otherwise behaves exactly as today.
- **Shutdown.** On stop, the executor is drained with a short timeout; unfinished tasks are
  abandoned (their events keep `summary = null`).

### 5.3 Summarizer & configuration

A thin `Summarizer` module under `argusAI/utils/` wraps the LLM call:
`summarize(model, prompt, message) -> str`. OpenAI is the first implementation; the seam
exists so a different provider is a new implementation, not a rewrite. Each call's `usage`
object is logged (see §6).

Config keys (in `argus_web.example.yaml`, read once at worker startup via
`Config.load_yaml_config()`; changing any of them = worker restart):

| Key | Default | Notes |
| --- | ------- | ----- |
| `OPENAI_API_KEY` | — | placeholder in the example file only; follows the existing secret conventions |
| `OPENAI_SUMMARY_MODEL` | `gpt-5-mini` | starting point; final choice is gated on the evaluation (§7) |
| `EVENT_SUMMARIZATION_ENABLED` | `false` | master switch |
| `EVENT_SUMMARIZATION_PROMPT` | built-in default | editable without a code change; the working baseline from the PR discussion: *"Summarize this error event in a way we don't lose information and use minimum tokens. Don't add anything more from your side."* |
| `EVENT_SUMMARIZATION_MAX_CONCURRENCY` | `4` | executor size / rate-limit guard |

New dependency: `openai` in the root `pyproject.toml` (argusAI uses the root project).

### 5.4 Serving

`get_events_limited` already does `SELECT *` and returns raw row dicts, so the `summary`
column travels in every event payload **with zero backend code changes**. `message` stays in
the payload unchanged; the field is additive and existing API consumers are unaffected.
Duplicates carry `summary = null` by design — both display surfaces already group them under
the canonical event, which is the one carrying the summary.

### 5.5 Web UI

In `frontend/TestRun/SCT/SctEvent.svelte`:

- Add `summary?: string | null` to the `SCTEvent` TS interface (`SctEvents.svelte`).
- When `event.summary` is present, the event body offers **two views** — original message
  and summary — with a toggle, and a clear "AI summary" affordance on the summary view so
  preprocessed text is never mistaken for raw output.
- **Which view renders first is a per-user preference.** Stored in `localStorage`
  (the established pattern for view preferences — e.g. `Views.svelte`,
  `TestDashboard.svelte`); default **original-first**. A server-side `User` column can
  replace localStorage later if cross-device consistency is ever needed (open question).
- When `summary` is null/empty: render exactly as today, no visual change whatsoever.
- Copy-to-clipboard always copies the **original** message.

### 5.6 CLI

`argus run events` (`cli/cmd/run_nemeses_events.go`):

- Add `Summary string` (with JSON tag) to the Go `SCTEvent` struct
  (`cli/internal/models/runs.go:198`).
- **Default output renders the summary** where present, falling back to `message` when null
  — output is never blank. This is the opposite default from the web UI: the CLI is the
  primary interface for scripted/automated callers, so it optimizes for token savings first.
  A `--raw` flag forces the original `message` instead.
- The duplicate-aggregation path (`deduplicateEvents`) keeps the canonical event, which is
  the one carrying the summary; a promoted stand-in duplicate has `summary = null` and falls
  back cleanly.
- Note: the CLI caches event responses (`cache.TTLSCTEvents`, 5 minutes —
  `cli/internal/cache/keys.go:49`); a summary written after an event was cached appears
  once the TTL lapses — acceptable for best-effort.

### 5.7 Zeus integration

The whole point of the feature is that Zeus reads summaries instead of raw messages. Since
the API payload carries both `message` and `summary`, the token saving is only realized when
Zeus **prefers `summary` when non-null** — a small Zeus-side change to coordinate (Zeus is
an external service reached via the `/api/v1/zeus/` proxy). Until Zeus adopts it, the
feature costs money without saving any; adoption is therefore part of the rollout criteria,
not an afterthought.

Separately, and regardless of summarization: Zeus should be instructed to bound how many
events it fetches per investigation step (by time range and/or a `limit`), rather than
pulling a run's entire event history. This is good practice independent of this feature, but
matters more once events are summarized in bulk (see §11.3).

## 6. Metrics & Observability

Defined up front (as done for Zeus) so usage and pricing are assessable from day one. The
worker emits a structured log line **per summarization call** with:

- `model`, `prompt_tokens`, `completion_tokens`, `cached_tokens` (straight from the OpenAI
  response `usage` object), and derived cost;
- `latency_ms`, `input_chars`, `summary_chars` (compression ratio);
- outcome (`ok` / `error` + short reason).

Plus periodic aggregate counters: events summarized, failures, dispatches skipped
(disabled / duplicate / executor full), summarization lag (event `ts` → summary written).

These logs are the data source for the cost evaluation below and for ongoing monitoring of
coverage (what fraction of unique ERROR/CRITICAL events end up with a summary).

## 7. Evaluation

Three evaluations gate the defaults and the rollout; none of them require the full feature
to be built first.

**Model quality — evaluation test (required).** Take 20–50 real production events. Generate
reference summaries with a frontier model (Opus 4.8 or GPT-5.5). Generate candidate
summaries with cheaper models (`gpt-5-mini`, …). Score each candidate against the reference
(LLM-judge and/or embedding similarity) for information preservation — did the summary keep
the failure type, node, root-cause line? Pick the cheapest model that is "good enough"; this
sets `OPENAI_SUMMARY_MODEL`. The harness lives with the argusAI tests and is re-runnable
whenever a model swap is considered.

**Cost analysis (required, with real numbers).** The economics to validate: summarization
cost is *one* cheap-model pass per **unique** event (duplicates — the bulk of volume — are
free); the saving is `(raw_tokens − summary_tokens) × (number of Zeus reads) ×
(Zeus model price)`, where the read count is large because events are loaded at investigation
start, re-read every step, and runs are investigated multiple times. The per-call `usage`
logs (§6) provide the measured inputs. Deliverable: measured break-even (how many Zeus reads
amortize one summarization) and projected monthly cost at current event volume.

**Zeus quality PoC (required before human-facing default changes).** A manual A/B: run Zeus
investigations on the same runs with raw events vs. summaries and compare response quality.
This addresses the compounding-uncertainty concern from review (summarizer accuracy ×
Zeus accuracy) with evidence rather than argument — the counter-hypothesis being that a
shorter, cleaner context *improves* Zeus's accuracy rather than degrading it.

**Rollout.** Ship dark behind `EVENT_SUMMARIZATION_ENABLED=false`; pilot on a handful of
jobs first while watching the §6 metrics, then widen. If a job-scoped pilot gate is needed,
a temporary allowlist config key checked at dispatch time is the one-line lever; it is not
part of the steady-state design.

## 8. Testing Requirements

- **Worker unit tests (`argusAI/tests/`),** mirroring the v2 processor tests: OpenAI client
  mocked; unique event → summarization task dispatched → `UPDATE` executed with the right
  key; duplicate event → no dispatch; OpenAI error → logged, no write, loop unaffected;
  disabled / missing key → no dispatch, no crash; concurrency bound respected; executor
  backlog → dropped with log, main loop never blocks.
- **Backend unit tests (`argus/backend/tests/`):** `get_events` payload includes `summary`
  (value when set, `null` otherwise); original `message` intact in both cases.
- **Integration (Docker ScyllaDB, `@pytest.mark.docker_required`),** extending
  `argus/backend/tests/sct_events/test_event_embedding_integration.py`: submit ERROR event →
  queue row appears → one worker cycle with mocked OpenAI → `sct_event.summary` populated,
  queue row gone, `get_events` returns it; embedding rows identical to a run with
  summarization disabled (goal 6, demonstrated).
- **Evaluation harness (§7)** checked in and runnable on demand.
- **Manual:** UI preference + toggle on a real run; `argus run events --summary`; a run with
  summarization disabled shows originals everywhere with no errors.

## 9. Success Criteria

- A freshly submitted unique ERROR/CRITICAL event acquires a stored summary via the worker;
  the summary is visible in UI and CLI with the original one toggle/flag away; duplicates
  are never summarized.
- Per-user display preference works; the out-of-the-box default is original-first.
- Disabling summarization (flag off / no key / worker down / OpenAI outage) leaves the
  entire system functional on original text — demonstrated, not assumed.
- Embedding pipeline output is byte-for-byte unchanged with the feature on or off.
- Token/cost metrics are being emitted and the cost analysis (§7) is produced from them.
- Zeus consumes summaries and the measured cost per investigation drops.

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Misleading summary misdirects a human triager | Medium | Medium | Original is the default view and always retained; summaries are opt-in per user, visibly labeled as AI-generated; copy-to-clipboard stays raw. |
| Summarizer error compounds with Zeus error, lowering end-to-end accuracy | Medium | High | Zeus quality PoC (§7) before relying on summaries; counter-effect (shorter context → better reasoning) measured, not assumed. |
| OpenAI cost exceeds the saving | Medium | High | Only unique (deduplicated) events are summarized; cheap model (~20× cheaper than frontier); per-call usage metrics from day one; measured break-even before wide rollout. |
| OpenAI outage / latency | Medium | Low | Summarization is an isolated background task; embeddings and serving are untouched; affected events keep `summary=null` and fall back. |
| Rate limits at high event volume | Medium | Medium | Bounded executor concurrency; duplicates (bulk of volume) never reach OpenAI. |
| Lost summaries on worker crash/restart (no retry) | Medium | Low | Accepted under best-effort: fallback is the original message. A backfill pass over `summary IS NULL` events can be added later if coverage proves too low. |
| Raw event content (node names, IPs, paths) sent to OpenAI | Low | Medium | Deliberate (§4 — sanitization would strip the useful details); events contain test-infrastructure data, not customer data; flag to security if that assumption ever changes. |
| Secret leakage (`OPENAI_API_KEY` in YAML) | Low | High | Existing `ZEUS_TOKEN`/`*_SECRET` conventions; placeholder only in the example file. |
| Stale CLI cache hides fresh summaries | High | Low | Accepted: TTL-bounded; summaries are not time-critical for CLI users. |

## 11. Open Questions

1. **Final model** — `gpt-5-mini` is the working default; the evaluation test (§7) decides.
2. **Per-user preference storage** — **decided: localStorage** (per-browser, zero backend
   work, matches existing view-preference patterns). A server-side `User` column can replace
   it later if cross-device consistency is ever needed; not worth the backend work up front.
3. **Zeus payload shape** — **decided: no dedicated summaries-only view.** Instead, the CLI
   (§5.6) defaults to summary-first output (`--raw` for the original), and Zeus is instructed
   to bound its event fetches by time range / `limit` per investigation step rather than
   pulling a run's full event history — see §5.7.
4. **Record the producing model?** **Decided: no.** Dropped with the separate table (no
   `model` column on `sct_event`). If production A/B of models is ever needed, comparison
   happens offline via the evaluation harness instead.
