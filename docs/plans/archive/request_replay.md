# Argus Request Replay

## Problem Statement

Argus can go down for various reasons — maintenance windows, infrastructure failures, bugs, database issues. Test results produced by SCT, DTest, driver-matrix-tests, and sirenada are expensive to generate (long-running tests on cloud infrastructure). When Argus is unavailable during a test run, all submitted data is permanently lost.

The current retry mechanism in the Python client (`urllib3.Retry` with `max_retries=3` and `backoff_factor=1`) only handles transient network blips. It cannot recover from extended Argus outages that may last minutes or hours during a multi-hour test run.

**Goal:** Build a replay system that captures every Argus API request in a machine-parseable format, always on by default, so that when Argus recovers, all failed submissions can be replayed to reconstruct the intended system state.

---

## 1. Current Implementation

### 1.1 Client Architecture

All Argus API communication flows through the `ArgusClient` base class in `argus/client/base.py`. Every HTTP request passes through exactly two methods:

- `get()` (line 116) — used for status checks, data retrieval
- `post()` (line 132) — used for all data submissions

This single chokepoint makes it straightforward to intercept all state-mutating requests.

**Current logging (DEBUG level):**

```python
# base.py line 143
LOGGER.debug("POST Request: %s, params: %s, body: %s", url, params, body)
# base.py line 151
LOGGER.debug("POST Response: %s %s", response.status_code, response.url)
```

These debug logs are human-readable but not machine-parseable. They lack structure, don't include all the fields needed for replay, and are mixed in with all other application logs.

**Retry configuration:**

```python
retry_strategy = Retry(
    total=max_retries,       # default: 3
    connect=max_retries,
    read=max_retries,
    status=0,                # no HTTP status retries
    backoff_factor=1,
    status_forcelist=(),     # empty — no status code triggers
    allowed_methods=["GET", "POST"],
)
```

This retries on connection failures and read timeouts only, not on HTTP error status codes. Once retries are exhausted, the exception propagates and data is lost.

### 1.2 Client Types

Four specialized clients extend `ArgusClient`, each with their own test type and routes:

| Client                    | File                                         | test_type              | Routes                                                                                                              |
| ------------------------- | -------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `ArgusSCTClient`          | `argus/client/sct/client.py`                 | `scylla-cluster-tests` | 24+ (packages, screenshots, resources, nemesis, events, junit, stress commands, config, email, performance, gemini) |
| `ArgusGenericClient`      | `argus/client/generic/client.py`             | `generic`              | 3 (submit_run, trigger_jobs, finalize)                                                                              |
| `ArgusDriverMatrixClient` | `argus/client/driver_matrix_tests/client.py` | `driver-matrix-tests`  | 3 (submit_driver_result, submit_driver_failure, submit_env)                                                         |
| `ArgusSirenadaClient`     | `argus/client/sirenada/client.py`            | `sirenada`             | 1 (submit_sirenada_run — does everything in one call)                                                               |

All clients inherit the same `get()` and `post()` methods, so the replay log integration happens once in the base class.

### 1.3 Usage in SCT (scylla-cluster-tests)

SCT is the largest consumer. Key integration points:

- **Client initialization:** `sdcm/utils/argus.py` — `get_argus_client()` creates an `ArgusSCTClient` with credentials from `KeyStore`
- **Result submission:** `sdcm/argus_results.py` — `submit_results_to_argus()` wraps `client.submit_results()` with error handling
- **Event pipeline:** `sdcm/sct_events/argus.py` — multi-threaded pipeline: `ArgusEventCollector` → `ArgusEventAggregator` → `ArgusEventPostman`
- **Error handling pattern:** All argus calls are wrapped in try/except that logs warnings but doesn't fail the test

The event pipeline is particularly relevant because it operates across multiple threads, making sequence ordering critical.

### 1.4 Usage in pytest-argus-reporter

The pytest plugin (`pytest-argus-reporter/pytest_argus_reporter.py`) uses `ArgusGenericClient` and supports configuration via command-line options:

- `--argus-run-id`
- `--argus-test-type`
- `--argus-api-key`
- `--argus-base-url`

### 1.5 SCT's Existing Self-Healing for Argus Failures

SCT has several mechanisms to handle argus failures. Understanding them is critical because the replay log should complement — not duplicate — these existing patterns.

