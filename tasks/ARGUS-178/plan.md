# ARGUS-178 — implementation plan

**Spec:** `tasks/ARGUS-178/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Follow `docs/standards/`, in particular `backend/models.md`,
  `backend/migrations.md`, `frontend/components.md`, `frontend/css.md` and
  `testing/test-writing.md`.
- Put every import at the top of its module.
- Add no comment that explains why the change happened.
- Backend tests create and read issues through `IssueService` or the API,
  never through `JiraIssue.save()` or `JiraIssue.find()` in the test body. The
  Jira client stays a `MagicMock` on a dry-run `IssueService`
  (`mocked_issue_service` in `test_issues.py`).
- Write Svelte code with runes. A frontend test asserts the rendered DOM, not a
  component's state.
- The verify sequence is the `Commands` section of `CLAUDE.md`: pre-commit,
  `uv run pytest` (needs Docker), `yarn test`, then `yarn build` for the
  frontend.

## Task 1 — Store and sync the Jira priority

**Files:**
- Modify: `argus/backend/models/jira.py:12-22`
- Modify: `argus/backend/service/jira_service.py:61-141`
- Test: `argus/backend/tests/issues/test_issues.py`
- Test: `argus/backend/tests/issues/test_issue_version_filter.py:107-120`

**Internals:**
- `JiraIssue.priority: str | None = None`.
- `JiraService.priority_name(fields) -> str | None`, a static method next to
  `assignee_identity`. It returns
  `getattr(getattr(fields, "priority", None), "name", None)`.
- `get_issue` sets `issue.priority = self.priority_name(remote_issue.fields)`.
  `refresh_stale_issues` sets `local_issue.priority` the same way.
- `fake_remote_jira_issue` gains `priority: str | None = "P2"`. It sets
  `fields.priority` to `SimpleNamespace(name=priority)` when a priority is
  given, and to `None` otherwise.

Steps:
- [x] Write the failing tests in `test_issues.py`:
  - `test_submit_unknown_jira_issue_stores_its_priority`: submitting an issue
    whose remote is P1 returns `priority == "P1"`, and so does
    `IssueService.get("run_id", run.id)`.
  - `test_submit_jira_issue_without_priority_stores_none`: a remote with
    `priority=None` returns `priority is None`.
  - `test_refresh_stale_jira_issues_updates_priority`: submit at P3, have
    `search_issues` return P0, refresh, and `IssueService.get` returns `"P0"`.
- [x] Add `"priority": None` to `expected_jira_issue` in
  `test_issue_version_filter.py`. Its fixture creates the issue row directly,
  without a priority.
- [x] Run `uv run pytest argus/backend/tests/issues` and confirm that the new
  tests fail.
- [x] Add the field, `priority_name`, and the two assignments.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Backfill the priority of the stored issues

**Files:**
- Create: `scripts/migration/migration_2026-10-15_backfill_jira_issue_priority.py`

**Internals:**
- Follow the layout of `migration_2026-09-21_backfill_run_config_param_index.py`:
  the module docstring with the run commands, `setup_application_logging`,
  `LOGGER`, `DB = ScyllaCluster.get()`, `main()` with `argparse`, and
  `asyncio.run`.
- `BATCH_SIZE = 100`.
- `async def rows_without_priority(key: str | None) -> list[JiraIssue]`: either
  `JiraIssue.find(key=key).all()` for `--key`, or `JiraIssue.find().all()`.
  Keep the rows whose `priority is None`.
- `async def backfill(key: str | None) -> dict[str, int]`:
  - Group the rows by key, since two rows may share a key.
  - For each `chunk(keys, BATCH_SIZE)` (from `argus.backend.util.common`),
    run `asyncio.to_thread(jira.search_issues, f"key in ({', '.join(batch)})", fields="priority", maxResults=0)`.
  - For each returned issue with a priority, call
    `await row.update(priority=name)` on every row of that key, and count
    `updated`.
  - Count a key that came back without a priority, or did not come back, as
    `missing`.
  - On `JIRAError` or `RequestException`, log the batch, add its keys to
    `failed`, and continue.
- The Jira client is `JiraService().jira`. Before the first batch, the script
  logs how many rows it found.
- The summary logs the counts, and warns to re-run when `failed > 0`.

Steps:
- [x] Write the script.
- [x] Run `uv run python scripts/migration/migration_2026-10-15_backfill_jira_issue_priority.py --help`
  and confirm the usage text prints.
- [x] The migration scripts carry no unit tests. Task 8 runs this one against
  the dev database and live Jira.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — The priority badge and the runs link on the Jira card

**Files:**
- Modify: `frontend/Common/IssueTypes.ts`
- Modify: `frontend/Jira/JiraIssue.svelte`
- Modify: `frontend/IssueLinks/IssueLinks.svelte:49`
- Test: `frontend/Common/IssueCard.test.ts`
- Test: `frontend/Common/IssueTypes.test.ts`
- Test: `frontend/IssueLinks/IssueLinks.test.ts`

**Internals:**
- In `IssueTypes.ts`:
  - `JiraSubtype.priority: string | null`.
  - `export const JIRA_PRIORITIES = ["P0", "P1", "P2", "P3", "P4"]`.
  - `export const JiraPriorityClass: Record<string, string>` maps P0 to P4 to
    `text-bg-danger`, `text-bg-warning`, `text-bg-primary`,
    `text-bg-secondary` and `text-bg-light`.
  - `export const priorityClass = (priority: string) => JiraPriorityClass[priority] ?? "text-bg-secondary"`.
  - `export const priorityIndex = (priority: string | null): number`. A known
    priority returns its index in `JIRA_PRIORITIES`. An unknown name returns
    `JIRA_PRIORITIES.length`, and a null priority returns `Infinity`.
    `Issues.svelte` uses it to order the Priority checkboxes.
  - `export const priorityRank = (i: Issue): number` applies `priorityIndex` to
    the priority of a Jira issue, and returns `Infinity` for a GitHub issue.
- In `JiraIssue.svelte`:
  - Add the prop `showRunsLink?: boolean`, defaulting to `true`.
  - After the state pill, render
    `{#if issue.priority}<span class="badge rounded-pill {priorityClass(issue.priority)}" title="Priority">{issue.priority}</span>{/if}`.
  - After the key link, when `showRunsLink` is set, render
    `<a class="btn btn-sm btn-outline-secondary" href="/issues/{encodeURIComponent(issue.key)}" title="Runs linked to {issue.key}"><Fa icon={faList} /> Runs</a>`.
  - Add `priority: null` to the `$bindable` default issue.
- `IssueLinks.svelte` passes `showRunsLink={false}` to `IssueCard`.
- The `JIRA_ISSUE` fixture in `IssueCard.test.ts` gains `priority: "P1"`.

Steps:
- [x] Write the failing tests:
  - `IssueCard.test.ts`: the Jira card shows `P1`. Its "Runs" link has
    `href="/issues/FROBNICATOR-123"`. With `showRunsLink: false`, no link
    named "Runs" exists. A card with `priority: null` shows no priority badge.
  - `IssueTypes.test.ts`:
    - `priorityRank` gives 0 for P0 and 4 for P4.
    - It gives 5 for an unknown name such as "Critical".
    - It gives `Infinity` for a null priority and for a GitHub issue.
    - `priorityClass` falls back to `text-bg-secondary`.
  - `IssueLinks.test.ts`: the issue page renders no "Runs" link.
- [x] Run `yarn test` and confirm that the new tests fail.
- [x] Make the changes.
- [x] Run the verify sequence and `yarn build`.
- [x] Commit, with the boxes of this task checked.

## Task 4 — Checkbox filters for status, priority and Jira Space

**Files:**
- Modify: `frontend/Github/Issues.svelte:97-116, 192-212, 303-327`
- Test: `frontend/Github/Issues.test.ts`

**Internals:**
- Remove `stateFilter`, the state check in `shouldFilterByState`, and the
  Open and Closed switches. Keep the "Descending order" switch.
- Add `type FilterGroup = "state" | "priority" | "project"`.
- Add `const NO_PRIORITY = "none"`.
- Add `const excluded: Record<FilterGroup, Record<string, boolean>> = $state({ state: {}, priority: {}, project: {} })`.
- Add `const jiraIssues = $derived(issues.filter((i) => i.subtype === "jira") as JiraSubtype[])`.
- Add `const filterOptions = $derived({ state: distinct(issues.map((i) => i.state)), priority: distinct(jiraIssues.map((i) => i.priority ?? NO_PRIORITY)), project: distinct(jiraIssues.map((i) => i.project)) })`.
  - `distinct` returns the sorted unique values.
  - Sort the priorities with the order of `JIRA_PRIORITIES` first.
- In `shouldFilter`:
  - Return `true` when `excluded.state[issue.state]` is set.
  - For a Jira issue, also return `true` when
    `excluded.priority[issue.priority ?? NO_PRIORITY]` or
    `excluded.project[issue.project]` is set.
  - Then run the label check and the text check as before.
- Add `const toggleFilter = (group: FilterGroup, value: string, checked: boolean) => { excluded[group][value] = !checked; currentPage = 0; }`.
- Rendering:
  - Write `{#snippet filterGroup(title, group, values)}` as a row with a small
    label and one `form-check form-check-inline` checkbox per value. Each
    checkbox has a unique `id`, which is `issueFilter-{group}-{index}`, plus
    `checked={!excluded[group][value]}` and `onchange`.
  - Render Status always.
  - Render Priority and Space only when `jiraIssues.length > 0`.
- `sortedIssues` already reads `excluded` through `shouldFilter`, so it updates
  when a box changes.

Steps:
- [ ] Write the failing tests in `Issues.test.ts`:
  - The issues are one GitHub `open`, one GitHub `closed`, a Jira `to do` P1
    in SCT, a Jira `in progress` P0 in SCYLLADB, and a Jira `done` with no
    priority in SCT.
  - Add a fixture helper `stubIssues(issues)` that answers fetch with them.
  - The Status group lists `closed`, `done`, `in progress`, `open` and
    `to do`.
  - The Priority group lists `P0`, `P1` and `none`.
  - The Space group lists `SCT` and `SCYLLADB`.
  - Unchecking `to do` hides the SCT P1 issue and keeps the rest.
  - Unchecking `SCT` hides both SCT issues and keeps both GitHub issues.
  - Unchecking `none` hides the issue without a priority.
  - With GitHub issues only, no Priority group and no Space group render.
- [ ] Run `yarn test` and confirm that the new tests fail.
- [ ] Make the changes.
- [ ] Run the verify sequence and `yarn build`.
- [ ] Commit, with the boxes of this task checked.

## Task 5 — Fill the "All Labels" panel

**Files:**
- Modify: `frontend/Github/Issues.svelte:102, 142-153, 343-360`
- Test: `frontend/Github/Issues.test.ts`

**Internals:**
- Add `type PanelLabel = { label: Label; color: string }`.
- Add `const availableLabels: PanelLabel[] = $derived(...)`:
  - It covers the labels of every fetched issue, deduplicated by `label.id`
    and sorted by `label.name`.
  - `color` is `#${label.color}` for a GitHub issue, and `label2color(label)`
    for a Jira issue.
- Each chip is a button:
  - It uses `style="background-color: {color}; color: {Color(color).isDark() ? 'white' : 'black'}"`.
  - It carries `aria-pressed={labelActive(label.id, selectedLabels)}`.
  - When the label is active, it gets the class `border border-2 border-dark`
    and shows a `faCheck` icon.
  - `onclick` calls `handleLabelClick(label)`.
- Render the panel row only when `availableLabels.length > 0`.
- `handleLabelClick` also resets `currentPage = 0`.

Steps:
- [ ] Write the failing tests in `Issues.test.ts`:
  - Use two issues that share the label `bug`, and one with the label
    `perf`.
  - Opening "All Labels" shows one `bug` button and one `perf` button.
  - Clicking `perf` leaves only the issue with `perf`, and sets
    `aria-pressed="true"`.
  - Clicking `perf` again shows all three issues.
  - Issues without labels render no "All Labels" panel.
- [ ] Run `yarn test` and confirm that the new tests fail.
- [ ] Make the changes.
- [ ] Run the verify sequence and `yarn build`.
- [ ] Commit, with the boxes of this task checked.

## Task 6 — Sort by priority

**Files:**
- Modify: `frontend/Github/Issues.svelte:97-135, 214`
- Test: `frontend/Github/Issues.test.ts`

**Internals:**
- `type SortCriteria = "name" | "repo" | "date" | "priority"`. Type
  `sortCriteria` and `paginateIssues` with it.
- Add `SORT_ORDERS.priority = { field: "priority", friendlyString: "By priority", f }`, where `f`:
  - Takes `lhs` and `rhs` from `priorityRank`.
  - When both ranks are `Infinity`, or they are equal, falls back to the newest
    `added_on` first.
  - When one rank is `Infinity`, puts that issue last.
  - Otherwise returns `reverseSort ? lhs - rhs : rhs - lhs`.

Steps:
- [ ] Write the failing tests in `Issues.test.ts`:
  - Use Jira P2, Jira P0, a GitHub issue and a Jira issue without a priority.
  - "By priority" with "Descending order" on renders P0, P2, then the two
    issues without a priority.
  - With "Descending order" off, it renders P2, P0, then the two issues
    without a priority.
- [ ] Run `yarn test` and confirm that the new tests fail.
- [ ] Make the changes.
- [ ] Run the verify sequence and `yarn build`.
- [ ] Commit, with the boxes of this task checked.

## Task 7 — Document the priority in the API reference

**Files:**
- Modify: `docs/api_usage.md:315-330`

Steps:
- [ ] Add `"priority": "P2",` after `"project": "SCT",` in the example issue
  of `GET /api/v1/issues/{key}/links`.
- [ ] Commit, with the boxes of this task checked.

## Task 8 — Live check against the dev database and Jira

**Files:** none.

Steps:
- [ ] Run `uv run python -m argus.backend.cli sync-models` against the dev
  database, then confirm with `cqlsh` that `jira_issue` has a `priority`
  column.
- [ ] Run the backfill with `--key` on one stored key, then without it.
  Confirm the counts, and that a re-run finds no row to update.
- [ ] Start the app, `uv run uvicorn --factory argus_backend:create_app --port 5000`,
  and drive it with headless Chrome. Check the issue tab of a run, the release
  dashboard and an issue view widget:
  - The priority badges show.
  - The three filter groups hide and restore the issues.
  - The "All Labels" panel lists the labels and filters.
  - "By priority" orders the issues.
  - The "Runs" link opens `/issues/<KEY>`, and that page shows no "Runs" link.
- [ ] Link a Jira issue of type Task to a dev run, and confirm that its priority
  shows. A Task leaves the Seen Again Counter untouched, so the check writes
  nothing to Jira.
- [ ] Run `refresh-issues`, and confirm that it keeps the priorities.
