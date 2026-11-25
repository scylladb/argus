# ARGUS-184 — implementation plan

**Spec:** `tasks/ARGUS-184/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

**Code**
- Imports sit at the top of the module.
- No comments or docstrings that justify the change. Fix a comment only when
  it became wrong.
- No fallback link for a missing `build_number`.

**Tests**
- Backend tests create and read rows through the services or the API, never
  through `Model.save()` or `find()` in a test body.
- Every backend test with ScyllaDB needs Docker.
- Run Vitest under Node 22:
  `npx -y node@22 node_modules/vitest/vitest.mjs run`.
- Export `XDG_CACHE_HOME` to a scratch directory before any CLI test run.

**Commits**
- The commitlint header has the form `feature(<scope>): …`, the scope has at
  least 5 characters, and the header is at most 72 characters.
- A blank line follows the header.
- The body has at least 30 characters.
- The last line is `Task: ARGUS-184`.
- No Co-Authored-By line.
- `git add` takes explicit paths only.
- Commit through `uv run git commit`.
- Leave the code uncommitted until Komachi reviews it. The commit box of each
  task stays open until then.

## Task 1 — The build lookup returns every run of a build

**Files:**
- Modify: `argus/backend/service/testrun.py:81-98`
- Modify: `argus/backend/controller/main.py:39-94`
- Modify: `argus/backend/templates/run_view_by_plugin.html.j2:11`
- Modify: `argus/backend/controller/api.py:76-95`
- Modify: `argus/backend/service/chat/resolve.py:210-230`
- Test: `argus/backend/tests/testrun_api/test_run_by_build.py`
- Test: `argus/backend/tests/main_api/test_run_view.py`
- Test: `argus/backend/tests/chat/test_references.py`

**Internals:**

`TestRunService.get_runs_by_build_number(build_id, build_number) -> list[PluginModelBase]`:
- Replaces `get_run_by_build_number`.
- Returns `[]` when the test or the plugin is missing.
- Otherwise returns the full `find(...).allow_filtering().all()` list, which
  the clustering order already sorts newest first.

`_run_view(asgi_request, runs, tab, run_label)`:
- Takes the list.
- Checks `runs[0].test_id`.
- Passes `run=runs[0]` and `run_ids=[run.id for run in runs]` to the template.

Routes and template:
- `get_run_by_plugin` passes `[run]`.
- In the template, `gRun` becomes `{{ run_ids | tojson | safe }}`.

`api.get_run_by_build`:
- Response: `{"runs": [{"run_id": str, "plugin_name": str}], "url": <base> + url_for("main.get_run_by_build", build_id=, build_number=)}`.
- No runs raises, as today.

`resolve_run_reference`:
- Calls `get_runs_by_build_number`.
- An empty list keeps the existing "has no build" error.
- Several runs raise
  `TestReferenceError(f"{scope.label(test)} build #{number} has {len(runs)} runs: {ids}. Name one by its id.")`.
- One run continues to `run_in_scope`.

- [x] Change `test_get_run_by_build_resolves_run` to read `runs[0]` and to
  check that `url` ends in `/test/{build_system_id}/77`.
- [x] Add `test_get_run_by_build_returns_parallel_runs`: two submits with the
  same `job_url .../77`. The JSON `runs` holds both ids. `GET /test/{build_system_id}/77`
  renders a page whose `script_value(res.text, "gRun")` holds both ids.
- [x] Add a chat test: a build with two runs raises `TestReferenceError` that
  names both ids. Reuse the setup of the existing build-reference test in
  `test_references.py`.
- [x] Run them and confirm the failures.
- [x] Make the service, route, template, API and chat changes.
- [x] Run `uv run pytest argus/backend/tests/testrun_api argus/backend/tests/main_api argus/backend/tests/chat`.
- [x] Commit `feature(testrun): resolve every run of a build`.

## Task 2 — The report email links runs by build

**Files:**
- Modify: `argus/backend/service/email_service.py:40-44`
- Modify: `templates/email/partials/{header,main,packages,logs,screenshots,cloud,nemesis,events,generic_results,custom_html,custom_table}.html.j2`
- Test: `argus/backend/tests/email_service/test_email.py`

**Internals:**
- `Partial.__init__` adds
  `"run_path": f"/test/{self.test_run.build_id}/{self.test_run.build_number}"`
  to `_service_fields`.
- Each partial replaces `/tests/scylla-cluster-tests/{{ options['run_id'] }}`,
  or `options['id']` in the header, with `{{ options['run_path'] }}`. Each
  partial keeps its `/<tab>` suffix and the `http(s)://argus.scylladb.com` host.

