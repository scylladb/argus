# ARGUS-157 — implementation plan

**Spec:** `tasks/ARGUS-157/spec.md`

## Constraints

- Verify sequence from the `Commands` section of `CLAUDE.md`:
  `uv run pre-commit run --all-files`, `uv run pytest`, `yarn test`, and
  `yarn build` for the frontend tasks. A backend test starts a ScyllaDB
  container, so Docker must be up.
- `sync-models` owns the schema. A data job is a dated script under
  `scripts/migration/`, named for what it does, and is never edited once run.
- No test may live under `argus/backend/service/` — `pyproject.toml`
  `norecursedirs` skips it. Backend tests go under `argus/backend/tests/<area>/`
  with an `__init__.py`.
- Every new route takes `user: User = Depends(api_current_user)`, returns
  `APIResponse({"status": "ok", "response": ...})`, and is named
  `api.<module>.<function>`. OpenAPI is off, so a new endpoint is documented in
  `docs/api_usage.md`.
- A service raises `APIException` or `DataValidationError`. It never returns an
  error dictionary.
- Frontend is Svelte 5 runes. Pure logic goes in a `Common/` helper, because the
  vitest suite tests exported functions rather than mounted trees.
- Tasks 1-3 are deployable on their own and must reach production before task 5
  does. Tasks 1-3 add writes; tasks 5 and 7 move reads onto them.

## Task 1 — the three index models

**Files:**
- Modify: `argus/backend/models/run_config.py`
- Modify: `argus/backend/models/web.py` (`USED_MODELS`)
- Test: `argus/backend/tests/run_config/test_run_config_models.py` (new package)

**Internals:** `RunConfigParamByRun(run_id: UUID PrimaryKey, name: str
ClusteringKey, value: str | None)` on `run_config_param_by_run_v1`;
`RunConfigParamValueIndex(name: str PrimaryKey, value: str ClusteringKey)` on
`run_config_param_value_index_v1`; `RunConfigParamName(bucket: str PrimaryKey,
name: str ClusteringKey)` on `run_config_param_name_v1`, with
`NAME_BUCKET = "all"`.

- [ ] Write the failing test: each table round-trips a row, and a by-run read is
      one partition per run.
- [ ] Run it and confirm the failure.
- [ ] Add the models and the `USED_MODELS` entries.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 2 — write the index rows

**Files:**
- Modify: `argus/backend/service/client_service.py` (`parse_config_values`)
- Test: `argus/backend/tests/client_service/test_run_config_index.py`

**Internals:** `parse_config_values` writes the by-run row, the value-index row
and the name row alongside the existing `RunConfigParam`. `run_id` is normalised
to a `UUID` for the by-run row. A module-level `_SEEN_NAMES: set[str]` guards the
name-catalogue write, so a repeated name costs nothing after the first submit in
a process. `EMPTY_PARAM_VALUES = {"", "null", "None"}` is defined here and
imported by the service in task 4.

- [ ] Write the failing tests: a submitted config populates all four tables; a
      nested key keeps its dotted path; `None`, `""` and `False` land as
      `"None"`, `"null"` and `"False"`; a non-canonical run id in the path still
      writes a canonical `UUID`; a second submit of the same names issues no
      further name-catalogue writes.
- [ ] Run them and confirm the failure.
- [ ] Implement.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 3 — backfill

**Files:**
- Create: `scripts/migration/migration_2026-09-21_backfill_run_config_param_index.py`

**Internals:** pages `RunConfiguration` (keyed by `run_id`, so the scan is
resumable per run) and replays the task-2 write path over each row's `content`.
Upserts only, so re-running is safe. Takes `--run-id` to repair one run. Logs
and skips a row whose content is not JSON, matching `parse_config_values`.

- [ ] Run it against the dev keyspace over a seeded run and assert the row
      counts in the three new tables.
- [ ] Commit. It must run in production before task 5 deploys.

## Task 4 — `RunConfigParamService`

**Files:**
- Create: `argus/backend/service/run_config_params.py`
- Test: `argus/backend/tests/run_config/test_run_config_param_service.py`

