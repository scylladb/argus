# Implementation Plan Instructions

This document is the **authoritative source** for how implementation plans are written and maintained in the Argus repository. If a skill or workflow conflicts with this file, follow this file.

## Plan Types

Argus supports two plan formats:

| Aspect        | Full Plan                           | Mini-Plan                                  |
| ------------- | ----------------------------------- | ------------------------------------------ |
| Sections      | 7                                   | 4 (Problem, Approach, Files, Verification) |
| Frontmatter   | Required                            | None                                       |
| MASTER.md     | Required                            | None                                       |
| progress.json | Required                            | None                                       |
| Location      | `docs/plans/`                       | `docs/plans/mini-plans/`                   |
| Filename      | `kebab-case-name.md`                | `YYYY-MM-DD-kebab-case-name.md`            |
| Lifecycle     | Tracked until archived              | Disposable after PR merge or 30 days       |
| Use when      | Multi-phase, 1K+ LOC, cross-cutting | Single PR, under ~1K LOC                   |

## The 7-Section Structure (Full Plans)

Every full implementation plan follows this structure:

### 1. Problem Statement

What problem are we solving, and why now? Include measurable pain points — "slow" is not a problem statement; "API response time exceeds 5s for release dashboard queries" is.

### 2. Current State

What exists today in the codebase. **Every file path, class, and method referenced must be verified against the actual repository.** Do not guess or hallucinate paths.

### 3. Goals

Numbered, measurable objectives. Each goal must have a verifiable condition — a number, threshold, or concrete outcome.

### 4. Implementation Phases

How to get from Current State to Goals. Each phase:

- Is scoped to a **single Pull Request**
- Targets **≤200 lines of changed code**
- Has an **Importance** level: Critical / Important / Nice-to-have
- Has a **Definition of Done** checklist with concrete, verifiable items

Order phases by dependency — foundational changes before features that depend on them.

### 5. Testing Requirements

How each phase will be verified. Cover:

- **Unit tests**: pytest tests in `argus/backend/tests/` or `argus/client/tests/`
- **Integration tests**: tests requiring a running ScyllaDB instance
- **Manual testing**: steps to verify UI or API behavior by hand

### 6. Success Criteria

How to know the entire plan is done. Reference Definition of Done items from phases — do not duplicate them. Add plan-level criteria only when phases individually succeeding doesn't guarantee overall success.

### 7. Risk Mitigation

What could go wrong. For each risk, specify:

- **Likelihood**: Low / Medium / High
- **Impact**: Low / Medium / High
- **Mitigation**: Concrete steps to reduce or eliminate the risk

## YAML Frontmatter

Every full plan file must start with YAML frontmatter:

```yaml
---
status: draft # draft | approved | in_progress | blocked | complete
domain: backend # See domain taxonomy below
created: 2025-01-15
last_updated: 2025-01-15
owner: github-username # or null
---
```

### Domain Taxonomy

| Domain           | Scope                                                                |
| ---------------- | -------------------------------------------------------------------- |
| `backend`        | Flask/FastAPI services, blueprints, server logic in `argus/backend/` |
| `frontend`       | Svelte components, UI state, styles in `frontend/`                   |
| `api`            | REST endpoints, request/response contracts, client-server interface  |
| `database`       | ScyllaDB/Cassandra models, migrations, schema changes                |
| `client`         | Python client library in `argus/client/`                             |
| `testing`        | Test infrastructure, fixtures, reporters                             |
| `ci-cd`          | GitHub Actions workflows, Docker builds, deployment                  |
| `infrastructure` | Dev tooling, monitoring, operational concerns                        |

## Plan File Conventions

| Convention | Rule                                           |
| ---------- | ---------------------------------------------- |
| Location   | `docs/plans/` directory                        |
| Filename   | kebab-case, descriptive (e.g., `api-tests.md`) |
| Format     | Markdown with `# Plan Title` as first heading  |
| Archiving  | Move completed plans to `docs/plans/archive/`  |

## Tracking

Every full plan must be:

1. Registered in `docs/plans/MASTER.md` under the correct domain
2. Added to `docs/plans/progress.json` with plan metadata

Mini-plans are **not** registered in either tracking file.

## Argus-Specific Considerations

When writing plans for Argus, consider:

| Area              | What to Include                                                             |
| ----------------- | --------------------------------------------------------------------------- |
| **Backend**       | Flask blueprints in `argus/backend/`, service layer patterns                |
| **Frontend**      | Svelte 5 components using rune APIs, bundled via Rollup                     |
| **Database**      | ScyllaDB/Cassandra models via CQLEngine (migrating to coodie)               |
| **API**           | REST endpoints, JSON response contracts, httpx-based testing                |
| **Client**        | Python client in `argus/client/`, CLI in `cli/`                             |
| **CI/CD**         | GitHub Actions in `.github/workflows/`                                      |
| **Testing**       | pytest in `argus/backend/tests/` and `argus/client/tests/`, Docker-based DB |
| **Related Plans** | Check MASTER.md for existing plans in the same domain                       |
