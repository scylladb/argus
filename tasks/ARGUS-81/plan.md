# ARGUS-81 — implementation plan

**Spec:** `tasks/ARGUS-81/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Follow `docs/standards/`. These apply most:
  - frontend: `components.md`, `css.md`, `accessibility.md`, `responsive.md`;
  - backend: `api.md`, `models.md`, `migrations.md`;
  - testing: `test-writing.md`;
  - global: `minimal-implementation.md`.
- Every import goes at the top of the module.
- Comments explain only what the code cannot. No comment or docstring says
  why something changed.
- Backend tests create and read rows through services or the API, never
  `Model.save()` or `Model.find()` in the test body. They need Docker.
- Frontend:
  - New components use runes and typed props.
  - No `querySelector`. Reach Bootstrap widgets through an action.
  - Sort with `toSorted()` inside `$derived`. `.sort()` on a `$state` proxy
    throws.
  - Every status mark sets `background-color` and `color` together, and
    never uses color alone.
- Stage files by explicit path only.
- Commit subjects are `feature(<scope>): …`, `fix(<scope>): …` or
  `docs(<scope>): …`, with `Task: ARGUS-81` as the last line and no co-author
  trailer.
- The code stays uncommitted until Komachi has reviewed it. After the review,
  the docs go in their own commits and the code in one commit per scope, as
  Komachi chose; each task's last box names the commits that hold it.
- Verify sequence, from `CLAUDE.md`:
  1. `uv run pre-commit run --all-files`
  2. `uv run pytest`
  3. `yarn test`
  4. `yarn build`, for the frontend tasks
  5. `cd cli && make fmt && make lint && go test -race ./...`, for Task 2

## Task 1 — Release priority and release order

**Files:**
- Modify:
  - `argus/backend/models/web.py:164-177` (`ArgusRelease`)
  - `argus/backend/service/argus_service.py:130-134` (`get_releases`)
  - `argus/backend/util/common.py`: `version_key`
  - `argus/backend/controller/admin_api.py:42-49` (`EditReleaseRequest`; `pretty_name` becomes optional, because a release without one could not be edited and so could not get a priority)
  - `argus/backend/service/release_manager.py:16-23,182-195` (`ReleaseEditPayload`, `edit_release`)
  - `frontend/AdminPanel/ReleaseEditor.svelte:29-70`
- Test:
  - `argus/backend/tests/admin_api/test_admin_release_api.py`
  - `argus/backend/tests/api/test_release_api.py`
  - `argus/backend/tests/test_release_order.py` (new, unit)

**Internals:**
- **`ArgusRelease`:** gains `priority: int = 0`.
- **`version_key(name: str) -> tuple`:** a module function in
  `argus/backend/util/common.py`, because `test_lookup` cannot import
  `argus_service` without a cycle. It splits the name with `re.split(r"(\d+)", name)`. A
  text chunk becomes `(0, chunk.lower(), 0)` and a digit chunk becomes
  `(1, "", -int(chunk))`.
- **`release_sort_key(release)`:** returns
  `(release.dormant, -(release.priority or 0), version_key(release.name))`.
  `get_releases` uses it.
- **`EditReleaseRequest.priority`:** typed `int | None = None`.
- **`ReleaseEditPayload` and `edit_release`:** `ReleaseEditPayload.priority`
  is `int | None`, and `edit_release` sets
  `release.priority = payload.get("priority") or 0`.
- **`ReleaseEditor.svelte`:** a `form-group` with a labelled
  `<input type="number" min="0" class="form-control" bind:value={releaseData.priority}>`,
  labelled "Priority (higher is listed first)".

- [x] Write the failing tests:
  - `version_key` orders `scylla-2026.3 < scylla-2025.1`, `manager-3.12 < manager-3.9`, `enterprise-2024.1 < enterprise-2024.1/releng-testing`.
  - `release_sort_key` on `SimpleNamespace(priority=None, dormant=False, name=…)` sorts like priority 0.
  - an admin edit with `"priority": 5` makes `/api/v1/release/{id}/details` return 5, and `"priority": null` stores 0.
  - `GET /api/v1/releases` lists a priority-10 release first and a dormant release after every non-dormant one.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run `uv run python -m argus.backend.cli sync-models` against the dev DB.
- [x] Run the verify sequence.
- [x] Committed in 7e9fd00d `feature(release)`.

## Task 2 — Search index, query parser and paged search

**Files:**
- Modify:
  - `argus/backend/service/test_lookup.py` (all of `test_lookup`, `make_single_run_response:84-101`)
  - `argus/backend/controller/planner_api.py:53-66`
  - `argus/backend/controller/view_api.py:134-147`
  - `argus/backend/service/views.py:98-99`
  - `argus/backend/tests/conftest.py`: an autouse fixture
  - `cli/cmd/search/root.go:31-43`: the help text
  - `cli/internal/models/planner.go`: the `SearchResponse` comment on `total`
- Test:
  - `argus/backend/tests/test_query_parser.py` (new, unit)
  - `argus/backend/tests/planner_api/test_planner_api.py`
  - `argus/backend/tests/view_api/test_view_api.py`

**Internals:**
- **`TestLookup.__test__ = False`.**
- **`ParsedQuery` and `parse_query`:** the frozen dataclass and the function
  from the spec, using these helpers:
  - `_tokenize(query)` walks the characters. A double quote toggles phrase
    mode, and an unbalanced quote runs to the end of the query.
  - A `-` prefix negates, unless the token is made only of dashes.
  - `release:`, `group:` and `type:` become facets. Any other `key:value`
    stays a term.
  - `_job_path(token)` turns `http(s)://host/job/a/job/b/` into `a/b`.
  - A query made of one token that parses as a UUID sets `uuid`.
