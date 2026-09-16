# Dashboard Performance Optimization Plan

## Problem Statement

The Argus release dashboard was unacceptably slow. Three endpoints were identified as bottlenecks:

| Endpoint                            | Baseline | Root Cause                                                                                                                   |
| ----------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `GET /api/v1/release/stats/v2`      | ~1.7s    | Full fan-out scan: `SELECT ... WHERE build_id IN ?` across all plugin tables, streaming up to 500K rows, filtering in Python |
| `GET /api/v1/release/<id>/versions` | ~2.1s    | GSI scan on `release_id` index across entire SCT table to collect distinct `scylla_version` values                           |
| `GET /api/v1/release/<id>/images`   | ~2.1s    | Same GSI scan + UDT deserialization of `cloud_setup` on every row to extract `db_node.image_id`                              |

Additionally, the frontend was bypassing any potential caching by hardcoding `force=1` on every stats request.

---

## Changes Implemented

### Lever F — CL=ONE Read Profile for Stats Fan-out

**File:** `argus/backend/plugins/core.py`

`get_stats_for_release()` executes batched async queries (`build_id IN ?`, step size 90). These previously used the default consistency level. Changed to use the `read_fast` execution profile (CL=ONE, dict factory) already defined in `db.py`.

On a single-node local cluster this is a ~5% improvement. On production multi-node RF>1 clusters this avoids coordinator round-trips to a replica, giving a meaningful latency reduction.

```python
futures.append(cluster.session.execute_async(
    query=query,
    parameters=(next_slice,),
    execution_profile="read_fast",   # CL=ONE
))
```

---

### Lever B — Denormalized Index Tables for Versions and Images

**Files:** `argus/backend/models/web.py`, `argus/backend/plugins/sct/testrun.py`, `argus/backend/service/release_manager.py`, `argus/backend/cli.py`

#### Models

Two new Scylla tables are written to incrementally as runs progress:

```
argus_release_distinct_versions
  release_id  UUID  (partition key)
  version     TEXT  (clustering key)

argus_release_distinct_images
  release_id  UUID  (partition key)
  image_id    TEXT  (clustering key)
```

Each partition holds only the distinct values seen for that release. A read is a single partition scan returning O(distinct values) rows — typically 5–50 — instead of scanning the entire plugin table.

#### Write Hooks

Writes are best-effort (exceptions are logged, not raised) and are owned directly by each plugin model, which calls inherited helpers from `PluginModelBase`. No central dispatcher.

| Hook                       | Where called                     | Snapshot invalidation                                              | Versions index                                   | Images index                        |
| -------------------------- | -------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------ | ----------------------------------- |
| `submit_run()`             | Each plugin model's `submit_run` | `self.invalidate_release_snapshot()` — new run visible immediately | —                                                | SCT only: `self._index_image(self)` |
| `submit_product_version()` | Each plugin model's override     | —                                                                  | `self.index_version()` — version arrives mid-run | —                                   |
| `finish_run()`             | Each plugin model's `finish_run` | `self.invalidate_release_snapshot()` — final status visible        | `self.index_version()` — final version           | SCT only: `self._index_image(self)` |

`if_not_exists().create()` is used for idempotency — re-submitting the same version/image is a no-op at the Scylla level (LWT check). This means writes can be retried safely.

#### Plugin Ownership

Side-effect logic lives on `PluginModelBase` (`argus/backend/plugins/core.py`) as instance methods:

- `invalidate_release_snapshot()` — targeted snapshot invalidation (see Lever A)
- `index_version()` — writes `scylla_version` to `ReleaseDistinctVersions` (universal — all plugins have `scylla_version`)

SCT-specific logic stays on `SCTTestRun` only:

- `_index_image(run)` — extracts `cloud_setup.db_node.image_id` and writes to `ReleaseDistinctImages` (SCT-only field)

`ClientService` is a thin dispatcher: it calls the plugin method and `save()` only. No side-effect logic lives there.

#### Read Path

`SCTTestRun.get_distinct_product_versions()` and `get_distinct_cloud_images_for_release()` in `argus/backend/plugins/sct/testrun.py` read from the index tables first. If the index partition is empty (pre-backfill or new release), they fall back to the original GSI scan. This makes the transition safe with zero downtime.

#### Cleanup

