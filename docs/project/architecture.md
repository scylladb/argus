# System Architecture

## Overview

Argus records what automated test pipelines do. A pipeline reports a run,
Argus stores it in ScyllaDB, and a web interface shows the run, its events,
its resources and its results. Argus also compares runs of the same test.

The system holds five deployable parts and one shared library. Each part
builds and tests on its own.

## Architecture Pattern

**Pattern**: layered web application with a plugin layer for test sources.

Requests enter a FastAPI router, a service holds the business logic, and a
document model reads and writes ScyllaDB. Each test source adds its own run
model, and optionally its own router, through the plugin layer.

## System Structure

### Web backend

- **Location**: `argus/backend/`
- **Purpose**: serves the REST API, renders the server-side pages and holds
  all business logic.
- **Entry point**: `argus_backend.py`. `create_app()` returns the FastAPI
  application.
- **Layers**:
  - `controller/` — 16 modules. One router per feature: `testrun_api.py`,
    `client_api.py`, `view_api.py`, `planner_api.py`, `admin_api.py`,
    `notification_api.py`, `replay_api.py`, `ssh_api.py`, `auth.py`.
  - `service/` — 24 modules. The business logic each router calls.
  - `models/` — 12 modules. `web.py` holds the core entities. `jira.py`,
    `github_issue.py`, `pytest.py`, `result.py`, `plan.py`, `view_widgets.py`,
    `ssh_key.py`, `run_config.py`, `runtime_store.py` and `argus_ai.py` hold
    the rest.
  - `util/` — 7 modules of shared helpers.
  - `rendering.py` — the template helpers the `.j2` files expect.
  - `db.py` — session setup.
  - `cli.py` — maintenance commands: `sync-models`, `refresh-issues`,
    `scan-jenkins`.

Two modules under `service/` are named `test_lookup.py` and
`test_hierarchy.py`. They hold production lookup logic. `pyproject.toml` lists
`argus/backend/service` in `norecursedirs` so pytest does not collect them. A
real test placed in that directory is not collected either.

### Plugin layer

- **Location**: `argus/backend/plugins/`
- **Purpose**: adds a test source without a change to the core.
- **Sources**: `sct`, `sirenada`, `generic`, `driver_matrix_tests`.
- **Contract**: a plugin directory holds a `plugin.py` that exports
  `PluginInfo`, a subclass of `PluginInfoBase` with five fields.

  | Field | Meaning |
  |---|---|
  | `name` | The key the loader registers the plugin under. |
  | `model` | The run model, a `PluginModelBase` subclass. |
  | `controller` | An `APIRouter` for routes the source needs, or `None`. |
  | `all_models` | Every document the source owns, for `sync-models`. |
  | `all_types` | Every user-defined type the source owns. |

  `loader.py` imports each `plugin.py` it finds and keys the result by `name`.
  A plugin owns no service. `ClientService` reads `AVAILABLE_PLUGINS` and calls
  the classmethods on the run model, such as `submit_run` and `load_test_run`,
  so a new source needs no change in the shared service. The `sct` and
  `driver_matrix_tests` sources add a service of their own for logic beyond
  those methods. The `generic` and `sirenada` sources add none, and `generic`
  sets `controller = None`.

### Frontend

- **Location**: `frontend/`, built into `public/dist/`
- **Purpose**: the browser interface.
- **Structure**: one directory per feature area, in PascalCase, with the main
  component named after the directory. `Stores/` holds shared state.
  `Common/` holds helpers and type definitions.
- **Entry points**: `vite.config.ts` declares 25. Each one loads from a Jinja
  template in `templates/`.

### Command line tool

- **Location**: `cli/`
- **Purpose**: reads test runs, release status and build data from a terminal
  or from CI.
- **Structure**: Go module with `cmd/`, `internal/`, `main.go` and a
  `Makefile`.
- **Command groups**: auth, config, logs, metrics, pytest results, test runs,
  search, ssh, users and views.
- **Credentials**: the system keyring. macOS Keychain, Windows Credential
  Manager or `pass` on Linux. The tool manages `cloudflared` for Cloudflare
  Access.

### AI workers

- **Location**: `argusAI/`
- **Purpose**: makes large event sets readable.
- **Similarity**: `event_similarity_processor_v2.py` embeds SCT `ERROR` and
  `CRITICAL` events with BGE-Small-EN, 384 dimensions. It writes one table per
  severity.
- **Summarization**: `utils/summary_dispatcher.py` calls Claude through the
  `anthropic` client. `ANTHROPIC_SUMMARY_MODEL` names the model and
  `ANTHROPIC_API_KEY` authenticates it. A token count gates each call through
  `EVENT_SUMMARIZATION_MIN_TOKENS`, default 250. `EVENT_SUMMARIZATION_ENABLED`
  and `EVENT_SUMMARIZATION_PROMPT_VERSION` control the rest. Four workers run
  at once by default.
- **Evaluation**: `eval/` holds the baseline, the metrics, the judge, the
  dedup step and the pricing model.

### Client library and reporter

- **Location**: `argus/client/`, `argus/common/`, `pytest-argus-reporter/`
- **Purpose**: lets a pipeline submit a run and its results.
- **Distribution**: `argus-alm` on PyPI, with the console commands
  `argus-client-generic` and `argus-driver-matrix-client`.
  `pytest-argus-reporter` ships as its own package.

## Data Flow

1. A test pipeline runs. The client library or the pytest reporter submits the
   run to `client_api.py`.
2. The matching plugin service validates the payload and writes the run.
3. A run row carries its release, group and test identifiers directly.
   ScyllaDB has no joins, so a read needs no second query.
4. `cli.py scan-jenkins` reads job and build data from Jenkins.
5. `cli.py refresh-issues` refreshes the linked Jira and GitHub issues.
6. The AI workers read new events, embed them and write summaries.
7. The browser loads a page template, the bundle for that page fetches from
   the REST API, and the Svelte components render the result.

## Data Model Rules

ScyllaDB gives no joins, no foreign keys and no unique constraints. Three
rules follow.

- **Copy, do not reference.** A row carries the identifiers a reader needs.
- **Enforce uniqueness in the application.** Read through a secondary index
  first, then write.
- **Design the partition key for the read.** The key decides which queries are
  possible.

## External Integrations

| System | Purpose |
|---|---|
| ScyllaDB | Primary store. |
| Jenkins | Job and build data. |
| Jira | Issues linked to test runs. |
| GitHub | Issues linked to test runs, and OAuth sign-in. |
| Amazon S3 | Run artifacts. |
| Anthropic | Event summaries. |
| Cloudflare Access | Protects the deployed instance. The CLI authenticates through it. |
| Prometheus | Scrapes application metrics. |

## Configuration

- `argus.local.yaml` — database connection for local work.
- `argus_web.yaml` — application secrets and service endpoints. Copy
  `argus_web.example.yaml` to start.
- `gunicorn.conf.py` — worker count, socket path and Prometheus multiprocess
  settings.
- Environment variables control the AI workers.

Never commit a secret. `dev-db/` provides a local database, so no test needs a
production endpoint.

## Deployment Architecture

nginx accepts the request. It passes the request over a unix socket to
gunicorn, which runs 4 uvicorn workers. systemd starts the service. Prometheus
scrapes the metrics endpoint. `docs/config/` holds the nginx, systemd and
logrotate files. `docs/deployment.md` holds the procedure.

The AI workers run as their own systemd service. See
`argusAI/deployment/`.

---
*Source*: codebase analysis at commit `fd9099a0`, 2026-09-07.
