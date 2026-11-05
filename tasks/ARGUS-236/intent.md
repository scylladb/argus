# ARGUS-236 — Events tab sort order

## Problem

The SCT Events tab renders its timeline oldest-first and offers no way to
change that. `createTimeline` in `frontend/TestRun/SCT/SctEvents.svelte` sorts
ascending by timestamp at both of its sort sites, and nothing in the UI reaches
that ordering.

On a long run the events a user cares about most are the ones that just
happened, and reaching them costs a scroll to the bottom of a container capped
at 1024px. On a run that is still executing, the 60-second refresh keeps adding
events below the fold, so the newest event moves further away the longer the
tab stays open.

The events nested inside a nemesis block are worse: `innerEvents` is never
sorted at all. It inherits the order of the flattened severity store, so it
reads as all the CRITICALs, then all the ERRORs, and so on, rather than as a
sequence of what happened during that nemesis.

## Who it affects

Anyone triaging an SCT run in the Argus web UI, and most sharply anyone
watching a run that is still in progress.

## Evidence

`frontend/TestRun/SCT/SctEvents.svelte:258`

```
if (timelineMode === "classic") return [...sctEvents].sort((l, r) => l.ts - r.ts);
```

`frontend/TestRun/SCT/SctEvents.svelte:273`

```
let timeline = [...nemesisEvents, ...remainder].sort((l, r) => l.ts - r.ts);
```

`frontend/TestRun/SCT/SctEvents.svelte:266-267`, where the nested events are
filtered out of the flattened store and never sorted:

```
let nemesisEvents = sctEvents.filter((event) => evt.ts <= event.ts && event.ts < (evt.tsEnd || evt.ts));
evt.innerEvents = nemesisEvents;
```

## What good looks like

A user opens the Events tab, presses one button, and the newest event is at the
top of the list. Pressing it again returns the list to the order it has today.
The choice holds across both display modes and inside the nemesis blocks, and a
user who never presses the button sees the timeline order they see today.

## Out of scope

- The Events (Legacy) tab, `frontend/TestRun/EventsTab.svelte`. It is on the
  retirement track behind ARGUS-56 and ARGUS-57.
- Persisting the chosen order as a per-user preference. ARGUS-193 defines the
  `localStorage` pattern for this component and the preference should ride on
  it rather than on a second mechanism.
- Sorting the similar-events modal table by column. That is ARGUS-35.
- The backend read path. `SCTTestRun.get_events_limited` keeps its ascending
  order and its `PER PARTITION LIMIT`.
