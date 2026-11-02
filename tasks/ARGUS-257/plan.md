# ARGUS-257 — implementation plan

**Spec:** `tasks/ARGUS-257/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Standards: `docs/standards/backend/api.md`, `models.md`, `queries.md`,
  `migrations.md`, `global/error-handling.md`, `global/minimal-implementation.md`,
  `testing/test-writing.md`.
- Every import at module top. The lazy `import anthropic` in the summarizer
  goes: `anthropic` becomes a `web-backend` dependency.
- Moves go through `git mv` so the history follows the files.
- Backend tests create and read rows through the services or the API, never
  through a model call in the test body.
- No comment that justifies the change; fix only the comments the move makes
  wrong (`argusAI` paths, "standalone process", "worker").
- Timestamps: ScyllaDB keeps milliseconds and the driver returns naive UTC.
  The processor compares timestamps through one helper that makes them aware
  UTC and truncates them to milliseconds.

## Task 1 — Move argusAI into the SCT plugin

**Files:**
- Move: `argusAI/utils/event_message_sanitizer.py` → `argus/backend/plugins/sct/events/sanitizer.py`
- Move: `argusAI/utils/embedding.py` → `argus/backend/plugins/sct/events/embedding.py`
- Move: `argusAI/utils/summarizer.py`, `summary_metrics.py` → `argus/backend/plugins/sct/events/`
- Move: `argusAI/prompts/` → `argus/backend/plugins/sct/events/prompts/`
- Move: `argusAI/eval/` → `argus/backend/plugins/sct/events/eval/`
- Move: `argusAI/tests/test_embedding.py`, `test_summarizer.py` → `argus/backend/tests/sct_events/`
- Create: `argus/backend/plugins/sct/events/__init__.py` (empty)
- Modify: `pyproject.toml`, `uv.lock`, `.github/workflows/test.yml`

**Internals:**
- `MessageSanitizer.__init__()` loses `write_log` and the `logs/` file;
  `sanitize()` only transforms. `EventEmbedder.__init__()` loses `write_log`.
- `BgeSmallEnEmbeddingModel._download()` writes to `<archive>.<pid>.part` and
  `os.replace`s it onto the archive. `_extract_archive()` extracts into a
  `tempfile.mkdtemp(dir=DOWNLOAD_PATH)` and renames its `onnx/` onto the model
  directory; when another process got there first, it removes its copy.
  `_load()` sets `intra_op_num_threads = 1` and `inter_op_num_threads = 1`.
- `summary_metrics.start_metrics_server()` goes; the module docstring stops
  describing a standalone process.
- `eval/dedup.py`, `harness.py`, `judge.py`, `prompts.py` import the sibling
  modules. `eval/README.md` and `config.example.yaml` give the new
  `python -m argus.backend.plugins.sct.events.eval` invocation.
- `pyproject.toml`: `numpy`, `onnxruntime`, `tokenizers`, `anthropic`,
  `tiktoken` move to `web-backend`; the `ai` and `ai-eval` extras go.
  `test.yml` drops `--extra ai`.

- [x] Write the failing tests: two processes' worth of `_extract_archive()`
      calls into the same directory leave one intact model directory; a
      download that fails the SHA-256 leaves no archive behind.
- [x] Run them and confirm the failure.
- [x] Move the files, fix the imports, make the changes above, `uv lock`.
- [x] Run the moved embedding and summarizer tests and the eval import
      (`uv run python -m argus.backend.plugins.sct.events.eval --help`).
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Port the SCT event reads to coodie

**Files:**
- Modify: `argus/backend/plugins/sct/testrun.py` (`SCTTestRun.get_events_limited`)
- Modify: `argus/backend/plugins/sct/service.py` (`SCTService.get_similar_events_realtime`)
- Test: `argus/backend/tests/sct_events/test_sct_events.py`, `argus/backend/tests/sct_api/test_sct_api.py`

**Internals:**
- `get_events_limited()`: `SCTEvent.find(run_id=..., severity__in=...)`,
  `.filter(ts__lte=before)` / `.filter(ts__gte=after)` when given,
  `.per_partition_limit(n).all()`, then `model_dump()` of each, sorted by
  `ts`. The callers keep their dicts.
- `get_similar_events_realtime()`: `embedding_model.find().order_by_ann("embedding", query_embedding)
  .limit(limit + 1).only("run_id", "ts").all()`; attribute access on the rows;
  the `Config` keyspace lookup and both `execute_raw` imports go.

- [x] Write the failing test: two runs submit the same ERROR message through
      the API; `POST /{run_id}/event/similar` for one returns the other run
      (poll until the vector store indexes, as the conftest does).
- [ ] Run it and confirm the failure (no embedding until Task 5; the test
      lands red here and turns green there).
- [x] Port both reads. The existing `get_events_limited` tests stay green.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 3 — Async summary dispatcher

**Files:**
- Move: `argusAI/utils/summary_dispatcher.py` → `argus/backend/plugins/sct/events/summary_dispatcher.py`
- Move: `argusAI/tests/test_summary_dispatcher.py` → `argus/backend/tests/sct_events/`

**Internals:**
- `SummaryDispatcher(config: dict)`: same config keys, same `enabled`
  resolution, no `db` argument, no executor, no metrics port.
- `async summarize(events: list[UniqueEvent]) -> None`: `asyncio.gather` of
  `_summarize_one()` for each event.
- `_summarize_one()`: skips when disabled, empty or under `min_tokens`; drops
  and counts when `_pending >= max_backlog`; otherwise `_pending += 1`,
  `async with self._semaphore` (`EVENT_SUMMARIZATION_MAX_CONCURRENCY`),
  `await asyncio.to_thread(self._summarizer.summarize, ...)`, then
  `SCTEvent.find(run_id=, severity=, ts=).update(summary=...)`, metrics and
  log; `SummarizerError` and any other exception count as failed;
  `_pending -= 1` in `finally`.
- `UniqueEvent`: frozen dataclass `run_id, severity, ts, message`.

- [x] Rewrite the dispatcher tests for the async API with a fake summarizer
      and the real database: the summary lands on the event, disabled and
      keyless stay inert, an error leaves the summary null, the min-token
      gate, the backlog drop, the counters.
- [x] Run them and confirm the failure.
- [x] Rewrite the dispatcher.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 4 — Event processor and the queue column

**Files:**
- Create: `argus/backend/plugins/sct/events/processor.py`
- Modify: `argus/backend/plugins/sct/testrun.py` (`SCTUnprocessedEvent.queued_at`)
- Test: `argus/backend/tests/sct_events/test_event_processor.py`

**Internals:**
- `SCTUnprocessedEvent.queued_at: Optional[datetime] = None`.
- `QueuedEvent` frozen dataclass `run_id, severity, ts`.
- `EventProcessor(embedder: EventEmbedder, dispatcher: SummaryDispatcher)`;
  `_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="event-embedder")`;
  `_locks: WeakValueDictionary[UUID, asyncio.Lock]`.
- `async process(events)`: group by `run_id` in input order; per run, under
  its lock, `_process_one()` each event, catching and logging any exception
  per event; then `await dispatcher.summarize(unique)`.
- `_process_one(event) -> UniqueEvent | None`:
  `SCTEvent.find(run_id, severity, ts).only("message").first()`; missing or
  empty message → dequeue, `None`. Embed through
  `loop.run_in_executor(self._executor, embedder.embed, message, run_id)`;
  `ValueError` (empty after sanitizing) → dequeue, `None`; other errors
  propagate and keep the row. Read `model.find(run_id=).only("ts", "embedding").all()`
  for the severity's table; the first row with another `ts` and
  `cosine() < DUPLICATE_DISTANCE_THRESHOLD` is the match. Match with an
  event row → `SCTEvent.find(...).update(duplicate_id=match.event_id)`,
  dequeue, `None`. Otherwise `model(run_id=, ts=, embedding=vector.tolist()).save()`,
  dequeue, return the `UniqueEvent`.
- `async sweep(min_age: timedelta) -> int`: `SCTUnprocessedEvent.find().all()`,
  keep rows whose `queued_at` is null or older than now − `min_age`,
  `process()` them, return the count.
- `get_event_processor()`: `functools.cache`d; builds the dispatcher from
  `Config.load_yaml_config()`.

- [x] Write the failing tests with a deterministic stub model (a vector
      seeded from the SHA-256 of the sanitized text): ERROR and CRITICAL go
      to their tables; a repeated message in one run gets `duplicate_id` and
      no embedding; the same message in another run is unique; an empty
      message dequeues; a failing embedder keeps the row; the sweep takes a
      row without `queued_at` and an old one and skips a fresh one;
      reprocessing a stored event does not mark it a duplicate of itself.
- [x] Run them and confirm the failure.
- [x] Write the processor and the column.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 5 — Run the processor from the submit route

**Files:**
- Modify: `argus/backend/plugins/sct/service.py` (`submit_event`, `submit_events`)
- Modify: `argus/backend/plugins/sct/controller.py` (`sct_event_submit`)
- Modify: `argus/backend/tests/conftest.py`, `argus/backend/tests/sct_events/conftest.py`
- Delete: `argus/backend/tests/sct_events/test_event_embedding_integration.py`
- Test: `argus/backend/tests/sct_events/test_event_ingestion.py`, `test_sct_events.py`

**Internals:**
- `submit_event()` sets `queued_at` on the queue row and returns
  `tuple[CoredumpLink | None, QueuedEvent | None]`.
- `submit_events()` returns `list[QueuedEvent]`; it still raises the first
  failure after the coredump links are stored.
- `sct_event_submit(..., background_tasks: BackgroundTasks, ...)`:
  `background_tasks.add_task(get_event_processor().process, queued)`; the
  response stays `{"status": "ok", "response": true}`.
- The stub model fixture moves to the top-level backend `conftest.py`
  (session, autouse), because every ERROR or CRITICAL submit through the API
  now reaches the processor.

- [x] Write the failing tests through `api_client`: a submitted ERROR event
      has its embedding and no queue row after the response; a repeated
      message gets `duplicate_id`; WARNING events touch neither the queue nor
      the tables; the submit answers ok and the row stays when the stub model
      raises; with summarization enabled and a fake summarizer the event
      carries a summary. `test_get_events_includes_summary_field` gets its
      summary this way instead of a raw `UPDATE`.
- [x] Run them and confirm the failure.
- [x] Wire the route and the service.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 6 — The sweep command

**Files:**
- Modify: `argus/backend/cli.py`
- Test: `argus/backend/tests/sct_events/test_event_processor.py`

**Internals:**
- `process-event-queue` with `--min-age` (seconds, default 600):
  `asyncio.run(get_event_processor().sweep(timedelta(seconds=min_age)))`,
  echoes the count. The module docstring lists the command.

- [x] Write the failing test: `CliRunner` with `--min-age 0` processes a
      queued row (logging disabled, as the client suite does).
- [x] Run it and confirm the failure.
- [x] Add the command.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 7 — Remove the worker and its deployment hooks

**Files:**
- Delete: `argusAI/event_similarity_processor_v2.py`, `argusAI/utils/scylla_connection.py`,
  `argusAI/utils/__init__.py`, `argusAI/tests/test_event_similarity_processor_v2.py`,
  `argusAI/logs/`, `argusAI/README.md` (after Task 8 takes its content)
- Modify: `argus/backend/util/logsetup.py` (the `argusAI` logger)
- Modify: `scripts/release/build-bundle.sh` (copied tree, excludes, `argus-ai-worker` shim,
  `--extra ai`, verify block)
- Modify: `.github/workflows/release.yml` (smoke import, header comment)
- Modify: `argus_web.example.yaml` (summarization comment, metrics port)

- [x] `git grep -n argusAI` prints only task artifacts and archived plans.
- [ ] Build the bundle locally and run its verify block.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 8 — Docs

**Files:**
- Create: `argus/backend/plugins/sct/events/README.md` (from `argusAI/README.md`:
  the in-backend flow, the tables, the sweep command, the summary keys, the
  eval pointer)
- Modify: `docs/project/architecture.md`, `docs/project/tech-stack.md`,
  `docs/deployment.md`, `AGENTS.md`, `docs/INDEX.md` when an entry changes
- Modify: `argus/backend/plugins/sct/testrun.py` (the `summary` comment),
  `dev-db/seed_data.py` (docstring)

- [x] The docs describe one backend service, the timer, and no ArgusAI unit.
- [x] Commit, with the boxes of this task checked.

## Task 9 — Checks outside the suite

- [x] Parity: replay `eval/baseline/events.json` as one run through the old
      in-memory rule (from `git show master:argusAI/event_similarity_processor_v2.py`)
      and through `EventProcessor` with the real model; the `duplicate_id`
      assignments match. Scratch script, not committed.
- [ ] Dev stack: submit ERROR/CRITICAL events through the SCT client API,
      see embeddings, duplicates, the similar-events view and a summary;
      break the model path and see the submit still answer ok and the row
      stay; drain it with `argus-cli process-event-queue --min-age 0`.
- [x] Measure the worker start time and RSS with the model loaded.
- [ ] Draft the scylladb/qatools change: drop the ArgusAI unit from
      `roles/argus`, add the `process-event-queue` timer.
