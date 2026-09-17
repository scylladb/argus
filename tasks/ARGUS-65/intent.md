# ARGUS-65 — Avoid packages duplicates

## Problem

Submitting SCT packages for a run can create a second entry for a package
name the run already has. The Packages tab on a test run then shows two rows
for the same package, e.g. two `java-driver` entries with different
`date`/`build_id` values.

## Who it affects

Any SCT run whose CI job re-reports the same package list (a retry, a
re-triggered post-run step, or a second submission with a refreshed
`build_id`/`date`). The Packages tab and any consumer of `run.packages` (e.g.
`get_scylla_version_kernels_report`, `get_similar_runs_info`) sees the
duplicate name and picks whichever row iteration order returns first.

## Evidence

`argus/backend/plugins/sct/service.py::SCTService.submit_packages` guards the
append with `if package not in run.packages`, and `PackageVersion.__eq__`
(`argus/backend/plugins/sct/udt.py`) compares `name`, `version`, `date`,
`revision_id`, and `build_id` together. A second submission of the same
package `name` with a different `date` or `build_id` is not equal to the
first row, so the guard lets it through and the run ends up with two rows
for one package name (e.g. two `java-driver` rows).

## What good looks like

Submitting packages for a run never produces two rows with the same
`name` in `run.packages`. Re-submitting a package name the run already has is
a no-op for that name; the first-submitted row for that name stays.

## Out of scope

- Cleaning up duplicate package rows already stored for existing runs in
  production — a separate follow-up.
- Any change to `PackagesSubmitRequest`, the `PackageVersion` UDT or its
  `__eq__`, the client SDK, the controller, or the frontend.
