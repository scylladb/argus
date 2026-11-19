# ARGUS-278 — Rendered markdown runs script from user text

**Date**: 2026-11-19

## Root cause

**The markdown sites hand the output of `marked` to `{@html}` as it is.**
Five components parse user text with the global `marked` instance and render
the string with no sanitizer:

| Site | Line | Text |
|---|---|---|
| `frontend/Discussion/Comment.svelte` | 145 | run comment |
| `frontend/Discussion/CommentEditor.svelte` | 335-338 | preview of the comment being written |
| `frontend/Views/Widgets/ViewHighlights/HighlightItem.svelte` | 82 | view highlight |
| `frontend/Views/Widgets/ViewHighlights/ActionItem.svelte` | 92 | view action item |
| `frontend/Views/Widgets/ViewHighlights/Comment.svelte` | 73 | highlight comment |

```svelte
{@html marked.parse(commentBody.message, markdownRendererOptions)}
```

Two more sites assign the output of `marked` to `innerHTML` the same way.
Their input is run data that a client submitted, interpolated into a hidden
template element, so Svelte has already escaped its markup. A markdown link
in that data still becomes a live link:

| Site | Line | Text |
|---|---|---|
| `frontend/TestRun/IssueTemplate.svelte` | 73-74 | issue template preview, from the run |
| `frontend/TestRun/Sirenada/SirenadaIssueTemplate.svelte` | 18 | Sirenada issue template preview |

**`marked` does not filter URLs.** marked 16.1.2 renders the link
destination as written. Every variant below survives the backend's escaping.
A Node probe fed each payload, escaped as `strip_html_tags` escapes it, to
`marked.parse`:

```
## js_link        escaped:  <p><a href="javascript:alert(1)">x</a></p>
## js_link_entity escaped:  <p><a href="javascript&#58;alert(1)">x</a></p>
## js_ref         escaped:  <p><a href="javascript:alert(1)">x</a></p>
## data_link      escaped:  <p><a href="data:text/html;base64,...">x</a></p>
```

The browser decodes `&#58;` inside the attribute, so a filter that matched
the string `javascript:` would miss the second form.

**The backend escapes only `<` and `>`, and not on every path.**
`strip_html_tags`, `argus/backend/util/common.py:67-68`:

```python
def strip_html_tags(text: str):
    return text.replace("<", "&lt;").replace(">", "&gt;")
```

A run comment is escaped on post and on edit (`argus/backend/service/testrun.py:378`
and `:448`), a highlight and an action item on create and on update
(`argus/backend/service/views_widgets/highlights.py:231` and `:306`). A
highlight comment is not. `create_comment` and `update_comment` compute the
escaped text for the mention lookup and then store the raw payload,
`highlights.py:357-364` and `:386-387`:

```python
        mentions, content_stripped = await self._process_mentions(payload.content, creator_id)
        comment = WidgetComment(
            ...
            content=payload.content,
```

So raw HTML reaches `ViewHighlights/Comment.svelte`, and `marked` passes an
HTML block through untouched. Both paths date from the highlights widget,
82a60518 (2024-10-31).

**The one safe site.** `frontend/Teams/TeamDetail.svelte:192`, since
e31b4494 (2022-12-07):

```svelte
{@html DOMPurify.sanitize(parse(team.motd, markdownRendererOptions))}
```

**Live reproduction**, 2026-11-19, dev database through the API, worktree
server on :5018 (`yarn build:dev`), headless Chrome 157 driven over CDP with
`Page.javascriptDialogOpening` hooked. Each item held a `javascript:` link, the
same link with `&#58;`, `<img src=x onerror=alert('<site>-img')>`, and benign
markdown. A real mouse click (`Input.dispatchMouseEvent`) on each link:

```
PAGE /test/enterprise-2024.1/artifacts-offline-install/artifacts-oel76-test/6/discuss
  mouse click jslink-run: EXECUTED ["run-js"]
  mouse click entlink-run: EXECUTED ["run-ent"]
PAGE /view/argus-278-xss-probe
  mouse click jslink-hl: EXECUTED ["hl-js"]
  mouse click entlink-hl: EXECUTED ["hl-ent"]
  mouse click jslink-hc: EXECUTED ["hc-js"]
  mouse click entlink-hc: EXECUTED ["hc-ent"]
  mouse click jslink-ai: EXECUTED ["ai-js"]
  mouse click entlink-ai: EXECUTED ["ai-ent"]
```

