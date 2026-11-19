# ARGUS-278 — implementation plan

**Spec:** `tasks/ARGUS-278/rca.md`

A decision during the build that changes what the rca states updates the rca
in the same commit.

## Rules

- Follow `docs/standards/frontend/components.md` and
  `docs/standards/testing/test-writing.md`. The helpers are TypeScript in
  `frontend/Common/`, the home of a shared helper.
- Keep DOMPurify with its default config. The Sanitizer API is not Baseline
  Widely available.
- Touch only the import lines, the `marked.use(...)` block and the rendering
  line of each component. ARGUS-276 edits the markup of some of the same files
  for a11y warnings, and ARGUS-274 rewrites `ModalWindow`, a parent of
  `JobConfigureModal`. Do not touch `ModalWindow`, `vite.config.ts` or
  `templates/base.html.j2`.
- Leave `frontend/Chat/markdown.ts` as it is.
- No comment that justifies the change. Every import at the top of the
  module.
- The change stays uncommitted until it is reviewed. The commit then uses the
  header `fix(frontend): ...`, at most 72 characters, a short body, and the
  last line `Fixes ARGUS-278`.

## Task 1 — The shared helpers

**Files:**
- Create: `frontend/Common/safeHtml.ts`
- Create: `frontend/Common/markdown.ts`
- Test: `frontend/Common/safeHtml.test.ts`
- Test: `frontend/Common/markdown.test.ts`

**Internals:**

```ts
// frontend/Common/safeHtml.ts
export const sanitizeHtml = (html: string | null | undefined): string
// frontend/Common/markdown.ts
export const renderMarkdown = (text: string, { mentions = false }: { mentions?: boolean } = {}): string
```

Two modules, because `MarkdownUserMention` loads `argus.js`, which reads the
page global `gArgusCurrentUser`; `sanitizeHtml` callers and their tests must
not load it.

`sanitizeHtml` sanitizes `html ?? ""` with a dedicated instance,
`DOMPurify(window)`, and `ADD_ATTR: ["target"]`; an `afterSanitizeAttributes`
hook on that instance sets `rel="noopener noreferrer"` on every element with
a `target`. The global `DOMPurify` of `Chat/markdown.ts` keeps no hook. Two module-level
instances, `new Marked({ gfm: true, breaks: true, async: false })` and the
same with `extensions: [MarkdownUserMention]` from
`frontend/Discussion/MarkedMentionExtension.js`. `renderMarkdown` picks one by
`mentions`, parses `text ?? ""`, and returns `sanitizeHtml` of the result. No
`highlight` and no `langPrefix`: marked 16 ignores both, so the output of the
sites does not change.

`markdown.test.ts` mocks `../argus` with
`vi.mock("../argus", () => ({ applicationCurrentUser: { username: "admin" } }))`,
as `frontend/WorkArea/TestRuns.test.ts` does, because `argus.js` reads the
page global `gArgusCurrentUser`. Cases, by behavior:

`markdown.test.ts`, for `renderMarkdown`:
- `drops a javascript: link`: `[x](javascript:alert(1))` gives an `<a>` with
  no `href`, and no `javascript:` in the output.
- `drops a javascript: link written with an entity`:
  `[x](javascript&#58;alert(1))`, the same assertion.
- `strips an event handler from raw HTML`: `<img src="x" onerror="alert(1)">`
  keeps the `<img>` and drops `onerror`.
- `keeps ordinary markdown`: `**b**`, `` `c` ``, a fenced `js` block, an
  `https` link, a two-column table and a `- [x] done` task list render
  `<strong>`, `<code>`, `<pre><code class="language-js">`, the `href`, a
  `<table>` and a checked disabled checkbox.
- `renders a mention only when asked`: `hi @admin` gives
  `<span class="user-mention ...">@admin</span>` with `mentions: true`, and
  plain text without.

`safeHtml.test.ts`, for `sanitizeHtml`:
- `strips script from server HTML`: `<a href="javascript:alert(1)">x</a>`,
  `<img src="x" onerror="alert(1)">` and `<script>alert(1)</script>` lose the
  `href`, the `onerror` and the script.
- `keeps the links and markup the server sends`: the performance regression
  event text, a mention notification as `mention.html.j2` renders it, a pytest
  `<a href="https://...">` field, a Jenkins description with `<br>` and a link,
  and the 404 validation message keep their tags and `href`.
- `strips script from the validation message`: the 404 message built with the
  branch `"><img src=x onerror=alert(1)>` keeps the link and loses `onerror`.
- `keeps target on a link and forces rel`: `target="_blank"` stays, and `rel`
  becomes `noopener noreferrer`, also over `rel="opener"`.
- `keeps a target without href harmless`: `<a target="_blank" onclick=...>`
  keeps no `href` and no `onclick`, and gets the forced `rel`.
- `keeps the markup and the run link of a results graph tooltip`: the span
  keeps its `style`, and the "Open" link its `href`, `class`, `target` and icon.
- `returns an empty string for a missing value`: `undefined` and `null` give
  `""`.

- [x] Write the tests, and first helpers that return their input unsanitized,
      the code the sites run today.
- [x] Run `yarn test frontend/Common` and confirm the script cases fail and
      the others pass.
- [x] Sanitize with DOMPurify.
- [x] Run the tests again and confirm they pass.

## Task 2 — Move every markdown site onto `renderMarkdown`