`delete_release()` in `release_manager.py` deletes the `ReleaseDistinctVersions` and `ReleaseDistinctImages` partitions for the release to prevent orphaned rows.

#### Backfill

`scripts/migration/migration_2026-04-22.py` populates the index tables from existing run data. Pages through the SCT table per release with `fetch_size=2000`. The script checks whether `ReleaseDistinctVersions` already contains any rows; if so it exits immediately (idempotent). Run once after deploying to an existing environment via `uv run scripts/migration/migration_2026-04-22.py`.

**Result:** `/versions` 2.1s → ~7ms, `/images` 2.1s → ~6ms (-99.7%).

---

### Lever A — Release Stats Snapshot Cache

**Files:** `argus/backend/models/web.py`, `argus/backend/service/stats.py`

#### Model

```
argus_release_stats_snapshot
  release_id   UUID      (partition key)
  filter_key   TEXT      (clustering key)
  payload      TEXT      (JSON blob of ReleaseStats.to_dict())
  generated_at TIMESTAMP
```

`filter_key` is a deterministic human-readable string encoding the full set of query parameters:

```
v=<productVersion>::img=<imageId>::nov=<0|1>::lim=<0|1>
```

Examples:

- `v=::img=::nov=1::lim=0` — unfiltered, include-no-version
- `v=5.2::img=::nov=1::lim=0` — version-filtered
- `v=::img=ami-0abc1234::nov=0::lim=0` — image-filtered

Each distinct filter combination gets its own clustering row within the release's partition. A typical release will have 1–10 rows depending on how many filter combinations users have accessed.

#### Cache Read Path

`ReleaseStatsCollector.collect()` checks for a snapshot before executing the slow fan-out:

```
if not force:
    try snapshot = ReleaseStatsSnapshot.get(release_id, filter_key)
    if hit: return json.loads(snapshot.payload)   # ~5ms
    # else: fall through to slow path
```

The `force` parameter bypasses the cache entirely — used by the UI's manual refresh button.

#### Cache Write Path

After computing stats the slow way, the result is serialized using Flask's `ArgusJSONProvider` (which handles UUID, datetime, Cassandra UDTs, and enum keys) and written to the snapshot table:

```python
ReleaseStatsSnapshot.create(
    release_id=self.release.id,
    filter_key=filter_key,
    payload=current_app.json.dumps(result),
    generated_at=datetime.utcnow(),
)
```

Write failures are caught and logged — a failed snapshot write does not affect the response returned to the caller.

#### Cache Invalidation Architecture

Invalidation is **explicit, event-driven, and version-scoped**. It is triggered by `submit_run()` and `finish_run()` on each plugin model via the inherited `invalidate_release_snapshot()` method on `PluginModelBase`. No TTL, no background refresh, no scheduler.

```
finish_run() / submit_run()  [on plugin model instance]
  ├── self.invalidate_release_snapshot()
  │     ├── fetch all snapshot rows for self.release_id  (single partition scan)
  │     ├── delete rows where filter_key starts with "v=<self.scylla_version>::"
  │     └── delete rows where filter_key starts with "v=::"  (all-versions aggregate)
  ├── self.index_version()                    (on finish_run / submit_product_version)
  └── self._index_image(self)                 (SCT only, on submit_run / finish_run)
```

**Targeted invalidation — which rows are deleted:**

When a run with `scylla_version = "5.6.1"` finishes, only two groups of snapshots are invalidated:

1. `v=5.6.1::*` — every cached filter combination for that specific version (different `img`, `nov`, `lim` values)
2. `v=::*` — the all-versions aggregate view, since it includes data from `5.6.1`

All other version snapshots (`v=5.7.0::*`, `v=5.5.0::*`, etc.) are **left intact**. This means switching to an unaffected version remains fast (~5ms) even when another version is actively receiving new runs.

**Edge case — versionless runs:**

If `scylla_version` is `None` or empty, `version_prefix` becomes `"v=::"`, which is identical to `all_versions_prefix`. Only the all-versions aggregate is invalidated. This is correct — a run with no version does not belong to any specific version bucket.

**Why also invalidate `v=::*`?**

The unfiltered view aggregates all runs regardless of version. Any run finishing on any version changes run counts, statuses, and `last_run` pointers in the all-versions view — so its snapshot must be invalidated too.

**Why NOT invalidate other version snapshots?**

