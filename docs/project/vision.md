# Project Vision

## Overview
Argus is a test tracking system. It gives observability into automated test
pipelines that use long-running resources. A pipeline reports a run, Argus
stores it, and the web interface shows the run, its events, its resources and
its results. Argus also compares runs of the same test.

## Current State
- **Status**: active development.
- **Users**: ScyllaDB QA engineers and developers who track automated test
  pipelines.
- **Stack**: Python 3.12 with FastAPI on ScyllaDB, a Svelte 5 frontend, a Go
  command line tool, and Python AI workers.
- **Distribution**: the `argus-alm` package on PyPI, the `pytest-argus-reporter`
  package, and the `argus` CLI as a GitHub release binary.
- **Deployment**: nginx in front of gunicorn over a unix socket, started by
  systemd, with Prometheus scraping the metrics endpoint.

## Purpose
A long-running test holds cloud resources for hours or days. When it fails, an
engineer needs the run, its events, its nemeses, its resources and its logs in
one place. Argus collects that data from the pipeline as the test runs, and
keeps it after the resources are gone.

Argus also links a run to the Jira and GitHub issues that track its failures,
so a repeated failure stays connected to its issue.

## Sources of Work
A test source reports through the plugin layer. Each source keeps its own run
model, router and service.

- **SCT** — the ScyllaDB cluster test suite.
- **DTest through the driver matrix client** — the driver test matrix.
- **Sirenada** — the Sirenada suite.
- **Generic** — any pipeline that submits through `argus-client-generic`.
- **pytest** — any Python suite that installs `pytest-argus-reporter`.

## Consumers
- The web interface, for a release dashboard, a run view and a comparison.
- The `argus` CLI, for a terminal or a CI job.
- The REST API, for a script.

## Direction
The registry in `docs/plans/MASTER.md` holds the active plans, and
`docs/project/roadmap.md` states the current priorities and the known debt.
