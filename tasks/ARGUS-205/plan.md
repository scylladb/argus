# ARGUS-205 — implementation plan

**Spec:** `tasks/ARGUS-205/spec.md`

## Constraints

- Follow `docs/standards/backend/` for the router, service and model split, and
  `docs/standards/frontend/components.md` for the Svelte 5 runes.
- A service raises `DataValidationError`. It never returns an error dictionary,
  and every API failure stays inside the HTTP 200 envelope.
- Write a static column with the queryset `update()`. `Document.save()` inserts
  every column, so it nulls a static the caller did not set.
- Run the verify sequence from the `Commands` section of `CLAUDE.md` before each
  commit.

## Two readings of the spec, resolved

**The carrier row.** The design section places the statics on a row named `""`,
and the risk table records that `find(run_id=...).update(...)` writes a static
with the partition key alone. This plan takes the second mechanism, so the
service writes no row named `""`. ScyllaDB materializes a static-only partition
as one row whose clustering column is null, and the read drops any row with a
null or an empty name before it lists the items or sums them. The behavior a
client sees is the one the spec states.

**A duplicate item name.** The field shape belongs to the request model. The
rule that names are unique within one payload belongs to the service, which
raises `DataValidationError`.

## Task 1 — The table and the service

**Files:**
- Create: `argus/backend/models/run_cost.py`
- Modify: `argus/backend/models/web.py`, the import block and `USED_MODELS`
- Create: `argus/backend/service/run_cost_service.py`
- Test: `argus/backend/tests/run_cost/test_run_cost_service.py`

**Internals:** `RunCost` as the spec declares it, in the table `run_cost_v1`.
`RunCostService` with `set_estimated_cost`, `submit_cost_items`,
`recompute_actual_cost` and `get_run_cost`. The sum folds `math.fsum` over the
item rows of one partition read. The per-category breakdown folds over the same
read and is not stored.

- [ ] Write the failing tests: the estimate write, an item upsert, a repeated
      name overwriting its row, a sum that includes a leaked item, the fallback
      to the estimate, the no-partition no-op, the empty read, and a duplicate
      name raising `DataValidationError`.
- [ ] Run them and confirm the failure.
- [ ] Write the model, register it, and write the service.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 2 — The routes

**Files:**
- Modify: `argus/backend/controller/client_api.py`, the request models and two
  routes beside `submit_run_config`
- Create: `argus/backend/controller/cost_api.py`
- Modify: `argus/backend/controller/api.py`, the import and the router list
- Modify: `docs/api_usage.md`
- Test: `argus/backend/tests/run_cost/test_cost_api.py`

**Internals:** `EstimatedCostRequest`, `CostItemRequest` and `CostItemsRequest`
in the client router module. `Field(ge=0, allow_inf_nan=False)` rejects a
negative and a non-finite amount, and `Field(min_length=1)` rejects an empty
name and an empty category. `cost_api.py` carries `APIRouter(prefix="/cost")`
with the one read route.

- [ ] Write the failing tests: each route's success envelope, an empty name, a
      negative amount, a non-finite amount, a duplicate name, and the anonymous
      caller.
- [ ] Run them and confirm the failure.
- [ ] Add the request models, the routes and the registration.
- [ ] Document the three routes in `docs/api_usage.md`.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 3 — The finalize recompute

**Files:**
- Modify: `argus/backend/service/client_service.py`, `finish_run`
- Test: `argus/backend/tests/run_cost/test_run_cost_service.py`

**Internals:** `finish_run` calls `recompute_actual_cost` after it saves the
run. A run that reported no cost has no partition, so the call returns early.

- [ ] Write the failing tests: finalize repairs a stale sum, finalize with only
      an estimate sets the actual figure to it, and finalize on a run without
      cost changes nothing.
- [ ] Run them and confirm the failure.
- [ ] Add the call.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 4 — The Python client

**Files:**
- Create: `argus/client/types.py`
- Modify: `argus/client/base.py`, the `Routes` class and the method block
- Test: `argus/backend/tests/integration/test_run_cost.py`

**Internals:** `CostItem` as a dataclass. `SET_ESTIMATED_COST` and
`SUBMIT_COST_ITEMS` route templates, and `set_estimated_cost` and
`submit_cost_items` on the base class, so every plugin client inherits them.
The docstrings say to send nothing for a resource whose price is unknown,
because a zero is stored as a real figure.

- [ ] Write the failing end-to-end test: a real client posts an estimate and
      items, and the read route returns the totals, the sorted items and the
      per-category sums.
- [ ] Run it and confirm the failure.
- [ ] Add the dataclass, the routes and the two methods.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 5 — The Costs tab

**Files:**
- Create: `frontend/TestRun/CostsTab.svelte`
- Modify: `frontend/TestRun/TestRun.svelte`,
  `frontend/TestRun/DriverMatrixTestRun.svelte`,
  `frontend/TestRun/Generic/GenericTestRun.svelte`,
  `frontend/TestRun/Sirenada/SirenadaTestRun.svelte`
- Test: `frontend/TestRun/CostsTab.test.ts`

**Internals:** `CostsTab.svelte` takes `runId` and reads
`/api/v1/cost/run/{runId}` on mount through `fetchJson`. A null figure renders
"Not reported", never a zero. The items group by category with the subtotal the
read returns, and a leaked item carries a Bootstrap badge. Each run page gains a
tab button, an option in the narrow-screen select, and a panel gated on
`visitedTabs["costs"]`.

- [ ] Write the failing component test: the empty state, the two totals with a
      null rendering as "Not reported", and the grouped items with the mark.
- [ ] Run it and confirm the failure.
- [ ] Write the component, then wire the four run pages.
- [ ] Run `yarn build` and the verify sequence.
- [ ] Commit.

## Task 6 — The architecture note

**Files:** Modify `docs/project/architecture.md`.

**Internals:** The module counts there are explicit. The controller list gains
`cost_api.py`, and the counts move to 17 routers, 25 services and 13 models.

- [ ] Update the counts and the router list.
- [ ] Run the verify sequence.
- [ ] Commit.
