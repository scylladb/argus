# Spec: plugin-agnostic run cost API and data model

| | |
| --- | --- |
| **Intent** | [`intent.md`](intent.md) |
| **Jira** | [ARGUS-205](https://scylladb.atlassian.net/browse/ARGUS-205) |
| **PR** | [scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071) |
| **Stage** | 2 — Design |
| **Status** | **Proposed** — revised against the [#1071 design review](https://github.com/scylladb/argus/pull/1071); not implemented |
| **Date** | 2026-09-08 |

## Scope

A cost model and API keyed by run, owned by no plugin, storing an estimate and an actual
figure. The API accepts optional per-item lines from day one; SCT sends only the total in
phase 1. Plus a Costs tab on the run page.

Live cost during a run is **out** — dropped in review. The estimate shows until the run
finishes, then the actual. That removes the extrapolation machinery entirely.

## Data model

New module `argus/backend/models/cost.py`. Nothing is added to any plugin's run model or
UDT.

### `RunCost` — one row per run

```python
class RunCost(Document):
    run_id:          Annotated[UUID, PrimaryKey()]
    plugin_name:     str                       # scylla-cluster-tests | driver-matrix | ...
    release_id:      Optional[UUID] = None     # denormalized so aggregates need no join
    group_id:        Optional[UUID] = None
    test_id:         Optional[UUID] = None
    estimated_cost:  Annotated[Optional[float], Double()] = None
    actual_cost:     Annotated[Optional[float], Double()] = None
    unpriced_items:  int = 0                   # >0 means actual_cost is a floor
    last_reported_at: datetime

    class Settings:
        name = "run_cost"
```

`actual_cost` is a **stored column**, which is the point — intent constraint 3. Keeping it
off `sct_test_run` satisfies constraint 4: no plugin run table gains an index, and runs
that never report cost pay nothing. `release_id`/`group_id` are denormalized so the
per-release and per-team aggregates can be built without joining back to the plugin's run
table.

Amounts are USD. No currency column, per the review.

### `RunCostItem` — optional detail, accepted from day one

```python
class RunCostItem(Document):
    run_id:    Annotated[UUID, PrimaryKey()]
    name:      Annotated[str, ClusteringKey()]   # "longevity-100gb-12h-db-node-3"
    category:  Optional[str] = None              # free-form: "db_node", "loader", "network"...
    cost:      Annotated[Optional[float], Double()] = None
```

One partition per run, read whole. This is @soyacz's point: send the name *and* the
category, so Argus can sum by category now and drill down to the item later, without a
second reporting format when phase 2 arrives.

**There is no category table and no category enum** (intent constraint 5). Categories are
whatever producers send; the Costs tab groups the items it has. A category Argus has never
seen renders like any other. When a producer sends only a total, there are no items, no
categories, and the tab shows the total alone — which is exactly phase 1.

## API

### Write — plugin-agnostic, one idempotent upsert

```
POST /api/v1/client/cost/{run_id}/report
```

```jsonc
// Phase 1 — SCT sends this and nothing more
{ "plugin_name": "scylla-cluster-tests", "estimated_cost": 118.40, "actual_cost": 96.12 }
```

```jsonc
// Phase 2 — same endpoint, same fields, plus detail
{
  "plugin_name": "scylla-cluster-tests",
  "estimated_cost": 118.40,
  "actual_cost": 96.12,
  "items": [
    {"name": "longevity-100gb-12h-db-node-1", "category": "db_node", "cost": 10.20},
    {"name": "longevity-100gb-12h-loader-node-1", "category": "loader", "cost": 4.60},
    {"name": "sct-runner-1", "category": "runner", "cost": 12.42},
    {"name": "egress", "category": "network", "cost": null}   // reported, not priced
  ]
}
```

**One call carries the whole picture.** Argus never assembles a run's cost from a stream of
per-resource lifecycle events — that is what keeps it plugin-agnostic and removes the
ordering and partial-state problems a stream creates.

**Idempotent.** Each call replaces the run's cost and its items. A producer calls it when
it has the estimate, and again when it has the actual. Repeated calls are safe; there is no
merge semantics to reason about.

`actual_cost` is taken as sent, not recomputed from the items — the producer owns the
arithmetic (intent constraint 1). `unpriced_items` is derived by Argus as the count of
items with a null cost, so the producer needs no flag.

### Read

```
GET /api/v1/run/{plugin_name}/{run_id}/cost
```

```jsonc
{
  "status": "ok",
  "response": {
    "estimated_cost": 118.40, "actual_cost": 96.12,
    "unpriced_items": 1, "last_reported_at": "2026-09-08T09:12:00Z",
    "by_category": [ {"category": "db_node", "cost": 61.20, "item_count": 6} ],
    "items": [ /* … */ ]
  }
}
```

`by_category` is computed on read from the run's own item partition — a handful of rows,
one partition, no stored aggregate to keep consistent. Empty in phase 1.

Separate from the run payload, so the run page does not get heavier for viewers who never
open the tab.

### Client

```python
client.report_cost(estimated_cost=..., actual_cost=..., items=None)
```

On the shared client base, not `ArgusSCTClient`, so dtest and driver-matrix get it free.

## Requirements

| # | Requirement |
| --- | --- |
| F1 | Cost is stored keyed by `run_id` with a plugin name, in tables no plugin owns. |
| F2 | Both `estimated_cost` and `actual_cost` are stored, queryable columns. |
| F3 | The API accepts optional per-item lines carrying name and free-form category. |
| F4 | Argus defines no category vocabulary and rejects no category. |
| F5 | Re-reporting replaces the run's cost and items atomically; the endpoint is idempotent. |
| F6 | A non-positive or non-finite amount is coerced to `null`, never stored — including booleans. |
| F7 | A total with unpriced items is presented as a floor, not a complete figure. |
| F8 | A producer that reports nothing behaves exactly as today. |
| F9 | Phase 1 (total only) and phase 2 (total + items) use the same endpoint and payload shape. |

| # | Non-functional |
| --- | --- |
| N1 | No index added to any plugin run table. |
| N2 | Run-page load unchanged for users who never open the Costs tab. |
| N3 | One partition read per run for the whole breakdown. |
| N4 | No migration of existing runs; no backfill is possible — past costs are unknown. |

## Frontend

A **Costs tab** beside Resources — not columns in the Resources table, which is already too
wide.

Contents: the actual cost with the estimate beside it, or the estimate alone while the run
is unfinished. When items exist, a table grouped by category with a bar per row so the
dominant line is obvious. When they do not, the total alone — phase 1 must not look broken.

Open question 1 in the intent covers how an incomplete total is labelled; the tab needs
that answer before it is built.

## Flagged for policy owners

1. **Labelling an incomplete total** — intent open question 1. Product decision.
2. **Where aggregates read from** — intent open question 2. Affects whether ARGUS-218 owns
   a rollup or queries these tables directly.
3. **Retention.** Cost rows are never cleaned up. Whoever owns storage growth should say
   whether they follow run retention.

## Verification

- Unit: amount sanitisation — zero, negative, NaN, infinities, booleans.
- API: report → read round-trip; re-report replaces rather than merges; total-only (phase 1)
  and total-plus-items (phase 2); items with a null cost counted into `unpriced_items`;
  a category never seen before.
- Cross-plugin: the same endpoint against a non-SCT run — the requirement the current
  implementation cannot meet at all.
- Frontend: the tab with total-only, with items, and with nothing.

## Out of scope

- Cross-run aggregation and the Cost Explorer — [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218).
- Budgets, threshold alerts, approval gates — [SCT-851](https://scylladb.atlassian.net/browse/SCT-851) phases 3-4.
- Live cost during a run — dropped in review.
- Any pricing computation in Argus, permanently.

## Appendix — delta from what #1071 implements today

| Currently in #1071 | This spec | Why |
| --- | --- | --- |
| `cost`/`price_per_hour`/`is_spot` on the SCT `CloudInstanceDetails` UDT | `RunCost` + `RunCostItem`, plugin-agnostic | Cost is not an SCT concept |
| `estimated_cost` on `SCTTestRun`; actual summed at read time | Both stored columns on `RunCost` | Cannot filter or rank a read-time sum |
| Cost column in the Resources table | Separate Costs tab | The table is already too wide |
| Per-instance is the storage unit | Run is the unit; items optional, phase 2 | Phase 1 ships sooner; API still accepts both |
| Argus extrapolates live cost from `elapsed × rate` | **Removed** | Dropped in review; deletes the mechanism and its bug class |
| `sanitize_cost` and the no-false-zero rules | **Kept unchanged** | Model-independent, and the review round proved them necessary |
