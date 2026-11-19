# ARGUS-274 — Build ModalWindow on the native dialog element

This is a subtask of story ARGUS-273, which applies Chrome Modern Web
Guidance to the Argus frontend.

## Problem

`frontend/Common/ModalWindow.svelte` draws a modal as a `position: fixed`
div with `z-index: 9999`, and closes it from an Escape handler on
`<svelte:window>`. The browser does not treat that div as a modal:

- The focus stays on the trigger when the modal opens. Tab walks through the
  page behind the overlay as well as through the modal.
- The page behind the overlay stays interactive for the keyboard and for a
  screen reader. A screen reader reads the whole page, not only the modal.
- When the modal closes, the focus does not return to the trigger.
- Every open ModalWindow listens for Escape on the window. When one modal
  opens another, one Escape closes both.
- The overlay stacks by `z-index`, so every other layer must pick a number
  against `9999` to sit above or below it.

This breaks the Focus Management rule in
`docs/standards/frontend/accessibility.md`.

ModalWindow has 28 uses in 17 files. The 17 files are 16 direct callers and
`frontend/Common/ConfirmDeleteModal.svelte`, which wraps ModalWindow for the
Sidebar and the test runs selector. The admin panel, the release planner,
the views, the test run results, the SCT events and the GitHub issues all
open it.

## Who it affects

- Keyboard and screen reader users of every Argus page that opens a
  ModalWindow: user management, proxy tunnels, the chat configuration, the
  release planner, views, results graphs, SCT event issues and the workspace
  sidebar.
- Every user who opens a modal from inside another modal: release plan
  creation opens the grid view, plan copying opens the entity replacer, and
  view creation opens the error popup of the views manager.

## Evidence

The issue text of ARGUS-274:

> frontend/Common/ModalWindow.svelte makes a modal from a position: fixed div
> with z-index: 9999 and an Escape handler on <svelte:window>. It has no focus
> trap, and the page behind it stays interactive. This breaks the rule in
> docs/standards/frontend/accessibility.md (Focus Management): move the focus
> into a modal when it opens, and back to the trigger when it closes.

The rule in `docs/standards/frontend/accessibility.md`:

> ### Focus Management
> Move the focus into a modal when it opens, and back to the trigger when it
> closes. A dynamic update must not lose the focus.

The code on master 14e76bed, `frontend/Common/ModalWindow.svelte`:

```svelte
    function handleKeyDown(event) {
        if (event.key === "Escape") {
            dispatch("modalClose");
        }
    }
</script>

<svelte:window onkeydown={handleKeyDown} bind:innerWidth={innerWidth} />
<div class="modal-window">
```

```css
    .modal-window {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 9999;
    }
```

The guide that the issue names, `ui-components/dialog` of Chrome Modern Web
Guidance:

> The browser provides: inert page, focus containment, top layer,
> `::backdrop`, `Esc` and back-gesture dismissal, and focus return to the
> invoker.

## What good looks like

- The focus moves into the modal when it opens, and back to the trigger when
  it closes.
- The page behind an open modal gets neither the focus nor clicks.
- Escape closes only the topmost modal.
- All 17 caller files work without a change to their code.
- ModalWindow produces none of the six a11y warning codes that
  `vite.config.ts` suppresses today.

## Out of scope

- The other hand-made overlays in `frontend/` with their own `position:
  fixed` and `z-index`, such as the Jenkins build and clone modals, the
  screenshot modal and the enlarge view of `ResultsGraph.svelte`.
- The Bootstrap modals, such as the ignore-runs dialog of
  `TestRunsSelector.svelte`.
- The `suppressedSvelteCodes` list and the a11y warnings in other
  components. ARGUS-276 owns them.
- Changing the callers' markup, for example adding a title where a caller
  has none.