- **`IndexEntry` and `SearchIndex`:**
  - `IndexEntry` is a `@dataclass(slots=True, frozen=True)` with `id, type,
    name, pretty_name, release_id, group_id, build_system_id, enabled,
    test_metadata, haystack`.
  - `SearchIndex` holds `entries: list[IndexEntry]`,
    `by_id: dict[UUID, IndexEntry]`, `releases: dict[UUID, dict]`,
    `groups: dict[UUID, dict]` and `built_at: float`.
  - The release refs carry `priority` and `dormant`.
- **The index builder.** `_build_index()` makes three scans:
  - `ArgusRelease.find().all()`.
  - `ArgusGroup.find().only(...)`, without `description` and `assignee`.
  - `ArgusTest.find().only(...)`, without `description`, `assignee`,
    `build_system_url` and the plugin fields.
  - `asyncio.to_thread` builds the entries.
- **Index access.**
  - `INDEX_TTL = 60` sets the index lifetime in seconds.
  - `_get_index()` creates the lock lazily, keyed by `id(asyncio.get_running_loop())`, and rebuilds the index when it is stale.
  - `clear_index()` drops the index.
- **Matching and ranking:**
  - `_matches(entry, parsed, index)` applies terms, excluded terms, facets
    (same key OR, different keys AND) and the `enabled` and parent-`enabled`
    visibility rule. With `releaseId`, release entries are skipped.
  - `_rank_key(entry, parsed, index)` returns
    `(tier, type_order, dormant, -priority, version_key(display), str(id))`.
  - `_to_hit(entry, index)` builds the hit shape from the spec.
- **`test_lookup(query, release_id=None, limit=None, offset=0) -> tuple[list[dict], int]`:**
  - It resolves a UUID query through `by_id` first, then runs the existing
    run lookup.
  - Without `limit`, it prepends the "Add all..." row.
  - The total is the match count.
- **`make_single_run_response`:** it sets `run["name"]` only when the test
  resolves. Otherwise the name is `#<build_number>`.
- **Routes:**
  - `planner_api.search_tests` gains `limit: int | None = Query(None, ge=1)`
    and `offset: int = Query(0, ge=0)`.
  - `views.UserViewService.test_lookup` and `view_api.search_tests` unpack
    `(hits, total)`.
- **Fixture:** an autouse fixture `_clear_search_index` calls
  `TestLookup.clear_index()`. It imports through
  `from argus.backend.service import test_lookup as lookup`.

- [x] Write the failing tests.
  - Parser:
    - `release:"scylla 5.4"` strips the quotes;
    - `release:scylla-2025.1/releng-testing` keeps the `/`;
    - `longevity 50gb` makes two terms;
    - `-azure` excludes;
    - `-- root directory --` makes three plain terms;
    - a repeated `release:` ORs;
    - a Jenkins URL becomes its job path;
    - a UUID query sets `uuid`;
    - an unbalanced quote does not raise.
  - `planning/search`:
    - the unpaged response starts with "Add all..." and its fields match the CLI `SearchHit`;
    - `limit=2&offset=0` and `limit=2&offset=2` return disjoint hits with no special row, and `total` is the match count;
    - an exact name match ranks first;
    - a test in a priority-10 release ranks above the same name elsewhere;
    - `releaseId` scopes the results;
    - a test UUID query returns that test;
    - a group created after one search shows up after `clear_index()`.
  - `/api/v1/views/search` still returns `hits` and `total`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Update the CLI help text: quoted facet values, AND terms, `-` exclusion, job paths and URLs, entity UUIDs.
