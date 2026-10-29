# ARGUS-129 — implementation plan

**Spec:** `tasks/ARGUS-129/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Follow `docs/standards/`. A router holds no logic. A service raises, it
  never returns an error dictionary.
- A backend test creates and reads rows through the services or the API,
  never through `Model.save()` or `Model.find()` in the test body.
- New Svelte code uses runes and `lang="ts"`. A test renders the component
  through its props and asserts the DOM or the fetch calls.
- Verify sequence: section `Commands` of `CLAUDE.md`, plus `yarn build` for
  the frontend tasks.

## Task 1 — Backend: the `user_editable` flag

**Files:**
- Modify: `argus/backend/models/web.py` (`ArgusRelease`)
- Modify: `argus/backend/service/test_lookup.py` (`RELEASE_COLUMNS`)
- Modify: `argus/backend/service/release_manager.py` (`ReleaseEditPayload`,
  `edit_release`, `set_release_user_editable`)
- Modify: `argus/backend/controller/admin_api.py` (`EditReleaseRequest`,
  `SetReleaseUserEditableRequest`, `set_release_user_editable`)
- Test: `argus/backend/tests/admin_api/test_admin_release_api.py`

**Internals:** `ArgusRelease.user_editable: bool = False`.
`set_release_user_editable` follows `set_release_dormancy`.
`EditReleaseRequest.user_editable: bool = False`, and `edit_release` assigns
it. `POST /admin/api/v1/release/set_user_editable`, name
`admin.admin_api.set_release_user_editable`, admin only.

- [x] Write the failing tests: the switch round-trips through
  `/release/{id}/details`, `/release/edit` keeps the flag, `/api/v1/releases`
  carries it, and a non-admin gets 403 from the switch.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Backend: the cleanup service and the routes

**Files:**
- Create: `argus/backend/service/release_cleanup.py`
- Modify: `argus/backend/plugins/core.py` (`PluginModelBase.delete_run_data`)
- Modify: `argus/backend/plugins/sct/testrun.py` (`SCTTestRun.delete_run_data`)
- Modify: `argus/backend/controller/testrun_api.py` (`delete_run`)
- Modify: `argus/backend/controller/api.py` (`delete_test`, `delete_group`)
- Test: `argus/backend/tests/release_cleanup/test_release_cleanup_api.py`

**Internals:** `ReleaseCleanupError(Exception)`. `ReleaseCleanupService`
with `delete_group`, `delete_test`, `delete_run`, and the private
`_require_editable`, `_runs_of`, `_delete_test_cascade`,
`_delete_run_rows`, `_delete_test_results`. `_runs_of` unites
`plugin.model.find(build_id=...)` for every plugin with
`find(test_id=...)`, keyed by run id. `_delete_run_rows` removes the
comments, the events, the issue links, the run configuration rows and the
`RunConfigParam` rows they name, the cost, the pytest rows, the generic
result rows of the run under each metadata name, the four embedding tables,
then calls `plugin.model.delete_run_data(run.id)` and deletes the run.
`_delete_test_results` removes the generic result metadata, data and best
partitions and the graph views of the test. `delete_test` then calls
`ReleaseManagerService.delete_test`; `delete_group` cascades through the
tests and calls `ReleaseManagerService.delete_group`.
`PluginModelBase.delete_run_data` does nothing; `SCTTestRun` overrides it
for `SCTEvent` per severity, `SCTUnprocessedEvent`, `SCTNemesis`,
`SCTResource`, `StressCommand` and `SCTJunitReports`.
Routes: `DELETE /api/v1/test/{test_id}/run/{run_id}`
(`api.testrun_api.delete_run`), `DELETE /api/v1/test/{test_id}`
(`api.delete_test`), `DELETE /api/v1/group/{group_id}` (`api.delete_group`).

- [x] Write the failing tests: each route returns the error envelope and
  keeps the rows while the flag is off; a run removal drops the run, its
  comment, its event and its SCT events; a run of another test is refused;
  a test removal drops its runs and the test; a group removal drops its
  tests, their runs and the group; a generic run removal uses the default
  hook.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [ ] Commit, with the boxes of this task checked.

## Task 3 — Frontend: the confirmation modal and the sidebar

**Files:**
- Create: `frontend/Common/ConfirmDeleteModal.svelte`
- Create: `frontend/Common/ConfirmDeleteModal.test.ts`
- Modify: `frontend/WorkArea/Sidebar/sidebarState.svelte.ts` (`Release`,
  `#releaseFor`)
- Modify: `frontend/WorkArea/Sidebar/SidebarRow.svelte` (`onDelete`)
- Modify: `frontend/WorkArea/Sidebar/Sidebar.svelte` (`deleteTarget`,
  `deleting`, `confirmDelete`)
- Test: `frontend/WorkArea/Sidebar/Sidebar.test.ts`

**Internals:** `ConfirmDeleteModal` wraps `ModalWindow`; with
`confirmName` set, the danger button stays disabled until the input equals
it. `SidebarRow` renders a trailing trash button when `onDelete` is set,
`aria-label="Delete <name>"`. `Sidebar` passes `onDelete` for group and
test rows of a release with `user_editable`; `confirmDelete` sends the
`DELETE`, closes each open test the removal takes, reloads the list with
`force`, refreshes the stats, and reports through `sendMessage`.

- [x] Write the failing tests: the modal disables the button until the
  name matches and calls `onConfirm`/`onCancel`; the sidebar shows the
  buttons only on a flagged release; a confirmed test removal sends
  `DELETE /api/v1/test/<id>`, calls `onToggleTest` for an open test and
  refetches the tests; a group removal sends `DELETE /api/v1/group/<id>`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence and `yarn build`.
- [ ] Commit, with the boxes of this task checked.

## Task 4 — Frontend: the run selector

**Files:**
- Modify: `frontend/WorkArea/TestRunsSelector.svelte` (`deleteTarget`,
  `confirmRunDelete`)
- Modify: `frontend/WorkArea/TestRuns.svelte` (`handleRunDeleted`)
- Test: `frontend/WorkArea/TestRunsSelector.test.ts`

**Internals:** a trash button in the button group of an open run when
`testInfo.release?.user_editable`. `confirmRunDelete` sends
`DELETE /api/v1/test/<testId>/run/<runId>` and dispatches `runDeleted`.
`TestRuns` drops the id from `additionalRuns` and `clickedTestRuns`, then
`fetchTestRuns()`.

- [x] Write the failing tests: the button appears only with the flag and
  only on an open run; a confirmed removal sends the `DELETE` and
  dispatches `runDeleted`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence and `yarn build`.
- [ ] Commit, with the boxes of this task checked.

## Task 5 — Frontend: the admin switch and the editor

**Files:**
- Modify: `frontend/AdminPanel/ReleaseManager.svelte`
  (`handleReleaseUserEditableChange`, the switch)
- Modify: `frontend/AdminPanel/ReleaseEditor.svelte` (the checkbox)
- Test: `frontend/AdminPanel/ReleaseEditor.test.ts`

- [x] Write the failing test: the `releaseEdit` detail carries
  `user_editable`.
- [x] Run it and confirm the failure.
- [x] Write the smallest change that passes it.
- [x] Run the verify sequence and `yarn build`.
- [ ] Commit, with the boxes of this task checked.

## Task 6 — Documentation

**Files:**
- Modify: `docs/api_usage.md`

- [x] Describe the three `DELETE` routes, the flag, and the admin switch.
- [x] Run `uv run pre-commit run --all-files`.
- [ ] Commit, with the boxes of this task checked.
