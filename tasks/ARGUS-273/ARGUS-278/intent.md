# ARGUS-278 — Rendered markdown runs script from user text

## Problem

Argus renders the markdown that users write with `marked` and puts the HTML
into the page through Svelte's `{@html}`, with no sanitizer between them.
`marked` keeps every link URL as written, so a link such as
`[x](javascript:alert(1))` becomes `<a href="javascript:alert(1)">`. Any user
who clicks it runs the author's script in their own Argus session, with their
cookies and their rights.

The backend escapes `<` and `>` in run comments, view highlights and action
items, so raw HTML does not reach these pages, but a link with a `javascript:`
URL needs neither character. The comments on a view highlight are not escaped
at all, so raw HTML in such a comment runs as soon as the comments are
expanded, with no click.

The message of the day of a team is the one site that sanitizes today.

## Who it affects

- Every signed-in user who reads a run discussion, a view highlight, a view
  action item or a highlight comment, and clicks a link in it.
- Every user who expands the comments of a view highlight that carries raw
  HTML.
- The author of a comment, who sees the same HTML in the preview tab of the
  comment editor.

## Evidence

Jira issue ARGUS-278:

```
These components render user markdown with marked.parse straight into {@html}, with no sanitizer:
frontend/Discussion/Comment.svelte:145
frontend/Discussion/CommentEditor.svelte:335
frontend/Views/Widgets/ViewHighlights/HighlightItem.svelte:82
frontend/Views/Widgets/ViewHighlights/ActionItem.svelte:92
frontend/Views/Widgets/ViewHighlights/Comment.svelte:73
The backend escapes only < and > (strip_html_tags in argus/backend/util/common.py). marked does not filter link URLs. A markdown link such as [x](javascript:...) can possibly run script for each user who clicks it. Nobody has tested this.
frontend/Teams/TeamDetail.svelte:192 already sanitizes with DOMPurify.sanitize(parse(...)).
```

Reproduced on 2026-11-19 against the dev database, marked 16.1.2, headless
Chrome 157. A run comment, a view highlight, an action item and a highlight
comment each held `[jslink-<site>](javascript:alert('<site>-js'))`. A mouse
click on each link opened the alert:

```
mouse click jslink-run: EXECUTED ["run-js"]
mouse click jslink-hl: EXECUTED ["hl-js"]
mouse click jslink-hc: EXECUTED ["hc-js"]
mouse click jslink-ai: EXECUTED ["ai-js"]
```

The highlight comment also held `<img src="x" onerror="alert('hc-img-onload')">`.
Expanding the comments ran it with no click:

```
DIALOG: alert "hc-img-onload"
live <img src=x> elements: ["<img src=\"x\" onerror=\"alert('hc-img-onload')\">"]
```

`rca.md` holds the full record.

## What good looks like

- A `javascript:` link, or any other script URL, in a run comment, a view
  highlight, an action item or a highlight comment renders without the URL,
  and a click runs nothing.
- Raw HTML in a highlight comment renders without its event handlers and
  without script.
- Ordinary markdown renders as today: bold, code, tables, task lists, links to
  `http` and `https` addresses, and the `@user` mentions.
- One shared helper does the parse and the sanitize, and a test covers it.

## Out of scope

- The Sanitizer API. It is not Baseline Widely available, so DOMPurify stays.
- The chat answers. `frontend/Chat/markdown.ts` already sanitizes them with a
  stricter config.
- The `{@html}` sites that render no markdown: the run activity events, the
  notification content, the pytest user fields, the Jenkins parameter
  descriptions and the Jenkins validation messages. `rca.md` lists them for a
  follow-up issue.
- Escaping the highlight comments on the backend. The client sanitizer closes
  the hole for every reader.
- Rewriting the comments already stored.
