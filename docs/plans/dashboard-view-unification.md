---
status: draft
domain: backend
created: 2026-06-18
last_updated: 2026-06-18
owner: null
---

# Release Dashboard / Views Unification

## 1. Problem Statement

The release dashboard and the Views dashboard render the same test-grid UI but run on
divergent backend paths. Release stats are cached and indexed; view stats are not.

Measured/observed pain (single test-dashboard widget, page `/view/scylla-master-master-duty`):

- `GET /api/v1/views/stats` recomputes on every request — full plugin fan-out, no snapshot.
- `GET /api/v1/views/<id>/versions` and `/images` scan resolved tests every request.
- View pages multiply this work per widget; multiple test-dashboard widgets repeat the full fetch set.

Release equivalents serve from cache in ~5–12ms (per `docs/plans/dashboard-performance-optimization.md`),
so a view that is functionally "a release dashboard over a chosen test set" can be ~100x slower.

Two code paths also mean every future dashboard feature must be built twice.

## 2. Current State

### Backend — stats

- `argus/backend/service/stats.py:532-611` `ReleaseStatsCollector.collect()` — snapshot read (`:545-550`), fan-out, filter, snapshot write (`:600-607`).
- `argus/backend/service/stats.py:614-665` `ViewStatsCollector.collect()` — resolves `view.tests`, optional `widget_id` narrowing (`:627-636`), fan-out, filter; **no snapshot path**.
- `argus/backend/service/stats.py:198-241` `ViewStats` and `:295-336` `ReleaseStats` — near-duplicate aggregation classes; `GroupStats`/`TestStats` (`:379-529`) already shared.
- `snapshot_filter_key()` `argus/backend/service/stats.py:25-26` — already scope-agnostic.

### Backend — endpoints

- `argus/backend/controller/api.py:488-510` `GET /api/v1/release/stats/v2`.
- `argus/backend/controller/view_api.py:137-158` `GET /api/v1/views/stats` (adds `viewId`, `widgetId`).
- `argus/backend/controller/view_api.py:161-180` view versions/images.
- `argus/backend/controller/api.py` release versions/images via `argus/backend/service/argus_service.py:170-183`.

### Backend — cache / index models

- `argus/backend/models/web.py:401-406` `ReleaseStatsSnapshot` (keyed `release_id + filter_key`).
- `argus/backend/models/web.py:409-424` `ReleaseDistinctVersions` / `ReleaseDistinctImages`.
- `argus/backend/models/web.py:430-443` `invalidate_release_snapshots()`; targeted variant in `argus/backend/plugins/core.py:282-301`.
- ~30 invalidation call sites by `release_id` across `argus/backend/service/testrun.py`, `github_service.py`, `jira_service.py`, `planner_service.py`, `release_manager.py`.

### Backend — view resolution

- `argus/backend/service/views.py:129-205` resolve tests, versions, images.
- `ArgusUserView` model `argus/backend/models/web.py:182-194` (`tests`, `release_ids`, `group_ids`, `widget_settings`).

### Frontend

- `frontend/ReleaseDashboard/ReleaseDashboard.svelte:62-136` — fixed layout: Issues + ReleaseStats + TestDashboard + ReleaseActivity.
- `frontend/Views/ViewDashboard.svelte:131-151` — renders `widget_settings` via `WIDGET_TYPES`.
- `frontend/ReleaseDashboard/TestDashboard.svelte:100-111` — already dual-mode via `PANEL_MODES.release/.view`; `:245-306` stats fetch; `:339-390` versions/images; `:484-490` auto-refresh.
- `frontend/Common/ViewTypes.js:31-204` `WIDGET_TYPES`; includes `testDashboard`, `releaseStats`, `githubIssues`.
- `frontend/Views/ViewDashboard.svelte:40-52` `resolveViewTests()` caches only after fetch resolves (in-flight race for filtered widgets).

### Proof the release dashboard is already a view

- `argus/backend/service/planner_service.py:108-138` `VIEW_WIDGET_SETTINGS` builds a real view with `githubIssues` + `releaseStats` + `testDashboard` — identical to the release dashboard composition. `create_view_for_plan()`/`update_view_for_plan()` (`:296-357`) already auto-create/maintain system views.
- Pages: `argus/backend/controller/main.py:89-96` (view) and `:117-128` (release).