- [x] Time the search against the dev DB, cold and warm, for `longevity-50gb` and `-` with `limit=30`, and note the numbers for the PR body.
- [ ] Run the verify sequence, the CLI commands included. Open: golangci-lint is not installed here, so `make lint` did not run; gofmt, `go vet` and `go test -race` pass.
- [x] Committed in cda3f21d `feature(search)` and 414e922a `improvement(cli/search)`.

## Task 3 — Release stats summary route

**Files:**
- Modify:
  - `argus/backend/service/stats.py`: add `summarize_release_stats` after `ReleaseStatsCollector`
  - `argus/backend/controller/api.py:444-462`: the new route next to `release_stats_v2`
- Test:
  - `argus/backend/tests/test_stats_summary.py` (new, unit)
  - `argus/backend/tests/api/test_release_api.py`

**Internals:**
- **`summarize_release_stats(stats: dict) -> dict`:**
  - It returns `{"dormant": True}` unchanged.
  - Otherwise `_counts(d)` copies `total` and every `TestStatus` value, read with `str(key)`, because a fresh dict has enum keys and a snapshot has string keys.
  - It adds `to_investigate`: the sum of `failed`, `test_error` and `error` from `d.get("not_investigated", {})`, for the release and for each group.
- **Test entries.** Each test entry keeps `status` and `investigation_status`
  as strings. `start_time` is `None` when `last_runs` is empty. Otherwise it
  is the ISO string, and a `datetime` is encoded the same way
  `util/encoders.py` encodes one.
- **`release_stats_summary(release, force)`:** the route
  `GET /release/stats/summary`, named `api.release_stats_summary`. It calls
  `collect(limited=False, force=force, include_no_version=True)`, then
  `summarize_release_stats`.

- [x] Write the failing tests:
  - a snapshot-shaped dict (string keys, ISO `start_time`) and a fresh dict (enum keys, `datetime`) produce the same summary;
  - a test with an empty `last_runs` gets `start_time: None`;
  - a group without `not_investigated` gets `to_investigate: 0`;
  - dormant passes through;
  - the route returns the summary for the session `release` fixture.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Compare the bytes of `stats/v2` and `stats/summary` for scylla-master on the dev DB, and time a cold summary with `force=1`.
- [x] Run the verify sequence.
- [x] Committed in 976b4163 `feature(stats)`.

## Task 4 — Sidebar state, sort and status summary

**Files:**
- Modify: `package.json`, `yarn.lock` (`yarn add --exact svelte-multiselect@11.8.0`)
- Create:
  - `frontend/WorkArea/Sidebar/sidebarState.svelte.ts`
  - `frontend/WorkArea/Sidebar/sidebarSort.ts`
  - `frontend/WorkArea/Sidebar/StatusSummary.svelte`
- Test:
  - `frontend/WorkArea/Sidebar/sidebarState.test.ts`
  - `frontend/WorkArea/Sidebar/sidebarSort.test.ts`
  - `frontend/WorkArea/Sidebar/StatusSummary.test.ts`

**Internals:**
- **`sortTests(tests, stats) -> Test[]`.** It uses `toSorted`, ordering by
  `StatusSortPriority[stats?.tests?.[id]?.status] ?? StatusSortPriority.none`
  and then by display name.
