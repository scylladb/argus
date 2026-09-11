## Coding Standards & Conventions

Read @docs/INDEX.md before starting any task. It indexes the project's coding standards and conventions:
- Coding standards organized by domain (frontend, backend, testing, etc.)
- Project vision, tech stack, and architecture decisions

Follow standards in `docs/standards/` when writing code — they represent team decisions. If standards conflict with the task, ask the user.

`AGENTS.md` holds the repository facts: the module map, the key files, the
skills and the tooling. Read it for orientation.

## Development Flow

Read `docs/standards/development-flow.md`. It describes the six stages, the
artifact each stage produces, and who approves it.

When you review a pull request, work through the three passes in
`docs/standards/REVIEW.md` and state the outcome of each one.

## Task Artifacts

Each Jira issue gets a directory: `tasks/<KEY>/`, with the key in uppercase, as
in `tasks/ARGUS-123/`. Copy the matching template from `tasks/templates/`.

- An intent goes to `tasks/<KEY>/intent.md`.
- A spec goes to `tasks/<KEY>/spec.md`.
- A plan goes to `tasks/<KEY>/plan.md`.

Commit each artifact before you start the work that consumes it.

1. Do not start a task that has no intent. Write the intent first.
2. Do not write the spec until `tasks/<KEY>/intent.md` is committed.
3. Do not write the plan until `tasks/<KEY>/spec.md` is committed.
4. Do not write code until `tasks/<KEY>/plan.md` is committed.

A commit gate is not an approval gate. A committed artifact stays open to
review, and a later commit records the correction.

The brainstorming skill writes the spec. Its output goes to the task directory.
The skill writes no plan on its bounded path, so write the plan yourself. A
small task keeps a short plan.

A spike is the exception. When working code exists and no artifact does, stop
before you commit the code. Write `intent.md` and `spec.md` from the code, and
commit them. Then commit the code. That path writes no plan. See
`docs/standards/development-flow.md`.

`docs/plans/` holds the plans that started before this flow. Leave them in
their own format until the work ends. See `docs/plans/INSTRUCTIONS.md`.

### Standards Evolution

When you notice recurring patterns, fixes, or conventions during implementation that aren't yet captured in standards — suggest adding them. Examples:
- A bug fix reveals a pattern that should be standardized (e.g., "always validate X before Y")
- PR review feedback identifies a convention the team wants enforced
- The same type of fix is needed across multiple files
- A new library/pattern is adopted that should be documented

When this happens, briefly suggest the standard to the user.

## Commands

Run this sequence before you call the work done. Work is done when it passes.

```bash
uv run pre-commit run --all-files
uv run pytest
yarn test
```

A backend test needs Docker. The fixtures start a ScyllaDB container.

`pyproject.toml` lists `pytest-argus-reporter/tests` in `norecursedirs`, so
`uv run pytest` skips that suite. For a change under `pytest-argus-reporter/`:

```bash
cd pytest-argus-reporter && uv sync --all-extras && uv run nox
```

For a change under `cli/`:

```bash
cd cli && make lint && go test -race ./...
```

Run `make fmt` in `cli/` to format Go code before you commit.

For a change under `frontend/`, build the bundles:

```bash
yarn build
```
