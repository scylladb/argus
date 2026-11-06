# QATOOLS-617 — Shared chat with memory on releases and views

This task covers QATOOLS-617 to QATOOLS-621 of epic QATOOLS-614 (Zeus
Release Test Management): the release chat, the release context with its
history, starting tests from the chat, adding findings to the summary from
the chat, and using the context in every answer. It is the second part of
the epic. The first part, the release summary per version (QATOOLS-615),
gives the chat its numbers.

The stories name Zeus as the assistant. The problem is not tied to one
assistant: Argus has no way to call any language model from a release or a
view, so each story needs a generic model connection first.

## Problem

Argus has no place to ask about a release. Questions such as "what failed on
rc3" or "which upgrade tests still need a run" are asked and answered in
private messages, so the rest of the team does not see them. The person who
answers collects the numbers by hand, even though the release summary now
holds them.

Release conventions live in people's heads. Examples: "we run tests on GCE",
"for each minor release we run sanity tests and performance tests". Nothing
in Argus records them, nothing shows who changed them, and a new team member
does not know them. An assistant cannot follow a convention that nobody
wrote down, so a user would repeat it in every request.

Starting release tests is manual. A user opens each test, or each plan
label, and sets each parameter by hand. A request such as "rerun failed
upgrade tests" first needs the user to find the failed tests. A setting
that a test's job does not support is only found out when the build fails.

The release summary is computed from runs and issue links. A finding from an
investigation, or a correction of a count, has nowhere to go. It is lost on
the next recompute and does not show next to the numbers.

Views have the same gaps. A view collects tests across releases, often for
one release plan, and its team has the same questions and conventions as a
release team.

Argus has no connection to a chat model that an administrator controls. The
existing AI code is the event summarizer, a separate worker bound to one
provider through the `ANTHROPIC_*` settings. The web backend calls no model.

## Who it affects

- Release owners and QA leads ask about a release or a plan view and decide
  from the answers, with the whole team seeing the same conversation.
- Test engineers start and rerun release tests and record the team's
  conventions and findings.
- New team members learn the conventions of a release from its context.
- Argus administrators choose which model and endpoint answer, and keep the
  endpoint credentials out of user reach.

## Evidence

Jira: [QATOOLS-617](https://scylladb.atlassian.net/browse/QATOOLS-617).
From the issue body:

> The Argus release view has no place to ask Zeus about a release. Questions
> and answers about a release stay in private messages, so the rest of the
> team does not see them.

> All users see every question and every answer. Answers are collapsed by
> default. Questions and requests are usually short and answers are usually
> long, so the page shows the history of requests without a long wall of
> answers.

Jira: [QATOOLS-618](https://scylladb.atlassian.net/browse/QATOOLS-618).
From the issue body:

> Release conventions live in people's heads. Examples: "we run tests on
> GCE", or "for each minor release we run sanity tests and performance
> tests". Zeus cannot follow a convention that nobody wrote down, and a new
> team member does not know them.

> The history shows the author, the time, and the change for each edit.
> A user can read every earlier version of the context.

Jira: [QATOOLS-619](https://scylladb.atlassian.net/browse/QATOOLS-619).
From the issue body:

> To run release tests, a user starts each test or test plan label by hand
> and sets each parameter by hand. Common requests like "rerun failed upgrade
> tests" need the user to find the failed tests first.

> A test starts only with settings that its test metadata supports.

> "run week1 tests on gce" starts the tests with the week1 label on GCE.
> "rerun failed upgrade tests" starts only the upgrade tests that failed for
> this version.
> The answer lists each started test with a link to its run.
> A test whose metadata does not support the requested setting does not
> start, and the answer says why.

Jira: [QATOOLS-620](https://scylladb.atlassian.net/browse/QATOOLS-620).
From the issue body:

> The release summary is automatic. People find things that the automation
> does not know, such as a finding from an investigation or a wrong count.
> They have no way to add this to the summary.

Jira: [QATOOLS-621](https://scylladb.atlassian.net/browse/QATOOLS-621).
From the issue body:

> Without the release context, Zeus does not follow the release conventions.
> Users must repeat them in every request, and they forget some.

> The expanded chat answer shows the context version that Zeus used.
> After a change to the context, the next answer follows the new context.

The only model settings in `argus_web.example.yaml` belong to the event
summarizer:

```yaml
# ANTHROPIC_API_KEY: your-anthropic-key      # required only when summarization is enabled
# ANTHROPIC_BASE_URL: https://api.anthropic.com  # set for a proxy or compatible endpoint
ANTHROPIC_SUMMARY_MODEL: claude-sonnet-5      # eval winner (argusAI/eval/baseline)
```

Test labels are resolved only in the command line tool,
`cli/internal/services/planner.go`:

```go
// ResolveLabeledTests resolves a plan (by UUID or "releaseName#planNumber" key)
// and a set of labels to the plan's matching tests.
```

The plan-wide trigger, `PlanningService.trigger_jobs` in
`argus/backend/service/planner_service.py`, matches parameters only for
longevity jobs:

```python
            for param_set in params:
                if param_set["test"] == "longevity" and backend == param_set["backend"]:
```

## What good looks like

- A release and a view each have one chat that every user shares. A user
  asks a question and gets an answer. Another user sees the question, who
  asked it, and the answer, after a page reload too.
- Answers are collapsed by default. A user can retry an answer, or undo the
  last exchange, without losing what the others see.
- An answer about test results matches the release summary.
- Each release and view keeps memories: conventions and findings that any
  user adds, edits, or removes, directly or through the chat. Every change
  shows its author, its time, and the change itself, and can be reverted.
  A view's chat also follows the memories of the releases of its tests.
- Every answer follows the current memories, and the expanded answer shows
  which ones it used.
- A request to run tests by name, by plan label, or by status ("rerun failed
  upgrade tests") lists the matching tests with their settings. A test whose
  job does not support a requested setting is listed with the reason and is
  left out. Nothing starts until a user confirms. The answer then links each
  started test.
- A finding added through the chat shows in the release summary, with its
  author, and stays after the summary refreshes.
- A user sees how much of the model's context the conversation fills, and
  can compact it when it grows too large.
- An administrator connects Argus to any OpenAI-compatible chat endpoint,
  sees the models the endpoint offers with what each supports, and picks the
  model every chat uses. Endpoint credentials are never shown back.
- Docs describe the chat, the memories, the requests it understands with
  examples, and how memories affect the answers and the summary.

## Out of scope

- A second model API shape, such as the Anthropic Messages API, and the
  external Zeus service. They can connect later through the same interface.
- Limiting by role who may chat, confirm a test start, or edit memories.
- Memories that apply to every release.
- Moving the event summarizer onto the new model connection.
- A generated narrative in the release summary. Its numbers stay computed
  from runs and issues.
