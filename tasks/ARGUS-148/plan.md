# ARGUS-148 — implementation plan

**Spec:** `tasks/ARGUS-148/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Backend tests create and read rows through services and the API, never
  `Model.save()` or `find()` in the test body. They need Docker
  (`pytestmark = pytest.mark.docker_required`).
- Every import at module top.
- No comments that justify a change; docstrings only where the module already
  uses them.
- Svelte 5 runes. A prop the child mutates is copied into local `$state`. The
  DOM is reached through `bind:this`, never `querySelector`.
- A badge carries a self-contained `background-color` and `color` pair
  (`text-bg-*`).
- Frontend tests run under Node 22:
  `npx -y node@22 node_modules/vitest/vitest.mjs run <paths>`.
- Commits: `feature(chat-mode): ...`, `feature(frontend): ...` or
  `docs(chat-mode): ...`, with `Task: ARGUS-148` as the last line. Stage by
  explicit path. Commit through `uv run git commit`.

## Task 1 — Plan selection and states in the chat

**Files:**
- Modify: `argus/backend/service/chat/plans.py`
- Modify: `argus/backend/service/chat/actions.py` (drop `resolve_labeled_tests`)
- Modify: `argus/backend/service/chat/tools.py` (`entity_summaries` moves out;
  `STATUS_GROUPS` and the import of the moved helpers)
- Modify: `argus/backend/service/chat/agent.py` (import `entity_summaries`
  from `plans`)
- Test: `argus/backend/tests/chat/test_plan_progress.py`

**Internals:**
- `plans.entity_summaries(entity, scope=None, wait=False)` is moved from
  `tools.py` and passes `wait` to `ReleaseSummaryService.get`.
- `plans.STATES = ("passed", "failed", "aborted", "in_progress", "not_run")`.
  `plans.state_of(status: str | None) -> str` maps a summary status to a
  state. `STATUS_GROUPS` moves next to it. A missing status and `pending`
  map to `not_run`.
- `plans.plan_tests(scope, plan, labels=None, match_all=False) -> list[ArgusTest]`
  replaces `actions.resolve_labeled_tests`:
  - With no labels, the plan's enabled tests, where a group stands for its
    enabled tests.
  - With labels, today's label rules and error.
- `plans.plan_states(entity, scope, tests, version) -> tuple[dict[UUID, dict | None], bool]`
  reads `entity_summaries(entity, scope, wait=True)` and finds `version` in
  every release's families. It returns each test's summary entry, or `None`,
  and whether any summary came back stale.
- `plans.plan_version(plan, version) -> str` returns `version`, or the
  plan's `target_version`. It raises `TestReferenceError("Name a version: the
  plan <name> has no target version")` when neither is set.

Steps:
- [x] Write the failing tests:
  - `plan_tests` without labels returns the tests of a plan group plus a
    direct test.
  - `plan_states` gives the seeded failed run's test as `failed` and the
    other test as `None`.
- [ ] Run them and confirm the failure.
- [x] Move the helpers and write `plan_tests`, `plan_states`, `state_of` and
  `plan_version`. Point `execute_plan_tests` and `agent.py` at them.
- [x] Run `uv run pytest argus/backend/tests/chat`.

## Task 2 — `get_plan_progress` and the state filter on plan starts

**Files:**
- Modify: `argus/backend/service/chat/tools.py`
- Modify: `argus/backend/service/chat/prompt.py` (`TOOL_RULES`)
- Test: `argus/backend/tests/chat/test_plan_progress.py`

**Internals:**
- `PlanProgressArgs(plan, labels, match_all, version)`.
- Tool `get_plan_progress` returns the shape in the spec: counts per state, a
  per-test list capped at `SUMMARY_TEST_LIMIT` with a `truncated` note, and
  `stale`.
- `ExecutePlanArgs`:
  - `labels` becomes `StringList | None`.
  - New fields `version` and `only: list[Literal[*STATES]] | None`.
- `execute_plan_tests`:
  - With `only`, keep the tests whose `state_of` is listed. An empty result
    raises `TestReferenceError` naming the counts.
  - `dry_run` adds each test's state when `only` or `version` is set.
  - The selection over `EXPANSION_LIMIT` is refused as in `execute_tests`.
- `TOOL_RULES` gains one rule:
  - A plan's labels select tests.
  - Before starting another batch, check it with `get_plan_progress`.
  - To start only what still needs a run, pass `only` to
    `execute_plan_tests`.

Steps:
- [x] Write the failing tests:
  - Progress on `2037.1.0~rc1` counts one failed and one not run.
  - Progress takes the plan's target version when none is named.
  - Progress without any version asks for one.
  - `execute_plan_tests` with `only=["not_run"]` proposes only the second
    test.
  - With no labels, it takes the whole plan.
  - `only=["passed"]` proposes nothing and names the counts.
  - The tool spec test still passes with the new tool.
- [ ] Run them and confirm the failure.
- [x] Write the tool, the arguments and the rule.
- [x] Run `uv run pytest argus/backend/tests/chat`.

## Task 3 — Plan filter on the read tools

**Files:**
- Modify: `argus/backend/service/chat/tools.py`
- Test: `argus/backend/tests/chat/test_plan_progress.py`

**Internals:**
- `PlanFilterArgs(BaseModel)` with `plan`, `labels` and `match_all`. It is
  mixed into `ReleaseArgs`, `SummaryArgs` and `AssigneesArgs`.
- `async plan_filter(scope, args) -> set[UUID] | None`:
  - `None` without a plan.
  - Labels without a plan raise `TestReferenceError("Name the plan whose
    labels to use")`.
  - Otherwise, the ids of `plan_tests(...)`.
- `read_release` and `get_summary` keep only the tests in the set.
- `get_assignees`: `tests` becomes optional. With a plan and no tests it lists
  the plan's selection, and with neither it raises an error.

Steps:
- [x] Write the failing tests:
  - `read_release` with a plan and a label lists only the labelled test.
  - `get_summary` with a version and a plan lists only the plan's tests.
  - `get_assignees` with only a plan lists the plan's tests.
  - Labels without a plan give an error.
- [ ] Run them and confirm the failure.
- [x] Write the filter.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md` for
  the backend (`uv run pre-commit run --all-files`, `uv run pytest`).
- [x] Commit Tasks 1–3, with their boxes checked:
  `feature(chat-mode): follow a plan's progress and rerun what it still needs`.

## Task 4 — Plan label helpers

**Files:**
- Create: `frontend/ReleasePlanner/planLabels.ts`
- Test: `frontend/ReleasePlanner/planLabels.test.ts`

**Internals:**
- `type PlanOptions = Record<string, { labels?: string[] }>`.
- `parseOptions(options: string | PlanOptions | null | undefined): PlanOptions`.
- `labelsOf(options, testId, groupId?): string[]`: the test's labels, then its
  group's, without duplicates (ignoring case).
- `addLabel(options, id, label): PlanOptions | string`: returns the new
  options, or an error message when the label is empty or already on the
  item.
- `removeLabel(options, id, label): PlanOptions`: drops the key when its last
  label goes.
- `optionsDiff(original, current): { options_set, options_remove }`.
- `labelCounts(options, plan, testsOfGroup): {label, count}[]`, sorted by
  label. A group counts its tests.
- `matchesLabels(labels, selected): boolean`: matches any selected label,
  ignoring case. An empty selection matches everything.

Steps:
- [x] Write the failing tests for each function:
  - the diff for an added, a changed and an emptied entity
  - an inherited group label
  - a duplicate refused when it differs only in case
  - a string parsed from the API
- [ ] Run them and confirm the failure.
- [x] Write the module.
- [x] Run the tests.

## Task 5 — Labels in the planner

**Files:**
- Modify: `frontend/ReleasePlanner/ReleasePlanCreator.svelte`
- Modify: `frontend/ReleasePlanner/ReleasePlan.svelte`
- Modify: `frontend/ReleasePlanner/ReleasePlannerGridView.svelte` (badges on
  planned tests and groups; options prop)
- Create: `frontend/ReleasePlanner/PlanLabelEditor.svelte` (the badges of one
  item, the remove buttons, and the add input with a datalist)
- Create: `frontend/ReleasePlanner/PlanLabelFilter.svelte` (toggle buttons for
  the plan's labels)
- Test: `frontend/ReleasePlanner/ReleasePlanCreator.test.ts`

**Internals:**
- `ReleasePlanCreator`:
  - `let options = $state(parseOptions(plan.options))` and
    `originalOptions`, taken with the snapshot.
  - `createPlan` sends `options`.
  - `computeDiff` merges `optionsDiff(originalOptions, options)`.
  - `removeSelectedItem` and "Remove all" delete the options keys.
  - `explodeGroup` copies the group's labels to each new test and deletes the
    group's key.
  - `let labelFilter = $state<string[]>([])`. Items whose labels do not match
    are hidden with `{#if}` inside the existing `{#each}`.
- `ReleasePlan` shows `labelCounts` as `text-bg-light` badges under the
  description.
- `ReleasePlannerGridView` takes an `options` prop and shows `labelsOf` badges
  on each planned test and group.

Steps:
- [x] Write the failing tests, which mock `fetch` and render the creator in
  edit mode with a plan whose `options` is a JSON string:
  - a label added through the editor appears in the update body's
    `options_set`
  - in createFrom mode, the create body carries `options`
  - the filter hides an unlabelled item
- [ ] Run them and confirm the failure.
- [x] Write the components.
- [x] Run the tests and `yarn build`.

## Task 6 — Plan-label filter on the dashboards

**Files:**
- Modify: `frontend/ReleaseDashboard/TestDashboard.svelte`
- Modify: `frontend/ReleaseDashboard/TestDashboardTest.svelte` (plan label
  badges)
- Test: `frontend/ReleasePlanner/planLabels.test.ts` (`planLabelMatches`,
  `planLabelsOfTest`, `planLabelOptions`)

**Internals:**
- Fetch the plans once, on mount:
  - The release ids are `[dashboardObject.id]` for a release and
    `dashboardObject.release_ids` for a view.
  - Each id is fetched from `GET /api/v1/planning/release/{id}/all`.
  - A failed fetch leaves the list empty.
- Store `plans = $state([])` as `{id, name, options}` with parsed options.
- `FILTER_STACK.planLabel`:
  - state: `{planId, label} | undefined`
  - `f(test)` is true without a state, else
    `matchesLabels(labelsOf(options, test.test.id, test.test.group_id), [label])`
  - persisted with the rest, so the localStorage key is unchanged
- `planLabelOptions(plans)` is exported from `planLabels.ts`: one entry per
  plan and label, named "plan · label".
- A `<select>` labelled "Filter by plan label", next to the backend filter.
- `TestDashboardTest` takes an optional `planLabels: string[]` and shows them
  as badges when the filter is active.

Steps:
- [x] Write the failing tests for `planLabelOptions` and for the filter
  function over tests from a group label and from a test label.
- [ ] Run them and confirm the failure.
- [x] Write the filter and the select.
- [x] Run the tests and `yarn build`.
- [x] Commit Tasks 4–6, with their boxes checked:
  `feature(frontend): show, edit and filter plan labels`.

## Task 7 — Chat examples and help panel

**Files:**
- Create: `frontend/Chat/chatExamples.ts`
- Create: `frontend/Chat/ChatHints.svelte`
- Modify: `frontend/Chat/ChatModal.svelte` (empty state; header help button;
  `examples` side tab)
- Modify: `frontend/Chat/ChatComposer.svelte` (`text` becomes `$bindable`;
  focus through `bind:this`)
- Test: `frontend/Chat/ChatHints.test.ts`, `frontend/Chat/ChatModal.test.ts`

**Internals:**
- `EXAMPLE_GROUPS: {title: string, examples: string[]}[]` with Ask, Run
  tests, Plans and labels, Memories and Zeus. The examples come from
  `docs/release_chat.md`.
- `DOCS_URL = "https://github.com/scylladb/argus/blob/master/docs/release_chat.md"`.
- `ChatHints` props:
  - `onpick(text)`
  - `compact?: boolean`, for the side tab
- `ChatHints` renders:
  - each group as a heading with buttons (`btn btn-sm btn-outline-secondary`,
    wrapping)
  - the note about cards, **Run** and Auto mode
  - the docs link
- `ChatModal`:
  - `side` gains `"examples"`.
  - The header button "Examples" (`faCircleQuestion`, `aria-label`) sets
    `side = "examples"`.
  - `pick(text)` sets `draft = text` and calls `composer.focus()`.
- `ChatComposer` exports `focus()`, and `text = $bindable("")`.

Steps:
- [x] Write the failing tests:
  - `ChatHints` renders the four groups and the docs link.
  - A click calls `onpick` with the example text.
  - In `ChatModal`, an empty conversation shows the groups.
  - In `ChatModal`, clicking an example fills the textarea and makes no POST.
  - The header button opens the examples tab.
- [ ] Run them and confirm the failure.
- [x] Write the components.
- [x] Run `npx -y node@22 node_modules/vitest/vitest.mjs run frontend/Chat` and
  `yarn build`.
- [x] Commit: `feature(frontend): show what the chat can do`.

## Task 8 — Documentation

**Files:**
- Modify: `docs/release_chat.md`
- Create: `docs/release_plans.md`
- Modify: `docs/INDEX.md` (reference list)
- Check: `docs/project/architecture.md` (chat tools list, if any)

Content:
- `release_chat.md`:
  - "Asking" mentions the examples in an empty chat and the **Examples**
    button.
  - "Running tests" opens with a step-by-step list:
    1. ask
    2. read the card
    3. Edit parameters or ask for a change
    4. **Run**
    5. follow the progress
  - New examples for plan progress and for `only` ("rerun the week1 tests
    that failed or did not run on rc4").
  - "Plans" gains progress and the label filter on questions.
- `release_plans.md`:
  - labels in the planner: add, remove, filter, the plan card counts, the
    grid
  - copying and splitting keep labels
  - the dashboard filter
  - the CLI's `--label` / `--unlabel`
  - how the chat uses labels

Steps:
- [x] Write the documents.
- [x] Run the full verify sequence: `uv run pre-commit run --all-files`,
  `uv run pytest`, `yarn test` (under Node 22), `yarn build`.
- [x] Check in the running dev server, at two widths:
  - planner labels save and reload
  - createFrom and split keep labels
  - the dashboard filter survives a reload
  - an example fills the chat box
  - progress and an `only` start card on a real plan, dismissed without
    running
- [x] Commit: `docs(chat-mode): describe plan labels and running planned tests`.
