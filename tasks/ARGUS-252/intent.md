# ARGUS-252 — Replay a log into a chosen build path as a new run owned by the caller

## Problem

A local SCT run records its Argus calls in a replay log. `argus run replay`
re-applies that log, and the run keeps the values that the local run
recorded. The build path is `local_run`, the starter is the Linux user, and
the assignee comes from the release schedule. The engineer cannot put the
run in a folder of their choice, and the run does not show their Argus user.

A second replay of the same log changes nothing. SCT `submit_run`
(`from_sct_config` in `argus/backend/plugins/sct/testrun.py`) keeps a run
that already exists, so the run keeps its first build path, starter and
assignee.

The replay output shows only counters. The engineer must search Argus to
find the replayed run.

## Who it affects

Engineers who run SCT on their own machine or on minicloud, and replay the
log into a shared Argus instance such as staging.

## Evidence

The `submit_run` record of a local replay log,
`argus-replay-baseline.tar.zst` for run `91c226dc-a057-4ad4-a0b8-bf8bc73031b9`:

```
"run_id": "91c226dc-a057-4ad4-a0b8-bf8bc73031b9",
"job_name": "local_run",
"job_url": "",
"started_by": "linux_user=dmalusev",
```

The replay output:

```
❯ argus run replay --file ~/sct-results/qatools-123-minicloud-ab-20261006/argus/argus-replay-baseline.tar.zst
Replay summary: total=83 processed=83 succeeded=83 failed=0 skipped=0
```

## What good looks like

- One replay command puts the run under a build path that the engineer
  names, such as `scylla-staging/dusan/my-argus-local-run`. The last path
  segment is the job name.
- Each replay makes a new run, also when the original run exists in Argus.
- The run shows the Argus user of the engineer as its starter and its
  assignee.
- The replay output shows the full Argus link of each replayed run.
- The run keeps its logs from S3.

## Out of scope

- Moving or deleting a run that already exists.
- Replay logs from plugins other than SCT. The change must not break them.
- Assigning the run to a user other than the caller.
