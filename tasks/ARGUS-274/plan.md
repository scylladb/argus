# ARGUS-274 — implementation plan

**Spec:** `tasks/ARGUS-274/spec.md`

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
  `frontend/Common/ConfirmDeleteModal.test.ts` and `dismissible={false}` on
  the form modals (Task 7).
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
  - `const titleId = $props.id();` and
    `let dialog: HTMLDialogElement | undefined = $state();`
  - One `$effect`. Save `opener`: `document.activeElement` when it is an
    `HTMLElement` other than `document.body`, else `null`. Then call
    `dialog.showModal()`. The teardown calls `opener.focus()` when
    `opener?.isConnected` and `document.activeElement` is `null` or
    `document.body`.
  - Markup: `<dialog bind:this={dialog} class="modal-window"
    aria-labelledby={title ? titleId : undefined} onpointerdown=…
    onpointerup=… onclick={closeOnOutsideClick} onclose={() => dispatch("modalClose")}>`
    around today's inner markup.
    The frame div, `d-flex … p-4`, gets `bind:this={frame}`, with
    `let frame: HTMLElement | undefined = $state();`. The `h5` gets
    `id={titleId}` and renders `{@render title?.()}`. The body renders
    `{@render body?.()}`. The close button keeps its classes, its
    `aria-label`, its `title` and its `onclick` dispatch.
  - Style: keep `.w-50` and `.w-75`. Replace `.modal-window` with the two
    rules of the spec's Design section: `dialog.modal-window` and
    `dialog.modal-window::backdrop`. Set no `display` on the dialog.
  - Light dismiss: `outside(target)` is `target === dialog || target ===
    frame`. `onpointerdown` stores `outside(event.target)` in a plain
    `pressedOutside` flag, and `onpointerup` in `releasedOutside`.
    `closeOnOutsideClick` calls `dialog.close()` when both flags and
    `outside(event.target)` are true, and clears both flags.

- [x] Write `ModalWindow.test.ts`. Render through `@testing-library/svelte`
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
  - `closes_on_a_click_outside_the_box`: `pointerDown`, `pointerUp` and
    `click` on the dialog, then the same on the frame. Each closes the dialog
    and gives one `modalClose`.
  - `stays_open_on_a_click_inside_the_box`: `pointerDown`, `pointerUp` and
    `click` on the title. No call, and `open` stays true.
  - `stays_open_after_a_drag_from_the_box_to_the_outside`: `pointerDown` on
    a body input, `pointerUp` and `click` on the dialog. No call.
  - `stays_open_after_a_drag_from_the_outside_into_the_box`: `pointerDown`
    on the frame, `pointerUp` on a body input, `click` on the frame. No
    call.
- [x] Run `yarn test frontend/Common/ModalWindow.test.ts` and confirm the
  failures: no dialog role, and the Escape case dispatches.
- [x] Add `vitest.setup.ts` and the `setupFiles` line, then rewrite
  `ModalWindow.svelte`.
- [x] In `ConfirmDeleteModal.test.ts`, the case `cancels from the Cancel
  button, the close button and Escape` replaces
  `fireEvent.keyDown(window, { key: "Escape" })` with
  `(screen.getByRole("dialog") as HTMLDialogElement).close()`. Rename it to
  `... and a dialog close`.
- [x] Run `yarn test`. The Sidebar, ChatConfigManager, TestRunsSelector,
  Issues and ResultTable suites pass unchanged.
- [x] Run the verify sequence.
- [x] Commit `improvement(frontend): open ModalWindow as a native dialog`.

What jsdom proves: the dialog role and name, the `modalClose` mapping, no
window Escape listener, the focus rule at teardown, and the outside rule of
light dismiss. What it cannot
prove: the top layer, the inert page, the focus containment, Escape to
`cancel` and `close`, the backdrop, the scroll containment, and which
targets real pointer input produces. Task 5 checks
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

- [x] Write `chartTooltip.test.ts` with stubbed `getBoundingClientRect`,
  scroll offsets and scroll positions:
  `anchors_to_the_body_in_page_coordinates` and
  `anchors_to_the_enclosing_dialog_with_its_scroll_offset`.
- [x] Run it and confirm the failure: the module is missing.
- [x] Write `chartTooltip.ts` and change the two hunks of `ResultsGraph.svelte`.
- [x] Run the verify sequence.
- [x] Commit `fix(results): keep the graph tooltip inside an open modal`.

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
- `destroy` calls `hidePopover()`. On a popover that is already hidden it
  does nothing.
- AlertWidget puts `use:topLayer={messages.at(-1)?.id}` on both
  `#alertWidget` elements.
