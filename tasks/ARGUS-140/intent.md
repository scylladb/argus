# ARGUS-140 — Automatic dependency updates

## Problem

The Argus dependencies are updated by hand, when someone happens to need a
newer version. Nothing tells the team that a dependency has a new release or
a published vulnerability, so the backend, the client, the frontend and the
CLI drift behind their upstreams unnoticed. When an update finally happens,
it spans many releases at once, which makes a breakage harder to find.

GitHub's vulnerability alerts are disabled for the repository, so a known
vulnerable version in a lockfile raises no signal either.

## Who it affects

The maintainers of Argus, who carry the update work and the risk of large
catch-up upgrades. The users of the web application and of the `argus-alm`
client, which SCT installs, who run whatever versions were last picked.

## Evidence

Jira: [ARGUS-140](https://scylladb.atlassian.net/browse/ARGUS-140).
From the issue body:

> Currently, we update argus dependencies manually as needed, for both
> frontend and backend. This creates some issues as there might be blind
> spots in our update process or potential vulnerabilities. Proposal is to
> add automatic dependency update PRs, using Renovate or other tools to
> automatically bump stable versions of the packages.

`gh api repos/scylladb/argus/dependabot/alerts` on 2026-11-16:

> Dependabot alerts are disabled for this repository.

Drift on 2026-11-16. From `uv tree --outdated --depth 1`, 32 direct Python
dependencies have a newer release, among them:

> ├── fastapi v0.141.1 (extra: web-backend) (latest: v0.162.5)
> ├── pyjwt[crypto] v2.10.1 (extra: web-backend) (latest: v2.15.1)
> ├── scylla-driver v3.29.7 (extra: web-backend) (latest: v3.29.13)
> ├── uvicorn v0.40.0 (extra: web-backend) (latest: v0.54.0)
> ├── requests v2.32.5 (latest: v2.34.2)

From `yarn outdated`, 44 frontend packages have a newer release, among them:

> dompurify                           3.2.6   3.4.18  3.4.18  dependencies
> svelte                              5.55.5  5.57.3  5.57.3  dependencies
> vite                                8.0.10  8.3.8   8.3.8   devDependencies

From `go list -m -u all` in `cli/`, 8 direct Go modules have a newer release:

> github.com/klauspost/compress v1.18.5 -> v1.20.4
> golang.org/x/term v0.41.0 -> v0.48.0
> golang.org/x/text v0.28.0 -> v0.44.0

## What good looks like

New releases of the backend, client, frontend and CLI dependencies show up
as pull requests without anyone looking for them. A known vulnerable version
raises a pull request promptly. Each pull request runs the existing CI, so a
maintainer can see whether it breaks anything before merging it.

## Out of scope

- GitHub Actions, the Dockerfile and the pre-commit hook revisions.
- `qatools-health/` and `pytest-argus-reporter/`.
- Merging the update pull requests automatically.
- Upgrading the dependencies that are behind today; the updates arrive
  through the new pull requests.