## 3. Goals

1. One backend stats implementation serves both scopes; `ReleaseStatsCollector` and `ViewStatsCollector` become thin adapters over a shared collector (no duplicated fan-out/aggregation logic).
2. View stats are cached: warm `GET /api/v1/views/stats` returns in <50ms locally for version-filtered and widget-scoped reads (parity target with release warm path), down from full recompute. The unfiltered aggregate (`v=::*`) of a high-churn broad view is exempt — see the Performance Model.
3. View distinct versions/images served from index data: warm `GET /api/v1/views/<id>/versions` and `/images` in <50ms locally, via union of `ReleaseDistinctVersions`/`ReleaseDistinctImages`.
4. View snapshots invalidate version-scoped per affected view; an unaffected version/view stays warm after a run finishes (regression-tested).
5. `/dashboard/<release_name>` renders through the unified view path with no visible UI regression and an unchanged URL.
6. Frontend issues exactly one `resolve/tests` request per view load regardless of filtered-widget count.
7. No behavior change for release dashboards: response payload shape and timings preserved (existing release snapshot tests still pass).

## 4. Implementation Phases

Phases are ordered by dependency. Phase A is internal only — no URL or UI change. Phase B
unifies rendering and the remaining paths and depends on Phase A being complete.

### PHASE A — Internal unification (no UI/URL change)

#### A1. Generic scoped snapshot store

**Importance:** Critical

- New model `StatsSnapshot` in `argus/backend/models/web.py`: `scope_type` (TEXT) + `scope_id` (UUID) partition key; `filter_key` (TEXT) + `variant_key` (TEXT) clustering keys; `payload` (TEXT); `generated_at` (TIMESTAMP).
- New `argus/backend/service/stats_snapshot.py`: `get/put/invalidate(scope_type, scope_id, ...)` helpers.
- Register the model in `USED_MODELS` (`argus/backend/models/web.py:446`).
- Keep `ReleaseStatsSnapshot` intact this phase (parallel table, no migration yet).

**Definition of Done:**

- [ ] Model + store added; `CQLENG_ALLOW_SCHEMA_MANAGEMENT=1` creates the table.
- [ ] Unit tests for key composition + get/put/invalidate.
- [ ] `uv run ruff check` clean.

#### A2. Extract shared collector pipeline

**Importance:** Critical

- New `ScopedStatsCollector` encapsulating the common pipeline: resolve tests -> group `build_system_id` by plugin -> `get_stats_for_release()` fan-out -> version/image filter (`argus/backend/service/stats.py:563-588` and `:642-656`) -> build stats.
- Parameterize by a `Scope` object (release vs view) that supplies: the test set, the scope id, payload extras (`perpetual`/`enabled`/`valid_version_regex` for release; neutral defaults for view), and an optional widget filter.
- `ReleaseStatsCollector` and `ViewStatsCollector` delegate to it; **no endpoint/signature changes**.

**Definition of Done:**

- [ ] Both collectors delegate to the shared pipeline; duplicated fan-out/aggregation removed.
- [ ] Existing release snapshot tests (`argus/backend/tests/test_stats_snapshot.py`) pass unchanged.
- [ ] Output dicts byte-identical for a fixture release and a fixture view (golden test).

#### A3. View stats caching + version-scoped invalidation

**Importance:** Critical

- `ViewStatsCollector` reads/writes `StatsSnapshot(scope_type="view")` keyed by `filter_key` plus `variant_key="widget:<id>"` (empty variant for the whole-view stats); `force` bypasses the read.
- **No new public invalidation entry point.** Callers keep calling the two existing functions; both are extended to invalidate the view scope internally so every current call site covers release + view with no edits:
  - `invalidate_release_snapshots(release_id)` (`argus/backend/models/web.py:430-443`) — after the release-partition wipe, resolve affected views and full-wipe their `scope_type="view"` partitions (structural/metadata changes).
  - `PluginModelBase.invalidate_release_snapshot()` (`argus/backend/plugins/core.py:282-293`) — after the version-scoped release delete, apply the same version-scoped delete (`v=<version>::*` plus `v=::*`) to affected views (run submit/finish).