- **`displayName(entity)`.** Returns `pretty_name || name`.
- **`duplicateNames(items) -> Set<string>`.**
- **`class SidebarState`:**
  - Navigation:
    - `releases = $state([])`
    - `location = $state({release: null, group: null})`
    - `enterRelease(release)`, `enterGroup(group)`, `up()`
  - Caches:
    - `groups = new SvelteMap()`, keyed by release id
    - `tests = new SvelteMap()`, keyed by group id
    - `groupAssignees = new SvelteMap()`
    - `testAssignees = new SvelteMap()`
    - `stats = new SvelteMap()`, keyed by release name, with values
      `{data, fetchedAt, error, promise}`
  - Fetchers:
    - `loadReleases()`, `loadGroups(release, {force})` and
      `loadTests(group, {force})`. Each records an error state.
    - `ensureStats(release, {force})`. `STATS_TTL = 300_000`. It skips
      dormant releases and dedupes on `promise`.
  - Prefetch:
    - `limiter`: a small queue that runs at most 2 tasks at a time.
    - `prefetch(release)` replaces any pending prefetch with a 150 ms timer
      for this release. `cancelPrefetch()` drops it, and the list calls it on
      `pointerleave`. A row never calls back on `blur` or `pointerleave`:
      Chrome fires `blur` while a clicked row is torn down, and the row's
      callback props then read as a Svelte sentinel.
    - `loadEager()` sends every release with `priority > 0` through the
      limiter.
- **`StatusSummary.svelte`:**
  - Props: `stats` and `compact = false`.
  - Segments follow `StatusSortPriority` order, sized `count / total * 100%`.
    They are coloured with `StatusBackgroundCSSClassMap` and skipped when
    the count is zero.
  - It shows a count with an icon (`svelte-fa`) for failed (failed +
    test_error + error), running and passed, plus a `faMagnifyingGlass`
    badge for `to_investigate`.
  - It carries `role="img"` and an `aria-label` that lists every non-zero
    status and the total.

- [x] Write the failing tests:
  - `sortTests` puts failed before passed before not_run, and re-sorts when stats change;
  - `ensureStats`:
    - two concurrent calls send one fetch;
    - a second call inside the TTL sends none;
    - `force` sends `force=1`;
    - a dormant release sends none;
    - a rejected fetch sets `error` and clears `promise`;
  - the limiter never runs more than 2 at once;
  - `StatusSummary` renders one segment per non-zero status and the expected aria-label, and renders nothing for `total: 0`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Committed in e52823a9 `feature(workspace)`.

## Task 5 — Sidebar components, drawer, and the panel without search

**Files:**
- Create:
  - `frontend/WorkArea/Sidebar/Sidebar.svelte`
  - `frontend/WorkArea/Sidebar/SidebarRow.svelte`
  - `frontend/WorkArea/Sidebar/SidebarSearch.svelte`
  - `frontend/WorkArea/Sidebar/offcanvas.ts`
- Modify:
  - `frontend/WorkArea/WorkArea.svelte` (all)
  - `frontend/WorkArea/TestRunsPanel.svelte:1-111`
  - `svelte.config.js`: skip the TypeScript script preprocessor for files under `node_modules`. Without a tsconfig there, it drops imports that only the markup uses, such as `highlight_matches` in svelte-multiselect. The Svelte 5 compiler strips their type annotations itself.
- Delete:
  - `frontend/WorkArea/RunRelease.svelte`
  - `frontend/WorkArea/RunGroup.svelte`
  - `frontend/WorkArea/Test.svelte`
- Test:
  - `frontend/WorkArea/Sidebar/Sidebar.test.ts`
  - `frontend/WorkArea/Sidebar/SidebarSearch.test.ts`

**Internals:**
- **`offcanvas(node)` action.** It calls `Offcanvas.getOrCreateInstance(node)`
  and returns `destroy`. It exports `hideDrawer(node)`.
