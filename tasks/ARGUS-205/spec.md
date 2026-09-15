# ARGUS-205 — Show the cost of a test run

**Date**: 2026-09-15
**Status**: Draft

## Problem

A run row knows nothing about money. The producer does: SCT computes an
estimate from its instance catalog before it provisions anything, and the
actual figure once the resources are gone. It knows both for the run as a
whole and for each node. Argus has no table to hold the numbers, no endpoint
to receive them, and no place on the run page to show them.

The numbers live outside the plugin run tables, keyed by the run's `build_id`
and `build_number`. That is the pair the run page URL resolves, so the page
does a point read, the SCT model stays lean, and a later producer needs no
migration. A per-job history is a read on the same partition later.

Argus stores what it is told and computes no price. There is no pricing
catalog, no currency conversion and no extrapolation. An unknown figure is
null and never renders as zero.

## Goals

- Store an estimated and an actual USD cost per run.
- Store named cost items per run, each with a category, an optional pricing
  tier, and an estimated or actual USD figure. Categories are free-form.
- Three idempotent client write endpoints: run estimate, run actual, items.
- One read endpoint for the run page that returns the totals and the items.
- Methods on the base `ArgusClient`, so every plugin client inherits them.
- A Costs tab on the run page with an empty state when nothing was reported.
- A producer that reports nothing sees no change.

## Non-goals

- Leaked cost, a `leaked` flag, and the cleanup scripts as a producer.
- A partial or incomplete flag on the actual figure.
- Live cost during a run. The estimate stands until the actual arrives.
- Aggregation, filtering or a dashboard across runs. That is
  [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218).
- Deriving a run total from its items, or a category subtotal. The
  producer owns every figure Argus shows.
- Pricing, rates, instance-hours or currency logic in Argus.
- A Go CLI command for dtest and driver-matrix.
- A per-job cost history endpoint.
- Backfilling runs that finished before this change.
- Any change to a plugin run model, a UDT or a plugin table index.

## Target state

### Data model

New module `argus/backend/models/run_cost.py`, following
`argus/backend/models/run_config.py`. Two tables share the partition key, so
a run's totals and its items are two point reads on the same partition.

```python
class RunCost(Document):
    build_id: Annotated[str, PrimaryKey()]
    build_number: Annotated[int, ClusteringKey(order="DESC")]
    run_id: UUID
    estimated_cost: Annotated[Optional[float], Double()] = None
    estimated_at: Optional[datetime] = None
    actual_cost: Annotated[Optional[float], Double()] = None
    actual_at: Optional[datetime] = None

    class Settings:
        name = "run_cost_v1"


class RunCostItem(Document):
    build_id: Annotated[str, PrimaryKey()]
    build_number: Annotated[int, ClusteringKey(order="DESC", clustering_key_index=0)]
    name: Annotated[str, ClusteringKey(clustering_key_index=1)]
    run_id: UUID
    category: str
    pricing_tier: Optional[str] = None
    estimated_cost: Annotated[Optional[float], Double()] = None
    actual_cost: Annotated[Optional[float], Double()] = None
    updated_at: datetime

    class Settings:
        name = "run_cost_item_v1"
```

One partition per Jenkins job. `run_cost_v1` holds one row per build with the
run totals. `run_cost_item_v1` holds one row per build and item name; the
name is the producer's identifier for the item, such as a node name or
`network`. `category` is a free-form string the producer chooses, such as
`db_node`, `loader`, `monitor`, `runner` or `network`. `pricing_tier` is a
free-form string such as `spot`, `on-demand` or `reserved`.

Both amounts are USD. Timestamps are UTC and stamped by Argus on write.
`run_id` is a copy of the run identifier for the reader, never a lookup key.

The totals are a separate table rather than static columns because the
partition is the job, not the run, so a static column could not hold a
per-build value.

Add `RunCost` and `RunCostItem` to `USED_MODELS` in
`argus/backend/models/web.py`, so `sync-models` creates both tables.

### Service

New module `argus/backend/service/run_cost.py` with `RunCostService` and a
typed `RunCostError`.

- `set_estimated_cost(run_type, run_id, value)` and
  `set_actual_cost(run_type, run_id, value)`. Each resolves the run through
  `TestRunService.get_run` in `argus/backend/service/testrun.py`, reads its
  `build_id` and `build_number`, and writes the one figure with its timestamp
  plus `run_id` to `run_cost_v1`. Setting one figure never clears the other.
  A repeat call overwrites; the last write wins.
- `submit_cost_items(run_type, run_id, items)`. Resolves the run the same
  way, then upserts one `run_cost_item_v1` row per item, keyed by the item
  name. A figure absent from the payload leaves the stored figure untouched,
  so a producer sends the estimate when it creates a node and the actual
  when it terminates it, under the same name. `category` and `pricing_tier`
  are overwritten when present. A repeat call with the same items changes
  nothing but `updated_at`.
