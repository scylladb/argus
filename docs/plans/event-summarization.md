---
status: draft # draft | approved | in_progress | blocked | complete
domain: infrastructure
created: 2026-06-04
last_updated: 2026-06-08
owner: CodeLieutenant
---

# Event Summarization

## 1. Problem Statement

SCT ERROR/CRITICAL events are long and noisy: a single event message routinely runs
hundreds to thousands of characters (the frontend already hard-truncates at 600 chars —
`frontend/TestRun/SCT/SctEvent.svelte:30`, `MESSAGE_CUTOFF = 600`). Raw event text is the
primary input to our downstream AI investigation flow ("Zeus") and to humans triaging runs.

This causes three measurable pains:

1. **Token cost & latency in Zeus** — feeding full raw events inflates prompt token counts,
   which directly increases cost and investigation time per run.
2. **Hallucination risk** — long, low-signal-to-noise event bodies degrade the quality of
   downstream LLM reasoning.
3. **Human readability** — triagers scroll through walls of stack traces to find the point.

We want a concise, model-generated summary attached to each ERROR/CRITICAL event, stored for
reuse, surfaced in the UI/CLI, with the full original always one click/flag away. When no
summary exists, the system must silently fall back to the original message — no errors, no
blank states.

**Explicitly out of scope:** summarizing before embedding generation. Embeddings currently
work well; summarizing first risks degrading similarity matching for events that have no
summary yet. Embeddings continue to consume the existing sanitized raw message unchanged.

## 2. Current State

**The "argus similarity" service** — verified to live *inside this repo* at `argusAI/`, not a
separate checkout:

- `argusAI/event_similarity_processor_v2.py` — standalone worker. `main()` (line ~325) builds
  an `EventSimilarityProcessorV2` and calls `process_unprocessed_events()` (line 165), an
  infinite loop: read a batch from the queue (`_process_batch`, line 189, `LIMIT 100`),
  process each (`_process_single_event`, line 233), sleep `SLEEP_INTERVAL` when idle.
- `argusAI/utils/scylla_connection.py` — `ScyllaConnection` wraps a cassandra-driver
  `Cluster`/`Session` built from `Config.load_yaml_config()` (`SCYLLA_*` keys), with a prepared
  statement cache (`execute()`, line 55).
- `argusAI/utils/event_message_sanitizer.py` — `MessageSanitizer` strips IPs, URLs, file
  paths, UUIDs, timestamps, memory addresses. Used before embedding.
- `argusAI/deployment/argusai_event_similarity_processor.service` — systemd unit
  (`User=argus`, `WorkingDirectory=/home/argus/argusAI`, `PYTHONPATH=.`, `uv run`).
- `argusAI/README.md` — documents the queue → process → store → cleanup flow.

**The event queue & models:**

- `argus/backend/plugins/sct/testrun.py:79` — `SCTEvent` model (`sct_event`). PK =
  `(run_id, severity)` partition + `ts` clustering (ASC). Fields incl. `event_id`,
  `event_type`, `message` (required), `duplicate_id`.
- `argus/backend/plugins/sct/testrun.py:108` — `SCTUnprocessedEvent` (`sct_unprocessed_events`).
  PK = `run_id` partition, then `severity` (clustering ASC) + `ts` (clustering DESC) — note
  `severity` is a *clustering* key here, unlike in `SCTEvent` where it is a partition key. This
  is the embedding queue.
- `argus/backend/models/argus_ai.py` — embedding models incl. the custom `Vector` column
  type (line 34) and `SCTErrorEventEmbedding` / `SCTCriticalEventEmbedding` (keyspace
  `argus_tablets`), each with a `_sync_additional_rules` classmethod that creates a vector
  index. **This is the natural home for a new summary model.**

**Enqueue point:**

- `argus/backend/plugins/sct/service.py:478` — `SCTService.submit_event(run_id, raw_event)`.
  At line ~514 it constructs an `SCTUnprocessedEvent` and saves it for ERROR/CRITICAL events.
  **A summary-queue enqueue belongs right next to this.**

