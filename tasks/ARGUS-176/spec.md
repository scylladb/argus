# ARGUS-176 — Generic results across the tests of a release

## Overview

A new `results` router answers two reads for one release. The first lists the
generic result table names of the release. The second returns the cells of
the tables whose name matches a substring, for every test of the release.
The service reads the tests of the release and their table metadata. It
selects the runs of each test that started in the time window from the run
table, leaves out the ignored runs, then reads the cells of only those
runs. It groups the cells by table, then by test, then by run. The CLI gets
`argus results tables` and `argus results query` on top of the two routes.
The schema does not change, so results that exist today are readable at once.

## Constraints

- No schema change and no backfill. The release read is needed now.
- No `ALLOW FILTERING` query. Every read names a full partition key, or the
  `release_id` index of `argus_test_v2`.
- The time filter uses the write time of the result, as soyacz asked.
  `sut_timestamp` is a second, separate filter.
- The cost of a read follows the time window, not the full history of a
  test.

## Design

### Approaches

| Approach | For | Against |
|---|---|---|
| A. Fan-out over the full `(test_id, name)` partitions, bounded by one release | No schema change, no backfill, no new write path. Old results work at once. | Every read gets all runs a test ever sent, whatever the window. Time filters run in the application. No read across releases. |
| A′. A, but the runs of the window come first from the run table, keyed by `(build_id, start_time)`, and the data read names them with `run_id IN` | Everything A gives. ScyllaDB prunes by time. The run read also gives `investigation_status`, `build_number` and `scylla_version`. | One more query per test. A read with no window reads all runs, so the window has a default. The window selects runs by start time, so it needs a margin. No read across releases. |
| B. A query table keyed by `(name, day bucket)`, written next to `generic_result_data_v1` at submit | One partition read per table and day. Time ranges are cheap. Reads across releases work. | A new table, a second write on every submit, and a backfill job for old results. |
| C. A materialized view of `generic_result_data_v1` keyed by `name` | ScyllaDB builds the view and fills old rows. No new write in the application. | One partition per table name grows without bound. A view cannot carry `WRITETIME`. View builds and view consistency add operational risk. |
| D. A full scan of `generic_result_metadata_v1` with one `ALLOW FILTERING` read per pair (PR #1033) | No schema change. | Reads every test in Argus. The review of PR #1033 stopped it. |

This spec selects A′. A release bounds the fan-out, a release is the scope
that the users need now, and the run table already holds the time index.
B is the path when a read across releases becomes necessary, see
`Deferred work`.

### Read flow

```mermaid
sequenceDiagram
    participant C as CLI or agent
    participant R as results router
    participant S as ResultsService
    participant DB as ScyllaDB
    C->>R: GET /api/v1/results/release/{release}?table=...
    R->>S: get_release_results(release, table_filter, filters)
    S->>DB: argus_release_v2 by name (when release is not a UUID)
    S->>DB: argus_test_v2 WHERE release_id = ?
    par one per test, at most 50 at a time
        S->>DB: generic_result_metadata_v1 WHERE test_id = ?
    end
    Note over S: keep tests with a table whose name contains table_filter
    par one per test, at most 50 at a time
        S->>DB: <plugin run table> WHERE build_id = ?<br/>AND start_time >= since - 7 days [AND start_time <= until]
    end
    Note over S: drop ignored runs
    par one per (test, table), at most 50 at a time
        S->>DB: generic_result_data_v1 WHERE test_id = ? AND name = ?<br/>AND run_id IN (... up to 90 ...) with WRITETIME(status)
    end
    Note over S: filter by status, write time, sut_timestamp<br/>group by table, test, run
    S-->>R: list of table groups
    R-->>C: APIResponse
```

The tables read follows the same path up to the metadata step. It counts the
tests per table name and merges the column names.

### Failure behavior

| Condition | Behavior |
|---|---|
| The release name matches no release | `DataValidationError`, the response has `status: error` |
| No table name matches `table` | An empty list |
| A test or a run has no cell after the filters | The test or the run is left out of the output |
| A cell has no `sut_timestamp` and a `sut_*` filter is set | The cell is left out |
| The request has no `since` | `since` is 30 days before the request |
| A run is marked as ignored | The run is left out |
| A test has no `plugin_name` or no `build_system_id` | The test is left out |

## Contracts

### Outputs

```
GET /api/v1/results/release/{release}/tables
    release: release name or UUID
```

```json
{"status": "ok", "response": [
  {"name": "throughput", "description": "...", "columns": ["ops", "p99"], "tests": 12}
]}
```

```
GET /api/v1/results/release/{release}
    table      required, case-insensitive substring of the table name
    status[]   repeatable, keeps cells with one of these statuses
    since      ISO-8601, write time of the result >= since, default 30 days ago
    until      ISO-8601, write time of the result <= until
    sutSince   ISO-8601, sut_timestamp >= sutSince
    sutUntil   ISO-8601, sut_timestamp <= sutUntil
```

```json
{"status": "ok", "response": [
  {"table": "throughput", "description": "...", "tests": [
    {"test_id": "<uuid>", "test_name": "longevity-cdc", "build_id": "scylla-master/longevity/longevity-cdc",
     "runs": [
       {"run_id": "<uuid>", "build_number": 412, "scylla_version": "2026.2.0~dev",
        "submitted_at": "2026-10-20T08:12:00Z", "sut_timestamp": "2026-10-19T00:00:00Z",
        "cells": [{"row": "write", "column": "ops", "value": 1200.5, "status": "PASS"}]}
     ]}
  ]}
]}
```

Groups sort by table name. Runs sort by `submitted_at`, newest first.
`build_id` is `build_system_id` of the test. `value` holds `value_text` when
the cell has no number.

```
argus results tables <release>
argus results query <release> --table <substring> [--status S]... \
    [--since T] [--until T] [--sut-since T] [--sut-until T]
```

The CLI prints the response as JSON, or one row per cell with `--text`.

### Module API

```python
class ResultsService:
    async def get_release_result_tables(self, release: str) -> list[dict]: ...
    async def get_release_results(self, release: str, table_filter: str, statuses: list[str] | None = None,
                                  since: datetime | None = None, until: datetime | None = None,
                                  sut_since: datetime | None = None,
                                  sut_until: datetime | None = None) -> list[dict]: ...
```

## Risks

| Risk | Response |
|---|---|
| A release with many tests and tables sends many queries | `gather_limited` holds the reads at 50 at a time. The `table` filter cuts the data reads before they start. |
| A run writes results more than 7 days after it starts | Its late results fall outside the window, and no error shows it. The margin is a reviewer question in `Decisions`. |
| A wide window still reads every run in it | The 30-day default bounds a read with no window. Approach B removes the cost. |
| `WRITETIME(status)` changes when a run sends the same cell again | `submitted_at` shows the last write of the cell, not the first. |

## Deferred work

- A read across releases. It needs approach B, a query table keyed by the
  table name and a time bucket, and a backfill. The service API keeps
  `release` as one argument, so a second method can sit next to it.
- The move of the per-test results endpoints from `api.py` into the
  `results` router, and the frontend change that follows it. The intent asks
  for it. This change only puts the new routes in the new router.

## Decisions

- The release is the scope of the read. The users need releases now, and a
  release bounds the fan-out. (spec)
- The change ships without a schema change or a backfill, so old results are
  readable at once. (spec)
- The release path parameter takes a name or a UUID, so an agent can pass
  the name it already knows. (spec)
- `since` defaults to 30 days, and the run window starts 7 days before
  `since`. (open)
- A read across releases waits for approach B. (open)
