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
{{ key }}
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

- [ ] Write the tests.
- [ ] Run `uv run pytest argus/backend/tests/main_api/test_issue_page.py` and confirm the failure
  (HTTP 404).
- [ ] Add the route and the template.
- [ ] Run it again until it passes.

## Task 2 — Let the run selector hide its title bar

**Files:**
- Modify: `frontend/WorkArea/TestRuns.svelte`:
  - the JSDoc `Props` typedef (l.27–34)
  - the `$props()` destructuring (l.37)
  - the title-bar block (l.337–406)
- Test: `frontend/WorkArea/TestRuns.test.ts`

**Internals:**
- `@property {boolean} [showTitleBar]` in the typedef. `showTitleBar = true` in the
  destructuring.
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
  This keeps the plugin run views out of the import graph. No run is opened, so
  `TestRunDispatcher` never renders.
- The `AlertStore` mock from the Rules.

Stubs:
- `IntersectionObserver`, a class with `observe` and `disconnect`, for `TestRunsSelector`.
- `fetch`, routed by URL:
  - `/api/v1/test-info?…` returns
    `{test: {id, name: "longevity-frobnicator-4h", plugin_name: "scylla-cluster-tests", build_system_id, build_system_url}, release: {id, name: "master"}, group: {id, name: "longevity"}}`
  - `/api/v1/test/{id}/runs?…` returns one run, `{id, status: "failed", build_number: 412, start_time}`
  - the `HEAD` on `/api/v1/test-results` returns status 404

Cases:
- `shows the title bar by default`: `findByRole("button", { name: /longevity-frobnicator-4h/ })`
  resolves, and the run pill `#412` renders.
- `hides the title bar when showTitleBar is false`: after the pill `#412` renders,
  `queryByRole("button", { name: /longevity-frobnicator-4h/ })` is `null`, and `#412` appears
  once.

- [ ] Write the tests.
- [ ] Run `yarn vitest run frontend/WorkArea/TestRuns.test.ts`. The second case fails because the
  title bar is there.
- [ ] Add the prop and the `{#if}`.
- [ ] Run it again until it passes.

## Task 3 — Type the lookup response

**Files:**
- Modify: `frontend/Common/IssueTypes.ts`: add the two interfaces after `JiraSubtype` (l.62–69).

**Internals:** `LinkedRun` and `IssueLinks`, exactly as the spec's `Module API` states them.

- [ ] Add the interfaces.

## Task 4 — Render one linked run

**Files:**
- Create: `frontend/IssueLinks/LinkedRun.svelte`
- Test: `frontend/IssueLinks/LinkedRun.test.ts`

**Internals:**
- `let { link }: { link: LinkedRun } = $props();`
- `let open = $state(false);`
- `const version = $derived(link.scylla_version || link.product_version);`

The markup is one `bg-white rounded shadow-sm p-2 mb-2` card with a `d-flex flex-wrap
align-items-center gap-2` summary line, which holds:
- a `status-circle` span with `StatusBackgroundCSSClassMap[link.status] ?? StatusBackgroundCSSClassMap.unknown`
  and `title={titleCase(link.status)}`, styled as in `TestRuns.svelte` (the `.status-circle`
  rule)
- `link.test_name` in `fw-bold text-truncate`, then `#{link.build_number}`
- `timestampToISODate(link.start_time)`
- `{#if version}` the version in a `font-monospace` span
- `{#if link.linked_on}` `linked {timestampToISODate(link.linked_on)}` in `text-muted`
- `ms-auto` on a button group:
  - `<a class="btn btn-sm btn-primary" href={link.url}>` with `faExternalLinkAlt` and "Open run"
  - `<button class="btn btn-sm btn-outline-secondary" aria-expanded={open} onclick={() => (open = !open)}>`,
    labelled "Show inline" or "Hide", with `faChevronDown` or `faChevronUp`

Below the summary line:

