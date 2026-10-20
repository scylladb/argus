# ARGUS-47 — Support nemesis descriptions and extend NemesisTable

## Problem

SCT reports each nemesis to Argus with the docstring of its nemesis class
as a `description`. Argus accepts the field on the nemesis submit endpoint
and drops it: the nemesis row has no place for it, the run response does
not carry it, and nothing shows it. An investigation of a failed nemesis
still opens the SCT source to learn what the nemesis does.

The text cannot simply be copied into every nemesis row. A docstring
changes over time in SCT, and SCT branches that run in parallel send
different versions of it in the same week, so a run must keep the text it
was reported with, and the same text repeated across thousands of runs
would be stored thousands of times.

The run-page nemesis widget is a fixed `<table>` with five columns. It
has no room for a description. On a narrow window it overflows, its sort
reverses on every header click, including a click on a different column,
the sort by target node reorders the run data in place, a filter that is
not a valid regular expression hides every row, the expanded details of a
nemesis close on the two-minute refresh, and the filter input has no
label.

The Go CLI prints a nemesis table without a description.

## Who it affects

- Engineers who investigate an SCT run on the run page and in the Events
  tab, on a laptop screen or a split window.
- SCT pipelines, which already send the field on every nemesis.
- Callers of `argus run nemeses`, including the AI workers that read the
  CLI output.

## Evidence

The Jira issue, migrated from GitHub issue 683:

```
Currently we are sending only name for the nemesis, but we could be sending also a description of the nemesis. We could get description for the nemesis by running nemesis_method.__doc__ and we could send it to Argus as part of the send nemesis request. This would improve the investigations as more information would be present without the need to go to SCT code.

To make this work we need support in Argus for descriptions for Nemesis and then a small patch to SCT which would send the docstrings. Currently, not many disrupt methods have descriptions, but we could improve them gradually.
```

The commit that added the field to the API, `6144b476` (ARGUS-90):

```
Add API to send nemesis description.
Still Argus doesn't support saving it (we don't want to further
complicate sct table and not yet decided where we want to store these
descriptions).
```

SCT sends it on every nemesis, `sdcm/nemesis/__init__.py` in
scylla-cluster-tests since commit `d12fa4476`:

```
self.argus_submit(
    nemesis_name=class_name,
    start_time=start_time,
    nemesis_event=nemesis_event,
    description=nemesis.__class__.__doc__,
),
```

Argus takes the field and does not store it, `argus/backend/plugins/sct/service.py`:

```
class NemesisSubmissionRequest:
    name: str
    class_name: str
    start_time: int
    node_name: str
    node_ip: str
    node_shards: int
    description: str | None = None
```

```
nemesis_info = SCTNemesis(
    run_id=run_id,
    start_time=int(nem_req.start_time),
    class_name=nem_req.class_name,
    name=nem_req.name,
    end_time=0,
    duration=0,
    stack_trace="",
    status=NemesisStatus.RUNNING.value,
    target_node=node_desc,
)
```

The nemesis row, `argus/backend/plugins/sct/testrun.py`:

```
class SCTNemesis(Document):
    run_id: Annotated[UUID, PrimaryKey()]
    start_time: Annotated[int, ClusteringKey(clustering_key_index=0)]
    name: Annotated[str, ClusteringKey(clustering_key_index=1)]
    class_name: str
    duration: int
    target_node: NodeDescription
    status: str
    end_time: int
    stack_trace: str
```

The widget's sort by target node, `frontend/TestRun/NemesisTable.svelte`:

```
if (key == "node") {
    return nemeses.sort((a, b) => {
```

Its filter, which hides every row on a bad pattern:

```
try {
    return !RegExp(filterString.toLowerCase()).test(nemesisString.toLowerCase());
} catch (e) {
    return true;
}
```

## What good looks like

- A nemesis submitted with a description shows it on the run page, under
  its name and in its expanded details, and the client `GET
  /api/v1/client/sct/{run_id}/nemesis/get` returns it.
- A run keeps the description it was reported with. After the docstring
  changes in SCT, an older run still shows the old text and a newer run
  shows the new one.
- A description text is stored once, however many nemeses carry it.
- A nemesis sent without a description, and every nemesis reported before
  this change, shows no description and nothing else changes.
- The nemesis tab reads at a desktop width and at a narrow width, and keeps
  what the table does today: sorting by name, target node, status, start
  and end, text filtering, status colours, and expandable details with the
  failure or skip reason and the target node information.
- A sort click on a new column does not reverse the order, a bad filter
  pattern still matches as plain text, and an expanded nemesis stays
  expanded across the periodic refresh.
- `argus run nemeses` prints the description when asked for it, and its
  JSON output carries the field.

## Out of scope

- The SCT side. It already sends the class docstring. A fallback to the
  `disrupt_*` method docstring is an SCT change.
- The nemesis stats and graphed stats view widgets, and the email nemesis
  section.
- Typing the nemesis submit and finalize request bodies.
