# ARGUS-275 — implementation plan

**Spec:** `tasks/ARGUS-273/ARGUS-275/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Work in the worktree on branch `argus-275-font-awesome-load`.
- Touch only `frontend/font-awesome.scss`, `frontend/font-awesome.js`,
  `frontend/argus.js`, `vite.config.ts` (the `fontAwesome` input and the
  `base` key), `templates/base.html.j2`, `templates/partials/nav_bar.html.j2`,
  `templates/releases.html.j2`, and the new test file. Leave every Svelte
  component and the `suppressedSvelteCodes` list alone: ARGUS-276 owns them.
- Build the frontend with `NODE_ENV=production yarn build` for every number
  that goes into the pull request.
- Commit with `uv run git commit`. Stage by explicit path. The header follows
  commitlint, with no Jira key in it; the body ends with `Task: ARGUS-275`.
- No rationale comments in the code.
- Tasks 1 to 3 landed as one code commit, `perf(frontend): load Font
  Awesome icons from CSS and webfonts`. After Task 1 alone the
  build no longer emits the bundle, so the template asks for a missing
  script until Task 2 removes it; one commit keeps every commit free of that
  failing request. The three tasks were reviewed as one diff.

## Task 1 — Build the icons from the CSS and webfont

**Files:**
- Modify: `frontend/font-awesome.scss`
- Delete: `frontend/font-awesome.js`
- Modify: `frontend/argus.js` (import `./font-awesome.scss` next to `./fonts/noto.css`)
- Modify: `vite.config.ts` (drop the `fontAwesome` input, add `base: "/s/dist/"`)

**Internals:** `font-awesome.scss` becomes:

```scss
@use "@fortawesome/fontawesome-free/scss/variables" with ($font-path: "../node_modules/@fortawesome/fontawesome-free/webfonts");
@import "@fortawesome/fontawesome-free/scss/fontawesome.scss";
@import "@fortawesome/fontawesome-free/scss/solid.scss";
@import "@fortawesome/fontawesome-free/scss/regular.scss";
```

A probe build in round 1 confirmed this shape: Vite resolves the relative
font path, emits both woff2 files, and writes `url(/s/dist/fa-solid-900.woff2)`
with `base: "/s/dist/"`. A CSS file as a Vite input fails the build
(`Cannot read properties of undefined (reading 'referenceId')`), which is why
the main entry imports the SCSS.

The build output is configuration, so no unit test covers it. The checks
below stand in for one.

- [x] Run `NODE_ENV=production yarn build`. Confirm `public/dist` holds
  `fa-solid-900.woff2` (113,108 bytes) and `fa-regular-400.woff2` (18,892
  bytes), no `fa-brands-400.woff2`, and no `fontAwesome.bundle.js`.
- [x] Run `grep -o 'url([^d][^)]*)' public/dist/style.css`. Expect the two
  `/s/dist/fa-*.woff2` URLs and the four Noto URLs, now under `/s/dist/`.
- [x] Confirm `style.css` grew by about 1 KB, not more.
- [x] Load `/releases` with the bundle still in the template. The icons
  render as `<i>` from the webfont, and the theme icon follows a click.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked: in the one code commit, with Tasks 1 to 3.

## Task 2 — Remove the parser-blocking script

**Files:**
- Modify: `templates/base.html.j2:53` (remove the `fontAwesome.bundle.js`
  script, add the preload link after the `style.css` link)
- Test: `argus/backend/tests/main_api/test_page_head.py` (new)

**Internals:** the preload link from the `Outputs` section of the spec:

```html
<link rel="preload" href="/s/dist/fa-solid-900.woff2" as="font" type="font/woff2" crossorigin>
```

The tests parse the rendered page with `html.parser.HTMLParser` and collect
each `<script src>` and `<link>` in `<head>`:

- `test_page_head_loads_no_parser_blocking_script`: for `/releases` through
  `api_client` and `/error/?type=404` through `anon_client`, every
  `<script src>` in `<head>` carries `type="module"`, `defer` or `async`.
  Fails today on `fontAwesome.bundle.js`.
- `test_page_head_preloads_the_solid_icon_font`: the head holds a
  `<link rel="preload" as="font">` for `/s/dist/fa-solid-900.woff2` with
  `crossorigin`. Fails today.

- [x] Write the two failing tests.
- [x] Run `uv run pytest argus/backend/tests/main_api/test_page_head.py` and
  confirm both fail for the reason above.
- [x] Change `templates/base.html.j2`.
- [x] Run the tests and confirm they pass.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked: in the one code commit, with Tasks 1 to 3.

## Task 3 — Hide the template icons from assistive technology

This task follows the `(review)` decision of the spec on the template icons.

**Files:**
- Modify: `templates/partials/nav_bar.html.j2` (16 `<i>` icons)
- Modify: `templates/releases.html.j2:26-27` (2 `<i>` icons)
- Test: `argus/backend/tests/main_api/test_page_head.py`

**Internals:** each `<i class="fas|far fa-...">` gains `aria-hidden="true"`.
`#theme-icon` keeps the attribute when the theme script sets `className`.

- `test_template_icons_are_hidden_from_assistive_technology`: on `/releases`
  through `api_client` and `/error/?type=404` through `anon_client`, every
  `<i>` whose class holds `fas` or `far` carries `aria-hidden="true"`.

- [x] Write the failing test.
- [x] Run it and confirm it fails on the nav bar icons.
- [x] Add the attribute.
- [x] Run the test and confirm it passes.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked: in the one code commit, with Tasks 1 to 3.

## Task 4 — Live check and the after numbers

No code changes. The results go into the pull request body.

Set-up: production build, then
`uv run uvicorn --factory argus_backend:create_app --port 5015` from the
worktree as a background task, `POST /auth/login` with admin/admin into a
curl cookie jar (keep the `#HttpOnly_` session line), and
`google-chrome --headless=new --remote-debugging-port=9335` with a scratch
profile. Round 1 used `measure.mjs` and `probe-behaviour.mjs` in the session
scratch directory `ARGUS-275/`; reuse them unchanged so the numbers compare.
Confirm first that `/s/dist/style.css` from :5015 matches the worktree build.

- [x] Measure `/releases` and `/dashboard/scylla-master`, plain and
  throttled, 9 runs plus one warm-up, median, exactly as the spec's
  `Measurement` section states. Record first paint, FCP, DOMContentLoaded,
  script time, CLS, and the `responseEnd` of `fa-solid-900.woff2`.
- [x] Record the size table: `fontAwesome.bundle.js` before (1,503,956 raw,
  515,950 gzip -9) against the two woff2 files and the `style.css` delta.
- [x] On `/workspace`, `/releases`, `/views`, `/dashboard/scylla-master`, one
  `/test_run/<id>` of an SCT run, and `/error/?type=404` logged out: every
  `<i class*="fa">` has a width above 0, a non-empty `::before` content, and
  `document.fonts.check('900 1em "Font Awesome 7 Free"')` is true. Take a
  screenshot of each page and look at the nav bar and the icons.
- [x] Click the theme toggle three times. The icon changes sun, moon,
  circle-half-stroke with the label.
- [x] Change the class of an `<i class="fas fa-chevron-right">` to
  `fa-chevron-down`. The glyph changes.
- [x] Read the accessibility tree. The nav link names match round 1
  (`" Workspace"`, `" Releases"`, `" Views"`, ...).
- [x] Record every font request and its status. No request for a `.ttf`
  Noto file appears, as in round 1.
- [x] Check the `fa-spin` `svelte-fa` spinner in the summary widget still
  turns, when a view with that widget is available.
- [x] Stop the server and Chrome by their own task ids.
