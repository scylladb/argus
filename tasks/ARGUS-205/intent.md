# ARGUS-205 — Show the cost of a test run

## Problem

A test run page shows what a run did and what it produced. It does not show
what the run cost. The producer knows the cloud spend of a run (SCT computes
it from its instance catalog and the run duration), but Argus has no place to
store that number and no way to display it.

The figure exists elsewhere: cloud-monitor sends a cost report by email, and
DoIT has a report. In practice nobody reads either against a specific run, so
an oversized cluster or a wasteful configuration goes unnoticed until someone
audits the bill. Engineers need to see the cost of their own runs where they
already look, so that they weigh it when they rerun a test. Storing the figure
per run also lets Argus later show it per team and per release.

## Who it affects

- Engineers who open a run page and want to know what the run cost, and
  whether the actual figure matched the estimate.
- SCT, the first producer. It has the estimate before the run starts and the
  actual figure once the run finishes, per node and for the run.
- Other test sources (dtest, driver-matrix, generic runs). None plans to
  report cost soon. The store lives in its own table so that the SCT run
  model stays lean and a later producer needs no migration.
- The future cost dashboard, [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218).
  It needs stored per-run figures to aggregate. It is not built here.

## Evidence

The questions the reviewers of
[scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071) and
[scylladb/argus#1087](https://github.com/scylladb/argus/pull/1087) settled, with
the answer that closed each one.

**What does the first version show?**

> so, from my understanding, this intent is to have 2 things:
> 1. in each run to see the estimate and the actual cost
> 2. having a dashboard that enables filtering/aggregation [...]

> We should see this data in Argus UI in the first version. Maybe we don't
> need details like per category, but at least 'estimated' and 'actual' cost
> should be there.

**Who needs it?**

> Would amend that users need visibility of their run costs, so they would
> take it more into account when reruning tests
>
> Saving this data later would enable us to have visibility on a team or a
> release level

**Does cost belong on the SCT run model?**

> Cost is not only for SCTTestRun, can happen to any test (Dtest, driver
> matrix) or any other future kind of test we'll add to Argus.

> Yes, but there are no upcoming plans to introduce it in any of those types
> any time soon. [...] For the sake of not beefing the SCT model, it might
> make more sense to me

**Which currency?**

> I propose using USD, in case we face another currency, we'll be converting
> to USD

**Is a per-instance breakdown wanted?**

> No, I think the general cost is good enough, no need for individual
> breakdowns.

**Are cost items with a category in scope?**

> I think this is in the scope. Let's allow posting name of the cost,
> category, estimated cost and actual cost, also 'pricing_tier' - and
> anything we might want in the dashboard in the future we can't collect
> from other tables in Argus.

**Is live cost during a run wanted?**

> I don't see a reason for live cost, it can show just the upfront estimation
> until job is done.

**Is a partial flag on the actual figure wanted?**

> I'm o.k. with skipping this,
>
> we didn't fully defined this, if some instances doesn't have a price ? we
> didn't had the spot price ?

**Is leaked cost in scope?**

> I think the goal of this is API for reporting cost information and storing
> it.
>
> Leaking resources/cost report is something the can be built on top of it
> with its own goals and definition.

## What good looks like

- A producer reports an estimated cost for a run and later an actual cost,
  through the Python client. Both are USD amounts the producer computed.
  Argus stores them as sent and computes no price.
- A producer may also report named cost items for the run, each with a
  category, an optional pricing tier, and an estimated or actual figure.
  Argus defines no category vocabulary.
- The run page has a Costs tab. It shows the run's estimate and actual
  figure, and the items when there are any. It says that no cost was reported
  when there is none. An unknown figure never shows as zero.
- Cost lives in its own tables keyed by the run's `build_id` and
  `build_number`. No plugin run model, UDT or index changes.
- A producer that reports no cost behaves exactly as today.
- The stored figures are what ARGUS-218 will aggregate later.

## Out of scope

- Leaked cost and the periodic cleanup scripts as a producer. Agreed in the
  review of #1087: leak reporting is built on top of this API with its own
  definition.
- A partial or incomplete flag on the actual figure. Agreed in the review of
  #1087: what an unpriced instance or a missing spot price means is not yet
  defined.
- Live cost during a run. The estimate stands until the actual arrives.
- Any aggregation, filtering or dashboard across runs (ARGUS-218).
- Any pricing computation, catalog or currency conversion in Argus.
- A Go CLI command for dtest and driver-matrix. The Python client is the
  interface; a CLI command is a follow-up issue.
- Network or storage cost as separate figures. A producer includes them in
  the total, or reports them as items, if it computes them.
- Backfilling cost for runs that finished before this change.
