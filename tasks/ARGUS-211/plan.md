# ARGUS-211 — implementation plan

**Spec:** `tasks/ARGUS-211/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- The change lives under `cli/` only. Verify with
  `cd cli && make fmt && make lint && go test -race ./...`, then
  `uv run pre-commit run --all-files`. The change touches no backend or
  frontend code, so `uv run pytest` and `yarn test` have nothing to cover.
- Every exported Go symbol gets a doc comment, as the surrounding code does.
  No comment that justifies the change.
- Tests use `testify` (`assert`, `require`), as the package tests do. Service
  tests run against an `httptest` server and never against a real Argus.
- Commits:
  - commitlint header `feature(cli/issue): …`
  - a body of at least 30 characters
  - the last line is `Task: ARGUS-211`
  - no `Co-Authored-By` trailer
  - `git add` by explicit path only. Leave `pyproject.toml` and `uv.lock` alone.
- Leave the code uncommitted until Komachi reviews it.

## Task 1 — Decode the lookup and map it to run rows

**Files:**
- Modify: `cli/internal/models/issues.go`
- Create: `cli/internal/models/issues_test.go`
- Create: `cli/internal/models/rawjson.go`
- Create: `cli/internal/models/rawjson_test.go`

**Internals:**
- `LinkedRun`: the fields of one element of `links` that a summary row
  reads: `run_id`, `test_name`, `status`, `start_time`, `build_id`,
  `build_number` (`*int`), `scylla_version`, `product_version`, `url`. A null
  version decodes to `""`.
- `func (l LinkedRun) Version() string`: `scylla_version` when it is not
  empty, else `product_version`.
- `IssueLinks{Links []LinkedRun; raw RawJSON}`. `(*IssueLinks).UnmarshalJSON`
  decodes the links and keeps a copy of the payload bytes. `Raw()` returns
  them for `--raw`.
- `RawJSON []byte` in `rawjson.go`. `MarshalJSON` returns the bytes, or `null`
  when empty. `Headers()` is `Key, Value`. `Rows()` decodes with `UseNumber()`
  and flattens with `joinKey` from `tabular.go`: sorted object keys, indexed
  array elements, and `null`, `[]` and `{}` as values. A value that is not
  valid JSON is one row with an empty key.
- `IssueRunSummary` with the fields of the spec contract, and
  `Headers()` → `Id, Test, Build Id, Build Number, Version, Status, Start Time, Argus URL`.
  `Rows()` renders the build number with `strconv.Itoa`, or `""` when nil, as
  `JobSummary.Rows` does.
- `IssueRunSummaries []IssueRunSummary`: `Headers()` and `Rows()`, a copy of
  the `JobSummaries` pattern.
- `func (l IssueLinks) Summaries() IssueRunSummaries`: starts from
  `make(IssueRunSummaries, 0, len(l.Links))` and maps each link in order:
  `ID=RunID`, `Test=TestName`, `BuildID`, `BuildNumber`,
  `Version=link.Version()`, `Status`, `StartTime`, `ArgusURL=URL`.

**Tests** (`package models`):
- `TestIssueLinks_Summaries`: two links. Asserts every mapped field, the order,
  and that `url` lands in `ArgusURL`.
- `TestIssueLinks_Summaries_Version`: a Scylla version wins. A product
  version fills in for a missing Scylla version. No version gives `""`.
- `TestIssueLinks_Raw`: a payload with a null, a large number and an unknown
  field comes back byte for byte from `Raw()`, and the links still decode.
- `rawjson_test.go`: the bytes marshal as sent, an empty value marshals to
  `null`, the rows of a payload with `null`, `[]`, `{}` and a large number,
  and the row of invalid JSON.
- `TestIssueLinks_Summaries_Empty`: `IssueLinks{}` marshals its summaries to
  `[]`.
- `TestIssueRunSummaries_Rows`: the headers, one row with a build number and
  one with a nil build number, which renders as `""`.

- [x] Write the failing tests.
- [x] Run `go test ./internal/models/` and confirm that they fail to compile.
- [x] Add the types and `Summaries`.
- [x] Run `go test -race ./internal/models/` until it passes.

## Task 2 — Fetch the lookup

**Files:**
- Modify: `cli/internal/api/routes.go:37-40`
- Create: `cli/internal/services/issues.go`
- Create: `cli/internal/services/issues_test.go`

**Internals:**
- Route: under `// Issue routes`, add
  `IssueLinks = "/api/v1/issues/%s/links" // GET – the issue and the runs linked to it (issue key)`.
- `IssueService{client *api.Client}` and `NewIssueService(client *api.Client) *IssueService`.
  There is no cache argument, because the lookup is never cached.
- `(s *IssueService) Links(ctx context.Context, key string) (models.IssueLinks, error)`:
  `s.client.NewRequest(ctx, "GET", fmt.Sprintf(api.IssueLinks, url.PathEscape(key)), nil)`,
  then `api.DoJSON[models.IssueLinks](s.client, req)`.