**Serving path:**

- `argus/backend/plugins/sct/service.py:528` —
  `SCTService.get_events(run_id, limit, severities, before, after)` returns `list[dict]`.
- `argus/backend/plugins/sct/controller.py:168` `GET /<run_id>/events/get` (and
  `/<run_id>/events/<severity>/get` at line 182).
- `argus/backend/plugins/sct/service.py:649` `get_similar_events_realtime` +
  controller `POST /<run_id>/event/similar` (line 306) — existing realtime ANN pattern to
  mirror for any on-demand fetch.

**Frontend:**

- `frontend/TestRun/SCT/SctEvents.svelte` — list + filtering. TS `SCTEvent` interface.
- `frontend/TestRun/SCT/SctEvent.svelte` — single event. `MESSAGE_CUTOFF = 600` (line 30),
  `sliceMessage()` (line 39), `let fullMessage = $state(false)` (line 159) with its toggle
  button at line 366. The summary toggle reuses this exact `$state` pattern.

**CLI (Go):**

- `cli/cmd/testrun.go:457` `activityCmd` (`argus run activity`). **`argus run events` is a real
  command** — `runEventsCmd` defined at `cli/cmd/run_nemeses_events.go:177` and registered at
  line 482; output goes through a structured `out.Write(models.SCTEventsResponse{...})` (~:250).
  The Go `SCTEvent` struct is in `cli/internal/models/runs.go:198`. Event helpers
  (`filterEvents`, `deduplicateEvents`) are in `run_nemeses_events.go`.

**Config & deps:**

- Config: the **backend** reads `current_app.config.get("KEY")` (Flask); the **worker** has no
  app context and reads the plain dict from `Config.load_yaml_config()` directly (as
  `scylla_connection.py` does). `load_yaml_config()` **caches** the parsed YAML in a class
  attribute and does not re-read the file on subsequent calls. Example file
  `argus_web.example.yaml` (incl. `ZEUS_*`).
- **No** existing OpenAI/LLM dependency anywhere in Python or Go (`grep` confirmed). `openai`
  is not in `pyproject.toml`. argusAI has no own `pyproject.toml`; it uses the root one.

## 3. Goals

1. **Best-effort:** each new event in the configured severity set (default ERROR/CRITICAL) is
   *attempted* once and gets a stored row in a dedicated table — either a summary (`status=ok`)
   or a `status=failed` marker — within the worker's normal processing lag (target: same order
   as embeddings, ≤ a few minutes under normal queue depth). The model is config-driven and
   replaceable in production without a code change. Failures are never retried; dropping some
   is acceptable — the goal is maximum coverage, not 100%.
2. `SCTService.get_events(...)` attaches a `summary` field (string) to each event dict, or
   `null` when no summary exists — **never raising** on missing summaries.
3. The frontend shows the summary by default for events that have one, with a control to
   reveal the original full message; events without a summary render exactly as today.
4. The CLI (`argus run events`) shows the summary by default with a `--full`/`--raw` flag to
   print the original message.
5. Summarization is fully decoupled: if the OpenAI key is absent or the worker is down, event
   ingestion, embedding, serving, UI, and CLI all continue to work with original text
   (acceptance criterion: "fail silently, show original").
6. Embedding generation is byte-for-byte unchanged (no summarization in the embedding path).

## 4. Implementation Phases

Ordered by dependency: storage → producer (worker) → serving → UI → CLI. Each phase is one PR,
≤200 changed LOC.

### Phase 1 — Storage & queue models — **Critical**

Add the persistence layer and the dedicated summarization queue.

**New `SctEventSummary` table** in `argus/backend/models/argus_ai.py`. Design (recommended,
pending sync — see Open Question 2):

