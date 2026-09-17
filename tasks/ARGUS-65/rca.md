
# ARGUS-65 — Avoid packages duplicates

**Date**: 2026-09-17

## Root cause

`SCTService.submit_packages` (`argus/backend/plugins/sct/service.py`,
`submit_packages`) originally guarded every append with:

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

### Correction after PR review (round 2)

Round 1 landed a fix that guarded on `name` alone:

```python
if not any(existing.name == package.name for existing in run.packages):
    run.packages.append(package)
```

A PR reviewer flagged this against a real production example: two
byte-identical `java-driver` rows (`version="3.11.5.7"`, `date=null`,
`revision_id=null`, `build_id=null` on both) landed in `run.packages`. The
reviewer's stated hypothesis — that `None`/null values are "not correctly
compared" in the equality check — does not hold up: `PackageVersion.__eq__`
uses plain `==` field-by-field, and `None == None` is `True` in Python, so
two dicts identical in all five fields (including two `None`s) already
compare equal under the *original* pre-round-1 guard. `__eq__` itself was
never the defect.

Two real problems existed instead:

1. **Round 1's `name`-only key was too broad.** The reviewer explicitly
   requires "different versions of the same package[s] visible" — a run
   legitimately reporting `java-driver` 3.x and later a genuinely different
   `java-driver` 4.x build must keep both rows. Guarding on `name` alone
   silently drops the second version, which is a regression against that
   requirement, not a fix. The correct identity key is **`(name, version)`**,
   keep-first — narrow enough to let distinct versions of one package
   coexist, wide enough to collapse a re-submission that only changed
   `date`/`build_id`/`revision_id` for the same name+version.

2. **Neither guard (the original `__eq__`-based one nor round 1's
   `name`-only one) heals a duplicate that is already sitting in storage.**
   `run.save()` rewrites the whole `packages` list column; the guard only
   ever gate-keeps the *append* step for packages submitted in the *current*
   request. If two duplicate rows already exist in Cassandra — from a
   retried POST that raced two `SCTTestRun.get()` / `run.save()` cycles
   against each other (see `argus/client/session.py`'s retry-on-read-timeout
   behavior), or from historical data written before any dedup guard existed
   (before commit `b0babaf3`) — nothing in the old code path ever removes
   them. The reviewer's literal reported pair (byte-identical, `date=null`
   on both) is best explained by this: it's not that the equality guard let
   it through in one request, it's that the duplicate was already stored and
   nothing since has ever pruned it.

The fix therefore has two parts: change the key to `(name, version)`, and
make the guard *heal* on every submission — rebuild `run.packages`
deduplicated by that key (keep-first, original order) before processing new
submissions, so a run's stored list converges to at most one row per
`(name, version)` the next time packages are submitted for it, instead of
preserving any pre-existing duplicate forever.

### Checked: does `(name, version)` break any reader?

`argus/backend/service/results_service.py::_identify_most_changed_package`
groups packages by `name` and collects a *set* of `(version, date)` pairs
per name, to find which package name has the most distinct
version/date combinations (used to auto-pick the "main" package for
rolling-upgrade graphs). Its input,
`[pkg for sublist in runs_details.packages.values() for pkg in sublist]`, is
the *flattened packages of every run in a test* — the variance this function
relies on comes from different runs reporting different builds over time,
not from duplicate rows sitting inside one run's own `packages` list. Deduping
within a single run's list by `(name, version)` does not remove any
cross-run `(version, date)` diversity this function depends on; it only
collapses same-run entries that share both `name` and `version` and differ
only in `date`/`build_id`/`revision_id` — exactly the retried/duplicate
rows this fix targets. No conflict found; `(name, version)` is safe.

Other readers of `run.packages` (`get_scylla_version_kernels_report`,
`get_similar_runs_info`, `email_service.py`, `graphed_stats.py`,
`nemesis_stats.py`) all match by `name` (`pkg.name == pkg_name`) and take the
first or only hit; they are unaffected by collapsing same-`name`-same-`version`
duplicates and are exactly the callers a genuine second *version* under one
name must remain visible to, which `(name, version)` preserves.

## Approaches

**1. Keep-first by `(name, version)`, with healing rebuild on every
submission. Selected.**

```python
deduped: dict[tuple[str, str], PackageVersion] = {}
for existing in run.packages:
    deduped.setdefault((existing.name, existing.version), existing)
run.packages = list(deduped.values())
for package_dict in packages:
    package = PackageVersion(**package_dict)
    if "target" in package.name:
        SCTService.process_target_version(run, package)
    key = (package.name, package.version)
    if key not in deduped:
        deduped[key] = package
        run.packages.append(package)
run.save()
```

