# Argus Plan Templates

Templates and examples for each section of an Argus implementation plan, based on the 7-section structure defined in `docs/plans/INSTRUCTIONS.md`.

---

## Complete Plan Skeleton

Use this as a starting point for any new plan:

```markdown
---
status: draft
domain: <domain-key>
created: <YYYY-MM-DD>
last_updated: <YYYY-MM-DD>
owner: null
---

# <Feature/Change Name> Plan

## Problem Statement

<What needs to change and why. Include business/technical need, pain points, and justification.>

## Current State

<Analysis of existing implementation. MUST reference specific files, classes, and methods.>

### <Subsystem A>

- `path/to/file.py` — <What it does, what needs to change>
- `path/to/other.py:ClassName` — <Current behavior>

### What's Missing

- <Gap 1>
- <Gap 2>

## Goals

1. **<Goal 1>**: <Measurable outcome>
2. **<Goal 2>**: <Measurable outcome>
3. **<Goal 3>**: <Measurable outcome>

## Implementation Phases

### Phase 1: <Name>

**Importance**: Critical/Important/Nice-to-have
**Description**: <What will be implemented>

**Deliverables**:

- <Specific output 1>
- <Specific output 2>

**Definition of Done**:

- [ ] <Criterion 1>
- [ ] <Criterion 2>

---

### Phase 2: <Name>

**Importance**: Critical/Important/Nice-to-have
**Description**: <What will be implemented>

**Dependencies**: Phase 1

**Deliverables**:

- <Specific output>

**Definition of Done**:

- [ ] <Criterion>

## Testing Requirements

### Unit Tests

- <What to test at unit level>

### Integration Tests

- <What to verify end-to-end>

### Manual Testing

- <What requires human verification>

## Success Criteria

Completing all Definition of Done items across phases constitutes success. Add plan-level criteria only if they go beyond individual phase DoD:

1. <Plan-level measurable outcome not captured in any single phase DoD>

## Risk Mitigation

### Risk: <Risk Name>

**Likelihood**: High/Medium/Low
**Impact**: <What goes wrong>
**Mitigation**: <How to prevent or handle it>

## Related Plans

<Optional — only include if actual dependencies or overlaps exist with other plans.>

- [<related-plan-name>.md](<related-plan-name>.md) — <relationship description>

## PR History

| Phase   | PR  | Status      |
| ------- | --- | ----------- |
| Phase 1 | —   | Not started |
```

---

## Section-by-Section Guidance

### 1. Problem Statement

**Purpose**: Explain what needs to change and why.

**Must include**:

- Business or technical need driving the change
- Pain points with the current situation
- Justification for why this work is necessary

**Good example** (from `docs/plans/api_tests.md`):

```markdown
## Problem Statement

Argus is planning a major refactor: moving from Flask to FastAPI and replacing
CQLEngine with coodie. To guarantee no regressions, every public API endpoint
must have an integration test that exercises the endpoint over HTTP, asserts on
JSON response structure, and requires minimal changes after migration.
```

**Bad example**:

```markdown
## Problem Statement

We need to add more tests.
```

The bad example lacks specifics: no measurable problem, no root cause, no justification.

---

### 2. Current State

**Purpose**: Analyze the existing implementation with specific code references.

**Critical rule**: You MUST use file-reading tools to inspect actual code. Do not guess or hallucinate file names.

**Must include**:

- References to specific files, classes, and methods
- Description of how things currently work
- What needs to change
- Technical debt or limitations

**Pattern for referencing code**:

```markdown
### Backend Services

- `argus/backend/service/results_service.py` — Handles test result CRUD operations
- `argus/backend/controller/api.py` — REST endpoint definitions
- `argus/backend/db/models.py` — CQLEngine model definitions
```

---

### 3. Goals

**Purpose**: Define specific, measurable objectives.

**Rules**:

- Number each goal with bold title
- Make goals measurable ("reduce by 90%", "cover 100% of endpoints")
- Keep goals focused and achievable within the plan scope

**Good example**:

```markdown
## Goals

1. **100% endpoint coverage** — every public API endpoint has at least one integration test
2. **Zero CQLEngine assertions** — tests verify JSON responses only, not ORM objects
3. **Migration-safe tests** — tests require no changes after Flask-to-FastAPI migration
```

---

### 4. Implementation Phases

**Purpose**: Break the work into atomic, PR-scoped steps.

**Rules**:

- Phases should be scoped to single Pull Requests where possible
- Large phases should be split into separate commits within the PR for easier review
- Order by dependency: foundational work first
- Each phase needs Importance, Description, Deliverables, and Definition of Done
- Mark unclear steps as "Needs Investigation"
- Definition of Done items should be verifiable and serve as the success criteria for the phase

