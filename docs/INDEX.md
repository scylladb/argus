# Documentation Index

**IMPORTANT**: Read this file at the beginning of any development task to understand available documentation and standards.

## Quick Reference

### Project Documentation
Project-level documentation covering vision, goals, architecture, and technology choices.

### Technical Standards
Coding standards, conventions, and best practices organized by domain.

---

## Project Documentation

Located in `docs/project/`

### Vision (`project/vision.md`)
What Argus is and who uses it: a test tracking system for automated pipelines that hold long-running resources. Covers the current state (Python 3.12 with FastAPI on ScyllaDB, a Svelte 5 frontend, a Go CLI, Python AI workers), the purpose, the five test sources that report through the plugin layer, the three consumers, and where to read the current direction.

### Tech Stack (`project/tech-stack.md`)
Languages (Python 3.12, TypeScript and JavaScript, Go), backend and frontend frameworks, testing frameworks, ScyllaDB with the coodie document mapper, build tools and package management, containers, CI, hosting, linting and formatting, type checking, key dependencies, version management.

### Architecture (`project/architecture.md`)
Layered web application with a plugin layer for test sources. Covers the web backend layers, the plugin contract, the frontend, the command line tool, the AI workers, the client library, data flow, data model rules, external integrations, configuration and deployment.

### Roadmap (`project/roadmap.md`)
The active plans from `docs/plans/MASTER.md`, and the known debt: lint coverage, the Python version floor, the Docker requirement in the test suite, the legacy Svelte imports, an unreferenced bundle, and hand-written API documentation.

---

## Technical Standards

### Process Standards

Located in `docs/standards/`

#### Development Flow (`standards/development-flow.md`)
The six stages of work in this repository: the artifact each stage produces, its path under `tasks/<KEY>/`, and its approver. Covers the commit order that gates each stage on the artifact before it, the spike path for code that exists before any artifact does, and the Jira key as the join between the task directory and the pull request.

#### Review Policy (`standards/REVIEW.md`)
The three review passes applied to every pull request: bugs and logic, security, and compliance against the task spec. Also holds the checks that remove a false report, including the Svelte 5 rune semantics and the self-contained CSS color pair. A review states an outcome for every pass. Findings do not block a merge. A maintainer approves it.

### Global Standards

Located in `docs/standards/global/`

These standards apply across the entire codebase, regardless of frontend/backend context.

#### Coding Style (`standards/global/coding-style.md`)
Python 3.12 target against a `py310` linter floor, 4-space indentation and a 120-character line width, the reach of Ruff (`exclude = ["argus/"]` leaves the web backend unchecked), the explicit preview rule set, the pre-commit hooks, the installed but unrun ESLint, Prettier and svelte-check, Python and frontend naming, no dead code, and no backward compatibility without a stated need.

#### Commenting (`standards/global/commenting.md`)
Let the code speak, comment sparingly, no change-history comments.

#### Conventions (`standards/global/conventions.md`)
Layer ownership for a new file, the documents to update on an architecture change, the commitlint rules enforced at `commit-msg` (type enum, required scope, header and body limits), pull request format with the `Fixes ARGUS-<n>` closing line, the `ai-assisted` label, SHA-pinned actions, committed lockfiles in all three ecosystems, uv as the only Python tool runner, secrets in gitignored config files, and non-blocking review feedback tracked as a follow-up issue.

#### Error Handling (`standards/global/error-handling.md`)
Typed exceptions (`APIException`, `DataValidationError`, `<Domain>Error`) with `raise ... from`, no blind except, raising instead of returning an error dictionary, handling at the boundary, failing fast because the database enforces nothing, graceful degradation when Jira, GitHub, Jenkins or the AI worker fails, retry with backoff, and resource cleanup.

#### Minimal Implementation (`standards/global/minimal-implementation.md`)
Build what you need, clear purpose, delete exploration artifacts, no future stubs, no speculative abstractions, review before commit, unused code is debt.

#### Validation (`standards/global/validation.md`)
The database enforces nothing, so every rule lives in the application: Pydantic at the router boundary, business rules in the service, uniqueness through a secondary index read, reference checks before a write, escaping user content before a template renders it, and the same rule at every entry point.

---

### Backend Standards

Located in `docs/standards/backend/`

