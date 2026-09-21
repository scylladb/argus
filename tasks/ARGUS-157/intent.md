# ARGUS-157 — Filter a view's runs by an SCT config parameter

## Problem

A view shows every run of every test it contains. When the same test runs under
two different configurations, both sets of runs land in the same widget and in
the same statistics, and nothing in Argus tells them apart.

The four `weekly-microbenchmark` tests are the case that raised this. They run
with and without the offline installer. A reader of the view sees one mixed set
of runs and cannot tell which configuration produced a result, so the status of
a single configuration cannot be read off the dashboard at all.

## Who it affects

Whoever reads a view built from SCT tests that run under more than one
configuration. The reporter's case is the `weekly-microbenchmark` tests and the
offline installer. The general case is any SCT test whose behaviour depends on
a config parameter.

## Evidence

From the Jira issue:

> Create an Argus view that only includes runs with a specific parameter value
> instead of showing all runs.

> There are 4 weekly-microbenchmark tests. They may run with or without the
> offline installer.

> The view should allow filtering runs by an SCT config parameter.
> The filter should be able to select runs with a specific parameter value.
> The view should show the runs with the offline installer in a separate view.
> For this case, the runs can be filtered when the unified_package test
> parameter is not empty.

Argus already stores the flattened SCT config of every run that submits one, in
`run_config_param`, keyed so that "which runs have this parameter at this
value" is a single-partition read. Nothing reads it for this purpose today, and
no endpoint exposes it.

## What good looks like

A view can carry two Test Dashboard widgets side by side: one showing only the
runs whose `unified_package` parameter is set, the other the rest. Each widget's
tests, statuses and counts reflect only its own runs.

Whoever configures the view picks the parameter and its value by searching, and
does not have to know the exact parameter name or type it out. Whoever reads the
dashboard can see which parameters the widget is narrowed by.

## Out of scope

- The release dashboard. This is a view-level knob.
- Widgets other than the Test Dashboard.
- Operators beyond "equals this value" and "is set to some non-empty value":
  no regex, no negation, no numeric comparison.
- A stored, per-reader filter preference.
