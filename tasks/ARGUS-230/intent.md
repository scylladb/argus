# ARGUS-230 — Port the zeus SDLC improvements

## Problem

Argus and zeus run the same development flow. Zeus improved it in three merged
pull requests, and Argus still carries the earlier text. An engineer who works
in both repositories reads two versions of one flow.

The Argus spec template asks for "the files, the paths, and the behavior after
the change". A spec then fills with file lists and function signatures. A
maintainer who approves the design at Stage 2 reads implementation detail
instead. The template has no place for a flow diagram and no place for the
contracts a change adds.

The flow has one path. A bug fix has no design to review. It has a cause to
find, a fix to choose, and a test to prove the fix. The flow offers no artifact
for that, so a bug fix either writes a spec that says little or skips the flow
without a trace.

## Who it affects

Every engineer and every agent session that writes a spec or fixes a bug in
Argus. Every maintainer who approves a spec.

## Evidence

scylladb/zeus pull request 190: "The spec template carries a `Status` field
with the values `Draft`, `Approved` and `Implemented`. Nothing reads it."

scylladb/zeus pull request 191: "A spec becomes a short high-level design
document. It shows one flow diagram per flow the change adds or alters, and it
names the contracts."

scylladb/zeus pull request 193: "A Jira Bug gets a lighter path: `intent.md`,
`rca.md`, and code, with `plan.md` optional."

`tasks/templates/spec.md` in Argus reads: "## Target state — The files, the
paths, and the behavior after the change." It also carries the `Status` line.

`docs/standards/development-flow.md` in Argus names one artifact for Stage 2:
`tasks/<KEY>/spec.md`, approved by a maintainer. It names no path for a bug.

## What good looks like

The Argus templates, the flow document, the review policy, `CLAUDE.md`, and
`docs/INDEX.md` carry the zeus text at the merge of pull request 193. The
Argus-specific text stays: the `Fixes ARGUS-<n>` line, the `docs/plans/`
paragraph, the `AGENTS.md` line, and the Argus review checks.

## Out of scope

A change to `tasks/templates/intent.md`. A tool that checks the sections or the
length of a spec. A rewrite of any plan under `docs/plans/`.
