# ARGUS-261 — implementation plan

**Spec:** `tasks/ARGUS-261/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Backend tests create runs and read the rollup through services
  (`ClientService.submit_run`, `RunCostService.refresh_rollup`) and the
  existing `rollup_rows` helper; explorer tests keep the `seed` helper of
  `argus/backend/tests/cost_explorer/helpers.py`, which the suite already uses
  for rollup rows.
- No rationale comments. Every import at module top.
- The backfill script is re-run, not edited.

## Task 1 — Store `started_by` on the rollup and return it

**Files:**
- Modify: `argus/backend/models/run_cost_rollup.py` (`RunCostRollup`)
- Modify: `argus/backend/plugins/sct/testrun.py` (`cost_rollup_columns`, `cost_rollup_fields`)
- Modify: `argus/backend/plugins/generic/model.py` (`GenericRun`)
- Modify: `argus/backend/service/cost_explorer_service.py` (`_top_runs`)
- Modify: `docs/api_usage.md` (the `top_runs` example of `GET /api/v1/cost/explorer`)
- Test: `argus/backend/tests/cost_rollup/test_cost_rollup_service.py`
- Test: `argus/backend/tests/cost_explorer/test_cost_explorer_service.py`

**Internals:**
- `RunCostRollup.started_by: Optional[str] = None`.
- `SCTTestRun.cost_rollup_columns()` appends `"started_by"`; its
  `cost_rollup_fields()` returns `"started_by": self.started_by`.
- `GenericRun.cost_rollup_columns()` returns `ROLLUP_COLUMNS + ("started_by",)`;
  `GenericRun.cost_rollup_fields()` returns `{"started_by": self.started_by}`.
- `_top_runs` adds `"started_by": row.started_by` to each entry.

- [x] Write the failing tests: an SCT run submitted with `started_by` rolls up
      with it; a Generic run submitted through `ClientService.submit_run("generic", ...)`
      rolls up with it; a seeded row with `started_by="alice"` comes back on
      its `top_runs` entry, and one without it comes back as `None`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Update the `top_runs` example in `docs/api_usage.md`.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Show the "Started by" column

**Files:**
- Modify: `frontend/CostExplorer/types.ts` (`TopRun`)
- Modify: `frontend/CostExplorer/TopRuns.svelte`
- Test: `frontend/CostExplorer/TopRuns.test.ts`

**Internals:**
- `TopRun.started_by: string | null`.
- `Column` gains `"started_by"`; a `SortHeader` labelled "Started by" sits
  after "Status"; the cell shows `run.started_by || "—"`. Sorting reads
  `run.started_by || null`, so the sort helper puts empty values last.

- [ ] Write the failing tests: the row shows its `started_by` and a row
      without one shows `—`; clicking "Started by" orders the rows by it.
- [ ] Run them and confirm the failure.
- [ ] Write the smallest change that passes them.
- [ ] Run the verify sequence from the `Commands` section of `CLAUDE.md`,
      and `yarn build`.
- [ ] Commit, with the boxes of this task checked.

## Deploy note

After `sync-models` adds the column, re-run
`uv run python scripts/migration/migration_2026-10-29_backfill_run_cost_rollup.py`
so the rows written before the deploy carry `started_by`. The pull request
body states this step.
