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

**Internals:**
- `LinkedRun`: one element of `links`. Fields with their JSON names
  `run_id`, `test_id`, `test_name`, `plugin_name`, `status`, `start_time`,
  `build_id`, `build_number` (`*int`), `scylla_version`, `product_version`,
  `linked_on`, `url`. The nullable strings stay `string`, as in `UserJobRun`
  (`cli/internal/models/jobs.go`).
- `IssueLinks{Issue map[string]any; Links []LinkedRun}` with JSON names
  `issue` and `links`.
- `IssueRunSummary` with the fields of the spec contract, and
  `Headers()` → `Id, Test, Build Id, Build Number, Version, Status, Start Time, Argus URL`.
  `Rows()` renders the build number with `strconv.Itoa`, or `""` when nil, as
  `JobSummary.Rows` does.
- `IssueRunSummaries []IssueRunSummary`: `Headers()` and `Rows()`, a copy of
  the `JobSummaries` pattern.
- `func (l IssueLinks) Summaries() IssueRunSummaries`: starts from
  `make(IssueRunSummaries, 0, len(l.Links))` and maps each link in order:
  `ID=RunID`, `Test=TestName`, `BuildID`, `BuildNumber`,
  `Version=ScyllaVersion`, `Status`, `StartTime`, `ArgusURL=URL`.

**Tests** (`package models`):
- `TestIssueLinks_Summaries`: two links. Asserts every mapped field, the order,
  and that `url` lands in `ArgusURL`.
- `TestIssueLinks_Summaries_Empty`: `IssueLinks{}` marshals its summaries to
  `[]`.
- `TestIssueRunSummaries_Rows`: the headers, one row with a build number and
  one with a nil build number, which renders as `""`.

- [ ] Write the failing tests.
- [ ] Run `go test ./internal/models/` and confirm that they fail to compile.
- [ ] Add the types and `Summaries`.
- [ ] Run `go test -race ./internal/models/` until it passes.

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
  with an issue and two links. Asserts `Issue["key"]`, both run ids in order,
  the test name, the build number and the url.
- `TestIssueService_Links_UnknownKey`: serves `{"issue": null, "links": []}`.
  Asserts that `Issue` is nil and that the summaries marshal to `[]`.
- `TestIssueService_Links_RejectedKey`: `jsonErr` with
  `Not an issue key: 'SCT1234'`. Asserts that the error holds the message.

- [ ] Write the failing tests.
- [ ] Run `go test ./internal/services/` and confirm that they fail to compile.
- [ ] Add the route and the service.
- [ ] Run `go test -race ./internal/services/` until it passes.

## Task 3 — The `issue runs` command

**Files:**
- Modify: `cli/cmd/run_issue.go`
- Modify: `cli/cmd/run_issue_test.go`

**Internals:**
- `issueRunsCmd`:
  - `Use: "runs <issue-key>"`
  - `Short: "List the test runs linked to an issue"`
  - `Args: cobra.ExactArgs(1)`
  - `Long` holds the example `argus issue runs SCT-1234` and says four things:
    the order is newest first, the key may be in any case, a key without runs
    prints an empty list, and `--raw` prints the issue and every link field.
- RunE: follows `issueListCmd`. It sets `cmd.SilenceUsage`, takes the client
  and the outputter from the context, and logs through
  `logging.For(LoggerFrom(ctx), "issue-runs")`: debug before the call, error
  on failure, info with the count. It calls
  `services.NewIssueService(client).Links(ctx, args[0])`. With `--raw` it
  writes `models.NewKVTabular(links)`. Otherwise it writes `links.Summaries()`.
- `init()`: `issueRunsCmd.Flags().Bool("raw", false, "Emit the issue and its links as returned by the API")`,
  and `issueCmd.AddCommand(issueAddCmd, issueListCmd, issueRunsCmd)`.

**Tests** (`package cmd`):
- `TestIssueRunsCmd`: `issueRunsCmd` is a sub-command of `issueCmd`.
  `Args` rejects zero and two arguments and accepts one. The `--raw` flag
  exists, defaults to `false`, and has help text.

- [ ] Write the failing test.
- [ ] Run `go test ./cmd/` and confirm the failure.
- [ ] Add the command.
- [ ] Run `go test -race ./cmd/` until it passes.

## Task 4 — README

**Files:**
- Modify: `cli/README.md`, a new section `## Find the runs linked to an issue`
  before the `---` that precedes `## Storage locations`.

The section shows `argus issue runs SCT-1234`, `--text`, and `--raw`. It
names the columns and says that a key without runs prints an empty list and
exits 0.

- [ ] Write the section.

## Task 5 — Verify

- [ ] `cd cli && make fmt && make lint && go test -race ./...`
- [ ] `uv run pre-commit run --all-files`
- [ ] Build the binary into the scratchpad and check that `argus issue --help` lists
      `runs`.
- [ ] Against Argus: a key with linked runs as JSON, with `--text`, and with
      `--raw`. An unknown key such as `SCT-999999` prints `[]` and exits 0.
      `not-a-key` prints the API error and exits 1.
- [ ] Commit, with the boxes of this plan checked, after Komachi's review.
