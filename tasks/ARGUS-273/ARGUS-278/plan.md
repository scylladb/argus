# ARGUS-278 — implementation plan

**Spec:** `tasks/ARGUS-273/ARGUS-278/rca.md`

A decision during the build that changes what the rca states updates the rca
in the same commit.

## Rules

- Follow `docs/standards/frontend/components.md` and
  `docs/standards/testing/test-writing.md`. The helper is a TypeScript module
  in `frontend/Common/`, the home of a shared helper.
- Keep DOMPurify. The Sanitizer API is not Baseline Widely available.
- Touch only the import lines, the `marked.use(...)` block and the rendering
  line of each component. ARGUS-276 edits the markup of the same files for
  a11y warnings, and the two branches must merge cleanly.
- Leave `frontend/Chat/markdown.ts` as it is.
- Commit header `fix(frontend): ...` at most 72 characters, a short body,
  last line `Fixes ARGUS-278`. Stage by explicit path. Commit with
  `uv run git commit`.
- Verify sequence, from `CLAUDE.md`: `uv run pre-commit run --all-files`,
  `uv run pytest`, `yarn test`, and `yarn build` for a change under
  `frontend/`.

## Task 1 — Shared helper that parses and sanitizes

**Files:**
- Create: `frontend/Common/markdown.ts`
- Test: `frontend/Common/markdown.test.ts`

**Internals:**

```ts
export const renderMarkdown = (text: string, { mentions = false }: { mentions?: boolean } = {}): string
```

Two module-level instances, `new Marked({ gfm: true, breaks: true, async: false })`
and the same with `extensions: [MarkdownUserMention]` from
`frontend/Discussion/MarkedMentionExtension.js`. `renderMarkdown` picks one by
`mentions`, parses `text ?? ""`, and returns `DOMPurify.sanitize(html)` with
the default config. No `highlight` and no `langPrefix`: marked 16 ignores both,
so the output of the sites does not change.

The test mocks `../argus` with
`vi.mock("../argus", () => ({ applicationCurrentUser: { username: "admin" } }))`,
as `frontend/WorkArea/TestRuns.test.ts` does, because `argus.js` reads the
page global `gArgusCurrentUser`. Cases, by behavior:

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

- [ ] Write the test file, and a first `markdown.ts` that returns the parse
      result without `DOMPurify.sanitize`, the code the sites run today.
- [ ] Run `yarn test frontend/Common/markdown.test.ts` and confirm the three
      security cases fail and the other two pass.
- [ ] Wrap the result in `DOMPurify.sanitize`.
- [ ] Run the test file again and confirm it passes.
- [ ] Commit, with the boxes of this task checked.

## Task 2 — Move every markdown site onto the helper

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

- [ ] Change the eight sites and delete `frontend/markdownOptions.js`.
- [ ] Run `yarn build:dev`, start the worktree server on a free port, and
      repeat the reproduction of `rca.md` in headless Chrome: a run comment,
      a view highlight, an action item and a highlight comment, each with the
      `javascript:` link, the `&#58;` link and the quoted `<img onerror>`.
      Confirm no dialog opens on load or on a click, the benign markdown and
      a mention render, and the team message of the day and an issue template
      preview still render.
- [ ] Delete every item the check created, and the probe view, and list them.
- [ ] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [ ] Commit, with the boxes of this task checked.
