# ARGUS-276 — implementation plan

**Spec:** `tasks/ARGUS-276/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- The first box of Task 8, the "before" screenshots, runs before Task 1.
- One commit per task, in the order below. Tasks 1-6 each remove their code
  from `suppressedSvelteCodes` in `vite.config.ts` and touch no other line
  of that file. Task 7 does not touch `vite.config.ts`.
- The failing check of Tasks 1-6 is the build: remove the code first, run
  `yarn build`, and see its warnings. The task is done when the a11y count
  below drops to the expected number. Count with:

  ```bash
  yarn build 2>&1 | grep -o 'svelte.dev/e/a11y_[a-z_]*' | sort | uniq -c
  npx svelte-check --workspace frontend --output machine | grep -o 'a11y_[a-z_]*' | sort | uniq -c
  ```

  `svelte-check` also reports `a11y_label_has_associated_control` in the
  unused `TestRun/Jenkins/CheckParam.svelte`; that one stays (spec,
  Deferred work).
- Line numbers below are the source lines on `14e76bed`. `yarn build`
  prints shifted lines for a `lang="ts"` component.
- A Vitest test is written first where the task adds behaviour a test can
  hold in jsdom: a new prop, Escape, focus. A markup-only swap is covered by
  the build count and the live check of Task 8.
- Each task runs `uv run pre-commit run --all-files`, `yarn build` and
  `yarn test`. `uv run pytest` runs once on the finished branch; the change
  touches no backend code.
- Never touch `frontend/Common/ModalWindow.svelte`, the Font Awesome files,
  `templates/`, the `{@html}` and `marked` lines of `Discussion/*.svelte`
  and `ViewHighlights/*.svelte`, the toast code of `Alerts/AlertWidget.svelte`
  or the tooltip code of `TestRun/ResultsGraph.svelte`. An `<i class="fas">`
  moves with its parent unchanged.
- No comment that explains the change. A `svelte-ignore` line is a
  directive, and only Task 4 adds one.
- Commit header `fix(frontend): <verb> ...`, at most 72 characters; the body
  ends with `Task: ARGUS-276`. Stage by explicit path. Commit with
  `uv run git commit`.

## Task 1 — `a11y_missing_attribute`

**Files:**
- Modify: `vite.config.ts` (`suppressedSvelteCodes` only)
- Modify: `frontend/TestRun/ResultsGraphs.svelte:221`
- Test: `frontend/TestRun/ResultsGraphs.test.ts`

**Internals:** the tab `<a class="nav-link">` becomes
`<button type="button" class="nav-link" class:active aria-current={activeTab === i ? "true" : undefined}>`.
Bootstrap styles `button.nav-link` as a tab.

- [x] Remove the code; `yarn build` shows 1 `a11y_missing_attribute`.
- [x] Add a test: each tab is a `button` named by its text, and clicking
      `+ View` opens the New View form. Run it and confirm the failure.
- [x] Swap the element. The build shows no `a11y_missing_attribute`; the
      click_events and no_static counts drop by 1 each.
- [x] Run `yarn test` and pre-commit, then commit
      `fix(frontend): turn on the a11y_missing_attribute warning`.

## Task 2 — `a11y_interactive_supports_focus`

**Files:**
- Modify: `vite.config.ts`
- Modify: `frontend/Teams/TeamMember.svelte:85`, `:109`

**Internals:** each `<div class="px-2" role="button">` becomes
`<button type="button" class="btn btn-link px-2 py-0 border-0 rounded-0 text-reset text-decoration-none" class:border-end aria-expanded={show...}>`.
The visible text stays the icon and the count. `aria-label` reads
`"{stats.total} not investigated"` and `"{stats.total} investigated"`, so
the visible count is part of the name.

- [x] Remove the code; the build shows 2 `a11y_interactive_supports_focus`.
- [x] Swap both elements. The build shows none; click_events drops by 2.
- [x] Run `yarn test` and pre-commit, then commit.

## Task 3 — `a11y_no_noninteractive_element_to_interactive_role`

**Files:**
- Modify: `vite.config.ts`
- Modify: `frontend/AdminPanel/ReleaseManager.svelte:499-514`
- Modify: `frontend/AdminPanel/ReleaseManagerGroup.svelte:8, 17, 28, 37, 50-54, 65, 77, 86, 144-149`
- Modify: `frontend/Profile/NotificationsReader.svelte:57-82`
- Test: `frontend/AdminPanel/ReleaseManagerGroup.test.ts` (new)

**Internals:**
- `ReleaseManagerGroup` props gain `selected = false` and `onselect`
  (spec, Contracts). The name `<div>` becomes
  `<button type="button" class="btn btn-link p-0 border-0 rounded-0 flex-fill align-self-stretch text-start text-reset text-decoration-none" aria-current={selected ? "true" : undefined} onclick={onselect}>`.
- `ReleaseManager` drops `role="button"` and `onclick` from the `<li>`, keeps
  `class:selected`, and passes `selected={currentGroup?.id == group.id}` and
  `onselect={() => handleGroupChange(group)}`.
- The shield `onclick={(e) => e.stopPropagation()}` on
  `.popup-group-editor` (86) and on the delete modal (148) go (P4). The
  `e.stopPropagation()` calls in the edit, delete, toggle, update and delete
  handlers go too: no ancestor listens any more.
- `NotificationsReader`: the `<li>` loses its classes, `role` and `onclick`
  and holds `<button type="button" class="list-group-item list-group-item-action border-0 border-bottom" class:active aria-current={n.id == selectedNotification?.id ? "true" : undefined}>`
  with the old content and the old `onclick`. `.list-group-flush > .list-group-item`
  no longer matches the nested button, so the border utilities replace its
  flush borders; the screenshots of Task 8 confirm the look.

- [x] Remove the code; the build shows 2 warnings of it.
- [x] Write `ReleaseManagerGroup.test.ts`: the name button calls `onselect`;
      `aria-current="true"` follows `selected`; Edit and Delete do not call
      `onselect`. Run it and confirm the failure.
- [x] Make the change. The build shows none of this code; click_events
      drops by 4 and no_static by 2.
- [x] Run `yarn test` and pre-commit, then commit.

## Task 4 — `a11y_no_noninteractive_element_interactions`

**Files:**
- Modify: `vite.config.ts`
- Create: `frontend/Common/overlayFocus.ts`
- Test: `frontend/Common/overlayFocus.test.ts` (new)
- Modify: `frontend/AdminPanel/AvatarCropper.svelte:90`
- Modify: `frontend/TestRun/ResultsGraphs.svelte:3-5, 258-331`
- Test: `frontend/TestRun/ResultsGraphs.test.ts`

**Internals:**
- `overlayFocus(node: HTMLElement, active = true): { update(next: boolean): void; destroy(): void }`.
  On open it stores `document.activeElement` and, after `tick()`, calls
  `node.focus({ preventScroll: true })`; an overlay hidden by a class is
  still `display: none` until that DOM update lands. On close or destroy it returns the
  focus to the stored element when that is still connected. `update(next)`
  opens or closes on a change of `active`. A `keydown` listener on the node
  wraps Tab from the last shown, enabled control to the first and Shift+Tab
  from the first, or from the node, to the last; a control is skipped when
  it is `:disabled`, `hidden`, or under an ancestor with `display: none` or
  `visibility: hidden` inside the node. Same idea as `dialogOpen` in
  `ScreenshotModal.svelte`, which this task leaves alone.
- `AvatarCropper`: the line above the viewport `<div>` gets
  `<!-- svelte-ignore a11y_no_noninteractive_element_interactions, a11y_no_noninteractive_tabindex -->`.
  Nothing else changes.
- Each of the three ResultsGraphs modals (New View, Add Graph, Remove
  Graph): the outer `.modal` keeps `role="dialog"` and `tabindex="-1"`, and
  gains `aria-modal="true"`, `aria-labelledby` to an `id` on its
  `.modal-title`, `use:overlayFocus`, `onkeydown={(e) => e.key === "Escape" && close()}`,
  and `onclick={(e) => e.target === e.currentTarget && close()}`. The inner
  `.modal-dialog` loses `role="document"` and its `onclick`; the
  `createBubbler` and `stopPropagation` imports of lines 3-5 go. The close
  `×` buttons gain `aria-label="Close"`.

- [x] Remove the code; the build shows 4 warnings of it, and 1
      `a11y_no_noninteractive_tabindex`.
- [x] Write `overlayFocus.test.ts`: focus moves to the node on mount and on
      `update(true)`, and back to the trigger on `update(false)` and on
      destroy. Add to `ResultsGraphs.test.ts`: the New View dialog is found
      by `getByRole("dialog", { name: "New View" })` and has the focus;
      Escape closes it; a click on the backdrop closes it; a click in the
      form does not. Run them and confirm the failures.
- [x] Make the change. The build shows no warning of this code and no
      `a11y_no_noninteractive_tabindex`; click_events drops by 6.
- [x] Run `yarn test` and pre-commit, then commit.

## Task 5 — `a11y_click_events_have_key_events`

**Files:**
- Modify: `vite.config.ts`
- Modify: `frontend/Stats/NumberStats.svelte:119-133`
- Modify: `frontend/Views/Widgets/GraphsWidget/GraphsWidget.svelte:165-171, 176-185`
- Modify: `frontend/TestRun/ResultsGraph.svelte:2, 4, 367-368`

**Internals:**
- `NumberStats`: the investigation bar `<div ... cursor-pointer onclick>`
  becomes `<button type="button" class="align-self-start d-inline-flex shadow-sm overflow-hidden border rounded p-0 bg-transparent text-reset" aria-expanded={extended}>`.
  An `extended` `$state` flips in `toggleExtendedInvestigations`, which the
  Hide button also calls. The inner `<div role="button">` lose the role, and
  each status icon gets `title={TestInvestigationStatusStrings[...]}` so the
  button's name reads the status names with their counts. The unused
  `.cursor-pointer` rule goes.
- `GraphsWidget`: each `.card-header` loses its `onclick`; its heading wraps
  a `<button type="button" class="w-100 p-0 border-0 bg-transparent text-reset text-start fw-medium d-flex align-items-center" aria-expanded aria-controls="test-{testId}">`
  (and `view-{view.id}`) holding the existing `<i>` chevron and the name.
  No `.btn` class, so the heading keeps its font size and weight.
- `ResultsGraph`: `.modal-content` loses `onclick={stopPropagation(bubble('click'))}`;
  no component listens to `click` on `ResultsGraph` (P4). The
  `createBubbler` and `stopPropagation` imports and the `bubble` constant go;
  `run` stays. Its `×` button
  gains `aria-label="Close"`.

- [x] Remove the code; the build shows 4 warnings of it.
- [x] Make the change. The build shows none; no_static drops by 4.
- [x] Run `yarn test` and pre-commit, then commit.

## Task 6 — `a11y_no_static_element_interactions`

**Files:**
- Modify: `vite.config.ts` (the list becomes `[]`)
- Modify: `frontend/AdminPanel/ReleaseManagerGroup.svelte:86-92`
- Modify: `frontend/AdminPanel/ReleaseManagerTest.svelte:83-89`
- Modify: `frontend/TestRun/DriverMatrixBreakdown.svelte:137-147`
- Test: `frontend/AdminPanel/ReleaseManagerGroup.test.ts`

**Internals:**
- Both editor overlays (P3): the backdrop `.row` gains `role="dialog"`,
  `aria-modal="true"`, `aria-label="Edit group"` / `"Edit test"`,
  `tabindex="-1"`, `use:overlayFocus={editing}` and an Escape `onkeydown`
  that sets `editing = false`. The `onmousedown={self(...)}` backdrop close stays.
- `DriverMatrixBreakdown`: the `svelte-ignore` line goes; the toggle
  `<div>` becomes `<button type="button" class="ms-1 rounded px-2 py-1 border-0 {displayInfo.class} text-white" aria-pressed={displayInfo.show}>`.
  The `.cursor-pointer` rule goes if nothing else uses it.
- `suppressedSvelteCodes` is `[]`. Keep the `onwarn` hook: it is the place
  for a future entry with a stated reason.

- [x] Remove the last code; the build shows 3 warnings of it.
- [x] Add to `ReleaseManagerGroup.test.ts`: Edit opens the editor as a
      dialog named `Edit group` with the focus; Escape closes it and returns
      the focus to Edit. Run it and confirm the failure.
- [x] Make the change. `yarn build` prints no `a11y_*` line; `svelte-check`
      prints only the CheckParam warning.
- [x] Run `yarn test` and pre-commit, then commit.

## Task 7 — Icon-only button names

**Files:** the 33 components the search below lists on `14e76bed`, plus
`frontend/WorkArea/TestRuns.svelte`; test: `frontend/WorkArea/TestRunsSelector.test.ts`.

**Internals:** each button gains `title="X" aria-label="X"` (spec, P6);
a toggle gains `aria-expanded` or `aria-pressed` as listed. Hidden copy
buttons (`d-none`, shown on hover) get names as well. `TestRunsSelector`
gains a `graphShown = false` prop, and `TestRuns` passes
`graphShown={clickedGraph}`; a Vitest case checks `aria-expanded` and
`aria-controls` on "Show graph".

The search; it prints `0` when done:

```bash
python3 - <<'PY'
import re, glob
attr = r'((?:[^>{]|\{(?:[^{}]|\{[^{}]*\})*\})*)'
n = 0
for f in sorted(glob.glob('frontend/**/*.svelte', recursive=True)):
    s = open(f).read()
    for m in re.finditer(r'<button\b' + attr + r'>(.*?)</button>', s, re.S):
        a, body = m.group(1), m.group(2)
        rest = re.sub(r'<Fa\b' + attr + r'/>|<i\b[^>]*>\s*</i>|\{#if[^}]*\}|\{:else[^}]*\}|\{/if\}', '', body, flags=re.S).strip()
        if not rest and ('<Fa' in body or '<i ' in body) and not re.search(r'aria-label|\btitle=|aria-labelledby', a):
            n += 1
            print(f'{f}:{s.count(chr(10), 0, m.start()) + 1}')
