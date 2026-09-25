# ARGUS-207 — implementation plan

**Spec:** `tasks/ARGUS-207/spec.md`

## Constraints

- Follow `docs/standards/backend/` (router, service, model split; read
  through the mapper; select what you need; no loop of queries) and
  `docs/standards/testing/test-writing.md` (a new code path arrives with a
  test; a service test lives under `argus/backend/tests/`).
- One pull request. Group A commits are sync-safe and leave the suite green.
  Group B flips the models by layer and is green only after B6. Group C is
  one `perf` commit per hotspot, green throughout. The PR body states this.
- Stage by explicit path only. Leave `commitlint.config.js`/`.cjs` untouched;
  lint a message with the `.cjs` config and commit with `--no-verify` for the
  `commit-msg` stage only, after `uv run pre-commit run --files ...` passes.
- Commit scopes are at least five characters. No comments that justify a
  change; only fix a comment that became wrong.
- The verify sequence is the `Commands` section of `CLAUDE.md`. Every backend
  test run needs Docker.
- `asyncio.to_thread` is the one pattern for blocking I/O, applied inside the
  service that owns the client. `asyncio.gather` for a small fan-out,
  `gather_limited` for a data-driven one. No `TaskGroup`, no
  `return_exceptions=True`.
- IN lists go through `chunk()` (`argus/backend/util/common.py:35`). A limit
  that comes from the request stays raw with a bound `?`.
- High-volume reads use `.only(cols).values_list(cols)` and rebuild dicts
  with `dict(zip(cols, row))` inside the model method.

---

## Group A — sync-safe preparation

### Task A1 — Materialize QuerySets with an explicit `all()`

**Files:**
- Modify: `argus/backend/service/views_widgets/highlights.py:379-381, 451`
  (iterate once), `argus/backend/service/stats.py:171-185` (`links` is
  iterated twice; materialize once), `argus/backend/service/test_lookup.py:156-167`,
  `argus/backend/service/tunnel_service.py:232`,
  `argus/backend/service/results_service.py:694`,
  `argus/backend/plugins/core.py:78`,
  `argus/backend/service/build_system_monitor.py:28-30`

- [ ] Replace `list(qs)`, `for x in qs`, `next(... in qs)` with `qs.all()`.
- [ ] Run the verify sequence.
- [ ] Commit `refactor(services): materialize QuerySets with an explicit all()`.

### Task A2 — Fix the `filter` builtin test in `ReleaseStats.collect`

**Files:**
- Modify: `argus/backend/service/stats.py:343` (`if not filter` → `if not version_filter`)
- Test: `argus/backend/tests/test_stats_snapshot.py` (new test)

- [ ] Write `test_release_stats_keeps_plans_without_a_version_filter`: a plan
  with `target_version="X"`, collect with no filter, an unrun planned test
  reads `NOT_RUN`, not `NOT_PLANNED`. Confirm it fails.
- [ ] Apply the one-line fix. Verify. Commit
  `fix(service/stats): filter plans by the version filter, not the builtin`.

### Task A3 — Apply two discarded `.filter()` results

Outcome: `get_assignee_for_test` and `get_assignee_for_group` had no caller
anywhere in the repository, so they were deleted rather than fixed; only the
client config lookup received the fix and its test.

**Files:**
- Modify: `argus/backend/service/planner_service.py:599, 609`,
  `argus/backend/service/client_service.py:250`
- Test: `argus/backend/tests/planner_api/`, `argus/backend/tests/client_api/`

- [ ] For each site write the failing test that shows the filter has no
  effect today; assign `dml = dml.filter(...)`. Verify. One commit per
  module: `fix(service/planner): apply the discarded target_version filter`,
  `fix(service/client): apply the discarded run_id filter`.

### Task A4 — Fetch view links once in `IssueService.get`

**Files:**
- Modify: `argus/backend/service/issue_service.py:24-54`
- Delete: `GithubService.get_issues`, `GithubService._get_github_issues_for_view`
  (`github_service.py:195-210`), `JiraService.get_issues`,
  `JiraService._get_jira_issues_for_view` (`jira_service.py:169-184`)