**Importance levels** — use these to indicate which phases are essential vs. optional:

| Level            | Meaning                                       | Heuristic                                       |
| ---------------- | --------------------------------------------- | ----------------------------------------------- |
| **Critical**     | Must be completed for the plan to succeed     | Blocks other phases or is the core deliverable  |
| **Important**    | Significantly improves the outcome            | Adds meaningful value but plan works without it |
| **Nice-to-have** | Can be deferred or dropped if time is limited | Polish, optimization, or stretch goals          |

**PR sizing rules** — based on industry best practices:

- **Target ≤200 lines of code per PR.** Research shows PRs over 200 lines receive lower-quality reviews
- **One logical change per PR.** Do not mix refactoring, new features, and config changes in a single PR
- **Split large phases into sub-phases.** If a phase exceeds ~200 lines, break it into multiple PRs that each stand alone
- **Use separate commits for distinct changes within a PR** (e.g., one commit for refactoring, another for new functionality, another for tests)
- **Each PR must leave the codebase in a working state.** No broken intermediate states
- **Prep work goes in separate PRs.** Pre-refactoring, dependency upgrades, or configuration changes should be submitted before the main feature PR

**Phase template**:

```markdown
### Phase N: <Name>

**Importance**: Critical/Important/Nice-to-have
**Description**: <What will be implemented and why>

**Dependencies**: <Which phases must be complete first>

**Deliverables**:

- <Concrete output 1>
- <Concrete output 2>

**Adaptation Notes**: <Optional: explain tradeoffs, deviations from the original design,
or context that helps reviewers understand why this phase differs from initial expectations>

**Definition of Done**:

- [ ] <Verifiable criterion 1>
- [ ] <Verifiable criterion 2>
```

---

### 5. Testing Requirements

**Purpose**: Define what testing is needed to verify each phase. Think about testing upfront, not as an afterthought.

**Must include**:

- Unit tests the LLM can write and run
- Integration testing needs (what to verify end-to-end)
- Manual testing procedures (what requires human verification)

**Pattern**:

```markdown
## Testing Requirements

### Unit Tests

- Test service layer with mocked database calls
- Test API endpoint response formats
- Run with: `uv run pytest argus/backend/tests/ -v`

### Integration Tests

- Test with Docker-based ScyllaDB instance (see `dev-db/`)
- Verify end-to-end API calls return correct data
- Run with: `uv run pytest argus/backend/tests/ --docker-required`

### Manual Testing

- Verify UI renders correctly after API changes
- Check release dashboard loads within acceptable time
```

---

### 6. Success Criteria

**Purpose**: Confirm overall plan completion. Completing all Definition of Done items across phases constitutes success.

**Rules**:

- Avoid duplicating DoD items — reference them instead
- Only add plan-level criteria that span multiple phases or cannot be captured in a single phase's DoD
- If all DoD items cover success fully, this section can simply state that

**Good example**:

```markdown
## Success Criteria

All Definition of Done items across phases are met. Additionally:

1. No regressions in existing unit tests
2. API documentation updated in `docs/api_usage.md`
```

---

### 7. Risk Mitigation

**Purpose**: Identify risks and mitigation strategies.

**Must include**:

- Potential blockers
- Rollback strategies
- Dependencies on external systems
- Compatibility concerns

**Pattern**:

```markdown
### Risk: <Name>

**Likelihood**: High/Medium/Low
**Impact**: <What goes wrong if this happens>
**Mitigation**: <How to prevent it or what to do if it happens>
```

---

## Argus-Specific Conventions for Plans

| Convention       | Rule                                                                             |
| ---------------- | -------------------------------------------------------------------------------- |
| File location    | Store in `docs/plans/` directory                                                 |
| Filename         | kebab-case, descriptive (e.g., `api-tests.md`)                                   |
| Backend details  | Document impact on Flask blueprints, service layer, database models              |
| Frontend details | Document impact on Svelte components, state management                           |
| Test commands    | Use `uv run pytest argus/backend/tests/` and `uv run pytest argus/client/tests/` |
| Linting          | Include `uv run ruff check` in testing steps                                     |
| Code references  | Always point to real files — verify with file-reading tools                      |
| Open questions   | Mark unclear requirements as "Needs Investigation"                               |
| Archiving        | Move completed plans to `docs/plans/archive/`                                    |

---

## Existing Plan Examples

Reference these for style and quality:

| Plan                              | Type                  | Demonstrates                                             |
| --------------------------------- | --------------------- | -------------------------------------------------------- |
| `docs/plans/api_tests.md`         | Integration testing   | Measurable goals, phased approach, migration-safe design |
| `docs/plans/ssh-tunnel-design.md` | Infrastructure design | Security considerations, detailed architecture           |
