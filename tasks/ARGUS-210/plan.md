# ARGUS-210 — implementation plan

**Spec:** `tasks/ARGUS-210/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Imports sit at the top of the module.
- No comments or docstrings that justify the change.
- New components use runes and `lang="ts"`. They reach no DOM node through
  `querySelector`.
- Bootstrap utilities first. A status color comes from
  `StatusBackgroundCSSClassMap` (`frontend/Common/TestStatus.js:74`), which already pairs the
  background and the text color.
- Frontend tests render through `@testing-library/svelte`, stub `fetch` with
  `vi.stubGlobal`, mock `../Stores/AlertStore` and `../Stores/UserlistSubscriber.js` as
  `frontend/Github/Issues.test.ts:7-15` does, and assert the DOM.
- A Svelte 5 component is a plain function, `Component(anchor, props)`. A test replaces a child
  component with `vi.mock("<path>.svelte", () => ({ default: vi.fn() }))` and reads its props
  from `vi.mocked(Child).mock.calls`.
- Commits:
  - commitlint header `feature(issues): …`
  - a body of at least 30 characters
  - the last line is `Task: ARGUS-210`
  - no co-author line
  - `git add` by explicit path only
- Leave the code uncommitted until the user reviews it.

## Task 1 — Serve the page shell

**Files:**
- Modify: `argus/backend/controller/main.py`: add the route after `get_run_by_build` (l.82–94),
  before `home` (l.97).
- Create: `templates/issue_links.html.j2`
- Test: `argus/backend/tests/main_api/test_issue_page.py`

**Internals:**

```python
@router.get("/issues/{key}", name="main.issue_links")
async def issue_links(asgi_request: Request, key: str, user: User = Depends(ui_current_user)):
    return templates.TemplateResponse(asgi_request, "issue_links.html.j2", {"key": key})
```

The template copies `templates/run_view_by_plugin.html.j2`:

```jinja
{% extends "base.html.j2" %}

{% block title %}
{{ key | e }}
{% endblock %}

{% block javascripts %}
{{ super() }}
<script>
    const gIssueKey = {{ key | tojson }};
</script>
<script defer type="module" src="/s/dist/issueLinks.bundle.js"></script>
{% endblock javascripts %}

{% block body %}
<div class="container p-1" id="issueLinks">