A run for version `5.6.1` does not change the data visible under version `5.7.0`. Leaving other version snapshots intact means:

- Users browsing an unaffected version see ~5ms response times even during active CI on other versions
- Only the specific version snapshot and the aggregate require recomputation
- The snapshot partition typically contains O(10) rows; the scan + selective delete is negligible

**Invalidation frequency:**

Invalidation fires at two points per run lifecycle: `submit_run()` (run created) and `finish_run()` (run completed). On an active release, only the snapshots for the run's specific version and the all-versions aggregate are dropped. Snapshots for other versions remain warm.

**Dormant releases:**

A release with no active runs never gets invalidated. All snapshots persist indefinitely and every load is served from cache. This is correct behaviour — the data is not changing.

**`?force=1` semantics:**

The `force` query parameter bypasses the cache read (always recomputes) but still writes a fresh snapshot on completion. This is used by the manual refresh button in the UI. It does not delete the existing snapshot before computing — it simply overwrites it at the end.

---

### Frontend Fix — Remove Hardcoded `force=true`

**File:** `frontend/ReleaseDashboard/TestDashboard.svelte`

`fetchReleaseStats()` and `fetchViewStats()` were hardcoding `force: new Number(true)` in their query params on every request — including the initial page load and the 5-minute auto-refresh interval. This meant every single request bypassed the snapshot cache, and the cache was written but never read.

Fixed to pass the `force` argument through:

```js
// Before
force: new Number(true),

// After
force: new Number(force),   // force defaults to false; refresh button passes true
```

---

## Architecture Diagram

```
UI: page load
  │
  ├─ GET /api/v1/release/<id>/versions  ──→ ReleaseDistinctVersions (single partition, ~5ms)
  ├─ GET /api/v1/release/<id>/images    ──→ ReleaseDistinctImages   (single partition, ~5ms)
  └─ GET /api/v1/release/stats/v2?force=0
       │
       ├─ cache HIT  ──→ ReleaseStatsSnapshot.get(release_id, filter_key) → json.loads() ~5ms
       └─ cache MISS
            │
            ├─ fan-out: SELECT ... WHERE build_id IN ? (CL=ONE, batched async) ~1.7s
            ├─ Python-side filtering (version, image, no-version)
            ├─ ReleaseStats.collect() + to_dict()
            ├─ ReleaseStatsSnapshot.create(...)  ← write snapshot
            └─ return result

CI/CD runner: run finishes (e.g. scylla_version = "5.6.1")
  └─ POST /api/v1/client/finish_run
       └─ plugin_model.finish_run()   [PluginModelBase method]
            ├─ invalidate_release_snapshot()
            │    ├─ scan release snapshot partition (few rows)
            │    ├─ delete rows matching "v=5.6.1::*"   ← only this version
            │    └─ delete rows matching "v=::*"         ← all-versions aggregate
            ├─ index_version()              ← upsert "5.6.1" to ReleaseDistinctVersions
            └─ _index_image(self)           ← SCT only: upsert to ReleaseDistinctImages
```

---

## Benchmark Results

All measurements on a single-node local ScyllaDB cluster with ~500K seeded runs across 6 tests.

| Endpoint        | Before | After (cold) | After (warm) |
| --------------- | ------ | ------------ | ------------ |
| `GET /stats/v2` | ~1.7s  | ~1.7s        | **~5–12ms**  |
| `GET /versions` | ~2.1s  | n/a          | **~7ms**     |
| `GET /images`   | ~2.1s  | n/a          | **~6ms**     |

Total dashboard API time on a warm cache: **~20ms** vs ~6s before.

---

## Test Plan

### Unit Tests

#### `test_snapshot_filter_key`

Location: `argus/backend/tests/test_stats_snapshot.py`

- Verify `_snapshot_filter_key(None, None, True, False)` returns `"v=::img=::nov=1::lim=0"`
- Verify `_snapshot_filter_key("5.2", None, True, False)` returns `"v=5.2::img=::nov=1::lim=0"`
- Verify `_snapshot_filter_key(None, "ami-abc", False, True)` returns `"v=::img=ami-abc::nov=0::lim=1"`
- Verify two calls with the same args produce identical keys (determinism)
- Verify two calls with different args produce different keys (no collisions between version/image/nov/limited)

#### `test_invalidate_snapshot_targeted`

Location: `argus/backend/tests/test_stats_snapshot.py`

