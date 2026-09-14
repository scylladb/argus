# ARGUS-205 — Show the overall cost of a test run

**Date**: 2026-09-14
**Status**: Draft

## Problem

A run row knows nothing about money. The producer does: SCT computes an
estimate from its instance catalog before it provisions anything, and the
actual figure once the resources are gone. Argus has no table to hold either
number, no endpoint to receive it, and no place on the run page to show it.

The number has to live outside the plugin run tables. Cost is not an SCT
concept; dtest, driver-matrix and generic runs incur it too, and a second
producer must not need a migration. The store is keyed by the run's
`build_id` and `build_number`, the same pair the run page URL resolves, so the
page does a point read and a later per-job history is a read on the same
partition.

Argus stores what it is told and does no arithmetic. There is no pricing
catalog, no currency conversion and no extrapolation. An unknown figure is
null and never renders as zero.

## Goals

- Store an estimated and an actual USD cost per run, keyed by
  `(build_id, build_number)`.
- Two idempotent client write endpoints, one per figure.
- One read endpoint for the run page.
- Methods on the base `ArgusClient`, so every plugin client inherits them.
- A Costs tab on the run page with an empty state when nothing was reported.
- A producer that reports nothing sees no change.

## Non-goals

- Cost by category, cost per instance, and item rows.
- Leaked cost and the cleanup scripts as a producer.
- A partial or incomplete flag on the actual figure.
- Live cost during a run. The estimate stands until the actual arrives.
- Aggregation, filtering or a dashboard across runs. That is
  [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218).
- Pricing, rates, instance-hours or currency logic in Argus.
- A Go CLI command for dtest and driver-matrix.
- Network or storage cost as separate figures.
- A per-job cost history endpoint.
- Backfilling runs that finished before this change.
- Any change to a plugin run model, a UDT or a plugin table index.

## Target state

### Data model