- **Primary key mirrors `SCTEvent`'s identity** so summaries attach with a partition read,
  not an N+1: partition key `(run_id, severity)` + clustering `ts` — exactly the shape of
  `SCTEvent` (`run_id`+`severity` are both partition keys there, `ts` clusters). `get_events`
  already reads per-`(run_id, severity)` partition, so it can pull all summaries for the same
  partition in one query.
- **`event_id` stored as a column** (the `SCTEvent.event_id` UUID) so every summary carries an
  explicit, stable reference back to the canonical event — for debugging, the API payload, and
  any future "fetch original by event_id" path. We do **not** key the table by `event_id`
  alone: it is only a secondary index on `SCTEvent`, so keying by it would force per-event
  lookups when serving a run's event list.
- Other fields: `summary` (Text — null/empty on failure), `model` (Text — records *which*
  model produced this summary, so we can compare models tested in production),
  `status` (Text — `ok` | `failed`), `error` (Text — short failure reason, optional),
  `created_at` (DateTime), `source_length` (Int — original message length, for evaluating
  coverage/cost).
- **Best-effort, at-least-once (idempotent).** A row is written per event — `status=ok` with
  the summary, or `status=failed` on any error — then the queue entry is deleted. We never
  *deliberately* retry, but because the row's PK is the event identity, a re-attempt after a
  crash between INSERT and DELETE just upserts the same row. We accept dropping events; the goal
  is "as many as possible," not "all." A failed row is the durable "we tried, it failed, don't
  touch again" record.
- Keyspace: `argus_tablets` (with the embedding tables) vs. default — Open Question 3. **Note:**
  placing `SctEventSummary` in `argus_ai.py` keeps it with the AI models and lets its
  `_sync_additional_rules` run; a non-vector summary table needs no special index, so this is fine.

**Schema registration (this is the actual wiring — easy to miss):** tables are created only by
the manual `flask sync-models` command, which iterates `USED_MODELS` (`argus/backend/models/web.py:400`,
where the embedding models are already listed) and each plugin's `all_models`
(`argus/backend/plugins/sct/plugin.py:23`). Therefore:
- Add `SctEventSummary` to `USED_MODELS` in `models/web.py`.
- Add `SctUnsummarizedEvent` to the SCT plugin's `all_models` in `plugins/sct/plugin.py` (it
  lives with the other `sct_*` models).
- A model not in one of these lists is **silently never created**. Production tables don't
  exist until an operator runs `flask sync-models`.

**New `SctUnsummarizedEvent` queue** (`sct_unsummarized_events`), structurally identical to
`SCTUnprocessedEvent`. **Separate queue, not shared** — the similarity worker DELETEs from
`sct_unprocessed_events` as it drains it, so a shared queue would race: whichever worker
deletes first starves the other.

**Enqueue in `SCTService.submit_event`** (`argus/backend/plugins/sct/service.py:~514`),
beside the existing `SCTUnprocessedEvent` save, but gated on **configurable severities**
(`EVENT_SUMMARIZATION_SEVERITIES`, default `[ERROR, CRITICAL]`) — independent from the
embedding queue's gating, so the two can monitor different severity sets. Optionally also gate
on a configurable minimum length (`EVENT_SUMMARIZATION_MIN_LENGTH`) so short, already-concise
events are skipped — this is the "only summarize long events" lever (see Open Question 1).
Sentinel semantics: **`-1` = unlimited** (no length gate, summarize every monitored event);
a value `> 0` = only events whose message length ≥ that value; `0` is a degenerate "min length
0" that also matches everything (makes no real sense, accepted but pointless). Default `-1`
(maximum coverage — "do as much as possible"); raise it to restrict to long events for cost.

**Definition of Done:**
- [ ] `SctEventSummary` (with `event_id` column) defined in `argus_ai.py` and added to
      `USED_MODELS`; `SctUnsummarizedEvent` defined and added to the SCT plugin's `all_models`.
- [ ] `flask sync-models` creates both new tables on a local ScyllaDB.
- [ ] `submit_event` enqueues based on the configured severity set (default ERROR/CRITICAL)
      and the optional min-length gate.