- Test: `argus/backend/tests/issues/test_issues.py`

**Internals:** `IssueService._get_links(filter_key, aggregate_by_issue, ...)`
fetches the view once and the `IssueLink` chunks once.

- [ ] Write `test_get_by_view_returns_each_link_once`; confirm it fails with
  duplicates. Fix, verify, commit `fix(service/issues): fetch view links once`.

### Task A5 — Return rows from `get_stats_for_release`

**Files:**
- Modify: `argus/backend/plugins/core.py:126-139`,
  `argus/backend/service/stats.py:551-553, 633-635`

**Internals:** `get_stats_for_release(cls, release, build_ids: list[str]) -> list[dict]`
resolves its futures and returns flattened rows; the callers drop
`future.result()`; the `build_ids=list[str]` default becomes an annotation.

- [ ] Change, verify (`tests/test_stats_snapshot.py`, `tests/view_api/`),
  commit `refactor(plugins/core): return rows from get_stats_for_release`.

### Task A6 — Drive `ignore_jobs` through coodie batches

**Files:**
- Modify: `argus/backend/plugins/core.py:117-124`,
  `argus/backend/service/testrun.py:17, 531-562`

**Internals:** `prepare_investigation_status_update_query(...) -> tuple[str, list]`
via `build_update(cls._get_table(), cls._get_keyspace(), {...}, parse_filter_kwargs({...}))`
(the `run_cost_service.py:56-76` pattern); `ignore_jobs` uses two
`BatchQuery` objects and `batch.add(*stmt)`; `BatchStatement` and
`ConsistencyLevel` imports go.

- [ ] Verify with `tests/testrun_api/` ignore-jobs tests. Commit
  `refactor(service/testrun): drive ignore_jobs through coodie batches`.

### Task A7 — Replace `functools.cache` on `_get_runs_details`

**Files:**
- Modify: `argus/backend/service/results_service.py:412-423`

**Internals:** `self._runs_details: dict[UUID, RunsDetails]` filled on first
call.

- [ ] Verify with `tests/results_service/`, `tests/widgets/test_graphs_widget.py`.
  Commit `refactor(service/results): replace functools.cache on _get_runs_details`.

### Task A8 — Build the Jira and GitHub clients lazily

**Files:**
- Modify: `argus/backend/service/jira_service.py:41`,
  `argus/backend/service/github_service.py:40`

**Internals:** `JiraService.jira` and `GithubService.gh` become
`cached_property`.

- [ ] Verify with `tests/issues/`. Commit
  `refactor(services): build the Jira and GitHub clients lazily`.

### Task A9 — Delete dead code

**Files:**
- Modify: `argus/backend/plugins/sct/testrun.py:5` (unused `Lock` import),
  `argus/backend/plugins/core.py:141-157` (`get_run_meta_by_build_id`,
  `get_run_meta_by_run_id`, no callers),
  `argus/backend/service/views_widgets/pytest.py:148` (prepare never run),
  `argus/backend/service/argus_service.py:48-53` (two prepares never run)

- [ ] Grep each name for callers first. Verify. Commit
  `refactor(backend): delete dead raw CQL and an unused import`.

### Task A10 — Raw CQL through the mapper, sync-safe sites

One commit per module. Each replaces the prepared statement with a coodie
query per `spec.md` § Design; the row shape callers see stays a dict.

**Files and internals:**
- `refactor(plugins): read versions and images through the mapper` —
  `sct/testrun.py:239-240, 248-250, 266-267`, `generic/model.py:39-40`,
  `sirenada/model.py:67-68`, `driver_matrix_tests/model.py:133-134`,
  `driver_matrix_tests/service.py:17-19`; `get_image(value)` takes the
  column value. Remove the `cluster` parameter from the generic and sirenada
  `get_distinct_product_versions` overrides.
- `refactor(plugins/core): read job metadata through the mapper` —
  `core.py:100-115` via `cls.find(assignee=...)`/`cls.find(test_id=...)`
  with `.only(*cols).values_list(*cols)`.
