# ARGUS-276 — implementation plan

**Spec:** `tasks/ARGUS-273/ARGUS-276/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- The first box of Task 7, the "before" screenshots, runs before Task 1.
- One commit per task, in the order below. A task's commit removes its code
  from `suppressedSvelteCodes` in `vite.config.ts` and touches no other line
  of that file.
- The failing check of every task is the build: remove the code first, run
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
  the build count and the live check of Task 7.
- Each task runs `uv run pre-commit run --all-files`, `yarn build` and
  `yarn test`. Task 7 runs the full verify sequence, `uv run pytest`
  included.
- Never touch `frontend/Common/ModalWindow.svelte`, the Font Awesome files,
  `templates/base.html.j2`, or the `{@html}` lines of the ARGUS-278
  components. An `<i class="fas">` moves with its parent unchanged.
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
`<button type="button" class="nav-link" class:active aria-current={activeTab === i ? "page" : undefined}>`.
Bootstrap styles `button.nav-link` as a tab.

- [ ] Remove the code; `yarn build` shows 1 `a11y_missing_attribute`.
- [ ] Add a test: each tab is a `button` named by its text, and clicking
      `+ View` opens the New View form. Run it and confirm the failure.
- [ ] Swap the element. The build shows no `a11y_missing_attribute`; the
      click_events and no_static counts drop by 1 each.
- [ ] Run `yarn test` and pre-commit, then commit
      `fix(frontend): turn on the a11y_missing_attribute warning`.

## Task 2 — `a11y_interactive_supports_focus`

**Files:**
- Modify: `vite.config.ts`
- Modify: `frontend/Teams/TeamMember.svelte:85`, `:109`

**Internals:** each `<div class="px-2" role="button">` becomes
`<button type="button" class="btn btn-sm btn-link text-reset text-decoration-none px-2 py-0 border-0 rounded-0" class:border-end aria-expanded={show...}>`.
The visible text stays the icon and the count. `aria-label` reads
`"{stats.total} not investigated, show details"` and
`"{stats.total} investigated, show details"`, so the visible count is part
of the name.

- [ ] Remove the code; the build shows 2 `a11y_interactive_supports_focus`.
- [ ] Swap both elements. The build shows none; click_events drops by 2.
- [ ] Run `yarn test` and pre-commit, then commit.

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
  `<button type="button" class="btn btn-link text-reset text-decoration-none text-start p-0 border-0 flex-fill" aria-current={selected ? "true" : undefined} onclick={onselect}>`.
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
  flush borders; the screenshots of Task 7 confirm the look.

- [ ] Remove the code; the build shows 2 warnings of it.
- [ ] Write `ReleaseManagerGroup.test.ts`: the name button calls `onselect`;
      `aria-current="true"` follows `selected`; Edit and Delete do not call
      `onselect`. Run it and confirm the failure.
- [ ] Make the change. The build shows none of this code; click_events
      drops by 4 and no_static by 2.
- [ ] Run `yarn test` and pre-commit, then commit.

## Task 4 — `a11y_no_noninteractive_element_interactions`

**Files:**
- Modify: `vite.config.ts`
- Create: `frontend/Common/overlayFocus.ts`
- Test: `frontend/Common/overlayFocus.test.ts` (new)
- Modify: `frontend/AdminPanel/AvatarCropper.svelte:90`
- Modify: `frontend/TestRun/ResultsGraphs.svelte:3-5, 258-331`
- Test: `frontend/TestRun/ResultsGraphs.test.ts`

**Internals:**
- `overlayFocus(node: HTMLElement, active = true): ActionReturn<boolean>`.
  On open it stores `document.activeElement` and calls
  `node.focus({ preventScroll: true })`. On close or destroy it returns the
  focus to the stored element when that is still connected. `update(next)`
  opens or closes on a change of `active`. Same idea as `dialogOpen` in
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

- [ ] Remove the code; the build shows 4 warnings of it, and 1
      `a11y_no_noninteractive_tabindex`.
- [ ] Write `overlayFocus.test.ts`: focus moves to the node on mount and on
      `update(true)`, and back to the trigger on `update(false)` and on
      destroy. Add to `ResultsGraphs.test.ts`: the New View dialog is found
      by `getByRole("dialog", { name: "New View" })` and has the focus;
      Escape closes it; a click on the backdrop closes it; a click in the
      form does not. Run them and confirm the failures.
- [ ] Make the change. The build shows no warning of this code and no
      `a11y_no_noninteractive_tabindex`; click_events drops by 6.
- [ ] Run `yarn test` and pre-commit, then commit.

## Task 5 — `a11y_click_events_have_key_events`

**Files:**
- Modify: `vite.config.ts`
- Modify: `frontend/Stats/NumberStats.svelte:119-133`
- Modify: `frontend/Views/Widgets/GraphsWidget/GraphsWidget.svelte:165-171, 176-185`
- Modify: `frontend/TestRun/ResultsGraph.svelte:2, 4, 367-368`

**Internals:**
- `NumberStats`: the investigation bar `<div ... cursor-pointer onclick>`
  becomes `<button type="button" class="align-self-start d-inline-flex shadow-sm overflow-hidden border rounded p-0 bg-transparent text-reset" aria-expanded={extended} aria-controls=...>`.
  An `extended` `$state` flips in `toggleExtendedInvestigations`, which the
  Hide button also calls. The inner `<div role="button">` lose the role. The
  unused `.cursor-pointer` rule goes if nothing else uses it.
- `GraphsWidget`: each `.card-header` loses its `onclick`; its heading wraps
  a `<button type="button" class="btn w-100 text-start p-0 border-0 d-flex align-items-center" aria-expanded aria-controls="test-{testId}">`
  (and `view-{view.id}`) holding the existing `<i>` chevron and the name.
- `ResultsGraph`: `.modal-content` loses `onclick={stopPropagation(bubble('click'))}`;
  no component listens to `click` on `ResultsGraph` (P4). The
  `createBubbler` and `stopPropagation` imports and the `bubble` constant go;
  `run` stays. Its `×` button
  gains `aria-label="Close"`.

- [ ] Remove the code; the build shows 4 warnings of it.
- [ ] Make the change. The build shows none; no_static drops by 4.
- [ ] Run `yarn test` and pre-commit, then commit.

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

- [ ] Remove the last code; the build shows 3 warnings of it.
- [ ] Add to `ReleaseManagerGroup.test.ts`: Edit opens the editor as a
      dialog named `Edit group` with the focus; Escape closes it and returns
      the focus to Edit. Run it and confirm the failure.
- [ ] Make the change. `yarn build` prints no `a11y_*` line; `svelte-check`
      prints only the CheckParam warning.
- [ ] Run `yarn test` and pre-commit, then commit.

## Task 7 — Verify and live check

**Files:** none in the repository. Scripts and screenshots go to
`/tmp/claude-1000/-home-komachi-development-argus/953332aa-7103-4aeb-981d-ae86661cd75b/scratchpad/ARGUS-276/`.

- [ ] Before Task 1, capture the "before" screenshots: run the steps below
      on the plan commit, at 1920 and 1280 px wide.
- [ ] Run `yarn build:dev` in the worktree. Start
      `uv run uvicorn --factory argus_backend:create_app --port 5016` as a
      background task. Never touch the user's server on :5000; stop this one
      by its task id.
- [ ] Log in: `curl -c jar -F username=admin -F password=admin http://127.0.0.1:5016/auth/login`.
      Keep the `#HttpOnly_` line when reading the session cookie from the jar.
