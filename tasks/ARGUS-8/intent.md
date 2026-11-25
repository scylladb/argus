# ARGUS-8 — SCT packages live on the run row

## Problem

An SCT run stores the package versions it tested in the `packages` column of
`sct_test_run`, a list of `PackageVersion` values on the run row. It is the
last per-run collection left there. Nemeses moved out under ARGUS-7 and
allocated resources under ARGUS-4.

A list on the run row has three costs.

The list is rewritten by writes that have nothing to do with packages. A
package submission reads the list, merges the new entries, and writes it back
under a lightweight transaction guarded on the old value. Every other write to
an SCT run (the heartbeat, a status change, the runner details, the replay)
loads the whole run and saves the whole run. A full save writes back the list
it read. When a package submission lands between that read and that save, the
save restores the old list and the submitted packages are lost. The
lightweight transaction cannot see a write that is not conditional.

Reading packages means reading run rows. The results charts, the Summary,
Graphed Stats and Nemesis Stats widgets, and the performance history read the
`packages` column of every run of a test. The results charts do this again on
every results submission. Each read goes through the run row, which averages
about 44 KB.

The release kernel report fails. `GET /api/v1/client/sct/release/{name}/kernels`
indexes a `PackageVersion` as a dictionary and raises a `TypeError` for any
release with a run that has packages. No test covers it.

## Who it affects

- SCT runs, which submit their packages through the client while the same run
  sends heartbeats and status updates.
- People who read the package versions of a run: the run page Packages tab,
  the run details, the issue template, the report email.
- People who read versions across runs: the results charts, the Summary,
  Graphed Stats and Nemesis Stats widgets, the performance history, and the
  similar-runs list.
- Callers of the release kernel report.

## Evidence

Jira ARGUS-8, "Promote packages to separate table", status In Progress:

> packages could be moved to separate table for more efficient access

The column, `argus/backend/plugins/sct/testrun.py:203`:

```python
    packages: list[PackageVersion] = Field(default_factory=list)
```

The conditional write in the package submission,
`argus/backend/plugins/sct/service.py:134`:

```python
            result = await run.update(if_conditions={"packages": stored or None}, **updates)
```

An unconditional full-row write, the heartbeat,
`argus/backend/service/client_service.py:110-114`:

```python
    async def heartbeat(self, run_type: str, run_id: UUID) -> int:
        model = self.get_model(run_type)
        run = await model.load_test_run(run_id)
        run.update_heartbeat()
        await run.save()
```

coodie's `save()` writes every column of the model,
`coodie/aio/document.py:195-196`:

```python
        columns = _insert_columns(cls)
        values = [getattr(self, c) for c in columns]
```

Readers of the column across all runs of a test,
`argus/backend/service/results_service.py:431`:

```python
        rows = await select_rows(plugin.model.find(test_id=test_id), "id", "investigation_status", "packages")
```

and `argus/backend/service/views_widgets/nemesis_stats.py:13`,
`argus/backend/service/views_widgets/graphed_stats.py:24`.

The kernel report indexes the value type as a dictionary,
`argus/backend/plugins/sct/service.py`, `get_scylla_version_kernels_report`:

```python
            scylla_pkgs = {
                p["name"]: p for p in packages if "scylla-server" in p["name"]}
```

The shape of the stored data on the dev cluster: 14,990 runs, 12,443 with
packages, a median of 4 and a maximum of 10 per run, 14 distinct names. In
1,931 runs one name appears more than once, always with identical values
(`scylla-server-upgraded`, four times). No run holds two different versions
under one name.

## What good looks like

- A package submission is never lost to a concurrent write to the run.
- Reading package versions for many runs does not read their run rows.
- Every place that shows package versions today shows the same versions after
  the change: the run page, the run details, the issue template, the report
  email, the results charts, the widgets, the performance history and the
  similar-runs list.
- The existing runs keep their packages.
- The release kernel report returns the Scylla versions and kernels of a
  release.

## Out of scope

- The client submission format and route stay as they are. SCT needs no
  change.
- The other columns of the run row stay on the run row.
- The legacy column and its user-defined type are dropped later, after the
  deploy, in a separate step.
- Other plugins have no packages and are not touched.