- [ ] Existing `SCTUnprocessedEvent` (embedding) enqueue is untouched and still fires.

### Phase 2 — Summarization worker in `argusAI/` — **Critical**

The core deliverable, mirroring `event_similarity_processor_v2.py`.

- New `argusAI/event_summarization_processor.py`: a class (e.g. `EventSummarizationProcessor`)
  with the same shape as the v2 processor — `__init__(stop_event)`, `process_*` loop,
  `_process_batch(LIMIT 100)`, `_process_single_event(run_id, severity, ts)`, `shutdown()`,
  `main()` using `setup_application_logging`.
- **DB access is raw CQL via `ScyllaConnection.execute()` — NOT CQLEngine.** Critical: the
  worker process never calls `cqlengine.connection.setup()` (only the Flask backend does, in
  `argus/backend/db.py`). The v2 embedding worker reads/writes with raw CQL strings via
  `self.db.execute(...)` (INSERT at `event_similarity_processor_v2.py:297`, DELETEs at 162/226/312).
  Calling `SctEventSummary(...).save()` or `.objects` in this process would raise
  `connection 'default' doesn't exist`. So the worker must `INSERT`/`SELECT`/`DELETE` the new
  tables with raw CQL, exactly like the embedding worker. The CQLEngine `SctEventSummary` model
  exists only to (a) define + sync the schema and (b) back the **backend** read path (Phase 3).
- Per-chunk flow (**best-effort, at-least-once, no retries**): the worker reads queue rows,
  loads + sanitizes each event message (raw CQL), groups eligible events into **chunks**, and
  makes **one model call per chunk** (see "Batching" below). For each event in the chunk that
  came back with a summary → `INSERT` a row (`status=ok`, model name); for events the model
  omitted, or on a whole-chunk failure → `INSERT` a `status=failed` row (+ short `error`); then
  `DELETE` all the chunk's `sct_unsummarized_events` rows. The PK is the event's identity, so a
  re-attempt (e.g. process crash between INSERT and DELETE — same window the embedding worker
  has) simply **upserts/overwrites** the prior row; effectively idempotent. We never
  *deliberately* retry; dropping some is acceptable. Throughput-maximizing, not exhaustive.
- **Model must be easily replaceable in production (A/B testing).** Wrap the LLM call behind a
  thin `Summarizer` abstraction (small module under `argusAI/utils/`) so the concrete model —
  and even provider — is a config value, not a code change:
  - `OPENAI_SUMMARY_MODEL` (the model id) is re-read **fresh from the YAML file at the start of
    each batch**. Caveat: `Config.load_yaml_config()` caches the parsed YAML in a class
    attribute (`config.py`) and will *not* re-read the file, so the worker must bypass that
    cache — either add a `force`/`reload` path to `Config` or `yaml.safe_load` the resolved
    config path directly each batch. Without this, a model swap needs a worker restart. Pick
    one explicitly; do not assume `load_yaml_config()` re-reads.
  - The prompt lives in config too (`EVENT_SUMMARIZATION_PROMPT`) or a single editable
    constant, so prompt iteration is equally cheap.
  - Each summary row stores the `model` that produced it, so summaries from different models
    are distinguishable when comparing results in production.
  - The abstraction is **batch-shaped**: `summarize_batch(model, prompt, items) -> {index:
    summary}` where `items` is a list of `(index, sanitized_text)`. An OpenAI implementation
    ships first, but the seam means a different provider is a new impl, not a rewrite.
- **Config in the worker is read via `Config.load_yaml_config()` (plain dict), NOT
  `current_app.config`** — there is no Flask app context in the worker (the v2 worker reads
  `config["SCYLLA_*"]` this way in `scylla_connection.py`).
- If key/flag is absent, the worker logs and idles (no crash); the queue is left intact.
- Add `openai` to root `pyproject.toml` dependencies.
- New systemd unit `argusAI/deployment/argusai_event_summarization_processor.service`. Note: the
  existing similarity unit runs the **v1** file and references a non-existent
  `argusAI/pyproject.toml` — do not blind-copy it. Decide the runtime (root pyproject) and point
  the new unit at `event_summarization_processor.py` deliberately.
