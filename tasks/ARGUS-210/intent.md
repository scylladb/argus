# ARGUS-210 — No Argus page shows the test runs linked to a Jira issue

## Problem

Argus links a test run to a Jira issue, and since ARGUS-209 the API can list
the runs linked to one issue key. No page in Argus shows that list. The web UI
shows the link from the run side only: a run's issue tab lists its issues.

Somebody who holds an issue key, from a ticket or a chat message, has no page
to open. They open runs one by one, call the API by hand, or query the
database.

The nearest view is the aggregated issue card on a test's issue tab. It lists
the runs of one issue among the runs of that test only, and it needs a run
page open first to reach it.

## Who it affects

- Engineers who judge how far a known issue reaches: how many runs, which
  tests, which versions.
- Triage and release owners who receive an issue key in a ticket or a chat
  message and want the runs behind it.
- The Jira write-back work under epic ARGUS-219 ("Show Jira reproducers in
  Argus"), which needs a stable Argus URL per issue to point back to.

## Evidence

Jira ARGUS-210, "No Argus page shows the test runs linked to a Jira issue",
status In Progress, epic ARGUS-219:

> When a Jira issue tracks a test failure, there is no page in Argus that
> shows which test runs are linked to it.
> Argus shows the link from the run side only. Somebody holding an issue key,
> from a ticket or a chat message, has no page to open.
> The answer today comes from opening runs one by one, or from a direct
> database query.

> This work depends on ARGUS-209, which defines the lookup API and its
> response shape.
> This hurts anyone judging how far a known issue reaches — how many runs,
> which tests, which versions.

The data source exists. `argus/backend/controller/testrun_api.py:283-295`
serves the lookup that ARGUS-209 added:

```python
@router.get("/issues/{key}/links", name="api.testrun_api.issue_links")
async def issue_links(asgi_request: Request, key: str, user: User = Depends(api_current_user)):
    result = await IssueService().get_issue_links(key=key)
```

No page route renders it. `argus/backend/controller/main.py` declares no route
under `/issues`, and no entry point in `vite.config.ts` loads an issue page.

The aggregated card reaches the runs of an issue only from a test's issue tab.
`frontend/TestRun/IssueTab.svelte:69` scopes it to one test:

```svelte
<Issues ... id={testInfo.test.id} testId={testInfo.test.id} filter_key="test_id" aggregateByIssue={true} submitDisabled={true}/>
```

## What good looks like

From the acceptance criteria of ARGUS-210:

- A URL that names the issue key opens a page that lists every test run linked
  to that Jira issue.
- Each listed run shows enough to judge it — test name, run status, start
  time, and version — and links to the run page.
- The page shows the issue itself with its summary and state, and links to
  Jira.
- A key that is unknown or has no links shows an empty state, not an error
  page.
- The page works in a browser against a real Jira issue that has linked runs.

## Out of scope

- Changes to the lookup API or its response shape (ARGUS-209).
- The CLI command for the same lookup (ARGUS-211).
- Writing back to Jira: the link to Argus, the versions, the last reproduction
  date (ARGUS-220), and the Seen Again Counter (ARGUS-212).
- Links to the new page from other Argus pages, such as the issue cards.
- Adding, removing or editing issue links from the new page.
- A page for a GitHub issue. GitHub issues are retired.
