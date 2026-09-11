---
description: "Review a PR with project-specific false-positive filtering on top of standard review"
argument-hint: "[PR number or URL]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Agent"]
---

# Argus PR Review

Review pull request: "$ARGUMENTS"

This command layers project-specific rules on top of the standard code review workflow. It does NOT replace the built-in review agents — it provides context they need to avoid false positives specific to this codebase.

## Step 1: Gather PR context

Run these in parallel:
```bash
gh pr diff "$ARGUMENTS"
gh pr view "$ARGUMENTS" --json number,title,body,files,baseRefName,headRefOid
gh api repos/scylladb/argus/issues/$(echo "$ARGUMENTS" | grep -oE '[0-9]+')/comments
gh api repos/scylladb/argus/pulls/$(echo "$ARGUMENTS" | grep -oE '[0-9]+')/comments
```

Record:
- The **exact list of changed files** — this is the review boundary
- Any **demos, screenshots, or staging URLs** in the PR body or comments
- Any **existing review comments** from human reviewers

## Step 2: Read project review rules

Read `docs/standards/REVIEW.md`. It holds the three review passes and the checks that remove a false report in this repository. These rules are mandatory for this review.

## Step 3: Launch the standard code-review agents

Use the `code-review:code-review` skill's methodology but inject these constraints into every agent prompt:

**Scope constraint:** "You may ONLY flag issues in these files: [list from step 1]. Do not read or comment on any other files."

**Review passes:** work through the three passes in `docs/standards/REVIEW.md` — bugs and logic, security, compliance against `tasks/<KEY>/spec.md` — and state an outcome for each one.

For the third pass, take the Jira key from the `Fixes ARGUS-<n>` line in the PR body (step 1) or from a `tasks/<KEY>/` path in the diff, then read that spec. When neither exists, the pull request predates the flow: report the third outcome as `not applicable — no task spec` and check the standards only.

**False-positive filters:** apply every check in the "Before you report a finding" section of `docs/standards/REVIEW.md`. Inject them into each agent prompt verbatim. In addition:

1. **Diff-only rule.** Only flag issues on changed lines. Pre-existing issues in unchanged code are out of scope.
2. **3-5 findings max.** If you have more, keep only the highest-confidence ones.

## Step 4: Post-filter all findings

Before presenting results, run each finding through this checklist:

- [ ] Is the flagged file in the PR diff?
- [ ] Is the flagged line actually changed in this PR?
- [ ] Did I read the full surrounding context (not just the flagged line)?
- [ ] Can I describe a concrete, realistic failure scenario?
- [ ] Does the PR demo/screenshot contradict my finding?
- [ ] Is this pattern used elsewhere in the codebase (grep for it)?
- [ ] Has a human reviewer already flagged this?
- [ ] Am I applying the correct framework version's semantics?

**If any check fails, drop the finding.**

## Step 5: Format output

```markdown
# PR Review: [title]

**Reviewed files:** [N files from diff]
**Existing review comments noted:** [count, if any]

## Issues (sorted by confidence)
1. **[file:line]** (confidence: N/100) — Description.
   **Reproduction:** How this fails in practice.
   **Fix:** Concrete suggestion.

[... up to 5 max ...]

## Suggestions (optional, low confidence)
- Brief one-liners only

## Strengths
- What the PR does well

## Systemic notes (if any)
- At most 1-2 one-liners about patterns noticed outside the diff, clearly labeled as future work
```

If no issues meet the confidence threshold:
```markdown
# PR Review: [title]

No significant issues found. Reviewed [N] files from the diff.

## Strengths
- ...
```