The `<img>` payload rendered as text in the run comment, the highlight and
the action item, because the backend had escaped it. In the highlight comment
it first rendered as text too: CommonMark does not take an unquoted attribute
value that holds `'`, so `onerror=alert('hc-img')` was not an HTML tag. The
quoted form `<img src="x" onerror="alert('hc-img-onload')">` ran as soon as
the comments were expanded, with no click:

```
  DIALOG: alert "hc-img-onload"
  live <img src=x> elements: ["<img src=\"x\" onerror=\"alert('hc-img-onload')\">"]
```

DOMPurify 3.2.6 with its default config removes each of these, in a Node
probe under jsdom:

```
"[x](javascript:alert(1))" => <p><a>x</a></p>
"[x](javascript&#58;alert(1))" => <p><a>x</a></p>
"<img src=x onerror=alert(1)>" => <img src="x">
"<a href=\"#\" onclick=\"alert(1)\">c</a>" => <p><a href="#">c</a></p>
```

**Two side findings in the same code.**

- `markdownRendererOptions`, `frontend/markdownOptions.js`, passes
  `highlight` and `langPrefix`. marked dropped both options before version 16,
  so a fenced block renders `<code class="language-js">` with no highlighting.
  Only `gfm: true` and `breaks: true` take effect.
- `Comment.svelte:36-38`, `HighlightItem.svelte:40-42` and
  `ActionItem.svelte:50-52` call `marked.use({ extensions: [MarkdownUserMention] })`
  in the component body. That changes the global instance on every mount, so
  mentions render in `CommentEditor`, `ViewHighlights/Comment`, and the issue
  templates only when one of those components mounted first.

### Other `{@html}` sites

The grep of `frontend/` finds 22 `{@html}` sites. The ones not above:

| Site | Source of the HTML | Status |
|---|---|---|
| `Chat/ChatMessage.svelte:82,94,155`, `Chat/ChatActionCard.svelte:103,220,253` | `renderMarkdown` of `Chat/markdown.ts` | Sanitized, with a stricter config |
| `Teams/TeamDetail.svelte:192` | team message of the day | Sanitized |
| `TestRun/ActivityTab.svelte:70` | activity event text, formatted on the server by `str.format` from user names, GitHub and Jira issue titles, and the free-text reason of `POST /ignore_jobs` (`testrun.py:559-561`), none escaped. The performance regression event of `plugins/sct/service.py:317-319` carries an `<a href>` to the compared runs | Unsafe, by code reading. Not reproduced live: `ignore_jobs` rewrites the investigation status of every failed run of a test |
| `Profile/Notification.svelte:86` | notification content, rendered from `templates/notifications/*.html.j2`, which `rendering.py:33-38` does not autoescape. The templates hold `<span class='fw-bold'>` and `<a href>`, and interpolate the view display name | Unsafe, by code reading |
| `Views/Widgets/PytestWidget/PytestResultRow.svelte:108`, `TestRun/Pytest/PytestItem.svelte:88` | a pytest user field that starts with `<a`, submitted by the reporter | Unsafe by design, from an authenticated client |
| `TestRun/Jenkins/ParameterEditor.svelte:98`, `TestRun/Jenkins/SCTParameterWizard.svelte:713` | Jenkins job parameter descriptions, HTML that Jenkins renders as HTML | Jenkins admins write them |
| `TestRun/Jenkins/CloneTargetSelector.svelte:234`, `WorkArea/JobConfigureModal.svelte:175` | the message of `POST /jenkins/clone/settings/validate`. On a 404 from GitHub, `_verify_sct_settings` (`jenkins_service.py:265-266`) returns an `<a href>` built from the branch the user typed | Unsafe, reflected to the user who typed it |
| `TestRun/Sirenada/SirenadaTestBreakdown.svelte:196,204` | `hljs.highlight(...).value` | Safe: highlight.js escapes its input |

None of them renders markdown, and each of the unsafe ones needs real HTML: a
link or a bold span that the server or the client wrote. Section `Approaches`
gives the fix for each.

One more sink is outside the `{@html}` grep. `TestRun/ResultsGraph.svelte:249`
builds a chart tooltip as a string from `raw.ori` and `raw.changes` of the
submitted results and assigns it to `innerHTML`. Section `Approaches` gives
its fix with the others.