#### 1.5.1 Graceful Degradation via MagicMock (Production Anti-Pattern)

When argus initialization fails, the client falls back to `unittest.mock.MagicMock` (`sdcm/test_config.py`). All subsequent argus calls silently succeed (no-op). The test continues without argus. This means **no data is captured at all** — it's pure graceful degradation with total data loss.

Using `unittest.mock.MagicMock` as a production fallback is an anti-pattern. It silently swallows every method call on every attribute chain, making it impossible to distinguish "argus is disabled" from "argus call has a bug." It also means the replay log never gets written because the real client was never instantiated.

**Proposed replacement:** If argus client initialization fails (network error, auth error, etc.), the client should either:

1. **Fail the test** — if the team decides argus data is mandatory, the test should not run without it. This is the safest option for preventing silent data loss.
2. **Switch to replay-only mode** — the `ArgusClient` is still instantiated with a valid `ReplayLog`, but all HTTP calls are skipped. The replay log records every intended request with `"success": false`. When argus recovers, the entire test run can be reconstructed from the JSONL file via `argus replay` or the server-side ingest endpoint (Section 7). This gives the same graceful degradation as MagicMock but with **zero data loss**.

The replay-only mode is implemented at the `ArgusClient` level — no changes needed in consumer projects. The client constructor accepts a `replay_only: bool` flag (or detects it from a failed health check), and `get()`/`post()` skip the HTTP call but still write to the replay log.

#### 1.5.2 Heartbeat Thread with Limited Retry

The heartbeat thread (`sdcm/tester.py:466-490`) implements a simple retry:

```python
fail_count = 0
while not stop_signal.is_set():
    if fail_count > 5:
        break                      # Give up after 5 consecutive failures
    try:
        client.sct_heartbeat()
        fail_count = 0             # Reset on success
    except Exception:
        fail_count += 1
    stop_signal.wait(timeout=30.0) # 30-second interval
```

After 5 consecutive failures (~2.5 minutes), the heartbeat thread exits permanently. No further heartbeats are sent for the rest of the test run.

#### 1.5.3 Event Pipeline — Fire-and-Forget

The three-stage event pipeline (`sdcm/sct_events/argus.py`) uses `verbose_suppress()` around every operation:

- **ArgusEventCollector** — extracts event data, skips on error
- **ArgusEventAggregator** — deduplicates within 90-second windows, skips on error
- **ArgusEventPostman** — calls `client.submit_event()`, suppresses on error

#### 1.5.4 Test Finalization — Combined with Status

The original `argus_finalize_test_run()` in `sdcm/tester.py:659-683` performed three operations in a single try/except: submit events (legacy), set status, and call finalize. If any call failed, the entire block was skipped.

**This is simplified as follows:**

- The legacy event submission step is removed (covered by the replay log).
- `finalize_run()` — which only set `end_time` — is removed from the client call path.
- When the backend receives a **terminal status** (`Failed`, `Aborted`, `Passed`, `Error`, `NotRun`) via `set_status`, it sets `end_time = now()` automatically **if `end_time` is not already set**.
- The client calls only `set_status(terminal_status)` as the final operation. No separate finalize call is needed.
- The `POST /client/testrun/:type/:id/finalize` endpoint remains on the backend for manual/forced finalization but is no longer part of the normal client flow.

#### 1.5.5 Node Operations — No Retry

All node-level argus operations (`_add_node_to_argus`, `update_shards_in_argus`, `_terminate_node_in_argus` in `sdcm/cluster.py`) catch exceptions and log them. No retry, no recovery. These calls are captured by the replay log and can be replayed after an outage.

#### 1.5.6 Summary of Gaps Addressed

| Data Type           | Previous Recovery                        | With Replay Log                               |
| ------------------- | ---------------------------------------- | --------------------------------------------- |
| Events (real-time)  | None — fire-and-forget                   | Captured in JSONL replay log                  |
| Events (batch)      | `argus_offline_collect_events`           | Replaced by replay log                        |
| Test run submission | None                                     | Captured in JSONL                             |
| Test status         | None                                     | Captured in JSONL                             |
| Results/performance | None                                     | Captured in JSONL                             |
| Resources (nodes)   | None                                     | Captured in JSONL                             |
| Packages            | None                                     | Captured in JSONL                             |
| Nemesis records     | None                                     | Captured in JSONL                             |
| Logs/screenshots    | None                                     | Captured in JSONL (links; actual files on S3) |
| JUnit reports       | None                                     | Captured in JSONL                             |
| Config              | None                                     | Captured in JSONL                             |
| Stress commands     | None                                     | Captured in JSONL                             |

