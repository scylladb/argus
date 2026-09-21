# QATOOLS-464 — implementation plan

**Spec:** `tasks/QATOOLS-464/spec.md`

## Constraints

- Prose in ASD-STE100 Simplified Technical English, flavored mode.
- No text keeps a record of the deleted files or of the old body line.
- The task carries no test. `docs/standards/testing/test-writing.md` writes no
  test for Markdown content. Each task ends with `uv run pre-commit run
  --all-files` and a grep that shows no reference to a deleted path outside
  `tasks/`.
- One commit per task, subject `type(scope): summary`, scope of five
  characters or more, body of thirty characters or more.

## Task 1 — Bind the repository with init

**Files:**
- Modify: `.claude/settings.json`, add `extraKnownMarketplaces` and
  `enabledPlugins`
- Create: `tasks/README.md`, the plugin text verbatim
- Modify: `CLAUDE.md:12-69`, the `Development Flow` and `Task Artifacts`
  sections give way to the plugin section, `{{KEY_PREFIX}}` set to `ARGUS`

**Internals:** none.

- [x] Run `/qatools-sdlc:init`.
- [x] Delete `CLAUDE.md` lines 12 to 69 and place the plugin section there.
- [x] Run init a second time. `git status --short` shows the same files.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit.

## Task 2 — Delete the copies

**Files:**
- Delete: `docs/standards/development-flow.md`
- Delete: `docs/standards/REVIEW.md`
- Delete: `tasks/templates/intent.md`, `spec.md`, `plan.md`, `rca.md`
- Delete: `.claude/commands/review-pr.md`
- Create: `docs/standards/global/review-findings.md`, the sections of the
  spec Outputs: Scope, Before you report a finding, A pull request without a
  task

**Internals:** none.

- [x] Write `review-findings.md` from the `Scope` and `Before you report a
  finding` sections of `docs/standards/REVIEW.md`, checks 1 to 5 and 8, and
  the `not applicable — no task spec` paragraph.
- [x] Delete the seven files.
- [x] `grep -rn "development-flow.md\|REVIEW.md\|tasks/templates\|review-pr" --exclude-dir=tasks --exclude-dir=node_modules --exclude-dir=.git .`
  lists only the pointers that Task 3 changes.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit.

## Task 3 — Point the documents at the plugin

**Files:**
- Modify: `docs/INDEX.md:35-43`, the `Process Standards` block names the
  plugin and its skills in place of the two files
- Modify: `docs/INDEX.md:58`, the conventions entry reads
  `closes <KEY>` or `refs <KEY>` for the closing line
- Modify: `docs/INDEX.md`, a `Review Findings` entry under `Global Standards`
- Modify: `AGENTS.md:57-58`, the two table rows name the plugin skills and
  `docs/standards/global/review-findings.md`
- Modify: `AGENTS.md:93-96`, the `Implementation Plans` section names
  `/qatools-sdlc:plan`
- Modify: `README.md:83-85`, the `Contributing` section names the plugin and
  its two install commands
- Modify: `docs/project/roadmap.md:4`, the sentence names the plugin flow
- Modify: `docs/standards/global/conventions.md:29`, the body line rule in
  the words of the spec
- Modify: `docs/standards/global/conventions.md:62-64`, the review policy
  lives in the plugin, the Argus checks in `review-findings.md`

**Internals:** none.

- [x] Edit each file.
- [x] The grep of Task 2 lists nothing outside `tasks/`.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit.