#### API Design (`standards/backend/api.md`)
The router, service and model layers and what belongs in each, one `APIRouter` per feature with an explicit prefix and an `api.<module>.<function>` route name, `Depends(api_current_user)` on every API route, the `APIResponse` status and response shape, Pydantic request bodies, raising `APIException` and `DataValidationError` instead of returning an error, and the disabled OpenAPI schema.

#### Models (`standards/backend/models.md`)
The coodie document mapper (`Document`, `UserType`, `PrimaryKey`, `ClusteringKey`, `Indexed`), explicit versioned table names in `class Settings`, designing the partition key from the read, what ScyllaDB does not give you (no joins, no foreign keys, no unique constraints) and the three rules that follow, the NULL collection trap, the annotated types, `sync-models`, and plugin-owned models.

#### Queries (`standards/backend/queries.md`)
Reading through the mapper with `find()`, designing the partition key for the read, the cost of `allow_filtering()` and where it stays acceptable, one read per screen, avoiding a query inside a loop, restricting columns on a wide row, application-side uniqueness, and precomputing an expensive aggregate into a snapshot table.

#### Schema and Data Changes (`standards/backend/migrations.md`)
The models are the schema and `sync-models` applies them, additive changes first, a new versioned table for a breaking change, one-off data jobs as dated scripts under `scripts/migration/`, zero-downtime constraints under four workers, and never editing a script that already ran.

---

### Frontend Standards

Located in `docs/standards/frontend/`

#### Components (`standards/frontend/components.md`)
Svelte 5 runes as the default (`$props`, `$state`, `$derived`, `$effect`), the deep reactive proxy on a `$state` array, never reassigning a `$derived` variable, reaching the DOM through `bind:this` or an action instead of `querySelector`, composition over imperative DOM updates, keeping data transformations in the script block, the `frontend/` directory layout with `Stores/` and `Common/`, adding an entry point to `vite.config.ts` with its Jinja template, and typed props.

#### CSS (`standards/frontend/css.md`)
Bootstrap 5 first, the self-contained `background-color` and `color` pair on a badge or an alert, scoping a rule to its component, reusing the Bootstrap scales, and deleting unused rules.

#### Responsive Layout (`standards/frontend/responsive.md`)
Argus as a dense desktop dashboard: the Bootstrap grid and breakpoints, letting a wide table scroll, fluid containers, relative units, readable type, content priority, and checking two widths before a pull request.

#### Accessibility (`standards/frontend/accessibility.md`)
Semantic HTML, keyboard navigation, color contrast, alt text and labels, screen reader testing, ARIA when needed, heading structure, focus management.

---

### Testing Standards

Located in `docs/standards/testing/`

#### Test Writing (`standards/testing/test-writing.md`)
Testing behavior, clear names, mandatory unit tests, risk-based depth, where each suite lives and which runner covers it, the two `norecursedirs` collection traps (the reporter suite needs nox, and `argus/backend/service` collects nothing), the Docker requirement behind the `docker_required` marker, shared fixtures in `conftest.py`, which dependencies to mock, Vitest in jsdom for the frontend, `-race` for the Go CLI, no tests for Markdown content, and the CI quality gates.

---

### CLI Standards

None yet. The Go CLI under `cli/` follows the conventions in its own
`Makefile` and the golangci-lint defaults that `cli-test.yml` runs. Add a
standard here when the team settles one.

---

## Reference Documents

Located in `docs/`. Single-topic notes, outside the standards.

- `dev-setup.md` — the local environment, the database, the config and the seed data.
- `deployment.md` — the production deployment procedure.
- `api_usage.md` — the REST API, written by hand.
- `generic_results.md` — the generic results submission format.
- `argus_status_page.md` — the status page.
- `pypi-guide.md` — publishing the Python packages.
- `config/` — the nginx, systemd and logrotate files.
- `plans/` — the plans that started before the development flow. See `plans/INSTRUCTIONS.md`.

---

## How to Use This Documentation

1. **Start Here**: Always read this INDEX.md first to understand what documentation exists
2. **Project Context**: Read relevant project documentation before starting work
3. **Standards**: This index only points to the standards — open and follow the specific standard files relevant to your task; do not rely on the index alone
4. **Keep Updated**: Update documentation when making significant changes

## Updating Documentation

- Project documentation should be updated when goals, tech stack, or architecture changes
- Technical standards should be updated when team conventions evolve
- Always update INDEX.md when adding, removing, or significantly changing documentation
