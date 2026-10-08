# ARGUS-81 — Rework the workspace sidebar

## Problem

The workspace sidebar on `/workspace` is how people find a test and open its
runs. It is three nested accordions (release, group, test), and each level has
its own filter box that only searches that level. That causes these problems:

- **Finding a test is slow.** You have to know which release and group a test
  lives in, open both, and filter each one separately. No single place lets you
  find a release, a group or a test by name.
- **The release order hides the important releases.** Releases sort by plain
  name. `scylla-master` comes 59th of 83, behind every `enterprise-*`,
  `manager-*` and `operator-*` release. Version numbers sort as text, so
  `manager-3.10` comes before `manager-3.2`.
- **Test order goes stale.** Tests sort by status only when the group first
  loads its tests. Stats that arrive later, and the *Update Stats* button, never
  re-sort the list.
- **Stats are slow and sometimes stuck.**
  - Opening a release downloads its full stats document, even though the
    sidebar uses only a few counts from it.
  - *Update Stats* returns the stored snapshot instead of new stats.
  - A failed stats request leaves every group row spinning forever.
  - Collapsing and reopening a group downloads its tests again.
- **Some rows are wrong or ambiguous.**
  - A test that never ran shows the date `1970-01-01 01:00`.
  - Two groups can share a display name, and nothing tells them apart.
  - The bar indicator does not show what needs attention.
- **The filters crash.** Each filter box treats its input as a regular
  expression, so typing a character such as `(` throws.
- **Small screens and keyboards are left out.**
  - The sidebar has a fixed height of 960px, taller than most viewports.
  - Below 768px it is hidden, so you cannot browse on a phone.
  - On a phone the page also scrolls sideways.
  - Test rows respond to the mouse only, and the sidebar has no keyboard
    navigation.
- **The other search box is slow and limited.** The runs panel has a search box
  that reads every release, group and test row on each query and returns every
  match, with no limit on the number of results.
  - Its query syntax drops the quotes it asks for, so a `release:"..."` facet
    never matches.
  - A facet value cannot contain `/`, and many release names do.
  - Several words must appear together, in order, to match.

## Who it affects

Engineers who use the workspace to triage test results. They open the
workspace to find a test in a release, check its status, and open its runs.
Admins who manage releases have no way to keep the main releases at the top.

## Evidence

Jira ARGUS-81:

> Rework the sidebar UX and improve its visual design / responsiveness.
>
> Migrated from GitHub issue: https://github.com/scylladb/argus/issues/887

Measured on a local instance with 83 releases and about 41.7k tests:

- `GET /api/v1/releases` returns releases in name order. `scylla-master` is
  entry 59.
- The stats for `scylla-master` with no runs at all:

  ```
  limited=0 1714476 bytes 0.020839s
  ```

- Every test with no runs carries the epoch as its start time, and the sidebar
  renders it:

  ```
  [('str:1970-01-01T0', 1875)]
  longevity-50gb-3days-test 1970-01-01 01:00
  ```

- The `scylla-master` group list shows `Cluster - Core QA Longevities` twice.
- Panel search timings:

  ```
  search 492490 bytes 0.816789s        (query=longevity-50gb)
  59612043 bytes 1.207926s              (query=-)
  ```

- At a 390px wide viewport the sidebar computes `display: none` and the page
  scroll width is 402.
- `frontend/WorkArea/WorkArea.svelte`:

  ```
  return !RegExp(filterString).test(name);
  ```

- `frontend/WorkArea/WorkArea.svelte`:

  ```
  #run-sidebar {
      height: 960px;
      overflow-y: scroll;
  }
  ```

## What good looks like

- One search box finds a release, a group, a test or a run by name, by job
  path, or by facet, and takes you to it. Typing any character does not break
  it. Results come back fast and in a sensible order.
- The sidebar shows one level at a time, with breadcrumbs back up.
- Releases that admins mark as important, such as `scylla-master` and
  `scylla-staging`, sit at the top. Other releases list newest version first.
- Test order follows status whenever stats arrive or are refreshed.
- Stats load only when needed, never spin forever, and *Refresh* returns fresh
  numbers.
- The status indicator shows failures, runs in progress, passes and pending
  investigations at a glance.
- Tests that never ran show no date. Groups that share a name can be told
  apart.
- The sidebar works with the keyboard alone.
- On a phone, a button at the bottom left opens the sidebar as a drawer, and
  the page does not scroll sideways.

## Out of scope

- The runs panel itself: the run list, run details and the share link.
- The release dashboard and its stats widgets.
- Shared caching or search infrastructure across workers, such as an external
  cache or a search service.
- The release grid picker, which is reached from the panel search box.