---

## 2. Always-On JSONL Replay Log

### 2.1 Design Principles

This is **not** request logging for debugging. This is a **replay journal** of every API call that can be used to reconstruct Argus state from scratch.

1. **Always on by default** — we don't know when Argus will start failing, so every mutating request must be recorded
2. **Written after the HTTP call completes (or fails)** — each record is a single, complete JSONL line with the final outcome. If the process crashes mid-HTTP-call, that one record is lost — the same behavior as today, and not worth the complexity of a write-ahead approach since the server may or may not have processed the request anyway.
3. **One file per process per run** — timestamp in the filename prevents parallel processes from overwriting each other (see Section 2.2)
4. **Queue + writer thread** — request threads enqueue complete records onto a `queue.Queue`; a single background thread drains the queue and writes to disk. This eliminates file I/O contention from the request hot path entirely.

### 2.2 File Naming

```
{log_dir}/argus_replay_log_{run_id}_{unix_ms}.jsonl
```

- `run_id` scopes the file to one test run.
- `unix_ms` is Unix epoch time in milliseconds captured once at `ArgusClient.__init__()` time. This disambiguates parallel processes sharing the same `log_dir` and `run_id` (e.g. parallel pytest workers all reporting to the same run — each worker gets its own file).
- `log_dir` is the test's existing log directory, passed by each consumer at client construction time. There is no `ARGUS_LOG_DIR` env var or fallback — each test framework is responsible for providing its own log directory.

**Multiple files per run are expected and supported.** The CLI upload command and backend ingest endpoint both handle multiple JSONL files for the same `run_id` by merging and sorting records by `ts` before execution.

### 2.3 JSONL Record Schema

Each line in the file is a single, self-contained JSON object written **after** the HTTP call completes (or fails):

```json
{
  "ts": 1712345678901,
  "method": "POST",
  "endpoint": "/testrun/$type/$id/submit_results",
  "location_params": {"type": "scylla-cluster-tests", "id": "550e8400-e29b-41d4-a716-446655440000"},
  "params": null,
  "body": {
    "schema_version": "v8",
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Performance Results",
    "columns": [...],
    "results": [...]
  },
  "test_type": "scylla-cluster-tests",
  "success": true
}
```

On failure:

```json
{
  "ts": 1712345679100,
  "method": "POST",
  "endpoint": "/sct/$id/event/submit",
  "location_params": {"id": "550e8400-e29b-41d4-a716-446655440000"},
  "params": null,
  "body": { ... },
  "test_type": "scylla-cluster-tests",
  "success": false,
  "error": "ConnectionError: Connection refused"
}
```

One line per request — no pre-call/post-call pairs, no merging needed.

**Field descriptions:**

| Field             | Type              | Description                                                                                                                 |
| ----------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `ts`              | int               | Unix epoch milliseconds at record write time. Used for ordering during replay.                                              |
| `method`          | string            | HTTP method: always `"POST"` (only mutating calls are recorded).                                                            |
| `endpoint`        | string            | Route template with `$` placeholders (e.g. `/testrun/$type/$id/submit_results`). Enables replay against any Argus instance. |
| `location_params` | object\|null      | Parameters to resolve the endpoint template into a full path.                                                               |
| `params`          | object\|null      | URL query parameters.                                                                                                       |
| `body`            | object\|null      | Full request body as sent to the API.                                                                                       |
| `test_type`       | string            | The client's test type (redundant with body but useful for filtering).                                                      |
| `success`         | bool              | `true` if HTTP 2xx and response body has no `"error"` key. `false` otherwise.                                               |
| `error`           | string (optional) | Present only when `success` is `false`. Human-readable error description.                                                   |

**What is NOT stored (by design):**

- Auth token — tokens are per-user and may rotate; reconstructed at replay time
- HTTP response body — not needed for replay
- `schema_version` as a separate field — already embedded in every `body`

### 2.4 Why "Failed Only" Replay is Unsafe

