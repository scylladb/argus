# ARGUS-209 — The API cannot list the test runs linked to a Jira issue

## Problem

Argus stores a link between a test run and a Jira issue, but it reads that
link in one direction only. Given a release, a group, a test, a run, a view or
an event, the API returns the linked issues. Given an issue, it returns
nothing. No call answers "which test runs are linked to SCT-1234".

A consumer that needs the answer today reads issues entity by entity, then
resolves their runs. Otherwise it queries the database directly. Neither works
for a caller that holds only the issue key, from a ticket, a chat message or a
bot.

## Who it affects

- Automation built on the link data: blast-radius checks, triage bots, and
  reports that group failures by known issue. Zeus is one of them; the
  ARGUS-219 epic notes that it cannot fetch the Jira reproducers.
- The Argus web page for one issue (ARGUS-210). It has no machine-readable
  source to render from.
- The Argus CLI command for the same lookup (ARGUS-211). It has the same gap.
- Engineers who judge how far a known issue reaches and open runs one by one
  to find out.

## Evidence

Jira ARGUS-209, "Argus API cannot list the test runs linked to a Jira issue",
status In Progress, epic ARGUS-219 "Show Jira reproducers in Argus":

> Argus links a test run to a Jira issue, but the link is readable in one
> direction only.
> From a run you can see its issues. From an issue you cannot see its runs.
> There is no API call that answers "which test runs are linked to SCT-1234".
> A consumer that needs the answer today must read runs one by one or query
> the database directly.

> This blocks every automated use of the link data — blast-radius checks,
> triage bots, and reports that group failures by known issue.
> It also blocks the Argus web page and the Argus CLI command for the same
> lookup, which both need a machine-readable source.

The only issue read path, `argus/backend/service/issue_service.py:25-36`,
accepts no issue as a filter:

```python
    async def _get_links(self, filter_key: str, filter_id: UUID | str) -> list[IssueLink]:
        if filter_key not in ["release_id", "group_id", "test_id", "run_id", "user_id", "view_id", "event_id"]:
            raise Exception(
                "filter_key can only be one of: \"release_id\", \"group_id\", \"test_id\", \"run_id\", \"user_id\", \"view_id\", \"event_id\""
            )
```

The storage does not serve the reverse read. `argus/backend/models/github_issue.py:61-63`
keys the link table by run, with the issue as an unindexed clustering column:

```python
class IssueLink(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    issue_id: Annotated[UUID, ClusteringKey()]
```

`argus/backend/models/jira.py:12-19` indexes the permalink, not the key:

```python
class JiraIssue(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    user_id: Annotated[UUID, Indexed()]
    summary: str
    key: str
    state: str
    project: str
    permalink: Annotated[str, Indexed()]
```

## What good looks like

From the acceptance criteria of ARGUS-209:

- One HTTP API call takes a Jira issue key, such as `SCT-1234`, and returns
  the test runs linked to that issue.
- The request names the issue by tracker plus key, so a second tracker can be
  served later without a breaking change to the contract.
- The JSON response gives, for each run, enough to identify and open it: run
  id, test name, run status, start time, and the run link.
- The response also carries the issue itself: key, summary, state, and its
  tracker link.
- A key that is unknown or has no links returns an empty result with a success
  status, not an error.
- The response shape is written down where API consumers find it, with an
  example.
- The lookup works against a real Jira issue that has linked runs.

## Out of scope

- The web page that lists the runs of an issue (ARGUS-210).
- The CLI command for the same lookup (ARGUS-211).
- Writing back to Jira: the link to Argus, the versions, the last reproduction
  date (ARGUS-220), and the Seen Again Counter (ARGUS-212).
- A lookup by GitHub issue. GitHub issues are retired. The contract leaves
  room for a second tracker but serves Jira only.
- A lookup by the internal issue id.
- Changes to the existing issue read paths and their response shapes.
