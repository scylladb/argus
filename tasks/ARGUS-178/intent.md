# ARGUS-178 — Jira issue priority, Space and status filters

## Problem

Argus keeps a copy of every Jira issue linked to a run, but not its
priority. The issue widget on the run page, the release dashboard and the
view widget cannot show which linked issue is a P0. It cannot order the issues
by priority, and it cannot filter them by priority either.

The widget cannot narrow the list to one Jira Space (project). It also cannot
narrow it to a status. It has two switches, Open and Closed, which fit GitHub
issues only. The Jira statuses have no control, and an issue in a Jira status
that the widget does not list in advance never appears. A `To Do` issue is
stored as `to do`, which is not in that list, so it is always hidden.

The "All Labels" panel of the widget opens empty. A label can only be picked
by clicking it on an issue card.

A Jira label has no color of its own, so Argus derives one from a hash of its
name. About a quarter of the derived colors are grey, and labels of one scope,
such as `backport/2025.1` and `backport/6.2-done`, get unrelated colors. A
label chip picks its text color by a brightness rule, which leaves the text of
some chips below a 4.5:1 contrast ratio. This applies to GitHub labels too.

An issue card does not link to the page that lists the runs linked to that
issue, `/issues/<KEY>`. The page is reachable only by typing its address.

## Who it affects

Engineers who triage test failures in Argus: on the issue tab of a run, the
issues of a release dashboard and the issue view widget.

## Evidence

The Jira issue:

> Currently there are several instances where Jira implementation for Argus is lacking:
> Missing Priority field support (Blocker/P1/P2/P3/) and filtering (checkbox-based)
> Missing Jira Spaces filter (checkbox-based)
> Also, both github and Jira issues would benefit from checkbox-based filter for statuses (Open/Closed/New/Todo)

The priority Jira returns for ARGUS-178 itself:

```
"priority": {
  "iconUrl": "https://jira-prod-eu-101-4.prod.atl-paas.net/images/icons/priorities/low.svg",
  "id": "4",
  "name": "P3",
  ...
}
```

The priorities in use, in Jira's order, are `Release Blocker`, `P0`, `P1`,
`P2`, `P3` and `P4`.

The status filter of the widget, `frontend/Github/Issues.svelte`:

```
const stateFilter: Record<State, boolean> = $state({
    open: true,
    closed: true,
    "in progress": true,
    ...
    todo: true,
    new: true,
});
...
if (!stateFilter[issue.state]) return true;
```

The label list of the "All Labels" panel, in the same file:

```
let availableLabels: Label[] = [];
```

The color of a Jira label, `frontend/Common/IssueTypes.ts`, and its text color,
`frontend/Jira/JiraIssue.svelte`:

```
const START_COLOR = [255, 238, 0];
const END_COLOR = [0, 32, 255];
const factor = (parseInt(sha1(label.name).slice(0, 16), 16) % 10000) / 10000;
```

```
style="color: {Color(`${label2color(label)}`).isDark() ? 'white' : 'black'}; background-color: {label2color(label)};"
```

## What good looks like

- Each Jira issue card shows the priority of the issue, and the priority stays
  current as Jira changes it.
- Issues linked before this change show their priority too.
- The widget filters the issues by status, by priority and by Jira Space with
  checkboxes. Every status present in the list has a checkbox, for GitHub and
  Jira alike.
- The widget sorts the issues by priority.
- The "All Labels" panel lists the labels of the issues shown, and picking one
  filters the list.
- Jira labels of one scope share a color family, and the text of every label
  chip stays readable.
- A Jira issue card outside `/issues/<KEY>` links to that page.

## Out of scope

- Priority for GitHub issues, which have none.
- Showing the priority anywhere other than the issue cards, such as the
  compact issue badges, the graphed stats or the Go CLI.
- Filtering on the server.
