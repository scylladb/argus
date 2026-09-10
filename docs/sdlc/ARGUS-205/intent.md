# Intent: make the cost of a test run visible in Argus

| | |
| --- | --- |
| **Jira** | [ARGUS-205](https://scylladb.atlassian.net/browse/ARGUS-205) · epic [SCT-851](https://scylladb.atlassian.net/browse/SCT-851) · [SCT-852](https://scylladb.atlassian.net/browse/SCT-852) |
| **PR** | [scylladb/argus#1071](https://github.com/scylladb/argus/pull/1071) |
| **SCT side** | [scylla-cluster-tests#15979](https://github.com/scylladb/scylla-cluster-tests/pull/15979) |
| **Stage** | 1 — Plan |
| **Status** | Agreed in the [#1071 discussion](https://github.com/scylladb/argus/pull/1071); open questions below |
| **Participants** | @soyacz, @k0machi, @roydahan, @fruch |
| **Date** | 2026-09-10 |

## Problem

Engineers who run tests cannot see what a run costs. The data exists only on the
cloud-monitor cost site and in DoIT reports, which are cumbersome to reach and effectively
nobody checks, so expensive mistakes — an oversized cluster, a run that leaked nodes for a
weekend — go unnoticed until someone audits the bill.

A specific failure worth naming, because it drives the leak requirement: someone sees that
`longevity-x` cost a great deal and concludes the test is expensive, when most of the
figure was resources left behind after the run finished. Without separating the two, the
number misleads.

## Proposed outcome

Two things, and deliberately nothing else.

### 1. Per run: the estimate and the actual cost

Every run page shows what the run was estimated to cost and what it actually cost. The
estimate is available up front and stands until the run finishes; the actual replaces it
at the end of the run, or after resources are cleaned up.

A run-level breakdown by **category** is available here too — DB nodes, loaders, monitors,
runner, network. Aggregates do not use it, but being able to ask "how much of this run was
loaders" is worth keeping at run level.

### 2. A cost dashboard: filter and aggregate across runs

| Filter / aggregate | |
| --- | --- |
| Time range | The primary axis |
| Release | Frequently the first thing asked for |
| Backend | Cloud provider |
| Test status | Passed / failed — spend on failed runs is its own question |
| Lifecycle | Spot vs on-demand |
| Leaked | Cost of resources removed by the periodic cleanup scripts, not by the run |
| Cost by test | |
| Cost by run | Top spenders |
| Team | TL and manager visibility into their own footprint |

Each figure carries whether it is complete or partial.

The [Cost Explorer mockup](https://claude.ai/code/artifact/6f49b965-a496-4d64-80a2-d9ab0073fcca)
([ARGUS-218](https://scylladb.atlassian.net/browse/ARGUS-218)) shows the shape. Not all of
it lands on day one, but the data model is designed so that it can.

**Network cost is a day-one requirement** and counts toward the total (@roydahan). A
breakdown of network cost specifically is a later addition.

## Affected users and systems

**Users.** Engineers on the run page; release owners tracking a release against its
estimate; TLs and managers via the dashboard; whoever is answering "why did the cloud bill
go up".

**Producers.** SCT first, plus the **periodic cleanup scripts**, which are the only thing
that can report a leaked cost. Cost is not an SCT concept — dtest, driver-matrix and any
future plugin can incur it — so the model and API are plugin-agnostic from the start.

**Systems.** New cost tables and endpoints, a new tab on the run page, a dashboard, and
the client. Not the existing resource tables and not any plugin's run model.

## Constraints

1. **All cost arithmetic stays in the producer.** Argus has no pricing catalog and must not
   grow one.
2. **Plugin-agnostic**, keyed by `run_id` — never a field on a plugin's run model or UDT.
3. **Actual cost is stored and queryable**, alongside the estimate. The dashboard is
   impossible against a read-time sum.
4. **No new index on the plugin run tables.**
5. **Argus defines no category vocabulary.** Categories are whatever the producer sends.
6. **Unknown must never render as free.** An unpriced component is null, never `0`.
7. **The run page is already dense** — cost gets its own tab, not columns in the Resources
   table.
8. **Old clients keep working.** A producer that reports no cost sees no error.

## Settled in discussion

| Question | Decision |
| --- | --- |
| Category vocabulary | **Producer-defined, free-form.** Argus defines and rejects nothing. |
| Categories from day one? | **Yes** (@roydahan: better more information than less; @soyacz agreed). Stored day one, used for run-level detail. |
| Per-individual-instance breakdown | **Not needed** (@roydahan). Item rows exist so run-level detail is possible, but no product requirement asks for per-instance figures. |
| Aggregates over categories or totals? | **Totals** (@soyacz). Category detail is run level only. |
| Live cost during a run | **No.** The estimate stands while the run is in flight; the actual arrives at the end of the run or at cleanup. No extrapolation anywhere. |
| Currency | **USD only.** Producers convert before reporting. |
| Network cost | **Day one, inside the total** (@roydahan). Its own breakdown is later. |
| Leaked cost | **Tracked as its own figure**, reported by the periodic cleanup scripts. |
| Per-view aggregation | **Feasible** — a widget aggregating run costs over the view's tests (@k0machi). Whether it ships day one is open, below. |

## Open questions — @fruch, for the team

These need answers before the spec is final. Raising them rather than assuming.

1. **xcloud / k8s backend attribution.** Raised by @soyacz: for xcloud and k8s the backend
   is compound. Do we record the underlying provider, `xcloud`/`k8s` alone, or both as
   separate fields? Both is cheap now and impossible to retrofit into rows already written.
2. **Is per-view aggregation worth doing?** @k0machi has shown it is feasible by storing
   `test_id` and hydrating names on the backend. @soyacz asked whether it is worth the
   extra denormalization. My read: yes, because a view is how teams already scope their
   work — but I would rather @roydahan confirm it is a real need than build it on my guess.
3. **How precise does leaked cost need to be?** @roydahan is clear that identifying leaks
   matters. My question is whether the *amount* must be accurate, or whether "this run
   leaked, and roughly this much" is enough. It changes how hard the cleanup scripts have
   to work.
4. **Is `actual_cost` sent or computed?** @soyacz's `set_actual_cost` takes a value;
   @k0machi suggested the backend sum the reported items so successive calls accumulate
   correctly. These conflict, and the answer decides whether a producer can report a total
   without itemising.
5. **Instance-hours are not stored.** @soyacz listed this as a limitation. Accepting it
   means we can never re-price history when rates change, or show a $/hour figure. Fine by
   me, but it should be a decision.
6. **Network cost is a day-one requirement that nothing computes yet.** SCT's
   [#15979](https://github.com/scylladb/scylla-cluster-tests/pull/15979) is instance-hours
   only. Does Argus ship the field and wait, or does this block?
7. **dtest and driver-matrix need a CLI command** to report cost, since they are
   executables rather than pluggable modules (@k0machi). Who owns adding it, and is it in
   scope here or a follow-up?