- `get_run_cost(build_id, build_number)`. Two point reads. Returns
  `{"total": <row or None>, "items": [<rows>]}`, items sorted by category
  then name.
- A missing run, or a run whose `build_number` is null, raises
  `RunCostError` and writes nothing.

The service performs no arithmetic on the amounts.

### API

Write routes go in `argus/backend/controller/client_api.py`, beside
`run_heartbeat` and `run_set_status`, because they share the
`/testrun/{run_type}/{run_id}/...` shape the base client already builds.

| Method | Path | Route name |
|---|---|---|
| POST | `/api/v1/client/testrun/{run_type}/{run_id}/cost/estimated` | `api.client_api.run_set_estimated_cost` |
| POST | `/api/v1/client/testrun/{run_type}/{run_id}/cost/actual` | `api.client_api.run_set_actual_cost` |
| POST | `/api/v1/client/testrun/{run_type}/{run_id}/cost/items` | `api.client_api.run_submit_cost_items` |

Request bodies:

```json
{"schema_version": "v8", "value": 118.40}
```

```json
{
  "schema_version": "v8",
  "items": [
    {"name": "longevity-db-node-1", "category": "db_node", "pricing_tier": "spot",
     "estimated_cost": 12.30},
    {"name": "longevity-loader-1", "category": "loader", "actual_cost": 4.60}
  ]
}
```

Pydantic request models validate every amount: a finite number greater than
zero, and not a boolean. An item needs a non-empty `name`, a non-empty
`category`, and at least one of `estimated_cost` and `actual_cost`. Item
names are unique within one payload. Anything else raises
`DataValidationError`, so the error contract in
`docs/standards/backend/api.md` applies and nothing is written. The endpoints
reject rather than coerce because they carry nothing but the cost; a rejected
call loses no other record.

The read route goes in a new module `argus/backend/controller/run_cost_api.py`
with `router = APIRouter(prefix="/cost")`, included in
`argus/backend/controller/api.py` beside the other routers.

| Method | Path | Route name |
|---|---|---|
| GET | `/api/v1/cost/run?build_id=<str>&build_number=<int>` | `api.run_cost_api.get_run_cost` |

The response is `{"total": ..., "items": [...]}`, with `total` null and
`items` empty when nothing was reported. Query parameters carry the key
because `build_id` contains slashes.

Every route takes `user: User = Depends(api_current_user)` and returns
`APIResponse({"status": "ok", "response": ...})`. `docs/api_usage.md` lists
the four endpoints.

### Client

`argus/client/base.py`:

- `Routes.SET_ESTIMATED_COST = "/testrun/$type/$id/cost/estimated"`
- `Routes.SET_ACTUAL_COST = "/testrun/$type/$id/cost/actual"`
- `Routes.SUBMIT_COST_ITEMS = "/testrun/$type/$id/cost/items"`
- `set_estimated_cost(run_type: str, run_id: UUID, value: float) -> None`
- `set_actual_cost(run_type: str, run_id: UUID, value: float) -> None`
- `submit_cost_items(run_type: str, run_id: UUID, items: list[CostItem]) -> None`

`CostItem` is a dataclass beside `LogLink` in `argus/client/sct/types.py`,
with `name`, `category`, `pricing_tier=None`, `estimated_cost=None` and
`actual_cost=None`. `submit_cost_items` sends `asdict` of each item and drops
the `None` fields, so an absent figure stays absent on the wire.

Each method posts `{**self.generic_body, ...}` and calls `check_response`,
in the shape of `heartbeat`. `ArgusSCTClient` and `ArgusGenericClient`
inherit all three. SCT calls the run estimate before it provisions, submits
an item with an estimate when it creates a node, submits the same name with
an actual when it terminates the node, and sets the run actual after
teardown.

### Frontend

New component `frontend/TestRun/CostsInfo.svelte` in Svelte 5 runes with typed
props `buildId: string` and `buildNumber: number`. On mount it fetches
`/api/v1/cost/run` with the fetch and `sendMessage` pattern of
`fetchTestRunData` in `frontend/TestRun/TestRun.svelte`. It renders:

- Two rows, Estimated and Actual, each as a USD amount through
  `Intl.NumberFormat` with the report timestamp beside it. "Not reported" for
  a null figure. A null figure never renders as `$0.00`.
- A table of items with the columns Name, Category, Pricing tier, Estimated
  and Actual, grouped by category, shown only when there are items. A null
  cell shows "Not reported".
- One alert, "No cost reported for this run", when `total` is null and
  `items` is empty.

No arithmetic in the component: no delta between the two figures and no
subtotal per category.