Test that invalidation only removes snapshots for the run's version and the all-versions aggregate:

- Mock `ReleaseStatsSnapshot.filter().all()` returning rows with keys:
    - `v=5.6.1::img=::nov=1::lim=0`
    - `v=5.6.1::img=::nov=0::lim=0`
    - `v=::img=::nov=1::lim=0` (all-versions aggregate)
    - `v=5.7.0::img=::nov=1::lim=0`
- Call `invalidate_release_snapshot()` on a run with `scylla_version="5.6.1"`
- Assert `.delete()` called exactly 3 times (the two `5.6.1` rows + the all-versions row)
- Assert the `v=5.7.0::*` row is **not** deleted

#### `test_invalidate_snapshot_no_version`

- Mock rows as above
- Call `invalidate_release_snapshot()` on a run with `scylla_version=None`
- Assert only the `v=::*` row is deleted (versionless run only affects aggregate)
- Assert `v=5.6.1::*` and `v=5.7.0::*` rows are untouched

#### `test_invalidate_snapshot_no_release_id`

- Call `invalidate_release_snapshot()` with `release_id=None` → assert no DB calls made

#### `test_invalidate_snapshot_exception_swallowed`

- Mock `ReleaseStatsSnapshot.filter()` raising an exception → assert function returns without raising, warning logged

#### `test_index_version_helper`

Location: `argus/backend/tests/test_stats_snapshot.py`

- Call with valid `release_id` and `scylla_version` → assert `ReleaseDistinctVersions.if_not_exists().create()` called with correct args
- Call with `scylla_version=None` → assert no DB calls made
- Call with `release_id=None` → assert no DB calls made
- Mock create raising exception → assert function returns without raising

#### `test_index_image_helper`

Location: `argus/backend/tests/test_stats_snapshot.py`

- Mock SCT run with valid `cloud_setup.db_node.image_id` → assert `ReleaseDistinctImages.if_not_exists().create()` called
- Mock run with `cloud_setup=None` → assert no DB call
- Mock run with `db_node=None` → assert no DB call
- Mock run with `image_id=None` → assert no DB call

---

### Integration Tests

#### `test_stats_cache_miss_then_hit`

Location: `argus/backend/tests/test_stats_snapshot.py`

Setup: empty `argus_release_stats_snapshot` table, seeded release with known runs.

1. Call `ReleaseStatsCollector("seed-release").collect(force=False)` → verify slow path executed (full fan-out), snapshot row written to DB
2. Call same collector again with `force=False` → verify snapshot row read, result identical to step 1, no fan-out queries executed (mock/spy the fan-out)
3. Assert `ReleaseStatsSnapshot.get(release_id, filter_key)` returns the row written in step 1

#### `test_stats_force_bypasses_cache`

1. Write a stale snapshot row with known bogus payload directly to DB
2. Call `collect(force=True)` → verify result does NOT match bogus payload (real data returned)
3. Verify snapshot row overwritten with fresh data

#### `test_stats_force_writes_fresh_snapshot`

1. Call `collect(force=True)` → snapshot written
2. Call `collect(force=False)` → snapshot served (proves force still populates cache)

#### `test_different_filter_keys_cached_separately`

1. Call `collect(release_version="5.2", force=False)` → snapshot written with key `v=5.2::...`
2. Call `collect(release_version="5.3", force=False)` → snapshot written with key `v=5.3::...`
3. Assert two distinct rows exist in `argus_release_stats_snapshot` for the same `release_id`
4. Assert each returns the correct version-filtered result

#### `test_finish_run_invalidates_only_matching_version`

Location: `argus/backend/tests/test_stats_snapshot.py`

Setup: pre-write snapshot rows for multiple versions:

- `v=5.6.1::img=::nov=1::lim=0`
- `v=5.7.0::img=::nov=1::lim=0`
- `v=::img=::nov=1::lim=0`

Steps:

1. Call `finish_run()` with a run carrying `scylla_version="5.6.1"`
2. Assert `v=5.6.1::*` snapshot is deleted
3. Assert `v=::*` (all-versions) snapshot is deleted
4. Assert `v=5.7.0::*` snapshot is **still present** (unaffected version)
5. Assert `ReleaseDistinctVersions` row written for `5.6.1`

#### `test_submit_run_also_invalidates`

Setup: pre-write snapshot for a release.

