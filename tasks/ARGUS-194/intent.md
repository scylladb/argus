# ARGUS-194 — SCT event summary output in argus CLI (--raw flag)

## Problem

`argus run events` prints the full message of every SCT event, even when
the event has a summary. The `sct_event.summary` column exists, and the
worker fills it (PR #1048). Commit b4ef8476 (ARGUS-254) added `Summary` to
the Go `SCTEvent` struct. The table output now shows a `Message` column
and a `Summary` column side by side. The JSON output carries both fields.

A scripted caller reads the full message for every event. The summary does
not replace it, so the output is longer than before, not shorter. A caller
also has no switch to ask for the original message only.

## Who it affects

Scripted and automated callers of `argus run events`. The main caller is
the Zeus triage agent (`triage.md` in scylladb/qatools), which reads the
events of a failed SCT run and pays for each token of the output.

## Evidence

From ARGUS-194:

> Default output renders the summary where present, falling back to message
> when null — output is never blank. This is the opposite default from the
> web UI: the CLI is the primary interface for scripted/automated callers, so
> it optimizes for token savings first.

> Add a --raw flag that forces the original message instead.

> Acceptance: argus run events prints summaries by default when available,
> argus run events --raw always prints the original message, and events
> without a summary print unchanged either way.

Current table headers, `cli/internal/models/runs.go`:

```go
return []string{"Severity", "Timestamp", "Type", "Node", "Nemesis", "Repeats", "Message", "Summary"}
```

## What good looks like

- `argus run events` prints the summary of an event that has one.
- `argus run events` prints the message of an event with no summary. No
  event prints a blank text.
- `argus run events --raw` prints the original message of every event.
- A duplicate promoted to the canonical event has no summary, and it prints
  its message.
- Unit tests cover three cases: summary present, summary null, and a
  promoted duplicate.
- The Zeus `triage.md` reads the summary output.

## Out of scope

- The generation and storage of `sct_event.summary`. PR #1048 did that.
- The web UI. It keeps the message as its default.
- The 5-minute event cache (`cache.TTLSCTEvents`). A summary written after
  an event was cached shows after the TTL ends.
- The `triage.md` change in scylladb/qatools. That repository gets its own
  change.
