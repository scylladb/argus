# ARGUS-138 — The issue template is unreadable in dark mode

## Problem

The issue template panel on a test run page renders its template text on a
light grey block in both themes. In dark mode the page supplies a light body
text color, so light grey text lands on a light grey block. The template text
is there, and it cannot be read.

The panel behind the "Scylla Issue Template" button is the one users copy an
issue body from. A user in dark mode has to select the text blind, copy it, and
paste it somewhere else to see what it says.

## Who it affects

Any engineer who files a Scylla issue from a run page with the dark theme
active. It covers the SCT issue template and the Sirenada cloud issue template,
which carry the same panel.

## Evidence

The block sets a background and no text color, so the dark theme's body color
is inherited over it:

```css
.code {
    font-size: 11pt;
    padding: 1em;
    background-color: #f0f0f0;
}
```

The dark theme sets the inherited color the block does not override:

```scss
[data-bs-theme="dark"] {
    --bs-body-color: #dee2e6;
    --bs-body-bg: #1a1d21;
}
```

`#dee2e6` on `#f0f0f0` is a contrast ratio of 1.14:1. WCAG AA asks for 4.5:1
on body text.

## What good looks like

The template text reads at a glance in dark mode, at the same contrast the
light theme already gives. The Preview tabs next to it already read correctly,
and they stay as they are.

## Out of scope

Any other panel on the run page. The template content itself. The light theme
appearance, which does not change.