- Add config keys to `argus_web.example.yaml`: `OPENAI_API_KEY`, `OPENAI_SUMMARY_MODEL`
  (default a small model, e.g. `gpt-5-mini` — exact choice TBD by production eval),
  `EVENT_SUMMARIZATION_ENABLED`, `EVENT_SUMMARIZATION_SEVERITIES` (default `[ERROR, CRITICAL]`),
  `EVENT_SUMMARIZATION_MIN_LENGTH`, `EVENT_SUMMARIZATION_PROMPT`,
  `EVENT_SUMMARIZATION_BATCH_SIZE` (default 20), `EVENT_SUMMARIZATION_BATCH_MAX_CHARS`.

#### Batching (one model call summarizes up to N events)

The model call is the slow, costly step (the embedding call was on-device and fast; OpenAI is a
network round-trip of ~seconds). So we summarize **many events per request**, getting back one
independent summary per event. Per-event *storage and display* are unchanged — only the API call
is batched.

- **Chunking.** `_process_batch` fetches up to `FETCH_LIMIT` (keep 100) queue rows, loads +
  sanitizes + min-length-filters each, then splits the eligible events into chunks where each
  chunk holds **≤ `EVENT_SUMMARIZATION_BATCH_SIZE` events (default 20)** *and*
  **≤ `EVENT_SUMMARIZATION_BATCH_MAX_CHARS` total input** (a token-budget guard — 20 × multi-KB
  stack traces would otherwise blow the context window and slow the call).
  - This is exactly the "first one is ONE request, the rest batch" behavior, for free: when
    events trickle in one at a time the queue holds 1 row → a 1-event chunk → a single request;
    once a backlog builds, chunks fill to 20. No special first-event logic.
  - A single event that alone exceeds `BATCH_MAX_CHARS` becomes its own chunk, with its input
    truncated to the cap before sending. This is the genuine "must be one request" case.
- **The request — Structured Outputs.** Build one prompt containing the chunk's messages, each
  tagged with a small integer `index` (1..N, *not* the UUID — saves tokens and avoids the model
  mangling it). Constrain the response with an OpenAI JSON schema
  (`response_format`): `{ "summaries": [ { "index": int, "summary": string } ] }`, instructing
  "summarize each event independently; return exactly one summary per index." Keep a local
  `index -> (run_id, severity, ts)` map to write results back.
- **Mapping back & partial failure.** Indices present in the response → `status=ok`. Indices the
  model omitted, or a chunk whose call/parse failed entirely → `status=failed`. Either way every
  queue row in the chunk is deleted. Blast radius of one failed call is now up to `BATCH_SIZE`
  events instead of 1 — an accepted trade for best-effort; an *optional* one-time "split the
  failed chunk in half and retry" can be added later, default off.
- **Trickle vs. backlog (latency knob, optional).** Under a slow trickle the worker still sends
  1-event requests every cycle (fine, lowest latency). If we'd rather raise batch fill under
  light load, an optional "linger" (wait up to T ms / until K events queued before flushing)
  trades first-summary latency for fewer requests. Default: no linger — process what's there.

**Definition of Done:**
- [ ] Worker persists summary rows via **raw CQL** (`ScyllaConnection.execute`), not CQLEngine
      `.save()`, and the end-to-end flow works against a local DB + a real/mocked OpenAI call.
- [ ] Changing `OPENAI_SUMMARY_MODEL` in config changes the model used on the next batch
      (via a cache-bypassing reload) without a code change; the new model name is recorded on
      produced rows. If the reload path is descoped, the DoD is "after a worker restart."
- [ ] Missing API key / disabled flag → worker idles, does not crash, queue is left intact.
- [ ] Per-event errors write a `status=failed` row, dequeue, and never reprocess; the loop
      keeps running.