A record with `"success": false` does not mean the server-side operation failed. The server may have completed the write and prepared a response, but the connection dropped before the client received it. Additionally, a backend serialization bug (e.g. missing JSON serializer) can cause the response to fail even though the service function completed successfully.

Therefore: **the replay system does not filter by `success` field.** All records are uploaded. The server applies idempotency classification (Section 6) to handle duplicates — SAFE endpoints are last-write-wins, CHECK_FIRST endpoints verify existence before creating, and APPEND endpoints rely on natural deduplication (matching on payload content). This correctly handles both "actually failed" and "client thought it failed but server succeeded" cases.

### 2.5 ReplayLog Implementation

The `ReplayLog` uses a context manager API and a background writer thread. Request threads build the record in memory, execute the HTTP call, set the outcome, and enqueue the complete record. A single background thread drains the queue and writes to disk.

```python
import atexit
import json
import queue
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class ReplayRecord:
    """Mutable record populated during the HTTP call, written after completion."""
    __slots__ = ("ts", "method", "endpoint",
                 "location_params", "params", "body", "test_type",
                 "success", "error")

    def __init__(self, *, method: str, endpoint: str,
                 location_params: dict | None, params: dict | None,
                 body: dict | None, test_type: str):
        self.ts = int(time.time() * 1000)
        self.method = method
        self.endpoint = endpoint
        self.location_params = location_params
        self.params = params
        self.body = body
        self.test_type = test_type
        self.success: bool = False
        self.error: str | None = None

    def to_dict(self) -> dict:
        d = {
            "ts": self.ts,
            "method": self.method,
            "endpoint": self.endpoint,
            "location_params": self.location_params,
            "params": self.params,
            "body": self.body,
            "test_type": self.test_type,
            "success": self.success,
        }
        if self.error:
            d["error"] = self.error
        return d


_SENTINEL = object()


class ReplayLog:
    def __init__(self, log_dir: str, run_id: str, test_type: str, init_ts_ms: int):
        self._path = Path(log_dir) / f"argus_replay_log_{run_id}_{init_ts_ms}.jsonl"
        self._test_type = test_type
        self._queue: queue.Queue = queue.Queue()
        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name="replay-log-writer",
        )
        self._writer_thread.start()
        atexit.register(self.close)

    def _writer_loop(self):
        """Background thread: drain queue, write JSONL lines to disk."""
        with open(self._path, "a") as f:
            while True:
                item = self._queue.get()
                if item is _SENTINEL:
                    break
                f.write(json.dumps(item, default=str) + "\n")
                f.flush()

    @contextmanager
    def record(self, method: str, endpoint: str, location_params: dict | None,
               params: dict | None, body: dict | None):
        """Context manager: yields a ReplayRecord, enqueues it on exit."""
        rec = ReplayRecord(
            method=method,
            endpoint=endpoint,
            location_params=location_params,
            params=params,
            body=body,
            test_type=self._test_type,
        )
        try:
            yield rec
        except Exception as exc:
            rec.success = False
            rec.error = str(exc)
            raise
        finally:
            self._queue.put(rec.to_dict())

    def close(self):
        """Signal the writer thread to flush and exit."""
        self._queue.put(_SENTINEL)
        self._writer_thread.join(timeout=5.0)
```

**Key design choices:**

- **`queue.Queue` + writer thread** — request threads never touch the file. The writer thread is the sole consumer, so no file locking is needed.
- **`daemon=True`** — the writer thread won't prevent process exit. `atexit` + `close()` ensures a clean drain on normal shutdown. On hard kills (`SIGKILL`), in-flight queue items are lost — acceptable since those records were from requests that just completed (the data is either already on the server or genuinely lost).
- **Context manager** — the record is built before the HTTP call (in memory only), the caller executes the request inside the `with` block, and the final record is enqueued on `__exit__` regardless of success or failure.
- **Ordering by `ts`** — records are sorted by timestamp during replay. In multithreaded environments, two requests within the same millisecond may have identical `ts` values, but since all endpoints are idempotent, replay order between same-ms records does not affect correctness.

### 2.6 Integration into ArgusClient

The replay log is initialized in `ArgusClient.__init__()` and used via context manager in `post()`:

