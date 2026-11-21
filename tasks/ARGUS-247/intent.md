# ARGUS-247 — Serve release dashboards and views from one cached path

## Problem

The release dashboard and the view dashboard render the same test-grid UI, but they run
on two backend paths. A release reads its stats from a snapshot and its versions and
images from an index. A view recomputes all of it on every request.

On `/view/scylla-master-master-duty`, each request to `GET /api/v1/views/stats`
fans out to every plugin and reads the run partitions of every test in the view.
`GET /api/v1/views/<id>/versions` and `/images` scan the same runs. A view with several
Test Dashboard widgets repeats the whole set once per widget.

The cost is the database read, not the aggregation. It grows with the number of runs
stored under the view's tests, while the release path stays flat.

Measured on a local single-node ScyllaDB, one uvicorn worker, warm, 157k runs
(4 releases, 600 tests, about 260 runs per test):

| Request | View, 150 tests | View, 600 tests | Release, 150 tests |
|---|---|---|---|
| stats | 0.5–0.9 s | 3.8–5.9 s | 8–13 ms (snapshot hit) |
| stats, version filter | 0.5–0.6 s | 1.7–2.4 s | 5 ms |
| stats, one widget | not run | 1.9–3.8 s | not run |
| versions | 0.45–0.54 s | 1.6–1.75 s | 3–6 ms |
| images | 0.6–0.8 s | 2.2–2.4 s | about 3 ms |

- Page load with 3 widgets (stats, versions and images each): 5.6–20 s for the broad
  view, about 0.1 s for the release.
- The gap grows with run count. At 18k runs the same broad view took 0.2–0.5 s for
  stats, so a fixed "Nx" figure misstates it. The ratio was about 6–30x at 18k runs and
  is about 500x for one stats call at 157k runs.
- Of a 1.8–3.6 s broad stats request, the read is 1.8–3.6 s and the aggregation is
  25–78 ms. Reads are the cost.
- The release path is not faster code. An uncached release read (`force=1`) takes
  0.5–0.6 s, the same as the equivalent 150-test view. The snapshot and the version and
  image indexes are the whole difference.

The two paths also mean each dashboard feature is built twice.

## Who it affects

Whoever opens a view, most of all a broad view that spans several high-traffic releases
and carries more than one Test Dashboard widget. Also the developer who adds a dashboard
feature and has to write it for both paths.

## Evidence

- `ViewStatsCollector.collect()` has no snapshot read or write. `ReleaseStatsCollector.collect()`
  has both.
- `UserViewService.get_versions_for_view` and `get_images_for_view` resolve every test and
  scan the plugin tables per call. `get_distinct_product_versions` and
  `get_distinct_cloud_images_for_release` read the `ReleaseDistinctVersions` and
  `ReleaseDistinctImages` indexes. The image index exists for the SCT plugin only.
- `ViewStats` and `ReleaseStats` in `argus/backend/service/stats.py` are near-duplicate
  aggregation classes. `GroupStats` and `TestStats` are already shared.
- `frontend/ReleaseDashboard/TestDashboard.svelte` already runs in both modes
  (`PANEL_MODES.release` and `PANEL_MODES.view`).
- `planner_service.py` already builds a real view from `githubIssues`, `releaseStats` and
  `testDashboard`, which is the release dashboard's composition.
- `ViewDashboard.svelte` caches `resolve/tests` only after the request resolves, so
  filtered widgets that load together each send their own request. That request costs
  15–22 ms, so it is a small part of the total.
- View stats vary by more than version and image. A widget's `filter`, its
  `configParamFilters` and the `paramFilterOff` query parameter change the row set, and
  a param filter also widens the per-partition read from 15 to 50 runs.

## What good looks like

A view reads its stats, versions and images from cache and answers a version-filtered or
widget-scoped read in well under 50 ms once warm, at the run volume above.

A view's versions and images come from the per-release indexes, not from a scan of its
runs.

The cache key identifies the effective read: version, image, the no-version flag, the
limited flag, and the widget scope (test filter and param filters). A read never
returns data for a different scope.

A finished run drops only the cached entries of the views that contain its test, and
only for its version. Other versions and other views stay warm. A plan, issue, comment,
link or view-membership change drops the entries it affects.

A view loads its tests once, however many filtered widgets it has.

`/dashboard/<release_name>` keeps its URL and its look, and is served by the same path as
a view. There is one stats implementation behind both.

The unfiltered aggregate of a broad, high-churn view cannot stay warm, because any member
run invalidates it. That read is outside the warm-latency goal.

## Delivery order

1. Versions and images from the per-release indexes. It removes two of the three
   request types per widget, needs no invalidation design, and the gain is 1.6–2.4 s
   to milliseconds on the broad view.
2. Memoize the in-flight `resolve/tests` request in `ViewDashboard.svelte`.
3. View stats snapshot with the widget-scope key and view-scoped invalidation.
4. One stats implementation behind release and view.

## Open questions for the spec

- A `test_id -> view_ids` reverse index, or a scan of all views on every run finish.
  Run finish is the hot path and invalidation cost is unmeasured. The spec decides
  with a measurement.
- Whether a widget with param filters is cached under a scope hash or left uncached.
  These widgets have the widest reads.
- A view built from individual tests or groups has versions and images that are a subset
  of its releases' indexes. The spec states whether an over-approximation is accepted.
- The image index covers SCT only. The spec states the answer for other plugins.

## Out of scope

- Changing the response shape of `/api/v1/release/stats/v2` or `/api/v1/views/stats`.
- New widget types beyond the release activity feed.

## Measurement notes

The numbers come from one local node, not production, which runs four workers on a
cluster. Absolute values will differ. The split between read cost and aggregation cost,
and the growth with run count, are the findings to rely on. The seed and measurement
scripts are not part of the repository.