```svelte
{#if open}
    <TestRuns testId={link.test_id} additionalRuns={[link.run_id]} tab="details" showTitleBar={false} />
{/if}
```

**Tests:** `vi.mock("../WorkArea/TestRuns.svelte", () => ({ default: vi.fn() }))`. The fixture
link has these values:
- `test_name: "longevity-frobnicator-4h"`
- `status: "failed"`
- `build_number: 412`
- `scylla_version: "2026.2.0~dev"`
- `url: "http://testserver/test/frobnicator/longevity/412"`

Cases:
- `shows the run summary`:
  - the test name, `#412`, `2026.2.0~dev` and `linked …` render
  - the status span's title is `Failed`
- `falls back to the product version`: with `scylla_version: null` and
  `product_version: "2026.1.3"`, `2026.1.3` renders.
- `links to the run page`: the "Open run" link has `href === link.url`.
- `opens the run inline`:
  - one click sets `aria-expanded="true"`
  - `TestRuns` was called once, with props `testId === link.test_id`,
    `additionalRuns` equal to `[link.run_id]`, `tab === "details"` and `showTitleBar === false`
  - a second click sets `aria-expanded="false"`
  - a third click calls `TestRuns` a second time

- [ ] Write the tests.
- [ ] Run `yarn vitest run frontend/IssueLinks/LinkedRun.test.ts` and confirm the failure (the
  module does not exist).
- [ ] Write the component.
- [ ] Run it again until it passes.

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

The markup, in this order:

| Condition | Renders |
|---|---|
| `error` | `<div class="alert alert-danger">` with the message |
| `!result` | `spinner-border spinner-border-sm` and "Loading runs linked to {issueKey}…" |
| `!result.issue` | `<div class="alert alert-secondary">Argus holds no issue {issueKey.toUpperCase()}.</div>` |
| otherwise | see below |

The last row renders:
- `<IssueCard issue={result.issue} runId="" deleteEnabled={false} />`
- an `<h5>` with "{result.links.length} linked runs"
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
- `renders the issue and its runs in order`: two links. The summary renders, and the two test
  names appear in API order.
- `shows that Argus holds no such issue`: `{issue: null, links: []}`. "Argus holds no issue
  SCT-1234." renders.
- `shows an issue without runs`: `links: []`. The summary and "No test runs are linked to
  SCT-1234." render.
- `shows the API error`: `{status: "error", response: {exception: "IssueServiceException", arguments: ["Not an issue key: 'SCT1234'. Expected a Jira key such as SCT-1234."]}}`.
  The alert holds that message.

- [ ] Write the tests.
- [ ] Run `yarn vitest run frontend/IssueLinks/IssueLinks.test.ts` and confirm the failure (the
  module does not exist).
- [ ] Write the component.
- [ ] Run it again until it passes.

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

- [ ] Add the entry point and the input.
- [ ] Run `yarn build`, and check that `public/dist/issueLinks.bundle.js` exists.

## Task 7 — Verify

- [ ] Run `uv run pre-commit run --all-files`, `uv run pytest` and `yarn test`.
- [ ] On the dev server, with the ARGUS-209 indexes in place (`sync-models`):
  - `/issues/<a real key with links>`:
    - the Jira card, the count and the rows render
    - "Open run" lands on `/test/<build_id>/<n>`
    - "Show inline" shows the run pills and the linked run expanded, with no title bar
    - "Hide" removes the inline view
  - `/issues/sct-99999999`: "Argus holds no issue SCT-99999999."
  - `/issues/SCT1234`: the alert with the API message
  - logged out, `/issues/<key>`: the login page, then back to the issue page
  - the page at a narrow width and a wide width (`docs/standards/frontend/responsive.md`)
- [ ] Hand the diff to the user for review. After approval, commit Tasks 1–6 as one
  `feature(issues): …` commit, with the checked boxes of this plan.
- [ ] The PR body ends with `closes ARGUS-210`.
