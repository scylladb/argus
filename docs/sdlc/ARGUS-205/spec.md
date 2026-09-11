# Spec: run cost API and data model

| | |
| --- | --- |
| **Intent** | [`intent.md`](intent.md) |
| **Jira** | [ARGUS-205](https://scylladb.atlassian.net/browse/ARGUS-205) |
| **PR** | [scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071) |
| **Stage** | 2 — Design |
| **Status** | **Proposed** — @soyacz's design, @k0machi's refinements applied; not implemented |
| **Date** | 2026-09-10 |

The shape below is @soyacz's proposal from the [#1071 discussion](https://github.com/scylladb/argus/pull/1071),
which @k0machi endorsed, with his subsequent review comments folded in. Anything still
contested is called out inline and tracked in the intent's open questions.

## API

Three endpoints, each doing one thing.

```
POST /api/v1/client/cost/{run_id}/estimated     { "value": 118.40 }
POST /api/v1/client/cost/{run_id}/actual        { "value": 96.12, "partial": false }
POST /api/v1/client/cost/{run_id}/add           { "name": "...", "category": "...", "value": 4.60 }
```

1. **`set_estimated_cost(run_id, value)`** — called once up front. The estimate stands
   until the run finishes.
2. **`set_actual_cost(run_id, value, partial)`** — called at the end of the run.
3. **`add_cost(run_id, name, category, value)`** — called as costs become known: on node
   termination during the run, and by the periodic cleanup scripts for leaked resources.

**No plugin name is sent.** The run is already identified by `run_id` and Argus knows which
plugin owns it (@k0machi).

**No merge semantics and no idempotency machinery.** `add_cost` writes a row keyed
`(run_id, name, category)`, so a repeat of the same call is naturally idempotent, and
reporting from several stages is just several calls (@k0machi). This is why the write path
is three small endpoints rather than one payload carrying everything.

> **Open — intent question 4.** `set_actual_cost` takes a value, but @k0machi suggested the
> backend sum the `add_cost` rows so successive calls accumulate correctly. Both cannot be
> the source of truth. The answer decides whether a producer may report a total without
> itemising — which SCT needs, since it will have a total before it has per-item detail.

### Leaked cost

The periodic cleanup scripts — the ones outside the test pipeline — call `add_cost` for
resources they reap. Argus adds those to `leaked_cost` rather than to the run's ordinary
total, so a run that looks expensive can be shown as *cheap run + expensive leak*. That
separation is the point (@roydahan).

### Client

`report_*` methods on the shared client base, so every plugin gets them.

dtest and driver-matrix are **executables, not pluggable modules**, so they additionally
need a CLI command exposing the call (@k0machi). Ownership is intent question 7.

## Data model

New module, new tables. Nothing added to any plugin's run model or UDT.

### `run_cost` — per run

```python
class RunCost(Document):
    run_id:   Annotated[UUID, PrimaryKey()]
    name:     Annotated[str, ClusteringKey(clustering_key_index=0)]
    category: Annotated[str, ClusteringKey(clustering_key_index=1)]
    value:    Annotated[float, Double()]

    # static — one set of values per run partition
    estimated_cost: Annotated[Optional[float], Double(), Static()] = None
    actual_cost:    Annotated[Optional[float], Double(), Static()] = None
    leaked_cost:    Annotated[Optional[float], Double(), Static()] = None
    team_name:      Annotated[Optional[str], Static()] = None
    backend:        Annotated[Optional[str], Static()] = None
    test_status:    Annotated[Optional[str], Static()] = None
    lifecycle:      Annotated[Optional[str], Static()] = None
```

One partition per run: the static columns carry the run's totals, the clustered rows carry
the itemised costs `add_cost` reports. One read gets both.

`name` and `category` are clustering keys and therefore **required, not optional**
(@k0machi). An item with no meaningful category should send an explicit one rather than
null.

### `cost_dashboard` — the aggregate query table

```python
class CostDashboard(Document):
    date:    Annotated[date, PrimaryKey()]
    run_id:  Annotated[UUID, ClusteringKey()]

    test_id: Annotated[UUID, Indexed()]     # release, group and build hang off this
    plugin_name:    str
    estimated_cost: Annotated[Optional[float], Double()] = None
    actual_cost:    Annotated[Optional[float], Double()] = None
    leaked_cost:    Annotated[Optional[float], Double()] = None
    team_name:   Optional[str] = None
    backend:     Optional[str] = None
    test_status: Optional[str] = None
    lifecycle:   Optional[str] = None
    cost_categories: dict[str, float]       # {category: value}
```

Partitioned by date because the dashboard's primary axis is a time range.

**`test_id` rather than names** (@k0machi): it already carries release, group and build, so
names are hydrated on read with `SELECT * FROM argus_test_v2 WHERE id IN ?`, chunked and
issued concurrently. 16 bytes per row instead of arbitrary-length names, and it is what
makes per-view aggregation possible at all. Columns used as filters are **indexed**,
otherwise they cannot be filtered on (@k0machi).

`cost_categories` is a denormalized map so a dashboard row needs no second read.

> **Open — intent question 1.** `backend` is a single column, but xcloud and k8s have an
> underlying provider too. If we want to filter by both, that is two columns, and it cannot
> be retrofitted into rows already written.

## Flow

1. The producer calls `set_estimated_cost` at run start, then `add_cost` as items become
   known, then `set_actual_cost` at the end.
2. On run finalization — or when the heartbeat stops — Argus resolves the dashboard fields
   and writes the `cost_dashboard` row.
3. When a periodic cleanup script reaps an instance it calls `add_cost`; the amount lands
   in `leaked_cost` and the dashboard row is updated.
4. The dashboard reads `cost_dashboard` by date range. Further filtering can happen on the
   frontend, so only a date-range change costs a backend call.

## Frontend

**Costs tab** on the run page, beside Resources — estimate and actual, the category
breakdown, and leaked cost shown separately from the run's own spend.

**Dashboard** — the [mockup](https://claude.ai/code/artifact/6f49b965-a496-4d64-80a2-d9ab0073fcca),
built on `cost_dashboard`, filtered as listed in the intent.

**Per-view widget** — aggregates run costs over the tests in a view. Feasible via `test_id`
(@k0machi); whether it ships day one is intent question 2.

## Requirements

| # | |
| --- | --- |
| F1 | Cost lives in its own tables keyed by `run_id`; no plugin run model or UDT changes. |
| F2 | `estimated_cost` and `actual_cost` are stored, queryable columns. |
| F3 | Three write endpoints as above; no plugin name in the payload. |
| F4 | `add_cost` is naturally idempotent on `(run_id, name, category)`. |
| F5 | Argus defines no category vocabulary and rejects no category. |
| F6 | Leaked cost is tracked separately from the run's own spend. |
| F7 | Non-positive, non-finite and boolean amounts are coerced to null, never stored. |
| F8 | Dashboard filter columns are indexed. |
| F9 | A producer that reports nothing behaves exactly as today. |

| # | Non-functional |
| --- | --- |
| N1 | No index added to any plugin run table. |
| N2 | One partition read returns a run's totals and its items. |
| N3 | Dashboard reads are bounded by date range; name hydration is chunked and concurrent. |
| N4 | No migration of existing runs — past costs are unknown and cannot be backfilled. |

## Known limitations

- **No instance-hours stored** — history cannot be re-priced when rates change, and no
  $/hour figure is derivable. Intent question 5.
- **No network breakdown day one** — network counts toward the total but is not itemised.
- **Nothing to backfill** — the dashboard starts empty and fills as runs complete.

## Verification

- Unit: amount sanitisation — zero, negative, NaN, infinities, booleans.
- API: each endpoint independently; `add_cost` repeated with identical data changes
  nothing; leaked costs land in `leaked_cost` and not in the run total.
- Finalization: the `cost_dashboard` row is written on run completion and on heartbeat
  timeout, and updated when a later leak is reported.
- Dashboard: filtering by each column; name hydration over a chunked `test_id IN` query.
- Cross-plugin: the endpoints against a non-SCT run.

## Out of scope

- Budgets, threshold alerts, approval gates — [SCT-851](https://scylladb.atlassian.net/browse/SCT-851) phases 3-4.
- Any pricing computation in Argus, permanently.
- Per-instance cost as a product feature — the rows exist, no view depends on them.
- Network cost breakdown.
