# ARGUS-256 — Pages break or run injected script when template data reaches JavaScript

## Problem

Several pages hand server data to their JavaScript through the Jinja2
templates, and the data does not reach the script intact.

The release dashboard fails to load with a JSON syntax error when the data
for the release holds certain characters. The release scheduler, the duty
planner, the standalone test runs page and the profile schedules page embed
their data the same way.

The run view and the admin panel copy a URL path segment into a script
unchanged. Someone can craft a link to an existing run or to an admin page
whose path segment closes the string and runs their script in the browser of
whoever opens it.

## Who it affects

- Every user who opens the release dashboard, scheduler or duty planner of
  a release whose release, group or test data holds a double quote, a
  newline or a backslash, such as a version regex like `^\d+\.\d+$`.
- Users of the standalone test runs page and the profile schedules page
  when their data holds the same characters.
- Any logged-in user who follows a crafted run view link, and any admin who
  follows a crafted admin panel link.

## Evidence

Jira issue ARGUS-256:

```
Some Argus templates render broken javascript due to incorrectly inserting JSON as a javascript object:scylla-master:1 Uncaught SyntaxError: Expected ',' or '}' after property value in JSON at position 31863 (line 1 column 31864)
    at JSON.parse (<anonymous>)
    at scylla-master:63:30
Affects release_dashboard.html.j2, but worth checking out other templates as well.
```

Reproduced with the Argus Jinja environment and Node. The release dashboard
script, with a description of `say "hi"` followed by a newline:

```
old: Expected ',' or '}' after property value in JSON at position 22 (line 1 column 23)
```

The run view script, rendered for the tab `x";console.log("INJECTED");"`:

```
const gTab = "x";console.log("INJECTED");""; console.log("tab:", gTab);
INJECTED
tab: x
```

## What good looks like

- The release dashboard, scheduler and duty planner load for a release whose
  data holds double quotes, newlines, backslashes and `</script>`. The page
  shows those values exactly as stored.
- The standalone test runs page and the profile schedules page load with
  the same characters in their data.
- A run view or admin panel URL whose path segment holds a quote cannot run
  script. The page gets the segment as plain text.

## Out of scope

- Escaping values in HTML outside a `<script>` block, such as page titles.
- Turning on autoescaping for the `.j2` templates.
- Script values that can only be a UUID or that come from server
  configuration.
- Email and notification templates.