- `refactor(service/results): read result tables through the mapper` —
  `results_service.py:414-419, 427-430, 436-451, 456-458, 565-568, 599-600,
  617-624`. `_get_tables_metadata` and `get_table_metadata` keep building
  `ArgusGenericResultMetadata(...)` through its constructor.
  `_exclude_disabled_tests` becomes one `id__in` query per chunk.
- `refactor(service/release-manager): move runs through the mapper` —
  `release_manager.py:31-37, 239-245`, `QuerySet.update(...)` per row.
- `refactor(plugins/sct): count events and read perf results through the mapper`
  — `sct/service.py:557-563` (`.count()`), `sct/testrun.py:291-294`.
- `refactor(service/testrun): aggregate pytest fields through the mapper` —
  `testrun.py:588-614` via `.aggregate(r=f"{fun}({field})")`.
- `refactor(views_widgets/pytest): distinct names through the mapper` —
  `views_widgets/pytest.py:121-122` via `.distinct().only("name").values_list("name").timeout(60.0)`.

- [ ] For each: change, run the module's tests plus `tests/widgets/`, verify,
  commit.

### Task A11 — Test configuration for async

**Files:**
- Modify: `pyproject.toml` (`dev`: `pytest-asyncio >= 1.0`; move `httpx2` to
  `web-backend`; `coodie ~= 1.7`; `[tool.pytest.ini_options]`:
  `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"`,
  `asyncio_default_test_loop_scope = "session"`), `uv.lock`

- [ ] `uv sync --all-extras`, verify (no behaviour change for a sync suite).
  Commit `test(pytest-config): add pytest-asyncio and the asyncio auto mode`.

---

## Group B — the flip

### Task B1 — Paging-aware coodie bridge

**Files:**
- Modify: `argus/backend/db.py:22-38`
- Test: `argus/backend/tests/db/test_paging.py` (new, `docker_required`)

**Internals:** `await_all_pages(driver_future) -> asyncio.Future[list]`
(module level; one `add_callbacks`; the success callback extends `rows`,
calls `start_fetching_next_page()` while `has_more_pages`, else
`loop.call_soon_threadsafe(done.set_result, rows)`; the error callback sets
the exception). `ArgusCoodieDriver._wrap_future(self, driver_future)` returns
it.

- [ ] Write the test: insert 5001 `ReleaseDistinctVersions` rows in one
  partition, `len(await M.find(release_id=x).all()) == 5001`. It fails
  against stock coodie (returns 5000). Cannot run before B2/B6; write it now,
  run it at B6.
- [ ] Commit `refactor(database): paging-aware coodie bridge`.

### Task B2 — Switch the documents to `coodie.aio`

**Files:**
- Modify: 16 model files (`argus/backend/models/*.py`, `plugins/core.py`,
  `plugins/sct/testrun.py`, `plugins/generic/model.py`,
  `plugins/sirenada/model.py`, `plugins/driver_matrix_tests/model.py`):
  `from coodie.aio import Document`; `service/test_lookup.py:9` type hint;
  `models/web.py:414-426` `invalidate_release_snapshots` async.
- Modify: `argus/backend/plugins/core.py` — every DB-touching method and the
  abstract contract become `async def` (spec § Module API);
  `_stats_query()` → `_stats_columns()`; `get_stats_for_release` gathers
  `cls.find(build_id__in=slice).per_partition_limit(15).only(*cols).values_list(*cols).consistency("ONE").all()`
  per chunk and returns `dict(zip(cols, row))` rows; `get_versions_by_run_ids`
  via `gather_limited` (add the helper here, `util/common.py`);
  `get_distinct_versions_for_view` gathers per chunk.
- Modify: the four plugin models' overrides, including
  `sct/testrun.py:274-278` (gathered), `429-431` and `sct/service.py:697-706`
  on `coodie.aio.execute_raw`, `SCTTestRun.get_run_response` awaits.
- Modify: `argus/backend/db.py`: `sync_core_tables` async
  (`sync_type_async`, `await sync_table()`); delete `prepare`,
  `prepared_statements`, the re-prepare loop in `reconnect`, the two
  `read_fast*` profiles, `get_session`. `session` stays for DDL.