**Internals:** `ConfigParamFilter(name: str, value: str | None)`, frozen and
slotted. `parse_filters(raw)` drops a row with a blank name, rejects a duplicate
name, and raises `DataValidationError` when `raw` is not a list of mappings.
`search_names(query, limit=100)` reads the single name partition and
substring-matches case-insensitively in Python. `search_values(name, query,
limit=100)` is a clustering range on `run_config_param_value_index_v1`
(`value__gte=query`, `value__lt=query + "￿"`) with the limit applied in the
query. `narrow_run_ids(run_ids, filters)` issues one prepared
`SELECT name, value FROM run_config_param_by_run_v1 WHERE run_id = ? AND name IN ?`
per candidate run through `execute_concurrent_with_args(..., concurrency=50)`,
mirroring `PluginModelBase.get_versions_by_run_ids`
(`argus/backend/plugins/core.py:161-171`), and matches in Python.

- [ ] Write the failing tests: a concrete value matches and a different one does
      not; "is set" accepts a real value and rejects each of
      `EMPTY_PARAM_VALUES`; two rows AND; a run absent from the table is
      excluded; an empty filter list returns the input unchanged;
      `parse_filters` drops a blank row, rejects a duplicate name and raises on
      garbage; `search_values` honours the prefix and the limit;
      `search_names` is case-insensitive.
- [ ] Run them and confirm the failure.
- [ ] Implement.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 5 — autocomplete endpoints

**Files:**
- Create: `argus/backend/controller/run_config_api.py`
- Modify: `argus/backend/controller/api.py`
- Modify: `docs/api_usage.md`
- Test: `argus/backend/tests/run_config/test_run_config_api.py`

**Internals:** `APIRouter(prefix="/run_configs")`, included from `api.py` beside
the other top-level routers. `GET /param_names?query=` named
`api.run_config_api.param_names`; `GET /param_values?name=&query=` named
`api.run_config_api.param_values`.

- [ ] Write the failing tests: both routes return the envelope; an
      unauthenticated call is rejected; `param_values` without `name` answers
      the 200 error envelope that
      `argus/backend/tests/integration/test_error_contract.py` asserts.
- [ ] Run them and confirm the failure.
- [ ] Implement and document both endpoints.
- [ ] Run the verify sequence.
- [ ] Commit. **Requires task 3 to have run.**

## Task 6 — the run window becomes a parameter

**Files:**
- Modify: `argus/backend/plugins/core.py` (`_stats_query`, `get_stats_for_release`)
- Modify: `argus/backend/plugins/sct/testrun.py`,
  `argus/backend/plugins/generic/model.py`,
  `argus/backend/plugins/sirenada/model.py`,
  `argus/backend/plugins/driver_matrix_tests/model.py`
- Test: `argus/backend/tests/api/test_stats_query_window.py`

**Internals:** `_stats_query(cls, per_partition_limit: int = 15)` and
`get_stats_for_release(cls, release, build_ids, per_partition_limit: int = 15)`.
All four plugins interpolate the parameter in place of the literal `15`.
Callers that pass nothing keep today's query text.

- [ ] Write the failing test: the default query text is unchanged for every
      plugin, and a non-default limit reaches the CQL.
- [ ] Run it and confirm the failure.
- [ ] Implement.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 7 — apply the filter in the view stats path

**Files:**
- Modify: `argus/backend/controller/view_api.py` (`view_stats`)
- Modify: `argus/backend/service/stats.py` (`ViewStatsCollector.collect`)
- Test: `argus/backend/tests/view_api/test_view_stats_param_filter.py`

**Internals:** `view_stats` gains
`param_filter_off: list[str] = Query([], alias="paramFilterOff")`.
`ViewStatsCollector.collect` reads `widget["settings"].get("configParamFilters")`
through `parse_filters`, keeps the rows whose name is not in `param_filter_off`,
raises the window to 50 when a row survives, applies `narrow_run_ids` to
`self.view_rows` **after** the version and image filters, then drops from
`all_tests` every test whose `build_system_id` has no surviving row before
`ViewStats.collect` runs.

- [ ] Write the failing tests: a configured row drops non-matching runs;
      `paramFilterOff` on a configured name widens the result; a
      `paramFilterOff` name the widget does not configure cannot add a filter;
      a pruned test is absent from the payload and from the group counts; no
      `configParamFilters` leaves the payload and the query text as they are
      today; a row with a blank name is ignored.
- [ ] Run them and confirm the failure.
- [ ] Implement.
- [ ] Run the verify sequence.
- [ ] Commit. **Requires task 3 to have run.**

## Task 8 — move the two existing reads onto the by-run table

**Files:**
- Modify: `argus/backend/plugins/sct/testrun.py` (`get_config_params`)
- Modify: `argus/backend/service/client_service.py` (`get_config_property`)
- Test: `argus/backend/tests/sct_api/test_sct_api.py`,
  `argus/backend/tests/client_service/test_client_service.py`

