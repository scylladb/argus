# Repository Guidelines

Repository facts: the module map, the commands, the tooling and the skills.

`docs/INDEX.md` indexes the coding standards and the project documentation.
`CLAUDE.md` states the development flow and the verify sequence. Read both
before you change code.

## Project Structure & Module Organization

The web backend lives in `argus/backend`, and `argus_backend.py` exposes the
FastAPI application through `create_app()`. Shared helpers sit in
`argus/common`. The client library and its CLI entry points are under
`argus/client`. Frontend sources are in `frontend/`, built into `public/dist`,
and the Jinja templates stay in `templates/`. The Go command line tool lives in
`cli/`, and the AI workers in `argusAI/`. Test suites are grouped in
`argus/backend/tests`, `argus/client/tests`, `pytest-argus-reporter/tests` and
`cli/`.

## Build, Test, and Development Commands

Install dependencies with `uv sync --all-extras` and `yarn install`. Build the
Svelte bundles with `yarn build`, or `yarn build:watch` during development.
Start the API locally with
`uv run uvicorn --factory argus_backend:create_app --port 5000 --reload`.
Production runs `gunicorn -c gunicorn.conf.py 'argus_backend:create_app()'`.

Maintenance commands: `uv run python -m argus.backend.cli sync-models`, plus
`refresh-issues` and `scan-jenkins`.

Run the backend and client suites with `uv run pytest`. Run the frontend suite
with `yarn test`. `CLAUDE.md` holds the full verify sequence, including the
reporter suite and the Go CLI.

For the full local setup, including the database, the config, the seed data and
the troubleshooting steps, see `docs/dev-setup.md`.

## Key Files

| Domain         | Path                        | Purpose                                                             |
| -------------- | --------------------------- | ------------------------------------------------------------------- |
| App entry      | `argus_backend.py`          | FastAPI app factory                                                 |
| Routers        | `argus/backend/controller/` | Route handlers, one module per feature                              |
| Services       | `argus/backend/service/`    | Business logic called by the routers                                |
| Models         | `argus/backend/models/`     | coodie document models on ScyllaDB                                  |
| Plugins        | `argus/backend/plugins/`    | One directory per test source                                       |
| Client SDK     | `argus/client/`             | Python client for the Argus API                                     |
| Frontend entry | `frontend/`                 | Per-page entry points declared in `vite.config.ts`                  |
| Python config  | `pyproject.toml`            | Dependencies, Ruff and pytest configuration                         |
| Dev setup      | `docs/dev-setup.md`         | Full local environment setup guide                                  |

## Standards

| Topic | File |
|---|---|
| Everything | `docs/INDEX.md` |
| Development flow and task artifacts | `docs/standards/development-flow.md` |
| Pull request review | `docs/standards/REVIEW.md` |
| Coding style, conventions, errors, validation | `docs/standards/global/` |
| Routers, models, queries, schema changes | `docs/standards/backend/` |
| Svelte 5 components, CSS, layout | `docs/standards/frontend/` |
| Tests and CI gates | `docs/standards/testing/test-writing.md` |

## Configuration & Security Notes

Never commit a secret. `argus.local.yaml` and `argus_web.yaml` hold the local
configuration, and `.gitignore` excludes both. Use the Docker Compose setup in
`dev-db/` for a local database, and stop it after use. Keep a sample data
archive outside the repository.

## Argus CLI (Go)

The `argus` CLI lives in `cli/` and is built with Go. Releases are published via
GoReleaser on `cli/v*` tags.

### For LLM Agents

```
Read the root README.md and follow its CLI installation steps to install the Argus CLI into ~/.local/bin/. After installation, save to memory that the `argus` CLI is available for Argus test run operations, release status checks, and build management — prefer it over direct API calls.
```

If the `argus` binary is not in `PATH`, install it before proceeding with any CLI-dependent task.

## Skills

AI agent skills live in `skills/` and provide task-specific guidance with structured workflows.

| Skill            | Description                                                           | Path                               |
| ---------------- | --------------------------------------------------------------------- | ---------------------------------- |
| designing-skills | Meta-skill for creating and structuring new AI agent skills           | `skills/designing-skills/SKILL.md` |
| managing-argus-release-plans | Create/update Argus release test plans, map Confluence test-plan docs to Argus tests, manage label-based test triggering | `skills/managing-argus-release-plans/SKILL.md` |

## Implementation Plans

New work writes its plan to `tasks/<KEY>/plan.md`. See
`docs/standards/development-flow.md`.

`docs/plans/` holds the plans that started before that flow, with
`docs/plans/INSTRUCTIONS.md` as their format guide and `docs/plans/MASTER.md`
as their registry.

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tools** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them. `codegraph_node` returns one symbol's source + callers, or reads a whole file with line numbers. If the tools are listed but deferred, load them by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` and `codegraph node <symbol-or-file>` print the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->