```python
class ArgusClient:
    def __init__(self, auth_token, base_url, ..., log_dir: str):
        # ... existing init code ...
        init_ts_ms = int(time.time() * 1000)
        self._replay_log = ReplayLog(
            log_dir=log_dir,
            run_id=getattr(self, "run_id", "unknown"),
            test_type=getattr(self, "test_type", "unknown"),
            init_ts_ms=init_ts_ms,
        )

    def post(self, endpoint, location_params=None, params=None, body=None):
        url = self.get_url_for_endpoint(endpoint=endpoint, location_params=location_params)
        LOGGER.debug("POST Request: %s, params: %s, body: %s", url, params, body)

        with self._replay_log.record("POST", endpoint, location_params, params, body) as rec:
            response = self.session.post(url=url, params=params, json=body,
                                          headers=self.request_headers, timeout=self._timeout)
            LOGGER.debug("POST Response: %s %s", response.status_code, response.url)
            success = 199 < response.status_code < 300
            if success:
                try:
                    success = "error" not in response.json()
                except Exception:
                    success = False
            rec.success = success

        return response
```

Only `post()` is recorded — `get()` calls are read-only and do not mutate state.

---

## 3. Log Storage Strategy

### 3.1 Storage Location

The JSONL replay file is written to the **test's existing log directory**. Each consumer passes its log directory at client construction time. There is no separate env var or fallback — the replay log is co-located with other test artifacts.

- For SCT: `~/sct-results/latest/`

### 3.2 Multiple Files per Run

Because the filename includes `init_ts_ms`, parallel processes using the same `log_dir` and `run_id` each write to their own file:

```
argus_replay_log_550e8400-..._1712345600000.jsonl   ← worker 0
argus_replay_log_550e8400-..._1712345600042.jsonl   ← worker 1
argus_replay_log_550e8400-..._1712345600107.jsonl   ← worker 2
```

The CLI upload command and backend ingest endpoint accept all files matching `argus_replay_log_{run_id}_*.jsonl` and merge their records by `ts` before processing.

### 3.3 Convention

1. File naming: `argus_replay_log_{run_id}_{unix_ms}.jsonl`
2. The file is co-located with other test artifacts; no new upload mechanism is needed.
3. For `pytest-argus-reporter`: add `--argus-log-dir` command-line option that passes through to `ArgusGenericClient`.

---

## 4. Backend — Terminal Status Auto-Finalize

When `set_status` receives a terminal status (`Failed`, `Aborted`, `Passed`, `Error`, `NotRun`):

- The backend sets `end_time = now()` **if `end_time` is not already set**.
- No separate `finalize` call is needed from the client.
- The `POST /client/testrun/:type/:id/finalize` endpoint remains on the backend for manual or forced finalization but is removed from the normal client flow.

This simplifies finalization from a two-step sequence (`set_status` → `finalize`) to a single call.

---

## 5. `argus replay` CLI Command

The `argus replay` CLI command collects all matching JSONL files, bundles them into a `tar.zst` archive, and uploads the archive to the Argus server-side ingest endpoint. All replay logic — ordering, idempotency, execution — runs on the server.

### 5.1 Command Interface

```
argus replay [flags]

Flags:
  --dir <path>         Directory to scan for argus_replay_log_*.jsonl files
  --run-id <uuid>      Filter files by run ID (used with --dir)
  --file <path>        Explicit file path (repeatable; mutually exclusive with --dir)
  --dry-run            Validate on the server without executing
  --target-url         Override the base URL (replay against a different Argus instance)
  --report             Output format for summary: "text" (default) or "json"
```

**Examples:**

```bash
# Replay all files for a specific run in the SCT results directory
argus replay --dir ~/sct-results/latest --run-id 550e8400-e29b-41d4-a716-446655440000

# Replay explicit files
argus replay --file argus_replay_log_550e8400-..._1712345600000.jsonl \
             --file argus_replay_log_550e8400-..._1712345600042.jsonl

# Dry-run to preview what would be replayed
argus replay --dir ~/sct-results/latest --run-id 550e8400-... --dry-run

# Replay against a different Argus instance
argus replay --dir ~/sct-results/latest --target-url https://argus-staging.example.com
```

### 5.2 Upload Format

All collected JSONL files are bundled into a **`tar.zst` archive** and uploaded as a single POST:

- Uses `archive/tar` + `github.com/klauspost/compress/zstd` — both already in `go.mod`
- `Content-Type: application/x-tar-zstd`
- Single round-trip; server handles decompression, merging, and ordering

