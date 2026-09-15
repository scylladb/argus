# ARGUS-230 — implementation plan

**Spec:** `tasks/ARGUS-230/spec.md`

## Constraints

- Write every document in Simplified Technical English, flavored mode.
- Keep no record of a dropped decision. Rewrite a stale sentence, do not
  annotate it.
- Write no test for the content of a document.
- Take the zeus text at the merge of scylladb/zeus pull request 193. Keep the
  Argus-specific sentences the spec names.
- Run the verify sequence from the `Commands` section of `CLAUDE.md` before
  each commit.

## Task 1 — The templates

**Files:**
- Create: `tasks/templates/rca.md`
- Modify: `tasks/templates/spec.md`
- Modify: `tasks/templates/plan.md`

- [x] Write the rca template from the zeus file, verbatim.
- [x] Replace the spec template with the zeus file, verbatim.
- [x] Replace the plan template with the zeus file, verbatim.
- [x] Run the verify sequence.
- [x] Commit.

## Task 2 — The flow and the review policy

**Files:**
- Modify: `docs/standards/development-flow.md`, the stage table, the order of
  commits, Stage 2, Stage 3, the spike path, a new "The bug fix path" section
- Modify: `docs/standards/REVIEW.md`, Pass 3

- [ ] Stage table: name `rca.md` for a bug at Stage 2, with its approver.
- [ ] Order of commits: name the bug fix path as the second exception.
- [ ] Stage 2: point at the template, state what carries the design decision
      and what bounds the scope, send a bug to the bug fix path.
- [ ] Stage 3: state that the plan carries the files, the internals, and the
      tests. Keep the `docs/plans/` paragraph.
- [ ] Spike path: state that the diff carries them and the spec keeps the
      template shape.
- [ ] Add the bug fix path section after the spike path.
- [ ] Pass 3: read `spec.md` or `rca.md`, add the contract question, the two
      rca questions, and the skip statement check.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 3 — The agent instructions and the index

**Files:**
- Modify: `CLAUDE.md`, Task Artifacts
- Modify: `docs/INDEX.md`, the Development Flow and Review Policy summaries

- [ ] Add `rca.md` to the artifact list and the gates, add the spec and plan
      split, the bug fix path, and the spike variant for a bug. Keep the
      `AGENTS.md` line and the `docs/plans/` paragraph.
- [ ] Rewrite the two summaries to match the documents. Keep the Argus
      sentences about the Svelte 5 and CSS checks.
- [ ] Run the verify sequence.
- [ ] Commit.
