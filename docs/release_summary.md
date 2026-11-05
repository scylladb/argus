# Release summary

The release summary counts the tests and issues of each tested version of a
release. The release dashboard shows it for the whole release. A view shows it
as the *Release summary per version* widget, for the tests of the view only.

## Versions and families

The summary reads the `scylla_version` of each run and keeps the base version
plus an optional `~rcN` or `~dev` suffix. Package build suffixes are dropped.

| Run version | Summary version | Family |
|---|---|---|
| `2025.1.0~rc2` | `2025.1.0~rc2` | `2025.1.0` |
| `2025.1.0.rc0.0.20250128.f407799f252d` | `2025.1.0~rc0` | `2025.1.0` |
| `2025.1.0.0.20250325.9dca28d2b818` | `2025.1.0` | `2025.1.0` |
| `2024.1.0~dev` | `2024.1.0~dev` | `2024.1.0` |
| `2025.1.1` | `2025.1.1` | `2025.1.1` |

A family is the final version that its development builds and release
candidates lead to. A patch version such as `2025.1.1` is a family of its own.
A run whose version does not have this shape, or that has no version, is not
counted.

The versions of a release are the versions of its runs plus the target
versions of its release plans. A planned version with no runs yet shows every
planned test as pending.

When the release sets a valid version regex in the release editor, only runs
and plans whose version matches it count. The match is unanchored, as in the
dashboard's version filter: `2025.1(.*)` keeps `2025.1.0~rc2` and `2025.1.1`
and leaves out a `2024.2.6` run of the same release.

## What each number counts

Each test counts once per version, by its latest run on that version. Disabled
tests, and tests of disabled groups, are not counted.

| Number | Counts |
|---|---|
| Executed | Tests whose latest run passed, failed, ended in a test error or an error, or was aborted |
| Passed | Tests whose latest run passed |
| Failed | Tests whose latest run failed, or ended in a test error or an error |
| Aborted | Tests whose latest run was aborted |
| In progress | Tests whose latest run is created or running |
| Pending | Tests that a release plan for this version holds, with no run on this version |
| New issues | Issues linked to a run of this version and first seen on this version |
| Existing issues | Issues linked to a run of this version and first seen before it |

A release plan holds its tests and every enabled test of its groups. Only
plans with a target version count. The target version is read the same way as
a run version.

### New or existing

An issue's first run is the run of its earliest link, in any release. An issue
is new on a version when that run is a run of this release on that version. On
the family row, it is new when that run is on any version of the family.
Otherwise the issue is existing. Jira and GitHub issues follow the same rule.
Argus removes an issue when its last link goes, so an issue linked again
afterwards counts from its new first link.

## The family row

The family row, *All of 2025.1.0*, rolls up the family's versions:

- A test counts once, by its latest run in version order (`~dev`, `~rc0`,
  `~rc1`, …, then the final build), then by start time.
- Pending counts the tests that a plan for any version of the family holds and
  that have no run in the family.
- An issue is **fixed** when no test that reproduced it carries it on its
  family result, and each of those tests ran again to a final status on a
  later version. Otherwise it is open.
- The row adds the *Fixed issues* count.

The issue list groups issues by their state in Jira or GitHub. Each issue says
whether it is linked to the latest run of a test in the family, or on which
version it was last seen. A closed issue on a latest run is not necessarily
back: it may have been closed after that run, before any test ran again.

## Reading the summary

The release dashboard shows the summary as a collapsed *Release summary* panel.
Each family has two tabs:

- **Timeline**: one row per version, with the family row first. A click on a
  count, or on a bar segment, lists the tests behind it.
- **Grid**: one row per test and one column per version, each cell linked to
  its run.

The status toggles filter both tabs, each on its own; a count or a bar segment
shows only its status. On the release dashboard, a click on a
test name adds the test to the selected tests beside the test dashboard, as a
click in the test dashboard does.

## When the summary refreshes

The summary is stored per release and recomputed on the first read after a
change. These actions mark it for a refresh:

- a run is submitted, changes status, gets its version, or finishes
- an issue is linked to or unlinked from a run
- a comment, an assignee or an investigation status changes
- a release plan changes
- a release, a group or a test is edited, enabled or disabled, or moves

A refresh reads every run of the release once. If a refresh fails, the summary
shows the last stored figures with a note.

## API

`GET /api/v1/release/{release_id}/version_summary` and
`GET /api/v1/views/widgets/release_summary?view_id=` return the summary.
[`api_usage.md`](api_usage.md) describes the response.
