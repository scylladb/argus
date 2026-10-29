# ARGUS-129 — Users cannot remove their own runs and jobs from Argus

## Problem

A run that Jenkins no longer holds stays in Argus. A job that an engineer
created for a one-off experiment stays in Argus too, with every run it ever
reported. Only an admin can remove a group or a test, from the admin panel,
and that removal leaves every run of the test in place. Nothing in Argus
removes a run.

Staging releases and personal folders collect runs and jobs that nobody
needs. The release dashboard, the workspace and the search show them next
to the runs that matter.

## Who it affects

- Engineers who run SCT, driver matrix, generic or sirenada jobs into a
  staging release or a personal folder, and want to keep only the runs they
  care about.
- Admins, who are the only ones who can remove a group or a test today, and
  who cannot remove a run at all.
- Every user who reads a staging release, because the stale runs and jobs
  stay in the lists and the stats.

## Evidence

Jira issue ARGUS-129:

```
In Jenkins I can delete runs that I don't care about but they remain in Argus.
For Jobs inside an user's my own staging, it should be possible to delete Argus runs and even entire jobs.
```

The admin panel release deletion popup,
`frontend/AdminPanel/ReleaseDeletionConfirmationPopup.svelte`:

```
Runs submitted for this release will be preserved
```

`argus/backend/service/release_manager.py`, `delete_test`, removes only the
test row:

```python
async def delete_test(self, test_id: UUID) -> bool:
    test_to_delete = await ArgusTest.get(id=test_id)
    await test_to_delete.delete()
    await invalidate_release_snapshots(test_to_delete.release_id)
    return True
```

## What good looks like

- An admin marks a release as one its users may edit.
- On such a release, a logged-in user removes a run from the run selector,
  a test from the workspace sidebar, or a group from the workspace sidebar.
  Each removal asks for confirmation. A test or group removal asks for the
  name of the entity.
- A removed test takes its runs with it. A removed group takes its tests and
  their runs with it. A removed run takes the rows that belong to it: its
  comments, events, issue links, configuration, cost, results and the
  plugin's own event and resource rows.
- A release without the mark shows no removal controls, and its API refuses
  a removal.
- The admin panel keeps its current behavior.

## Out of scope

- Removing a release from outside the admin panel.
- Changing what the admin panel deletes.
- Removing the notification rows, the issue rows without links, the
  distinct version and image indexes, and the references held by views and
  plans.
- Stopping the Jenkins monitor or a replay from recreating a removed job.