**Files:**
- Modify: `frontend/Discussion/Comment.svelte:2,10-11,36-38,145`
- Modify: `frontend/Discussion/CommentEditor.svelte:5,24,335-338`
- Modify: `frontend/Views/Widgets/ViewHighlights/HighlightItem.svelte:8-10,40-42,82`
- Modify: `frontend/Views/Widgets/ViewHighlights/ActionItem.svelte:9-11,50-52,92`
- Modify: `frontend/Views/Widgets/ViewHighlights/Comment.svelte:7-8,73`
- Modify: `frontend/Teams/TeamDetail.svelte:5-6,12,192`
- Modify: `frontend/TestRun/IssueTemplate.svelte:6,11,73-74`
- Modify: `frontend/TestRun/Sirenada/SirenadaIssueTemplate.svelte:4,6,18`
- Delete: `frontend/markdownOptions.js`

At each site, import `renderMarkdown` from `Common/markdown` and drop the
imports of `marked`, `markdownRendererOptions`, `MarkdownUserMention` and
`DOMPurify` that the file no longer uses. Remove the three
`marked.use({ extensions: [MarkdownUserMention] })` blocks.

| Site | New call |
|---|---|
| `Discussion/Comment.svelte` | `{@html renderMarkdown(commentBody.message, { mentions: true })}` |
| `Discussion/CommentEditor.svelte` | `{@html renderMarkdown(commentBody.message, { mentions: true })}` |
| `ViewHighlights/HighlightItem.svelte` | `{@html renderMarkdown(highlight.content, { mentions: true })}` |
| `ViewHighlights/ActionItem.svelte` | `{@html renderMarkdown(action.content, { mentions: true })}` |
| `ViewHighlights/Comment.svelte` | `{@html renderMarkdown(comment.content, { mentions: true })}` |
| `Teams/TeamDetail.svelte` | `{@html renderMarkdown(team.motd)}` |
| `TestRun/IssueTemplate.svelte` | `renderedElement.innerHTML = renderMarkdown(templateElement.innerHTML)`, and the same for `renderedShortElement` |
| `TestRun/Sirenada/SirenadaIssueTemplate.svelte` | `renderedElement.innerHTML = renderMarkdown(templateElement.innerHTML)` |

Then `grep -rn "markdownOptions\|from \"marked\"" frontend` lists only
`Common/markdown.ts` and `Chat/markdown.ts`.

- [x] Change the eight sites and delete `frontend/markdownOptions.js`.

## Task 3 — Sanitize the non-markdown sites

**Files:**
- Modify: `frontend/TestRun/ActivityTab.svelte:5,70`
- Modify: `frontend/Profile/Notification.svelte:6,86`
- Modify: `frontend/Views/Widgets/PytestWidget/PytestResultRow.svelte:8,108`
- Modify: `frontend/TestRun/Pytest/PytestItem.svelte:6,88`
- Modify: `frontend/TestRun/Jenkins/ParameterEditor.svelte:6,98`
- Modify: `frontend/TestRun/Jenkins/SCTParameterWizard.svelte:10,713`
- Modify: `frontend/TestRun/Jenkins/CloneTargetSelector.svelte:8,234`
- Modify: `frontend/WorkArea/JobConfigureModal.svelte:7,175`
- Modify: `frontend/TestRun/ResultsGraph.svelte:10,249`

At each site, import `sanitizeHtml` from `Common/safeHtml` after the last
import, and wrap the expression of the `{@html}` tag, or of the `innerHTML`
assignment in `ResultsGraph.svelte`:

| Site | New tag |
|---|---|
| `ActivityTab.svelte` | `{@html sanitizeHtml(activity.events[event.id])}` |
| `Notification.svelte` | `{@html sanitizeHtml(notification.content)}` |
| `PytestResultRow.svelte`, `PytestItem.svelte` | `{@html sanitizeHtml(value)}` |
| `ParameterEditor.svelte` | `{@html sanitizeHtml(param.description)}` |
| `SCTParameterWizard.svelte` | `{@html sanitizeHtml(param.description ?? rawParams.find(v => v.name == param.internalName)?.description)}` |
| `CloneTargetSelector.svelte`, `JobConfigureModal.svelte` | `{@html sanitizeHtml(validationMessage)}` |
| `ResultsGraph.svelte` | `tooltipEl.innerHTML = sanitizeHtml(innerHtml)` |

Then every `{@html` in `frontend/` passes through `renderMarkdown`,
`sanitizeHtml`, the chat's `renderMarkdown` or `hljs.highlight`.

- [x] Change the nine sites.

## Task 4 — Verify

- [x] Run `uv run pre-commit run --all-files`, `yarn test` and `yarn build`.
      Compare the build warnings with a build of the base commit.
- [x] Run `yarn build:dev`, start the worktree server on :5018, and repeat the
      reproduction of `rca.md` in headless Chrome. One probe view, one
      highlight, one action item, one highlight comment and one run comment,
      each with the `javascript:` link, the `&#58;` link, the quoted
      `<img onerror>`, an `https` link, bold text and an `@admin` mention.
      Confirm no dialog opens on load or on a click, and the benign markdown,
      the mention and the link render. Take a screenshot of each page.
- [ ] Hover a results graph tooltip and follow its "Open" link. Not done: the
      dev database has result metadata for three tests and graph data for
      none, so no graph renders; the tooltip case of `safeHtml.test.ts`
      covers its markup.
- [x] Check that the team message of the day, an issue template preview and
      the activity tab of a run still render. Reach no site through a call
      that changes a run status or sends a notification.
- [x] Delete every item the API can delete, and list the rows left with the
      CQL that removes them.
- [x] Leave the change uncommitted for review.