- **`Sidebar.svelte`.**
  - Props:
    - `openTests: string[]`
    - `onToggleTest(testId)`
    - `onOpenTest(testId)`
    - `onOpenTests(ids)`
    - `onOpenRun(testId, runId)`
  - **Layout.**
    - Outer markup: `<aside class="offcanvas-md offcanvas-start" id="workspace-sidebar" tabindex="-1" use:offcanvas>`.
    - It wraps an inner `<nav aria-label="Workspace">`, which carries the
      background and border.
    - The nav holds, in order: the search, `<nav aria-label="breadcrumb"><ol class="breadcrumb">`, the level header, then the `<ul>` list.
    - A fixed button `d-md-none position-fixed bottom-0 start-0 m-3` uses
      `data-bs-toggle="offcanvas"` and `data-bs-target="#workspace-sidebar"`.
      It has an `aria-label` and the `faBars` icon.
  - **Focus.** `activeId` names the row with `tabindex="0"`. `focusRow(index)`
    sets `activeId` and bumps `focusRequest`, and the active row focuses its
    own button in an `$effect`. A keyed `each` that binds button refs through
    a prop loses them when rows are torn down.
  - **Keyboard.** Each row passes `onkeydown` up:
    - ArrowUp, ArrowDown, Home and End move `activeIndex`.
    - Enter and ArrowRight call `activate(item)`.
    - ArrowLeft and Backspace call `up()` and restore the focus to the
      parent row through `lastIndexByLevel`.
  - **`/` shortcut.** `<svelte:window onkeydown>` handles `/`. It ignores
    keys with a modifier held, and keys typed into an `input`, `textarea`,
    `select` or `isContentEditable` element.
  - **Drawer.**
    - On `shown.bs.offcanvas`, focus moves to the search.
    - `hideDrawer` runs when a test opens.
  - **Level header.**
    - Release level: a Dashboard link `/dashboard/{name}`, and Refresh, which calls `ensureStats(force)` and `loadGroups(force)`.
    - Group level: "Open all tests", which calls `onOpenTests`, and Refresh.
  - **Desktop-only styles.** The sticky positioning and a fixed
    `height: calc(100vh - 2rem)` live inside `@media (min-width: 768px)`; the
    runs panel gets the same `min-height`, so neither column jumps while a list
    loads.
- **`SidebarRow.svelte`.**
  - Props: `kind`, `name`, `active`, `pressed`, `subtitle`, `stats`,
    `statsLoading`, `statsError`, `status`, `startTime`, `pinned`, `dormant`,
    `assignees`, `focusRequest`, `onActivate`, `onKeydown`, `onFocus`,
    `onHover`.
  - It renders a single `<button>` with `tabindex={active ? 0 : -1}`, and
    `aria-pressed` on test rows.
  - Releases show a `text-bg-secondary` "dormant" badge and a pin toggle, a
    sibling `<button>` with `aria-pressed`, a fixed label and `tabindex` 0
    only on the active row.
  - Tests show a status dot with a `visually-hidden` status label, and
    `timestampToISODate(start_time)` only when `start_time` is set.
- **`SidebarSearch.svelte`.**
  - Props: `scopeRelease`, `onPick(hit)`.
  - It keeps `scopeAll = $state(false)`, which resets when `scopeRelease`
    changes.
  - `{#key scopeKey}` wraps `<MultiSelect maxSelect={1} loadOptions={{fetch: loadHits, debounceMs: 200, batchSize: 30, onOpen: false}} bind:selected onadd={...}>`.
  - `loadHits({search, offset, limit})` fetches `/api/v1/planning/search` with
    `releaseId` when scoped. It maps each hit to
    `{...hit, label: displayName(hit), value: hit.id}` and returns
    `{options, hasMore: offset + hits.length < total}`.
  - Snippets:
    - `option` renders a type badge, the label and the muted
      `release / group` path.
    - `beforeInput` renders the "in <release> ×" chip.
  - Styling: the `--sms-*` variables point at `var(--bs-body-bg)`,
    `var(--bs-border-color)` and `var(--bs-body-color)`.
- **Hit routing.** `routeHit(state, hit, callbacks)` is a pure function in
  `sidebarState.svelte.ts`:
  - `release` calls `enterRelease`.
  - `group` resolves its release from `state.releases`, then calls `enterGroup`.
  - `test` enters its group and calls `onOpenTest`.
  - `run` enters the group of `hit.test` and calls `onOpenRun`.
- **`WorkArea.svelte`.**
  - State: `testRuns` and `additionalRuns` are `$state`.
  - `pushUrl()` holds the existing `stateEncoder` + `pushState` code.
  - Handlers: `toggleTest`, `openTest`, `openTests`, `openRun`.
  - Layout: `d-md-flex gap-3`. The sidebar is a `col-md-4 col-xl-3` column
    and the panel a `flex-grow-1 min-w-0` column.
  - It keeps `onpopstate`.
- **`TestRunsPanel.svelte`.**
  - Remove `SearchBar`, `handleSearch`, `fetchGroupTests`, `handleGridSelect`,
    `selectingFromGrid`, `release`, the `ModalWindow` and
    `ReleasePlannerGridView` block, and their imports.
  - `additionalRuns = $bindable({})`.

