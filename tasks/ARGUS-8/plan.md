# ARGUS-8 — implementation plan

**Spec:** `tasks/ARGUS-8/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

**Code**
- Imports sit at the top of the module.
- No comments or docstrings that justify the change. Fix a comment only when
  it became wrong.
- No dual write to the legacy column and no fallback read from it.

**Tests**
- Backend tests create and read rows through the services or the API, never
  through `Model.save()` or `find()` in a test body.
- Every backend test with ScyllaDB needs Docker.
- Run Vitest under Node 22:
  `npx -y node@22 node_modules/vitest/vitest.mjs run`.

**Commits**
- The commitlint header has the form `<type>(<scope>): …`, the scope has at
  least 5 characters, and the header is at most 72 characters.
- The body has at least 30 characters.
- The last line is `Task: ARGUS-8`.
- No Co-Authored-By line.
- `git add` takes explicit paths only.
- Commit through `uv run git commit`.

## Task 1 — Fix the release kernel report on the current column

The report fails today. Fix it before the column moves, so the move in Task 2
changes only where the packages come from.

**Files:**
- Modify: `argus/backend/plugins/sct/service.py:958-1000`
- Test: `argus/backend/tests/sct_api/test_sct_api.py`

**Internals:** `get_scylla_version_kernels_report` reads each package through
its attributes (`p.name`, `p.version`, `p.date`, `p.revision_id`). The status
counts key on `kernel_package.version` in both places.

- [x] Write the failing test: two runs in one release submit `scylla-server`
  and `kernel` packages through the API, one run passes and one fails.
  `GET /api/v1/client/sct/release/{name}/kernels` returns both kernels under
  the `version-date.revision_id` key, with the status counts.
- [x] Run it and confirm the `TypeError`.
- [x] Write the smallest change that passes it.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit `fix(plugins/sct): read the kernel report packages by attribute`.

## Task 2 — Store and read packages in sct_package

One commit. Every reader moves together with the write, so the suite passes
at the commit.

**Files:**
- Modify: `argus/backend/plugins/sct/testrun.py`:
  - Add `SCTPackage` next to `SCTResource` (:169).
  - Change `delete_run_data` (:188), the `packages` field (:203),
    `get_version_data_for_release` (:294), `get_perf_results_for_test_name`
    (:324), `sut_timestamp` (:490) and `get_run_response` (:512).
- Modify: `argus/backend/plugins/sct/plugin.py:3-46`.
- Modify: `argus/backend/plugins/sct/udt.py:9-22`, removing `PackageVersion`.
- Modify: `argus/backend/plugins/sct/service.py`:
  - Imports (:43).
  - `submit_packages` and `process_target_version` (:111-148).
  - `get_performance_history_for_test` (:344).
  - `get_similar_runs_info` (:798-950).
  - The kernel report (:958).
- Modify: `argus/backend/service/results_service.py`:
  - Imports (:20), `RunsDetails` (:82), the helpers' hints (:358, :370, :410).
  - `_load_runs_details` (:428-435) and `get_tests_by_version` (:620-645).
- Modify: `argus/backend/service/views_widgets/graphed_stats.py:17-60, 95-160`.
- Modify: `argus/backend/service/views_widgets/nemesis_stats.py:11-30`.
- Modify: `argus/backend/service/email_service.py`, the `Main` and `Packages`
  sections (:79-110).
- Test, new cases in `argus/backend/tests/sct_api/test_sct_api.py`:
  - Submit, then read through the run response.
  - A resubmission is idempotent.
  - Concurrent submissions with different packages all persist. This replaces
    `test_submit_packages_concurrent_submissions_keep_one_row`, which forced
    the conditional-write retry.
  - A heartbeat that saves the run after a submission keeps its packages.
  - A target package sets `scylla_version` and `version_source`.
- Test, update to the table:
  - `argus/backend/tests/results_service/test_results_service.py:116-160`:
    submit through `SCTService.submit_packages`.
  - `test_chartjs_additional_functions.py`: value objects become
    `SCTPackage.model_construct(...)`. `test_create_chartjs.py` needs no change.
  - `argus/backend/tests/widgets/test_graphed_stats_widget.py:64`.
  - `argus/backend/tests/testrun_api/test_testrun_service.py:33`: the
    full-only field becomes `screenshots`.
  - `integration/test_sct_lifecycle.py`: the client run info no longer carries
    `packages`, so the test reads them from the run response.
  - Re-run `email_service/test_email.py` and `release_summary/test_hooks.py`.
    Each must pass unchanged.

**Internals:**

`SCTPackage(Document)`:
- Fields: `run_id` (partition key), `name` (clustering key), `version`, `date`,
  `revision_id`, `build_id`.
- Table name: `sct_package`.
- `classmethod for_runs(run_ids) -> dict[UUID, list[SCTPackage]]`:
  - `chunk(run_ids)` (`argus/backend/util/common.py:58`).
  - One `find(run_id__in=batch).all()` per batch, through `gather_limited`, so a
    view over thousands of runs keeps at most 50 reads in flight.
  - Then groups the rows by `run_id`.
  - Returns `{}` for no ids.

`SCTTestRun`:
- Loses the `packages` field.
- `get_packages()` returns `SCTPackage.find(run_id=self.id).all()`.
- `sut_timestamp` reads `await self.get_packages()`.
- `get_run_response` adds the package read to its `gather` and sets
  `response["packages"]`.
- `delete_run_data` adds `SCTPackage` to its loop.
- `get_version_data_for_release` and `get_perf_results_for_test_name` select
  `id` without `packages`. Each row gets `row["packages"]` from `for_runs`.

`SCTService.submit_packages(run_id, packages)`:
1. `SCTTestRun.get(id=run_id)`; `DocumentNotFound` raises `SCTServiceException`.
2. Build one `SCTPackage` per entry. A later entry wins over an earlier one of
   the same name.
3. Save them in an `AsyncBatchQuery(logged=False)`.
4. For each target package, call `process_target_version`.
5. When the submission holds a target package, call
   `run.update(version_source=..., scylla_version=...)`, then `index_version()`
   and `mark_release_summary_stale(run.release_id)`, as the old code did.
6. Return `"added"`.

`CONDITIONAL_WRITE_ATTEMPTS` stays, because the nemesis-stats write uses it.

`get_similar_runs_info` reads the packages of each similar run with
`for_runs` over the ids it loads.

`ResultsService._load_runs_details`:
- Selects `id` and `investigation_status`.
- Calls `SCTPackage.for_runs` over the non-ignored ids only when
  `plugin.model is SCTTestRun`. Otherwise `packages` is `{}`.

`get_tests_by_version`, `graphed_stats.get_graphed_stats` and
`nemesis_stats.get_nemesis_data` work the same way, per test.
`graphed_stats.get_runs_details` makes one `for_runs` call over its id list.

`email_service`: `Main` and `Packages` read `await self.test_run.get_packages()`
in `create_context`, which is async; `default_options()` is not, and loses its
`packages` key.

- [x] Write the failing tests.
- [x] Run them and confirm the failures. On the old code the heartbeat test
  loses the submitted package, and the one-row-per-name test fails on the old
  append.
- [x] Write the change.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit `feature(plugins/sct): store packages in their own table`.

## Task 3 — Read a run's packages through the client

**Files:**
- Modify: `argus/backend/plugins/sct/controller.py:92-100`.
- Modify: `argus/backend/plugins/sct/service.py`.
- Modify: `argus/client/sct/client.py:17-31, 146-160`.
- Test: `argus/backend/tests/sct_api/test_sct_api.py`.
- Test: `argus/backend/tests/integration/test_sct_lifecycle.py`.
- Test: `argus/backend/tests/release_cleanup/test_release_cleanup_api.py`. A
  deleted run leaves no packages. The route is the read that does not go
  through the run row, so this test lands here.

**Internals:**
- Route `GET /{run_id}/packages/get`, named
  `api.client_api.sct_api.sct_get_packages`, with `Depends(api_current_user)`.
  It returns `APIResponse({"status": "ok", "response": ...})`.
- `SCTService.get_packages(run_id) -> list[SCTPackage]`.
- `ArgusSCTClient.Routes.GET_PACKAGES = "/sct/$id/packages/get"`.
- `ArgusSCTClient.get_packages() -> list[dict]` follows `get_resources()`.

- [x] Write the failing tests: the route returns the submitted packages,
  `sct_client.get_packages()` returns them in the lifecycle test, and a
  deleted run has none.
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit `feature(plugins/sct): return the packages of a run to clients`.

## Task 4 — Copy the existing packages

**Files:**
- Create: `scripts/migration/migration_<date>_copy_packages_to_sct_package.py`,
  dated the day it is written.

**Internals:**
- `asyncio.run(copy_rows(args.run_id))`, with an argparse `--run-id`.
- The docstring states the deploy order:
  1. `sync-models`
  2. this script
  3. the release flip
  4. this script again
- `legacy_rows(run_id)`: paged raw CQL `SELECT id, packages FROM {ks}.sct_test_run`,
  with `WHERE id = %s` for one run, served by the existing index on `id`.
- Keep the first entry per name. Build `SCTPackage.model_construct(...)` for
  each.
- Add the rows to a 64 KB unlogged batch, the `FinishedRowBatch` pattern of
  `migration_2026-10-19_copy_nemesis_to_v2.py`, copied, not imported.
- Count runs, rows, batches and failures. Log progress every 5000 runs and a
  summary at the end.
- No unit test. No migration script has one. Task 5 checks it on the dev
  cluster.

- [x] Write the script.
- [x] Run `uv run pre-commit run --all-files`.
- [x] Commit `feature(scripts/migration): copy packages into sct_package`.

## Task 5 — Check on the dev cluster

No commit. Record the results in the pull request body.

- [x] From the worktree, run `sync-models` against the dev cluster. Confirm
  that `sct_package` exists and `sct_test_run.packages` stays.
- [x] Run the backfill. The row count equals the sum of distinct names per run
  (from the shape scan: 12,443 runs). Run it again; the count stays.
- [x] Compare the change against master on the same runs. The running dev
  server serves another branch, so both sides run one authenticated
  `TestClient` script on the dev data, one from a master checkout:
  - The run page Packages tab, the details versions and the issue template.
  - A results chart with release markers.
  - The Summary, Graphed Stats and Nemesis Stats widgets.
  - The perf history.
  - The kernel report.
  - An email report preview.
- [x] Import the app on Python 3.13, as the release bundle runs it.

The dev data holds no SCT test with result tables and no perf run with
packages, so the results chart and the perf history rest on the backend tests.