- **Invalidate on the most precise key the event carries, not on `release_id` alone.** Run/data events are per-test (e.g. `invalidate_release_snapshots(test.release_id)` at `argus/backend/service/testrun.py:170` is really a `test.id` event); structural events are release/group level (e.g. `delete_group` at `argus/backend/service/release_manager.py:123`). Keying view invalidation on `release_id` is too coarse for per-test events — it would drop snapshots for views that include the release through other, unchanged tests.
- **Single set-based resolver, not three overloads.** Everything reduces to "a set of changed `test_id`s, and a view is affected iff its test set intersects it" (a view is resolved purely through `view.tests`, `argus/backend/service/stats.py:632-636`). The one new function is:
  - `affected_view_ids(test_ids: set[UUID]) -> set[UUID]` — views whose `tests` intersect `test_ids`.
  - Each event computes its own `test_ids`: run/status/issue/comment events pass `{test_id}` directly (no expansion on the hot path); structural events expand `group_id`/`release_id` → tests via the indexed `ArgusTest.filter(group_id=...)`/`filter(release_id=...)` (`group_id`/`release_id` are `index=True`, `argus/backend/models/web.py:200-201`).
- **Hybrid rule (precision + soundness):** per-run events stay `{test_id}` (frequent, cheap, no expansion); structural events expand to tests **and** additionally union views matching by `release_ids`/`group_ids` membership as the staleness fallback below.
- **Why the membership fallback is still needed:** `view.tests` is a lazily-refreshed flattened snapshot (`refresh_stale_view`, `argus/backend/service/views.py:146-163`). A test added after the last refresh exists on the live event side but not yet in `view.tests`, so a pure `test_id` intersection would miss it. Unioning structural membership for structural events closes that window. Over-invalidation here is safe (costs a recompute); under-invalidation would serve stale data.
- **Reverse-lookup strategy — scan first (v1).** `affected_view_ids` scans `ArgusUserView` and intersects each view's `tests`. This is the dominant per-event cost; it is acceptable at current view counts and is the simplest correct implementation. A `test_id -> view_ids` reverse-index table is the scalable fast-follow (constant-time lookup, cost amortized to rare view edits) — deferred until A6 metrics justify it. See the Performance Model below.

**Definition of Done:**

- [ ] Cold view stats request writes a snapshot; warm request serves it (<50ms local).
- [ ] Existing call sites unchanged: invalidating a release also invalidates its views via the same two functions (no parallel `invalidate_view_*` method added).
- [ ] Single set-based `affected_view_ids(test_ids)` is the only new resolver (no per-key overloads).
- [ ] Per-run events pass `{test_id}` (no release→tests expansion on the hot path); structural events expand via indexed `group_id`/`release_id` queries.
- [ ] Per-test events invalidate only views containing that `test_id` (plus the staleness fallback), not every view referencing the release (test).
- [ ] Finishing a run for version X invalidates only X + aggregate for affected views; unaffected version stays warm (integration test).
- [ ] A run for a test not contained in a view does not invalidate that view (test).
- [ ] Structural events union the precise test-set match with `release_ids`/`group_ids` membership to cover not-yet-refreshed `view.tests`.
- [ ] View snapshot partition dropped on view update/refresh (`update_view`/`refresh_stale_view`, `argus/backend/service/views.py:77-101,146-163`).

#### A4. View versions/images via union of release indexes

**Importance:** Important

- `get_versions_for_view`/`get_images_for_view` (`argus/backend/service/views.py:194-205`) compute the set of release ids for the view (from `release_ids` plus releases derived from `group_ids`/`tests`) and union the `ReleaseDistinctVersions`/`ReleaseDistinctImages` partitions; fall back to the current fan-out when the index is empty (parity with the SCT read path in `argus/backend/plugins/sct/testrun.py:223-259`).

**Definition of Done:**

- [ ] Warm view versions/images <50ms local.
- [ ] Empty-index fallback returns the same values as the fan-out (test).

#### A5. Frontend: dedupe `resolve/tests`

**Importance:** Important

