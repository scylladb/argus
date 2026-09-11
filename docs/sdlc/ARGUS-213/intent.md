# Intent: make the view-widget per-test fan-out concurrent

| | |
| --- | --- |
| **Jira** | [ARGUS-213](https://scylladb.atlassian.net/browse/ARGUS-213) (spike), [ARGUS-215](https://scylladb.atlassian.net/browse/ARGUS-215) (dependent) |
| **PR** | [scylladb/argus#1073](https://github.com/scylladb/argus/pull/1073) |
| **Stage** | 1 — Plan |
| **Status** | Accepted (retro-fitted; see note) |
| **Date** | 2026-09-07 |

> **Retro-fit note.** These artifacts were written *after* the implementation, from the
> ARGUS-213 spike measurements and the PR diff. They describe the change accurately, but
> they did not drive it — the ordinary intent → spec → plan → code sequence was not
> followed here, so do not read this pair as evidence that it was. The first change to
> use the flow prospectively should say so explicitly.

## Problem

Generic results and run rows are partitioned by `test_id`:

- `GenericResultData` — partition key `(test_id, name)`, clustering key `(run_id, column, row)`
  (`argus/backend/models/result.py:159`)
- `GenericResultMetadata` — queried as `WHERE test_id = ?`

There is therefore no single query that reaches results across all tests. Every widget
that aggregates across a view works around this with a Python-side loop over the tests in
that view, and **all four of them did it sequentially**, so each endpoint's latency is the
*sum* of its per-test queries rather than roughly the slowest one:

| Controller | Fan-out granularity |
| --- | --- |
| `views_widgets/graphed_stats.py` | one query per test |
| `views_widgets/nemesis_stats.py` | one query per test |
| `views_widgets/graphs.py` | one per test, and `get_test_graphs` is the heaviest per-test read of any widget |
| `views_widgets/summary.py` | one query per **run** — widest of the four |

The ARGUS-213 spike measured this directly on a 3-node cluster (RF=3) with 50 tests
returning 12,500 rows, using `dev-db/bench_result_queries.py`:

| Strategy | Latency |
| --- | --- |
| Sequential per-test fan-out (current code) | 0.949s |
| Concurrent per-test fan-out | **0.252s** |

3.8× on that shape, and the gap **widens with cluster size** — the per-test reads land on
different replicas, so they genuinely parallelise (1 node: 0.380s, 3 nodes: 0.252s).

This is not a hypothesis about slowness. It is a measured 0.7s of wall-clock that every
dashboard load pays for no reason.

## Proposed outcome

Widget endpoints issue their per-test queries concurrently instead of serially, so latency
tracks the slowest query rather than their sum. Users see dashboards load in roughly a
quarter of the time on the measured shape, and the improvement grows as the cluster grows.

Explicitly **not** in this outcome: any change to what the endpoints return, any schema
change, any new widget, or any change to how "global" is scoped. Response payloads must be
byte-identical.

This is the **interim** step the spike recommended. The target state for genuinely
cross-test analysis is a table denormalized by `(column, time_bucket)`; that is
[ARGUS-215](https://scylladb.atlassian.net/browse/ARGUS-215) and needs a migration plus a
dual write. This change is worth doing on its own merits regardless of whether that lands,
because it needs no migration and improves as the cluster scales.

## Affected users and systems

**Users.** Anyone opening a view dashboard in Argus — QA engineers and release leads. No
behaviour change is visible beyond latency; there is nothing to learn or opt into.

**Systems.**

- The four widget controllers above.
- `argus/backend/util/concurrency.py` — new shared helper.
- The Scylla cluster: the same number of queries, issued in a shorter window. Peak
  concurrent read requests per process rises from 1 to the worker cap.
- Starlette's threadpool: widget endpoints are sync `def`, not `async def`, so they already
  run there and may block on a future safely.

**Not affected.** The frontend (no contract change), the SCT client, result submission, and
every non-widget endpoint.

## Constraints

1. **Payloads must be identical.** Callers concatenate per-test results, so ordering is
   part of the contract — a reordered payload would be a silent behaviour change. Two
   endpoints need real restructuring to go concurrent, and both must be checked against the
   previous construction rather than assumed equivalent.
2. **Fan-out must be bounded.** A per-request thread pool would let N concurrent requests
   open N × workers database requests, turning a latency fix into a way to overwhelm the
   cluster. The bound has to cap what the whole process can generate, not what one request
   can.
3. **Failures must stay visible.** A widget that silently dropped the tests whose queries
   failed would render a chart with missing data and no indication of it. Errors must
   surface exactly as they do from a sequential loop.
4. **No schema change and no migration** — that is what makes this cheap and independent of
   ARGUS-215.
5. **Thread safety.** The cassandra driver's `Session` is thread-safe, so service objects
   can be shared across tasks; anything that is not must not be submitted.

## Open questions

- **Worker count.** 16 was chosen to hide per-query latency without letting one request
  flood the cluster; it was not swept experimentally. The right number depends on
  production node count and concurrent dashboard users, neither of which was measured.
- **Behaviour under load.** All measurements are single-request. With many dashboards open
  at once the shared pool saturates and requests queue — total throughput should still beat
  sequential, but the latency distribution under concurrency is unmeasured.
- **No deadline.** There is no per-request timeout; one pathologically slow test still
  holds a worker for as long as its query takes. Sequential code had the same property, so
  this is not a regression, but a bounded pool makes it easier for one slow tenant to
  affect others.
- **Nested use is unsafe.** Submitting work that itself calls the helper can deadlock a
  bounded pool. Documented in the module, not enforced in code.
- **Should this generalise?** Other endpoints may have the same shape. This change
  deliberately touches only the four the spike measured.
