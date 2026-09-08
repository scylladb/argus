# Intent: make the cost of a test run visible in Argus

| | |
| --- | --- |
| **Jira** | [ARGUS-205](https://scylladb.atlassian.net/browse/ARGUS-205) · epic [SCT-851](https://scylladb.atlassian.net/browse/SCT-851) · [SCT-852](https://scylladb.atlassian.net/browse/SCT-852) |
| **PR** | [scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071) |
| **SCT side** | [scylla-cluster-tests#15979](https://github.com/scylladb/scylla-cluster-tests/pull/15979) |
| **Follow-up** | [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218) (cross-run Cost Explorer) |
| **Stage** | 1 — Plan |
| **Status** | **Open for discussion** — this supersedes the approach currently implemented in #1071 |
| **Date** | 2026-09-08 |

> **Why this document exists.** #1071 was opened without one, and the first substantive
> review comment was that the decisions in it had nowhere to be discussed. That is a fair
> hit. This intent and its spec are the place to settle the API and data model *before*
> more code is written, and they deliberately propose something different from what the PR
> currently implements.

## Problem

Engineers who run tests cannot see what a run costs. The data exists only on the
cloud-monitor cost site, which is cumbersome to reach and effectively nobody checks, so
expensive mistakes — an oversized cluster, a run that leaked nodes for a weekend — go
unnoticed until someone audits the bill.

The cost is knowable. SCT already has the pricing classes behind the cost site, and it
knows the instance types, regions, lifecycles and runtimes. What is missing is somewhere
to put the number where the person who caused it will see it.

## Proposed outcome

A run's cost is stored in Argus and shown on that run's page, broken down by what the
money went on — DB nodes, loaders, monitors, the runner, networking — so an engineer can
see both the total and which part of the setup dominated it.

**The unit is the run, not the instance.** Argus stores a total plus a category breakdown
that the producing system computes and sends. Argus does not assemble a run's cost by
summing per-instance records, and does no pricing arithmetic of its own.

Per-instance cost is a **possible later extension**, not part of this. It is genuinely
useful for "which node was expensive", but it is not what makes the feature worth having,
and treating it as the core forces a per-resource schema on every test type that reports
cost.

## Affected users and systems

**Users.** Anyone opening a run page — QA engineers, release leads. Later, whoever is
answering "why did the cloud bill go up", via [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218).

**Producers.** SCT first. But cost is **not an SCT concept** — dtest, driver-matrix and
any future plugin can incur cost, so the model and the API must be plugin-agnostic from
the start. Retrofitting that later means a migration.

**Systems.** A new cost model and its endpoints; the run page (a new tab); the Python
client. Not the existing resource tables, not `SCTTestRun`'s schema, not any plugin's run
model.

## Constraints

1. **All cost arithmetic stays in the producer.** Argus has no pricing catalog and must not
   grow one. It stores what it is told and adds it up for display.
2. **Plugin-agnostic.** Keyed by `run_id` and carrying a plugin name — never a field on
   `SCTTestRun` or on an SCT UDT.
3. **Actual cost must be stored, not only estimated.** A run needs both, and the actual
   figure has to be a queryable column, because filtering and ranking by real spend is the
   obvious next request and is impossible against a value that is only summed at read time.
4. **No new index on the plugin run tables.** Cost queries must not make `sct_test_run`
   more expensive to write for everyone, including runs that never report cost.
5. **Unknown must never render as free.** An unpriced component is null, never `0`.
   Partial totals must say they are partial.
6. **The run page is already dense.** The Resources table is wide before any of this; cost
   does not belong as extra columns in it.
7. **Old clients keep working.** A producer that reports no cost sees no error and no
   change in behaviour.

## Open questions — these are the discussion

1. **Category set.** Proposed: `db_node`, `loader`, `monitor`, `runner`, `oracle`,
   `network`, `storage`, `other`. Fixed enum, or free-form strings the producer chooses?
   Fixed gives comparable dashboards; free-form avoids Argus needing a change every time
   SCT grows a new kind of resource.
2. **Who owns "partial"?** Proposed: the producer sends a `complete` flag, since only it
   knows whether a component was unpriced. The alternative — Argus infers it from null
   categories — needs Argus to know the expected category set.
3. **Live cost during a run.** Proposed: the producer re-reports periodically and Argus
   shows the latest. The alternative, which #1071 currently implements, is Argus
   extrapolating `elapsed × hourly_rate`. That inherits a real defect: Argus stamps times
   when it is *told*, not when the instance started, and it already produced one
   false-zero bug from clock skew. Re-reporting removes the whole class.
4. **Where does filtering by cost live?** A `(release_id, bucket)` query table, or defer
   entirely to the ARGUS-218 rollup? This intent assumes the latter and only requires that
   `actual_cost` be a real stored column so either is possible.
5. **Currency.** Assume USD everywhere, or store a currency code? Cheap now, awkward later.
6. **Is per-instance wanted at all**, even as an extension? If nobody would use it, the
   optional table should not be built.
7. **Networking and storage.** The model has slots for them; SCT currently computes neither
   ([#15979](https://github.com/scylladb/scylla-cluster-tests/pull/15979) is instance-hours
   only). Do we ship categories that are always null until SCT catches up?

## What this means for #1071 as it stands

The PR currently puts `cost`, `price_per_hour` and `is_spot` on the SCT
`CloudInstanceDetails` UDT, `estimated_cost` on `SCTTestRun`, sums per-resource costs in
the frontend, and adds a Cost column to the Resources table. Under this intent, most of
that is the wrong shape: it is SCT-only, it stores no actual run cost, and it makes
per-instance the core rather than an extension.

What survives is the parts that were about honesty rather than structure — `sanitize_cost`
and the no-false-zero rules, which apply to any model — and the SCT-side contract that the
producer computes and Argus stores.

The reasonable paths are (a) reduce #1071 to the agreed core and move the per-instance
work to a follow-up, or (b) close it and open a clean one against this spec. That is a
decision for the reviewers, not for me to take unilaterally.