- [x] Write the failing tests, with `fetch` mocked per URL and `userList` stubbed:
  - clicking a release shows its groups and the breadcrumb `Releases › <release>`;
  - ArrowDown then Enter drills into a group;
  - ArrowLeft returns, and the group row has focus;
  - the breadcrumb button returns to Releases;
  - a test row toggles `onToggleTest` and carries `aria-pressed`;
  - two groups with the same `pretty_name` show their raw names;
  - a test with `start_time: null` shows no date;
  - `/` typed in a textarea does not move the focus;
  - `routeHit` handles a release, a group, a test and a run;
  - `loadHits` passes `releaseId` only when scoped, and computes `hasMore`.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run `yarn build` and drive `/workspace` in headless Chrome:
  - at 1600×1000 and at 390×844, in light and in dark;
  - the keyboard round trip, the breadcrumbs, and the search hits for
    `longevity-50gb`, `release:"scylla-master"`, a job path and a Jenkins URL;
  - the drawer opens from the bottom-left button, closes on opening a test,
    and returns focus;
  - `scrollWidth === innerWidth` on mobile;
  - no 1970 dates.
- [x] Run the verify sequence.
- [x] Committed in e52823a9 `feature(workspace)`.

## Task 6 — Release pins and multi-pick search

**Files:**
- Modify:
  - `frontend/WorkArea/Sidebar/sidebarSort.ts`
  - `frontend/WorkArea/Sidebar/sidebarState.svelte.ts`
  - `frontend/WorkArea/Sidebar/SidebarRow.svelte`
  - `frontend/WorkArea/Sidebar/Sidebar.svelte`
  - `frontend/WorkArea/Sidebar/SidebarSearch.svelte`
- Test: the four `frontend/WorkArea/Sidebar/*.test.ts` files

**Internals:**
- **`pinnedFirst(items, pinned)`:** lifts the pinned items and keeps the order
  within each part.
- **`SidebarState.pinned`:** a `SvelteSet` read from
  `localStorage["argus-workspace-pinned-releases"]` (`PINS_KEY`).
  `togglePin(release)` writes it back, inside try/catch, and queues the stats
  of a newly pinned release. `loadEager` includes pinned releases.
- **Sidebar focus:** `pending = {id, move}`. A search pick navigates with
  `move: false`, which marks the row active without a focus request, so the
  search keeps the focus. Rows focus only on a request aimed at them
  (`focusTarget`).
- **`SidebarSearch`:** no `maxSelect`, because the library closes and blurs
  once a pick reaches it. `resetFilterOnAdd={false}`. `held` keeps the scope
  from `onopen` to `onclose`. Takes `openTests` and marks those hits with a
  check.
- A search pick no longer closes the mobile drawer.
- **Deselect:** picking a test hit that is already open calls `onToggleTest`
  and leaves the sidebar where it is.
- **Clear button:** an `afterInput` × shows while the query is not empty. It
  empties the query and focuses the input. The × and the scope chip both stop
  the click from propagating. Svelte removes them before the click reaches the
  library's outside-click listener on `window`, which would otherwise close the
  dropdown. Widening refocuses the input that `{#key}` rebuilt.

- [x] Write the failing tests: pinned order, persistence, blocked storage, eager stats for pins, the pin toggle in the list, two picks from one query, the held scope, the open marks, the focus kept in the search, the clear button.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Check in headless Chrome: pins move to the top and persist, two keyboard picks open two tests on desktop and in the mobile drawer, and the runs panel height stays put while a release loads.
- [x] Run the verify sequence.
- [x] Committed in e52823a9 `feature(workspace)`.

## Task 7 — The status facet and status indicators in search

**Files:**
- Modify:
  - `argus/backend/service/test_lookup.py`
  - `cli/cmd/search/root.go`
  - `frontend/WorkArea/Sidebar/SidebarRow.svelte`
  - `frontend/WorkArea/Sidebar/SidebarSearch.svelte`
  - `frontend/WorkArea/Sidebar/Sidebar.svelte`
  - `frontend/WorkArea/Sidebar/sidebarState.svelte.ts`
- Create: `frontend/WorkArea/Sidebar/StatusDot.svelte`
- Test: `argus/backend/tests/test_query_parser.py`, `argus/backend/tests/planner_api/test_planner_api.py`, `frontend/WorkArea/Sidebar/SidebarSearch.test.ts`, `frontend/WorkArea/Sidebar/Sidebar.test.ts`

**Internals:**
- **`STATS_FACETS`** = `status`, `istatus`, `assignee`, added to `FACET_KEYS`.
- **`_status_scope(release_id, parsed, index)`:** returns the release from
  `releaseId`, or else the one release a `release:` value names: an exact name
  first, then a single substring match.
