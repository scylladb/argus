# Spec: plugin-agnostic run cost API and data model

| | |
| --- | --- |
| **Intent** | [`intent.md`](intent.md) |
| **Jira** | [ARGUS-205](https://scylladb.atlassian.net/browse/ARGUS-205) |
| **PR** | [scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071) |
| **Stage** | 2 — Design |
| **Status** | **Proposed** — not implemented; supersedes what #1071 currently contains |
| **Date** | 2026-09-08 |

## Scope

A cost model and API that is keyed by run, owned by no plugin, and stores both an estimate
and an actual figure with a category breakdown. Plus a Costs tab on the run page that reads
it. Per-instance cost is specified as an optional extension and is explicitly not required
for the core to ship.

## Data model

New module `argus/backend/models/cost.py`. Nothing is added to any plugin's run model or
UDT.

### `RunCost` — one row per run, the thing everything reads

```python
class RunCost(Document):
    run_id:          Annotated[UUID, PrimaryKey()]
    plugin_name:     str                       # scylla-cluster-tests | driver-matrix | ...
    release_id:      Optional[UUID] = None     # denormalized so rollups need no join
    group_id:        Optional[UUID] = None
    test_id:         Optional[UUID] = None
    currency:        str = "USD"
    estimated_cost:  Annotated[Optional[float], Double()] = None
    actual_cost:     Annotated[Optional[float], Double()] = None
    is_complete:     bool = False              # False while any component is unpriced
    last_reported_at: datetime

    class Settings:
        name = "run_cost"
```

`actual_cost` is a **stored column**, which is the point. Requirement 3 in the intent —
filtering and ranking by real spend — is impossible against a number that only exists as a
read-time sum. Keeping it here rather than on `sct_test_run` also satisfies requirement 4:
no plugin run table gains an index, and runs that never report cost pay nothing.

### `RunCostByCategory` — the breakdown the Costs tab renders

```python
class RunCostByCategory(Document):
    run_id:     Annotated[UUID, PrimaryKey()]
    category:   Annotated[str, ClusteringKey()]   # db_node|loader|monitor|runner|oracle|network|storage|other
    cost:       Annotated[Optional[float], Double()] = None
    unit_count: Optional[int] = None              # nodes, or GB for network
    detail:     Optional[str] = None              # "6 x i4i.4xlarge (spot)"
```

One partition per run, a handful of rows, read whole. This is the answer to "how much did
the DB nodes cost versus the loaders" without any per-instance storage.

### `RunCostItem` — **optional extension, not core**

```python
class RunCostItem(Document):
    run_id:         Annotated[UUID, PrimaryKey()]
    resource_name:  Annotated[str, ClusteringKey()]
    category:       str
    cost:           Annotated[Optional[float], Double()] = None
    price_per_hour: Annotated[Optional[float], Double()] = None
    is_spot:        Optional[bool] = None
```

Ships only if open question 6 resolves yes. The core must not read it, and the Costs tab
must render correctly when the table is empty.

## API

### Write — plugin-agnostic, one idempotent upsert

```
POST /api/v1/client/cost/{run_id}/report
```

```jsonc
{
  "plugin_name": "scylla-cluster-tests",
  "currency": "USD",
  "estimated_cost": 118.40,
  "actual_cost": 96.12,        // omit or null while unknown
  "complete": false,           // producer says whether anything is unpriced
  "categories": [
    {"category": "db_node", "cost": 61.20, "unit_count": 6, "detail": "6 x i4i.4xlarge"},
    {"category": "loader",  "cost": 18.40, "unit_count": 4},
    {"category": "monitor", "cost": 4.10,  "unit_count": 1},
    {"category": "runner",  "cost": 12.42, "unit_count": 1},
    {"category": "network", "cost": null}          // slot exists, not yet computed
  ]
}
```

**One call carries the whole picture.** Argus never assembles a run's cost from a stream of
per-resource events, which is what makes it plugin-agnostic and removes the ordering and
partial-state problems that a stream creates.

**Idempotent and repeatable.** The producer calls it whenever it has a better number: once
at run start with the estimate, periodically in flight, and once at teardown. Each call
replaces the run's cost rows. This is how live cost works (open question 3) — the producer
re-reports, and Argus shows the latest with `last_reported_at`. Argus does no
extrapolation, so the clock-skew class of bug cannot occur.

**Categories replace wholesale, per call.** A partial category list would need merge rules
nobody wants to reason about.

### Read

```
GET /api/v1/run/{plugin_name}/{run_id}/cost
```

```jsonc
{
  "status": "ok",
  "response": {
    "currency": "USD", "estimated_cost": 118.40, "actual_cost": 96.12,
    "is_complete": false, "last_reported_at": "2026-09-08T09:12:00Z",
    "categories": [ /* as above, ordered by cost desc */ ]
  }
}
```

Separate from the run payload so the run page does not get heavier for viewers who never
open the tab, and so a plugin with no cost data costs one cheap miss.

### Client

```python
client.report_cost(estimated_cost=..., actual_cost=..., complete=..., categories=[...])
```

On the shared client base, not `ArgusSCTClient`, since dtest and driver-matrix get it for
free that way.

## Requirements

| # | Requirement | Note |
| --- | --- | --- |
| F1 | Cost is stored keyed by `run_id` with a plugin name, in tables no plugin owns. | Intent constraint 2 |
| F2 | Both `estimated_cost` and `actual_cost` are stored columns. | Intent constraint 3 |
| F3 | A category breakdown is stored and returned, ordered by cost. | soyacz's "db nodes vs loaders vs monitor vs networking" |
| F4 | Re-reporting replaces the run's cost atomically; the endpoint is idempotent. | Live cost |
| F5 | An unpriced component is `null`; a non-positive or non-finite report is coerced to `null`, never stored. | `sanitize_cost`, carried over from #1071 |
| F6 | A total with any unpriced component renders as partial. | Intent constraint 5 |
| F7 | A producer that reports nothing behaves exactly as today. | Intent constraint 7 |
| F8 | The core reads nothing from `RunCostItem`. | Keeps per-instance optional |

| # | Non-functional | |
| --- | --- | --- |
| N1 | No index added to any plugin run table. | Intent constraint 4 |
| N2 | Run-page load does not get slower for users who never open the Costs tab. | Separate endpoint |
| N3 | One partition read per run for the whole breakdown. | |
| N4 | No migration of existing runs; no backfill is possible. | Costs of past runs are unknown |

## Frontend

A **Costs tab** beside Resources, per k0machi. Not columns in the Resources table, which is
already too wide (intent constraint 6).

Contents: the run total with its estimate beside it and a partial marker when applicable; a
category table with a bar per row so the dominant line is obvious at a glance; and
`last_reported_at`, because a live figure that might be stale must say when it was taken.
If `RunCostItem` ships, a collapsed per-resource section goes at the bottom.

## Flagged for policy owners

1. **Category enum vs free-form** (open question 1) — a product decision about whether
   cross-run dashboards must compare like with like.
2. **Whether per-instance is wanted at all** (open question 6) — if not, `RunCostItem`
   should never be built.
3. **Currency handling** (open question 5) — cheap now, a migration later.
4. **Retention.** Cost rows outlive nothing in particular and are never cleaned up. Whoever
   owns storage growth should say whether they should follow run retention.

## Verification

- Unit: `sanitize_cost` boundary behaviour — zero, negative, NaN, the infinities, booleans.
- API: report → read round-trip; re-report replaces rather than merges; a report with no
  actual cost; a producer that never reports; a category list with a null cost.
- Cross-plugin: the same endpoint exercised against a non-SCT run, which is the requirement
  the current implementation cannot meet at all.
- Frontend: the Costs tab with complete, partial, and absent data; unit tests on the
  formatting and partial logic.

## Out of scope

- Cross-run aggregation and the Cost Explorer — [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218),
  which should read `RunCost` rather than inventing its own.
- Budgets, threshold alerts and approval gates — [SCT-851](https://scylladb.atlassian.net/browse/SCT-851) phases 3-4.
- Any pricing computation in Argus, permanently.
- Networking and storage *computation* — the model has the slots; producing the numbers is
  SCT's side and not yet built.

## Appendix — what #1071 currently implements, and why this differs

| Current in #1071 | This spec | Why |
| --- | --- | --- |
| `cost`/`price_per_hour`/`is_spot` on the SCT `CloudInstanceDetails` UDT | `RunCost` + `RunCostByCategory`, plugin-agnostic | Cost is not an SCT concept |
| `estimated_cost` on `SCTTestRun`; actual summed at read time | Both stored columns on `RunCost` | Cannot filter or rank on a read-time sum |
| Cost column added to the Resources table | Separate Costs tab | The table is already too wide |
| Per-instance is the storage unit | Per-run is the unit; per-instance optional | Forces a per-resource schema on every plugin |
| Argus extrapolates live cost from `elapsed × rate` | Producer re-reports; Argus shows the latest | Argus's timestamps are when it was told, not when the instance ran — this already caused a false-zero bug |
| `sanitize_cost`, no-false-zero rules | **Kept unchanged** | Structure-independent, and the review round proved them necessary |
