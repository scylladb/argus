# QATOOLS-615 — Release summary per version, rolled up into the final version

This task covers QATOOLS-615 and QATOOLS-616 of epic QATOOLS-614 (Zeus
Release Test Management). The epic splits into two parts. The first is the
release summaries: this task. The second is the release chat and memory
(QATOOLS-617 to QATOOLS-621), a later task that reads the summary this task
builds.

## Problem

Nobody sees the test status of a release version in one place. Before a
release decision, release owners collect the numbers by hand across the test
runs and Jira. The work is slow, and the numbers go stale while tests still
run.

A final version, for example `2025.1.0`, is tested through its release
candidates `2025.1.0~rc0`, `~rc1`, and so on. Nothing shows the total status
of the final version across its candidates. A plain sum of the candidates
also misleads: an issue that rc1 reproduced and rc2 no longer shows still
reads as open.

The release dashboard and the view dashboard show one status per test, for
one selected version. They do not count per version. Their stats read only
the latest 15 runs of each test, so a version tested earlier in the release
falls out of the window. A version filter matches by prefix, so `2025.1`
mixes every family of the release. The stats know whether a run has an
issue, but not how many issues were reproduced, or whether an issue is new
to this version or was seen before.

## Who it affects

Release owners and QA leads decide from the summary whether a version is
ready to ship. Test engineers see which planned tests still need to run or
need triage. Developers and management read the release quality without
opening each run. The release chat in the second part of the epic answers
from the same summary.

## Evidence

Jira: [QATOOLS-615](https://scylladb.atlassian.net/browse/QATOOLS-615).
From the issue body:

> For each tested release version (for example 2026.4.0-rc1, 2026.4.0-rc2,
> 2026.4.0, 2026.4.1), the Argus release page shows an automatic summary for
> that version:
> tests executed
> tests pending for this version (planned, not started)
> tests in progress
> tests failed
> tests passed
> existing issues reproduced
> new issues reproduced

> The summary changes when a test of that version starts, finishes, or gets
> an issue.

Jira: [QATOOLS-616](https://scylladb.atlassian.net/browse/QATOOLS-616).
From the issue body:

> A later release candidate can fix an issue that an earlier one reproduced.
> A plain sum of the release candidate summaries shows that issue as still
> open.

> The 2026.4.0 summary counts the tests of all 2026.4.0-rcX versions.
> An issue that rc1 reproduced and rc2 fixed shows as fixed in the 2026.4.0
> summary.
> Each release candidate keeps its own summary next to the final one.

SCT runs of release `scylla-2025.1` on the development database, counted by
`scylla_version`:

```
    146                          2025.1.0
     10      2025.1.0.0.20250325.9dca28d2b818
      1      2025.1.0.0.20250401.023b27312d2b
    146                          2025.1.0~rc0
      1  2025.1.0.rc0.0.20250128.f407799f252d
    140                          2025.1.0~rc1
    266                          2025.1.0~rc2
      1  2025.1.0.rc2.0.20250216.6ee17795783f
    234                          2025.1.0~rc3
    190                          2025.1.0~rc4
```

The stats window, `argus/backend/plugins/core.py`:

```python
DEFAULT_STATS_PER_PARTITION_LIMIT = 15
```

The version filter, `argus/backend/util/common.py`:

```python
def check_version(filter_string: str, version: str) -> bool:
    if not version:
        return False
    if version.startswith(filter_string):
        return True
```

The only issue signal in the stats, `argus/backend/service/stats.py`:

```python
        self.has_bug_report = len(target_run["issues"]) > 0
```

## What good looks like

- Each tested version of a release has its own summary with the seven
  numbers. Each number matches a manual count of the runs and issues of
  that version.
- Each final version has a rolled-up summary over its release candidates,
  its `~dev` builds and the final build itself. An issue that a later
  candidate no longer reproduces shows as fixed. A patch version such as
  `2025.1.1` is a final version of its own.
- The summary follows the release without manual work. A run that starts,
  changes status or finishes, or an issue linked or unlinked, shows in the
  next read.
- A view dashboard can carry the summary as a widget. On a view it counts
  only the view's tests. The release dashboard shows the summary for the
  whole release.
- Opening the summary on a busy release stays fast, since the expensive
  count runs only after a change.
- Docs describe the summary, what each number counts, and how the rollup
  counts tests and issues across release candidates.

## Out of scope

- The release chat, the release context, starting tests from Argus, and
  changes to the summary by hand or from a chat. These belong to the second
  part of the epic (QATOOLS-617 to QATOOLS-621).
- Whether an issue is new or existing for an issue tracked in GitHub. The
  GitHub tracker is deprecated and new issues go to Jira.
- Changes to the response shape of the existing release and view stats
  routes.
