# <KEY> — implementation plan

**Spec:** `tasks/<KEY>/spec.md`, or `tasks/<KEY>/rca.md` for a bug fix

## Constraints

The project-wide rules that every task below inherits.

## Task 1 — <name>

**Files:**
- Create: `<path>`
- Modify: `<path>:<lines>`
- Test: `<path>`

**Internals:** the functions, the classes, and the fields this task adds.
Omit the line when the task adds none.

- [ ] Write the failing test.
- [ ] Run it and confirm the failure.
- [ ] Write the smallest change that passes it.
- [ ] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [ ] Commit.