print(n)
PY
```

| Component | Names |
|---|---|
| AdminPanel/UserManager | `Dismiss error` |
| AdminPanel/ViewWidget | `Edit widget`, `Remove widget` |
| AdminPanel/ViewsManager | `Add widget` |
| Discussion/CommentEditor | `Bold`, `Italic`, `Underline`, `Quote`, `Code`, `Link`, `Numbered list`, `Bulleted list`, `Task list` |
| Discussion/MentionSelector | `Close` |
| Profile/NotificationsReader | `Previous page`, `Next page` |
| Profile/PlannedJob | `Details` + `aria-expanded` |
| Profile/ProfileJob | `Investigation` + `aria-expanded` |
| ReleaseDashboard/TestPopoutSelector | `Scroll to top` |
| ReleasePlanner/CommentTableRow | `Save comment`, `Edit comment` |
| ReleasePlanner/ReleasePlan | `Details` + `aria-expanded`, `Create a plan from this one`, `Edit plan`, `Copy plan to a release`, `Delete plan` |
| ReleasePlanner/ReleasePlanCreator | `Grid view`, `Split group into tests`, `Remove` |
| ReleasePlanner/ReleasePlanEditor | `Remove test` |
| ReleasePlanner/ReleasePlannerGridView | `Deselect test`, `Deselect group` |
| ReleasePlanner/Schedule | `Close`, `Reassign` |
| Teams/TeamDetail | `Edit name` |
| Teams/TeamMember | `All jobs` (Bootstrap's collapse sets `aria-expanded`) |
| TestRun/Components/ResultTable | `Copy as Markdown` |
| TestRun/Pytest/PytestItem | `Details` + `aria-expanded`, `Copy message`, `Copy value` |
| TestRun/ResultsGraph | `Copy to clipboard` (the modal copy button, away from the tooltip code) |
| TestRun/RuntimeConfig | `Details` + `aria-expanded`, `Copy parameter` |
| TestRun/SCT/SctEvent | `Copy message` |
| TestRun/SCT/SctNemesis | `Events` + `aria-expanded` |
| TestRun/SCT/SctSetup | `Details` + `aria-expanded`, `Copy command` |
| TestRun/SCTSubTests/Gemini/GeminiTabBodyComponent | `Copy command` |
| Views/ViewRow | `Favorite` + `aria-pressed` |
| Views/Widgets/PytestWidget/PytestResultRow | `Select test`, `Details` + `aria-expanded`, `Copy message`, `Filter by this value`, `Copy value` |
| Views/Widgets/PytestWidget/ViewPytestOverview | `Remove marker`, `Negate filter` + `aria-pressed`, `Remove filter` |
| Views/Widgets/SummaryWidget/SummaryWidget | `Previous version`, `Next version`, `Details` + `aria-expanded` |
| Views/Widgets/ViewHighlights/ActionItem | `Edit` + `aria-pressed` |
| Views/Widgets/ViewHighlights/Comment | `Edit` + `aria-pressed` |
| Views/Widgets/ViewHighlights/HighlightItem | `Edit` + `aria-pressed` |
| WorkArea/TestRunsSelector | `Show graph` + `aria-expanded={graphShown}` and `aria-controls="collapse-graphs"` while shown, `Show more runs` |

- [x] Run the search; it prints 65.
- [x] Add the names. The search prints 0.
- [x] Check the diff touches no `{@html}`, `marked`, toast or tooltip line.
- [x] Run `yarn build`, `yarn test` and pre-commit, then commit
      `fix(frontend): name the icon-only buttons`.

## Task 8 — Verify and live check

**Files:** none in the repository. Scripts and screenshots go to
`/tmp/claude-1000/-home-komachi-development-argus/953332aa-7103-4aeb-981d-ae86661cd75b/scratchpad/ARGUS-276/`.

- [x] Before Task 1, capture the "before" screenshots: run the steps below
      on the plan commit, at 1920 and 1280 px wide.
- [x] Run `yarn build:dev` in the worktree. Start
      `uv run uvicorn --factory argus_backend:create_app --port 5016` as a
      background task. Never touch the user's server on :5000; stop this one
      by its task id.
- [x] Log in: `curl -c jar -F username=admin -F password=admin http://127.0.0.1:5016/auth/login`.
      Keep the `#HttpOnly_` line when reading the session cookie from the jar.