- [ ] Events are summarized in chunks of ≤ `BATCH_SIZE` (default 20) and ≤ `BATCH_MAX_CHARS`
      per model call; the response maps back one summary per event by index; omitted indices
      and whole-chunk failures are written `status=failed`. A 1-event queue produces a 1-event
      request.
- [ ] `openai` dependency added; `uv sync` succeeds; `uv run ruff check` is clean.

### Phase 3 — Backend serving (attach summary, fail silently) — **Important**

- Extend `SCTService.get_events` (`service.py:528`). It returns raw driver-row dicts
  (`SELECT * ...`), so attaching means: read the matching `SctEventSummary` rows, build a
  `(severity, ts) -> summary` map (one query per `(run_id, severity)` partition the result spans
  — not per event), then add a `summary` key to each event dict. Only `status=ok` rows surface a
  summary; **missing _or_ `status=failed` → `summary: null`**, never an exception. The client
  can't distinguish "not yet processed" from "permanently failed" — both correctly fall back to
  the original message.
- Keep `message` (original) in the payload unchanged so the client can always show the full
  text. No new endpoint required for v1 (summary travels with the event); a dedicated
  `GET …/event/<id>/full` is a documented fallback option only if payload size becomes a concern.

**Definition of Done:**
- [ ] `get_events` response objects include a `summary` key (string or null).
- [ ] Events without a summary return `summary: null` and original `message` intact.
- [ ] A lookup failure against the summary table degrades to `summary: null`, not a 500.
- [ ] Unit test covers: has-summary, no-summary, lookup-error paths.

### Phase 4 — Frontend display + toggle — **Important**

- Add `summary?: string | null` to the `SCTEvent` TS interface in
  `frontend/TestRun/SCT/SctEvents.svelte`.
- In `frontend/TestRun/SCT/SctEvent.svelte`, when `event.summary` is present, render it as the
  default body with a clear "summarized" affordance and a toggle ("show original") that reveals
  `event.message`. Reuse the existing `fullMessage` `$state` toggle pattern (line 366). When
  `summary` is null/empty, render exactly as today (no visual change).
- Keep copy-to-clipboard copying the **original** message.

**Definition of Done:**
- [ ] Events with a summary show it by default; toggle reveals the original.
- [ ] Events without a summary are visually identical to current behavior.
- [ ] `yarn build` succeeds; no new Rollup warnings; Svelte 5 rune patterns per AGENTS.md.

### Phase 5 — CLI display — **Important** (explicit requirement)

`argus run events` **must show event summaries by default, not full events**, with a `--full`
flag to print everything. This is a stated requirement, not optional polish.

- Add a `Summary` field (with JSON tag) to the Go `SCTEvent` struct
  (`cli/internal/models/runs.go:198`) so it deserializes the new API field.