- The desktop stack trades `position-absolute` for `position-fixed`, keeping
  `top-0 start-0`. In the top layer an absolute box is placed against the
  initial containing block and scrolls with the page. Without Popover, a
  fixed box at the origin inside the fixed `#argusErrors` lands where the
  absolute one did.
- Style, in `:global(...)` rules because the action sets `popover` at
  runtime and Svelte prunes a scoped attribute selector it cannot see:
  `#alertWidget[popover]` resets `margin`, `border`, `background` and
  `color` from the user agent sheet. The desktop stack adds `inset: 0 auto
  auto 0; padding: 0; overflow: visible`. The mobile bar adds `inset: auto 0
  0 0; width: auto` and keeps its padding and `pointer-events: none`.

- [x] Write `topLayer.test.ts` with `showPopover` and `hidePopover` stubbed
  on the prototype: `does_nothing_without_popover_support`,
  `shows_the_node_as_a_manual_popover_on_mount`,
  `raises_the_node_again_when_the_key_changes`,
  `keeps_the_node_in_place_when_the_key_repeats`,
  `hides_the_node_on_destroy`.
- [x] Run it and confirm the failure.
- [x] Write `topLayer.ts`, then change the markup and the style of
  AlertWidget.
- [x] Run `yarn test frontend/Alerts`. `AlertWidget.test.ts` passes
  unchanged, because jsdom has no Popover.
- [x] Run the verify sequence.
- [x] Commit `fix(alerts): show toasts above an open modal`.

## Task 4 — No suppressed a11y warning from ModalWindow

**Files:** none committed. `vite.config.ts` changes locally for one build.

- [x] Replace the `suppressedSvelteCodes` array in `vite.config.ts` with
  `[]`.
- [x] Run `yarn build:dev > <scratch>/build-unsuppressed-after.log 2>&1`.
- [x] Run `git checkout -- vite.config.ts` and confirm that `git status
  --short vite.config.ts` prints nothing.
- [x] `grep -A1 "Common/ModalWindow.svelte\|Alerts/AlertWidget.svelte\|Alerts/topLayer\|TestRun/chartTooltip"`
  on the log prints no `a11y_` code from these files. The two warnings
  that `ResultsGraph.svelte` prints are the ones from before this task. The
  baseline is the round-1 log, with none in these files. Record the count in
  the pull request body.

## Task 5 — Live check in headless Chrome

**Files:** none committed. Scripts and screenshots go to the scratch
directory `ARGUS-274/live/`.

Setup:

- [x] Before Task 1, on the branch tip, run `yarn build:dev` and take the
  "before" screenshots of L1 and L5 below.
- [x] After Task 3, run `yarn build:dev`. Start `uv run uvicorn --factory
  argus_backend:create_app --port 5014` as a background task, and stop it
  by its task id. Never use `pkill`: the user's own server runs on :5000.
- [x] Log in with `curl -c <jar> -d username=admin -d password=admin
  http://127.0.0.1:5014/auth/login`. Keep the `#HttpOnly_` session line when
  you parse the jar, and pass the cookie to Chrome with
  `Network.setCookie`.
- [x] Start `google-chrome --headless=new --remote-debugging-port=9334
  --user-data-dir=<scratch>/chrome-profile`, and drive it from Node 22 with
  the built-in `WebSocket`. Click and type through `Input.dispatch*`, so that
  focus and user activation are real. `probe/probe.mjs` from round 1 has the
  helpers.

Checks. Each one records pass or fail, with a screenshot for L1, L5, L6, L7,
L8, L10 and L11:

- [x] L1 `/admin/users`, the change email modal. On open the focus is in the
  dialog, and the dialog matches `:modal`. Ten Tab presses keep the focus in
  the dialog, or leaves the document for the browser UI and comes back.
  `elementFromPoint` over a page button returns the dialog or a node in it.
  Escape closes the dialog and the focus returns to the trigger. Reopen,
  click Cancel: the focus returns to the trigger.
- [x] L2 `/release/<name>/planner`, the plan creator, then its Grid View.
  The first Escape closes only the grid view, and the focus is on the Grid
  View button. The second Escape closes the creator.
- [x] L3 In the plan creator, open a svelte-select list and press Escape.
  The list closes and the modal stays open.
- [x] L4 A `mouseWheel` over the backdrop and over a short modal leaves
  `window.scrollY` unchanged.
- [x] L5 A test run's Results tab, then a column header that opens the graph
  modal. The dev data has no graph for any run, so the check serves a
  synthetic graph in the backend's shape through `Fetch.fulfillRequest`.
  Hover a point: `#chartjs-tooltip` is inside the dialog and wins the hit
  test. Click the point: the "Open" link wins the hit test.