- [x] In `test_send_default_email`, assert that the sent HTML holds
  `/test/{fake_test.build_system_id}/<n>/details` and no `/tests/scylla-cluster-tests/`.
- [x] Run it and confirm the failure.
- [x] Change the service and the 11 partials.
- [x] Run `uv run pytest argus/backend/tests/email_service`.
- [x] Commit `feature(email): link report sections to the run by build`.

## Task 3 — Responses that carry only a run id gain the build fields

**Files:**
- Modify: `argus/backend/service/views_widgets/nemesis_stats.py:12-42`
- Modify: `argus/backend/service/views_widgets/graphed_stats.py:18-79`
- Modify: `argus/backend/service/results_service.py`:
  - `RunsDetails` (:80)
  - `get_sorted_data_for_column_and_row` (:154)
  - `create_chartjs` (:383-400)
  - `_load_runs_details` (:429)
  - `get_tests_by_version` (:625-654)
- Modify: `argus/backend/plugins/sct/service.py:877,944` (`get_similar_runs_info`)
- Modify: `argus/backend/service/views_widgets/pytest.py` (`result_filter`)
- Test:
  - `argus/backend/tests/widgets/test_nemesis_stats_widget.py`
  - `argus/backend/tests/widgets/test_graphed_stats_widget.py`
  - `argus/backend/tests/widgets/test_summary_widget.py`
  - `argus/backend/tests/widgets/test_pytest_widget.py`
  - `argus/backend/tests/widgets/test_graphs_widget.py`
  - `argus/backend/tests/results_service/test_results_service.py`
  - `argus/backend/tests/results_service/test_create_chartjs.py`
  - `argus/backend/tests/sct_api/test_sct_api.py`

**Internals:**
- **Nemesis stats:** `.only()` gains `build_id` and `build_number`, and each
  entry gains both.
- **Graphed stats:** `.only()` gains `build_number`, and each `test_runs` entry
  and each `nemesis_data` entry gains it.
- **Results graphs:**
  - `RunsDetails` gains `build_id: str` (the test's `build_system_id`, read
    with `plugin_name`) and `build_numbers: dict[RunId, int | None]`.
  - `_load_runs_details` selects `build_number` too.
  - Each point gains `"build_number": runs_details.build_numbers.get(entry.run_id)`.
  - `create_chartjs` adds `"build_id": runs_details.build_id` to each graph
    dict.
- **Summary (`get_tests_by_version`):** `select_rows` gains `build_number`, and
  the per-method dict gains `'build_number'`.
- **Similar runs:** both result dicts gain `"build_job": test_run.build_id`
  and `"build_number": test_run.build_number`. `build_id` keeps its `job#N`
  string.
- **Pytest (`result_filter`):**
  - After slicing `hits = results[:limit]`, read
    `AVAILABLE_PLUGINS["generic"].model.find(id=run_id).only("build_id", "build_number").first()`
    for each distinct `run_id` in the hits, through `gather_limited`.
  - Set `build_id` and `build_number` on every hit, `None` when the run is
    missing.
  - This is the plugin that `ClientService.submit_pytest_result` resolves a
    result against.

- [x] Extend each seeded test to assert the new fields:
  - Nemesis, graphed stats, summary and similar runs: `build_number == 42`,
    from the `job_url .../job/42` of `sct_run`.
  - Pytest: a seeded generic run gives the hit its `build_id` and
    `build_number`.
  - Graphs widget: the graph's `build_id` and the point's `build_number`.
  - Update the exact dicts in `test_get_tests_by_version_groups_runs_correctly`
    and in `test_create_chartjs.py`.
