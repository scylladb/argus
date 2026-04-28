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

## Pull Request Review Guidelines
- **Scope reviews to the PR diff only.** Only flag issues in files and lines actually changed in the pull request. Do not audit the broader codebase for related issues — that is a separate task, not a PR review. If you notice a broader pattern worth mentioning, note it once as an aside at the end, not as individual findings.
- **Limit findings to 3-5 maximum.** Prioritize ruthlessly. If unsure whether something is real, omit it. A review with 2 correct findings is more valuable than 2 correct findings buried among 5 false positives.
- **Verify claims before flagging.** Read the full context (complete CSS rule, surrounding function, component logic) before reporting. Do not flag `color: black` without checking the selector's `background-color`. Do not flag a variable as unused without grepping. Do not flag a function as broken without reading its callers.
- **Require concrete failure scenarios for bugs.** Only label something "Critical" or "likely a bug" if you can demonstrate a realistic reproduction. Theoretical edge cases involving UUIDs, rare events, or unlikely race conditions are suggestions at best. Use "potential concern" or "worth verifying" for speculative findings.
- **Respect visual/runtime evidence.** When a PR includes demos, screenshots, or staging URLs, do not contradict them with static analysis alone. Acknowledge the evidence and qualify findings accordingly.
- **Treat repeated patterns as conventions.** If a pattern appears in 3+ places in the codebase, it is likely a deliberate project convention, not a bug. Do not flag it.
- **Check existing comments first.** Do not re-report issues already identified by human reviewers in the same PR.
- **Svelte 5 runes are not Svelte 4.** `$state` creates deeply reactive proxies — `.push()` on a `$state` array triggers reactivity (no reassignment needed). `$derived` values can be reassigned. Do not apply Svelte 4 mental models to this codebase.
- **CSS color pairs are self-contained.** Severity badges, status indicators, and alert classes set both `background-color` and `color` as a pair. They work in any theme. Only flag color issues when an element relies on the inherited page background.
- **Do not flag migration-period code.** Fallbacks, temporary dual paths, and compatibility shims in PRs that are part of an ongoing migration are intentional.

## Configuration & Security Notes

Never commit secrets: When testing against Cassandra, use the Docker compose setup in `dev-db/` and tear it down after use. Keep sample data archives outside the repository to avoid leaking production artifacts.

## Skills

AI agent skills live in `skills/` and provide task-specific guidance with structured workflows.

| Skill            | Description                                                           | Path                               |
| ---------------- | --------------------------------------------------------------------- | ---------------------------------- |
| writing-plans    | Write implementation plans (full 7-section or lightweight mini-plans) | `skills/writing-plans/SKILL.md`    |
| designing-skills | Meta-skill for creating and structuring new AI agent skills           | `skills/designing-skills/SKILL.md` |

## Implementation Plans

Plans are tracked in `docs/plans/`. See `docs/plans/INSTRUCTIONS.md` for the authoritative guide on plan structure, and `docs/plans/MASTER.md` for the registry of active plans.
