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
2. **Switch to replay-only mode** — the `ArgusClient` is still instantiated with a valid `ReplayLog`, but all HTTP calls are skipped. The replay log records every intended request with `"success": false`. When argus recovers, the entire test run can be reconstructed from the JSONL file via `argus replay` or the server-side ingest endpoint (Section 6.4). This gives the same graceful degradation as MagicMock but with **zero data loss**.

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

There is **no retry, no buffer, no queue persistence**. If `submit_event()` fails, the event is lost from the real-time pipeline.

#### 1.5.4 Offline Event Recovery (`argus_offline_collect_events`)

This is SCT's primary recovery mechanism (`sdcm/utils/argus.py:94-107`). Called from `store_logs_in_argus()` in `sct.py:1865-1866`:

```python
# sct.py — after log collection
if not argus_client.get_run().get("events"):
    argus_offline_collect_events(client=argus_client)
```

The function:

1. Reads the local `~/sct-results/latest/` directory
2. Reconstructs `EventsProcessesRegistry` from disk
3. Collects the last 100 events grouped by severity
4. Submits them as a batch via `client.submit_events()`

**Limitations:**

- Only recovers **events** — not results, resources, packages, nemesis, configs, or any other data type
- Only triggered during the `collect-logs` CLI step — if that step doesn't run, no recovery
- Checks `get_run().get("events")` — if the run itself wasn't submitted (argus was down from the start), `get_run()` will fail and recovery is skipped
- Limited to 100 most recent events — older events are lost
- SCT-specific — doesn't help generic, driver-matrix, or sirenada tests

#### 1.5.5 Test Finalization — Single Attempt

`argus_finalize_test_run()` (`sdcm/tester.py:659-683`) submits events, sets status, and finalizes — all in a single try/except. If any call fails, the entire finalization is logged and skipped. No retry.

#### 1.5.6 Node Operations — No Retry

All node-level argus operations (`_add_node_to_argus`, `update_shards_in_argus`, `_terminate_node_in_argus` in `sdcm/cluster.py`) catch exceptions and log them. No retry, no recovery.

#### 1.5.7 Summary of Gaps

| Data Type           | Current Recovery                                    | Gap                                                                      |
| ------------------- | --------------------------------------------------- | ------------------------------------------------------------------------ |
| Events (real-time)  | None — fire-and-forget                              | Lost if argus is down during event                                       |
| Events (batch)      | `argus_offline_collect_events` — last 100 from disk | Only 100 events, only during `collect-logs`, only if run exists in argus |
| Test run submission | None                                                | If argus is down at test start, nothing works                            |
| Test status         | None                                                | Lost                                                                     |
| Results/performance | None                                                | Lost — most expensive data                                               |
| Resources (nodes)   | None                                                | Lost                                                                     |
| Packages            | None                                                | Lost                                                                     |
| Nemesis records     | None                                                | Lost                                                                     |
| Logs/screenshots    | None                                                | Lost (links only, actual files are on S3)                                |
| JUnit reports       | None                                                | Lost                                                                     |
| Config              | None                                                | Lost                                                                     |
| Stress commands     | None                                                | Lost                                                                     |

**The replay log addresses all of these gaps** because it records at the HTTP layer — every `post()` call is captured regardless of the data type. SCT's existing recovery is event-specific and limited; the replay log is universal.

#### 1.5.8 How the Replay Log Replaces SCT's Self-Healing

With the replay log in place, SCT's custom recovery code becomes redundant and can be removed. The replay log operates at the HTTP layer inside `ArgusClient` itself, so it captures every data type across all test types — something SCT's event-specific recovery never could.

**Code that can be deleted from SCT:**

1. **`argus_offline_collect_events()`** (`sdcm/utils/argus.py:94-107`) — This function reads events from disk and re-submits them. The replay log captures the original `submit_event()` calls with full payloads (not limited to 100), making offline collection redundant.

2. **The `if not argus_client.get_run().get("events")` check** (`sct.py:1865-1866`) — This conditional triggers offline event recovery during `store_logs_in_argus()`. With the replay log, there's no need to check whether events made it to argus and manually re-collect them.

3. **`MagicMock` fallback** (`sdcm/test_config.py`) — Replaced by the client's replay-only mode. The real `ArgusClient` is always instantiated (with replay log), so data is never silently lost.