`frontend/TestRun/TestRun.svelte` gains a Costs tab: a button after Resources
in the tab bar, the matching `<option value="costs">` in the mobile select,
and a panel gated on `visitedTabs["costs"]` that mounts `CostsInfo` with
`testRun.build_id` and `testRun.build_number`. No new Vite entry point and no
new template.

### Files

| Action | Path |
|---|---|
| Create | `argus/backend/models/run_cost.py` |
| Modify | `argus/backend/models/web.py` (`USED_MODELS`) |
| Create | `argus/backend/service/run_cost.py` |
| Modify | `argus/backend/controller/client_api.py` |
| Create | `argus/backend/controller/run_cost_api.py` |
| Modify | `argus/backend/controller/api.py` |
| Modify | `argus/client/base.py` |
| Modify | `argus/client/sct/types.py` (`CostItem`) |
| Create | `frontend/TestRun/CostsInfo.svelte` |
| Modify | `frontend/TestRun/TestRun.svelte` |
| Modify | `docs/api_usage.md` |
| Create | `argus/backend/tests/client_api/test_run_cost_api.py` |
| Create | `argus/backend/tests/integration/test_run_cost_client.py` |
| Create | `frontend/TestRun/CostsInfo.test.ts` |

## Risks

| Risk | Response |
|---|---|
| The run has no `build_number` because none was parsed from the job URL | The service raises `RunCostError`, the client sees an API error, nothing is written |
| A producer sends `0` to mean unknown | Rejected at the boundary; unknown stays null |
| The key is the build, not the run, so a resubmitted build reuses the rows | Each row carries `run_id`; the last write wins, which matches how the run page resolves a build |
| A producer reuses an item name for two resources | The second write overwrites the first; the producer owns unique names, as it does for resource names today |
| A run with many nodes writes many item rows | One row per node per run, bounded by the cluster size; one partition per job holds all builds, and the read is bounded by one build |
| SCT vendors `argus/client` and cannot call the new methods until a release | Cut a client release after the merge, per `docs/pypi-guide.md` |
| ARGUS-218 needs `test_id`, release or status on the row | Add columns additively later, or resolve them through the run |
| A client on an old Argus gets an unknown route | Producers guard the call as they do for other optional reports; the run itself is unaffected |

## Verification

Backend, `argus/backend/tests/client_api/test_run_cost_api.py`, with the
`api_client` and `fake_test` fixtures and the run submission pattern from
`argus/backend/tests/sct_api/test_sct_api.py`:

- The estimate lands in `run_cost_v1` under the run's `build_id` and
  `build_number`, with `run_id` and `estimated_at` set.
- Setting the actual keeps the estimate; setting the estimate again keeps the
  actual.
- A repeated call with the same value changes nothing but the timestamp.
- Items land in `run_cost_item_v1` keyed by name; a second submission of the
  same name with only `actual_cost` keeps the stored estimate and sets the
  actual.
- An item without a name, without a category, without any figure, or a
  payload with a duplicate name returns the error envelope and writes no row.
- `0`, a negative number, `NaN`, `Infinity`, `true` and a string, as a run
  figure or an item figure, each return the error envelope and write nothing.
- An unknown `run_id` returns the error envelope.
- The GET returns the totals and the items sorted by category then name; the
  GET for a run with no cost returns a null total and an empty list.
- The writes work for a run of the generic plugin.

Integration, `argus/backend/tests/integration/test_run_cost_client.py`, with
the `sct_client` fixture: one end-to-end call of each new client method
against the live server, including a `CostItem` with an absent figure.

Frontend, `frontend/TestRun/CostsInfo.test.ts`, with the fetch stub pattern
from `frontend/Common/ApiUtils.test.ts`: both totals render as USD; the item
table renders grouped by category; a null figure renders as "Not reported"
and never as `$0.00`; an empty response renders the empty state.

Then the verify sequence from `CLAUDE.md`:

```bash
uv run pre-commit run --all-files
uv run pytest
yarn test
```

## Deferred work

- Leaked cost. Add a nullable `leaked` flag to `run_cost_item_v1` and let
  the cleanup scripts submit items with it set, once leak reporting has its
  own definition.
- A partial flag on the actual figure, once an unpriced instance or a
  missing spot price has a defined meaning.
- Category subtotals on the Costs tab, if the team wants Argus to sum items.
- A per-job cost history read on the `run_cost_v1` partition, for a trend on
  the test page.
- The dashboard and its aggregation table, in ARGUS-218. `pricing_tier` and
  `category` are stored now so that it can filter on them.
- A Go CLI `cost` command so dtest and driver-matrix can report without the
  Python client.
- Backend attribution for xcloud and k8s runs. A dashboard concern; the rows
  do not carry a backend.
