# ARGUS-218 — implementation plan

**Spec:** `tasks/ARGUS-218/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Follow `docs/standards/backend/` for the router, service and model split,
  `docs/standards/frontend/components.md` for the Svelte 5 runes and the
  entry-point registration, and `docs/standards/frontend/css.md` for the
  Bootstrap-first styling and the self-contained color pair on a badge.
- The mapper is async: every model imports `coodie.aio.Document` and every
  query is awaited.
- A service raises `DataValidationError`; every API failure stays inside the
  HTTP 200 envelope.
- No module under `argus/backend/service/` imports an SCT plugin module at
  module level. Plugin-specific data comes through hooks on `PluginModelBase`.
- A rollup write sits inside the `except (DriverException, NoHostAvailable)`
  guard `ClientService.finish_run` uses, so a client call never fails on it.
- Backend tests create runs through `ClientService.submit_run`, resources
  through `SCTService`, and cost through `RunCostService`, never through a
  model `save()` in the test body. Explorer tests seed `RunCostRollup` rows
  through `CostRollupService.refresh` where a run exists, and directly only
  for the pure fold cases that need many rows.
- Run the verify sequence from the `Commands` section of `CLAUDE.md` before
  each commit; `yarn build` for a frontend task.

## Task 1 — The rollup table, the plugin hooks and the rollup service

**Files:**
- Create: `argus/backend/models/run_cost_rollup.py`
- Modify: `argus/backend/models/web.py`, the import block and `USED_MODELS`
- Modify: `argus/backend/plugins/core.py`, `PluginModelBase`
- Modify: `argus/backend/plugins/sct/testrun.py`, `SCTTestRun`
- Create: `argus/backend/service/cost_rollup_service.py`
- Modify: `argus/backend/service/run_cost_service.py`, the lookup and `refresh_rollup`
- Test: `argus/backend/tests/cost_rollup/test_cost_rollup_service.py`

**Internals:** `UNASSIGNED_RELEASE = UUID(int=0)` and `RunCostRollup` in the
table `run_cost_by_month_v1`, as the spec declares it. `ROLLUP_COLUMNS` and the
hooks `PluginModelBase.cost_rollup_columns()` and
`PluginModelBase.cost_rollup_fields(item_names)`, the base returning the common
columns and an empty dict. The `SCTTestRun` overrides: the columns add
`cloud_setup`, `sct_runner_host`, `region_name`; the fields read
`SCTResource.find(run_id=self.id).only("name", "resource_type")` and the
`event_type` of the run's `CRITICAL` events, drop a resource whose type is
`sct-runner` or whose name contains it, and return `backend`, `region`,
`spot_terminated` (a `SpotTerminationEvent` among the critical events),
`resource_count`, `priced_count`.
`RunCostReleaseSpan` in `run_cost_release_span_v1`, widened by
`CostRollupService.extend_span(release_id, start_time)` after every save.
`CostRollupService.refresh(run)`, `month_of(dt)` (naive → UTC,
`strftime("%Y-%m")`), `_tier_sums(items)` with `math.fsum`, and
`coverage(resource_count, priced_count, item_count)`.
`RunCostService.refresh_rollup(run_id)` and `_find_run(run_id)`
(`asyncio.gather` of `model.find(id=run_id).only(*cols).first()` over
`AVAILABLE_PLUGINS`, imported at module level; the module sits outside the
plugin graph).

- [x] Write the failing tests: one row keyed by month, release and run with
      the tier and leaked sums; a second refresh keeps one row; an unknown
      run returns `None` and writes nothing; a run without a release lands
      under `UNASSIGNED_RELEASE`; coverage is `partial` with one of two
      priced resources and `complete` after the second, the runner excluded,
      and `none` without items; backend and region are copied (the spot flag
      is covered by the event test of Task 2); `month_of` treats a naive
      datetime as UTC; the coverage verdict table.
- [x] Run them and confirm the failure.
- [x] Write the model, register it, add the column and the hooks, write the
      service.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — The write paths

**Files:**
- Modify: `argus/backend/service/run_cost_service.py`, `submit_cost_items` and `set_estimated_cost`
- Modify: `argus/backend/service/client_service.py`, `finish_run`
- Modify: `argus/backend/plugins/sct/service.py`, `submit_event`
- Test: `argus/backend/tests/cost_rollup/test_rollup_write_paths.py`
- Test: `argus/backend/tests/sct_events/test_spot_termination_event.py`

**Internals:** `RunCostService._refresh_rollup_guarded(run_id)`, the guarded
call, invoked after the recompute in `submit_cost_items` and after the update
in `set_estimated_cost`. `finish_run` calls `CostRollupService().refresh(run)`
after the recompute, inside the same guard. `SCTService._refresh_cost_rollup(run_id)`:
read the run with `.only(*SCTTestRun.cost_rollup_columns())`, then
`refresh(run)`; called from `submit_event` when the event type is a
`SpotTerminationEvent`.

- [x] Write the failing tests: an item submit writes the row; an estimate
      submit writes a row with `actual_cost` null and coverage `none`; a
      finalize without cost writes a row with status and end time; a leaked
      item after finalize updates the sums and keeps status and end time;
      finalize and item submit return normally when `refresh` is patched to
      raise `NoHostAvailable`; a `SpotTerminationEvent` marks the rollup
      row, a stored one marks a later refresh, another critical event does
      not.
- [x] Run them and confirm the failure.
- [x] Add the calls and the event refresh.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — The backfill script

**Files:**
- Create: `scripts/migration/migration_2026-10-29_backfill_run_cost_rollup.py`

**Internals:** `list_cost_run_ids()` over `SELECT DISTINCT run_id FROM run_cost_v1`
with three attempts; `list_sct_run_ids()` over every `ArgusTest` of the SCT
plugin and `SCTTestRun.find(build_id=...).only("id")` through `gather_limited`,
with no date bound so imported historical cost lands too;
`refresh_sct_run(run_id)` loading the SCT run directly, `refresh_one` falling
back to `RunCostService.refresh_rollup` for a cost partition of another
plugin; `backfill(run_id)` over the union through `gather_limited(limit=20)`
with the counts `runs`, `written`, `missing`, `failed`; argparse `--run-id`.
Structure of `migration_2026-09-21_backfill_run_config_param_index.py`.

- [x] Write the script.
- [x] Run it against the dev database and record the counts in the pull request.
      (dev: 996 SCT tests scanned, 2 cost partitions, 1 written, 1 missing, 0 failed)
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 4 — The explorer service

**Files:**
- Create: `argus/backend/service/cost_explorer_service.py`
- Modify: `argus/backend/models/run_cost_rollup.py`, `argus/backend/service/cost_rollup_service.py`, the tier counts
- Test: `argus/backend/tests/cost_explorer/test_cost_explorer_service.py`

**Internals:** `MAX_WINDOW_DAYS = 366`, `TOP_RUNS = 20`, `ERRORED_STATUSES`,
`CostScope` and `CostQuery` as the spec declares them, each with `matches(row)`,
and `CostExplorerService` with `explore`, `query_for_view`, `months_between`,
`_read` (one `find(month=m, release_id=r)` per month and restricted release,
or one per month, gathered), `bucket_key`, `bucket_keys`, `spend_of`, the
panel folds `_tiles`, `_series`, `_releases`, `_top_runs`, `_coverage`,
`_tiers`, `_spot_terminations`, `_span` (the union of the selected releases'
span rows), and `_names` (chunked `__in` reads of
`ArgusRelease`, `ArgusGroup`, `ArgusTest` with `.only("id", "name", "pretty_name")`).
The rollup model and service gain `spot_count`, `on_demand_count` and
`untiered_count`.

- [x] Write the failing tests: months across a year boundary; the day, week
      and month bucket keys; spend ignores a run without data; the previous
      window feeds only the trend; the release filter; the tier filter; the
      series per backend and bucket; the breakdown by test resolves names;
      the unassigned names; top runs sorted and limited; the coverage, tier
      and spot counts; leaked spend and the backend filter; a window over 366
      days, an end before the start and a bad option raise
      `DataValidationError`; the view's ids match any.
- [ ] Run them and confirm the failure. (The tests and the service were
      written together; the run that followed passed.)
- [x] Write the service.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 5 — The API route

**Files:**
- Modify: `argus/backend/controller/cost_api.py`
- Modify: `docs/api_usage.md`
- Test: `argus/backend/tests/cost_explorer/test_cost_explorer_api.py`

**Internals:** `GET /explorer`, `name="api.cost_api.explorer"`, the query
parameters of the spec with `NoneIfEmpty` on the optional ones, `Literal`
types on `tier`, `breakdown` and `granularity`, ISO datetimes converted to
UTC, `default_window(start, end)` giving 90 days back at 00:00 UTC up to
now, `query_for_view` when `viewId` is given.

- [x] Write the failing tests: the envelope holds every panel with the
      defaults echoed in `window`; a release filter with an offset ISO
      window; `viewId` expands to the view's ids; an unknown granularity,
      a bad window and an unknown view return the error envelope; an
      anonymous caller gets 403.
- [ ] Run them and confirm the failure. (Written together with the route;
      the first run found two assertion mistakes in the tests, then passed.)
- [x] Add the route and document it.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 6 — The page: route, template, navbar, entry, root, tiles and chart

**Files:**
- Modify: `argus/backend/controller/main.py`
- Create: `templates/cost_explorer.html.j2`
- Modify: `templates/partials/nav_bar.html.j2`
- Modify: `vite.config.ts`
- Create: `frontend/cost-explorer.js`
- Create: `frontend/CostExplorer/types.ts`, `api.ts`, `filters.ts`, `format.ts`,
  `palette.ts`, `chart.ts`, `theme.svelte.ts`, `CostExplorer.svelte`,
  `FilterBar.svelte`, `StatTiles.svelte`, `SpendOverTime.svelte`
- Test: `frontend/CostExplorer/filters.test.ts`, `StatTiles.test.ts`, `CostExplorer.test.ts`

**Internals:** the `main.cost_explorer` route at `/costs`; the `Costs` link
with `fas fa-coins`; the `costExplorer` entry; `loadExplorer(filters)` building
`URLSearchParams` with the camelCase keys and omitting empties;
`parseFilters`, `serializeFilters`, `defaultFilters`, `presetRange`,
`apiParams` (UTC datetimes, inclusive end date); the `usd`, `percent`,
`share`, `trend`, `duration` and `dateLabel` formatters; the categorical
palette validated for both themes with a fixed backend order and
`watchTheme` reading `data-bs-theme`; the `chart` action creating, updating
and destroying a chart.js instance from a `$state.snapshot`; the root with
`filters` in `$state`, an `$effect` that loads on change and rewrites the
query string, the loading and error states.

- [x] Write the failing tests: the filter round trip and the defaults; the
      tiles' trend sign and no-data state; the root's request URL carries the
      camelCase filters, renders the tiles, and toasts on error.
- [ ] Run them and confirm the failure. (Written together with the
      components; the first run passed.)
- [x] Write the route, the template, the navbar entry, the entry point and
      the components.
- [x] Run `yarn build` and the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 7 — The remaining panels

**Files:**
- Create: `frontend/CostExplorer/ReleaseBreakdown.svelte`, `TopRuns.svelte`,
  `Coverage.svelte`, `TierSplit.svelte`, `SpotTerminations.svelte`
- Modify: `frontend/CostExplorer/CostExplorer.svelte`
- Test: `frontend/CostExplorer/TopRuns.test.ts`, `ReleaseBreakdown.test.ts`, `SpotTerminations.test.ts`

**Internals:** the per-release sections with the group or test rows, the top
three open, long lists folded past ten rows; the top runs table linking
`/test/{build_id}/{build_number}` with status, coverage and spot badges; the
coverage counts as a stacked bar in the Bootstrap status colors with the
earliest priced run; the tier split as a stacked bar in the categorical palette;
the spot terminations count, rate, spend and the table by backend and
region.

- [x] Write the failing tests: the run link and the badges; the "Unassigned"
      row and the cost-per-run format; the long list folds behind a toggle;
      the rate as a percentage and the two empty states.
- [ ] Run them and confirm the failure. (Written together with the
      components; the first run found one duplicate-text lookup in a test.)
- [x] Write the components and wire them.
- [x] Run `yarn build` and the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 8 — The view widget

**Files:**
- Create: `argus/backend/controller/views_widgets/costs.py`
- Create: `frontend/Views/Widgets/ViewCosts.svelte`
- Modify: `frontend/Common/ViewTypes.js`
- Test: `argus/backend/tests/cost_explorer/test_costs_widget_api.py`, `frontend/Views/Widgets/ViewCosts.test.ts`

**Internals:** `GET /widgets/costs`, `name="api.view_api.costs.get_costs"`,
`view_id` and `days` (1 to 366, default 30), by day up to 31 days and by week
beyond; the widget component reusing `StatTiles` and `SpendOverTime` with the
link to `/costs?viewId=`; the `costs` entry of `WIDGET_TYPES` with the `days`
setting.

- [x] Write the failing tests: the route reads the view's ids over the last
      days; a window past a month uses weeks; a window over 366 days and an
      unknown view return the error envelope; the component requests the
      widget route with the configured days, defaults to 30, and links the
      page.
- [ ] Run them and confirm the failure. (Written together with the route and
      the component; the first run passed.)
- [x] Write the route, the component and the registry entry.
- [x] Run `yarn build` and the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 9 — The documentation

**Files:**
- Modify: `docs/project/architecture.md`
- Modify: `docs/standards/backend/queries.md`

**Internals:** the router list and the counts; `run_cost_by_month_v1` named
beside `ReleaseStatsSnapshot` under "Precompute the Expensive Aggregate".

- [x] Update both documents. (Edited directly: a two-line addition to an
      existing standard whose `docs/INDEX.md` entry stays accurate.)
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.