**Code that remains unchanged in SCT:**

- `verbose_suppress()` wrappers in the event pipeline — still useful for preventing test failures from argus errors
- `try/except` wrappers around argus calls in `tester.py`, `cluster.py` — still useful for graceful degradation
- Heartbeat thread — still useful for signaling test liveness to argus

**What changes for other consumers (dtest, driver-matrix, sirenada):**

Nothing. They get the replay log automatically because it's in `ArgusClient`. They never had SCT-style recovery code, so there's nothing to delete — they just gain recovery capability they never had.

---

## 2. Always-On JSONL Replay Log

### 2.1 Design Principles

This is **not** request logging for debugging. This is a **replay journal** — a write-ahead log of every API call that can be used to reconstruct Argus state from scratch.

1. **Always on by default** — we don't know when Argus will start failing, so every mutating request must be recorded
2. **Independent of request outcome** — captures what _should_ be sent to achieve the desired state, not what happened
3. **Single file per test run** — one test run is always one type, no need for multi-file complexity
4. **Persistent atomic sequence numbers** — `seq` field uses a lock-protected counter that survives process restarts; this determines the exact replay order even in concurrent environments
5. **Records success/failure** — so replay can filter to only re-send what failed

### 2.2 New Module: `argus/client/replay_log.py`

A `ReplayLog` class initialized in `ArgusClient.__init__()`, always active. Writes to a single JSONL file.

**File location:** `{log_dir}/argus_replay_{run_id}.jsonl`

- `log_dir` determined by constructor param or `ARGUS_LOG_DIR` env var, falling back to current working directory

### 2.3 JSONL Record Schema

Each line in the file is a self-contained JSON object:

```json
{
  "seq": 1,
  "ts": "2024-01-15T10:30:00.123456Z",
  "method": "POST",
  "endpoint": "/testrun/$type/$id/submit_results",
  "location_params": {"type": "scylla-cluster-tests", "id": "550e8400-e29b-41d4-a716-446655440000"},
  "params": null,
  "body": {
    "schema_version": "v8",
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Performance Results",
    "description": "Throughput metrics",
    "columns": [...],
    "results": [...]
  },
  "test_type": "scylla-cluster-tests",
  "success": true
}
```

**Field descriptions:**

| Field             | Type         | Description                                                                                                                 |
| ----------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `seq`             | int          | Atomic, persistent sequence number. Determines replay order.                                                                |
| `ts`              | string       | ISO 8601 timestamp of when the request was made.                                                                            |
| `method`          | string       | HTTP method: `"GET"` or `"POST"`.                                                                                           |
| `endpoint`        | string       | Route template with `$` placeholders (e.g. `/testrun/$type/$id/submit_results`). Enables replay against any Argus instance. |
| `location_params` | object       | Parameters to resolve the endpoint template into a full path.                                                               |
| `params`          | object\|null | URL query parameters.                                                                                                       |
| `body`            | object\|null | Full request body as sent to the API. Includes `schema_version` via `generic_body`.                                         |
| `test_type`       | string       | The client's test type (redundant with body but useful for filtering).                                                      |
| `success`         | bool         | `true` if HTTP status is 2xx and the response body does not contain an `"error"` key, `false` otherwise.                    |

**What is NOT stored (by design):**

- Auth token — security: tokens are per-user and may rotate
- HTTP headers — reconstructed at replay time
- Response body — not needed for replay; success/failure is enough
- `schema_version` as separate field — already embedded in every `body` via `generic_body`

### 2.4 Persistent Sequence Number

