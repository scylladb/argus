# QATOOLS-393 — Publish a release bundle the deployment can install

## Problem

Argus has no release artifact a host can run. A deployment is a source build
on the host: clone the repository, `uv sync --all-extras`, `yarn install`,
`yarn build`, then start gunicorn through `uv run` from a login shell. The
host needs Python, uv, Node, yarn and a route to PyPI and the npm registry,
and two hosts deployed a month apart run whatever those resolved to that day.

The release workflow publishes the `argus-alm` wheel to PyPI on every `v*`
tag, and that wheel is the client library: `MANIFEST.in` prunes the backend
out of it. Nothing on a release describes the server.

`qatools-deployments` now deploys Zeus and Maia from a checksummed release
bundle each repository publishes, and its new `roles/argus` is written
against the same shape for Argus. Until this repository publishes that
bundle, the role has nothing to install.

## Who it affects

The QA Tools engineers who deploy Argus, and the `roles/argus` in
`qatools-deployments` that expects `argus-<version>-linux-<arch>.tar.zst`
with a sha256 beside it on every release. The reviewer of a release, who
today cannot say which build production runs.

## Evidence

Jira: [QATOOLS-393](https://scylladb.atlassian.net/browse/QATOOLS-393),
"Deploy Argus with the same ansible automation as Zeus and Maia":

> In the Argus repo: a release workflow (mirroring zeus's) that builds a
> bundle with the frontend assets already compiled and the backend
> dependencies vendored in, and publishes it with a sha256 checksum to a
> GitHub release.

`docs/deployment.md`, the procedure a host runs today:

```
uv sync --all-extras
yarn install
yarn build
```

`MANIFEST.in`, why the PyPI wheel is not the server:

```
prune **/tests
prune **/backend
```

`.github/workflows/release.yml` builds and publishes that wheel and attaches
`dist/*` to the GitHub release; no bundle is built anywhere.

The bundle contract the deployment expects, from
`qatools-deployments:tasks/QATOOLS-393/spec.md`:

```
argus-<version>/
  VERSION  COMMIT  .argus_version
  argus_backend.py  gunicorn.conf.py  argus/  argusAI/  templates/  public/  scripts/migration/
  config/  python/  lib/
  bin/argus-web  bin/argus-cli  bin/argus-ai-worker
```

## What good looks like

- Every `v*` tag publishes `argus-<version>-linux-x86_64.tar.zst` and
  `argus-<version>-linux-aarch64.tar.zst`, each with a `.sha256` beside it,
  on the same GitHub release that carries the wheels.
- A bundle carries the application, the built frontend, the argusAI worker,
  its own CPython and every locked dependency of the `web-backend` and `ai`
  extras. A host extracts it and runs it, with no Python, Node or network
  beyond the download.
- The workflow refuses to publish a bundle it has not run: extracted to
  another path, in a container with no Python, its entry points start.
- `docs/deployment.md` points at the deployment repository. The shell
  wrappers, the reference unit, vhost and logrotate files, and the argusAI
  unit file leave this repository, because the role owns them now.

## Out of scope

- The Ansible role, the hosts, the cut-over. They are `qatools-deployments`.
- Health endpoints and monitoring (QATOOLS-425).
- The Docker image and `docker-entrypoint.sh`.
- The PyPI publication of the wheels, which stays as it is.
- The Go CLI's own release workflow.
