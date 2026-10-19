# ARGUS-150 — A nemesis is missing from the run when two start in one second

**Date**: 2026-10-19

## Root cause

**The nemesis row key has one-second resolution.** A nemesis is a row of
`sct_nemesis`, keyed by the run and the start time,
`argus/backend/plugins/sct/testrun.py:133-145`:

```python
class SCTNemesis(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    start_time: Annotated[int, ClusteringKey()]
```

SCT sends the start time in whole seconds (`sdcm/nemesis/__init__.py`,
`argus_submit`: `start_time=int(start_time)`). The two disruptions in the
ticket started at `13:20:45.393005` and `13:20:45.425795`. Both truncate to
the same second, so both submits address one row.

**The second submit is dropped.** `submit_nemesis`,
`argus/backend/plugins/sct/service.py:440-441`, answers `"created"` without
writing when the row exists:

```python
        if await SCTNemesis.find(run_id=run_uuid, start_time=int(nem_req.start_time)).first() is not None:
            return "created"
```

The request of `ModifyTableMaxIndexIntervalMonkey` reached Argus first and
made the row. The request of `GrowShrinkClusterNemesis` found it and wrote
nothing, and SCT got a success. The key and the check both arrived with
commit 3168803c (2026-04-08), which moved the nemeses from the
`nemesis_data` list on the run row into their own table. As list items, two
nemeses in one second coexisted. The ticket (2026-05-19) is against the
table.

**The finalize lands on the wrong row.** `finalize_nemesis`,
`service.py:471-478`, looks the row up by the same two columns and ignores
the name the request carries:

```python
            nemesis = await SCTNemesis.get(
                run_id=run.id, start_time=int(nem_req.start_time))
            ...
            if nemesis.status != NemesisStatus.RUNNING.value:
                return "updated"
```

The first finalize to arrive, from either nemesis, writes its status and
message onto the one row. The second finds the row no longer running and
returns. The row the run keeps can carry the other nemesis's outcome. The
second `except DocumentNotFound` at `service.py:491-493` is unreachable, so
a missing run is logged as "Nemesis not found".

**A second collision source in SCT.** `precheck_nemesis`
(`sdcm/nemesis/__init__.py`, since SCT d98f8030d, 2026-06-16) takes one
`start_time = time.time()` before its loop and submits and finalizes every
precheck-excluded nemesis with it. The first excluded nemesis makes the
row; every later one is dropped, parallel nemesis or not. The names differ
per class, since SCT reports each class once.

**The counters race.** Both endpoints count on the run row with a
read-modify-write, `service.py:458-459` and `484-485`:

```python
            run.update_nemesis_stats("total")
            await run.save()
```

`update_nemesis_stats` (`testrun.py:449-454`) increments a key of the
in-memory `nemesis_stats` map, and `save()` is an INSERT of every column of
the run (coodie `aio/document.py:184-201`). Two submits in one instant read
the same map and both write it back with one increment, so one count is
lost. The same INSERT writes back the stale in-memory copy of every other
column, `packages` and `heartbeat` included, which undoes a concurrent
update of those columns and defeats the compare-and-set that bed90ea8 gave
`submit_packages`.

## Approaches

**A. A new versioned table keyed by run, start time and name.** *Selected.*
`SCTNemesis` moves to `sct_nemesis_v2` with the clustering key
`(start_time, name)`. The submit's duplicate check and the finalize's lookup
add the name. The key is exactly the identity the finalize request already
carries, and SCT passes one variable to both calls on every path, so no
client changes. `start_time` stays first in the key, so the row order and
any range read stay as today. A primary key cannot change in place and
`sync-models` only creates tables and adds columns, so this is a `_v2`
table and a backfill, as `docs/standards/backend/migrations.md` prescribes.
The backfill is a dated script under `scripts/migration/` that copies every
`sct_nemesis` row: a running row with `INSERT … IF NOT EXISTS`, so a re-run
never overwrites a row the new release finalized in v2, and a finished row
with a plain upsert, so the status the old release wrote after the first
pass reaches v2. The deploy runs the script right before the release flip
and again right after it. The old table stays until a later change drops
it. The counters move to a compare-and-set in the shape of
`submit_packages`: read the map, write the incremented map with
`IF nemesis_stats = <read map>`, retry on a lost race. That writes one
column and retires the full-row `save()` in both endpoints. Cost: a new
table, a backfill with two passes, about 48,000 rows on the production
snapshot. Risk: the deploy window, in the table below.

**B. SCT sends a unique nemesis id or a sub-second start time.** Argus
would key on what SCT sends. Cross-repo, and every older SCT branch keeps
sending whole seconds, so Argus keeps the collision for them. A sub-second
timestamp is a type change, which is still a new table, and the precheck
path shares one start time by design. Rejected.

**C. Keep the table and shift a colliding start time by one second.** The
submit would store the second nemesis at `start_time + 1`. It stores a
start time the nemesis did not have, and the finalize request, which
carries the real start time, would not find the row. Rejected.

## Regression test

`argus/backend/tests/sct_api/test_sct_api.py`, through the API, fixture
`sct_run_id`:

- `test_nemesis_submit_keeps_two_nemeses_with_one_start_time`: submit
  `GrowShrinkClusterNemesis` and `ModifyTableMaxIndexIntervalMonkey` with
  one start time, finalize the first as succeeded and the second as failed,
  and read `/nemesis/get`. Both rows come back, each with its own status
  and message. Fails today: the second submit is dropped and its finalize
  is swallowed by the first row.
- `test_nemesis_submit_concurrent_submissions_keep_every_increment`: a
  second submit runs inside the first one's read of the run, the pattern of
  `test_submit_packages_concurrent_submissions_keep_one_row`. The run's
  `nemesis_stats` reads `{"total": 2}`. Fails today: one increment is lost.

The backfill script has no test. No script under `scripts/migration/` has
one; it runs by hand against the dev cluster before the pull request.

## Risks

| Risk | Response |
|---|---|
| Run pages show no nemeses between the flip and the backfill | The first pass runs after `sync-models` and right before the flip; 48,000 rows copy in minutes |
| A nemesis submitted to the old table after the first pass and finalized by the new release before the second | One "Nemesis not found" for that finalize, which SCT logs and survives; the second pass copies the row as running, the outcome of any failed finalize today. The second pass runs right after the flip to keep the window to minutes |
| The first pass copied a running row that the old release then finished in the old table | The second pass upserts finished rows, so the final status reaches v2 |
| Two threads run the same nemesis class in the same second | Still one row: SCT sends the class name, not its unique disruption name. Out of scope per the intent |
| A reader still on `sct_nemesis` | Only the model names the table. Every reader goes through `SCTNemesis` by `run_id` and uses columns that do not change |
| The conditional update on a map column | The same builder path as the `packages` list condition in `submit_packages`, which runs in production. An empty map reads back as null, so the condition compares against null the same way |
| A client finalizes under a name other than the one it submitted | SCT passes one variable to both calls on every path, and the client API required the name in both before this change |
