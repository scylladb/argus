# ARGUS-205 — Show the overall cost of a test run

## Problem

A test run page shows what a run did and what it produced. It does not show
what the run cost. The producer knows the cloud spend of a run (SCT computes
it from its instance catalog and the run duration), but Argus has no place to
store that number and no way to display it. An engineer who wants the figure
opens the cloud-monitor cost site or a DoIT report instead, and in practice
nobody does, so an oversized cluster or a wasteful configuration goes
unnoticed until someone audits the bill.

The first attempt, [scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071),
put cost fields on the SCT `CloudInstanceDetails` UDT and on `SCTTestRun`, and
summed them in the Resources table. Review rejected that shape: cost is not an
SCT concept, a per-instance breakdown is not wanted, the Resources table is
already too wide, and a run-level total that exists only as a read-time sum
cannot be filtered or ranked later. The PR discussion then grew into a
two-table design with categories, item rows, leaked cost and a dashboard.
That is more than the first step needs.

## Who it affects

- Engineers who open a run page and want to know what the run cost.
- SCT, the first producer. It already has the estimate before the run starts
  and the actual figure once the run finishes.
- Every other test source (dtest, driver-matrix, generic runs). The store and
  the API must not depend on the SCT plugin, or a second producer needs a
  migration.
- The future cost dashboard, [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218).
  It needs a stored per-run figure to aggregate. It is not built here.

## Evidence

From the SCT design document behind
[scylla-cluster-tests#15979](https://github.com/scylladb/scylla-cluster-tests/pull/15979):

> Engineers running SCT tests cannot see what a run costs. The data exists
> only on the cloud-monitor cost site, which is awkward to reach and
> effectively nobody checks, so expensive mistakes go unnoticed until someone
> reviews the bill.

> The contract with Argus is that **all cost arithmetic happens in SCT**.
> Argus stores what it is told, sums it for display, and never grows a
> pricing catalog of its own.

From the review of [scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071):

> Cost is not only for SCTTestRun, can happen to any test (Dtest, driver
> matrix) or any other future kind of test we'll add to Argus.

> so, from my understanding, this intent is to have 2 things:
> 1. in each run to see the estimate and the actual cost
> 2. having a dashboard that enables filtering/aggregation [...]

> I propose using USD, in case we face another currency, we'll be converting
> to USD

> No, I think the general cost is good enough, no need for individual
> breakdowns.

> I don't see a reason for live cost, it can show just the upfront estimation
> until job is done.

## What good looks like

- A producer reports an estimated cost for a run, and later an actual cost,
  through the Python client with two calls. Both are USD amounts the
  producer computed. Argus stores them as sent and does no arithmetic.
- The run page has a Costs tab. It shows the estimate and the actual figure
  when they exist and says that no cost was reported when they do not. An
  unknown cost never shows as zero.
- Cost lives in its own table keyed by the run's `build_id` and
  `build_number`. No plugin run model, UDT or index changes.
- A producer that reports no cost behaves exactly as today.
- The stored per-run figures are what ARGUS-218 will aggregate later.

## Out of scope

- Cost by category, cost per instance, and item rows.
- Leaked cost and the periodic cleanup scripts as a producer.
- A partial or incomplete flag on the actual figure.
- Live cost during a run. The estimate stands until the actual arrives.
- Any aggregation, filtering or dashboard across runs (ARGUS-218).
- Any pricing computation, catalog or currency conversion in Argus.
- A Go CLI command for dtest and driver-matrix. The Python client is the
  interface; a CLI command is a follow-up issue.
- Network or storage cost as separate figures. A producer includes them in
  the total if it computes them.
- Backfilling cost for runs that finished before this change.