**Tests** (`package services_test`, the server wired as in `newJobsSvc` in
`jobs_test.go`, with the `jsonOK` and `jsonErr` helpers of the package):
- `TestIssueService_Links`: the mux serves `/api/v1/issues/SCT-1234/links`
  with an issue and two links. Asserts that `Raw()` holds the issue key and
  a link field that `LinkedRun` does not decode, both run ids in order, the
  test name, the build number, the url and the version fallback.
- `TestIssueService_Links_UnknownKey`: serves `{"issue": null, "links": []}`.
  Asserts that `Raw()` is that payload and that the summaries marshal to
  `[]`.
- `TestIssueService_Links_RejectedKey`: `jsonErr` with
  `Not an issue key: 'SCT1234'`. Asserts that the error holds the message.

- [x] Write the failing tests.
- [x] Run `go test ./internal/services/` and confirm that they fail to compile.
- [x] Add the route and the service.
- [x] Run `go test -race ./internal/services/` until it passes.

## Task 3 — The `issue runs` command

**Files:**
- Modify: `cli/cmd/run_issue.go`
- Modify: `cli/cmd/run_issue_test.go`

**Internals:**
- `issueRunsCmd`:
  - `Use: "runs <issue-key>"`
  - `Short: "List the test runs linked to an issue"`
  - `Args: cobra.MatchAll(cobra.ExactArgs(1), …)`: the second check calls
    `issueKey`.
- `issueKey(arg string) (string, error)`: trims the argument. It rejects an
  empty key with `the issue key is empty`, and `.` or `..` with
  `not an issue key`, since `NewRequest` would resolve them as dot segments.
  - `Long` holds the example `argus issue runs SCT-1234` and says four things:
    the order is newest first, the key may be in any case, a key without runs
    prints an empty list, and `--raw` prints the issue and every link field.
- RunE: follows `issueListCmd`. It sets `cmd.SilenceUsage`, takes the client
  and the outputter from the context, and logs through
  `logging.For(LoggerFrom(ctx), "issue-runs")`: debug before the call, error
  on failure, info with the count. It calls
  `services.NewIssueService(client).Links(ctx, key)` with the key from
  `issueKey`. With `--raw` it writes `links.Raw()`. Otherwise it writes
  `links.Summaries()`.
- `init()`: `issueRunsCmd.Flags().Bool("raw", false, "Emit the issue and its links as returned by the API")`,
  and `issueCmd.AddCommand(issueAddCmd, issueListCmd, issueRunsCmd)`.

**Tests** (`package cmd`):
- `TestIssueRunsCmd`: `issueRunsCmd` is a sub-command of `issueCmd`.
  `Args` rejects zero arguments, two arguments, a blank key, `.` and `..`,
  and accepts one key. The `--raw` flag exists, defaults to `false`, and has
  help text.
- `runIssueRuns` runs `RunE` against an `httptest` stub that serves a payload
  for `SCT-1234`, with a link field the CLI does not know, and an empty
  result for any other key. It returns the output, JSON or `--text`, and the
  request paths. The tests that use it:
  - `TestIssueRunsCmd_PrintsRunRows`: the two summary rows, version fallback
    included.
  - `TestIssueRunsCmd_TrimsTheKey`: `" SCT-1234 "` requests
    `/api/v1/issues/SCT-1234/links`.
  - `TestIssueRunsCmd_UnknownKeyPrintsEmptyList`: `[]`.
  - `TestIssueRunsCmd_RawPrintsThePayloadAsSent`: the output equals the
    stub payload, the unknown field included.
  - `TestIssueRunsCmd_RawTextShowsNulls`: an unknown key under `--raw --text`
    prints the rows `issue null` and `links []`.

- [x] Write the failing test.
- [x] Run `go test ./cmd/` and confirm the failure.
- [x] Add the command.
- [x] Run `go test -race ./cmd/` until it passes.

## Task 4 — README

**Files:**
- Modify: `cli/README.md`, a new section `## Find the runs linked to an issue`
  before the `---` that precedes `## Storage locations`.

The section shows `argus issue runs SCT-1234`, `--text`, and `--raw`. It
names the columns and says that a key without runs prints an empty list and
exits 0.

- [x] Write the section.

## Task 5 — Verify

- [x] `cd cli && make fmt && make lint && go test -race ./...`
- [x] `uv run pre-commit run --all-files`
- [x] Build the binary into the scratchpad and check that `argus issue --help` lists
      `runs`.
- [x] Against Argus: a key with linked runs as JSON, with `--text`, and with
      `--raw`. An unknown key such as `SCT-999999` prints `[]` and exits 0.
      `not-a-key` prints the API error and exits 1.
- [x] Commit, with the boxes of this plan checked, after Komachi's review.
