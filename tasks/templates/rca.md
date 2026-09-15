# <KEY> — <short title>

**Date**: <YYYY-MM-DD>

## Root cause

The mechanism that produces the symptom in `intent.md`. Name the code path,
file and line included. Quote the evidence that ties the cause to the symptom.

## Approaches

One to three. For each one: what changes, what it costs, what it risks. Mark
the selected one and give the reason. This section is a decision record, so
the rejected approaches stay in it.

## Regression test

The test that fails before the fix and passes after it. Name the file and the
case. When no test can reproduce the bug, as with a setting that exists only
in production, write `None` and the reason.

## Risks

| Risk | Response |
|---|---|
| | |

---

A bug fix that changes a contract or a module boundary writes `spec.md` in
place of this file. A very small fix may skip the flow. The pull request
description then says so.