New module `argus/backend/models/run_cost.py`, following
`argus/backend/models/run_config.py`.

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
```

One partition per Jenkins job, one row per build. Both amounts are USD.
`estimated_at` and `actual_at` are UTC timestamps stamped by Argus when the
figure is written. `run_id` is a copy of the run identifier for the reader,
never a lookup key.

Add `RunCost` to `USED_MODELS` in `argus/backend/models/web.py`, so
`sync-models` creates the table.

### Service

New module `argus/backend/service/run_cost.py` with `RunCostService` and a
typed `RunCostError`.

- `set_estimated_cost(run_type, run_id, value)` and
  `set_actual_cost(run_type, run_id, value)`. Each resolves the run through
  `TestRunService.get_run` in `argus/backend/service/testrun.py`, reads its
  `build_id` and `build_number`, and writes the one figure with its timestamp
  plus `run_id`. Setting one figure never clears the other. A repeat call
  overwrites; the last write wins. A missing run, or a run whose
  `build_number` is null, raises `RunCostError` and writes nothing.
- `get_run_cost(build_id, build_number)`. A point read. Returns the row as a
  dict, or `None` when no cost was reported.

The service performs no arithmetic on the amounts.

### API

Write routes go in `argus/backend/controller/client_api.py`, beside
`run_heartbeat` and `run_set_status`, because they share the
`/testrun/{run_type}/{run_id}/...` shape the base client already builds.

| Method | Path | Route name |
|---|---|---|
| POST | `/api/v1/client/testrun/{run_type}/{run_id}/cost/estimated` | `api.client_api.run_set_estimated_cost` |
| POST | `/api/v1/client/testrun/{run_type}/{run_id}/cost/actual` | `api.client_api.run_set_actual_cost` |

Request body:

```json
{"schema_version": "v8", "value": 118.40}
```

A Pydantic request model validates `value`: a finite number greater than
zero, and not a boolean. Anything else raises `DataValidationError`, so the
error contract in `docs/standards/backend/api.md` applies and nothing is
written. The endpoints reject rather than coerce because they carry nothing
but the cost; a rejected call loses no other record.

The read route goes in a new module `argus/backend/controller/run_cost_api.py`
with `router = APIRouter(prefix="/cost")`, included in
`argus/backend/controller/api.py` beside the other routers.

| Method | Path | Route name |
|---|---|---|
| GET | `/api/v1/cost/run?build_id=<str>&build_number=<int>` | `api.run_cost_api.get_run_cost` |

The response is the row, or `null` when no cost was reported. Query
parameters carry the key because `build_id` contains slashes.

Every route takes `user: User = Depends(api_current_user)` and returns
`APIResponse({"status": "ok", "response": ...})`. `docs/api_usage.md` lists
the three endpoints.

### Client

`argus/client/base.py`:

- `Routes.SET_ESTIMATED_COST = "/testrun/$type/$id/cost/estimated"`
- `Routes.SET_ACTUAL_COST = "/testrun/$type/$id/cost/actual"`
- `set_estimated_cost(run_type: str, run_id: UUID, value: float) -> None`
- `set_actual_cost(run_type: str, run_id: UUID, value: float) -> None`

Each method posts `{**self.generic_body, "value": value}` and calls
`check_response`, in the shape of `heartbeat`. `ArgusSCTClient` and
`ArgusGenericClient` inherit both. SCT calls the estimate before it
provisions and the actual after teardown.

### Frontend

New component `frontend/TestRun/CostsInfo.svelte` in Svelte 5 runes with typed
props `buildId: string` and `buildNumber: number`. On mount it fetches
`/api/v1/cost/run` with the fetch and `sendMessage` pattern of
`fetchTestRunData` in `frontend/TestRun/TestRun.svelte`. It renders:

- Two rows, Estimated and Actual, each as a USD amount through
  `Intl.NumberFormat` with the report timestamp beside it.
- "Not reported" for a null figure. A null figure never renders as `$0.00`.
- One alert, "No cost reported for this run", when the response is `null`.

No arithmetic in the component, so no delta between the two figures.

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
| The key is the build, not the run, so a resubmitted build reuses the row | The row carries `run_id`; the last write wins, which matches how the run page resolves a build |
| SCT vendors `argus/client` and cannot call the new methods until a release | Cut a client release after the merge, per `docs/pypi-guide.md` |
| ARGUS-218 needs `test_id`, release or status on the row | Add columns additively later, or resolve them through the run; the row stays small |
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
- `0`, a negative number, `NaN`, `Infinity`, `true` and a string each return
  the error envelope and write no row.
- An unknown `run_id` returns the error envelope.
- The GET returns the row; the GET for a run with no cost returns `null`.
- The write works for a run of the generic plugin.

Integration, `argus/backend/tests/integration/test_run_cost_client.py`, with
the `sct_client` fixture: one end-to-end call of each new client method
against the live server.

Frontend, `frontend/TestRun/CostsInfo.test.ts`, with the fetch stub pattern
from `frontend/Common/ApiUtils.test.ts`: both figures render as USD; a null
figure renders as "Not reported" and never as `$0.00`; a `null` response
renders the empty state.

Then the verify sequence from `CLAUDE.md`:

```bash
uv run pre-commit run --all-files
uv run pytest
yarn test
```

## Deferred work

- Cost by category and item rows. Add a clustered table under the same
  `(build_id, build_number)` key, or a second table keyed by `run_id`, with
  an `add_cost` endpoint. Categories stay producer-defined.
- Leaked cost. The cleanup scripts become a producer with their own endpoint
  and a `leaked_cost` column.
- A partial flag on the actual figure, if a producer needs to mark a floor.
- A per-job cost history read on the `run_cost_v1` partition, for a trend on
  the test page.
- The dashboard and its aggregation table, in ARGUS-218.
- A Go CLI `cost` command so dtest and driver-matrix can report without the
  Python client.
- Backend attribution for xcloud and k8s runs. A dashboard concern; the
  per-run row does not carry a backend.
