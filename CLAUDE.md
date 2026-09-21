## Coding Standards & Conventions

Read @docs/INDEX.md before starting any task. It indexes the project's coding standards and conventions:
- Coding standards organized by domain (frontend, backend, testing, etc.)
- Project vision, tech stack, and architecture decisions

Follow standards in `docs/standards/` when writing code — they represent team decisions. If standards conflict with the task, ask the user.

`AGENTS.md` holds the repository facts: the module map, the key files, the
skills and the tooling. Read it for orientation.

<!-- qatools-sdlc:begin -->
## Development flow

This repository uses the `qatools-sdlc` plugin. Every piece of work goes
through its flow: `/qatools-sdlc:intent <KEY>`, then `/qatools-sdlc:spec` or
`/qatools-sdlc:rca` for a bug, then `/qatools-sdlc:plan`, then the code.
Commit each artifact before the stage that consumes it. A review works
through `/qatools-sdlc:review`. The user may skip the flow for a very small
fix when they say so. The pull request description then states the skip in
one line.

If the `/qatools-sdlc:*` skills are not available, stop and ask the user to
run these two commands, then start a new session:

    /plugin marketplace add git@github.com:scylladb/qatools.git
    /plugin install qatools-sdlc@qatools

Jira keys: `ARGUS-<n>`. Task artifacts: `tasks/<KEY>/`. Read
`docs/INDEX.md` before any task and follow the standards in
`docs/standards/`. Suggest `/qatools-sdlc:standards-update` when a
convention comes up that no standard holds. Verify sequence: section
`Commands` of this file.
<!-- qatools-sdlc:end -->

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