- [x] Run them and confirm the failures.
- [x] Make the service changes.
- [x] Run `uv run pytest argus/backend/tests/widgets argus/backend/tests/results_service argus/backend/tests/sct_api`.
- [x] Commit `feature(views): return the build of each run in widget data`.

## Task 4 — The frontend builds every run link through `runUrl`

**Files:**
- Modify: `frontend/Common/RunUtils.js`, adding `runUrl`
- Modify:
  - `frontend/TestRun/TestRun.svelte:42-55,187,239,267`
  - `frontend/TestRun/Generic/GenericTestRun.svelte`
  - `frontend/TestRun/Sirenada/SirenadaTestRun.svelte`
  - `frontend/TestRun/DriverMatrixTestRun.svelte`
- Modify:
  - `frontend/TestRun/SCT/SctSimilarEvents.svelte`
  - `frontend/Views/Widgets/ViewNemesisStats.svelte:570`
  - `frontend/Views/Widgets/SummaryWidget/SummaryWidget.svelte:354`
  - `frontend/Views/Widgets/ViewGraphedStats/PaginatedTable.svelte:142` and `Interfaces.ts`
  - `frontend/TestRun/ResultsGraph.svelte:239`
  - `frontend/Views/Widgets/PytestWidget/PytestResultRow.svelte:62` and the `PytestResult` type
- Modify:
  - `frontend/CostExplorer/TopRuns.svelte:34`
  - `frontend/Chat/ChatActionCard.svelte:83`
  - `frontend/Views/Widgets/ReleaseSummary/SummaryTestList.svelte:72`
  - `frontend/Views/Widgets/ReleaseSummary/FamilyGrid.svelte:87`
- Delete dead code:
  - `dispatchRunClick` and `on:runClick` in `TestRun/Components/ResultTable.svelte`
    and `TestRun/ResultsGraphs.svelte`
  - `on:runClick` on `<ResultsGraphs>` in `WorkArea/TestRuns.svelte:527`
- Test: `frontend/Common/RunUtils.test.js`, `frontend/Common/safeHtml.test.ts:78,85`

**Internals:**

`runUrl`:
- `export const runUrl = (buildId, buildNumber, tab) => \`/test/${buildId}/${buildNumber}${tab ? \`/${tab}\` : ""}\`;`

Run views:
- The tab switch calls `runUrl(testInfo.test.build_system_id, buildNumber, tabName)`.
- The header link calls `runUrl(testRun.build_id, buildNumber)`.
- `TestInfo.test` gains `build_system_id: string`.

Widgets:
- Similar events: `runUrl(runsInfo[...].build_job, runsInfo[...].build_number)`,
  merged next to `build_id`.
- Nemesis stats and graphed stats: `runUrl(run.build_id, run.build_number)`.
- Summary: `runUrl(test_info[testId].build_id, currentVersionRuns[testId][methodName].build_number)`.
- Results graph tooltip: `runUrl(graph.build_id, point.build_number)`.
- Pytest row: `runUrl(test.build_id, test.build_number)`.

Existing builders:
- TopRuns and ChatActionCard keep their null guard and call `runUrl` inside it.

Dead code:
- `ResultsGraph` never dispatches `runClick`, so the handlers that relay it
  never run.
- Before deleting, confirm that no other code uses `createEventDispatcher`
  in `ResultsGraphs`.

- [x] Add the `runUrl` tests: no tab, a tab, and a `build_id` with slashes kept
  as they are.
