# ARGUS-150 — A nemesis is missing from the run when two start in one second

## Problem

An SCT run that drives several nemesis threads at once shows only one of
the nemeses that start within the same second. The run page lists
`ModifyTableMaxIndexIntervalMonkey` but not `GrowShrinkClusterNemesis`,
although SCT started both 32 ms apart. The submit of the second nemesis
is accepted and the response reports success, so SCT does not retry or
log it.

When the lost nemesis finishes, its status and message land on the
nemesis that is shown, and the shown nemesis's own finish is discarded.
The one row the run keeps can carry the other nemesis's outcome.

The same loss hits the nemeses SCT excludes before the run loop. SCT
reports every excluded nemesis with one start time, so the run keeps one
of them.

The run's nemesis counters, which the release dashboard shows as
`failed / total`, are counted on the run row with a read-modify-write.
Two submits in the same instant can lose a count, so the counter and the
list can disagree.

## Who it affects

- Engineers who open the nemesis tab of a run with parallel nemesis, or a
  run that excluded nemeses by precheck, and see fewer nemeses than SCT
  ran.
- Engineers who triage from the release dashboard: the `failed / total`
  badge of the run can disagree with its nemesis list.
- The nemesis stats and graphed stats widgets, which count succeeded and
  failed nemeses per version from the same rows, so a lost nemesis never
  reaches a trend.
- The run report email, which lists the run's nemeses from the same rows.

## Evidence

Jira issue ARGUS-150:

```
https://argus.scylladb.com/tests/scylla-cluster-tests/a5a85827-89f5-4948-a0f6-e687d5bd7aa1/nemesisOnly
ModifyTableMaxIndexIntervalMonkey is listed, GrowShrinkClusterNemesis is missing
In actions.log
{"datetime": "2026-05-19T13:20:45.393005+00:00Z", "status": "info", "source": "Nemesis25bbeaf8", "action": "Started - Disruption GrowShrinkClusterNemesis on raft-double-cluster-size-with-schem-db-node-a5a85827-0-1"}
{"datetime": "2026-05-19T13:20:45.425795+00:00Z", "status": "info", "source": "Nemesisdf00d0e0", "action": "Started - Disruption ModifyTableMaxIndexIntervalMonkey on raft-double-cluster-size-with-schem-db-node-a5a85827-0-2"}
```

SCT sends the start time in whole seconds, `sdcm/nemesis/__init__.py`,
`argus_submit`:

```python
            argus_client.submit_nemesis(
                name=nemesis_name,
                class_name=self.get_class_name(),
                start_time=int(start_time),
```

SCT reports every precheck-excluded nemesis with one start time,
`sdcm/nemesis/__init__.py`, `precheck_nemesis`:

```python
        start_time = time.time()
        precheck_node = self.cluster.nodes[0]
        for nemesis in self.disruptions_list:
```

## What good looks like

- A run shows every nemesis SCT submitted, two or more in one second
  included, each with its own name, node, status and message.
- The nemeses SCT excludes by precheck all appear, each as skipped or
  failed with its own reason.
- The run's `failed / total` counter equals the count of the rows in its
  nemesis list, under parallel submits too.
- Runs recorded before the fix keep every nemesis they have today.

## Out of scope

- Changes to what SCT sends. The fix works with the payload SCT sends
  today and with older SCT branches.
- Two threads that run the same nemesis class in the same second. SCT
  sends the class name, not the unique disruption name, so the run cannot
  tell them apart.
- Recovering the nemeses that past runs already lost. The rows were never
  written.
