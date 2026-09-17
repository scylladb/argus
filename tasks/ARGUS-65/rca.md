# ARGUS-65 — Avoid packages duplicates

**Date**: 2026-09-17

## Root cause

`SCTService.submit_packages` (`argus/backend/plugins/sct/service.py`)
originally guarded every append with:

```python
if package not in run.packages:
    run.packages.append(package)
```

`package not in run.packages` calls `PackageVersion.__eq__`
(`argus/backend/plugins/sct/udt.py`), which compares all five fields
(`name`, `version`, `date`, `revision_id`, `build_id`). A re-submission of a
package the run already has — same `name`, different `date` or `build_id`,
which is exactly what a CI retry or a re-triggered post-run step produces —
compares unequal to the stored row, so the guard lets it through and the run
ends up with two rows for one package name (e.g. two `java-driver` rows).

## Round 1 and its follow-up correction

Round 1 (`b06431b`) narrowed the guard to `name` alone:

```python
if not any(existing.name == package.name for existing in run.packages):
    run.packages.append(package)
```

A PR reviewer flagged this: it collapses two genuinely different versions of
the same package name (e.g. `java-driver` 3.x and a later 4.x build) into
one row, against the explicit requirement that different versions stay
visible. The reviewer's stated hypothesis — that `PackageVersion.__eq__`
mishandles `None` comparisons — does not hold: plain `==` already treats
`None == None` as equal, so the original full-field guard was never broken
by that. The real defect was the key being too broad in the *name-only*
direction.

## Fix

Widen the key back to `(name, version)`, keep-first, on the same single
append-time guard round 1 had (no separate rebuild/heal step):

```python
if not any(existing.name == package.name and existing.version == package.version
           for existing in run.packages):
    run.packages.append(package)
```

This is narrow enough to let distinct versions of one package name coexist
(the reviewer's requirement), and wide enough to collapse a re-submission
that only changed `date`/`build_id`/`revision_id` for the same name+version
(the original bug).

### Checked: does `(name, version)` break any reader?

`argus/backend/service/results_service.py::_identify_most_changed_package`
groups packages by `name` and collects `(version, date)` pairs, but its
input is the flattened `packages` of every run *in a test*, aggregated
across runs, not within one run's own list. Deduping within a single run's
`packages` list by `(name, version)` does not remove any cross-run
diversity this function relies on. Other readers of `run.packages`
(`get_scylla_version_kernels_report`, `get_similar_runs_info`,
`email_service.py`, `graphed_stats.py`, `nemesis_stats.py`) match by `name`
and take the first or only hit; collapsing same-name-same-version
duplicates doesn't change their behavior, and a genuine second version
under one name stays visible to them, which is what `(name, version)`
preserves.

## Scope boundary (reaffirmed)

This fix, like round 1, only guards the *append* step for packages
submitted in the current request. It does not rebuild or heal
`run.packages` for rows already stored from before this call. A retried
request racing two `get()`/`save()` cycles, or historical data written
before any dedup guard existed, could in principle already have duplicate
rows sitting in Cassandra; that is a known possibility but is explicitly out
of scope here (see `intent.md`'s "Out of scope"). Cleaning up existing
duplicate rows in production needs a proper one-off maintenance
command/ticket, not an implicit side effect of every `submit_packages` call.
An earlier version of this fix (round 2) added such a rebuild step; it was
reverted as unrequested scope creep — see PR #1093 review.

## Regression test

`argus/backend/tests/sct_api/test_sct_api.py::test_submit_packages_deduplicates_by_name_and_version`
(renamed and extended from round 1's `test_submit_packages_deduplicates_by_name`):

1. Submits `java-driver` `3.11.5.7`, then re-submits `java-driver`
   `3.11.5.7` with a different `date`/`build_id`/`revision_id`, alongside a
   distinct `kernel` package in the same call. Asserts exactly one
   `java-driver` row and one `kernel` row, with the `java-driver` row
   retaining the *first* submission's `date`/`build_id` (keep-first).
2. Submits `java-driver` `4.15.0` — a different version, same name — as a
   third call. Asserts the run now holds *two* `java-driver` rows, one per
   version. This fails under round 1's `name`-only guard (which would have
   collapsed it to one row) and passes under this guard.

`test_submit_packages` (unchanged) continues to cover the single-submission
path.

## Risks

| Risk | Response |
|---|---|
| ScyllaDB's `list<packageversion_v2>` column has no server-side uniqueness constraint; nothing stops a future code path from appending a duplicate `(name, version)` outside this guard | Service-layer only fix, as scoped, same as round 1. |
| Existing duplicate rows already stored in production are not touched by this fix | Explicitly out of scope per `intent.md`; needs a separate follow-up maintenance command/ticket. |
| Keep-first drops a legitimately updated `date`/`build_id` for a `(name, version)` pair that changes mid-run | Accepted, same as round 1: packages are reported once per run in practice. |
