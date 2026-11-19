# ARGUS-275 — Load Font Awesome without stopping the HTML parse

## Problem

`templates/base.html.j2` loads `/s/dist/fontAwesome.bundle.js` as a classic
`<script>` in `<head>`, with no `defer`, `async` or `type="module"`. Every page
extends the base template, so every page loads it. The browser stops the HTML
parse until the script downloads and runs, and it paints nothing before that.

The bundle comes from `frontend/font-awesome.js`. It holds the Font Awesome
SVG JavaScript and all four icon sets: core, solid, regular and brands. The
production build makes it 1.5 MB. Argus draws most of its icons with
`svelte-fa`, which does not need this bundle. The bundle only serves the
`<i class="fas fa-...">` and `<i class="far fa-...">` elements in the Jinja
templates, in a few Svelte components and in one chart tooltip string.

## Who it affects

Every user on every page. The cost grows on a slow network or a slow CPU,
because the first paint waits for the whole bundle.

## Evidence

From ARGUS-275:

> templates/base.html.j2 loads fontAwesome.bundle.js as a classic <script>
> in <head>. The bundle (frontend/font-awesome.js) holds the Font Awesome SVG
> JavaScript and all four icon sets: core, solid, regular and brands. The
> browser stops the HTML parse until the script loads and runs. Every page
> loads this script.

`templates/base.html.j2:53` at master 14e76bed:

```html
<script src="/s/dist/fontAwesome.bundle.js"></script>
```

The production build at master 14e76bed (`NODE_ENV=production yarn build`):

```
public/dist/fontAwesome.bundle.js               1,503.95 kB │ gzip: 524.58 kB
```

It is the largest file in `public/dist`. On `/releases` with a 4x CPU
slowdown and a 10 Mbit/s link, the bundle finishes downloading at 1657 ms
and the first paint lands at 1840 ms, as the median of 9 runs. The spec
records the method.

## What good looks like

- No script for Font Awesome stops the HTML parse.
- Argus loads only the icon sets it uses.
- Every icon shows on the main pages: the nav bar, Workspace, Releases,
  Views, a release dashboard and a test run.
- The pull request shows the size and the first paint before and after.

## Out of scope

- The icons that `svelte-fa` draws. They do not use the bundle.
- Accessible names and `aria-hidden` on icons that the Svelte build warns
  about. ARGUS-276 owns that work.
- A switch away from Font Awesome to another icon set.
- `scripts/argus-status-page/index.html`. It loads Font Awesome 6 from a CDN
  and is not part of the Argus web application.
