# QATOOLS-393 — implementation plan

**Spec:** `tasks/QATOOLS-393/spec.md`

## Constraints

- The bundle layout is the contract in
  `qatools-deployments:tasks/QATOOLS-393/spec.md`; a change to it is a change
  there first.
- Every third-party action is pinned to a full commit SHA with a `# vX.Y.Z`
  comment (`docs/standards/global/conventions.md`). Reuse the pins the other
  workflows carry.
- The verify sequence of `CLAUDE.md`: `uv run pre-commit run --all-files`,
  `uv run pytest`, `yarn test`. No Python or frontend source changes here,
  so pytest and vitest are unaffected; pre-commit covers the YAML and the
  shell script.
- The script is verified by running it for one architecture in the manylinux
  container on a developer machine, and the workflow by a `workflow_dispatch`
  run that publishes nothing.

## Task 1 — The build script

**Files:**
- Create: `scripts/release/build-bundle.sh`

**Internals:** `set -euo pipefail`; `VERSION="${1:?}"`; `PYTHON_VERSION=3.13`;
`git archive HEAD` of the tree with the exclusions the spec lists; the
`public/dist` copy with a check on `main.bundle.js`; `uv` bootstrapped into
`dist/.uv-bin` when absent; the managed interpreter copied to `python/`;
`uv export --frozen --no-emit-project --extra web-backend --extra ai` then
`uv pip install --python <bundle python> --target lib/`; the `.pth`; the
three shims from one `write_shim name module [cd]` function; `mkdir config`;
`VERSION`, `COMMIT`, `.argus_version`; pruning as zeus's script; `compileall`
over `argus`, `argusAI`, `lib`; the self-check from `dist/selfcheck/`, a copy
of the tree at another path.

- [x] Run `bash scripts/release/build-bundle.sh 0.0.0-test` inside
      `quay.io/pypa/manylinux_2_34_x86_64` with the checkout mounted at `/io`,
      after `yarn install --frozen-lockfile && NODE_ENV=production yarn build`
      on the host. Confirm the script stops without `public/dist`.
- [x] Confirm the self-check passes and `du -sh dist/argus-0.0.0-test` is
      recorded in the pull request. 560 MB on x86_64: 472 MB of `lib/`
      (chromadb and onnxruntime), 80 MB of interpreter, 5.7 MB of frontend.
- [x] `uv run pre-commit run --all-files`. Commit
      `feature(release): build a self-contained bundle of the server [QATOOLS-393]`.

## Task 2 — The release workflow

**Files:**
- Modify: `.github/workflows/release.yml`

**Internals:** jobs `version` (tag without `v`, or `inputs.version`),
`frontend` (`ubuntu-24.04`, setup-node 22, `yarn install --frozen-lockfile`,
`NODE_ENV=production yarn build`, upload `public/dist`), `bundle` (matrix
`x86_64` on `ubuntu-24.04`, `aarch64` on `ubuntu-24.04-arm`; download
`public/dist`; `docker run` the manylinux image with the script; `tar | zstd
-19 -T0 --long=27`; `sha256sum`; extract to `${RUNNER_TEMP}/verify` and run
the entry point in the same image; upload the two files), `build` unchanged,
`publish-to-pypi` renamed `release`: needs `build` and `bundle`, downloads the
wheels into `dist/` and the bundles into `bundles/`, asserts both
architectures are present, publishes the wheels to PyPI as before, and hands
`dist/*` and `bundles/*` to `softprops/action-gh-release`.

- [ ] Run the workflow with `workflow_dispatch` on the branch for a test
      version. Confirm both bundle artifacts exist and no release was created.
- [ ] Download the aarch64 artifact and hand it to the deployment repository's
      developer VM through `argus_bundle_local_path`, or to the staging host.
- [ ] `uv run pre-commit run --all-files`. Commit
      `ci(release): publish the bundle beside the wheels on every tag [QATOOLS-393]`.

## Task 3 — The documentation and the files the role now owns

**Files:**
- Modify: `docs/deployment.md` (the pointer, in full), `docs/project/architecture.md`
  (the deployment paragraph), `README.md` (the two deployment lines),
  `docs/INDEX.md` if it names the removed files
- Delete: `docs/config/argus.service`, `docs/config/argus.nginx.conf`,
  `docs/config/argus.logrotate`, `start_argus.sh`, `scan_jobs.sh`,
  `refresh_issues.sh`, `argusAI/deployment/argusai_event_similarity_processor.service`

- [x] Grep for every removed path across the repository and update each
      reference.
- [x] `uv run pre-commit run --all-files`. Commit
      `docs(deployment): point at the deployment repository [QATOOLS-393]`.

## Task 4 — Review

- [ ] Pull request `feature(release): publish a release bundle for the
      deployment [QATOOLS-393]`, body ending with `refs QATOOLS-393`, naming
      `scylladb/qatools` as the repository that closes the issue.
- [ ] Tag the first bundle release once merged, and pin it in the deployment
      repository.