**Internals:** `get_config_params()` reads
`RunConfigParamByRun.find(run_id=self.id)`, dropping the `allow_filtering()`
full scan. `get_config_property` reassigns the immutable queryset
(`dml = dml.filter(run_id=run_id)`), which is a silent no-op today.

- [ ] Write the failing test for the `get_config_property` `run_id` narrowing,
      which currently returns every run's rows.
- [ ] Run it and confirm the failure.
- [ ] Fix both, keeping `get_xcloud_details` green.
- [ ] Run the verify sequence.
- [ ] Commit. **Requires task 3 to have run.**

## Task 9 — filter helpers and the setting editor

**Files:**
- Create: `frontend/Common/ConfigParamFilters.ts`
- Create: `frontend/Views/WidgetSettingTypes/ConfigParamFilterValue.svelte`
- Modify: `frontend/Common/ViewTypes.js`
- Test: `frontend/Common/ConfigParamFilters.test.ts`

**Internals:** `ANY_VALUE` and its label, `normalizeRows`, `hasDuplicateName`,
`badgeLabel(row)`, `disabledNames(rows, offNames)`. The editor honours the
`{settingName, definition, settings = $bindable()}` contract, initialises with
`settings[settingName] = [...(definition.default ?? [])]` — `ViewWidget.svelte`
assigns `definition.default` by reference and the registry's `[]` is one shared
array — and reassigns on add and remove rather than mutating. Two
`svelte-select` 5.8.3 instances use `loadOptions` with the `item` and `empty`
slots, after `frontend/AdminPanel/ViewsManager.svelte:440-460`; the value select
stays disabled until a name is chosen and prepends the synthetic "(any value)"
option that stores `null`; a duplicate name is refused.

- [ ] Write the failing tests for each helper, including that two editor
      instances do not share one row array.
- [ ] Run them and confirm the failure.
- [ ] Implement and register `configParamFilters` under
      `WIDGET_TYPES.testDashboard.settingDefinitions` with `default: []`.
- [ ] Run the verify sequence, `yarn build` included.
- [ ] Commit.

## Task 10 — the dashboard badge bar

**Files:**
- Create: `frontend/ReleaseDashboard/ConfigParamFilterBar.svelte`
- Modify: `frontend/ReleaseDashboard/TestDashboard.svelte`
- Test: `frontend/ReleaseDashboard/ConfigParamFilterBar.test.ts`

**Internals:** props `{rows, offNames}` with an `on:toggle` dispatch, after
`AssigneeFilter.svelte`. A badge carries its own `background-color` and `color`
pair. `TestDashboard` holds `paramFiltersOff = $state([])`, never in
`FILTER_STACK` and never in `localStorage`, renders the bar after the
version-selector block when `dashboardObjectType == "view"` and the setting is
non-empty, and adds `paramFilterOff: paramFiltersOff` to the `fetchViewStats`
query string, read inside the function so the periodic refresh picks up a
toggle. `fetchReleaseStats` is untouched.

- [ ] Write the failing tests: one badge per row with the "any value" label; a
      click emits the row's name; a switched-off badge renders muted.
- [ ] Run them and confirm the failure.
- [ ] Implement.
- [ ] Run the verify sequence, `yarn build` included.
- [ ] Commit.

## Task 11 — isolate the widget stats bucket

**Files:**
- Modify: `frontend/Common/ViewTypes.js` (export `calculateWidgetStatsKey`),
  `frontend/Views/ViewDashboard.svelte`
- Test: `frontend/Common/ViewTypes.test.ts`

**Internals:** `calculateWidgetStatsKey(widget)` keeps
`sha1(filter.join(""))` when the widget configures no rows, and returns
`sha1(filter.join("") + "#" + widget.position)` when it does. Today the key is
`sha1(widget.filter)` alone, so a param-filtered Test Dashboard shares the
`GLOBAL_STATS_KEY` bucket with the stat bar and every other unfiltered widget
and silently rewrites their numbers. Taking the position only when rows exist
leaves every existing view's keys byte-identical, `GLOBAL_STATS_KEY` included.
`versionDispatch` keeps the current key, so the preselect at
`ViewDashboard.svelte:23` still lands.

- [ ] Write the failing tests: an unfiltered widget still yields
      `GLOBAL_STATS_KEY`; two param-filtered widgets sharing a `filter` yield
      different keys.
- [ ] Run them and confirm the failure.
- [ ] Implement.
- [ ] Run the verify sequence, `yarn build` included.
- [ ] Commit.
