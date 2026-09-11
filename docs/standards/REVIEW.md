# Review policy

This policy applies to every pull request. A reviewer works through the three
passes in order.

Findings do not block a merge on their own. A maintainer approves the merge.

## Scope

The diff is the review boundary. Report a finding on a line the pull request
changes. A problem in unchanged code is a separate task.

Report the highest-confidence findings, up to five. Group the small ones into
one comment. A review of twenty minor findings hides the one that matters.

## The outcome of a pass

A review states an outcome for every pass. The outcome is `pass`, or the
findings of that pass. A pass with no outcome did not run.

A pass runs even when it finds nothing. Report the three outcomes together, in
order, so a reader sees which pass produced which finding.

## Pass 1 — Bugs and logic

- Does the change do what the pull request says it does?
- Which input makes it fail? Name one.
- Does an error path swallow the error? A bare `except` and an ignored return
  value both hide a failure.
- Does a test assert the behavior, or does it assert the implementation?
- Does a read use `allow_filtering()` on a table that grows without a bound?

## Pass 2 — Security

- Does a diff carry a credential, a token, or a host name?
- Does a route reach the service layer without `Depends(api_current_user)`?
- Does a template render user content into an unescaped environment?
- Does a query build CQL from user input by string formatting?
- Does a new dependency arrive without a version floor?

## Pass 3 — Compliance against the spec

Find the spec first. The Jira key comes from the `Fixes ARGUS-<n>` line in the
pull request body, or from a `tasks/<KEY>/` directory in the diff. Read
`tasks/<KEY>/spec.md`.

A pull request that predates this flow carries no spec. Record the outcome
`not applicable — no task spec` and check the standards only. Do not ask the
author to write one for work that is already open.

- Read `tasks/<KEY>/spec.md`. Does the change stay inside its goals?
- Does the change do something the spec lists as a non-goal?
- Does the change follow the standards in `docs/standards/`?
- Does a new prose artifact keep a record of a dropped decision?
- A spec from the spike path states the design the code carries. Does it?

## Before you report a finding

Each check below removes a class of false report seen in this repository. Drop
the finding when a check fails.

1. **Read the full context.** Read the complete CSS rule, the whole function,
   or the component. Do not report `color: black` before you check the
   `background-color` of the same selector. Do not call a name unused before
   you search for it. Do not call a function broken before you read its
   callers.
2. **Name a concrete failure.** A report of `Critical` or `likely a bug` needs
   a realistic reproduction. Call a rare race or an unlikely input a
   `potential concern` instead.
3. **Weigh the runtime evidence.** A pull request that links a staging URL or
   describes a manual test carries evidence. A static finding against that
   evidence needs a qualifier.
4. **Treat a repeated pattern as a convention.** A pattern in three or more
   places is a decision of the team.
5. **Read the existing comments first.** Do not report what a human reviewer
   already found.
6. **Apply Svelte 5 semantics.** `$state` makes a deep reactive proxy, so
   `.push()` on a `$state` array triggers an update and needs no reassignment.
   A reassigned `$derived` variable is a bug. Report it.
7. **Treat a CSS color pair as self-contained.** A severity badge, a status
   indicator and an alert class each set `background-color` and `color`
   together, so they hold in any theme. Report a color only when the element
   depends on the inherited page background.
8. **Leave migration code alone.** A fallback or a dual path inside a migration
   is deliberate.
