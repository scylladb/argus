# Plan Frontmatter Fields

Every plan file in `docs/plans/` must start with YAML frontmatter. This document defines the fields, valid values, and conventions.

---

## Required Fields

```yaml
---
status: draft
domain: backend
created: 2026-01-15
last_updated: 2026-03-15
owner: null
---
```

### `status`

Current lifecycle state of the plan.

| Value         | Meaning                                   | When to Use                                             |
| ------------- | ----------------------------------------- | ------------------------------------------------------- |
| `draft`       | Plan written, not yet started             | Default for new plans                                   |
| `approved`    | Reviewed and approved for implementation  | After team review/sign-off                              |
| `in_progress` | Active implementation underway            | At least one phase has started                          |
| `blocked`     | Implementation blocked                    | External dependency or issue prevents progress          |
| `complete`    | All phases implemented and verified       | All DoD items checked off                               |
| `pending_pr`  | Plan exists in an open PR, not yet merged | Used only in MASTER.md/progress.json for unmerged plans |

### `domain`

The functional area of the codebase this plan affects. Must be one of:

| Domain Key       | Covers                                           | Codebase Areas                                                          |
| ---------------- | ------------------------------------------------ | ----------------------------------------------------------------------- |
| `backend`        | Flask/FastAPI services, blueprints, server logic | `argus/backend/`                                                        |
| `frontend`       | Svelte components, UI state, styles              | `frontend/`                                                             |
| `api`            | REST endpoints, request/response contracts       | `argus/backend/controller/`, client-server interface                    |
| `database`       | ScyllaDB/Cassandra models, migrations, schema    | `argus/backend/db/`                                                     |
| `client`         | Python client library                            | `argus/client/`                                                         |
| `testing`        | Test infrastructure, fixtures, reporters         | `argus/backend/tests/`, `argus/client/tests/`, `pytest-argus-reporter/` |
| `ci-cd`          | GitHub Actions workflows, Docker builds          | `.github/workflows/`, `docker/`                                         |
| `infrastructure` | Dev tooling, monitoring, operational concerns    | `dev-db/`, `scripts/`, deployment                                       |

### `created`

Date the plan was first written. Format: `YYYY-MM-DD`. Derive from `git log --diff-filter=A` if adding frontmatter to an existing plan.

### `last_updated`

Date of the most recent substantive change. Format: `YYYY-MM-DD`. Update this when modifying plan content or status.

### `owner`

GitHub username of the person responsible for driving implementation. Set to `null` if unassigned.

---

## Corresponding Tracking Files

When creating or updating a plan's frontmatter, also update:

1. **`docs/plans/MASTER.md`** — Add/update the plan's row in the correct domain table
2. **`docs/plans/progress.json`** — Add/update the plan's entry with matching status

See [update-plan-status.md](../workflows/update-plan-status.md) for the step-by-step workflow.