- [ ] Commit `refactor(models): switch the documents to coodie.aio`.

### Task B3 — Services await the models and wrap blocking clients

**Files:**
- Modify: every module under `argus/backend/service/` and
  `argus/backend/service/views_widgets/`, `plugins/sct/service.py`,
  `plugins/driver_matrix_tests/service.py`, `plugins/loader.py` if it
  touches models.
- `results_service.py:464-470` on `execute_raw`; the rewrite table in
  `spec.md` and the plan constraints apply to every site.
- Blocking I/O via `asyncio.to_thread`: `jira_service.py` (`issue`,
  `search_issues`), `github_service.py:123-124, 276-287`,
  `jenkins_service.py:108-368, 243`, `user.py:91-155, 551`,
  `testrun.py:213, 222, 233, 259, 273`, `send_email.py`/`email_service.py:362`,
  `notification_manager.py` SMTP sender, `tunnel_service.py:571`,
  `argus_service.py:57`.
- `replay_service.py`: `ingest`, `_process_one`,
  `_diagnose_missing_hierarchy`, `_ensure_hierarchy_for_submit_run`,
  `_test_client` → `_async_client` returning
  `httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self._app), base_url="http://replay")`,
  the two boto3 helpers via `to_thread`; archive extraction via `to_thread`.
- `stats.py`: collectors drop `self.database`/`self.session`; `collect`
  becomes `async`; `fetch_issues` awaits (the concurrency restructure waits
  for C2/C3).
- `error_handlers.py:138`: `await asyncio.to_thread(DBErrorHandler.handle_db_errors, exception)`.

- [ ] Commit `refactor(services): await the async models and wrap blocking clients`.

### Task B4 — Async route handlers and dependencies

**Files:**
- Modify: `argus/backend/controller/*.py`,
  `argus/backend/controller/views_widgets/*.py`,
  `argus/backend/plugins/sct/controller.py`,
  `argus/backend/plugins/driver_matrix_tests/controller.py`,
  `argus/backend/metrics.py:157`, `argus/backend/controller/main.py:274`
  (file read via `to_thread`), `controller/api.py:590-596` (zeus proxy via
  `to_thread`)
- Modify: `argus/backend/service/user.py:444-534` — `load_user`,
  `api_current_user`, `require_roles` inner, `ui_current_user`,
  `ui_require_roles` inner become `async def`.

- [ ] Every handler `async def`; every service call awaited. Commit
  `refactor(controllers): async route handlers and dependencies`.

### Task B5 — CLI under `asyncio.run`

**Files:**
- Modify: `argus/backend/cli.py:32-88`,
  `argus/backend/service/build_system_monitor.py:27-30` (loads move into
  `async def collect()`; Jenkins calls via `to_thread`)

- [ ] Commit `refactor(backend-cli): run the async bodies under asyncio.run`.

### Task B6 — The test suite on the new model

**Files:**
- Modify: `argus/backend/tests/conftest.py` (`asyncio.run(sync_models(...))`
  at 161; `release`, `group`, `fake_test` async; `spec=JenkinsService` /
  `spec=IssueService` on the two mock fixtures),
  `tests/integration/conftest.py:57-80`, `tests/asgi/conftest.py`,
  `tests/widgets/conftest.py`, `tests/replay/test_replay_service.py:80-122`
  (fake client `async def post/request`), and every test that calls a model
  directly (~30 files, ~259 lines): `async def` + `await`.
  `tests/test_stats_snapshot.py:259-409` and
  `tests/issues/test_jira_unification.py:213-248` await `collect()` /
  `fetch_issues()`.
- Test: `tests/asgi/test_foundation.py` — every `APIRoute.endpoint` in
  `asgi_app.routes` is `inspect.iscoroutinefunction`; run
  `tests/db/test_paging.py` from B1.

- [ ] `uv run pytest` green. Grep gates from `spec.md`/plan verification
  empty. Commit `test(backend-suite): async fixtures and model calls, paging and handler gates`.

---

## Group C — the concurrency pass

Each task: read the function, apply the gather per `spec.md` § Concurrency
rules, keep result order, run the listed tests, verify, commit with a body
line stating the serial-depth change.