- Output currently goes through `out.Write(models.SCTEventsResponse{...})`
  (`run_nemeses_events.go:~250`), a structured serializer. The default human/table rendering
  must choose `Summary` when present, original `Message` otherwise; `--full` (alias `--raw`)
  always renders `Message`. Decide the concrete outputter behavior (the struct serialization
  alone won't pick one) — likely a display-time field selection in the events command.
- An event with no summary (null / `status=failed`) falls back to its original message even in
  default mode, so default output is never blank.

**Definition of Done:**
- [ ] `argus run events` shows summaries by default; events lacking one show their original.
- [ ] `--full` (and `--raw` alias) prints the complete original messages.
- [ ] `go build ./...` and existing CLI tests pass.

## 5. Testing Requirements

- **Unit (pytest, `argus/backend/tests/`):**
  - `submit_event` enqueues both `SCTUnprocessedEvent` and `SctUnsummarizedEvent` for
    ERROR/CRITICAL, and neither for other severities.
  - `get_events` attaches `summary` correctly across has/no/error cases.
- **Unit (worker, `argusAI/tests/`):** mirror
  `argusAI/tests/test_event_similarity_processor_v2.py` — init, OpenAI client mocked,
  disabled/no-key idling, shutdown. **Batching specifically:** chunking respects `BATCH_SIZE`
  and `BATCH_MAX_CHARS`; a 1-event queue yields a 1-event call; the `index -> event` mapping is
  correct; an omitted index → `status=failed` for that event only; a whole-chunk failure →
  every event in the chunk `status=failed` and all queue rows deleted; an oversized single event
  becomes its own truncated chunk.
- **Integration (Docker ScyllaDB, marker `@pytest.mark.docker_required`):** extend the pattern
  in `argus/backend/tests/sct_events/test_event_embedding_integration.py` — submit ERROR event
  → row appears in `sct_unsummarized_events` → run one worker cycle (mocked OpenAI) →
  `SctEventSummary` written, queue row gone, `get_events` returns the summary.
- **Manual:** UI toggle on a real run; CLI `--full`; verify a run with summarization disabled
  shows originals everywhere with no errors.

## 6. Success Criteria

- All phase Definition-of-Done checklists complete.
- End-to-end: a freshly submitted ERROR/CRITICAL event acquires a stored summary via the
  worker, and that summary is visible in both UI and CLI with the original one toggle/flag away.
- Disabling summarization (no key / flag off / worker stopped) leaves the entire system
  functional on original text — demonstrated, not assumed.
- Embedding pipeline output is unchanged (diff of embedding code paths is empty).

## 7. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| OpenAI cost/rate limits at high event volume | Medium | High | A single `POST .../events/submit` enqueues an event **list** (`controller.py:214` runs `submit_event` per item), so a backlog builds fast. Mitigated by the **batching design** (≤20 events per call, char-budget capped) which cuts request count ~20× vs. per-event, plus a small model (`gpt-5-mini`) and input truncation. Further levers if still too high: positive `MIN_LENGTH` default (vs. `-1`), or a per-run digest as the most aggressive token cut. |
| Batched call has a larger failure blast radius (≤20 events lost per failed call) | Medium | Low | Accepted under best-effort; each failed event is recorded `status=failed` and the original message still shows. Optional half-split-retry of a failed chunk can be added later if loss is material. |
| Shared-queue race with the similarity worker | Medium | High | Dedicated `sct_unsummarized_events` queue (Phase 1); never reuse `sct_unprocessed_events`. |
| Summary table read becomes N+1 on event lists | Medium | Medium | Partition-scoped batch read in `get_events`; summaries share `run_id` partitioning with events. |
| OpenAI outage / latency stalls the worker | Medium | Low | Worker is fully decoupled; failures dequeue-and-continue; serving falls back to `null` → original. No user-facing impact. |
| Transient outage permanently marks a batch `failed` (write-once, no retry) | Medium | Low | **Accepted tradeoff** — best-effort by design: a failed event is never reprocessed and its summary is lost. If this proves too lossy in practice, a future opt-in retry/backfill pass can re-enqueue `status=failed` rows; not in scope for v1. |
| LLM summary drops the one detail a triager needed | Medium | Medium | Original message always retained and one toggle/flag away; summary is additive, never destructive. |
| Secret leakage (`OPENAI_API_KEY` in YAML) | Low | High | Follow existing `ZEUS_TOKEN`/`*_SECRET` config convention; never commit real keys; example file gets a placeholder only. |
| argusAI has no own `pyproject.toml` but the systemd unit references `--project argusAI/pyproject.toml` | Low | Low | Confirm dependency/runtime story during Phase 2 (root pyproject vs. add a minimal argusAI one); align the new unit with whatever the similarity unit actually uses in prod. |

## Open Questions & Evaluation

These are **not tracked in this file** — they live as copy-paste blocks for the PR description:

- **Open questions** (granularity / table keying / keyspace): `event-summarization-open-questions.pr.md`.
  Inline `Open Question 1/2/3` references above map to the numbered items in that block.
- **Token-usage & cost evaluation** (TBD, must be measured): `event-summarization-evaluation.pr.md`.
