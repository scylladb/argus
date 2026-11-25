# ARGUS-148 — Run planned tests by label, with labels visible and the chat explained

The release chat (QATOOLS-617) already starts the tests of a release plan
that carry a label, after a user confirms the card. This task covers what the
issue's comments still ask for before the feature counts as complete.

## Problem

Release plans carry labels such as `week1`, and the chat starts the tests
that carry them. The web UI never shows a label. The planner does not list
the labels of a plan or of its tests and groups, cannot add or remove one,
and cannot filter by one. The release dashboard cannot filter by one either.
A user learns which tests `week1` holds only by asking the chat or by reading
the plan through the command line tool.

The planner also loses labels. Creating a plan from an existing one sends no
labels, so the new plan has none. Splitting a group into its tests removes
the group, and the group's labels go with it.

Running a plan is a series of batches with a check in between: start the
`week1` tests, see how they did, then rerun what failed or did not run. The
chat cannot answer "how is `week1` doing on rc4?" for a plan in one step, and
cannot start only the labelled tests that failed or did not run on a version.
The read tools that list tests, results and assignees cannot be narrowed to a
plan's labels.

A user who opens the chat sees one sentence of examples. Nothing in the chat
tells the user that it can start tests, that a start waits for a
confirmation, or how labels select tests. The documentation lists examples,
but the chat does not link to it.

## Who it affects

- Release owners and QA leads who plan a release in labelled batches and
  follow each batch.
- Test engineers who start and rerun the tests of a plan, from the chat or
  from the planner.
- Release engineering, who want the planned tests of a new release candidate
  started with little manual work.
- New users of the chat, who do not know what it can do.

## Evidence

Jira: [ARGUS-148](https://scylladb.atlassian.net/browse/ARGUS-148).
From the issue body:

> We should provide the releng team the API/CLI to update Arugs that new RC is promoted.
> Argus will take the list of jobs that are planned for the RC and execute them with that RC.

From the comments:

> I don’t mind about the mechanism to operate it (e.g. AI chat or schedule), but I do mind about the ability to easily trigger set of jobs that were defined as part of the plan. It can be set of prompts with a verification step in between, or human approval between steps and AI maintaining the jobs triggering.

> for this to consider it as complete we need more documentation and some UI hints: show and filter by labels , show what users can do in AI chat - especially how to run tests

The plan editor creates a plan without its labels,
`frontend/ReleasePlanner/ReleasePlanCreator.svelte`:

```js
            let planPayload = {
                name: plan.name,
                description: plan.description,
                owner: plan.owner,
                participants: plan.participants,
                target_version: plan.target_version,
                release_id: plan.release_id,
                view_id: plan.view_id,
                tests: plan.tests,
                groups: plan.groups,
                assignments: plan.assignments,
                created_from: plan.id,
            };
```

No file under `frontend/ReleasePlanner/` reads the plan's `options`, which
hold the labels.

The whole hint of an empty chat, `frontend/Chat/ChatModal.svelte`:

```svelte
                            <p class="mb-1">No questions yet.</p>
                            <p class="small mb-0">Try "what failed on the latest release candidate?" or "rerun the
                                failed upgrade tests on gce".</p>
```

## What good looks like

- The planner shows each plan's labels, and the labels of each test and group
  in a plan. A user adds and removes labels there and filters the plan's
  tests by label. A plan created from another one keeps its labels, and
  splitting a group keeps the group's labels on its tests.
- The release dashboard filters its tests by a plan label.
- The chat answers how a plan, or a label of it, did on a version: how many
  tests passed, failed, still run or did not run, and which ones.
- The chat proposes to start only the tests of a plan, or of a label, that
  failed or did not run on a version. Nothing starts until a user confirms.
- Questions about tests, results and assignees can be narrowed to a plan's
  labels.
- An empty chat shows what users can ask, grouped by what it does, with
  starting tests among them. A user can bring up the same examples at any
  time, and from there reach the documentation.
- The documentation describes labels in the planner, the label filters, plan
  progress, and running tests step by step.

## Out of scope

- Starting tests without a user's confirmation, on a schedule or from a
  release promotion.
- Labels in the plan-wide trigger API and its command line command.
- Labels outside release plans, such as on tests or groups themselves.
- Changing how the command line tool edits labels.
