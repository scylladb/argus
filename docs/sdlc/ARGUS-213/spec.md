# Spec: bounded concurrent fan-out for view widgets

| | |
| --- | --- |
| **Intent** | [`intent.md`](intent.md) |
| **Jira** | [ARGUS-213](https://scylladb.atlassian.net/browse/ARGUS-213) |
| **PR** | [scylladb/argus#1073](https://github.com/scylladb/argus/pull/1073) |
| **Stage** | 2 — Design |
| **Status** | Implemented (retro-fitted; see the note in `intent.md`) |
| **Date** | 2026-09-07 |

## Scope

One shared helper plus its application to the four widget controllers that fan out per
test. No schema change, no new endpoint, no payload change.

## Functional requirements

| # | Requirement | Verified by |
| --- | --- | --- |
| F1 | Per-test queries in the four widget endpoints are issued concurrently. | `test_actually_runs_concurrently` (barrier-based) |
| F2 | Results are returned in **input order**, so concatenated payloads are unchanged. | `test_preserves_input_order` |
| F3 | An exception in any task propagates to the caller, as it would from a sequential loop. | `test_exception_propagates` |
| F4 | Response payloads are byte-identical to the sequential implementation, including edge cases. | Manual equivalence check — see Verification |
| F5 | Total concurrent database requests are capped per process, not per request. | Design: single module-level executor |
| F6 | Empty and single-item inputs work without touching the executor. | `test_empty_and_single_item` |
| F7 | Any iterable is accepted, not only sequences. | `test_accepts_any_iterable_not_just_sequences` |
| F8 | More items than workers all complete. | `test_more_items_than_workers_all_complete` |

## Design

### Interface

`argus/backend/util/concurrency.py`

```python
MAX_FANOUT_WORKERS = 16

def map_concurrently(fn: Callable[[T], R], items: Iterable[T]) -> list[R]:
    """Apply fn to every item concurrently, returning results in input order."""
```

Deliberately the same shape as `map`, so a call site converts from
`for x in xs: f(x)` to `for r in map_concurrently(f, xs)` with no other change. Three of
the four controllers are exactly that one-line substitution.

### Decisions and their reasons

**One module-level `ThreadPoolExecutor`, not one per request.** This is the load-bearing
choice. A per-request pool bounds each request but not the process: N simultaneous
dashboard loads would open N × 16 concurrent database requests, so a latency fix would
become a way to overwhelm the cluster under exactly the load it is meant to help. A single
shared pool caps total fan-out no matter how many requests are in flight, and avoids
re-creating threads per request. The cost is that requests queue when the pool is
saturated — accepted, because queueing is strictly better than unbounded fan-out, and
throughput still beats sequential.

**Threads, not asyncio.** The cassandra driver's `Session` is synchronous and thread-safe;
the widget endpoints are sync `def`, so FastAPI already runs them in Starlette's
threadpool, where blocking on a future is safe. Converting the endpoints to `async def`
would have meant an async driver path that does not exist here.

**Order preserved.** `Executor.map` yields in input order regardless of completion order.
Callers concatenate, so this is a correctness requirement, not a nicety (F2).

**Exceptions propagate; no partial results.** A widget rendering a chart with silently
missing series is worse than a visible error, because the reader cannot tell the data is
incomplete. `Executor.map` re-raises on iteration, which matches sequential semantics
exactly.

**Short-circuit for ≤1 item.** Skips the executor round-trip when there is nothing to
overlap.

### Per-controller application

| Controller | Change | Risk |
| --- | --- | --- |
| `nemesis_stats.py` | Direct substitution — `map_concurrently(service.get_nemesis_data, view.tests)`. | Minimal |
| `graphed_stats.py` | Direct substitution with a lambda closing over `filters`. | Minimal |
| `graphs.py` | Per-test body extracted into a local `collect()` returning `(view_data, test_name)`. `test_name` is resolved inside the task and the `tests_details` guard is reapplied outside. `start_dt`/`end_dt` hoisted out of the loop (they were recomputed per graph view). | Reshape — needs F4 check |
| `summary.py` | Fans out per **run**, so `(test_id, method, run_id)` triples are flattened into one task list and zipped back. Key-metric list lifted to `SUMMARY_KEY_METRICS`. | Real restructure — needs F4 check |

## Non-functional requirements

| # | Requirement | Status |
| --- | --- | --- |
| N1 | Widget latency on the measured shape improves materially. | 0.949s → 0.252s (3.8×) on 3 nodes, 50 tests, 12,500 rows |
| N2 | Concurrent database requests per process bounded by a constant. | 16 |
| N3 | No schema change, no migration, no data backfill. | Satisfied |
| N4 | No new dependency. | `concurrent.futures` is stdlib |
| N5 | Improvement does not degrade as the cluster grows. | 1 node 0.380s → 3 nodes 0.252s |

## Flagged for policy owners

Items this change surfaced that are **not** for the author to settle alone:

1. **Ruff does not lint backend code.** `pyproject.toml` sets `exclude = ["argus/"]`
   (line 110) with `force-exclude = true`, so the pre-commit ruff hooks are no-ops for
   everything under `argus/`. A green "ruff passed" line on a backend commit carries no
   information. Someone owns the decision to either narrow that exclusion or stop implying
   backend code is linted. Out of scope here, but it should not stay silent.
2. **Worker count is a capacity decision, not a code decision.** 16 was reasoned, not
   swept. Whoever owns cluster capacity should confirm it against production node count and
   expected concurrent dashboard users.
3. **No per-request deadline.** Inherited from the sequential code rather than introduced,
   but a bounded shared pool makes one slow tenant likelier to affect others. If widget
   endpoints need an SLO, that is a separate change.
4. **Nested `map_concurrently` can deadlock.** Documented in the module docstring and
   unenforced. If the helper spreads, this deserves a guard (e.g. a thread-local depth
   check) rather than a comment.

## Verification

**Unit — `argus/backend/tests/test_concurrency.py`, 6 tests, no database required.**
All passing. `test_actually_runs_concurrently` uses a `threading.Barrier(4)` that only
releases if four tasks are genuinely in flight, so it fails if execution silently regresses
to sequential — every other test in the file would still pass in that case.

**Payload equivalence (F4).** Both reshapes were checked against the previous construction
rather than assumed. This caught a real bug: the first version of `summary.py` used
`setdefault`, which dropped the key entirely for a test with **no methods**, where the old
nested loops emitted an empty dict. The response dict is now seeded from the request
(`{test_id: {} for test_id in versioned_runs}`), so that case matches exactly.
`graphs.py`'s `tests_details` guard was verified equivalent for both empty and non-empty
`graph_views`.

**Not run: the DB-backed widget tests.** `argus/backend/tests/view_widgets/` needs a live
Scylla cluster, and the containers were stopped mid-task at the owner's request. The
controller changes are mechanical rewiring plus the two reshapes above, but CI should be
the gate rather than the author's word. Flagged rather than glossed.

## Out of scope

- The denormalized `(column, time_bucket)` table — [ARGUS-215](https://scylladb.atlassian.net/browse/ARGUS-215).
- Dropping the unused `generic_result_data_v1_column_idx` / `..._row_idx` secondary
  indexes, which cost write amplification on every insert and are queried by no code. A
  separate small win noted in the spike; needs confirmation that nothing external uses them.
- Applying the helper anywhere beyond the four measured controllers.
- Any change to what "global" scope means for widgets.