- [x] Run them and confirm the failure.
- [x] Add `runUrl` and switch every site.
- [x] Delete the dead `runClick` relay.
- [x] Update the `safeHtml.test.ts` fixture.
- [x] Run Vitest under Node 22 and `yarn build`.
- [x] Run `grep -rn '"/tests/\|`/tests/\|/tests/{' frontend --include='*.svelte' --include='*.ts' --include='*.js'`
  outside `node_modules`. Only the `/api/v1/tests/` calls remain.
- [x] Commit `feature(frontend): link runs by build id and build number`.

## Task 5 — The CLI shows a run by its build and prints build links

**Files:**
- Modify: `cli/cmd/replay.go:406-420`
- Modify: `cli/internal/api/api.go:210-214`, deleting `RunPageURL`
- Modify: `cli/internal/api/routes.go`
- Modify: `cli/cmd/testrun.go:115-160,390-470,789-792`
- Modify: `cli/internal/models/runs.go:162,403-425,429,943-1100`
- Modify: `cli/README.md:321`
- Test: `cli/cmd/replay_upload_test.go:98,169`, `cli/cmd/testrun_get_test.go`

**Internals:**

Routes:
- `api.TestRunByBuild = "/api/v1/test/%s/%d"`.

Models:
- `models.RunsByBuild{Runs []struct{RunID string \`json:"run_id"\`; PluginName string \`json:"plugin_name"\`}; URL string}`.
- `RunBase` and `RunMeta` gain `BuildNumber *int \`json:"build_number"\``.
- `RunDetails` gains `ArgusURL string`. `Rows` adds `{"Argus URL", d.ArgusURL}`
  after "Build Job", and `MarshalJSON` adds `"argus_url"`.
- `GenericRunDetails`, `DriverRunDetails` and `SirenadaRunDetails` gain
  `ArgusURL string \`json:"argus_url"\``.
- A new `models.BuildRunDetails []BuildRunDetail` (`ID string`, `Details output.Tabular`):
  - `Tables()` returns one `NamedTable{Name: "Run " + ID}` per run.
  - `MarshalJSON` returns the array of `Details`.

Handlers:
- The `RunTypeDetailsHandlers` entries fill `ArgusURL` with
  `api.RunURL(c.BaseURL(), run.BuildID, derefInt(run.BuildNumber))`.
- `derefInt` already exists in `internal/services/jobs.go`. Reuse it, or move
  it where both packages can import it.

`run get`:
- The flags `--build-id` and `--build-number` are added.
- `--run-id` is no longer `MarkFlagRequired`. Replace that with
  `MarkFlagsOneRequired("run-id", "build-id")`,
  `MarkFlagsMutuallyExclusive("run-id", "build-id")` and
  `MarkFlagsRequiredTogether("build-id", "build-number")`.
- The existing single-run body moves into `getRunDetails(ctx, cmd, runType, runID, full) (any, error)`.
- With the build flags, `RunE` calls the build lookup. It then calls
  `getRunDetails` per run with that run's `plugin_name` as the type, and writes
  one `BuildRunDetails`.
- With `--full`, each element is the KV view of the full run.

Replay:
- `runLinks` uses `api.RunURL(base, r.BuildID, derefInt(r.BuildNumber))`.
- When there is no build number, `RunURL` returns `""`, and the link is left
  out, as for a dry run.

- [x] Change the replay tests to expect `https://argus.example.com/test/<build_id>/<n>`.
- [x] Add `run get` tests against `stubRunAPI`, extended with
  `/api/v1/test/<build_id>/412`:
  - One run prints the run and its `Argus URL`.
  - Two runs print a JSON array of two objects.
  - `--run-id` together with `--build-id`, and `--build-id` without
    `--build-number`, each fail before any request.
- [ ] Run `go test ./cmd/...` and confirm the failures.
- [x] Make the changes and update the README example.
- [x] Run `make fmt && make lint && go test -race ./...` in `cli/`.
- [x] Commit `feature(cli/run): show a run by its build and print build links`.

## Task 6 — Verify

- [x] Run `uv run pre-commit run --all-files`.
- [x] Run `uv run pytest`.
- [x] Run Vitest under Node 22 and `yarn build`.
- [x] Run `cd cli && make lint && go test -race ./...`.
- [ ] Live check on the running dev server. Find it with `ss -ltnp`, and drive
  it with headless Chrome:
  - Open `/test/<job>/<n>`, switch tabs, and check that the address stays in
    the build form.
  - Check that the header link uses the build form.
  - A build with two runs opens two panels.
  - Check the links of a similar-events row, the nemesis, graphed stats,
    summary and pytest widgets, and a results graph tooltip.
- [ ] Run `argus run get --build-id <job> --build-number <n>` against the dev
  server.
