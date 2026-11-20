# ARGUS-193 — Opt-out AI summaries in the SCT events view

## Problem

The event processor stores an LLM summary of each ERROR and CRITICAL SCT event in
`sct_event.summary`, and the events API returns it, but the web UI never shows it. A user who
triages a run reads every event in full, including long tracebacks, backtraces and coredumps,
even when a short summary of that event is already stored.

## Who it affects

Engineers who triage SCT runs on the test run page, in the Events tab.

## Evidence

The model stores the field (`argus/backend/plugins/sct/testrun.py`):

```python
    summary: Optional[str] = None  # LLM-generated summary; null until/unless summarized (see events/)
```

The events read returns every column (`SCTTestRun.get_events_limited`):

```python
        return sorted((event.model_dump() for event in events), key=lambda evt: evt["ts"])
```

The frontend's `SCTEvent` interface in `frontend/TestRun/SCT/SctEvents.svelte` has no
`summary` field, and `SctEvent.svelte` renders only `event.message`.

Jira ARGUS-193:

> Split out of ARGUS-146 (design: event-summarization.md §5.5, plan PR #1016). The
> backend/worker path that generates and stores sct_event.summary is done (PR #1048); this
> issue covers the web UI part explicitly deferred as a follow-up in that PR.

The Jira description asks for a per-browser localStorage default and a toggle on every
summarized event. This task replaces that with a server-side setting per user, on by
default, described below.

## What good looks like

- The profile page has a setting for AI event summaries. It is on by default, and a user can
  turn it off. It is saved per user on the server, so it follows the user across browsers. A
  username change keeps it.
- With the setting on, an event card that has a summary shows the summary in place of the
  event text. The card marks the summary as an AI summary, so nobody takes it for raw output.
  A button on the card shows the original event.
- With the setting off, an event card that has a summary shows the original event, with a
  button that shows the summary.
- An event without a summary looks exactly as it does today.
- The copy button always copies the original event message, never the summary.

## Out of scope

- Generating or storing summaries, and the summarization prompt and model.
- Summaries anywhere outside the SCT Events tab, for example the similar-events view or the
  chat tools.
- Other user preferences beyond this one setting.
