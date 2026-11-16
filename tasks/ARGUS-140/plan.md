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
- Every Renovate run works on a scratch clone and writes its cache in the
  container, so it leaves nothing in the checkout or the user cache.

## Task 1 — Renovate configuration

**Files:**
- Create: `renovate.json`

**Internals:** the configuration of the spec's `Contracts → Outputs`,
unchanged unless the validator or the dry run proves a key wrong. The spec
gets a correction in that case.

- [x] Run `npx --yes --package renovate@44.199.2 -- renovate-config-validator --strict` from the
      repository root before the file exists and confirm it fails.
- [x] Write `renovate.json` from the spec.
- [x] Run the validator again and confirm it passes with no warnings.
- [x] Dry run in the `ghcr.io/renovatebot/renovate:44.199.2` container. The local Node 22 lacks
      `RegExp.escape`. Use a scratch clone with `renovate.json` committed: the local platform reads
      tracked files only. Run `--platform=local --dry-run=lookup`. Confirm all four:
  - [x] Deps are extracted from `pyproject.toml`, `package.json` and `cli/go.mod` only,
        and none from `qatools-health/` or `pytest-argus-reporter/`.
  - [x] Minor and patch updates fall into the three groups: `python non-major`,
        `frontend non-major` and `cli non-major`.
  - [x] Majors and the `go` directive stay separate branches.
  - [x] The `>=` floors in `pyproject.toml` keep their value.
- [x] Render the commit messages. The local platform does not, so run Renovate for real against
      a throwaway Gitea container, with the schedule cleared in the clone. Feed every branch's
      commit message through `@commitlint/cli@19.8.1` with `commitlint.config.cjs` and confirm
      each passes.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Documentation

**Files:**
- Modify: `docs/project/tech-stack.md` (section `Version Management`)
- Modify: `docs/standards/global/conventions.md` (section `Pull Requests`)
- Modify: `docs/INDEX.md` (the Conventions entry, only if its summary changes)

**Internals:** none.

- [x] Add a line to `Version Management` covering:
  - Renovate proposes the updates for the root `pyproject.toml`, `package.json` and `cli/go.mod`
  - one weekly PR per ecosystem for minor and patch, majors one by one, a monthly lockfile refresh
  - vulnerability fixes at once
  - maintainers merge them by hand
- [x] Add a line to `Pull Requests`: Renovate's pull requests carry no Jira key and no
      `closes`/`refs` last line.
- [x] Run `uv run pre-commit run --all-files`.
- [x] Commit, with the boxes of this task checked.

## Task 3 — `0.x` minors and the Python range strategy

**Files:**
- Modify: `renovate.json`
- Modify: `tasks/ARGUS-140/spec.md`

**Internals:** a package rule for Python and npm that gives a minor update below
1.0 its own pull request. `rangeStrategy: update-lockfile` returns to the
Python rule.

- [x] Dry run with the default Python range strategy and confirm the gap: `>=`
      dependencies such as fastapi, uvicorn and click get no update.
- [x] Restore `update-lockfile` and add the `0.x` rule.
- [x] Run the validator and confirm it passes.
- [x] Dry run and confirm all three:
  - [x] The `>=` dependencies get lockfile-only updates, and no floor moves.
  - [x] Every `0.x` minor leaves its group for a branch of its own: fastapi, uvicorn,
        tiktoken, tokenizers, ruff, pytest-subtests and sv.
  - [x] `0.x` patches and Go's `0.x` minors stay grouped.
- [x] Update the spec: the range strategy, the `0.x` rule, the PR limits, and the
      header examples.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.
