# replay-dir-file-names — `argus run replay --dir` finds no replay log of an SCT run

## Problem

`argus run replay --dir <directory>` reports that the directory holds no
replay log, although the directory holds the replay log of an SCT run.
`--run-id` does not filter these logs either. A user must give each file
with `--file` to replay a run.

## Who it affects

Every user who replays an SCT run with `--dir`: a local or minicloud run that
goes to `local-runs`, and a Jenkins run after an Argus outage. The SCT run
directory under `~/sct-results/<timestamp>/` is the usual input. The examples
in `cli/README.md`, section `Replaying a run`, use `--dir`.

## Evidence

The replay log of the QATOOLS-123 minicloud run:

```
~/sct-results/qatools-123-minicloud-ab-20261006/argus/candidate/argus_replay_log_cc54896b-d95b-4f60-b6d8-42c65b13ca48_1791278702821085000_70948_98b1e2bebc1e4d379c9ed1553f050c47.jsonl
```

`--dir` on that directory:

```
$ argus run replay --dir ~/sct-results/qatools-123-minicloud-ab-20261006/argus/candidate --dry-run
Error: no argus_replay_log_*.jsonl[.zst] files in "/Users/dmalusev/sct-results/qatools-123-minicloud-ab-20261006/argus/candidate"
```

`--file` on the same file:

```
$ argus run replay --file .../argus_replay_log_cc54896b-d95b-4f60-b6d8-42c65b13ca48_1791278702821085000_70948_98b1e2bebc1e4d379c9ed1553f050c47.jsonl --dry-run
Replay summary: total=72 processed=72 succeeded=72 failed=0 skipped=0 backfilled_logs=0
Run cc54896b-d95b-4f60-b6d8-42c65b13ca48 would replay as (local-runs/CodeLieutenant/longevity-100gb-4h#1)
```

## What good looks like

`argus run replay --dir <SCT run directory>` finds the replay log that the
Python client wrote there. `--run-id <run ID>` keeps the logs of that run
and drops the others.

## Out of scope

- The start time of a replayed run. A replayed run starts at the time of the
  replay. That is a separate task.
- The names that the Python client writes.
- `.tar.zst` archives, which the CLI already reads by prefix and suffix.