### Task C1 — `gather_limited`

Outcome: the helper and its first caller landed inside the flip commits
(`refactor(models): switch the documents to coodie.aio`) because the fan-out
reads rewritten there needed it; this task kept only the test.

**Files:** `argus/backend/util/common.py`; test `argus/backend/tests/util/test_common.py`
(order preserved, in-flight never exceeds `limit`, first exception propagates).
Already introduced in B2 for `get_versions_by_run_ids`; this task adds the
test. Commit `test(util/common): cover gather_limited`.

### Task C2 — View stats (`stats.py:620-660`, `245-285`)

**Internals:** `ViewStatsCollector.collect` → `_fetch()` gathering test
chunks, then one gather of plugin stats, plans, links, comments, releases,
groups, then one gather of GitHub/Jira per issue chunk; `fetch_issues` →
`_fetch_links(release_ids)` + `_resolve_links(links)`;
`_fetch_multiple_release_queries` gathers per release, drops the `hasattr`
branch; timing log line. Test: `tests/view_api/test_view_api.py:261-283` plus
a new test on a seeded view with a run, a linked issue and a comment
(reuse `tests/widgets/conftest.py` `seeded_view_with_run`,
`linked_github_issue`). Commit `perf(service/stats): fetch view stats concurrently`.

### Task C3 — Release stats (`stats.py:537-606`, `336-366`)

Keep release → snapshot serial; `dormant` early return before the fan-out;
gather tests, plans, links, comments, groups; gather stats rows and issue
resolution; awaited snapshot write. Tests: `tests/test_stats_snapshot.py`,
`tests/api/test_release_api.py:290`. Commit
`perf(service/stats): fetch release stats concurrently`.

### Task C4 — Run page (`plugins/sct/testrun.py:503-516`)

Gather `cls.get(id=run_id)`, junit, nemeses, resources inside the existing
`except DocumentNotFound`. Tests: `tests/testrun_api/test_testrun_api.py:72-84`,
`tests/sct_api/test_sct_api.py:503-513, 280-320`. Commit
`perf(plugins/sct): load run sub-tables with the run`.

### Task C5 — Graphed and nemesis stats widgets

`controller/views_widgets/graphed_stats.py:28-31`,
`nemesis_stats.py:18-20`: `gather_limited` per test; the services gather
nemesis chunks. Tests: `tests/widgets/test_graphed_stats_widget.py`,
`test_nemesis_stats_widget.py`. Commit
`perf(views_widgets): fan out graphed and nemesis stats per test`.

### Task C6 — Results service and its widgets

`results_service.py`: `get_test_graphs` gathers runs_details + tables_meta
then per table data + best results (`get_best_results(..., runs_details=None)`);
`get_run_results` gathers per table; `get_tests_by_version` gathers per-test
runs. `controller/views_widgets/graphs.py:24-63` and `summary.py:28-35`
`gather_limited` per test / per triple. Tests: `tests/widgets/test_graphs_widget.py`,
`test_summary_widget.py`, `tests/results_service/`. Commit
`perf(service/results): gather tables and per-test runs`; split into two if
over ~300 lines.

### Task C7 — Runs details (`service/views_widgets/graphed_stats.py:85-150`)

Gather link chunks with `gather_limited` run lookups; then gather GitHub and
Jira for all ids. Test: `tests/widgets/test_graphed_stats_widget.py:32-101`.
Commit `perf(views_widgets): gather run details lookups`.

### Task C8 — Similar runs (`plugins/sct/service.py:728-870`)

Links → gather[GH, Jira, ≤20 run gets] → gather step-5 gets. Test: extend
`tests/sct_api/test_sct_api.py:714-744` with a run that has a linked issue,
assert `issues[0].subtype`. Commit `perf(plugins/sct): gather similar-run lookups`.

### Task C9 — Planned jobs (`service/argus_service.py:316-351`)