- [x] Start `google-chrome --headless=new --remote-debugging-port=9336 --user-data-dir=<scratch>/chrome`
      and drive it from a Node script over CDP: set the cookie, open a page,
      send Tab with `Input.dispatchKeyEvent` until `document.activeElement`
      is the target, then Enter or Space, and read the result from the DOM.
- [x] Sample, one per pattern, using what the dev database holds:
  - [x] `/teams/`: a TeamMember stat toggle opens on Enter, `aria-expanded` flips (P1).
  - [x] `/admin/`, releases: a group name selects on Space, `aria-current` moves (P2); Edit opens
        the editor with the focus inside, Escape closes it and the focus returns to Edit (P3).
  - [ ] `/notifications/`: a row opens on Enter (P2). The dev data holds no notification for
        the admin user.
  - [x] A test run with generic results: the `+ View` tab opens the dialog on Enter, Escape
        closes it (P1, P3).
  - [x] A release dashboard: the investigation bar expands on Enter (P1).
  - [ ] A view with a graphs widget, when one exists: a header toggles on Space (P1). No view
        on the dev data holds one.
- [x] Read Chrome's accessibility tree (`Accessibility.getPartialAXTree`) on
      two pages with icon buttons, such as a test run and the release planner,
      and confirm each sampled button has the name of Task 7.
