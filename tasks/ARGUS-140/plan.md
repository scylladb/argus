# ARGUS-140 — implementation plan

**Spec:** `tasks/ARGUS-140/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Renovate tooling runs through `npx` pinned to `renovate@44.199.2`, a release
  older than two weeks. Nothing is added to `package.json`.
- The change adds no runtime code, so it adds no unit test. The Renovate config
  validator and a local dry run take the place of the failing test.
- Run the dry run with `XDG_CACHE_HOME` and `RENOVATE_BASE_DIR` pointing to a scratch
  directory, so it leaves nothing in the checkout or the user cache.

## Task 1 — Renovate configuration

**Files:**
- Create: `renovate.json`

**Internals:** the configuration of the spec's `Contracts → Outputs`,
unchanged unless the validator or the dry run proves a key wrong. The spec
gets a correction in that case.

- [ ] Run `npx --yes --package renovate@44.199.2 -- renovate-config-validator --strict renovate.json`
      before the file exists and confirm it fails.
- [ ] Write `renovate.json` from the spec.
- [ ] Run the validator again and confirm it passes with no warnings.
- [ ] Dry run against the checkout:
      `LOG_LEVEL=debug npx --yes --package renovate@44.199.2 -- renovate --platform=local --dry-run=lookup`.
      Confirm all four:
  - [ ] Deps are extracted from `pyproject.toml`, `package.json` and `cli/go.mod` only,
        and none from `qatools-health/` or `pytest-argus-reporter/`.
  - [ ] Minor and patch updates fall into the three groups: `python non-major`,
        `frontend non-major` and `cli non-major`.
  - [ ] Majors and the `go` directive stay separate branches.
  - [ ] The commit messages carry the spec's types and scopes.
- [ ] Feed the longest header from the spec, with a table body, through commitlint
      (`npx --yes commitlint@<pinned>` with `commitlint.config.cjs`) and confirm it passes.
- [ ] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [ ] Commit, with the boxes of this task checked.

## Task 2 — Documentation

**Files:**
- Modify: `docs/project/tech-stack.md` (section `Version Management`)
- Modify: `docs/standards/global/conventions.md` (section `Pull Requests`)
- Modify: `docs/INDEX.md` (the Conventions entry, only if its summary changes)

**Internals:** none.

- [ ] Add a line to `Version Management` covering:
  - Renovate proposes the updates for the root `pyproject.toml`, `package.json` and `cli/go.mod`
  - one weekly PR per ecosystem for minor and patch, majors one by one, a monthly lockfile refresh
  - vulnerability fixes at once
  - maintainers merge them by hand
- [ ] Add a line to `Pull Requests`: Renovate's pull requests carry no Jira key and no
      `closes`/`refs` last line.
- [ ] Run `uv run pre-commit run --all-files`.
- [ ] Commit, with the boxes of this task checked.
