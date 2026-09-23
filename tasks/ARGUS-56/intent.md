# ARGUS-56 — SCT events live on the run row and cannot be addressed one by one

## Problem

An SCT run's events are stored on the run row itself, in the `events` column of
`sct_test_run`. The column is a list of `EventsBySeverity`, one entry per
severity, each carrying a list of raw message strings.

Nothing in that shape identifies a single event. An event is a string at a
position in a list, so anything that wants to point at one event has to point
at a list index. The embedding worker names an event by its position:

```python
event_id: str = f"{test_run.id}_{idx}_{event_idx}"
```

An index is not a stable identity. It moves whenever the list changes, and the
list does change, because each severity keeps only the last 100 messages:

```python
    def _collect_event_message(self, event: EventsBySeverity, message: str):
        if len(event.last_events) >= 100:
            event.last_events = event.last_events[1:]

        event.event_amount += 1
        event.last_events.append(message)
```

`event_amount` keeps counting past 100 while `last_events` drops the oldest
message, so the row records how many events a run produced and no longer holds
them. On a long run the events a reader most wants are the ones already gone.

A replacement exists. The `sct_event` table gives each event its own row keyed
by run, severity and timestamp, with its own `event_id`, and the new events
endpoints, the new Events tab and the current embedding worker all read it. Runs that predate
the cutover have their events only in the column, so to the new system those
runs look like they produced nothing at all.

Two more columns on the run row are in the same position. `nemesis_data` and
`allocated_resources` have replacement tables, `sct_nemesis` and `sct_resource`,
which every read and write already uses, but the columns themselves remain on
the row and are still declared on the model.

## Who it affects

Every SCT pipeline that reports to Argus, and every engineer reading a run.

The similar-events feature is the sharp edge: it cannot group or deduplicate
events reliably while an event's identity is its index in a truncated list.
Anyone opening a run from before the `sct_event` cutover sees an empty Events
tab. Anyone reading a run that produced more than 100 events of a severity sees
a count that does not match the messages.

Old SCT clients are affected in a different way. They still post to the legacy
submission endpoint and must keep working through and after the change.

## Evidence

The Jira issue, verbatim:

> Summary: Migrate all events from sct_run table to new events table
>
> Description: So we can use it in similar events feature properly and remove
> old events approach
>
> Migrated from GitHub issue: https://github.com/scylladb/argus/issues/790

The scale of what sits on a single run row, from a backfill run of
`scripts/migration/migration_2026-05-08.py` on 2026-09-22:

```
[WARNING] migration_2026-05-08::migrate_run - Large batch for run_id=78337082-1555-4863-a6c1-aff2fdc68705: 160 events, 1490614 bytes over the 65536 soft cap
[ERROR] migration_2026-05-08::migrate_run - InvalidRequest executing batch
```

160 events, 1.49 MB, on one run row.

## What good looks like

Every run's events are readable from `sct_event`, including runs that predate
the new table, so a reader opening an old run sees the same thing as a reader
opening a new one.

An event has an identity that does not depend on its position, so the
similar-events feature can point at one event and keep pointing at it.

No event is dropped because a per-severity list filled up.

The legacy shape is gone from the run row and from the code that served it, and
`sct_test_run` no longer carries a column whose data lives somewhere else.

Throughout, an SCT client that has not been upgraded keeps submitting without
an error. The old submission endpoint answers as it always did.

## Out of scope

The argusAI v1 embedding worker. It reads the legacy column, it is no longer
the running process, and retiring it is handled separately.

Dropping the user-defined types from the keyspace. The types stop being used;
the CQL `DROP TYPE` is not part of this task.

The shape of the event text itself. Messages move across as they are; parsing
them into fields is not this task's problem.