- [x] Take the "after" screenshots and compare each element with its "before"
      at both widths. A shifted layout is a bug in its task's commit.
- [x] Run `uv run pre-commit run --all-files`, `yarn test` and `yarn build`.
      `yarn build` prints no `a11y_*` line and `suppressedSvelteCodes` is `[]`.
- [x] `uv run pytest`, on the finished branch: 1980 passed.
- [x] Live-check the Tab wrap in "Edit group": Tab past Update reaches the first control,
      Shift+Tab from there returns to Update.
- [x] Stop the server and Chrome by their task ids.

## Task 9 — Click area of the group rows and the graph headers

**Files:**
- Modify: `frontend/AdminPanel/ReleaseManager.svelte` (the group `<li>`)
- Modify: `frontend/AdminPanel/ReleaseManagerGroup.svelte`
- Modify: `frontend/Views/Widgets/GraphsWidget/GraphsWidget.svelte`

**Internals:**
- Group row (spec, P2): the `<li>` gains `p-0`. The name button trades
  `p-0` for `py-2 ps-3 pe-0` and a scoped `group-select` class that sets
  `--bs-btn-focus-box-shadow` to the same ring drawn `inset`. The row
  `<div>` gains `pe-3`, and the Edit and Delete wrappers gain `py-2`, so the
  row keeps its height.
