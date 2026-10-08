# ARGUS-211 — The argus CLI cannot list the test runs linked to a Jira issue

## Problem

The argus CLI links an issue to a run and lists the issues of a run, a test, a
group, a release, a user, a view or an event. It cannot go the other way. No
command takes a Jira issue key and prints the test runs linked to it.

Since ARGUS-209 the API answers that question, but only through a hand-written
HTTP call. Somebody who holds an issue key in a terminal or a script has to
build the request, carry the credentials and parse the JSON themselves.

## Who it affects

- Engineers who triage in a terminal and hold an issue key from a ticket or a
  chat message.
- Scripts and agents that drive Argus through the CLI rather than the HTTP API:
  blast-radius checks, triage helpers, and reports that group failures by known
  issue.

## Evidence

Jira ARGUS-211, "argus CLI cannot list the test runs linked to a Jira issue",
status In Progress, epic ARGUS-219:

> The argus CLI can add and list the issues of a run, but it cannot go the
> other way.
> There is no command that takes a Jira issue key and prints the test runs
> linked to it.
> Anyone who wants that answer in a terminal or a script must call the HTTP API
> by hand.

> This work depends on ARGUS-209, which defines the lookup API and its response
> shape.
> This keeps the lookup out of scripts and out of the terminal, where triage
> work happens.

The `issue` command group holds two commands. `cli/cmd/run_issue.go:173`:

```go
	issueCmd.AddCommand(issueAddCmd, issueListCmd)
```

`issue list` filters by an entity id only. `cli/cmd/run_issue.go:89-91`:

```go
var issueListCmd = &cobra.Command{
	Use:   "list",
	Short: "List issues linked to a test run or other entity",
```

The CLI knows no route for the lookup. `cli/internal/api/routes.go:37-40`:

```go
	// Issue routes
	TestRunIssueSubmit      = "/api/v1/test/%s/run/%s/issues/submit" // POST – submit an issue (test_id, run_id)
	IssuesGet               = "/api/v1/issues/get"                   // GET  – list issues (filterKey, id query params)
	TestRunEventIssueSubmit = "/api/v1/test/%s/run/%s/issues/event/%s/submit"
```

The data source exists. `argus/backend/controller/testrun_api.py:283-285`
serves the lookup that ARGUS-209 added:

```python
@router.get("/issues/{key}/links", name="api.testrun_api.issue_links")
async def issue_links(asgi_request: Request, key: str, user: User = Depends(api_current_user)):
    result = await IssueService().get_issue_links(key=key)
```

## What good looks like

From the acceptance criteria of ARGUS-211:

- One argus command takes a Jira issue key, for example `SCT-1234`, and prints
  the test runs linked to it.
- The command prints a human-readable table and a machine-readable form, like
  the other run commands.
- Each printed run carries enough to identify and open it: run id, test name,
  status, start time, and the run link.
- A key that is unknown or has no links exits with success and an empty list.
- The command appears in the CLI help and in the CLI README.
- The command works against a real Jira issue that has linked runs.

## Out of scope

- Changes to the lookup API or its response shape (ARGUS-209).
- The web page for the same lookup (ARGUS-210).
- Adding or removing issue links from the new command.
- Writing back to Jira: the link to Argus, the versions, the last reproduction
  date (ARGUS-220), and the Seen Again Counter (ARGUS-212).
- A lookup by GitHub issue. GitHub issues are retired.
