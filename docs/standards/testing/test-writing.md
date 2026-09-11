## Test Writing

### Test Behavior
Assert what the code does, not how it does it. An implementation detail in an
assertion blocks a safe refactor.

### Clear Names
Name a test for the behavior and the expectation, as in
`test_returns_error_envelope_for_unknown_run`.

### Unit Tests Mandatory
A new code path arrives with a test. Cover the success path, the edge case and
the error path.

### Risk-Based Depth
Match the depth to the risk. Cover the critical path of a release dashboard
read and a run submission first.

### Where Tests Live
| Suite | Path | Runner |
|---|---|---|
| Web backend | `argus/backend/tests/` | `uv run pytest` |
| Client library | `argus/client/tests/` | `uv run pytest` |
| pytest reporter | `pytest-argus-reporter/tests/` | `uv run nox` |
| Frontend | `frontend/**/*.test.{js,ts}` | `yarn test` |
| Command line tool | `cli/` | `go test -race ./...` |

Backend tests group into a directory per feature, as in
`argus/backend/tests/planner_api/`. A file follows `test_*.py`.

### Two Collection Traps
`pyproject.toml` lists two paths in `norecursedirs`.

1. `pytest-argus-reporter/tests` — `uv run pytest` skips the reporter suite.
   Run it through nox from inside `pytest-argus-reporter/`.
2. `argus/backend/service` — the modules `test_lookup.py` and
   `test_hierarchy.py` hold production logic, and the entry keeps pytest from
   collecting them. A real test placed in that directory is not collected
   either. Put a service test under `argus/backend/tests/`.

### Docker Is Required
The backend fixtures start a ScyllaDB container, set
`CQLENG_ALLOW_SCHEMA_MANAGEMENT=1` and apply the models with `sync_models`.
114 tests carry `@pytest.mark.docker_required`, and `conftest.py` defines no
skip logic for the marker. Every backend run needs Docker.

### Shared Fixtures
Put a shared fixture in `argus/backend/tests/conftest.py`. Reuse the session
and the seeded release, group and test rows rather than creating new ones.

### Mock the External Service
Mock Jira, GitHub, Jenkins, S3 and the Anthropic API. Keep the database real, because the
fixtures provide it.

### Frontend Tests
Vitest runs in a jsdom environment and collects `frontend/**/*.test.{js,ts}`.
Test a component through its props and its rendered output.

### Go Tests
CI runs `go test -race -json -v ./...` from `cli/`. Keep the code free of a
race. Use `httptest.NewServer` for an HTTP test.

### No Tests for Document Content
Write no test that asserts the content of a Markdown file in this repository.
No substring match, no heading check, no index membership. Such an assertion
pins the wording rather than the rule, so a rewrite for clarity reads as a
failure. Review catches document drift. Code that reads or converts Markdown
keeps its tests.

### CI Quality Gates
- `lint.yml` — `uv run pre-commit run --all-files`
- `test.yml` — `uv run pytest`, then nox for the reporter, then `yarn test`
- `cli-test.yml` — golangci-lint and `go test -race -json -v ./...`