## Approaches

**A. Two shared helpers that sanitize.** *Selected.*
Two modules in `frontend/Common/`, each exporting a function that returns a
string `{@html}` may render:

```ts
// frontend/Common/safeHtml.ts
export const sanitizeHtml = (html: string | null | undefined): string
// frontend/Common/markdown.ts
export const renderMarkdown = (text: string, options?: { mentions?: boolean }): string
```

They are two modules, not one, because `MarkdownUserMention` imports
`argus.js`, which reads the page global `gArgusCurrentUser` when it loads. In
one module, every `sanitizeHtml` caller would load it too, and a test that
renders `ParameterEditor` without that global
(`frontend/TestRun/Jenkins/JenkinsParamsFetch.test.ts`) fails on import.

`sanitizeHtml` sanitizes `html ?? ""` with a DOMPurify instance of its own,
`DOMPurify(window)`, in the default config plus `ADD_ATTR: ["target"]`. An
`afterSanitizeAttributes` hook on that instance sets `rel="noopener noreferrer"`
on every element that has a `target`. The hook lives on the dedicated
instance, so the global `DOMPurify` that `Chat/markdown.ts` uses is unchanged.
`renderMarkdown`
parses with a module-level `new Marked({ gfm: true, breaks: true, async: false })`,
or with a second instance that also carries `MarkdownUserMention` when
`mentions` is true, and returns `sanitizeHtml` of the result. Both use
DOMPurify's default config, the config `TeamDetail` uses today. Every markdown site calls
it: the five `{@html}` sites with `mentions: true`, which is what they render
today on a page where a comment mounted first, and `TeamDetail` and the two
issue templates without. The three `marked.use(...)` calls go, so the global
instance no longer changes on mount. `markdownOptions.js` loses its last
user and goes. `Chat/markdown.ts` keeps its own stricter helper.
Cost: two files of about 15 lines, one line at each site, seventeen files. Risk: a
markdown feature that DOMPurify drops, covered by the benign case of the
test; `<input>` of a task list, tables, code and `https` links survive the
default config, checked in the same probe.

Each non-markdown site takes one of two fixes: render text without `{@html}`,
or keep `{@html}` and pass the string through `sanitizeHtml`. Text keeps the
same look only where the string holds no markup, and none of the nine does:

| Site | Fix | Reason |
|---|---|---|
| `ActivityTab.svelte:70` | `sanitizeHtml` | The performance regression event links to the compared runs with `<a href>`; text would show the tag |
| `Notification.svelte:86` | `sanitizeHtml` | Every template holds `<span class='fw-bold'>` and an `<a href>`; the client gets only the rendered string, not the parameters to rebuild it in Svelte |
| `PytestResultRow.svelte:108`, `PytestItem.svelte:88` | `sanitizeHtml` | The branch exists to render the reporter's `<a>` as a link; rebuilding the anchor in Svelte would mean parsing the HTML and checking the URL, which is the sanitizer's job |
| `ParameterEditor.svelte:98`, `SCTParameterWizard.svelte:713` | `sanitizeHtml` | Jenkins descriptions are HTML by design, with links and line breaks |
| `CloneTargetSelector.svelte:234`, `JobConfigureModal.svelte:175` | `sanitizeHtml` | The 404 message links to the target repository with `<a href>` |
| `ResultsGraph.svelte:249` (`innerHTML`) | `sanitizeHtml` | The tooltip is markup built in the script: a coloured `<span style>`, the title and change lines, and an "Open" link with `target="_blank"` to the run. Only the assignment and the import change; ARGUS-274 moves the tooltip host in the same file |

The default config was a question at review and stays: it keeps `style`
attributes and `<form>`, which run no script. The one addition is `target`, so
a Jenkins description link or the tooltip's "Open" link still opens a new tab;
the forced `rel` keeps the new tab from reaching `window.opener`.

**B. Drop unsafe link URLs inside `marked`.** A `walkTokens` hook or a link
renderer would allow `http`, `https`, `mailto` and relative URLs. It does not
cover raw HTML, so the `onerror` of a highlight comment still runs, and it
re-implements URL parsing that a sanitizer already does against the decoded
attribute. Rejected.

