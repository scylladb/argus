# ARGUS-65 — Avoid packages duplicates

**Date**: 2026-09-17

## Root cause

`SCTService.submit_packages` in `argus/backend/plugins/sct/service.py:95-107`
reads the run, checks each submitted package against `run.packages`, appends
the new ones, and saves the run. The four steps are not atomic. Two requests
that run at the same time both pass the check, because neither sees the row
the other one adds.

The equality check is correct. `PackageVersion.__eq__` in
`argus/backend/plugins/sct/udt.py` compares the five fields, and `None`
compares equal to `None`. The check has no chance to see the duplicate.

SCT produces the parallel requests. `StressThread.run` in
`sdcm/stress_thread.py` submits one `_run_cs_stress` task per loader and per
CPU to a thread pool. Each task builds a `CassandraStressVersionReporter` and
calls `report_package_to_argus`, which posts the `java-driver` package. The
`lru_cache` on that function does not stop the parallel misses, and its
`runner` argument differs per loader. The result is N identical POST requests
in the same instant, one per stress thread.

The duplicate rows in the staging run came from the cqlengine mapper, which
saved a list append as `packages = packages + [row]`. Each racing request
appended its own copy. The coodie mapper saves the full row, so the same race
today keeps one copy but drops the packages that the other request added. The
mechanism is the same read-then-write window in both cases.

## Approaches

1. **Compare-and-set on the packages column** — selected. Read the run, merge
   the submitted packages into the stored list, and write the list with a
   conditional update: `UPDATE ... SET packages = ? IF packages = ?`. When the
   condition fails, read again and retry. Cost: one lightweight transaction
   per submission, a few per run. Risk: a retry limit that a hot run can hit.
   The service raises after the limit, and the client logs the failure.
   Reason: it closes the window without a schema change, and a probe against
   the test ScyllaDB confirmed that the condition works on the
   `list<frozen<packageversion_v2>>` column.
2. **A `set<frozen<packageversion_v2>>` column.** The database enforces the
   uniqueness. Cost: a new versioned table, a data copy, and a change to
   every reader of `packages`. Risk: a long migration for a small gain.
   Rejected for cost.
3. **A lock per run in the process.** Cost: small. Risk: the web backend runs
   several workers, so the lock covers one process only. Rejected because it
   does not close the window.

## Regression test

`argus/backend/tests/sct_api/test_sct_api.py::test_submit_packages_concurrent_submissions_keep_one_row`.
The test patches `SCTTestRun.get` so that a second submission of the same
package lands between the read and the write of the first one. Before the
fix, the run holds two identical rows with the cqlengine append, or loses the
second submission's package with the coodie full-row save. After the fix,
the run holds one row per distinct package.

## Risks

| Risk | Response |
|---|---|
| Another endpoint saves the full run row while a package submission runs, and the save writes a stale `packages` list. | Outside this fix. The same window exists for every other column of the run. |
| The retry limit is hit under heavy contention. | The service raises `SCTServiceException`. The client logs it and the test goes on. |
| An empty stored list reads back as `None`, and the condition `IF packages = []` does not match it. | The service passes `None` as the expected value when the stored list is empty. |
