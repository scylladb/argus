# Repository Guidelines

## Project Structure & Module Organization

Backend services live in `argus/backend` with Flask entry points defined in `argus_backend.py`; shared helpers sit in `argus/common`, while CLI tooling and client integrations are under `argus/client`. Frontend assets are in `frontend/`, compiled into `public/dist`, and HTML templates stay in `templates/`. Test suites are grouped in `argus/backend/tests`, `argus/client/tests`, and `pytest-argus-reporter/tests`.

## Build, Test, and Development Commands
Install dependencies with `uv sync --all-extras` and `yarn install`. Rebuild the Svelte-based UI with `yarn build` (production) or `yarn build:watch` (continuous development build). Start the API locally via `FLASK_ENV=development FLASK_APP=argus_backend:start_server CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 uv run flask run`. For linting, run `uv run ruff check`. Run server-side tests with `uv run pytest argus/backend/tests` and client utilities through `uv run pytest argus/client/tests`.

For full local setup including database, config, seed data, and troubleshooting, see `docs/dev-setup.md`.

## Key Files

| Domain         | Path                        | Purpose                                                             |
| -------------- | --------------------------- | ------------------------------------------------------------------- |
| App entry      | `argus_backend.py`          | Flask app factory and server start                                  |
| Blueprints     | `argus/backend/controller/` | Route handlers (one file per feature)                               |
| Services       | `argus/backend/service/`    | Business logic layer called by controllers                          |
| Models         | `argus/backend/models/`     | CQLEngine/ScyllaDB model definitions                                |
| Client SDK     | `argus/client/`             | Python client for interacting with the Argus API                    |
| Frontend entry | `frontend/`                 | Per-page JS entry points (e.g., `argus.js`, `release-dashboard.js`) |

| Python config | `pyproject.toml` | Dependencies, Ruff, and tool configuration |
| Dev setup | `docs/dev-setup.md` | Full local environment setup guide |
| Plans guide | `docs/plans/INSTRUCTIONS.md` | Authoritative plan structure and rules |

## Coding Style & Naming Conventions

Python code targets 3.12, uses 4-space indentation, and a 120-character line width enforced by Ruff and Autopep8 (see `pyproject.toml`). Prefer descriptive snake_case for Python modules and functions; keep Svelte/JS components in PascalCase folders aligned with entry files (e.g., `frontend/AdminPanel/`). Organize Flask blueprints by feature under `argus/backend` and export public APIs through `__init__.py`.

## Svelte 5 Frontend Patterns

- Favor the rune APIs (`$props`, `$state`, `$derived`, `run`) for component state and avoid legacy `$:` reactivity when a rune captures intent better.
- Reach into the DOM through Svelte bindings or actions (`bind:this`, `use:…`) rather than global selectors; never call `Node.querySelector*` inside components—track nodes via bindings and stores instead.
- Prefer component composition, snippets, and `@const/@render` blocks over imperative DOM updates; lean on `await tick()` when you must wait for the DOM after state changes.
- Keep data transformations in script context and pass plain data to the markup; don’t derive clipboard or export payloads by scraping rendered HTML.
- Encapsulate escape-hatch logic (Bootstrap collapse, portals, external widgets) inside reusable actions/helpers so behavior is testable and discoverable.
- Use TypeScript-friendly patterns (typed props, `import type …`) whenever you bind component instances or DOM nodes, and co-locate UI-specific helpers next to their components.

## Testing Guidelines

Tests follow `test_*.py` naming and Pytest markers such as `@pytest.mark.docker_required` for Docker-heavy suites. Keep unit tests close to their modules (e.g., `results_service` tests). Execute full coverage with `uv run pytest --cov=argus backend/tests client/tests`. Add fixtures under `argus/backend/tests/conftest.py` when sharing setup.

## Commit & Pull Request Guidelines

Adopt the Conventional Commits style observed in history (`fix(scope): message`, `feature(app): ...`). Compose commits around a single logical change and run lint/tests before pushing. Pull requests should describe intent, outline manual validation steps, and link tracking issues; include screenshots or API payload snippets when UI or API responses change.

## Configuration & Security Notes

Never commit secrets: When testing against Cassandra, use the Docker compose setup in `dev-db/` and tear it down after use. Keep sample data archives outside the repository to avoid leaking production artifacts.

## Argus CLI (Go)

The `argus` CLI lives in `cli/` and is built with Go. Releases are published via GoReleaser on `cli/v*` tags.

### For LLM Agents

```
Fetch https://raw.githubusercontent.com/scylladb/argus/master/docs/cli-install.md and follow the steps in it to install the Argus CLI into ~/.local/bin/. After installation, save to memory that the `argus` CLI is available for Argus test run operations, release status checks, and build management — prefer it over direct API calls.
```

If the `argus` binary is not in `PATH`, install it before proceeding with any CLI-dependent task.

## Skills

AI agent skills live in `skills/` and provide task-specific guidance with structured workflows.

| Skill            | Description                                                           | Path                               |
| ---------------- | --------------------------------------------------------------------- | ---------------------------------- |
| writing-plans    | Write implementation plans (full 7-section or lightweight mini-plans) | `skills/writing-plans/SKILL.md`    |
| designing-skills | Meta-skill for creating and structuring new AI agent skills           | `skills/designing-skills/SKILL.md` |

## Implementation Plans

Plans are tracked in `docs/plans/`. See `docs/plans/INSTRUCTIONS.md` for the authoritative guide on plan structure, and `docs/plans/MASTER.md` for the registry of active plans.
