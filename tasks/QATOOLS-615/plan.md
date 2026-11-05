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

**Files:** all new files are under `frontend/Views/Widgets/ReleaseSummary/`.
- Create:
  - `types.ts`: the response types
  - `summaryUtils.ts`: the pure helpers
  - `SummaryBar.svelte`: the stacked status bar
  - `SummaryTestList.svelte`: the test list of one version or of the family
  - `FamilyTimeline.svelte`: one row per version, the family row first
  - `FamilyGrid.svelte`: tests by version
  - `FamilyIssues.svelte`: open and fixed issues
  - `FamilySummary.svelte`: one family, with the tabs and the status filter
  - `ReleaseSummary.svelte`: loading, the refresh time, the stale note and
    the collapsed mode
  - `frontend/Common/flyout.ts`: the arc keyframes, the landing point and
    the two actions, `flyAlongArc` and `ping`
  - `frontend/Common/FlyoutLayer.svelte`: renders the flights and the
    landing pings
- Modify:
  - `frontend/Common/ViewTypes.js`: the `releaseSummary` entry, no settings
  - `frontend/ReleaseDashboard/ReleaseDashboard.svelte`: a collapsed
    accordion under the Issues one, and a test click that adds the test to
    the test popout through the release stats the dashboard already holds
- Test: `summaryUtils.test.ts`, `ReleaseSummary.test.ts`,
  `frontend/Common/flyout.test.ts`, `frontend/Common/FlyoutLayer.test.ts`

**Internals:**
- `ReleaseSummary` props: `{dashboardObject, dashboardObjectType, collapsible, onTestClick}`.
  - It fetches the release route or the view route.
  - `collapsible` renders an accordion item. Its header carries the newest
    three families with a compact bar each. The body renders on open.
- Each family block:
  - The header holds a toggle, the rollup bar (a segment click filters the
    family tests), the test totals and the issue badges.
  - The first family of a release starts open.
  - The tabs are Timeline and Grid. Beside them is a status filter: one
    coloured toggle per status, with a check or a cross and its count, as in
    the SCT events tab. "Show all statuses" appears once one is off.
  - The issue column reads the selected version on Timeline and the family
    on Grid. It stretches to the main column's height and scrolls inside.
- The Timeline tab:
  - One row per version, the family row first. Each row has a bar and one
    button per non-zero count, which selects that version and status.
  - Below the table, the test list of the selected row. A test name hands
    the test to `onTestClick` when one is set. The run number links to
    `/test/{build_id}/{build_number}`.
- The Grid tab:
  - Rows are the family tests under group header rows, filtered by their
    family result. Columns are the versions.
  - Each cell is a status badge with an icon, linked to its run, titled
    `<version>: <status>, run #<n>`.
- The issue list groups issues by tracker state through
  `isClosedInTracker` in `Common/IssueTypes.ts`: closed, done, duplicate and
  won't fix count as closed.
  - Each row has a line with the state pill (the shared colour and icon
    maps), the key and the one-line title.
  - Under it sits a line of badges: "on latest run" or "last seen <rcN>";
    then new or existing, and the short versions.
  - Rows on a latest run sort first. A row click expands the shared
    `IssueCard` with `aggregated` set, no delete and no current run.
- The backend entry adds `issue`: the issue's model dump with `subtype` and
  the links in scope, the shape `JiraService.resolve_issues` and
  `GithubService.resolve_issues` give with `aggregate_by_issue`.
- The family header is a grid with fixed name and bar columns, so the bars
  of every family line up whatever the version length. A click anywhere on
  the header toggles the family. A click on a bar segment opens the family
  with that filter instead of toggling it.
- Layout follows the dashboard's layering. The families sit in a rounded
  `bg-light-one` inset with `shadow-sm`, each family a `bg-white rounded
  shadow-sm` card with no border. Inside an open family:
  - another `bg-light-one` inset flows white cards with flexbox: the
    timeline, the test list or the grid, and the issues
  - each issue is a `bg-light-three` tile
- The flyout: a test click that adds a test to the popout also launches a
  flight.
  - `ReleaseDashboard` keeps the flights in `$state`, and `FlyoutLayer`
    renders each as a pill with the test name.
  - The pill flies on a quadratic arc from the cursor (from the button for a
    keyboard click) to the popout column. The landing point is clamped to
    the viewport, so a popout below the screen draws the pill to the bottom
    edge.
  - A ping ring marks the landing.
  - Under `prefers-reduced-motion` only the ping shows. No animation API
    (jsdom) lands at once.
- Badges use the existing `StatusBadgeCSSClassMap` class pairs. Svelte 5
  runes, no `svelte/legacy` imports.

- [x] Write the failing tests:
  - [x] the helpers: status groups, bar segments, "updated ago", issue
    versions, grid rows and the grid filter
  - [x] the timeline lists the family row first, then the versions in order
  - [x] a version click and a count click narrow the test list, and the
    status filter widens it again
  - [x] a test click goes to `onTestClick`, and the run link stays
  - [x] the Grid tab shows a cell per version with its title, and the
    family issues
  - [x] the issues group into open and fixed, with state, tests and versions
  - [x] the collapsed mode shows the families in the header and opens on click
  - [x] a click anywhere on a family header toggles it, and a bar segment
    opens it with its filter
  - [x] each status toggles on its own, and "Show all statuses" resets them
  - [x] the issues group by tracker state, and each says whether it is on a
    latest run, with no regression flag on closed issues
  - [x] an issue row expands into the issue card in aggregated mode, without
    "Add to current run"
  - [x] `isClosedInTracker` and `shortVersion`
  - [x] backend: each issue entry carries the issue with its links in scope
  - [x] the view route names each release
  - [x] the stale note and the empty state
  - [x] the arc starts at the cursor, ends at the target and bends up; a
    short hop lifts less; the landing point clamps to the viewport
  - [x] the flyout layer shows the flight's label at the cursor and reports
    the landing
- [x] Run them and confirm the failure.
- [x] Write the components, the registry entry and the dashboard wiring.
- [x] Run `yarn test`, `yarn build`, `svelte-check` on the widget folder and
  the verify sequence.
- [x] Check the dashboard at 1600 and 900 pixels on the dev instance:
  collapsed, timeline, a count filter, the grid.
- [x] Check on the dev instance that the family bars of `enterprise-2024.1`
  share their edges, and that a click on a summary test flies a pill and
  adds the test to the popout.
- [x] Commit, with the boxes of this task checked.

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
