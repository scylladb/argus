# QATOOLS-251 — attach an issue to an SCT event from the CLI

## Problem

`argus issue add` links an issue to a run only. It cannot link an issue to one
SCT event of the run. The Argus server already accepts an event link, and
`argus issue list --event-id` already reads it back.

## Who it affects

The Zeus `triaging-agent`. It classifies each error event of an SCT run and
attaches the known issue to that event. The agent runs only the `argus` CLI.

## Evidence

The server route exists in `argus/backend/controller/testrun_api.py`:

```
@router.post("/test/{test_id}/run/{run_id}/issues/event/{event_id}/submit",
             name="api.testrun_api.issues_submit_for_event")
```

`argus issue add --help` shows only `--run-id`, `--issue-url` and `--test-id`.

## What good looks like

`argus issue add --run-id <run> --event-id <event> --issue-url <url>` links the
issue to that event. `argus issue list --event-id <event>` then shows it.

## Out of scope

- Removing an issue from an event.
- Event links for plugins other than SCT.