The archive contains one entry per JSONL file, preserving original filenames so the server can associate files with their `run_id` via the filename convention.

### 5.3 No `--failed-only` Flag

There is no `--failed-only` flag. All records are uploaded unconditionally. The server handles idempotency per endpoint classification (Section 6). See Section 2.4 for the rationale.

The CLI implementation details (package structure, command wiring) are handled in the CLI repository separately.

---

## 6. Endpoint Idempotency Classification

Each API endpoint is classified into one of three replay strategies. The server-side ingest service uses this classification when processing each JSONL entry.

### 6.1 SAFE — Replay Freely

These endpoints are idempotent or last-write-wins. Replaying them multiple times produces the same result.

| Endpoint                                    | Client Methods                                                                                                    |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `/testrun/$type/$id/set_status`             | `set_status()`, `set_sct_run_status()`, `set_matrix_status()`                                                     |
| `/testrun/$type/$id/update_product_version` | `update_product_version()`, `update_scylla_version()`                                                             |
| `/testrun/$type/submit`                     | `submit_run()`, `submit_sct_run()`, `submit_generic_run()`, `submit_driver_matrix_run()`, `submit_sirenada_run()` |
| `/sct/$id/sct_runner/set`                   | `set_sct_runner()`                                                                                                |
| `/testrun/$type/$id/logs/submit`            | `submit_logs()`, `submit_sct_logs()`                                                                              |
| `/sct/$id/screenshots/submit`               | `submit_screenshots()`                                                                                            |
| `/sct/$id/packages/submit`                  | `submit_packages()`                                                                                               |
| `/sct/$id/resource/create`                  | `create_resource()` — deduplicates by resource name                                                               |
| `/sct/$id/resource/$name/update`            | `update_resource()`                                                                                               |
| `/sct/$id/resource/$name/shards`            | `update_shards_for_resource()`                                                                                    |
| `/$id/config/submit`                        | `sct_submit_config()`                                                                                             |
| `/driver_matrix/env/submit`                 | `submit_env()`                                                                                                    |
| `/testrun/$type/$id/submit_results`         | `submit_results()` — keyed by table name, overwrites                                                              |

> **Note:** For heartbeat calls (`/testrun/$type/$id/heartbeat`), only the **last** heartbeat record is replayed. This sets the heartbeat timestamp to the expected final value without replaying every intermediate heartbeat (which would serve no purpose after the test has finished).

> **Sirenada bug:** `submit_sirenada_run` (`argus/backend/plugins/sirenada/model.py`) appends to `run.results` without dedup when the run already exists — replaying it duplicates results. The other list fields (`sirenada_test_ids`, `browsers`, `clusters`, `s3_folder_ids`) already have `not in` guards. Fix: add the same `not in` guard to `results` before appending. This should be done as a prerequisite in Phase 2.

### 6.2 APPEND — Naturally Idempotent

These endpoints append records. The backend endpoints are inherently idempotent — duplicate submissions with identical payloads are handled gracefully (either ignored or produce the same result).

| Endpoint                       | Client Methods                 |
| ------------------------------ | ------------------------------ |
| `/sct/$id/event/submit`        | `submit_event()`               |
| `/sct/$id/nemesis/submit`      | `submit_nemesis()`             |
| `/sct/$id/nemesis/finalize`    | `finalize_nemesis()`           |
| `/driver_matrix/result/submit` | `submit_driver_result()`       |
| `/driver_matrix/result/fail`   | `submit_driver_failure()`      |
| `/sct/$id/stress_cmd/submit`   | `add_stress_command()`         |
| `/sct/$id/junit/submit`        | `sct_submit_junit_report()`    |
| `/sct/$id/gemini/submit`       | `submit_gemini_results()`      |
| `/sct/$id/performance/submit`  | `submit_performance_results()` |

### 6.3 SKIP — Do Not Replay

These endpoints have side effects beyond Argus state. They are always skipped during replay.

| Endpoint                 | Side Effect         | Client Methods   |
| ------------------------ | ------------------- | ---------------- |
| `/testrun/report/email`  | Sends actual emails | `send_email()`   |
| `/planning/plan/trigger` | Triggers CI jobs    | `trigger_jobs()` |

---