The run keeps the first row it ever saw for a given `(name, version)` pair;
a later submission with the same `name` *and* `version` but a different
`date`/`build_id`/`revision_id` is a no-op. A later submission with the
same `name` but a *different* `version` is appended as its own row, per the
reviewer's explicit requirement. Any duplicate already stored under the old
guards is pruned the next time this endpoint runs for that run, because the
rebuild step runs unconditionally before new packages are processed.

**2. Keep-first by `name` alone (round 1's approach).**

Rejected on reviewer feedback: it merges two rows that differ in `version`,
which the reviewer explicitly said must stay distinct and visible. Kept in
this document as the approach superseded by this round.

**3. Keep-first by full 5-field equality (the original, pre-round-1
behavior).**

Rejected: this is what let the reviewer's exact-duplicate pair through in
the first place. It correctly rejects an *identical* re-submission within
one request, but doesn't stop two duplicate rows both ending up stored
across two racing requests, and doesn't heal a duplicate once it exists in
storage. `__eq__` itself is not wrong, but the guard built on top of it
never guaranteed convergence over time.

**4. Upsert by `(name, version)`: replace the existing row with the new
one.**

Rejected. `run.packages` is read at several places with "first match by
name" semantics; an unconditional replace could still leave a run's
`date`/`build_id` at whatever the *last* submission set it to, rather than
the deliberately-chosen "first" the rest of this fix relies on for
consistency across reads. Keep-first plus healing accomplishes the visible
goal (no duplicate rows, distinct versions preserved) without introducing a
second kind of "latest wins" semantics alongside it.

**5. Deduplicate at read time (e.g. in `get_run_response` or the
frontend).**

Rejected. It treats the symptom instead of the cause: writes still
accumulate duplicate rows in the underlying `list<packageversion_v2>`
column, so every reader would need the same workaround, and the stored data
keeps growing. `ResultsService._remove_duplicate_packages` already exists
as a narrow, unrelated read-time filter for a different purpose (collapsing
`scylla-server`/`scylla-server-upgraded`/`*-target` variants into one
"main" package for graphing) — it is not a general dedup mechanism and this
fix does not extend or rely on it.

## Regression test

`argus/backend/tests/sct_api/test_sct_api.py::test_submit_packages_deduplicates_by_name_and_version`
(renamed and extended from round 1's
`test_submit_packages_deduplicates_by_name`):

1. Submits `java-driver` `3.11.5.7`, then re-submits `java-driver`
   `3.11.5.7` with a different `date`/`build_id`/`revision_id` (the
   reviewer's reported shape) alongside a distinct `kernel` package in the
   same call. Asserts exactly one `java-driver` row and one `kernel` row,
   with the `java-driver` row retaining the *first* submission's
   `date`/`build_id` (keep-first).
2. Submits `java-driver` `4.15.0` — a different version, same name — as a
   third call. Asserts the run now holds *two* `java-driver` rows, one per
   version (`{"3.11.5.7", "4.15.0"}`). This is the case round 1's test
   never exercised; it fails under round 1's `name`-only guard (which would
   have collapsed it to one row) and passes under this round's
   `(name, version)` guard.

`test_submit_packages` (unchanged) continues to cover the single-submission
path.

## Risks

| Risk | Response |
|---|---|
| ScyllaDB's `list<packageversion_v2>` column has no server-side uniqueness constraint; nothing stops a future code path from appending a duplicate `(name, version)` outside this guard | Service-layer only fix, as scoped. Flagged as a deviation from the general "enforce data rules at the database level" guidance in `docs/standards/backend/models.md` — a list column of a UDT cannot express a uniqueness constraint on a sub-tuple of fields, so this rule is enforced at the point of the only writer (`submit_packages`) instead. The healing rebuild mitigates drift: even if some other path appends a duplicate, the next `submit_packages` call for that run prunes it. |
| Keep-first drops a legitimately updated `date`/`build_id` for a `(name, version)` pair that changes mid-run | Accepted, same as round 1: the run's package identity per version is set once per run in practice; `test_submit_packages` and the SCT client's usage confirm packages are reported once per run, not updated in place for the same version. |
| Existing duplicate rows already stored in production, for runs that never get another `submit_packages` call, are not touched by this fix | Reduced from round 1 but not eliminated: the healing rebuild now prunes duplicates on the *next* submission for a given run, so any run with ongoing package reporting self-heals; a run whose packages will never be submitted again still needs an out-of-band cleanup. Out of scope per `intent.md`; a follow-up Jira issue covers any production data cleanup that the healing rebuild doesn't reach. |
| `(name, version)` key could, in principle, hide multiple `date` values for one `(name, version)` from a reader that needs them | Checked: `_identify_most_changed_package` (`results_service.py`) is the one place in the codebase that inspects `date` alongside `version`, and it aggregates across *runs*, not within one run's list — see "Checked" section above. No reader depends on seeing multiple `date` values for the same `(name, version)` inside a single run's `packages` list. |