- In `frontend/Views/ViewDashboard.svelte`, cache the in-flight promise (not just the resolved array) so concurrent filtered widgets share a single request.

**Definition of Done:**

- [ ] One `GET /api/v1/views/<id>/resolve/tests` per load with N filtered widgets (manual network check).

#### A6. Invalidation instrumentation + scan→index decision gate

**Importance:** Important

- Instrument `affected_view_ids` and the view-invalidation path: record per-event resolver duration and the count of views scanned/affected; record view-snapshot cache hit/miss per `filter_key` class (aggregate `v=::*` vs version-scoped `v=<ver>::*` vs widget variant).
- Define a decision gate: if median per-event resolver time exceeds a threshold (e.g. >25ms) or write-path read volume becomes material under production-like ingest, implement the `test_id -> view_ids` reverse-index table as a follow-up; otherwise keep the scan.

**Definition of Done:**

- [ ] Metrics emitted for resolver duration, views scanned/affected, and per-key-class hit rate.
- [ ] Documented threshold and go/no-go criterion for building the reverse-index table.
- [ ] Broad multi-release view aggregate (`v=::*`) hit-rate captured as the key bottleneck metric.

### Performance Model (Phase A invalidation)

Invalidation runs on the **write path**; the hot path is runs (`submit_run()` + `finish_run()` = 2 events/run, `argus/backend/plugins/core.py:282`). Structural events are rare and not performance-relevant.

Per-run event cost components:

| Component | Cost | Notes |
| --------- | ---- | ----- |
| Release snapshot delete | Single partition scan, ~O(10) rows | Exists today (`argus/backend/models/web.py:440`); unchanged |
| **Reverse lookup `test_id -> view_ids`** | **Dominant.** Scan: O(N_views) row reads + `tests` list deserialization. Index: ~O(1) partition read | Set by scan-vs-index (A6), not by the hybrid rule |
| Expansion (group/release → tests) | Skipped on run events; indexed query on structural events | Hybrid passes `{test_id}` on the hot path |
| View snapshot deletes | Version-scoped, few keys per affected view | Hybrid minimizes over-invalidation |

The hybrid's wins are no hot-path expansion and minimal deletes; the **reverse lookup dominates** and is governed by the scan-vs-index choice (A6 gate). Scan is acceptable at current view counts; the reverse-index is the scalable upgrade.

**True ceiling — broad multi-release views:** a view spanning many high-traffic releases (e.g. `scylla-master-master-duty`) has its all-versions aggregate key `v=::*` invalidated whenever *any* member run finishes, so that key is effectively never warm and is recomputed on most loads. No invalidation strategy fixes this — it is inherent to caching a constantly-changing aggregate. **Version-scoped keys** (`v=<ver>::*`) and **widget variants** still stay warm and deliver the cache benefit. The "<50ms warm" goal is realistic for version-filtered/narrow reads, not guaranteed for the unfiltered aggregate of a high-churn broad view (tracked via A6).

#### A7. Cache architecture documentation + diagrams

**Importance:** Important

- Author `docs/architecture/dashboard-view-cache.md` describing the unified caching model end to end so future contributors understand reads, writes, and invalidation without reverse-engineering `stats.py`.
- Content to cover:
  - The two scopes (release, view) and why they share one collector and one `StatsSnapshot` store (`scope_type`/`scope_id`/`filter_key`/`variant_key`).
  - The `filter_key`/`variant_key` grammar and worked examples (`v=5.6.1::img=::nov=1::lim=0`, `variant=widget:3`).
  - The read path (cache hit vs miss → fan-out → snapshot write).
  - The write/invalidation path: the single set-based `affected_view_ids(test_ids)` resolver, the hybrid hot-path (`{test_id}`) vs structural-event expansion, and the staleness fallback.
  - The Performance Model summary and the broad-view aggregate ceiling.
  - The underlying data fact that drives design: run table is partitioned by `build_id` with `PER PARTITION LIMIT 15` (`argus/backend/plugins/sct/testrun.py:206-208`).