</div>
{% endblock %}
```

`tojson` writes `<`, `>`, `&` and `'` as `<`, `>`, `&` and `'`. The title
block autoescapes.

**Tests:** in the form of `argus/backend/tests/main_api/test_run_view.py`, with `api_client`.
- `test_issue_page_renders_for_a_key`: `GET /issues/SCT-1234` gives 200. The body holds
  `/s/dist/issueLinks.bundle.js` and `"SCT-1234"`.
- `test_issue_page_escapes_the_key`: `GET /issues/%3Cb%3Ex-1` gives 200. The body does not hold
  `<b>x-1`. It holds `<b>x-1` and `&lt;b&gt;x-1`.

- [x] Write the tests.
- [x] Run `uv run pytest argus/backend/tests/main_api/test_issue_page.py` and confirm the failure
  (HTTP 404).
- [x] Add the route and the template.
- [x] Run it again until it passes.

## Task 2 — Let the run selector hide its title bar and keep the URL

**Files:**
- Modify: `frontend/WorkArea/TestRuns.svelte`:
  - the JSDoc `Props` typedef (l.27–34)
  - the `$props()` destructuring (l.37)
  - the title-bar block (l.337–406)
- Modify: `frontend/WorkArea/TestRunDispatcher.svelte`
- Modify: the four plugin run views, `frontend/TestRun/TestRun.svelte`,
  `frontend/TestRun/DriverMatrixTestRun.svelte`, `frontend/TestRun/Sirenada/SirenadaTestRun.svelte`
  and `frontend/TestRun/Generic/GenericTestRun.svelte`: the `Props` interface, the destructuring and
  `setActiveTab`
- Test: `frontend/WorkArea/TestRuns.test.ts`

**Internals:**
- `@property {boolean} [showTitleBar]` and `@property {boolean} [updateUrl]` in the typedef.
  `showTitleBar = true` and `updateUrl = true` in the destructuring.
- `TestRuns` passes `{updateUrl}` to `TestRunDispatcher`, which passes it to the plugin view.
- Each plugin view declares `updateUrl?: boolean`, defaults it to `true`, and guards the
  `history.replaceState` in `setActiveTab` with `updateUrl &&`, next to the existing `/workspace`
  check.
- `{#if showTitleBar}` … `{/if}` around `<div class="border-none mb-2">` … `</div>`
  (l.337–406). That is the header with the status circle, the test name, the start time, the
  build number, the configure, rebuild and clone buttons, and the collapse toggle.
- No change below l.406: the modals, the `collapse show` body, `TestRunsSelector` and
  `TestRunDispatcher`.

**Tests:**

Mocks, at the top of the file:
- `vi.mock("../argus", () => ({ applicationCurrentUser: { roles: [] } }))`. `frontend/argus.js`
  reads the global `gArgusCurrentUser` and imports stylesheets.
- `vi.mock("../Common/PluginDispatch", () => ({ AVAILABLE_PLUGINS: {}, isPluginSupported: () => true }))`.
  This keeps the plugin run views out of the import graph.
- `vi.mock("./TestRunDispatcher.svelte", () => ({ default: vi.fn() }))`. The cases that open a run
  read its props from `vi.mocked(TestRunDispatcher).mock.calls`.
- The `AlertStore` mock from the Rules.

Stubs:
- `IntersectionObserver`, a class with `observe` and `disconnect`, for `TestRunsSelector`.
- `fetch`, routed by URL:
  - `/api/v1/test-info?…` returns
    `{test: {id, name: "longevity-frobnicator-4h", plugin_name: "scylla-cluster-tests", build_system_id, build_system_url}, release: {id, name: "master"}, group: {id, name: "longevity"}}`
  - `/api/v1/test/{id}/runs?…` returns one run, `{id, status: "failed", build_number: 412, start_time}`
  - the `HEAD` on `/api/v1/test-results` returns status 404

Cases:
- `shows the title bar by default`: after the run pill `#412` renders, the title bar
  `getByRole("button", { name: /longevity-frobnicator-4h/ })` is there. The title bar renders
  with the test info, before the runs arrive, so the case waits for the pill first.
- `hides the title bar when showTitleBar is false`: after the pill `#412` renders,
  `queryByRole("button", { name: /longevity-frobnicator-4h/ })` is `null`, and `#412` appears
  once.
- `lets the run view update the URL by default`: with `additionalRuns: [run id]`, the dispatcher
  gets that `runId` and `updateUrl === true`.
- `passes updateUrl false on to the run view`: with `updateUrl: false` too, the dispatcher gets
  `updateUrl === false`.

- [x] Write the tests.
- [x] Run `yarn vitest run frontend/WorkArea/TestRuns.test.ts`. The second case fails because the
  title bar is there.
- [x] Add the prop and the `{#if}`.
- [x] Run it again until it passes.

## Task 3 — Type the lookup response

**Files:**
- Modify: `frontend/Common/IssueTypes.ts`: add the two interfaces after `JiraSubtype` (l.62–69).

**Internals:** `LinkedRun` and `IssueLinks`, exactly as the spec's `Module API` states them.

- [x] Add the interfaces.

## Task 4 — Render one linked run

**Files:**
- Create: `frontend/IssueLinks/LinkedRun.svelte`
- Test: `frontend/IssueLinks/LinkedRun.test.ts`

**Internals:**
- `let { link }: { link: LinkedRun } = $props();`
- `let open = $state(false);`
- `const version = $derived(link.scylla_version || link.product_version);`
- `const location = $derived(link.build_id.split("/").slice(0, -1).join("/"));`, the release
  path of the test, such as `scylla-5.2/artifacts`
- ``const linkedOn = $derived(link.linked_on ? `linked ${timestampToISODate(link.linked_on)}` : "");``

The markup is one `linked-run bg-white rounded border px-2 py-1` card, with a lighter shadow than
`shadow-sm` (`0 1px 2px rgba(0, 0, 0, 0.05)`; `argus.scss` turns `shadow-sm` into a heavy shadow in
the dark theme). It holds one Bootstrap `row g-2 align-items-center`, whose columns line up with
the header of Task 5 from the `lg` breakpoint:

| Column | Classes | Content |
|---|---|---|
| Status | `col-auto col-lg-1` | `<span class="badge border text-uppercase {StatusBadgeCSSClassMap[link.status] ?? StatusBadgeCSSClassMap.unknown}">` with `titleCase(link.status.replaceAll("_", " "))` |
| Test | `col col-lg-5 min-w-0` | `link.test_name` in `fw-bold text-truncate`, and below it `[location, linkedOn].filter(Boolean).join(" · ")` in `small text-muted text-truncate` |
| — | `w-100 d-lg-none` | a break: below `lg` the run details and the buttons take a second line |
| Build | `col-auto col-lg-1` | `#{link.build_number}` |
| Started | `col-auto col-lg-2 text-nowrap` | `timestampToISODate(link.start_time)` |
| Version | `col-auto col-lg-1 text-truncate` | `version`, or `—` |
| Actions | `col-auto ms-auto col-lg-2 d-flex justify-content-end` | the button group below |

`.min-w-0 { min-width: 0; }` lets the test name truncate inside its column.

The button group:
- `<a class="btn btn-sm btn-primary text-nowrap" href={link.url}>` with `faExternalLinkAlt` and
  "Open run"
- `<button class="btn btn-sm btn-outline-secondary text-nowrap" aria-expanded={open} onclick={() => (open = !open)}>`,
  labelled "Show inline" or "Hide", with `faChevronDown` or `faChevronUp`. Both labels sit in one
  `d-inline-grid text-start` cell (`grid-area: 1 / 1`), and the inactive one takes `invisible`,
  so the button keeps the width of the longer label in both states

Below the row:

```svelte
{#if open}
    <div class="mt-2" transition:slide={{ duration: 300, easing: cubicInOut }}>
        <TestRuns
            testId={link.test_id}
            additionalRuns={[link.run_id]}
            tab="details"
            showTitleBar={false}
            updateUrl={false}
        />
    </div>
{/if}
```

`slide` comes from `svelte/transition` and `cubicInOut` from `svelte/easing`.

**Tests:** `vi.mock("../WorkArea/TestRuns.svelte", () => ({ default: vi.fn() }))`. jsdom has no
`Element.animate`, so `vi.mock("svelte/transition", () => ({ slide: () => ({ duration: 0 }) }))`:
Svelte skips the animation for a zero duration. The fixture
link has these values:
- `test_name: "longevity-frobnicator-4h"`
- `status: "failed"`
- `build_number: 412`
- `scylla_version: "2026.2.0~dev"`
- `url: "http://testserver/test/frobnicator/longevity/412"`

Cases:
- `shows the run summary`:
  - the test name, `#412` and `2026.2.0~dev` render
  - `frobnicator/longevity · linked 2026-10-01 07:02` renders under the name
  - the status badge reads `Failed`
- `falls back to the product version`: with `scylla_version: null` and
  `product_version: "2026.1.3"`, `2026.1.3` renders.
- `links to the run page`: the "Open run" link has `href === link.url`.
- `opens the run inline`:
  - one click sets `aria-expanded="true"`
  - `TestRuns` was called once, with props `testId === link.test_id`,
    `additionalRuns` equal to `[link.run_id]`, `tab === "details"`, `showTitleBar === false` and
    `updateUrl === false`
  - a second click sets `aria-expanded="false"`
  - a third click calls `TestRuns` a second time

- [x] Write the tests.
- [x] Run `yarn vitest run frontend/IssueLinks/LinkedRun.test.ts` and confirm the failure (the
  module does not exist).
- [x] Write the component.
- [x] Run it again until it passes.

## Task 5 — Render the issue and its runs

**Files:**
- Create: `frontend/IssueLinks/IssueLinks.svelte`
- Test: `frontend/IssueLinks/IssueLinks.test.ts`

**Internals:**
- `let { issueKey }: { issueKey: string } = $props();`
- `let result: IssueLinks | undefined = $state();` and `let error = $state("");`
- `onMount` calls `fetchJson` (`frontend/Common/ApiUtils.js:46`) on
  `` `/api/v1/issues/${encodeURIComponent(issueKey)}/links` ``. It catches the thrown `Error`
  into `error`.
- `plural(count, word)` returns `"1 test"` or `"2 tests"`.
- `summary`, a `$derived.by`, joins with ` · `:
  - the count of distinct `test_id`
  - the count of distinct versions (`scylla_version || product_version`, empty ones left out)
  - one `"{n} {status}"` per status, the most frequent first, `_` read as a space

The markup, in this order:

| Condition | Renders |
|---|---|
| `error` | `<div class="alert alert-danger">` with the message |
| `!result` | `spinner-border spinner-border-sm` and "Loading runs linked to {issueKey}…" |
| `!result.issue` | `<div class="alert alert-secondary">Argus holds no issue {issueKey.toUpperCase()}.</div>` |
| otherwise | see below |

The last row renders:
- `<IssueCard issue={result.issue} runId="" deleteEnabled={false} />`
- an `<h5>` with `plural(result.links.length, "linked run")`, and below it the `summary` in
  `small text-muted`
- an inset frame, `run-list mx-2 p-2 d-flex flex-column gap-2 border rounded bg-light-three`, with
  `box-shadow: var(--bs-box-shadow-inset)`. It holds:
  - a column header, `row g-2 px-2 small text-muted text-uppercase d-none d-lg-flex`: Status
    (`col-lg-1`), Test (`col-lg-5`), Build (`col-lg-1`), Started (`col-lg-2`), Version
    (`col-lg-1`)
  - `{#each result.links as link (link.run_id)}<LinkedRun {link} />{/each}`
- or, when there are no links,
  `<div class="alert alert-secondary">No test runs are linked to {result.issue.key}.</div>`

**Tests:**
- Mocks: `vi.mock("../WorkArea/TestRuns.svelte", () => ({ default: vi.fn() }))`, plus the
  `AlertStore` and `UserlistSubscriber` mocks from the Rules.
- `fetch` returns the body under test. The Jira issue fixture follows `JIRA_ISSUE` in
  `frontend/Common/IssueCard.test.ts:37-51`, without `links`.

Cases:
- `requests the lookup for the key`: `fetch` was called with `/api/v1/issues/SCT-1234/links`.
- `renders the issue and its runs in order`: two links of one test and one version.
  - The issue summary renders.
  - "2 linked runs" and "1 test · 1 version · 2 failed" render.
  - The two test names appear in API order.
- `shows that Argus holds no such issue`: `{issue: null, links: []}`. "Argus holds no issue
  SCT-1234." renders.
- `shows an issue without runs`: `links: []`. The summary and "No test runs are linked to
  SCT-1234." render.
- `shows the API error`: `{status: "error", response: {exception: "IssueServiceException", arguments: ["Not an issue key: 'SCT1234'. Expected a Jira key such as SCT-1234."]}}`.
  The alert holds that message.

- [x] Write the tests.
- [x] Run `yarn vitest run frontend/IssueLinks/IssueLinks.test.ts` and confirm the failure (the
  module does not exist).
- [x] Write the component.
- [x] Run it again until it passes.

## Task 6 — Bundle the page

**Files:**
- Create: `frontend/issue-links.js`
- Modify: `vite.config.ts`: add `issueLinks: "./frontend/issue-links.js",` after `teams` (l.56).

**Internals:** `frontend/issue-links.js`, in the form of `frontend/run-by-plugin.js`:

```js
import IssueLinks from "./IssueLinks/IssueLinks.svelte";
import { mount } from "svelte";

const app = mount(IssueLinks, {
    target: document.querySelector("div#issueLinks"),
    props: {
        issueKey: gIssueKey,
    },
});
```

- [x] Add the entry point and the input.
- [x] Run `yarn build`, and check that `public/dist/issueLinks.bundle.js` exists.

## Task 7 — Show an aborted status in the dark theme

**Files:**
- Modify: `frontend/argus.scss`: the light rules after `.bg-test-error` (l.57), the dark rules
  after the dark `.bg-test-error` in the `[data-bs-theme="dark"]` block.
- Modify: `frontend/Common/TestStatus.js`:
  - `StatusBackgroundCSSClassMap.aborted` and `StatusButtonCSSClassMap.aborted`
  - the new `StatusBadgeCSSClassMap`, before `StatusTableBackgroundCSSClassMap`

**Internals:**

```scss
.bg-aborted {
    background-color: $dark;
}

.btn-aborted {
    @include button-variant($dark, $dark);
}

[data-bs-theme="dark"] {
    .bg-aborted {
        background-color: $gray-700;
    }

    .btn-aborted {
        @include button-variant($gray-700, $gray-700);
    }
}
```

- `argus.scss` imports Bootstrap's SCSS, so `$dark`, `$gray-700` and `button-variant` resolve.
- `.bg-dark` itself stays: navbars and other dark surfaces use it.
- `StatusBackgroundCSSClassMap.aborted` becomes `"bg-aborted"`, and
  `StatusButtonCSSClassMap.aborted` becomes `"btn-aborted"`.
- `StatusBadgeCSSClassMap` maps each status to a background and text pair:
  - `text-bg-*` for the Bootstrap colors
  - `bg-test-error text-white`, `bg-aborted text-white` and `bg-not-planned text-dark` for the
    custom ones

No unit test: the change is CSS. Task 9 checks it in a browser.

- [x] Add the classes and the map.
- [x] Run `yarn build` and check the aborted badge, pill and status button in both themes.

## Task 8 — Lay out the issue cards on two lines

A commit of its own.

**Files:**
- Modify: `frontend/Jira/JiraIssue.svelte` and `frontend/Github/GithubIssue.svelte`, the card
  block at the top of the markup (`<div class="row m-2">`). The run-list pop-up and the delete
  dialog stay.

**Internals:** the same layout in both cards, with no fixed width:
- `issue-card col rounded border p-2 bg-white`, with `box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05)` in
  place of `shadow-sm`.
- The first line, `d-flex flex-wrap align-items-center gap-2`, holds:
  - the state pill, without its fixed `10em` column
  - the brand icon and the key as a link, `fw-bold text-nowrap link-body-emphasis
    link-underline-opacity-0 link-underline-opacity-75-hover`. The key is `{issue.key}` for Jira
    and `{issue.owner}/{issue.repo}#{issue.number}` for GitHub.
  - the label buttons, unchanged but for the `me-1` that the `gap` replaces
  - `ms-auto` on the existing "Added by", delete and aggregated-actions block
- The second line is the summary (Jira) or the title (GitHub), as a `d-block mt-1` link with
  `link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover`. It drops the fixed
  `30em` width. Its box starts at the state pill's left edge and ends at the right edge of the
  "Added by" block.

**Tests:** `frontend/Common/IssueCard.test.ts` and `frontend/Github/Issues.test.ts` render both
cards and keep passing. No new test: the change is layout.

- [x] Rework both cards.
- [x] Run `yarn test`.
- [x] Check the cards on `/issues/<key>` and on a run's issue tab, in both themes and at 600 px.

## Task 9 — Verify

- [x] Run `uv run pre-commit run --all-files`, `uv run pytest` and `yarn test`.
- [x] On the dev server, with the ARGUS-209 indexes in place (`sync-models`):
  - `/issues/<a real key with links>`:
    - the Jira card, the count and the rows render
    - "Open run" lands on `/test/<build_id>/<n>`
    - "Show inline" shows the run pills and the linked run expanded, with no title bar
    - "Hide" removes the inline view
  - `/issues/sct-99999999`: "Argus holds no issue SCT-99999999."
  - `/issues/SCT1234`: the alert with the API message
  - logged out, `/issues/<key>`: the login page, then back to the issue page
  - the page at a narrow width and a wide width (`docs/standards/frontend/responsive.md`)
- [x] Hand the diff to the user for review. After approval, make two commits, each with the
  checked boxes of its tasks:
  - Tasks 1–7 as `feature(issues): …`
  - Task 8 as `improvement(frontend/issues): …`
- [ ] The PR body ends with `closes ARGUS-210`.

## Task 10 — Give each run selector its own ignore-runs dialog

From the review of PR #1120.

**Files:**
- Modify: `frontend/WorkArea/TestRunsSelector.svelte`
- Test: `frontend/WorkArea/TestRunsSelector.test.ts`

**Internals:**
- `let ignoreRunsDialog: HTMLElement | undefined = $state();`, bound with `bind:this` on the
  dialog's `<div class="modal">`, which drops its `id="modalIgnoreRuns-{testInfo.test.id}"`.
- The ban button opens `new Modal(ignoreRunsDialog)` in place of the `#modalIgnoreRuns-…` selector,
  which found the first selector of that test on the page.

**Tests:**
- `opens the dialog of the selector that was clicked`: two selectors with one `testInfo`. A click
  on the second one's "Ignore failed runs" shows the second one's `.modal` and leaves the first one
  hidden. Stubs: `IntersectionObserver`, and `fetch` for the `HEAD` on `/api/v1/test-results`.

- [x] Write the test.
- [x] Run `yarn vitest run frontend/WorkArea/TestRunsSelector.test.ts` and confirm the failure
  (the first selector's dialog opens).
- [x] Bind the dialog.
- [x] Run it again until it passes.
- [x] On `/issues/<key>`, open two runs of one test inline and click "Ignore failed runs" in the
  second: only its dialog opens.

## Task 11 — Load inline runs without refresh timers

From the review of PR #1120.

**Files:**
- Modify: `frontend/WorkArea/TestRuns.svelte`, `frontend/WorkArea/TestRunDispatcher.svelte`, the
  four plugin run views and `frontend/IssueLinks/LinkedRun.svelte`
- Test: `frontend/WorkArea/TestRuns.test.ts`, `frontend/IssueLinks/LinkedRun.test.ts`

**Internals:**
- `autoRefresh = true` next to `updateUrl` in `TestRuns`, `TestRunDispatcher` and each plugin run
  view, passed down the same way.
- `TestRuns` sets its 120 s run-list timer only when `autoRefresh` holds. Each plugin view sets
  its run-data timer (120 s for SCT, 300 s for the others) only when it holds.
- `LinkedRun` passes `autoRefresh={false}`.
- The Events tab (stops itself on a finished run) and the Discussion tab keep their timers.

**Tests:**
- `refreshes the run list every two minutes by default`: with
  `vi.useFakeTimers({ shouldAdvanceTime: true })`, one run-list fetch after the pill renders and
  a second after `advanceTimersByTimeAsync(120_000)`.
- `does not refresh the run list when autoRefresh is false`: still one fetch after 120 s.
- `passes autoRefresh on to the run view`: the dispatcher gets `autoRefresh === false`.
- `opens the run inline` in `LinkedRun.test.ts` also checks `autoRefresh === false`.

- [x] Write the tests.
- [x] Run them and confirm the three failures.
- [x] Add the flag.
- [x] Run `yarn test` until it passes.
- [x] In Chrome, with `setInterval` recorded: opening a run inline on `/issues/<key>` adds no 120 s
  or 300 s timer, and the run's own page still sets its two 120 s timers.

## Task 12 — Fit the status badge and the buttons in their columns

From the review of PR #1120. It replaces the `col-lg-1` status, `col-lg-5` test and `col-lg-2`
actions columns of Tasks 4 and 5.

**Files:**
- Modify: `frontend/IssueLinks/LinkedRun.svelte` and `frontend/IssueLinks/IssueLinks.svelte`

**Internals:**
- The row and the header use `col-auto status-col` for the status, `col` for the test, and
  `col-auto actions-col` for the buttons. The header gains an empty `actions-col` cell.
- `IssueLinks.svelte` sizes both from the `lg` breakpoint, for the header and every row:
  `@media (min-width: 992px)` with `.run-list :global(.status-col) { width: 7.5rem; }` and
  `.run-list :global(.actions-col) { width: 12.5rem; }`.
- Measured before: the `col-lg-1` status content is 68, 83 and 98 px at the `lg`, `xl` and `xxl`
  widths. "NOT PLANNED" (104 px) overflowed it at all three, "TEST ERROR" (88 px) up to 1399 px,
  "RUNNING" and "ABORTED" at `lg`. The 182 px button group overflowed its 143 px `col-lg-2` at
  `lg` and covered the version.

No unit test: jsdom does no layout.

- [x] Change the columns.
- [x] In Chrome, with the lookup answered by statuses `test_error`, `not_planned`, `aborted`,
  `running` and `passed`, at 992, 1100, 1199, 1200, 1300, 1399, 1400 and 1920 px: every badge
  and the button group stay inside their columns, and the header lines up with the rows.
