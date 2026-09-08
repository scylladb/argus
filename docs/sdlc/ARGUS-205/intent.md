# Intent: make the cost of a test run visible in Argus

| | |
| --- | --- |
| **Jira** | [ARGUS-205](https://scylladb.atlassian.net/browse/ARGUS-205) · epic [SCT-851](https://scylladb.atlassian.net/browse/SCT-851) · [SCT-852](https://scylladb.atlassian.net/browse/SCT-852) |
| **PR** | [scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071) |
| **SCT side** | [scylla-cluster-tests#15979](https://github.com/scylladb/scylla-cluster-tests/pull/15979) |
| **Follow-up** | [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218) (cross-run Cost Explorer) |
| **Stage** | 1 — Plan |
| **Status** | Open for discussion — decisions from the [#1071 review](https://github.com/scylladb/argus/pull/1071) folded in |
| **Date** | 2026-09-08 |

## Problem

Engineers who run tests cannot see what a run costs. The data exists only on the
cloud-monitor cost site, which is cumbersome to reach and effectively nobody checks, so
expensive mistakes — an oversized cluster, a run that leaked nodes for a weekend — go
unnoticed until someone audits the bill.

Nobody can answer these today:

- *What did this run cost?* — the run page shows no cost at all.
- *Is this release tracking to its estimate?* — a release owner has no running total to
  compare against what was budgeted.
- *What is my team spending?* — TLs and managers have no view of their own footprint,
  which is the visibility scylla-staging spend most needs.

## Proposed outcome

A run's cost is stored in Argus and shown on that run's page. Where the producer sends
detail, the run's cost is broken down by what the money went on; where it sends only a
total, the total is what is shown.

**The unit is the run.** Argus stores what the producer computes and sends. It performs no
pricing arithmetic of its own, and never derives a run's cost by inferring it from
resource records it happens to hold.

Cost also has to be **queryable across runs**, not just displayable on one, because the
questions above are aggregate questions:

| Aggregate | Who needs it |
| --- | --- |
| Per release | Release owner, tracking actual against the estimate while the release is in flight |
| Per team / per group | TLs and managers, for their own spend |
| Global, over time | Whoever is answering "why did the cloud bill go up" |

That is [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218) — the
[Cost Explorer mockup](https://claude.ai/code/artifact/6f49b965-a496-4d64-80a2-d9ab0073fcca)
shows the shape. This intent does not build it, but it must not make it impossible: an
actual cost that only exists as a read-time sum cannot be filtered or ranked, so the number
has to be stored.

**Phasing.** Phase 1 is the run total. Per-item detail is phase 2, and possibly never if it
proves not worth it — but the API and data model must accept both from the start, so phase
2 is a producer change rather than an Argus migration.

## Affected users and systems

**Users.** Anyone opening a run page. Later, release owners, TLs and managers via the
aggregate views.

**Producers.** SCT first. Cost is **not an SCT concept** — dtest, driver-matrix and any
future plugin can incur it — so the model and API are plugin-agnostic from the start.
Retrofitting that later means a migration.

**Systems.** A new cost model and its endpoints, a new tab on the run page, and the Python
client. Not the existing resource tables, not any plugin's run model.

## Constraints

1. **All cost arithmetic stays in the producer.** Argus has no pricing catalog and must not
   grow one. It stores what it is told and adds it up for display.
2. **Plugin-agnostic.** Keyed by `run_id` and carrying a plugin name — never a field on a
   plugin's run model or UDT.
3. **Actual cost is a stored, queryable column**, alongside the estimate. Required by the
   aggregates above.
4. **No new index on the plugin run tables.** Cost must not make `sct_test_run` more
   expensive to write for everyone, including runs that never report cost.
5. **Argus defines no category vocabulary.** Categories are whatever the producer sends. A
   fixed enum would mean an Argus change every time SCT grows a resource kind.
6. **Unknown must never render as free.** An unpriced component is null, never `0`.
7. **The run page is already dense.** The Resources table is wide before any of this; cost
   does not belong as extra columns in it.
8. **Old clients keep working.** A producer that reports no cost sees no error.

## Settled in review

Recorded here so they are not reopened by accident. Full threads on
[#1071](https://github.com/scylladb/argus/pull/1071).

| Question | Decision |
| --- | --- |
| Fixed category enum, or producer-defined? | **Producer-defined, free-form.** Argus shows what it is sent and defines nothing. |
| Live cost during a run? | **Dropped.** The estimate is shown until the run finishes, then the actual. This removes the whole live-extrapolation mechanism and shrinks the work. |
| Currency handling? | **USD only.** A producer with another currency converts before reporting. |
| Per-instance detail — core, or later? | **Both supported by the API; total ships first**, per-item is phase 2. Item rows carry a name and a category so Argus can sum by category now and drill down later. |
| Networking / storage costs? | Phase 2 at the earliest. No slots reserved — they are just categories, and appear if a producer sends them. |

## Open questions

1. **What does "partial" mean to a reader, and does it need a label?** It arises when a
   producer reports item detail but some items are unpriced, so the total is a floor rather
   than the real figure. Options: a `partial` / `incomplete cost` badge next to the total,
   or a plain count of unpriced items. Worth settling before the tab is built, because it
   determines whether the producer must send a flag or Argus can infer it from the items.
2. **Where do the aggregate views read from?** Directly from the stored per-run cost, or
   from a rollup maintained by [ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218)?
   This intent only requires that the per-run number be stored so either remains possible.