- Include Mermaid diagrams (render on GitHub):
  - A **component/data-flow diagram**: UI → stats endpoint → shared collector → `StatsSnapshot` (hit) / plugin fan-out (miss); CI run → plugin model → release + view invalidation via `affected_view_ids`.
  - A **sequence diagram** for cache miss → compute → write, and a second for run-finish → invalidate.
  - An **ER/relationship diagram**: `ArgusRelease`/`ArgusUserView`/`ArgusTest` ↔ `StatsSnapshot` (+ `ReleaseDistinctVersions`/`ReleaseDistinctImages`).
- Link the new doc from `docs/plans/dashboard-performance-optimization.md` and from this plan; note it must be updated if the storage migration (B4) lands.

**Definition of Done:**

- [ ] `docs/architecture/dashboard-view-cache.md` exists and covers read path, write/invalidation path, key grammar, and performance model.
- [ ] At least the data-flow diagram, one sequence diagram, and the relationship diagram are present as Mermaid and render on GitHub.
- [ ] Diagrams reference real models/functions (`StatsSnapshot`, `affected_view_ids`, `ReleaseStatsCollector`/`ViewStatsCollector`) — no invented names.
- [ ] Cross-linked from `docs/plans/dashboard-performance-optimization.md` and this plan.
- [ ] Markdown passes the repo's doc conventions (kebab-case filename, `#` H1 title).

### PHASE B — UI / path unification

Depends on Phase A. Keeps the bespoke release path live until parity is verified.

#### B1. System view per release (lazy, maintained)

**Importance:** Critical

- Add a `ReleaseSystemViewService` (reusing the `planner_service` auto-view patterns) that lazily creates/updates a system-owned `ArgusUserView` per release: tests = `release_id` tests, layout = `githubIssues` + `releaseStats` + `testDashboard` (+ `releaseActivity` once widgetized in B2).
- Mark the view as a system view (see Needs Investigation B1) so it is hidden from user view lists (`argus/backend/controller/main.py:84-86`) and skipped by user-edit guards (`argus/backend/service/views.py:79-80, 106-107`).

**Definition of Done:**

- [ ] First `/dashboard/<name>` access creates/refreshes the system view idempotently.
- [ ] System view excluded from `/views` listing; not user-deletable.

#### B2. ReleaseActivity as a widget (parity gap)

**Importance:** Important

- Add a `releaseActivity` widget type (`frontend/Common/ViewTypes.js` + a `Views/Widgets` wrapper component) so the release layout is fully expressible as widgets. **Needs Investigation:** confirm the `ReleaseActivity` data source is release-scoped only.

**Definition of Done:**

- [ ] Activity renders inside a view widget with no regression vs `frontend/ReleaseDashboard/ReleaseDashboard.svelte:134-136`.

#### B3. Route `/dashboard/<release_name>` through ViewDashboard

**Importance:** Critical

- `argus/backend/controller/main.py:117-128` resolves/creates the release system view and renders `view_dashboard.html.j2` (or a thin release shell embedding `ViewDashboard`), preserving the URL and page title.
- Keep `release_dashboard.html.j2`/`ReleaseDashboard.svelte` until parity is verified, then remove in B5.

**Definition of Done:**

- [ ] `/dashboard/<name>` shows issues + stats + grid + activity, served by the unified stats path.
- [ ] Manual parity check vs the current dashboard (groups, statuses, version filter, image filter).

#### B4. Migrate release snapshot storage to the generic store

**Importance:** Important

- Point the release collector at `StatsSnapshot(scope_type="release")`; update the ~30 `invalidate_release_snapshots()` call sites to the generic invalidator (keep the function name as a shim delegating to the store).
- Dual-read window: read the generic store first, fall back to legacy `ReleaseStatsSnapshot` until confident; drop the legacy model in a follow-up.

**Definition of Done:**

- [ ] Release stats cache hits/invalidation behave as before via the generic store (existing tests pass).
- [ ] No remaining direct references to `ReleaseStatsSnapshot` except the compat shim.

#### B5. Remove the bespoke release dashboard path

**Importance:** Nice-to-have

- Delete `frontend/ReleaseDashboard/ReleaseDashboard.svelte`, `templates/release_dashboard.html.j2`, and `frontend/release-dashboard.js` once B3 parity holds; update `vite.config.ts` entries.

**Definition of Done:**

