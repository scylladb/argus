## Review Findings

The `qatools-sdlc` plugin holds the review policy and its three passes. This
standard holds the rules that shape a finding in this repository.

### Scope
The diff is the review boundary. Report a finding on a line the pull request
changes. A problem in unchanged code is a separate task.

Report the highest-confidence findings, up to five. Group the small ones into
one comment. A review of twenty minor findings hides the one that matters.

### Before You Report a Finding
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
6. **Leave migration code alone.** A fallback or a dual path inside a
   migration is deliberate.

`frontend/components.md` states the Svelte 5 rune semantics, and
`frontend/css.md` states the self-contained color pair. Apply both before you
report a frontend finding.

### A Pull Request Without a Task
A pull request that predates the flow carries no `tasks/<KEY>/`. Record the
outcome `not applicable — no task spec` for pass 3 and check the standards
only. Do not ask the author to write a spec for work that is already open.
