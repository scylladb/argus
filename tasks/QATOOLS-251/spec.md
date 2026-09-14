# QATOOLS-251 — attach an issue to an SCT event from the CLI

**Date**: 2026-09-14
**Status**: Implemented

## Problem

`argus issue add` always sends `POST /api/v1/test/$test_id/run/$run_id/issues/submit`.
The server also has `POST /api/v1/test/$test_id/run/$run_id/issues/event/$event_id/submit`,
which calls `IssueService.submit_for_sct_event`. No CLI command sends it.

## Goals

- `argus issue add` accepts an optional `--event-id`.
- With `--event-id`, the command sends the event submit route.
- Without `--event-id`, the command sends the run submit route as before.

## Non-goals

- A new command. The flag extends `argus issue add`.
- Validation that the event belongs to the run. The server owns that check.
- Delete or update of an event link.

## Target state

- `cli/internal/api/routes.go`: `TestRunEventIssueSubmit` holds the event
  submit route.
- `cli/cmd/run_issue.go`: `issueSubmitRoute` picks the route from the event id.
  The `--event-id` flag and the command help name the new behavior.
- `cli/cmd/run_issue_test.go`: a table test covers both routes.

## Risks

| Risk | Response |
|---|---|
| An event id from another run links the issue to the wrong event. | The caller takes the event id from `argus run events` for the same run. |

## Deferred work

None.