1. Call `submit_run()` with a run carrying `scylla_version="5.6.1"`
2. Assert `v=5.6.1::*` and `v=::*` snapshots are deleted
3. Assert `v=<other>::*` snapshots are untouched

#### `test_new_run_appears_after_invalidation`

Location: `argus/backend/tests/test_stats_snapshot.py`

This is the critical stale-data test.

1. Seed release with N runs for version `5.6.1` → call `collect(release_version="5.6.1", force=False)` → snapshot written, assert run count = N
2. Also call `collect(release_version=None, force=False)` → all-versions snapshot written
3. Submit a new run via `submit_run()` + `finish_run()` with `scylla_version="5.6.1"`
4. Assert `v=5.6.1::*` and `v=::*` snapshots deleted
5. Call `collect(release_version="5.6.1", force=False)` → cache miss, recompute
6. Assert run count in result = N+1 (new run visible)
7. Call same again → cache hit, run count still N+1

#### `test_unaffected_version_cache_stays_warm`

This is the key regression test for the targeted invalidation improvement.

1. Seed release with runs for `5.6.1` and `5.7.0`
2. Warm both version snapshots: `collect("5.6.1")`, `collect("5.7.0")`
3. Submit and finish a new run with `scylla_version="5.6.1"`
4. Assert `v=5.7.0::*` snapshot is **still present** in DB (was not deleted)
5. Call `collect("5.7.0", force=False)` → assert it serves from cache (no fan-out), response time < 50ms
6. Call `collect("5.6.1", force=False)` → assert cache miss (fan-out executed), then snapshot re-written

#### `test_run_from_different_release_does_not_invalidate`

Setup: two releases A and B, each with a snapshot.

1. Call `finish_run()` with a run belonging to release A
2. Assert release A's matching snapshots are deleted
3. Assert release B's snapshots are untouched

#### `test_dormant_release_snapshot_persists`

1. Set release `dormant=True`
2. Call `collect(force=False)` → snapshot written
3. Do NOT call `finish_run()` (no active runs)
4. Call `collect(force=False)` 5 more times → assert same snapshot row returned each time (no recompute)

---

### Regression Tests

#### `test_versions_endpoint_returns_correct_values`

Location: `argus/backend/tests/test_argus_service.py`

- Backfill `ReleaseDistinctVersions` with known set
- Assert `get_distinct_release_versions(release_id)` returns exactly those values, sorted descending
- Drop all rows from `ReleaseDistinctVersions` partition → assert fallback to GSI scan returns same values

#### `test_images_endpoint_returns_correct_values`

- Backfill `ReleaseDistinctImages` with known set
- Assert `get_distinct_release_images(release_id)` returns exactly those values
- Drop all rows from `ReleaseDistinctImages` partition → assert fallback to GSI scan returns same values

#### `test_backfill_idempotent`

- Run `migration_2026-04-22.migrate()` twice on the same data
- Assert row counts unchanged after second run (second call exits early on idempotency check)
- Assert no LWT exceptions raised

#### `test_delete_release_cleans_up_indexes`

- Create release with versions/images indexed and a snapshot cached
- Call `delete_release()`
- Assert `ReleaseDistinctVersions` partition empty
- Assert `ReleaseDistinctImages` partition empty
- Assert `ReleaseStatsSnapshot` partition empty

---

## Operational Notes

### Running the Backfill

After deploying to an existing environment, run the migration script to populate the index tables:

```bash
CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 uv run scripts/migration/migration_2026-04-22.py
```

The script checks whether `ReleaseDistinctVersions` already contains any rows and exits immediately if so — safe to re-run at any time.

### Warming the Cache

The snapshot cache is populated lazily on first request. For high-traffic releases, the cache can be pre-warmed after deployment by hitting the stats endpoint once per release:

```bash
curl "https://<host>/api/v1/release/stats/v2?release=<name>&limited=0&includeNoVersion=1&force=0" \
  -H "Authorization: token <token>"
```

### Monitoring Stale Data

Signs that the snapshot cache contains stale data:

- A run completed but does not appear in the dashboard → check `finish_run()` logs for invalidation failures
- Run count in dashboard does not match DB → manually invalidate with `?force=1` on the stats URL

To force a full cache refresh for a release:

```
GET /api/v1/release/stats/v2?release=<name>&force=1&limited=0&includeNoVersion=1
```