## 7. Server-Side Replay Ingest Endpoint

```
POST /api/v1/client/replay/ingest
Content-Type: application/x-tar-zstd
```

**Query parameters:**

- `dry_run=false` — if true, validate and return what would be replayed without executing

**How it works:**

1. Flask receives the `tar.zst` body and decompresses it using `zstandard`
2. Extracts all JSONL files from the archive
3. Parses all records, merges across files, sorts by `ts`
4. Applies ordering rules: `submit_run` first, terminal `set_status` / finalize last
5. For each record:
    - Apply idempotency classification (Section 6)
    - Call the corresponding internal service function directly (no HTTP self-requests)
    - Record outcome (success or error with detail)
6. Returns a summary:

```json
{
    "total": 47,
    "processed": 42,
    "succeeded": 41,
    "failed": 1,
    "skipped_no_replay": 4,
    "errors": [{ "ts": 1712345679100, "endpoint": "/sct/$id/nemesis/submit", "error": "..." }]
}
```

---

## 8. Implementation Phases

### Phase 1: Replay Log (Python Client)

**New file:** `argus/client/replay_log.py`

- `ReplayRecord` data class and `ReplayLog` class with context manager `record()` method
- `queue.Queue` + background writer thread for contention-free disk I/O
- Filename convention: `argus_replay_log_{run_id}_{unix_ms}.jsonl`

**Modify:** `argus/client/base.py`

- Add `log_dir` parameter to `ArgusClient.__init__()` (required, no fallback — each consumer provides its test log directory)
- Capture `init_ts_ms` at construction time; pass to `ReplayLog`
- Initialize `ReplayLog` (always on)
- Add `replay_only` mode: `get()` and `post()` skip the HTTP call but still write to the replay log
- Wrap `post()` with `self._replay_log.record(...)` context manager

**New file:** `argus/client/tests/test_replay_log.py`

- JSONL format correctness (single line per request, all fields present)
- Thread safety with concurrent writes via queue
- `replay_only` mode: no HTTP calls, JSONL written with `success=false`
- Multiple files for the same run do not interfere
- Writer thread clean shutdown via `close()`

### Phase 2: Backend Changes

**Modify:** `argus/backend/service/client_service.py`

- In `update_run_status()`: if status is terminal, set `end_time = now()` when not already set

**Fix:** `argus/backend/plugins/sirenada/model.py`

- In `submit_sirenada_run()`: add dedup guard on `run.results` before appending (same `not in` pattern already used for `sirenada_test_ids`, `browsers`, `clusters`, `s3_folder_ids`)

### Phase 3: Remove SCT Self-Healing Code

**Modify `sdcm/utils/argus.py`:**

- Remove `argus_offline_collect_events()`

**Modify `sct.py`:**

- Remove the `if not argus_client.get_run().get("events"):` block at line 1865-1866

**Modify `sdcm/tester.py`:**

- Remove the one-shot `submit_events` re-fire block in `argus_finalize_test_run()`
- Replace separate `set_status` + `finalize_run` calls with a single `set_status(terminal_status)` call

**Modify `sdcm/test_config.py`:**

- Replace `MagicMock` fallback with replay-only mode client instantiation

### Phase 4: pytest-argus-reporter Integration

**Modify:** `pytest-argus-reporter/pytest_argus_reporter.py`

- Add `--argus-log-dir` command-line option
- Pass `log_dir` to `ArgusGenericClient` constructor

### Phase 5: `argus replay` CLI Command

Add an `argus replay` command to the CLI that collects JSONL files, bundles them into a `tar.zst` archive, and uploads to the Argus ingest endpoint. Supports `--dir`, `--run-id`, `--file`, `--dry-run`, `--target-url`, and `--report` flags. Implementation details handled in the CLI repository.

### Phase 6: Server-Side Replay Ingest (Argus Backend)

**New blueprint:** `argus/backend/controller/replay_api.py`

- `POST /api/v1/client/replay/ingest`
- Decompresses `tar.zst` body with `zstandard`
- Delegates to `ReplayService`

**New service:** `argus/backend/service/replay_service.py`

- Extracts and merges JSONL files from archive
- Sorts records by `ts`, applies ordering rules
- Maps endpoint templates to internal service functions
- Applies idempotency classification (Section 6)
- Collects per-record outcomes; returns summary
