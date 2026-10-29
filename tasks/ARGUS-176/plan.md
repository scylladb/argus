# ARGUS-176 — implementation plan

**Spec:** `tasks/ARGUS-176/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Follow `docs/standards/backend/api.md`: one `APIRouter` with an explicit
  prefix, `api.<module>.<function>` route names, `Depends(api_current_user)`
  on every route, and errors raised as `DataValidationError`.
- Follow `docs/standards/backend/queries.md`: every read names a full
  partition key, no `allow_filtering()`, and `select_rows` with only the
  columns the read uses.
- Fan-out reads go through `gather_limited`. `IN` lists go through `chunk`.
- Backend tests need Docker. They submit runs and results through
  `client_service`, as `test_hidden_columns.py` does.

## Task 1 — Release results service

**Files:**
- Modify: `argus/backend/service/results_service.py`
- Test: `argus/backend/tests/results_service/test_release_results.py`

**Internals:**
- `RELEASE_RESULTS_WINDOW = timedelta(days=30)` and
  `RUN_START_MARGIN = timedelta(days=7)`, module constants.
- `_resolve_release_id(release)`: a UUID string as is, else
  `ArgusRelease.find(name=...)`. No match raises `DataValidationError`.
- `_get_release_tables(release, table_filter)`: the tests of the release
  (`id`, `name`, `build_system_id`, `plugin_name`), each with its metadata
  tables whose name contains `table_filter`, case-insensitive.
- `_get_runs_started(test, since, until)`: the plugin run table by
  `build_id` and a `start_time` range. Returns `{run_id: row}` with
  `investigation_status`, `build_number` and `scylla_version`, ignored runs
  left out. A test with no plugin or no `build_system_id` gives `{}`.
- `_get_runs_cells(test_id, table_name, run_ids)`: a raw read of
  `generic_result_data_v1` with `run_id IN (...)` and
  `WRITETIME(status) AS submitted`, 90 ids per query.
- `get_release_result_tables(release)`: one entry per table name with
  `description`, the merged `columns`, and the `tests` count.
- `get_release_results(...)`: `since` defaults to now minus
  `RELEASE_RESULTS_WINDOW`. Runs are selected from `since - RUN_START_MARGIN`.
  Cells are filtered by status, by write time, and by `sut_timestamp`, then
  grouped by table, test, and run, in the shape of the spec `Outputs`.

- [x] Write the service.
- [x] Write the tests: grouping and `build_number`, the status and
  write-time filters, the run start-time window, `until` alone with a
  backdated run, ignored runs left out, a run of the `generic` plugin, and
  the table catalog.
- [x] Run the `until` test against the service without the fix, and confirm
  that it fails.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Results router

**Files:**
- Create: `argus/backend/controller/results_api.py`
- Modify: `argus/backend/controller/api.py` (import and `include_router`)
- Test: `argus/backend/tests/results_service/test_release_results.py`

**Internals:**
- `router = APIRouter(prefix="/results")`.
- `api.results.release_tables`: `GET /release/{release}/tables`.
- `api.results.release_results`: `GET /release/{release}` with `table`,
  `status[]`, `since`, `until`, `sutSince` and `sutUntil`. The dates go to
  UTC before the service call.

- [x] Write the router. Upper-case `status[]` before the service call.
- [x] Write the tests: the endpoint by release name, a lower-case status,
  and an unknown release that gives `status: error`.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit with Task 1, because both tasks share one test file.

## Task 3 — CLI commands

**Files:**
- Create: `cli/cmd/results.go`
- Create: `cli/internal/models/results.go`
- Modify: `cli/internal/api/routes.go` (`ReleaseResultTables`, `ReleaseResults`)
- Modify: `cli/README.md` (section `Compare generic results across a release`)

**Internals:**
- `genericResultsCmd` (`argus results`) with `genericResultsTablesCmd`
  (`tables <release>`) and `genericResultsQueryCmd` (`query <release>`).
  The names avoid `resultsCmd` of `cli/cmd/testrun.go`.
- `query` flags: `--table` (required), `--status` (repeatable), `--since`,
  `--until`, `--sut-since` and `--sut-until`, sent as the query parameters of
  the spec.
- `ResultTableSummaries` and `ResultGroups` implement `output.Tabular`.
  `ResultGroups` prints one row per cell. `ReleaseResultCell` avoids
  `ResultCell` of `models/runs.go`.
- `releaseResultsRoute(release, table, statuses, window)` builds the query
  route, and `releaseResultsWindowParams` maps the time flags to parameters.

- [x] Write the commands and the models.
- [x] Write the tests: `cmd/results_test.go` for the route and the flags,
  `internal/models/results_test.go` for the text rows.
- [x] Run `make fmt`, then `make lint` and `go test -race ./...` in `cli/`.
  Revert the files that `make fmt` changes outside this task.
- [x] Commit, with the boxes of this task checked.

## Task 4 — Move the per-test results endpoints

**Files:**
- Modify: `argus/backend/controller/api.py` (remove `test_results`,
  `create_graph_view`, `update_graph_view` and their request models)
- Modify: `argus/backend/controller/results_api.py`
- Modify: `frontend/WorkArea/TestRunsSelector.svelte`,
  `frontend/TestRun/ResultsGraphs.svelte`,
  `frontend/TestRun/Components/ResultTable.svelte`
- Test: `argus/backend/tests/api/test_graphs_api.py`

**Internals:** the three endpoints and `CreateGraphViewRequest` and
`UpdateGraphViewRequest` move unchanged, at the paths of the spec table.

- [x] Move the endpoints and the request models.
- [x] Point the frontend and `test_graphs_api.py` at the new paths.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`,
  and `yarn build`.
- [x] Commit, with the boxes of this task checked.