**C. Fix it on the backend.** Escape the highlight comments like the other
three, and reject `javascript:` URLs at write time. The rows already stored
keep their payloads, every entry point would need the rule, and the client
would still render whatever the API returns. Rejected as the fix. Escaping the
highlight comments on write stays a candidate for the follow-up, as defence in
depth.

The Sanitizer API (`Element.setHTML`) is not Baseline Widely available:
Chrome and Edge 146, Firefox 148, not Safari. Its fallback would ship
DOMPurify anyway, and two sanitizers with different defaults would render one
comment two ways. `{@html}` needs a string, so the helper serializes the
sanitized result; DOMPurify's string output is its supported mode for this.

## Regression test

Vitest in jsdom.

`frontend/Common/markdown.test.ts`, `../argus` mocked as in
`frontend/WorkArea/TestRuns.test.ts`:

- `drops a javascript: link`: `[x](javascript:alert(1))` renders an `<a>`
  with no `href`, and the output holds no `javascript:`.
- `drops a javascript: link written with an entity`:
  `[x](javascript&#58;alert(1))`, same assertion.
- `strips an event handler from raw HTML`:
  `<img src="x" onerror="alert(1)">` keeps no `onerror`.
- `keeps ordinary markdown`: bold, inline code, a fenced block, an `https`
  link, a table and a task list render as `marked` renders them.
- `renders a mention only when asked`: ` @admin` gives a `user-mention` span
  with `mentions: true` and plain text without.

`frontend/Common/safeHtml.test.ts`:

- `strips script from server HTML`: `<a href="javascript:alert(1)">x</a>`,
  `<img src="x" onerror="alert(1)">` and `<script>alert(1)</script>` lose the
  `href`, the `onerror` and the script.
- `keeps the links and markup the server sends`: the performance regression
  event, a rendered mention notification with its `<span class="fw-bold">`, a
  pytest `<a href="https://...">` field, a Jenkins description with `<br>` and a
  link, and the 404 validation message keep their tags and `href`.
- `strips script from the validation message`: the 404 message built with the
  branch `"><img src=x onerror=alert(1)>` keeps the link and loses `onerror`.
- `keeps target on a link and forces rel`: `target="_blank"` stays, and `rel`
  becomes `noopener noreferrer`, also over a `rel="opener"` the input set.
- `keeps a target without href harmless`: `<a target="_blank" onclick=...>`
  keeps no `href` and no `onclick`, and gets the forced `rel`.
- `keeps the markup and the run link of a results graph tooltip`: the coloured
  span keeps its `style`, the change line its text, and the "Open" link its
  `href`, `class`, `target` and icon.
- `returns an empty string for a missing value`: `undefined` and `null` give
  `""`.

The script cases of both functions fail against a module that returns its
input unsanitized, the code the sites run today.

## Risks

| Risk | Response |
|---|---|
| A stored comment uses markup that DOMPurify removes | The run comments, highlights and action items hold no raw HTML, since the backend escaped it. Highlight comments lose only script, event handlers and the elements DOMPurify forbids |
| `MarkdownUserMention` reads `applicationCurrentUser` from `argus.js`, which reads a page global | The test mocks `../argus`; the pages define the global |
| A site starts or stops rendering mentions | The editor preview gets `mentions: true`, as it renders today once a comment has mounted. The team page registers no extension today and gets none. The issue template previews lose the mention span they get today when the run has a comment; their text is run data, and the span is styling only |
| ARGUS-276 edits the same components for a11y warnings, and ARGUS-274 rewrites `ModalWindow`, a parent of `JobConfigureModal` | The change touches only the import lines, the `marked.use` block and the rendering line of each file, and not `ModalWindow` |
| A `javascript:` link inside an action item's `<label>` loses its `href`, so a click on it toggles the action item's checkbox | Accepted. Seen in the live check; such links do not exist in real data, and the label wraps the whole item, so a click on plain text toggles it too |
| A link keeps `target="_blank"` from the input | `rel="noopener noreferrer"` is forced on every element with a `target` |
| The non-markdown sites cannot all be reached live without side effects | The live check covers the markdown sites and the activity tab; the sanitize cases of the test cover the strings of the other sites |

## Deferred work

- Escape the highlight comments on the backend, as the highlights and action
  items are escaped. `create_comment` and `update_comment` in
  `argus/backend/service/views_widgets/highlights.py` store `payload.content`
  where they already compute `content_stripped`. A follow-up subtask of
  ARGUS-273; its draft text is outside this repository.
