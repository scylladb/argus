# ARGUS-218 — Cost Explorer: track cloud spend across releases, groups and tests

## Problem

A run page shows what one run cost. Nothing answers the questions that drive
spending decisions: which releases, groups and tests consume the budget,
whether spend trends up or down, how much goes to failed runs, how much goes
to resources that outlived their run, and how much of the total is actually
known.

The per-run figures exist since ARGUS-205. They live in a table keyed by the
run identifier alone. It carries no release, group, test, time or backend, so
any question across runs means reading every run's partition and joining it
to the run row. There is no place to read "spend for release 2026.1 over the
last 90 days", and no page to show it.

A cost item can arrive after the run has ended: the job's cleanup stage
reports the resources it terminates, and the scheduled cloud sweep reports
the instances a run leaked. Any cross-run figure has to absorb those late
items or it quietly under-reports.

A spot instance that the cloud reclaims ends the run early. SCT publishes a
`SpotTerminationEvent` for it like any other event, so nobody can count how
many spot runs were reclaimed, how often, or what they cost.

## Who it affects

- Engineers and team leads who want to see what their tests, groups and
  releases cost, so that they can weigh a rerun, a cluster size or a spot
  policy against the figure.
- Release and QA management, who need spend per release and its trend.
- SCT, the only producer today. It sends an estimate before provisioning, a
  cost item per node when it terminates, and items from cleanup and from the
  leaked-resource sweep. It computes every price; Argus stores and sums.
- The view dashboards. A team's view already names its releases, groups and
  tests, so its cost belongs beside its other widgets.
- The future budget and alerting work in epic SCT-851, which should read the
  figures this task stores rather than compute its own.

## Evidence

From the Jira issue:

> Follow-up to ARGUS-205, which makes a single run's cost visible. That
> answers "what did this run cost?" but not the questions that actually drive
> spending decisions: which releases, groups and tests are eating the budget,
> whether spend is trending up, and how much is being burned on failed or
> leaked resources.

> There is no way to answer "spend for release 2026.1 over 90 days" without
> either scanning every run's resource partition or storing the number.

> Backfill is not possible for runs predating ARGUS-205, and there is no
> point pretending otherwise - the page should show the data horizon
> explicitly.

> Cost data coverage - complete / partial / no data. Without this the totals
> are quietly wrong; with it they are an honest floor.

> Store a spot-termination marker on `SCTTestRun` (for example
> `spot_terminated`). Set it when the run receives a `SpotTerminationEvent`.

The data model the issue describes is the one ARGUS-205 proposed, not the one
it landed. `tasks/ARGUS-205/spec.md` records what exists:

> One table. The partition is the run, the static columns hold the run's
> totals once, and each clustered row is one item. [...] No timestamps and no
> build identifiers: a dashboard that needs `build_id` gets it from its own
> table.

> The dashboard in ARGUS-218 aggregates `estimated_cost` and `actual_cost`
> and filters on `category`, `pricing_tier` and `leaked`, from a table of its
> own; this table stays the per-run source.

There is no cost column on `sct_resource`, no `is_spot` flag and no
instance-hours figure. An item carries a name, a category, a cost, a pricing
tier and a leaked flag.

The producer side, `sdcm/utils/cost_reporting.py` in scylla-cluster-tests:

> Keys and values stay within lowercase letters, digits, `_` and `-`, so the
> same pair is a valid AWS tag, GCE label, Azure tag and OCI defined tag.

> `leaked` is for the scheduled cloud sweep, which only reaches what a test
> failed to clean up; a job's own cleanup stage is the normal end of a run's
> resources and reports them as not leaked.

The mockup linked from the issue shows the panels: a filter bar (range,
release, group, view, backend, lifecycle, week/day/month granularity), four
stat tiles (spend in range with trend, weekly run rate, spent on failed runs,
leaked past teardown), spend over time by backend, top tests, most expensive
runs, cost data coverage, and spot versus on-demand.

## What good looks like

- A `Costs` entry in the navigation bar opens one page that shows, for a
  chosen time range, the spend per release, broken down by group or by test,
  with group as the default.
- The page charts spend over time at day, week or month granularity, lists
  the most expensive runs with a link to each run, and splits spend by
  pricing tier.
- Every figure on the page says how much of it is known: how many runs in
  range have complete cost data, partial data, or none. No total is presented
  as complete when it is not, and the page states the date before which no
  cost data exists.
- A cost item that arrives after the run ended, leaked or not, shows up in
  the figures without any manual step.
- The page counts the spot runs a reclaim stopped, their share of all spot
  runs and their spend, by backend and region.
- Every panel can be restricted to spot or on-demand spend.
- A view dashboard can show its own cost: a widget with the spend and the
  trend for the view's releases, groups and tests, and a link to the page
  filtered the same way.
- Reading the page costs a bounded number of partition reads, independent of
  how many runs exist.
- Runs that reported cost before this change are included once a one-off
  script has run.

## Out of scope

- Any pricing lookup, rate or currency conversion in Argus. The ARGUS-205
  contract holds: the producer computes, Argus stores and sums.
- Instance-hours, and any savings figure derived from them. The producer
  sends a cost per item and no duration, so the mockup's "instance-hours
  against spend" panel has no source.
- Anything but what the producer reports as items: no egress, storage, S3 or
  Kubernetes control-plane cost.
- Budgets, alerting and approval gates (epic SCT-851, phases 3 and 4).
- Changes to what SCT sends. The page shows what arrives today.
- Cost for runs that ended before ARGUS-205 landed. No figure exists for
  them.
- A Go CLI command.