- [x] L6 Make an action in a modal fail: the Sidebar delete confirmation,
  with the `DELETE` answered 500 through `Fetch.fulfillRequest`, so that
  nothing reaches the server. The toast is drawn above the backdrop, where
  it sat before the change.
- [x] L7 Light dismiss on the L1 modal. A click on the dim area beside the
  box closes it, and the focus returns to the trigger. A click on the box's
  text keeps it open. A drag that selects text in the email input and ends
  outside the box keeps it open, with the typed text. A drag from the dim
  area into the email input keeps it open.
- [x] L8 Light dismiss on a form modal: the delete confirmation of the
  Sidebar, or the user manager's change password editor. Type into the
  input, drag from the input to the outside: it stays open with the text.
  Click outside: it closes.
- [x] L9 A press and a drag on the scrollbar of a tall modal, the L5 graph
  modal, keep it open.
- [x] L10 At 400 px width, `/workspace`, the Sidebar drawer: delete a test.
  Typing in the confirmation input changes its value, and the focus stays
  in the dialog.
- [x] L11 At 400 px width, the L6 failure: the mobile toast bar is a shown
  popover, full width at the bottom of the viewport, above the backdrop.
- [x] Record a check that the dev data cannot reach as skipped, with the
  reason, in the pull request body.

## Task 6 — Toasts usable above a modal and the error console

Review round 2. A live probe on the Task 3 build confirmed both findings. With
a modal open, the toast stack is drawn above the backdrop but inert: the hit
test at its close button returns the dialog. On a phone the click closes the
modal and keeps the toast, and on a desktop it lands in the box and does
nothing. With the error console open, the stack covers it: on a phone the bar
covers "Clear all" and takes the click, and on a desktop the 512 px column
covers the console's left edge.

**Files:**
- Create: `frontend/Stores/ModalStore.ts`
- Modify: `frontend/Common/ModalWindow.svelte` (the `$effect`)
- Modify: `frontend/Alerts/topLayer.ts` (whole file)
- Modify: `frontend/Alerts/AlertWidget.svelte` (script, both stacks, the
  console markup, style)
- Test: `frontend/Alerts/topLayer.test.ts`, `frontend/Alerts/AlertWidget.test.ts`,
  `frontend/Common/ModalWindow.test.ts`

**Internals:**
- `ModalStore.ts`: `openModals = writable<HTMLDialogElement[]>([])`,
  `addModal(dialog)` appends, `removeModal(dialog)` filters it out.
- ModalWindow's `$effect` keeps the dialog in a local `shown`, calls
  `shown.showModal()` and then `addModal(shown)`. The teardown calls
  `removeModal(shown)` before the focus rule.
- `topLayer(node, { key, host, shown })`:
  - `home` is `node.parentElement` at mount. It sets `popover="manual"` when
    `showPopover` exists, and tracks `open` itself, because jsdom has no
    `:popover-open`.
  - `place`: the target is `host ?? home`. When the node's parent is not the
    target it appends the node there and sets `open = false`, because the
    browser hides a popover that leaves the document. Without Popover it stops
    here. With `shown === false` it hides an open node. Otherwise it shows the
    node when a raise is due or it is not open, hiding it first when open.
  - Mount places with a raise. `update` raises when the key changed.
    `destroy` hides an open node and removes it when it is not at home.
- AlertWidget:
  - `layer = $derived({ key: messages.at(-1)?.id, host: $openModals.at(-1), shown: !showOldMessages })`,
    passed as `use:topLayer={layer}` on both `#alertWidget` elements. Each
    `#alertWidget` gets a plain wrapper `div`, so the moved node is never a
    block boundary.
  - The console is `<dialog bind:this={errorConsole} class="alert-bucket-modal"
    aria-labelledby={consoleTitleId} onclose={() => (showOldMessages = false)}>`,
    with `consoleTitleId = $props.id()` on its `h5`. An `$effect` calls
    `errorConsole?.showModal()`. The close button and "Clear all" call
    `errorConsole?.close()`, so the browser returns the focus.
  - Style: `dialog.alert-bucket-modal` takes ModalWindow's full-viewport
    transparent layout without a `z-index`, and its `::backdrop` the old
    `rgba(0, 0, 0, 0.55)`. `:global(#alertWidget[popover]:not(:popover-open))`
    sets `display: none`, because the phone bar's `display: flex` overrides
    the user agent rule.

