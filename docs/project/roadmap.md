# Development Roadmap

## Active Work
A task follows `docs/standards/development-flow.md`. Its intent, spec and plan
live in `tasks/<KEY>/`, and the Jira board holds the status.

## Known Debt

### Lint coverage
- Ruff sets `exclude = ["argus/"]` with `force-exclude = true`, so the whole
  web backend and client package stay unchecked. Narrow the exclusion, or
  remove it after a formatting pass.
- ESLint, Prettier and svelte-check are installed. No hook and no workflow runs
  them.

### Python version floor
`pyproject.toml` declares `requires-python = ">=3.10"` and Ruff sets
`target-version = "py310"`, while all workflows pin 3.12. Raise the floor to
match what CI tests.

### Tests need Docker
114 tests carry `@pytest.mark.docker_required`, and `conftest.py` defines no
skip logic for the marker. A machine without Docker cannot run the backend
suite at all.

### Legacy Svelte
45 files import `svelte/legacy`. Convert them to runes.

### Unreferenced bundle
`vite.config.ts` declares 25 entry points. No template references
`viewUserResolver`. Remove it or wire it up.

### API documentation
`create_app()` sets `openapi_url=None`, so there is no generated schema.
`docs/api_usage.md` is written by hand and drifts.

---
*Assessment as of 2026-09-11.*
