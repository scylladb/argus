# QATOOLS-615 — implementation plan

**Spec:** `tasks/QATOOLS-615/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- **Backend tests** live in `argus/backend/tests/release_summary/` and need
  Docker.
  - They create releases, tests, runs, plans and issue links through the
    services or the API: `ReleaseManagerService`, `ClientService`,
    `PlanningService`, `IssueService` with mocked remote clients.
  - They read the summary through `ReleaseSummaryService.get` or the routes.
  - No `Model.save()` or `Model.find()` in a test body. The one exception is
    the static timestamps in the race test, which have no service entry
    point.
- **Imports** go at the top of the module.
- **Comments:** no prose comments that justify the change.
- **The verify sequence** is section `Commands` of `CLAUDE.md`:
  `uv run pre-commit run --all-files`, `uv run pytest`, `yarn test`,
  `yarn build`.
- **Hooks never fail the action they sit in.**
  `mark_release_summary_stale` logs and swallows a driver error, like
  `invalidate_release_snapshots`.

## Task 1 — Version parsing

**Files:**
- Create: `argus/common/versions.py`
- Test: `argus/backend/tests/release_summary/test_versions.py` (no Docker)

**Internals:**
- `VERSION_RE`.
- `ScyllaVersion(base, pre)`, a frozen dataclass:
  - `__str__` gives `base` or `base~pre`.
  - `family` is the property `base`.
  - `sort_key()` gives `(base as an int tuple, rank)`. The rank is
    `0` for dev, `1 + n` for rcN, and a large constant for the final build.
- `parse_version(raw) -> ScyllaVersion | None`.

- [x] Write the failing tests:
  - [x] Every row of the spec's version table.
  - [x] The order `~dev < ~rc0 < ~rc2 < ~rc10 < final`.
  - [x] Families sort by number: `2025.1.10 > 2025.1.9`.
  - [x] `None`, `""` and `"master"` return `None`.
- [x] Run them and confirm the failure.
- [x] Write `versions.py`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Table and stale mark

**Files:**
- Create: `argus/backend/models/release_summary.py`
- Modify:
  - `argus/backend/models/web.py`: import the model, add it to
    `USED_MODELS`, call the stale mark inside `invalidate_release_snapshots`
- Test: `argus/backend/tests/release_summary/test_hooks.py`

**Internals:**
- `ReleaseSummary(Document)` with `Settings.name = "release_summary_v1"`:
  - keys: `release_id` (`PrimaryKey`), `family` and `version`
    (`ClusteringKey`)
  - static columns: `invalidated_at`, `generated_at`
    (`Annotated[Optional[datetime], Static()]`)
  - `payload: str`
- `async def mark_release_summary_stale(*release_ids: UUID | None) -> None`:
  - Writes `ReleaseSummary.find(release_id=id).update(invalidated_at=now)`
    for each distinct id that is not None.
  - Catches `DriverException` and `NoHostAvailable` and logs a warning.

- [x] Write the failing tests:
  - [x] Posting a comment through `TestRunService` makes the partition stale.
- [ ] Run them and confirm the failure.
- [x] Write the model, the helper and the hook in `invalidate_release_snapshots`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — `ReleaseSummaryService`

**Files:**
- Create: `argus/backend/service/release_summary.py`
- Modify: `argus/backend/plugins/core.py`: `PluginModelBase.get_summary_rows_for_release`
- Test: `argus/backend/tests/release_summary/test_release_summary.py`

**Internals:**
- `SUMMARY_COLUMNS = ("id", "build_id", "start_time", "test_id", "group_id", "status", "build_number", "scylla_version")`.
- `PluginModelBase.get_summary_rows_for_release(release_id) -> list[dict]`
  calls `select_rows(cls.find(release_id=...), *SUMMARY_COLUMNS)`.
- `ReleaseSummaryService`:
  - `get(release_id, test_ids=None) -> dict` follows the spec's sequence
    diagram:
    - It reads the partition. The partition is stale when it has no rows,
      or when `invalidated_at > generated_at`.
    - When stale, it awaits `_recompute(release_id)` through a per-process
      `dict[UUID, asyncio.Task]` that joins concurrent callers.
    - It builds the response and filters it when `test_ids` is set.
  - `get_for_view(view_id) -> dict`:
    - Calls `UserViewService().resolve_view_tests(view_id)` and groups the
      test ids by `release_id`.
    - Calls `get` for each release, sorted by release name.
  - `_recompute(release_id) -> list[dict]`:
    - Takes `started_at` before the reads.
    - Gathers the runs of every plugin in `all_plugin_models()`, plus the
      tests, groups, plans and `IssueLink` rows of the release, the Jira and
      GitHub issues of those links, and every link of each of those issues,
      to find its earliest link.
    - Calls `build_summaries(...)`.
    - Writes each row with
      `find(release_id, family, version).update(payload=..., generated_at=started_at)`.
    - Deletes the rows it read that are gone.
    - Never deletes the partition: a partition delete would also erase a
      newer `invalidated_at`.
  - `build_summaries(runs, tests, groups, plans, links, issues) -> dict[(family, version), Summary]`
    is a pure function. It holds the count and rollup rules of the spec.
  - `filter_summary(summary, test_ids) -> Summary` keeps the tests and
    issues within `test_ids` and recounts.
  - Failure handling follows the spec's failure table:
    - If the recompute raises and rows exist, it returns the stored rows
      with `stale: true`.
    - If the write raises, it returns the computed rows.

- [x] Write the failing tests:
  - [x] Runs on `~rc0`, `~rc1` and the final build give the version rows
    and the rollup, with all counts.
  - [x] A test is counted once, by its latest run on the version.
  - [x] A disabled test is left out.
  - [x] A plan targeting `X.Y.Z~rc1` makes its unrun tests pending on rc1,
    and in the rollup only when they never ran in the family.
  - [x] A group in a plan expands to its enabled tests.
  - [x] A planned version with no runs shows up, all pending.
  - [x] A Jira issue first linked on rc1 is new on rc1 and existing on rc2.
    In the rollup it is new.
  - [x] An issue first linked in an earlier family is existing everywhere.
  - [x] A GitHub issue follows the same new-or-existing rule.
  - [x] An issue on rc1 whose test re-ran on rc2 to a final status without
    it is `fixed` in the rollup. The same issue still linked on the latest
    run is `open`.
  - [x] `test_ids` filtering drops other tests and issues and recounts.
  - [x] A run whose version does not parse is left out.
  - [x] Second read with no change: no recompute. Assert that
    `generated_at` is unchanged.
  - [x] Race: set `invalidated_at` after `started_at`, during a recompute
    (patch `build_summaries` to write the mark). The next read recomputes.
- [ ] Run them and confirm the failure.
- [x] Write the plugin method and the service.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 4 — Staleness hooks

**Files:**
- Modify:
  - `argus/backend/plugins/core.py` `invalidate_release_snapshot`: call
    `mark_release_summary_stale(self.release_id)`
  - `argus/backend/service/client_service.py`: `update_run_status`,
    `submit_product_version` and `finish_run`, each after `run.save()`
  - `argus/backend/service/testrun.py` `terminate_stuck_runs`: once per
    distinct release
  - `argus/backend/plugins/sct/service.py`: `submit_packages` after an
    applied update, and the Gemini and perf auto-fail after `run.save()`
  - `argus/backend/service/release_manager.py` `move_test_runs`: the old
    releases and the new one
  - `argus/backend/service/replay_service.py`: the backfill, the old release
    and the new one
- Test: `argus/backend/tests/release_summary/test_hooks.py`

- [x] Write the failing tests. Each one reads the summary, acts through the
  service, then reads again and sees the change:
  - [x] client status update to `running`, then `failed`
  - [ ] finish through `ClientService.finish_run`. Not written: an SCT
    finish changes no status, so the summary shows no difference
  - [x] product version submit, so the run moves to the version row
  - [x] SCT package submit with a `scylla-server-target` package
  - [ ] stuck-run sweep, so the run moves to `aborted`. Not written: the
    sweep aborts every stale run of the shared test database, and no service
    sets a heartbeat in the past
  - [x] moving a test to another group: the next read shows the new group.
    `batch_move_tests` keeps the release of a test, so a move between
    releases has no service path to test
  - [x] Jira link and unlink: the issue counts appear and disappear
- [x] Run them and confirm the failure.
- [x] Add the hook calls.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 5 — API routes

**Files:**
- Modify: `argus/backend/controller/api.py`:
  `GET /release/{release_id}/version_summary`, name `api.release_version_summary`
- Create: `argus/backend/controller/views_widgets/release_summary.py`:
  `GET /widgets/release_summary`, name
  `api.view_api.release_summary.get_release_summary`
- Test: `argus/backend/tests/release_summary/test_release_summary_api.py`

- [x] Write the failing tests:
  - [x] The release route returns the contract's shape for a seeded
    release: families newest first, versions in order.
  - [x] An unknown release gives `status: error`.
  - [x] The view route on a view of one test counts only that test.
  - [x] A view across two releases gives two release objects.
  - [x] An unknown view gives `status: error`.
- [ ] Run them and confirm the failure.
- [x] Write both routes. Each uses `Depends(api_current_user)` and
  `APIResponse`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 6 — Frontend widget

**Files:**
- Create: `frontend/Views/Widgets/ReleaseSummary/ReleaseSummary.svelte`
- Create: `frontend/Views/Widgets/ReleaseSummary/ReleaseSummaryCounts.svelte`
- Modify: `frontend/Common/ViewTypes.js`: the `releaseSummary` entry, no
  settings
- Modify: `frontend/ReleaseDashboard/ReleaseDashboard.svelte`: a fixed
  section after the release stats
- Test: `frontend/Views/Widgets/ReleaseSummary/ReleaseSummary.test.ts`

**Internals:**
- Props are `{dashboardObject, dashboardObjectType}`. The component fetches
  the release route or the view route from them.
- Layout:
  - One card per release, holding one block per family.
  - Each family block shows the rollup counts as Bootstrap badges, each with
    its own `background-color` and `color` pair.
  - A collapsible table lists the family's versions, one row of counts each.
  - The rollup's issue list links to the tracker and marks each issue as
    new, existing or fixed.
  - A count with tests behind it expands to the list of those tests, each
    linked to its run.
- Svelte 5 runes, with no `svelte/legacy` imports.

- [x] Write the failing tests:
  - [x] It renders a family with its rollup and the versions in order.
  - [x] The issue states are shown.
  - [x] It calls the view URL for `dashboardObjectType="view"` and the
    release URL for `"release"`.
  - [x] It shows an empty state when there are no families.
- [ ] Run them and confirm the failure.
- [x] Write the components, the registry entry and the dashboard section.
- [x] Run `yarn test`, `yarn build` and the verify sequence.
- [ ] Commit, with the boxes of this task checked.

## Task 7 — Docs

**Files:**
- Create: `docs/release_summary.md`. It covers what each number counts, the
  version and family rules, the rollup and the fixed rule, new versus
  existing, and when the summary refreshes.
- Modify:
  - `docs/api_usage.md`: the two routes
  - `docs/project/architecture.md`: the summary table and its staleness
  - `docs/INDEX.md`: the reference entry

- [x] Write the docs.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 8 — Live check on the dev cluster

- [x] Run `sync-models` against `argus_tablets`.
- [x] Open `/dashboard/scylla-2025.1`. Compare the `2025.1.0` family with a
  cqlsh count of `scylla-2025.1` runs: the latest run per test on each of
  `~rc0` to `~rc4` and on `2025.1.0`.
- [x] Add the widget to a view with a few tests of `scylla-2025.1`, and
  confirm that it counts only those tests.
- [ ] Change a run's status from the UI, reload, and see the count move.
  Covered by `test_a_status_change_from_the_ui_shows_on_the_next_read`
  instead of a click on the dev instance
- [x] Check the page at two widths, as the responsive standard asks.
