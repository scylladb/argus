# ARGUS-96 — Timeout metrics and test durations cannot be compared across tests and releases

## Problem

An engineer cannot answer a question about a timeout metric or a test
duration across many tests, or across releases. Before Argus, SCT sent this
data to Elasticsearch, and a global query was possible. Argus shows the
history of these values on a graph for one job only.

SCT submits the adaptive-timeout datasets as generic result columns with
`visible=False`. Argus filters these columns out by default.
`include_hidden` on the results fetch path (ARGUS-175) and
`argus run results --show-hidden` make them readable for one run.

ARGUS-176 added a read of generic results across the tests of one release,
through the CLI and the API. Gaps remain:

- No read compares one metric between two releases, such as `master` and
  `branch-2026.1`, over a time window.
- The web UI has no view of a metric across tests or releases.
- Argus computes the duration of a run per test, in the graphed stats widget.
  No read filters or compares test durations across tests.
- Argus returns raw cells. No read gives a summary of the values, so the
  engineer must compute it by hand.

Every read of `generic_result_data_v1` starts with `WHERE test_id = ?`. A
global read is a fan-out over tests, and its cost grows with the number of
tests and the retained history.

## Who it affects

- QA engineers and SCT developers who investigate a bug in an operation that
  SCT measures, such as decommission or health.
- Test owners who set a default timeout, as in DTEST-82, and need the observed
  durations to choose a lower value.
- AI agents (Zeus, Maia) that read Argus through the `argus` CLI.
- ScyllaDB, which holds the Argus data and serves every global read.

## Evidence

ARGUS-213, the open sub-task of this issue:

```
We can't do global lookup on timeout metrics, as we could with Elasticsearch. We moved to Argus and don't use Elastic anymore.
There are multiple occasions we need this kind of global lookup — across all tests, or across a whole release. Today we can see history of those on a graph only for one specific job.
```

```
Being able to answer questions like:
How long decommission takes across all 2025.1 longevity jobs.
Compare how long health took in master vs. branch-2026.1 in the last 6 months.
Usable from the Argus UI, and from argus cli.
```

```
No constraints — keep the existing data model.
Since those would be used in UI at some point, they need to be quick enough for human interactions.
We probably target AI agents via argus cli, but still we want to optimize for quick and not hogging the ScyllaDB.
```

DTEST-82:

```
Timeout of 7200secs is unreasonably high
To the best of my knowledge, we don't have any tests that are running nearly that long.
However, when we fail, this is ridiculously long to wait for.
```

`argus/backend/tests/results_service/test_hidden_columns.py`:

```
Columns submitted with ``visible=False`` (SCT does this for the adaptive-timeout
datasets) are filtered out server-side by default.
```

The query-strategy spike on ARGUS-213 (Israel Fruchter, 2026-09-07), on a
3-node cluster with RF=3 and 125k cells:

```
A index            | 0.151s | 0.347s | 2.3× worse
B fan-out serial   | 0.793s | 0.949s | 1.2× worse
B' fan-out concurrent | 0.380s | 0.252s | 1.5× better
C denorm           | 0.094s | 0.103s | flat
```

```
Note: the "keep the existing data model" constraint above excludes the denormalized-table option that spike recommended.
```

`tasks/ARGUS-176/intent.md`, section `Out of scope`:

```
- A cross-test results view in the web UI.
```

Lukasz Sojka on ARGUS-96 (2026-11-10):

```
@Dusan Malusev you already work on it - see if we cover all and link yours PR’s
```

## What good looks like

- From the CLI and the web UI, an engineer gets the values of one timeout
  metric across the tests of a release, in a time window. Example: how long
  decommission takes across all 2025.1 longevity jobs.
- The engineer compares the same metric between two releases in a time
  window. Example: health on `master` against `branch-2026.1` for the last
  six months.
- The engineer filters test durations by release, test and time window. The
  engineer sees the observed durations next to the configured timeout.
- Each read includes the hidden adaptive-timeout columns.
- Each read is fast enough for a person who waits on a page. It does not use
  a secondary index on `generic_result_data_v1`, and it does not add a
  denormalized table.

## Out of scope

- Integration with `test.py` in the ScyllaDB core tests. That work stopped,
  and the comment on ARGUS-96 removes it from scope.
- A change to the default timeout in dtest or SCT. DTEST-82 holds that.
- A schema change, a new table, or a backfill.
- A change to how SCT or the client submits results.
- Removal of the unused `generic_result_data_v1_column_idx` and
  `generic_result_data_v1_row_idx` indexes.
