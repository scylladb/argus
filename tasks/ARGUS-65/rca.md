# ARGUS-65 — Avoid packages duplicates

**Date**: 2026-09-17

## Root cause

`SCTService.submit_packages` (`argus/backend/plugins/sct/service.py`,
`submit_packages`) guards every append with:

```python
for package_dict in packages:
    package = PackageVersion(**package_dict)
    if "target" in package.name:
        SCTService.process_target_version(run, package)
    if package not in run.packages:
        run.packages.append(package)
run.save()
```

`package not in run.packages` calls `PackageVersion.__eq__`
(`argus/backend/plugins/sct/udt.py`):

```python
def __eq__(self, other):
    if isinstance(other, PackageVersion):
        return all(getattr(self, a) == getattr(other, a) for a in ["name", "version", "date", "revision_id", "build_id"])
    return super().__eq__(other)
```

The guard treats two `PackageVersion` records as "the same package" only when
every field matches. `name` is one field among five. A re-submission of a
package the run already has — same `name`, different `date` or `build_id`,
which is exactly what a CI retry or a re-triggered post-run step produces —
compares unequal to the stored row, so the `not in` check is `True` and the
row is appended. The run ends up with two rows sharing one `name` (e.g. two
`java-driver` rows), which is what the Packages tab shows.

PR #830 (commit `79b701d`, "fix submit_packages API to not fail on empty
version_source") touched the same loop for a different symptom (an empty
`version_source` crashing `process_target_version`) and left this guard as
is.

## Approaches

**1. Keep-first by name: guard on `name` identity instead of full-record
equality. Selected.**

```python
if not any(existing.name == package.name for existing in run.packages):
    run.packages.append(package)
```

The run keeps the first row it ever saw for a given package `name`; a later
submission with the same `name` and different `date`/`build_id`/`revision_id`
is a no-op. Cost: one line. Risk: a package's `date`/`build_id` that
genuinely changes across the run's lifetime (e.g. a package the CI job
re-resolves partway through) no longer updates the stored row — see Risks.

**2. Upsert by name: replace the existing row with the new one.**

Rejected. `run.packages` is read at several places (e.g.
`get_scylla_version_kernels_report`, `get_similar_runs_info`) with "first
match by name" semantics; an unconditional replace would silently discard
whichever value (older or newer) the read path currently depends on,
including a pre-upgrade baseline value that a later "same name, upgraded
build" submission would then overwrite. Keep-first is the smaller, safer
change and matches what the guard was already trying to express before the
bug: "add it once".

**3. Deduplicate at read time (e.g. in `get_run_response` or the frontend).**

Rejected. It treats the symptom instead of the cause: writes still
accumulate duplicate rows in the underlying `list<packageversion_v2>`
column, so every reader would need the same workaround, and the stored data
keeps growing.

## Regression test

`argus/backend/tests/sct_api/test_sct_api.py::test_submit_packages_deduplicates_by_name`
— submits a `java-driver` package, then submits it again with a different
`date` and `build_id` alongside a distinct `kernel` package, and asserts
`run.packages` holds exactly one `java-driver` row and exactly one `kernel`
row. The two `java-driver` payloads differ only in `date`/`build_id`, so the
old `PackageVersion.__eq__`-based guard would let both through; the test
fails on the old guard and passes with the name-identity guard.
`test_submit_packages` (unchanged) continues to cover the single-submission
path.

## Risks

| Risk | Response |
|---|---|
| ScyllaDB's `list<packageversion_v2>` column has no server-side uniqueness constraint; nothing stops a future code path from appending a duplicate name outside this guard | Service-layer only fix, as scoped. Flagged as a deviation from the general "enforce data rules at the database level" guidance in `docs/standards/backend/models.md` — a list column of a UDT cannot express a uniqueness constraint on one sub-field, so this rule is enforced at the point of the only writer (`submit_packages`) instead. |
| Keep-first drops a legitimately updated `date`/`build_id` for a name that changes mid-run | Accepted: the run's package identity (which version of `scylla-server`, `java-driver`, etc. it used) is set once per run in practice; the existing single-submission test and the SCT client's usage confirm packages are reported once per run, not updated in place. |
| Existing duplicate rows already stored in production are not touched by this fix | Out of scope per `intent.md`; a follow-up Jira issue covers any production data cleanup. |
