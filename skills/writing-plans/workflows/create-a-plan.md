# Creating an Implementation Plan

A 5-phase process for writing an Argus implementation plan following the 7-section structure.

---

## Before You Start: Check Plan Type Routing

Before beginning Phase 1, determine whether this task needs a full plan or a mini-plan. Follow the routing decision tree in [SKILL.md](../SKILL.md#plan-type-routing):

1. Did the user explicitly say "big" or "small"? Use their answer.
2. Working on a PR? Check for the `plans` label: `gh pr view <number> --json labels --jq '.labels[].name' | grep -q '^plans$'`
3. No PR context? Estimate scope — if under ~1K LOC and single PR, use the mini-plan workflow instead.

**If this is a mini-plan**, stop here and follow [create-a-mini-plan.md](create-a-mini-plan.md) instead.

**If this is a full plan**, continue to Phase 1 below.

---

## Phase 1: Gather Context

**Entry:** You have a feature or change request that needs an implementation plan.

**Actions:**

1. **Read `docs/plans/INSTRUCTIONS.md` completely.** This is the authoritative source for plan structure and guidelines. Do not skip this step.

2. **Identify the scope.** What problem is being solved? What areas of the codebase are affected? Which layers (backend, frontend, client, database) are impacted?

3. **Inspect the codebase.** Use file-reading tools to examine relevant source files. Identify:
    - Current implementations that will change
    - Flask blueprints and service layer code in `argus/backend/`
    - Test files in `argus/backend/tests/` or `argus/client/tests/` related to the area
    - Svelte components in `frontend/` if UI is affected
    - Existing documentation in `docs/`

4. **Check MASTER.md for existing plans in the same domain.** Read `docs/plans/MASTER.md` and look for plans in the same domain that may overlap, depend on, or provide context for the new plan.

5. **Review reference plans.** Read at least one existing plan (e.g., `docs/plans/api_tests.md`) to calibrate quality expectations.

**Exit:** You understand the problem, have inspected relevant code, and know the plan structure.

---

## Phase 2: Write the Foundation Sections

**Entry:** Phase 1 complete. Context gathered, code inspected.

**Actions:**

1. **Write the Problem Statement.** Include:
    - The business or technical need
    - Specific pain points (with measurements if available)
    - Justification for why this work is necessary

2. **Write the Current State section.** This is the most research-intensive section:
    - Reference specific files, classes, and methods (verify they exist)
    - Describe how things currently work
    - Identify what needs to change
    - Document technical debt or limitations
    - **Never guess file names** — use tools to locate and verify

3. **Write the Goals section.** Define 3-6 specific, measurable objectives:
    - Number each goal with a bold title
    - Include measurable criteria where possible
    - Keep goals achievable within the plan scope

**Exit:** Problem Statement, Current State, and Goals sections are complete with verified code references.

---

## Phase 3: Design the Implementation

**Entry:** Phase 2 complete. Foundation sections written.

**Actions:**

1. **Break the work into phases.** Each phase should be:
    - Atomic and scoped to a single Pull Request where possible
    - Ordered by dependency (foundational work first)
    - Marked with Importance level (Critical/Important/Nice-to-have)

2. **Keep PRs small and focused.** Target ≤200 lines of code per PR. One logical change per PR — don't mix refactoring, new features, and config changes. Split large phases into sub-phases. Within a PR, use separate commits for logically distinct changes.

3. **For each phase, write:**
    - **Importance**: Critical/Important/Nice-to-have (see heuristics in templates)
    - **Description**: What will be implemented and why
    - **Dependencies**: Which phases must be complete first
    - **Deliverables**: Concrete outputs (files, features, configurations)
    - **Definition of Done**: Verifiable criteria using checkboxes — these serve as the success criteria for the phase

4. **Mark uncertain steps.** If a requirement or dependency is unclear, mark it as "Needs Investigation" rather than making assumptions.

5. **Include a documentation update phase.** Every plan should have a phase (or phase deliverable) covering:
    - Updated or new entries in `docs/` for user-facing changes
    - README or guide updates if the feature changes user workflows

6. **Include Argus-specific details:**
    - Backend impact (Flask blueprints, service layer in `argus/backend/`)
    - Frontend impact (Svelte components in `frontend/`)
    - Database changes (ScyllaDB models, schema migrations)
    - API changes (endpoint contracts, response formats)
    - Client library changes (`argus/client/`)

7. **Add separation lines** (`---`) between phases for readability.

**Exit:** Implementation Phases section complete with Definition of Done for each phase.

---

## Phase 4: Define Testing and Success

**Entry:** Phase 3 complete. Implementation phases designed.

**Actions:**

1. **Write Testing Requirements.** Testing should be planned upfront, not as an afterthought:
    - **Unit tests**: What to test in isolation, expected location in `argus/backend/tests/` or `argus/client/tests/`
    - **Integration tests**: What to verify end-to-end, requiring a running ScyllaDB instance
    - **Manual testing**: What requires human verification (UI behavior, API responses)

2. **Write Success Criteria.** Completing all Definition of Done items across phases constitutes success. Only add plan-level criteria that span multiple phases or cannot be captured in any single phase's DoD.

3. **Write Risk Mitigation.** For each risk:
    - **Name**: Short description of the risk
    - **Likelihood**: High/Medium/Low
    - **Impact**: What goes wrong
    - **Mitigation**: How to prevent or handle it

4. **Common Argus risks to consider:**
    - Database schema migration compatibility
    - Backward compatibility with existing client library users
    - Impact on CI/CD pipeline (GitHub Actions)
    - Frontend/backend API contract breakage

**Exit:** Testing Requirements, Success Criteria, and Risk Mitigation sections complete.

---

## Phase 5: Validate the Plan

**Entry:** Phase 4 complete. All 7 sections written.

**Actions:**

1. **Verify the 7-section structure.** Confirm all sections are present:
    - [ ] Problem Statement
    - [ ] Current State (with code references)
    - [ ] Goals
    - [ ] Implementation Phases (with DoD per phase)
    - [ ] Testing Requirements
    - [ ] Success Criteria
    - [ ] Risk Mitigation

2. **Verify all code references.** Every file path mentioned in Current State must point to a real file. Use file-reading tools to confirm.

3. **Check phase dependencies.** Ensure no phase references work from a later phase. Foundational work comes first.

4. **Check for open questions.** If any requirement is unclear, it should be marked as "Needs Investigation" — not assumed.

5. **Check Definition of Done criteria.** Each criterion should be verifiable (someone can check it off), not vague ("it works").

6. **Review against an existing plan.** Compare structure and quality with `docs/plans/api_tests.md` or another reference plan.

7. **Verify filename.** Plan should be saved as `docs/plans/<kebab-case-name>.md` with a descriptive name.

8. **Verify YAML frontmatter.** Confirm the plan starts with valid frontmatter containing `status`, `domain`, `created`, `last_updated`, and `owner` fields. See [frontmatter-fields.md](../references/frontmatter-fields.md) for valid values.

9. **Register in MASTER.md.** Add the plan to the correct domain table in `docs/plans/MASTER.md` with appropriate status.

10. **Add progress.json entry.** Add an entry to `docs/plans/progress.json` with the plan's id, title, file, domain, status, created date, phases_total, and phases_done.

11. **Run linting.** Execute `uv run ruff check` to verify no formatting issues.

**Exit:** All 7 sections present, code references verified, phases ordered correctly, plan saved in `docs/plans/`, registered in MASTER.md, and tracked in progress.json.