- GraphsWidget headers (spec, P1): each `.card-header` gains `p-0`, and its
  button trades `p-0` for `py-2 px-3`.

No Vitest test: jsdom has no layout, so the click area is a live check.

- [x] Make the changes. `yarn build` prints no `a11y_*` line.
- [x] Live check at 1920 and 1280 px against screenshots of `057b462d`:
      the group rows match pixel for pixel; a mouse click on the left, top
      and bottom edge of a group row selects it, and the switch, Edit and
      Delete do not. No dev view holds a graphs widget, so its header markup
      is checked as a replica on a view page: the button covers the header,
      which keeps its size.
- [x] Run `yarn test`, pre-commit and `yarn build`, then commit.

## Task 10 — Focus of the investigation bar

**Files:**
- Modify: `frontend/Stats/NumberStats.svelte`
- Test: `frontend/Stats/NumberStats.test.ts` (new)

**Internals:** (spec, P1) `allowedStatuses` moves from an `{@const}` to a
`$derived` in the script. The bar, Hide and each quick-select button are
bound with `bind:this`; the quick-select buttons into a record keyed
`"{investigationStatus}:{status}"`. `toggleExtendedInvestigations` ends
with `focus({ preventScroll: true })` on the first bound quick-select button
in render order, or Hide, when it opens, and on the bar when it closes.

- [ ] Write `NumberStats.test.ts`: the bar starts with `aria-expanded="false"`;
      a click sets it to `"true"` and focuses the first quick-select button;
      Hide sets it back to `"false"` and focuses the bar; with no counts the
      focus goes to Hide. Run it and confirm the focus cases fail.
- [ ] Make the change. `yarn build` prints no `a11y_*` line.
- [ ] Live check: the investigation bar matches its screenshots pixel for
      pixel; Enter on the bar moves the focus into the panel, and Enter on
      Hide collapses it and brings the focus back to the bar.
- [ ] Run `yarn test`, pre-commit and `yarn build`, then commit.