The `seq` counter must survive process restarts. If the log file already exists (e.g. a test process crashed and restarted, or another component writes to the same run's log), the counter resumes from the last recorded value.

```python
import threading
import json
import datetime
from pathlib import Path


class ReplayLog:
    def __init__(self, log_dir: str, run_id: str, test_type: str):
        self._lock = threading.Lock()
        self._path = Path(log_dir) / f"argus_replay_{run_id}.jsonl"
        self._test_type = test_type
        self._seq = self._load_last_seq()
        self._file = open(self._path, "a")

    def _load_last_seq(self) -> int:
        """Resume sequence from existing file. Reads last line only — O(1)."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return 0
        with open(self._path, "rb") as f:
            # Seek backwards from EOF to find the last complete line
            try:
                f.seek(-2, 2)
                while f.read(1) != b"\n":
                    f.seek(-2, 1)
            except OSError:
                # File has only one line
                f.seek(0)
            last_line = f.readline().decode()
        try:
            return json.loads(last_line)["seq"]
        except (json.JSONDecodeError, KeyError):
            return 0

    def record(self, method: str, endpoint: str, location_params: dict | None,
               params: dict | None, body: dict | None, success: bool):
        """Record a request to the replay log.

        Only the seq counter is synchronized. File writes happen outside
        the lock since replay sorts by seq — disk order doesn't matter.
        """
        with self._lock:
            self._seq += 1
            seq = self._seq

        entry = {
            "seq": seq,
            "ts": datetime.datetime.now(datetime.UTC).isoformat(),
            "method": method,
            "endpoint": endpoint,
            "location_params": location_params,
            "params": params,
            "body": body,
            "test_type": self._test_type,
            "success": success,
        }
        # json.dumps + write + flush happen outside the lock.
        # Lines may interleave on disk but each is a complete JSON line
        # and replay sorts by seq, so disk order is irrelevant.
        self._file.write(json.dumps(entry, default=str) + "\n")
        self._file.flush()

    def close(self):
        self._file.close()
```

**Why only lock the counter, not the write:**

The replay tool sorts entries by `seq` before executing, so lines don't need to be ordered on disk. By holding the lock only for the integer increment (nanoseconds), we eliminate contention from JSON serialization and disk I/O. In concurrent systems like SCT's event pipeline (multiple threads submitting events simultaneously), this is a significant performance win.

Python's `file.write()` under the GIL guarantees that individual `write()` calls won't produce interleaved bytes, so concurrent writes of complete JSON lines are safe without a write lock.

### 2.5 Integration into ArgusClient

The replay log is initialized in `ArgusClient.__init__()` and called from `post()`:

```python
class ArgusClient:
    def __init__(self, auth_token, base_url, ..., log_dir: str | None = None):
        # ... existing init code ...
        self._replay_log = ReplayLog(
            log_dir=log_dir or os.environ.get("ARGUS_LOG_DIR", "."),
            run_id=getattr(self, "run_id", "unknown"),
            test_type=getattr(self, "test_type", "unknown"),
        )

    def post(self, endpoint, location_params=None, params=None, body=None):
        url = self.get_url_for_endpoint(endpoint=endpoint, location_params=location_params)
        LOGGER.debug("POST Request: %s, params: %s, body: %s", url, params, body)
        response = self.session.post(url=url, params=params, json=body,
                                      headers=self.request_headers, timeout=self._timeout)
        LOGGER.debug("POST Response: %s %s", response.status_code, response.url)

        # Record to replay log — determine success without raising
        success = 199 < response.status_code < 300
        if success:
            try:
                success = "error" not in response.json()
            except Exception:
                success = False
        self._replay_log.record(
            method="POST", endpoint=endpoint,
            location_params=location_params, params=params,
            body=body, success=success,
        )

        return response
```

Only `post()` is recorded — `get()` calls are read-only and do not mutate state, so they are not included in the replay log. The replay log write happens after the request completes (or fails), before the response is returned to the caller. This ensures we capture the actual success/failure status.

---

## 3. Log Storage Strategy

### 3.1 Storage Location

The JSONL replay file is written to the **test's existing log directory**. For now, this is the only supported storage target. How replay files are stored and accessed for other use-cases (e.g. generic CI environments) will be determined in the future.

- For SCT: `~/sct-results/latest/`
- For other consumers: pass `log_dir` to the client constructor or set the `ARGUS_LOG_DIR` environment variable. Falls back to the current working directory.

### 3.2 Convention

1. File naming: `argus_replay_{run_id}.jsonl` — one file per test run.
2. The file is co-located with other test artifacts; no new upload mechanism is needed.
3. For `pytest-argus-reporter`: add `--argus-log-dir` command-line option that passes through to `ArgusGenericClient`.

---

## 4. `argus replay` CLI Command

The `argus replay` CLI command is a thin uploader. It reads the local JSONL file and POSTs it to the Argus server-side ingest endpoint (`POST /api/v1/client/replay/ingest`). All replay logic — ordering, idempotency, execution — runs on the server.

### 4.1 Command Interface

```
argus replay <path-to-jsonl-file> [flags]

Flags:
  --failed-only       Only replay requests that originally failed (default: true)
  --dry-run           Validate on the server without executing
  --force-all         Ignore idempotency checks, replay everything
  --target-url        Override the base URL (replay against different Argus instance)
  --report            Output format for summary: "text" (default) or "json"
```

**Examples:**

```bash
# Upload replay file to Argus for server-side processing
argus replay ./argus_replay_550e8400.jsonl

# Dry-run to see what would be replayed
argus replay ./argus_replay_550e8400.jsonl --dry-run

# Replay against a different Argus instance
argus replay ./argus_replay_550e8400.jsonl --target-url https://argus-staging.example.com
```

### 4.2 Go Package Structure

New package: `cli/internal/replay/`

```
cli/internal/replay/
├── uploader.go     # Reads JSONL file, POSTs to ingest endpoint
├── reporter.go     # Formats and prints server summary response
└── *_test.go       # Tests for each component
```

New command file: `cli/cmd/replay.go` — follows patterns from `cli/cmd/testrun.go`.

---

## 5. Endpoint Idempotency Classification

Each API endpoint is classified into one of four replay strategies. The server-side ingest endpoint uses this classification to determine how to handle each entry.

### 5.1 SAFE — Replay Freely

These endpoints are idempotent or last-write-wins. Replaying them multiple times produces the same result.

| Endpoint                                    | Client Methods                                                   |
| ------------------------------------------- | ---------------------------------------------------------------- |
| `/testrun/$type/$id/set_status`             | `set_status()`, `set_sct_run_status()`, `set_matrix_status()`    |
| `/testrun/$type/$id/update_product_version` | `update_product_version()`, `update_scylla_version()`            |
| `/sct/$id/sct_runner/set`                   | `set_sct_runner()`                                               |
| `/testrun/$type/$id/logs/submit`            | `submit_logs()`, `submit_sct_logs()`                             |
| `/sct/$id/screenshots/submit`               | `submit_screenshots()`                                           |
| `/sct/$id/packages/submit`                  | `submit_packages()`                                              |
| `/sct/$id/events/submit`                    | `submit_events()` (batch overwrites)                             |
| `/sct/$id/resource/$name/update`            | `update_resource()`                                              |
| `/sct/$id/resource/$name/shards`            | `update_shards_for_resource()`                                   |
| `/$id/config/submit`                        | `sct_submit_config()`                                            |
| `/driver_matrix/env/submit`                 | `submit_env()`                                                   |
| `/testrun/$type/$id/finalize`               | `finalize_run()`, `finalize_sct_run()`, `finalize_generic_run()` |
| `/testrun/$type/$id/submit_results`         | `submit_results()` — keyed by table name, overwrites             |

> **Note:** Heartbeat calls (`/testrun/$type/$id/heartbeat`) are **not replayed**. They serve only to signal live test activity and have no value after the test has finished.

### 5.2 CHECK_FIRST — Verify Before Replay

These endpoints create new entities. Replaying when the entity already exists would cause errors or duplicates.

| Endpoint                   | Check Method                                | Client Methods                                                                                                    |
| -------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `/testrun/$type/submit`    | `GET /testrun/$type/$id/get` — if 200, skip | `submit_run()`, `submit_sct_run()`, `submit_generic_run()`, `submit_driver_matrix_run()`, `submit_sirenada_run()` |
| `/sct/$id/resource/create` | Check by resource name in run data          | `create_resource()`                                                                                               |

### 5.3 APPEND — Safe to Replay

These endpoints append records. All inserts are safe — replaying them is idempotent from a data-integrity standpoint because duplicate entries are acceptable.

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

### 5.4 SKIP — Do Not Replay by Default

These endpoints have side effects beyond Argus state. They are skipped unless `--force-all` is passed.

| Endpoint                 | Side Effect         | Client Methods   |
| ------------------------ | ------------------- | ---------------- |
| `/testrun/report/email`  | Sends actual emails | `send_email()`   |
| `/planning/plan/trigger` | Triggers CI jobs    | `trigger_jobs()` |

---

## 6. Automation

The goal is full automation without adding new services.

### 6.1 Manual Replay via CLI

After an outage, download the replay JSONL file from the test log directory and upload it to Argus for server-side processing:

```bash
# Upload replay file to Argus for server-side processing
argus replay ./argus_replay_550e8400.jsonl --server-side
```

The CLI's only job is to upload the file. All replay logic runs server-side.

### 6.2 Server-Side Replay Ingest Endpoint

Argus itself accepts a JSONL replay file and processes it internally. This is the only supported replay path — Argus heals itself.

**New API endpoint:**

```
POST /api/v1/client/replay/ingest
Content-Type: multipart/form-data

Body: JSONL file upload
```

**Query parameters:**

- `failed_only=true` (default) — only process entries with `"success": false`
- `dry_run=false` — if true, validate and return what would be replayed without executing
- `force_all=false` — if true, skip idempotency checks

**How it works:**

1. Argus receives the JSONL file
2. Parses entries, sorts by `seq`
3. Applies ordering rules (submit first, finalize last)
4. Applies idempotency classification (Section 5) — checks existence before creating, skips email/trigger endpoints
5. Executes each entry against its own internal service layer directly (no HTTP overhead — calls the service functions that the API controller would call)
6. Returns a summary report:

```json
{
    "total": 47,
    "processed": 12,
    "succeeded": 11,
    "failed": 1,
    "skipped": 35,
    "errors": [{ "seq": 23, "endpoint": "/sct/$id/nemesis/submit", "error": "Duplicate nemesis record" }]
}
```

**Advantages:**

- **No HTTP round-trip overhead** — Argus processes the replay internally by calling service functions directly, not re-issuing HTTP requests to itself
- **Argus can self-heal** — upload the file and Argus does the rest
- **Atomic processing** — Argus can wrap the replay in a database transaction or batch operation
- **Access control** — The endpoint uses the same `@api_login_required` auth as other client endpoints

---

## 7. Implementation Phases

### Phase 1: Replay Log and Replay-Only Mode (Python Client)

**New file:** `argus/client/replay_log.py`

- `ReplayLog` class with persistent sequence counter
- Thread-safe recording with minimal lock contention
- `replay_failed()` method for in-process retry

**Modify:** `argus/client/base.py`

- Add `log_dir` parameter to `ArgusClient.__init__()`
- Initialize `ReplayLog` (always on)
- Add `replay_only` mode: when `True`, `get()` and `post()` skip the HTTP call but still write to the replay log with `"success": false`
- Optional health check on init: if argus is unreachable, auto-enter replay-only mode
- Call `record()` from `post()` after each request

**New file:** `argus/client/tests/test_replay_log.py`

- Test JSONL format correctness
- Test sequence number persistence across restarts
- Test thread safety with concurrent writes
- Test replay-only mode skips HTTP but writes JSONL

### Phase 2: pytest-argus-reporter Integration

**Modify:** `pytest-argus-reporter/pytest_argus_reporter.py`

- Add `--argus-log-dir` command-line option
- Pass `log_dir` to `ArgusGenericClient` constructor

### Phase 3: `argus replay` CLI Command (Go)

**New command:** `cli/cmd/replay.go`

- Cobra command following `testrun.go` patterns
- Uploads the JSONL file to the Argus server-side ingest endpoint (`POST /api/v1/client/replay/ingest`)
- Flags: `--failed-only`, `--dry-run`, `--force-all`, `--target-url`
- Prints the summary report returned by the server

**New package:** `cli/internal/replay/`

- `uploader.go` — reads the JSONL file and POSTs it to the ingest endpoint
- `reporter.go` — formats and prints the server summary response
- `*_test.go` — Unit tests

### Phase 4: Server-Side Replay Ingest (Argus Backend)

**New blueprint:** `argus/backend/controller/replay_api.py`

- `POST /api/v1/client/replay/ingest` — accepts JSONL file upload, processes internally
- Applies ordering rules and idempotency classification
- Calls service layer directly (no HTTP self-requests)
- Returns summary report with per-entry status

**New service:** `argus/backend/service/replay.py`

- Parses JSONL entries
- Maps endpoints to internal service functions
- Applies idempotency checks (Section 5)
- Batch processing with error collection