- [ ] Build succeeds without the removed entrypoints; `/dashboard/<name>` still works.

#### B6. Documentation

**Importance:** Important

- Update the architecture doc authored in A7 (`docs/architecture/dashboard-view-cache.md`) to reflect Phase B: the release-as-system-view rendering path, the generic-store storage migration (B4), and removal of the bespoke release path (B5). Refresh the diagrams accordingly.
- Update `docs/plans/dashboard-performance-optimization.md` cross-reference.

**Definition of Done:**

- [ ] A7 architecture doc updated for the unified rendering path, generic snapshot store, and view invalidation; diagrams reflect Phase B end state.
- [ ] `docs/plans/dashboard-performance-optimization.md` links the architecture doc.

## 5. Testing Requirements

### Unit (`argus/backend/tests/`)

- Snapshot store key/get/put/invalidate; `snapshot_filter_key` reuse.
- Shared collector golden test: release vs view dicts unchanged vs current output.
- View reverse-lookup invalidation selects exactly the affected views.
- Versions/images union + empty-index fallback.

### Integration (Docker ScyllaDB, `@pytest.mark.docker_required`)

- View cache miss -> hit; `force` bypass; version-scoped invalidation keeps other versions/views warm.
- Release behavior unchanged after migration to the generic store (reuse `test_stats_snapshot.py` scenarios against the new store).
- System-view creation idempotency; cleanup on release/view delete (extend `release_manager.delete_release`).

### Manual

- `/dashboard/<name>` vs `/view/<name>`: identical grid, filters, timings warm.
- Network panel: one `resolve/tests` per view load; warm stats/versions/images <50ms.
- Multi-test-dashboard view: no duplicated base fetches beyond per-widget stats.

### Documentation

- A7 architecture doc renders on GitHub: Mermaid diagrams display, links resolve, and described models/functions exist in the codebase.

## 6. Success Criteria

- All Phase A and Phase B Definition of Done items satisfied.
- Goals 1–7 met; warm view endpoints reach the parity thresholds (Goals 2–3).
- Existing release snapshot test suite green against the generic store (Goal 7).
- `/dashboard/<name>` served by the unified path with no UI regression (Goal 5).
- Plan-level: no endpoint contract change to `/api/v1/release/stats/v2` or `/api/v1/views/stats` response shapes (clients unaffected).

## 7. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Stale view cache after a run finishes | Medium | High | Version-scoped invalidation tested; `force` refresh button; coarse full-view fallback if reverse-lookup misses |
| Reverse view lookup misses a membership path (tests added via group/release) | Medium | High | Single set-based `affected_view_ids(test_ids)`: per-run `{test_id}` match **unioned with** `release_ids`/`group_ids` membership for structural events to cover not-yet-refreshed `view.tests`; integration test covering all three paths |
| Invalidation write-path cost grows with view count (scan) | Medium | Medium | A6 instruments resolver duration/views scanned; documented threshold gates building the `test_id -> view_ids` reverse-index table |
| Broad multi-release view aggregate never warms (`v=::*` constantly invalidated) | High | Medium | Inherent to high-churn aggregates; version-scoped keys and widget variants still serve from cache; A6 tracks per-key hit-rate; `<50ms` goal scoped to version-filtered/narrow reads |
| Payload divergence breaks release UI (`perpetual`/`enabled`/`valid_version_regex`) | Medium | High | Golden byte-identical test in A2; release scope supplies these fields explicitly |
| System-view sprawl / user confusion | Medium | Medium | System flag, hidden from listings, idempotent create, cleanup on delete |
| Generic-store migration drops release cache hits | Low | Medium | Dual-read window (generic then legacy) before removing the legacy model |
| `ReleaseActivity` not fully release-scoped | Low | Medium | Marked Needs Investigation in B2 before widgetizing |
| Snapshot payload size growth (per-view variants) | Low | Medium | Same JSON-blob approach as release; monitor partition row counts |

## Needs Investigation

- **B2:** Confirm `ReleaseActivity` data is release-scoped only (no cross-release assumptions) before turning it into a widget.
- **B1:** Exact "system view" marker — reuse a `plan_id`-style ownership convention vs adding a new boolean column on `ArgusUserView`.