- **`stats_facts(stats) -> dict[str, StatsFacts]`:** reads `status`,
  `investigation_status` and the latest run's `assignee` from either input
  shape of `collect()`, and returns `{}` for a dormant release.
- **`_stats_lookup(release, parsed)`:** runs
  `ReleaseStatsCollector.collect(limited=False, force=False, include_no_version=True)`,
  the sidebar's snapshot, and loads `{user_id: "username\nfull name"}` through
  `select_rows` only when the query has `assignee:`.
- **`_matches`:** with a stats lookup, only tests match. `status:` and
  `istatus:` compare a prefix; `assignee:` a substring of the user names. A
  query with a stats facet and no single release matches nothing.
- **`StatusDot.svelte`:** the dot with its visually hidden label, shared by
  `SidebarRow` and the search options.
- **`SidebarSearch` `statsFor(hit)`:** returns `{status}` or `{counts}` from
  `Sidebar.hitStats`, which reads `sidebar.stats` by the hit's release name. A
  run hit uses its own `status`. With no scope and a `status:` token,
  `noMatchingOptionsMsg` explains the scope.

- [x] Write the failing tests: the parser facets; `stats_facts` on both shapes and on a dormant release; the scoped filter with `status:` and `-status:`; `istatus:` and `assignee:` by username and full name; the scope from a `release:` facet; no single release matches nothing; the dot and the bar in the options; the hint for each stats facet; the status from loaded stats in the sidebar search.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Update the CLI help text and the `api_usage.md` query table.
- [x] Run the verify sequence.
- [x] Committed in cda3f21d `feature(search)`, 414e922a `improvement(cli/search)` and e52823a9 `feature(workspace)`.

## Task 8 — The issue facet

**Files:**
- Modify: `argus/backend/service/test_lookup.py`, `cli/cmd/search/root.go`, `frontend/WorkArea/Sidebar/SidebarSearch.svelte`, `docs/api_usage.md`
- Test: `argus/backend/tests/test_query_parser.py`, `argus/backend/tests/issues/test_issues.py`, `frontend/WorkArea/Sidebar/SidebarSearch.test.ts`

**Internals:**
- **`ParsedQuery.issue_key`:** the first `issue:` value; `-issue:` is dropped.
- **`TestLookup._lookup_issue(key, index)`:** calls
  `IssueService().get_issue_links(key)` and maps each link with
  `_issue_run_hit`, which takes the group and release from the index by
  `test_id`. `IssueServiceException`, a value that is not a Jira key, gives no
  hits. The issue path runs before the UUID path and pages the same way.
- **`SidebarSearch`:** hides the release chip while the query holds `issue:`,
  and explains an empty result. It takes `openIds`, the open tests and the runs
  picked into them, and marks those hits.
- **Run deselect:** `Sidebar` takes `openRuns` (WorkArea's `additionalRuns`)
  and `onCloseRun`. Picking an open run hit calls `onCloseRun`; `WorkArea`
  drops the run and closes the test with its last one. Closing a test drops
  its picked runs.

- [x] Write the failing tests: the parser field and the dropped exclusion; the runs of a key newest first with the rest of the query and a `releaseId` ignored; paging; an unknown and an invalid key; the hint and the hidden chip; an open run hit marked and closed on a second pick.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Check `issue:SCT-717` on the dev data through the CLI and the sidebar: two runs of one test open together, and picking each again closes it, the last one with its test.
- [x] Run the verify sequence.
- [x] Committed in 5d79b54a `feature(search)`, c4a9be50 `improvement(cli/search)`, 62c80e4e `improvement(workspace)` and fa5e0a4b `docs(api-usage)`.

## Task 9 — Documentation

**Files:**
- Modify:
  - `docs/api_usage.md`: the `stats/summary` route, the search `limit`/`offset`, the query grammar and the TTL note
  - `docs/project/architecture.md`: one line on the per-worker search index

- [x] Write the entries in the style of the existing `api_usage.md` sections.
- [x] Run `uv run pre-commit run --all-files`.
- [x] Committed in 3298a936 `docs(api-usage)`.

The PR body lists these:
- An admin sets `priority` on scylla-master and scylla-staging after the deploy.
- The `/test_runs` breakout page loses its search box.
- The `/releases` page changes order.
- The search and stats measurements.
