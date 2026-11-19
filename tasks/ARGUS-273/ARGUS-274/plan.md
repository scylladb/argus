# ARGUS-274 — implementation plan

**Spec:** `tasks/ARGUS-273/ARGUS-274/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Svelte 5 runes. Reach the DOM through `bind:this` or an action, never
  `querySelector`. A DOM escape hatch lives in a small helper module next to
  its component, with its own test.
- No `z-index` in ModalWindow. Never set `overflow` or `position` on `html`
  or `body`.
- No caller file changes, except the Escape case of
  `frontend/Common/ConfirmDeleteModal.test.ts`.
- Do not edit the files of the sibling tasks: `frontend/font-awesome.js`,
  `frontend/font-awesome.scss`, `templates/base.html.j2`, the markdown
  rendering in `frontend/Discussion/` and `frontend/Views/Widgets/ViewHighlights/`,
  and `vite.config.ts`. Task 4 edits `vite.config.ts` locally and restores it
  before any commit.
- No comment that explains the change. Fix a comment only when it became
  wrong.
- Commit header `type(scope): summary`, at most 72 characters, with no key.
  The body ends with `Task: ARGUS-274`. Stage by explicit path. Commit with
  `uv run git commit`.
- Verify sequence (`CLAUDE.md`, `Commands`): `uv run pre-commit run
  --all-files`, `uv run pytest` (Docker), `yarn test`, then `yarn build` for
  a frontend change.

## Task 1 — ModalWindow on `<dialog>`

**Files:**
- Modify: `frontend/Common/ModalWindow.svelte` (whole file, lines 1-67)
- Create: `frontend/vitest.setup.ts`
- Modify: `vitest.config.mjs:9-12` (add `setupFiles`)
- Test: `frontend/Common/ModalWindow.test.ts` (new)
- Modify: `frontend/Common/ConfirmDeleteModal.test.ts:50-58`

**Internals:**
- `frontend/vitest.setup.ts` gives jsdom the two dialog methods it lacks,
  only when they are missing. `showModal()` sets `open`. `close()` returns
  when the dialog is not open; otherwise it removes `open` and dispatches a
  `close` Event. It models no top layer, no focus move and no Escape.
  `vitest.config.mjs` adds `setupFiles: ["frontend/vitest.setup.ts"]`. The
  file name does not match the `frontend/**/*.test.{js,ts}` include.
- `ModalWindow.svelte`:
  - Keep `createEventDispatcher`, the `Props` interface, the defaults and
    `<svelte:window bind:innerWidth>`. Drop `handleKeyDown`, the `onkeydown`
    on the window and the unused `onMount` and `onDestroy` import.
  - `const titleId = `${$props.id()}-title`;` and
    `let dialog: HTMLDialogElement | undefined = $state();`
  - One `$effect`. Save `opener`: `document.activeElement` when it is an
    `HTMLElement` other than `document.body`, else `null`. Then call
    `dialog.showModal()`. The teardown calls `opener.focus()` when
    `opener?.isConnected` and `document.activeElement` is `null` or
    `document.body`.
  - Markup: `<dialog bind:this={dialog} class="modal-window"
    aria-labelledby={title ? titleId : undefined} onclose={() =>
    dispatch("modalClose")}>` around today's inner markup. The `h5` gets
    `id={titleId}` and renders `{@render title?.()}`. The body renders
    `{@render body?.()}`. The close button keeps its classes, its
    `aria-label`, its `title` and its `onclick` dispatch.
  - Style: keep `.w-50` and `.w-75`. Replace `.modal-window` with the two
    rules of the spec's Design section: `dialog.modal-window` and
    `dialog.modal-window::backdrop`. Set no `display` on the dialog.

- [ ] Write `ModalWindow.test.ts`. Render through `@testing-library/svelte`
  with snippets from `createRawSnippet`, and collect `modalClose` through the
  `events` option. Cases:
  - `opens_a_dialog_named_by_its_title`: `getByRole("dialog", { name })`
    finds it, `open` is true, and the title and the body render inside it.
  - `has_no_accessible_name_without_a_title`: no `aria-labelledby`.
  - `dispatches_modalClose_from_the_close_button`: one call.
  - `dispatches_modalClose_when_the_dialog_closes`: `dialog.close()`, the
    path that Escape takes in a browser, gives one call.
  - `ignores_an_Escape_keydown_on_the_window`: zero calls. This pins the
    nested-modal fix.
  - `returns_the_focus_to_the_opener_on_unmount`: a button appended to
    `document.body` and focused, then render, focus the close button, and
    `unmount()`. The button has the focus.
  - `leaves_the_focus_alone_when_it_moved_outside`: focus a second outside
    button before `unmount()`. It keeps the focus.
  - `does_not_throw_when_the_opener_is_gone`: remove the opener before
    `unmount()`. The focus is on `document.body`.
- [ ] Run `yarn test frontend/Common/ModalWindow.test.ts` and confirm the
  failures: no dialog role, and the Escape case dispatches.
- [ ] Add `vitest.setup.ts` and the `setupFiles` line, then rewrite
  `ModalWindow.svelte`.
- [ ] In `ConfirmDeleteModal.test.ts`, the case `cancels from the Cancel
  button, the close button and Escape` replaces
  `fireEvent.keyDown(window, { key: "Escape" })` with
  `(screen.getByRole("dialog") as HTMLDialogElement).close()`. Rename it to
  `... and a dialog close`.
- [ ] Run `yarn test`. The Sidebar, ChatConfigManager, TestRunsSelector,
  Issues and ResultTable suites pass unchanged.
- [ ] Run the verify sequence.
- [ ] Commit `improvement(frontend): open ModalWindow as a native dialog`.

What jsdom proves: the dialog role and name, the `modalClose` mapping, no
window Escape listener, and the focus rule at teardown. What it cannot
prove: the top layer, the inert page, the focus containment, Escape to
`cancel` and `close`, the backdrop and the scroll containment. Task 5 checks
those in Chrome.

## Task 2 — Results graph tooltip inside the dialog

**Files:**
- Create: `frontend/TestRun/chartTooltip.ts`
- Modify: `frontend/TestRun/ResultsGraph.svelte:192-198` (create and append)
  and `:253-257` (position)
- Test: `frontend/TestRun/chartTooltip.test.ts`

**Internals:**

```ts
export function tooltipAnchor(
    canvas: HTMLCanvasElement, caretX: number, caretY: number,
): { host: HTMLElement; left: number; top: number }
```

- `host` is `canvas.closest("dialog") ?? document.body`.
- For `document.body`, `left = rect.left + window.scrollX + caretX` and
  `top = rect.top + window.scrollY + caretY`, as today.
- For a dialog, `left = rect.left - hostRect.left + host.scrollLeft + caretX`,
  and the same with `top` and `scrollTop`.
- In the `external` handler, ResultsGraph calls `tooltipAnchor`. It appends
  the tooltip element to `host` when its parent is a different element, and
  writes `left` and `top`. The other `getElementById("chartjs-tooltip")`
  removals stay, because they find the element in either host.

- [ ] Write `chartTooltip.test.ts` with stubbed `getBoundingClientRect`,
  scroll offsets and scroll positions:
  `anchors_to_the_body_in_page_coordinates` and
  `anchors_to_the_enclosing_dialog_with_its_scroll_offset`.
- [ ] Run it and confirm the failure: the module is missing.
- [ ] Write `chartTooltip.ts` and change the two hunks of `ResultsGraph.svelte`.
- [ ] Run the verify sequence.
- [ ] Commit `fix(results): keep the graph tooltip inside an open modal`.

## Task 3 — Toast stack above an open modal

**Files:**
- Create: `frontend/Alerts/topLayer.ts`
- Modify: `frontend/Alerts/AlertWidget.svelte:44` and `:58` (the two
  `#alertWidget` elements), and its style block
