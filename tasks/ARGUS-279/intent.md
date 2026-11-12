# ARGUS-279 — Screenshots tab hides the part of the screenshot we read

## Problem

Since PR #1141 (ARGUS-260, merged 2026-11-02), the Screenshots tab of a test
run shows the part of a screenshot that nobody reads:

- Each thumbnail shows the centre of the screenshot. The top, where the SCT
  monitor screenshots hold the CPU and requests panels, is cut off.
- The viewer opens a screenshot shrunk to fit the window. The text and the
  graph values of a monitor screenshot cannot be read at that size, so every
  screenshot needs an extra key press or click before it is useful.

## Who it affects

Engineers who triage SCT runs on the Screenshots tab of a test run. Other
plugins that submit screenshots get the same layout.

## Evidence

- Run: https://argus.scylladb.com/tests/scylla-cluster-tests/05bc3b69-fb17-4002-ab4d-5a5f7c88d017/screenshots
- Jira: https://scylladb.atlassian.net/browse/ARGUS-279
- PR #1141: https://github.com/scylladb/argus/pull/1141, commits `fb2ac5ed`
  (`fix(frontend): make the screenshot grid fit a narrow window`) and
  `62557420` (`fix(frontend): fit the screenshot viewer and add zoom, pan and keys`).
- Before `fb2ac5ed`, the thumbnail was:

  ```css
  .screenshot-thumb { width: 384px; height: 384px; background-size: cover; background-repeat: no-repeat; }
  ```

  in a `d-flex p-2 align-items-center justify-content-center` holder. After it:

  ```html
  <div class="row row-cols-2 row-cols-md-3 row-cols-lg-4 row-cols-xxl-5 g-2 p-2">
  ...
  <img class="object-fit-cover w-100 h-100" ...>
  ```

## What good looks like

- A thumbnail shows the top of its screenshot, with the CPU and requests
  panels in view.
- The viewer opens a screenshot at its natural size, from the top. Fit to
  window, zoom, pan and the previous and next controls still work.

## Out of scope

- The fixed 384px thumbnail size and the centred grid. The responsive grid
  from #1141 stays as it is.
- The zoom, pan, keyboard and swipe features of the viewer.
- Any backend or screenshot proxy change.