`plugin.model.find(build_id__in=chunk).per_partition_limit(1).all()` per
plugin per chunk, gathered; drop the dead `except DocumentNotFound`;
`get_jobs_for_user` gathers the plugins and returns a list. Test: extend
`tests/api/test_users_jobs_api.py:173-182` with a plan owned by the user and
a submitted run, assert `last_run.id`. Commit
`perf(service/argus): resolve last runs with a partition IN`.

### Task C10 — Long tail

Run-type probing (`testrun.py:100-109`, `test_lookup.py:44-50`,
`client_service.py:197-204`) via gathered `find_one`, first non-`None` in
plugin order; `client_service.get_run_info` gathers test/comments/events then
group/release; `views.refresh_stale_view` fetches the plan once and gathers;
`TestLookup.index` and `make_single_run_response` gather. Tests: existing
`tests/client_api/`, `tests/view_api/`, `tests/api/` lookup tests. Commit
`perf(services): probe plugin models concurrently`.

### Task C11 — Jenkins triggers (`planner_service.py:693-793`)

Extract `_trigger_one(...)` keeping its `try/except`;
`gather_limited(to_thread(...), limit=5)`; gather the test chunk reads. Test:
`tests/integration/test_trigger_jobs.py`. Commit
`perf(service/planner): trigger Jenkins jobs in bounded threads`.

### Task C12 — Mention notifications (`testrun.py:371-419`, `notification_manager.py`, `highlights.py:225-246`)

Gather mention lookups; gather release + run; gather per-mention sends with
event creation and snapshot invalidation; DB saver gathers its two
`User.get`. Tests: `tests/testrun_api/test_testrun_api.py:212-266`,
`tests/notification_api/`. Commit
`perf(service/testrun): send mention notifications concurrently`.

### Task C13 — Architecture note

**Files:** `docs/project/architecture.md` — a short paragraph on the async
execution model (async handlers, coodie aio, `to_thread` for external
clients, the paging bridge). Commit `docs(architecture): describe the async execution model`.

---

## Verification before the pull request

- `uv run pre-commit run --all-files`, `uv run pytest`, `yarn test`.
- Grep gates, empty: `coodie.sync` in `argus/` and `argus_backend.py`;
  `execute_concurrent|BatchStatement|read_fast|\.prepare\(` in
  `argus/backend`; `session\.execute` only in `models/pytest.py` DDL and the
  conftest `DESCRIBE`; `execute_raw` at exactly three sites; `\.result()`
  outside tests; `^def ` in the controller modules only for non-route helpers.
- `uvx ruff check --isolated --select ASYNC,RUF029 argus/backend`; review
  hits.
- Smoke on a local Scylla: `sync-models`, gunicorn, an SCT run page with many
  events, a release dashboard with `force=1`, a view's stats widget, the
  pytest widget, ignore-jobs, replay ingest. Watch for `Unprepared statement`
  log lines settling.
- Before/after medians with `curl -w "%{time_total}"` on `/api/v1/views/stats`,
  `/api/v1/release/stats/v2?...&force=1`, a run page and the four widgets;
  the fetch/collect log lines.

## Outcomes recorded after the build

- `test_backfill_migration_is_idempotent` and its `migration` fixture were
  removed in the flip: the test executed `scripts/migration/migration_2026-04-22.py`,
  a frozen sync script that cannot run against the aio models and will not run
  again.
- The review found four items and they were fixed on the branch: one SMTP
  conversation at a time per `Email` (concurrent mention sends shared a
  connection), an exception guard in the paging callback of `await_all_pages`,
  `gather_limited` closing the coroutines it never started on cancellation, and
  the SCT event submit route fanning out through `gather_limited`.
- Behaviour changes that ride with the refactor, for the pull request body:
  `_exclude_disabled_tests` drops an unknown test id instead of raising, and
  the GitHub and Jira local lookups no longer swallow a driver error behind a
  bare `except`.
- The pull request review added seven items, all fixed on the branch: coredump
  links written once per event batch, password hashing off the loop, the stats
  build off the loop, the two pre-existing bugs (issue deletion with links on
  other runs, group names in the view editor), the two 2026-09-08 token
  migration scripts and the four `dev-db` scripts ported to the aio models. The
  `dev-db` scripts were checked statically and need one run against a dev
  database.
