# QATOOLS-464 — Argus consumes the qatools-sdlc plugin

## Problem

Argus carries its own copy of the development flow text:
`docs/standards/development-flow.md`, `docs/standards/REVIEW.md`, the four
templates under `tasks/templates/`, and the Task Artifacts rules in
`CLAUDE.md`. The `qatools-sdlc` plugin holds the same text for every QA Tools
repository. The two copies diverge, and every change to the flow is ported to
Argus by hand.

The copy in Argus already differs from the plugin. The commit gates name
`rca.md` where the plugin names only `spec.md`. The pull request body rule
reads `Fixes ARGUS-<n>` where the plugin reads `closes <JIRA-ID>` or
`refs <JIRA-ID>`. The review policy holds a `Scope` section and a
`Before you report a finding` section that the plugin text does not hold.

An agent session in Argus follows the local text and the brainstorming skill.
It does not run the plugin skills, so a flow change that lands in the plugin
does not reach Argus until somebody copies it.

## Who it affects

Every engineer and every agent session that runs a task in Argus. The
maintainers of the plugin, who port each change to Argus by hand.

## Evidence

Jira: [QATOOLS-464](https://scylladb.atlassian.net/browse/QATOOLS-464). The
issue body:

> Argus carries its own copy of the development flow:
> `docs/standards/development-flow.md`, `docs/standards/REVIEW.md`,
> `tasks/templates/*.md` and the Task Artifacts rules in `CLAUDE.md`. The copy
> diverges from the plugin text, and every flow change is ported by hand.

`diff docs/standards/development-flow.md <plugin>/docs/development-flow.md`
on this branch, against plugin version 1.0.1:

```
< - Do not write the spec, or the rca, until `tasks/<KEY>/intent.md` is
<   committed.
< - Do not write the plan until `tasks/<KEY>/spec.md`, or `rca.md`, is
<   committed.
< - Do not write code until the last artifact of the task is committed.
---
> - Do not write the spec until `tasks/<KEY>/intent.md` is committed.
> - Do not write the plan until `tasks/<KEY>/spec.md` is committed.
> - Do not write code until `tasks/<KEY>/plan.md` is committed.
```

`.claude/settings.json` on this branch holds one key, `permissions`. It
declares no marketplace and no plugin.

## What good looks like

- Argus holds no copy of the flow text and no copy of the templates.
- `.claude/settings.json` declares the `qatools` marketplace and the
  `qatools-sdlc` plugin, so a session in the repository knows which plugin
  to install.
- `CLAUDE.md`, `README.md`, `docs/INDEX.md`, `AGENTS.md`, and the command
  files under `.claude/commands/` point at the plugin for the flow, the
  templates, and the review policy.
- One task, this one, runs through `/qatools-sdlc:intent`,
  `/qatools-sdlc:spec`, and `/qatools-sdlc:plan`, and its artifacts sit in
  `tasks/QATOOLS-464/`.

## Out of scope

- A change to the plugin text. A rule that Argus needs and the plugin lacks
  goes to a repository standard under `docs/standards/`, or to a plugin
  issue.
- A change to the artifacts of the tasks already under `tasks/`. They stay
  as a record.
- A change to the coding standards under `docs/standards/backend/`,
  `docs/standards/frontend/`, `docs/standards/testing/`, and
  `docs/standards/global/`, other than the lines that name the two deleted
  files.
- The install of the plugin at user scope on each engineer's machine.
