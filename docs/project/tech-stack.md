# Technology Stack

This document describes the technology choices for Argus.

Argus is a test tracking system. It gives observability into automated test
pipelines that use long-running resources.

## Languages

### Python 3.12

- **Usage**: about 283 files. The web backend, the client SDK, the AI workers
  and the maintenance scripts.
- **Floor**: `pyproject.toml` sets `requires-python = ">=3.10"` and Ruff sets
  `target-version = "py310"`. All three CI workflows pin 3.12.
- **Style**: 4-space indentation and a 120-character line width.

### TypeScript and JavaScript

- **Usage**: 288 files under `frontend/` — 212 Svelte components, 57 JavaScript
  modules and 19 TypeScript modules.
- **Node**: CI pins Node 22.

### Go 1.25.4

- **Usage**: the `argus` command line tool under `cli/`.
- **Release**: GoReleaser publishes per-platform binaries on `cli/v*` tags.

## Frameworks

### Backend

| Component | Version | Purpose |
|---|---|---|
| FastAPI | >= 0.141.1 | HTTP application. `argus_backend.py` exposes `create_app()`. |
| Uvicorn | >= 0.40.0 | ASGI worker class. |
| Gunicorn | >= 26.0.0 | Process manager. `gunicorn.conf.py` runs 4 workers on a unix socket. |
| Jinja2 | >= 3.1.0 | Server-side templates under `templates/`. |

`argus/backend/rendering.py` supplies the helpers the `.j2` templates expect:
`url_for`, `flash` and session access. It escapes only bare markup extensions,
because the templates assume an unescaped environment.

The OpenAPI schema is switched off. `create_app()` sets `openapi_url=None`.

### Frontend

| Component | Version | Purpose |
|---|---|---|
| Svelte | 5.46.4 | Component framework. Runes are on by default. |
| Vite | 8.0.0 | Build tool. `vite.config.ts` declares 25 entry points. |
| Rolldown | bundled with Vite | Bundler. `vite.config.ts` uses `rolldownOptions`. |
| Bootstrap | 5.x | Layout and components. |

206 of 212 components use runes. 45 files import `svelte/legacy`.

Each entry point maps to a Jinja template. 24 of the 25 bundles are referenced.
`viewUserResolver` is not.

### Testing

| Framework | Version | Scope |
|---|---|---|
| pytest | 8.3.5 | 74 Python test files. |
| Vitest | 4.1.4 | 18 frontend test files, jsdom environment. |
| Go testing | 1.25.4 | 38 test files under `cli/`. |
| nox | ~= 2025.5.1 | Session runner for `pytest-argus-reporter/`. |

114 Python tests carry the `docker_required` marker. `conftest.py` defines no
skip logic for it, so every run needs Docker.

## Database

### ScyllaDB

- **Type**: wide-column. No joins and no unique constraints.
- **Driver**: `scylla-driver >= 3.29.4`.
- **Document mapper**: `coodie >= 1.7.3`. Models under `argus/backend/models/`
  extend `coodie.sync.Document` and declare keys with `@PrimaryKey()`,
  `@ClusteringKey()` and `@Indexed()`.
- **Session setup**: `argus/backend/db.py` opens the session through
  `cassandra.cqlengine.connection`.
- **Schema**: `uv run python -m argus.backend.cli sync-models` applies models
  to the keyspace. The dated files under `scripts/migration/` are one-off data
  jobs that a developer runs by hand.

## Build Tools and Package Management

| Tool | Scope |
|---|---|
| uv | Python dependencies and command running. `uv.lock` is committed. |
| yarn 1.22.22 | Frontend dependencies. `yarn.lock` is committed. |
| go modules | CLI dependencies. `cli/go.sum` is committed. |
| setuptools-scm | Derives the Python version from git tags. |

Frontend commands: `yarn build`, `yarn build:dev`, `yarn build:watch`,
`yarn test`, `yarn test:watch`.

## Infrastructure

### Containers

`Dockerfile` and `docker-entrypoint.sh` build the application image. `dev-db/`
holds a Docker Compose file that starts a single ScyllaDB node for local work.

### CI

Five GitHub Actions workflows. Every action is pinned to a commit SHA.

| Workflow | Runs |
|---|---|
| `lint.yml` | `uv run pre-commit run --all-files` |
| `test.yml` | `uv run pytest`, nox for `pytest-argus-reporter`, and `yarn test` |
| `cli-test.yml` | `go test -race -json -v ./...` |
| `cli-release.yml` | GoReleaser on `cli/*` tags |
| `release.yml` | PyPI trusted publishing |

### Hosting

nginx in front of gunicorn over a unix socket, started by systemd. See
`docs/config/` and `docs/deployment.md`.

## Development Tools

### Linting and formatting

| Tool | Config | Reach |
|---|---|---|
| Ruff | `pyproject.toml` | `exclude = ["argus/"]`. About 50 files. 233 files under `argus/` stay unchecked. |
| ESLint | `eslint.config.js` | Flat config. No hook and no workflow runs it. |
| Prettier | `.prettierrc.js` | Installed. No hook and no workflow runs it. |
| svelte-check | `svelte.config.js` | Installed. No hook and no workflow runs it. |
| commitlint | `commitlint.config.js` | Runs at the `commit-msg` stage only, so `pre-commit run --all-files` skips it. |

`pre-commit` runs `ruff format` and `ruff check --fix --preview`, plus
whitespace, YAML, JSON and private-key checks.

### Type checking

TypeScript 5.x covers 19 modules. `tsconfig.json` extends
`@tsconfig/svelte`. Svelte components declare `lang="ts"`.

## Key Dependencies

| Package | Purpose |
|---|---|
| `jira >= 3.10.5` | Reads and refreshes Jira issues linked to test runs. |
| `pygithub >= 2.6.1` | Reads and refreshes GitHub issues linked to test runs. |
| `python-jenkins >= 1.7.0` | Reads job and build data from Jenkins. |
| `boto3 ~= 1.38.9` | S3 access for run artifacts. |
| `prometheus-client >= 0.26.0` | Metrics, with multiprocess support under gunicorn. |
| `prometheus-fastapi-instrumentator >= 8.1.0` | Request metrics. |
| `PyJWT[crypto] >= 2.10.0` | Token authentication. |
| `zstandard`, `lz4` | Artifact compression. |

Optional extra `ai`: `chromadb >= 1.0.15`, `anthropic >= 1.4.0`,
`tiktoken >= 0.7.0`. The extra `ai-eval` adds the evaluation harness inputs.

## Version Management

- `setuptools-scm` writes `argus/_version.py` from the git tag.
- The Python package publishes to PyPI as `argus-alm` on `v*` tags.
- The CLI publishes GitHub release binaries on `cli/v*` tags.
- Lockfiles for all three ecosystems are committed.

---
*Last updated*: 2026-09-07
*Source*: codebase analysis at commit `fd9099a0`.
