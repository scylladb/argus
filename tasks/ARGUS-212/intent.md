# ARGUS-212 — Linked runs do not raise the Jira Seen Again Counter

## Problem

Jira bugs carry a "Seen Again Counter" field that is meant to say how often an
issue comes back. Argus records every run that reproduces an issue as a run to
issue link, but it never touches that counter. The counter stays at its
default, so a Jira reader cannot tell an issue seen once from one that
reproduces every day.

Removing a link leaves the counter as it was, too.

Not every issue carries the field. It depends on the project and the issue
type, and the stored value does not reveal it: ARGUS-212, a Story that does not
show the field, returns the same `0` as the bug SCT-684, which does.

## Who it affects

- Engineers who triage and prioritize bugs from the Jira view.
- Zeus and anyone else who links runs to Jira issues in Argus: the links they
  record never reach the Jira issue as a number.
- Once QATOOLS-417 removes the repeated Zeus comments, the counter becomes the
  only recurrence signal a Jira reader has.

## Evidence

Jira issue ARGUS-212:

```
Problem
Jira carries a "Seen Again Counter" field on bugs in all our projects. It is meant to say how often an issue comes back.
Argus records every run that reproduces an issue as a run to issue link, but it never touches that counter. The number therefore stays wrong, and nobody reading the Jira issue can tell how often it reproduces.

Impact
Today a repeated Zeus comment is the only signal on the Jira side that an issue keeps happening. QATOOLS-417 removes those comments, so the counter becomes the only number a Jira reader has.
Without this, an issue that reproduces every day looks the same in Jira as one seen once. Triage and priority decisions are made on that view.
```

SCT-684 (Bug) holds 13 Zeus comments that report a new occurrence between
2026-07-23 and 2026-09-08, for example:

```
2026-07-23T09:02:59.503+0000 Zeus: New occurrence of the same failure — posting for tracking.
2026-09-08T14:04:27.864+0000 Zeus: Another occurrence — provisioning failure
```

Its Seen Again Counter (`customfield_11252`) still reads `0`:

```
$ acli jira workitem search --jql 'key = SCT-684 AND "Seen Again Counter" = 0' --json
-> SCT-684
{"key":"SCT-684","t":"Bug","v":0}
{"key":"ARGUS-212","t":"Story","v":0}
```

## What good looks like

- When Argus records a new link between a test run and a Jira issue that
  carries the field, the issue's Seen Again Counter grows by one.
- When Argus deletes such a link, the counter decreases by one.
- An issue that does not carry the field, because of its type or its project,
  is skipped, and the link still succeeds.
- A Jira write that fails never blocks the link and never loses it. The failure
  is visible in the Argus logs.
- The counter semantics are documented.

## Out of scope

- Backfilling the counter for links that exist before this change.
- A "Last Seen" date field. Jira has no such field today.
- GitHub issues.
- Removing the Zeus comments, which QATOOLS-417 covers.
