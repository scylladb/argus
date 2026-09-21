# ARGUS-138 — The issue template block has no text color of its own

**Date**: 2026-09-21

## Root cause

The issue template text sits in a `pre.code` block that sets a background and
no text color. `frontend/TestRun/IssueTemplate.svelte:357-361`, before the fix:

```css
.code {
    font-size: 11pt;
    padding: 1em;
    background-color: #f0f0f0;
}
```

With no `color` declaration the block inherits it, and the dark theme sets the
inherited value on the document root. `frontend/argus.scss:302,307-309`:

```scss
[data-bs-theme="dark"] {
    & {
        --bs-body-color: #dee2e6;
        --bs-body-bg: #1a1d21;
    }
}
```

`templates/base.html.j2:2` carries the attribute the theme hangs off, and a
script on the same page switches it:

```html
<html lang="en" data-bs-theme="light">
```

So in dark mode the block paints `#dee2e6` text on its own `#f0f0f0`
background, a contrast ratio of 1.14:1 against the 4.5:1 that WCAG AA asks of
body text. The block keeps its light background in both themes because the
rule is unconditional, and only the text color follows the theme. That is the
mechanism: one half of the pair is theme-aware and the other half is not.

`docs/standards/frontend/css.md` names this case directly. A color pair stays
together, and "an element that depends on the inherited page background is the
exception, and it needs a check in both themes." This block took the exception
without the check.

The same rule appears twice. `frontend/TestRun/Sirenada/SirenadaIssueTemplate.svelte:157-161`
declares it identically, so the Sirenada cloud issue template fails the same
way. The Preview tabs next to the raw template are unaffected, because
`frontend/argus.scss:924-927` themes `.markdown-body` explicitly.

## Approaches

1. **A self-contained color pair in each component** — selected. Add `color`
   to the existing rule, and add a `:global([data-bs-theme="dark"]) .code`
   rule with the dark pair. Cost: six lines per component, twelve in total.
   Risk: the two copies can drift, which the deferred extraction below
   addresses. Reason: it is the pattern the codebase already uses for exactly
   this case. `frontend/TestRun/NemesisReason.svelte:23-26` themes its
   stacktrace block the same way, the values come from the palette the dark
   theme already defines, and the rule stays in the component that owns it.
2. **Drop the background and inherit both halves from the theme.** The block
   would follow `--bs-body-bg` and `--bs-body-color` with no custom color at
   all. Cost: one line removed per component. Risk: the block stops reading as
   a block, because it would match the page behind it in light mode and the
   `#2b3035` card behind it in dark mode. Rejected: the padded grey slab is
   what marks the template as copyable text, and removing it changes the light
   theme, which `intent.md` puts out of scope.
3. **A global `.code` rule in `frontend/argus.scss`.** One rule would cover
   both components and any future one. Cost: one rule. Risk: `.code` is a
   generic name, and a global selector would reach every element that carries
   it across the application, including ones with their own background.
   Rejected: `docs/standards/frontend/css.md` puts a rule in the component
   that owns it and allows a global only for a Bootstrap override that must
   cross the boundary, which this is not.

## Regression test

`None`. The defect is a computed style under a theme attribute, and the
frontend suite cannot observe it. `docs/standards/testing/test-writing.md:56`
runs Vitest in jsdom, which does not resolve the CSS cascade, so it cannot
report the inherited color that the block ends up painting. A test asserting
the presence of the declaration would restate the diff rather than reproduce
the bug.

Verified instead against the compiled stylesheet that `yarn build` emits, where
both rules survive with their per-component scope hashes:

```css
.code.svelte-afei64{color:#212529;background-color:#f0f0f0;padding:1em;font-size:11pt}
[data-bs-theme=dark] .code.svelte-afei64{color:#dee2e6;background-color:#1a1d21}
.code.svelte-1qrxx6h{color:#212529;background-color:#f0f0f0;padding:1em;font-size:11pt}
[data-bs-theme=dark] .code.svelte-1qrxx6h{color:#dee2e6;background-color:#1a1d21}
```

The resulting contrast ratios:

| Pair | Ratio | WCAG |
|---|---|---|
| `#dee2e6` on `#f0f0f0` (before, dark) | 1.14:1 | fails |
| `#dee2e6` on `#1a1d21` (after, dark) | 12.99:1 | AAA |
| `#212529` on `#f0f0f0` (after, light) | 13.54:1 | AAA |

## Risks

| Risk | Response |
|---|---|
| The two copies of the rule drift apart | Both carry identical declarations in this change, and a reviewer reads them together |
| A later global `.code` rule reintroduces the inherited color | The pair is self-contained, so a global rule has to override both properties to break it |
| The block stops separating from the card in dark mode | `#1a1d21` against the `#2b3035` card keeps the block edge visible, and the padding holds |
| No automated test guards the regression | The color pair is now unconditional in both themes, and review rule 7 in `docs/standards/REVIEW.md` checks the pair on any later edit |

## Deferred work

The two components duplicate the whole issue template panel, not just this
rule. A shared component would give the block one home and remove the drift
risk above. This change does not build it, and it keeps the two rules
identical so the extraction stays cheap.

---

A bug fix that changes a contract or a module boundary writes `spec.md` in
place of this file. A very small fix may skip the flow. The pull request
description then says so.
