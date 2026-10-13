# ARGUS-256 — Pages break or run injected script when template data reaches JavaScript

**Date**: 2026-10-13

## Root cause

Two template patterns put a value into a `<script>` block in a form the
browser reads differently from the value the server meant.

**JSON inside a JS string.** Five templates write their data as
`JSON.parse('{{ x | tojson | safe }}')`:

- `templates/release_dashboard.html.j2:10`
- `templates/release_schedule.html.j2:10`
- `templates/duty_planner.html.j2:10`
- `templates/standalone_test_with_runs.html.j2:11`
- `templates/profile_schedules.html.j2:9`

`tojson` emits valid JSON. The quotes around it turn that JSON into the source
text of a JS string literal, and the JS parser applies the backslash escapes
before `JSON.parse` sees the text. JSON's `\"` becomes a bare `"`, `\n` becomes
a raw newline, and `\\` becomes a single `\`. A release, group or test field
that holds one of those characters, such as a `valid_version_regex` of
`^\d+\.\d+$`, hands `JSON.parse` broken JSON. The release routes in
`argus/backend/controller/main.py` (`release_dashboard` at line 154, and the
scheduler and duty planner routes after it) pass every release, group and test
`model_dump()` into `data`. One such field anywhere stops the page. The same
data rendered through the Argus environment and run in Node gives the error
from the ticket:

```
old: Expected ',' or '}' after property value in JSON at position 22 (line 1 column 23)
```

Commits bb045bff (`base.html.j2`) and f8a35593 (ARGUS-124,
`release_planner.html.j2`) fixed the same pattern in two other templates. They
write the `tojson` output as a JS literal. These five were left as they were.

**A path segment inside a JS string, unescaped.** `rendering.py:33`
`_autoescape` escapes only bare markup extensions, so no `.j2` template is
escaped. Two templates copy a URL path segment between double quotes:

- `templates/run_view_by_plugin.html.j2:12`: `const gTab = "{{ tab }}";`.
  `tab` is the free `{tab}` segment of `/tests/{plugin_name}/{run_id}/{tab}`
  (`main.py:68`) and `/test/{build_id}/{build_number}/{tab}` (`main.py:84`).
- `templates/admin/index.html.j2:5`: `const gCurrentRoute = "{{ current_route }}";`.
  `current_route` is the `{path}` segment of `/admin/{path}` (`admin.py:18`).

Starlette percent-decodes the path before it matches, so `%22` reaches the
template as `"`. Rendered for the tab `x";console.log("INJECTED");"`:

```
const gTab = "x";console.log("INJECTED");""; console.log("tab:", gTab);
INJECTED
tab: x
```

The segment cannot hold `/`, so it cannot close the `<script>` tag. Breaking
out of the string is enough to run code. The other quoted script values
(`gTestId`, `test_run_id`, the login constants) are UUIDs typed by FastAPI or
server configuration, and none of them can hold a quote.

## Approaches

**A. Keep `JSON.parse`, encode the JSON a second time as a JS string.**
Write `JSON.parse({{ x | tojson | tojson }})`: the outer `tojson` makes a
valid, HTML-safe JS string whose content is the JSON text. Cost: the payload
grows with a second layer of escapes, and the templates end up with two ways of
doing the same job. The one gain is V8's faster `JSON.parse` on large
payloads, which a dashboard-sized object does not need. It does not cover
`gTab` or `gCurrentRoute`, which still need `tojson`. Rejected.

**B. Write every script value as a `tojson` literal.** *Selected.*
`JSON.parse('{{ x | tojson | safe }}')` becomes `{{ x | tojson }}`, and
`"{{ tab }}"` and `"{{ current_route }}"` become `{{ tab | tojson }}` and
`{{ current_route | tojson }}`. Valid JSON is a valid JS expression, and
Jinja's `tojson` escapes `<`, `>`, `&` and `'` as `\u` sequences, so neither a
quote nor `</script>` can end the literal. Seven one-line template changes, no
backend or frontend change: each entry point reads the same global with the
same value. `tojson` returns `Markup`, so the `| safe` after it does nothing
and goes away on the lines this touches. Selected because it is the pattern
bb045bff and f8a35593 already use, and one rule covers both defects.

**C. Turn on autoescaping for the `.j2` templates.** It would HTML-escape
`{{ tab }}` and stop the injection. In a script it would give the frontend
`&#34;` in place of `"`, so the value would be wrong. It leaves the
`JSON.parse` defect as it is, because `tojson` returns `Markup` and autoescape
skips it. It also changes every template, the email bodies included, and each
intentional raw-HTML output would need a `| safe`. Rejected as too broad for
this bug. The intent places HTML-context escaping out of scope.

## Regression test

Each test reads the right-hand side of `const <name> = …;` from the rendered
page and decodes it with `json.loads`. Valid JSON is a valid JS literal, so a
decoded value equal to the input proves the browser gets the same value. Every
case fails on the current templates: `JSON.parse('…')` and a broken-out string
are not JSON.

- `argus/backend/tests/main_api/test_page_script_data.py`
  - `test_release_page_embeds_release_data_intact`, parametrized over
    `/dashboard/{name}`, `/release/{name}/scheduler` and
    `/release/{name}/duty`. A release created and edited through the admin API
    with a `description` of `say "hi"`, a newline and `</script>`, and a
    `valid_version_regex` of `^\d+\.\d+$`. Both come back unchanged in
    `releaseData["release"]`.
  - `test_runs_page_embeds_additional_runs_intact`: `/test/{id}/runs` with an
    `additionalRuns[]` value holding a quote and a backslash.
  - `test_admin_page_keeps_route_inside_its_string`:
    `/admin/x%22%3Balert(1)%3B%22` decodes to `x";alert(1);"` in
    `gCurrentRoute`.
- `argus/backend/tests/main_api/test_run_view.py`
  - `test_run_view_keeps_tab_inside_its_string`: the same injected segment as
    the tab of `/tests/scylla-cluster-tests/{run_id}/…` decodes to itself in
    `gTab`.

`profile_schedules.html.j2` gets the same one-line change with no test of its
own. Seeding a schedule with a quoted field would test the same mechanism a
fourth time.

## Risks

| Risk | Response |
|---|---|
| Another template still puts data into a script the old way | A search of `templates/` for `JSON.parse('{{` and for quoted `{{ … }}` inside `<script>` gave the list above. Every remaining quoted value is a UUID or comes from configuration |
| An entry point relied on getting a string, not an object | `JSON.parse` already returned the object, so the literal gives each entry point the same value. `gTab` and `gCurrentRoute` stay strings |
| A literal is slower to parse than `JSON.parse` on a large release | `base.html.j2` and `release_planner.html.j2` already embed literals of this size. A dashboard payload is tens of kilobytes |
| A value that `json.dumps` cannot encode now fails the render | Nothing changes: `tojson` and its `ArgusJSONProvider.default` already encode the same values today |
