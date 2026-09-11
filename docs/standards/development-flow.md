# Development flow

Argus runs six stages. Each stage produces one artifact. Each artifact is the
input of the next stage.

The Jira key joins the work. It names the task directory. It also appears in
the `Fixes ARGUS-<n>` line at the end of the pull request body.

## The stages

| Stage | Artifact | Approver |
|---|---|---|
| 1. Plan | `tasks/<KEY>/intent.md` | the issue reporter |
| 2. Design | `tasks/<KEY>/spec.md` | a maintainer |
| 3. Build | `tasks/<KEY>/plan.md`, then code | the engineer who runs the session |
| 4. Test | test output in the pull request | CI |
| 5. Review | review comments | a maintainer |
| 6. Maintain | a new Jira issue | the assignee of the Jira issue |

## The order of commits

Commit each artifact before you start the stage that consumes it.

- Do not start a task that has no intent. Write the intent first.
- Do not write the spec until `tasks/<KEY>/intent.md` is committed.
- Do not write the plan until `tasks/<KEY>/spec.md` is committed.
- Do not write code until `tasks/<KEY>/plan.md` is committed.

A commit gate is not an approval gate. A committed artifact stays open to
review, and a later commit records the correction. The gate fixes the order of
the work, not the content of the artifact.

The branch history then carries the flow. A reviewer reads the intent, the spec
and the plan in the order the work happened.

The spike path below is the one exception to this order.

## Stage 1 — Plan

State the problem, not the solution. Copy `tasks/templates/intent.md` to
`tasks/<KEY>/intent.md` and fill it in. An agent session writes this file from
a conversation.

A Jira issue body may already carry an intent. Start from it when it does.

The reporter reads the file and corrects any misunderstanding. An intent may
arrive incomplete or unclear, so review it either way. Commit it.

## Stage 2 — Design

Write `tasks/<KEY>/spec.md` from the approved intent. The brainstorming skill
writes this file. It covers the problem, the goals, the non-goals, the target
state, and the risks.

A spec that names no non-goal is not finished. Scope grows without one.

A maintainer approves the spec before the build stage starts.

## Stage 3 — Build

Write `tasks/<KEY>/plan.md` before any code. The spike path below is the
exception. The plan names the files, the order of work, and the tests.
Somebody who never saw the task must be able to follow it.

Then write the code. Follow the standards in `docs/standards/`.

`docs/plans/` holds the plans that started before this flow. Those plans keep
the format in `docs/plans/INSTRUCTIONS.md` until the work ends. New work writes
its plan to `tasks/<KEY>/plan.md`.

## The spike path

Sometimes the design lives in the head of the developer, who writes the fix to
find out whether it works. The code then exists and no artifact does.

This path applies to that case only. Use it for a small change, where the
design comes from the code. The artifacts still serve the review and the next
reader.

1. Stop before you commit the code.
2. Write `intent.md` and `spec.md` from the code that already works.
3. Commit the artifacts. Then commit the code.

The order of the commits holds. The artifacts are the earlier commits on the
branch, whatever order the work happened in.

The spec on this path states the design the code carries. A reviewer reads it
like any other spec, and Stage 5 checks the change against it.

This path writes no `plan.md`. A plan describes work that is already done.

## Stage 4 — Test

Run the verify sequence in the `Commands` section of `CLAUDE.md`. Work is done
when that sequence passes.

CI runs the same commands. A local pass and a remote pass must agree.

A backend test needs Docker. The fixtures start a ScyllaDB container.

## Stage 5 — Review

Open a pull request. Title it `type(scope): summary`. End the body with
`Fixes ARGUS-<n>`.

`docs/standards/REVIEW.md` holds the review policy. A reviewer works through
its three passes and states the outcome of each one.

A maintainer approves the merge. An agent never approves its own pull request.
Findings do not block a merge on their own.

## Stage 6 — Maintain

A production problem becomes a Jira issue, and the issue starts at Stage 1.

The assignee decides to fix it now, to schedule it, or to close it.

Prometheus scrapes the application metrics. No automatic trigger opens an issue
from a metric. A person reads the dashboard and files the issue.

## What runs without asking

CI runs the lint, the test and the build commands on every pull request: the
pre-commit hooks, the Python suites, the reporter suite, the frontend suite,
the frontend bundles and the Go suite. A workflow adds the `ai-assisted` label
when it finds an AI marker. Nothing else acts without a person. No hook checks
the order of the commits.

A person decides: the intent, the spec, the merge, and the release.
