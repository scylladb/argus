# ARGUS-252 — implementation plan

**Spec:** `tasks/ARGUS-252/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

The server picks the build path and the number, the build URL is
absolute, and a replayed run keeps its recorded run ID.

## Rules

- Follow `docs/standards/`. Raise `DataValidationError` for a bad request
  value, before the service dispatches a record.
- The replay service tests need no database. Mock the model reads, as the
  existing replay tests do.
- No schema change and no data script.
- Go tests use testify and call `t.Parallel()`.
- Verify sequence: section `Commands` of `CLAUDE.md`, plus
  `cd cli && make lint && go test -race ./...`.

## Task 1 — Server: the request parameters and the run summary

**Files:**
- Modify: `argus/backend/controller/replay_api.py` (`replay_ingest`)
- Modify: `argus/backend/service/replay_service.py` (`ReplaySummary`,
  `__init__`, `ingest`, `_dispatch_all`, `_runs_in`, `_record_run_id`,
  `_is_submit`)
- Test: `argus/backend/tests/replay/test_replay_controller.py`
- Test: `argus/backend/tests/replay/test_replay_service.py`

**Internals:** `replay_ingest` takes `as_me`, `local_runs` and `test_name`.
`create_missing_tests` changes from `False` to `None`, so the service picks
the default. The controller passes the caller and `BASE_URL` as
`argus_url`. `_runs_in` lists the distinct runs that the records address,
with the type from `location_params.type` or `test_type`. `ReplaySummary`
gets `runs`. `_dispatch_all` adds the run ID of each failed `submit_run` to
`_failed_submits`, and `ingest` sets `failed` on each entry of `runs`.

- [x] Write the failing tests: the controller passes the new parameters,
  the caller and `BASE_URL`, the summary lists each run, a run whose
  `submit_run` fails is marked `failed`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Server: the `local-runs` path and the build numbers

**Files:**
- Modify: `argus/backend/service/replay_service.py` (`ingest`,
  `_local_build_path`, `_local_job_name`, `_path_name`, `_model_for`,
  `_run_models`, `_run_exists`, `_run_build_numbers`,
  `_assign_build_numbers`, `_rewrite_submits`, `_process_one`,
  `_without_build_url`)
- Modify: `argus/backend/plugins/driver_matrix_tests/model.py`
  (`submit_matrix_run`)
- Test: `argus/backend/tests/replay/test_replay_service.py`
- Test: `argus/backend/tests/driver_matrix_tests/driver_matrix_api/test_driver_matrix_api.py`

**Internals:** With `local_runs` and an archive of one `submit_run` without
a build URL, `_local_build_path` returns `local-runs/<caller>/<test>`.
`<test>` is `test_name`, else the first SCT config file, else the last name
of the recorded path, else `local-run`. `_path_name` keeps
`A-Z a-z 0-9 . _ -`. A `test_name` without a build path, or with no
accepted character, raises `DataValidationError`. A build path without
`argus_url` raises `ReplayServiceError` before dispatch. `_run_exists`
reads the run by ID and maps `DocumentNotFound` to `False`. `ingest` keeps
the new runs in `_new_runs` and the others in `_kept_runs`.
`_assign_build_numbers` gives each new run the next number above the
highest one under the path, across every plugin. `_rewrite_submits` sets
the path and `<BASE_URL>/test/<path>/<n>/` under the keys of each plugin.
`create_missing_tests` resolves to `bool(_new_runs)` when the request does
not set it. The `submit_run` of a kept run gets neither the hierarchy
pre-step nor the missing-test check. `_without_build_url` keeps the build
URL off the test entity. `submit_matrix_run` sets `build_number` from
`job_url` with `get_build_number`.

- [x] Write the failing tests: a local run gets the path and the next
  number, `test_name` names the test and needs one local run, a name loses
  the characters a path rejects, a run that Argus holds replays as recorded
  and gets no number, a second replay creates no test and reports no
  missing test, a replay without `BASE_URL` fails with nothing dispatched,
  a legacy driver-matrix run gets the build number of its URL.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — Server: the owner and the log back-fill

**Files:**
- Modify: `argus/backend/service/replay_service.py` (`_resolve_owner`,
  `_rewrite_submits`, `_stamp_runs`, `_stamp_error`, `_assign_new`,
  `_assign_existing`, `_build_log_backfill_records`)
- Test: `argus/backend/tests/replay/test_replay_service.py`

**Internals:** `_resolve_owner` turns `as_me` on for a build path when the
request does not set it, and sets `_owner` to the caller. The `submit_run`
of a new run carries the owner as `started_by`. After the back-fill,
`_stamp_runs` skips a failed run, saves the assignee of a new run, and
calls `TestRunService.change_run_assignee` for a run that existed, only
when the assignee differs. A failure there adds a `stamp_run` error and the
replay continues. `_build_log_backfill_records` starts from `_runs_in`, so
a run without a recorded `logs/submit` gets its S3 logs.

- [x] Write the failing tests: a new run gets the owner as starter and
  assignee, an existing run changes only its assignee through the test run
  service, a failed run gets no assignee, a failed save adds a `stamp_run`
  error, a local run without a recorded `logs/submit` gets its S3 logs.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 4 — CLI: the flags and the run links

**Files:**
- Modify: `cli/cmd/replay.go` (`RunE`, `replayOptions`, `optionalBool`,
  `uploadReplay`, `replayRunLink`, `replayReport`, `runLinks`, `runLine`,
  `renderReplaySummary`, flags, help)
- Modify: `cli/internal/api/api.go` (`RunPageURL`)
- Modify: `cli/internal/models/replay.go` (`ReplayIngestSummary.Runs`,
  `ReplayRun`)
- Test: `cli/cmd/replay_upload_test.go`
- Test: `cli/internal/replay/extract_test.go`,
  `cli/internal/replay/pack_test.go` (`t.Parallel()`)

**Internals:** `uploadReplay` takes `replayOptions`. It sends `local_runs`
unless the user gives `--keep-run`, and sends `test_name` for `--test`.
`--as-me` and `--create-missing-tests` go out only when the user sets them.
`--keep-run` and `--test` exclude each other. `runLinks` gives each run
its `RunPageURL`, except in a dry run and for a failed run. `runLine`
prints the link, `failed: see the errors below`, or `would replay as` for
a dry run.

- [x] Write the failing tests: the query of each flag, no `local_runs`
  with `--keep-run`, a line per run, no link for a failed run or a dry run.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 5 — Documentation

**Files:**
- Modify: `cli/README.md` (section `Replaying a run`, after
  `Configuration`)
- Modify: `docs/api_usage.md` (`POST /api/v1/client/replay/ingest`)

- [x] Describe `local_runs`, `as_me`, `test_name`, the defaults, the
  `BASE_URL` rule, `runs` with `failed`, and the `hydra collect-logs` step.
- [x] Run `uv run pre-commit run --all-files`.
- [x] Commit, with the boxes of this task checked.