- Test: `frontend/Alerts/topLayer.test.ts`

**Internals:**

```ts
export function topLayer(node: HTMLElement, key: unknown): ActionReturn<unknown>
```

- With no `showPopover` in `HTMLElement.prototype`, it does nothing.
- On mount it sets `popover="manual"` and calls `showPopover()`.
- `update(key)` with a new key calls `hidePopover()` and then
  `showPopover()`. The stack becomes the newest top-layer element, above any
  modal that opened after it.
- `destroy` calls `hidePopover()` when the popover is open.
- AlertWidget puts `use:topLayer={messages.at(-1)?.id}` on both
  `#alertWidget` elements.
- Style: `#alertWidget[popover]` resets the popover defaults that the user
  agent sheet sets: `margin: 0; padding: 0; border: 0; background:
  transparent; color: inherit; overflow: visible`. The desktop stack sets
  `inset: 0 auto auto 0`. The mobile bar sets `inset: auto 0 0 0` and
  `width: auto`, and keeps its `pointer-events: none`.

- [ ] Write `topLayer.test.ts` with `showPopover` and `hidePopover` stubbed
  on the prototype: `does_nothing_without_popover_support`,
  `shows_the_node_as_a_manual_popover_on_mount`,
  `raises_the_node_again_when_the_key_changes`,
  `keeps_the_node_in_place_when_the_key_repeats`.