- [ ] Start `google-chrome --headless=new --remote-debugging-port=9336 --user-data-dir=<scratch>/chrome`
      and drive it from a Node script over CDP: set the cookie, open a page,
      send Tab with `Input.dispatchKeyEvent` until `document.activeElement`
      is the target, then Enter or Space, and read the result from the DOM.
- [ ] Sample, one per pattern, using what the dev database holds:
  - [ ] `/teams/`: a TeamMember stat toggle opens on Enter, `aria-expanded` flips (P1).
  - [ ] `/admin/`, releases: a group name selects on Space, `aria-current` moves (P2); Edit opens
        the editor with the focus inside, Escape closes it and the focus returns to Edit (P3).
  - [ ] `/notifications/`: a row opens on Enter (P2).
  - [ ] A test run with generic results: the `+ View` tab opens the dialog on Enter, Escape
        closes it (P1, P3).
  - [ ] A release dashboard: the investigation bar expands on Enter (P1).
  - [ ] A view with a graphs widget, when one exists: a header toggles on Space (P1).
- [ ] Take the "after" screenshots and compare each element with its "before"
      at both widths. A shifted layout is a bug in its task's commit.
- [ ] Run the full verify sequence from the `Commands` section of `CLAUDE.md`.
- [ ] Stop the server and Chrome by their task ids.