- [x] Probe Chrome on a static page: a popover appended into the modal is
  hit-testable, one outside stays inert when raised again, `showModal()` on
  a second dialog outside the modal makes it the topmost, and a popover
  removed with its dialog shows again once appended home.
- [x] Rewrite `topLayer.test.ts`: `sets_no_popover_without_popover_support`,
  `moves_into_the_host_without_popover_support`,
  `shows_the_node_as_a_manual_popover_on_mount`,
  `raises_the_node_again_when_the_key_changes`,
  `keeps_the_node_in_place_when_the_key_repeats`,
  `moves_into_the_host_modal_and_shows_the_node_there`,
  `returns_home_when_the_host_closes`,
  `hides_the_node_while_it_is_not_shown_and_shows_it_again_after`,
  `hides_the_node_on_destroy`, `removes_the_node_from_its_host_on_destroy`.
- [x] Add to `AlertWidget.test.ts`:
  `opens_the_error_console_as_a_modal_dialog_and_closes_it_with_Clear_all`,
  `closes_the_error_console_when_its_dialog_closes`,
  `moves_the_toast_stack_into_the_open_modal_and_back_when_it_closes`.
- [x] Add to `ModalWindow.test.ts`:
  `lists_the_dialog_as_open_while_it_is_mounted`.
- [x] Write the store, the action, and the ModalWindow and AlertWidget changes.
- [x] Run the verify sequence.
- [x] Commit `fix(alerts): keep toasts usable above modals and the console`.

## Task 7 — `dismissible` on ModalWindow

**Files:**
- Modify: `frontend/Common/ModalWindow.svelte` (`Props`, the defaults,
  `closeOnOutsideClick`)
- Modify: `frontend/ReleasePlanner/ReleasePlanner.svelte` (four modals),
  `frontend/ReleasePlanner/ReleasePlanCreator.svelte` (Grid View),
  `frontend/Views/Views.svelte`, `frontend/AdminPanel/ChatIdentityEditor.svelte`,
  `frontend/AdminPanel/ProxyTunnelCreateForm.svelte`
- Test: `frontend/Common/ModalWindow.test.ts`

**Internals:**
- `dismissible?: boolean` in `Props`, default `true`.
  `closeOnOutsideClick` closes only when `dismissible` and the three outside
  flags hold. Escape and the close button do not read it.
- The callers in the spec's Contracts pass `dismissible={false}`. The other
  20 uses keep the default: the delete and toggle confirmations, the
  `ReleasePlanEditor` schedule delete confirmation, the plan redirect notice,
  the views error prompt, the viewers (issues copy, results graph, SCT issues
  and similar events), the pickers (chat model, entity replacer) and the
  single-field prompts (SCT issue URL, user email and password).

- [x] Add to `ModalWindow.test.ts`:
  `stays_open_on_a_click_outside_the_box_when_not_dismissible` (the dialog and
  the frame) and `closes_from_the_close_button_and_a_dialog_close_when_not_dismissible`.
- [x] Add the prop and the eight `dismissible={false}` attributes.
- [x] Run the verify sequence.
- [x] Commit `improvement(frontend): add a dismissible prop to ModalWindow`.

## Task 8 — Live check, review round 2

**Files:** none committed. Scripts and screenshots go to the scratch
directory `ARGUS-274-review2/`. Setup as in Task 5. Before the change,
`probe.mjs` and `console.mjs` record both findings on the Task 3 build.

- [x] T1 at 1280 px and at 400 px: fail the Sidebar delete with a 500
  through `Fetch.fulfillRequest`. The stack is an open popover inside the
  dialog, and the hit test at its close button returns the button. A click
  there removes the toast, and the modal stays open with its input. After
  Escape the stack is back home.
- [x] T2 at 1280 px and at 400 px: three or four failures, close the modal,
  dismiss one toast, open the console. The console matches `:modal`, the
  stack is hidden, and the hit tests at the left, the middle and the right
  of "Clear all" and of its close button return them. A click on "Clear all"
  closes the console, and the stack shows again.
- [x] T3 at 400 px: open the console from the phone bar while the delete
  modal is open. The console is the topmost modal and "Clear all" wins the
  hit test. Escape closes only the console; the modal keeps its input.
- [x] T4 `/release/<name>/planner`, New Plan, which passes
  `dismissible={false}`: type a name, click outside the box. It stays open
  with the name. Escape closes it and the focus returns to New Plan; the
  close button closes it.
- [x] T5 `/admin/users`, Change Email, a default modal: a click outside the
  box closes it, and the focus returns to the trigger.
- [x] Rerun L1 to L11 of Task 5 on the new build.
- [x] Record the build with an empty `suppressedSvelteCodes`, as in Task 4.
