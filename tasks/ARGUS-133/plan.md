# ARGUS-133 — implementation plan

**Spec:** `tasks/ARGUS-133/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

The change touches `cli/` only. No backend, frontend or schema change.

## Rules

- Follow `docs/standards/`. Go tests use testify.
- A command test drives the package-level command through its `RunE`
  against an `httptest` server, with the context helpers of
  `cli/cmd/run_issue_test.go` (`runIssueRuns`). A nil cache in the context
  turns the cache off. A test that sets a flag on a package-level command
  restores it in `t.Cleanup`, so these tests do not call `t.Parallel()`.
- Export `XDG_CACHE_HOME` to a scratch directory before any CLI test or
  probe.
- Verify sequence: `cd cli && make fmt && make lint && go test -race ./...`,
  then `uv run pre-commit run --all-files` from the repository root.

## Task 1 — `run get --full` replaces `run details`

**Files:**
- Delete: `cli/cmd/run_details.go`
- Modify: `cli/cmd/testrun.go` (`newRunFetcher`, `getRunCmd`, `init`)
- Test: `cli/cmd/testrun_get_test.go` (new)

**Internals:** `fetchFullRun(ctx, client, c, runType, runID) (any, error)`
takes the body of the `fetchRun` closure of `newRunFetcher`: the
`RunTypeHandlers` lookup, the `cache.RunKey` read through
`runTypeCacheGetters`, the `TestRunGet` request, the write through
`runTypeCacheSetters`. An unknown type returns
`unknown run type %q, valid types: <ValidRunTypes()>`. `newRunFetcher`
passes `fetchFullRun`. `getRunCmd` reads `--full`. After the type
resolution, `--full` writes `models.NewKVTabular(fetchFullRun(...))`. The
summary path stays as it is. The Long help names `--full`.

- [x] Write the failing tests: `run get --full` against a stub SCT run
  prints a field only the whole run holds (`packages`), `run get` without
  the flag does not print it, and `runCmd` has no `details` sub-command.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — `run logs list` prints the names only

**Files:**
- Modify: `cli/internal/models/runs.go` (`LogEntry`)
- Modify: `cli/cmd/logs.go` (`logEntriesFromPairs`, `logEntriesFromMap`)
- Test: `cli/cmd/logs_test.go`

**Internals:** `LogEntry` keeps `Name` only. `logEntriesFromPairs` takes
`p[0]` and still skips a pair without a link, which the download endpoint
cannot serve. `logEntriesFromMap` keeps the sorted names.

- [x] Write the failing test: `run logs list` against a stub SCT run with
  two logs prints `[{"name": …}, {"name": …}]` and no `url` key.
- [x] Run it and confirm the failure.
- [x] Write the smallest change that passes it.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — failures by default on both pytest commands

**Files:**
- Create: `cli/internal/services/pytest.go`
- Modify: `cli/cmd/pytest.go` (`pytestResultsCmd`, `validPytestStatuses`,
  `init`)
- Modify: `cli/cmd/testrun.go` (`runPytestResultsCmd`, `init`)
- Test: `cli/internal/services/pytest_test.go` (new)
- Test: `cli/cmd/pytest_test.go` (new)

**Internals:**
- `services.PytestStatuses []string` holds the ten `models.PytestStatus*`
  values in backend enum order.
- `services.DefaultPytestStatuses() []string` returns the six statuses of
  the spec.
- `services.ParsePytestStatuses(values) ([]string, error)` returns
  `parseEnum(values, PytestStatuses, "status")`.
- In `cmd/pytest.go`:
  - `addPytestStatusFlag(cmd)` registers `--status` as a `StringSlice`
    with a nil default. Its usage text names the default, the
    `--status ""` lift, and every value. It replaces `validPytestStatuses`.
  - `pytestStatusFilter(cmd) ([]string, error)` returns the default when
    `--status` was not changed. Otherwise it returns the parsed values.
  - `filterPytestResults(results, statuses)` keeps the results whose status
    is in `statuses`. An empty `statuses` keeps every result.
- `pytestResultsCmd` sends `pytestStatusFilter` as `status[]`.
  `runPytestResultsCmd` filters the cached or fetched list. Both Long helps
  describe the default.

- [ ] Write the failing tests:
  - The default holds the six DTest statuses and none of `passed`,
    `skipped`, `xfailed`, `xpass`.
  - The parser trims, skips empty values, and rejects an unknown status.
  - `pytestStatusFilter` on a fresh command returns the default with no
    flag, the given values with `--status`, nothing with `--status ""`, and
    an error for an unknown value.
  - `pytest results` against a stub sends the default `status[]`, and sends
    none with `--status ""`.
  - `run pytest-results` against a stub drops the `passed` and `skipped`
    rows by default, and keeps them with `--status ""`.
- [ ] Run them and confirm the failure.
- [ ] Write the smallest change that passes them.
- [ ] Run the verify sequence.
- [ ] Commit, with the boxes of this task checked.
