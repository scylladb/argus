# ARGUS-276 — Turn on the suppressed Svelte accessibility warnings

## Problem

`vite.config.ts` drops six Svelte accessibility warnings before the build
prints them. The elements these warnings describe are still in the pages:

- A `<div>`, `<li>` or `<a>` that reacts to a mouse click but cannot be
  reached with the Tab key or activated with Enter or Space.
- An element that claims `role="button"` but is not focusable.
- A tab link with no `href`, so it is not a link and not a button.
- Modal overlays whose only handlers stop a click from bubbling, which the
  compiler reads as unlabelled interactive regions.

Because the build stays quiet, nobody sees these problems, and new code adds
more of them without notice.

## Who it affects

- Keyboard users and screen reader users of the admin release manager, the
  notifications reader, the team page, the release statistics, the results
  graphs of a test run and the graphs widget of a view.
- Developers, who get no signal from `yarn build` when a change adds an
  element of this kind.

## Evidence

`vite.config.ts` on master (`14e76bed`):

```ts
const suppressedSvelteCodes = [
    "a11y_click_events_have_key_events",
    "a11y_no_static_element_interactions",
    "a11y_no_noninteractive_element_interactions",
    "a11y_no_noninteractive_element_to_interactive_role",
    "a11y_missing_attribute",
    "a11y_interactive_supports_focus",
];
```

With the list emptied, `yarn build` reports 36 warnings of these six codes in
11 components. Two of them:

```
[vite-plugin-svelte] frontend/TestRun/ResultsGraphs.svelte:187:12 `<a>` element should have an href attribute
https://svelte.dev/e/a11y_missing_attribute

[vite-plugin-svelte] frontend/Teams/TeamMember.svelte:66:16 Elements with the 'button' interactive role must have a tabindex value
https://svelte.dev/e/a11y_interactive_supports_focus
```

The build prints the line after the TypeScript preprocessing of a
`lang="ts"` component. `svelte-check` reports the same warnings at their
source lines, `ResultsGraphs.svelte:221` and `TeamMember.svelte:85`.

The build also prints one accessibility warning today, outside the list:

```
[vite-plugin-svelte] frontend/AdminPanel/AvatarCropper.svelte:88:4 noninteractive element cannot have nonnegative tabIndex value
https://svelte.dev/e/a11y_no_noninteractive_tabindex
```

Jira: https://scylladb.atlassian.net/browse/ARGUS-276, under ARGUS-273
(Chrome Modern Web Guidance). Guide:
https://developer.chrome.com/docs/modern-web-guidance/guides/accessibility/accessibility

## What good looks like

- `suppressedSvelteCodes` in `vite.config.ts` is empty, or each entry left
  has a stated reason.
- `yarn build` prints no `a11y_*` warning.
- Each element the warnings named works from the keyboard: Tab reaches it,
  and Enter or Space does what a click does.

## Out of scope

- `frontend/Common/ModalWindow.svelte`. ARGUS-274 rewrites it on `<dialog>`.
- The Font Awesome loading and the `<i class="fa">` icons. ARGUS-275 owns
  them.
- The markdown rendering of the discussion and view highlights components.
  ARGUS-278 owns it.
- Accessibility problems that no Svelte compiler warning reports, such as an
  icon-only button with no accessible name, colour contrast or focus order.
- The other compiler warnings the build prints, such as
  `state_referenced_locally`.
