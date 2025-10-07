# Repository Guidelines

## Project Structure & Module Organization
Backend services live in `argus/backend` with Flask entry points defined in `argus_backend.py`; shared helpers sit in `argus/common`, while CLI tooling and client integrations are under `argus/client`. Frontend assets are in `frontend/`, compiled into `public/dist`, and HTML templates stay in `templates/`. Test suites are grouped in `argus/backend/tests`, `argus/client/tests`, and `pytest-argus-reporter/tests`.

## Build, Test, and Development Commands
Install dependencies with `uv sync --all-extras` and `yarn install`. Rebuild the Svelte-based UI with `ROLLUP_ENV=development yarn rollup -c --watch`. Start the API locally via `FLASK_ENV=development FLASK_APP=argus_backend:start_server CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 uv run flask run`. For linting, run `uv run ruff check`. Run server-side tests with `uv run pytest argus/backend/tests` and client utilities through `uv run pytest argus/client/tests`.

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
