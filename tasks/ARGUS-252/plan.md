# ARGUS-252 — implementation plan

**Spec:** `tasks/ARGUS-252/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

This plan covers the second round of the task: the release check, the CLI
check of `--build-id`, `source_run_id`, and resume. The first round (retarget,
`as_me`, the defaults, the run links) took the spike path and has no plan.

## Rules

- Follow `docs/standards/`. Raise `DataValidationError` for a bad request
  value, before the service reads the archive.
- The replay service tests need no database. Mock the model reads, as the
  existing replay tests do.
- The schema change is one additive column on `PluginModelBase`.
  `sync-models` applies it. No data script.
- Go tests use testify and call `t.Parallel()`.
- Verify sequence: section `Commands` of `CLAUDE.md`, plus
  `cd cli && make lint && go test -race ./...`.

## Task 1 — Build path form and release check

**Files:**
- Modify: `argus/backend/service/replay_service.py` (`_check_build_id`,
  `ingest`)
- Test: `argus/backend/tests/replay/test_replay_service.py`

**Internals:** `_check_build_id` requires two or more names.
`_check_release(build_id)` reads `ArgusRelease` by the first name and raises
`DataValidationError` when it is missing. `ingest` calls both before it reads
the archive, on a dry run too.

- [x] Write the failing tests: a one-name path fails, a missing release fails
  with nothing dispatched, an existing release passes.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — `source_run_id` column and the stamp step

**Files:**
- Modify: `argus/backend/plugins/core.py` (`PluginModelBase`)
- Modify: `argus/backend/service/replay_service.py` (`_assign_owner` becomes
  `_stamp_runs`, `_dispatch_all`)
- Test: `argus/backend/tests/replay/test_replay_service.py`

**Internals:** `PluginModelBase.source_run_id: Optional[UUID] = None`.
`_stamp_runs` runs when the replay retargets or has an owner. Per run that
`submit_run` did not fail, it sets `source_run_id` on a retargeted run, and
`assignee` and `started_by` when an owner is set, then saves once. A failure
adds an `assign_owner` error.

- [x] Write the failing tests: a retargeted run gets `source_run_id` without
  an owner, an owned run without `build_id` gets no `source_run_id`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — Resume a replay

**Files:**
- Modify: `argus/backend/service/replay_service.py` (`__init__`, `ingest`,
  `_retarget`)
- Modify: `argus/backend/controller/replay_api.py` (`resume_run_id` query)
- Test: `argus/backend/tests/replay/test_replay_service.py`
- Test: `argus/backend/tests/replay/test_replay_controller.py`

**Internals:** `ReplayService(resume_run_id: UUID | None)`.
`_check_resume(records)` requires `build_id` and one run in the records,
loads the run through `ClientService().get_model(type)`, and compares its
`source_run_id` and `build_id`. `_retarget` maps the one run to
`resume_run_id` in place of a new UUID.

- [x] Write the failing tests: resume reuses the ID, resume without
  `build_id` fails, a mismatched `source_run_id` or `build_id` fails, two
  runs in the archive fail, a missing run fails, the controller forwards
  `resume_run_id`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 4 — CLI: check `--build-id`, add `--resume`

**Files:**
- Modify: `cli/cmd/replay.go` (`RunE`, `replayOptions`, `uploadReplay`, flags)
- Test: `cli/cmd/replay_upload_test.go`

**Internals:** `checkBuildID(string) error` with the rule of Task 1, called
before the archive is packed. `replayOptions.ResumeRunID string`, sent as
`resume_run_id`.

- [x] Write the failing tests: `checkBuildID` table, `resume_run_id` reaches
  the server.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 5 — Run page: "Replayed from"

**Files:**
- Modify: `frontend/TestRun/TestRunInfo.svelte`
- Modify: `frontend/TestRun/Generic/GenericTestRunInfo.svelte`
- Test: `frontend/TestRun/Generic/GenericTestRunInfo.test.ts` (create)

**Internals:** a list item under "Started by", shown when
`test_run.source_run_id` is set, linking to `/test_run/<source_run_id>`.

- [x] Write the failing test: the line shows with the link when the field is
  set, and is absent when it is not.
- [x] Run it and confirm the failure.
- [x] Write the smallest change that passes it.
- [x] Run the verify sequence, and `yarn build`.
- [x] Commit, with the boxes of this task checked.

## Task 6 — Documentation

**Files:**
- Modify: `cli/README.md` (section `Replaying a run`)
- Modify: `docs/api_usage.md` (`POST /api/v1/client/replay/ingest`)
- Modify: `cli/cmd/replay.go` (the long help)

- [x] Describe the release rule, `--resume`, and "Replayed from".
- [x] Run `uv run pre-commit run --all-files`.
- [x] Commit, with the boxes of this task checked.