- [ ] Run it and confirm the failure.
- [ ] Write `topLayer.ts`, then change the markup and the style of
  AlertWidget.
- [ ] Run `yarn test frontend/Alerts`. `AlertWidget.test.ts` passes
  unchanged, because jsdom has no Popover.
- [ ] Run the verify sequence.
- [ ] Commit `fix(alerts): show toasts above an open modal`.

## Task 4 — No suppressed a11y warning from ModalWindow

**Files:** none committed. `vite.config.ts` changes locally for one build.

- [ ] Replace the `suppressedSvelteCodes` array in `vite.config.ts` with
  `[]`.
- [ ] Run `yarn build:dev > <scratch>/build-unsuppressed-after.log 2>&1`.
- [ ] Run `git checkout -- vite.config.ts` and confirm that `git status
  --short vite.config.ts` prints nothing.
- [ ] `grep -A1 "Common/ModalWindow.svelte\|Alerts/AlertWidget.svelte\|Alerts/topLayer\|TestRun/chartTooltip"`
  on the log prints no `a11y_` code. The baseline is the round-1 log: 38
  warnings, none in these files. Record the count in the pull request body.

## Task 5 — Live check in headless Chrome

**Files:** none committed. Scripts and screenshots go to the scratch
directory `ARGUS-274/live/`.

Setup:

- [ ] Before Task 1, on the branch tip, run `yarn build:dev` and take the
  "before" screenshots of L1 and L5 below.
- [ ] After Task 3, run `yarn build:dev`. Start `uv run uvicorn --factory
  argus_backend:create_app --port 5014` as a background task, and stop it
  by its task id. Never use `pkill`: the user's own server runs on :5000.
- [ ] Log in with `curl -c <jar> -d username=admin -d password=admin
  http://127.0.0.1:5014/auth/login`. Keep the `#HttpOnly_` session line when
  you parse the jar, and pass the cookie to Chrome with
  `Network.setCookie`.
- [ ] Start `google-chrome --headless=new --remote-debugging-port=9334
  --user-data-dir=<scratch>/chrome-profile`, and drive it from Node 22 with
  the built-in `WebSocket`. Click and type through `Input.dispatch*`, so that
  focus and user activation are real. `probe/probe.mjs` from round 1 has the
  helpers.

Checks. Each one records pass or fail, with a screenshot for L1, L5, L6 and
L7:

- [ ] L1 `/admin/users`, the change email modal. On open the focus is in the
  dialog, and the dialog matches `:modal`. Ten Tab presses keep the focus in
  the dialog. `elementFromPoint` over a page button returns the dialog.
  Escape closes the dialog and the focus returns to the trigger. Reopen,
  click Cancel: the focus returns to the trigger.
- [ ] L2 `/release/<name>/planner`, the plan creator, then its Grid View.
  The first Escape closes only the grid view, and the focus is on the Grid
  View button. The second Escape closes the creator.
- [ ] L3 In the plan creator, open a svelte-select list and press Escape.
  The list closes and the modal stays open.
- [ ] L4 A `mouseWheel` over the backdrop and over a short modal leaves
  `window.scrollY` unchanged.
- [ ] L5 A test run's Results tab, then a column header that opens the graph
  modal. Hover a point: `#chartjs-tooltip` is inside the dialog and wins the
  hit test. Click the point: the "Open" link wins the hit test.
- [ ] L6 Make an action in a modal fail, for example a proxy tunnel host the
  server rejects. The toast is drawn above the backdrop.
- [ ] L7 At 400 px width, `/workspace`, the Sidebar drawer: delete a test.
  Typing in the confirmation input changes its value, and the focus stays
  in the dialog.
- [ ] Record a check that the dev data cannot reach as skipped, with the
  reason, in the pull request body.
