# Local Development Setup

## Prerequisites

- Python 3.14
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- Node.js >= 22 with npm
- Yarn (`npm -g install yarn`)
- Docker and Docker Compose

---

## Daily Workflow (TL;DR)

If you've already done the first-time setup below, this is all you need
each time you sit down to work:

```bash
# 1. Start the database (wait ~60-90s for ScyllaDB to initialize)
docker compose -f dev-db/docker-compose.yaml up -d
docker logs -f dev-db-node1-1 2>&1 | grep -m1 "initialization completed"

# 2. Start the backend (in one terminal)
uv run uvicorn --factory argus_backend:create_app --port 5000 --reload

# 3. Start the frontend (in another terminal)
yarn build:watch

# 4. Open http://localhost:5000 — login with admin/admin
```

When you're done:

```bash
# Stop the backend with Ctrl+C, then stop the database. The data stays in
# the Docker volumes.
docker compose -f dev-db/docker-compose.yaml down
```

> The database **must be running** before you start the backend. It connects
> to ScyllaDB at startup and exits immediately if it can't reach it.

---

## First-Time Setup

Follow these steps once when you first clone the repository.

### 1. Install dependencies

```bash
# Python (skip --extra dev if you don't need linting/test tooling)
uv sync --extra web-backend --extra dev

# Frontend
yarn install
```

### 2. Create the config file

The webapp reads `argus_web.yaml` from the repository root. It is
gitignored — you need to create it yourself.

```bash
cp argus_web.example.yaml argus_web.yaml
```

Then replace the contents with this minimal local config:

```yaml
BASE_URL: "http://localhost:5000"
SCYLLA_CONTACT_POINTS:
    - 172.24.99.1
SCYLLA_USERNAME: cassandra
SCYLLA_PASSWORD: cassandra
SCYLLA_KEYSPACE_NAME: argus_tablets

APP_LOG_LEVEL: INFO
SECRET_KEY: MUSTBEUNIQUE

LOGIN_METHODS:
    - password

# Disable remote issue-tracking integrations not needed locally.
# When false, the corresponding credentials are not required.
GITHUB_ENABLED: false
JIRA_ENABLED: false

# Disable email notifications. When false, EMAIL_* keys are not required.
# In-app (DB-backed) notifications are unaffected.
EMAIL_ENABLED: false

JOB_VALIDITY_PERIOD_DAYS: 30
```

The keyspace is `argus_tablets`: the AI embedding models are bound to that
name, and the local setup keeps every table in one keyspace.

**`GITHUB_ENABLED: false` / `JIRA_ENABLED: false`** disables all remote
calls to GitHub issue tracking and Jira respectively. In this mode no
credentials are needed for those integrations and attempting to create a
new remote issue returns an error, while all local DB reads continue to
work normally.

> **Note:** `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are only needed
> when `gh` is included in `LOGIN_METHODS`. With password-only login they
> can be omitted entirely.

**`EMAIL_ENABLED: false`** skips instantiation of the email notification
sender entirely. In-app DB-backed notifications still work; no `EMAIL_*`
keys are required.

### 3. Start the database and seed it

```bash
# Start ScyllaDB + vector store. Compose also creates the keyspace.
docker compose -f dev-db/docker-compose.yaml up -d

# Wait for ScyllaDB to be ready (~60-90 seconds)
docker logs -f dev-db-node1-1 2>&1 | grep -m1 "initialization completed"

# Sync schemas, create admin user, populate test data
uv run python dev-db/seed_data.py
```

The seed script creates everything you need in one shot: all table
schemas, an admin user, and synthetic test data. See
[Seed Script Reference](#seed-script-reference) below for details.

### 4. Verify it works

```bash
# Start the backend
uv run uvicorn --factory argus_backend:create_app --port 5000 --reload
```

Open <http://localhost:5000> and log in with `admin` / `admin`.

You should see the "Seed Release" with longevity and performance test
groups populated with runs, events, and results.

> Use `localhost` (not `127.0.0.1`) if you later configure GitHub OAuth,
> since the callback URL is registered against `localhost`.

---

## Database Layout

`dev-db/docker-compose.yaml` runs these services on the bridge network
`172.24.99.0/24`:

| Service        | Address              | Role                                                              |
| -------------- | -------------------- | ----------------------------------------------------------------- |
| `node1`        | `172.24.99.1`        | ScyllaDB, always on, seed of the cluster                          |
| `node2`        | `172.24.99.2`        | ScyllaDB, profile `2-nodes` or `3-nodes`                          |
| `node3`        | `172.24.99.3`        | ScyllaDB, profile `3-nodes`                                       |
| `vector-store` | `172.24.99.10:6080`  | Vector search, reached by ScyllaDB over the bridge network         |
| `config`       | —                    | One-shot: renders `dev-db/scylla.yaml.template` into each node's config volume |
| `keyspaces`    | —                    | One-shot: creates `argus_tablets` with the configured RF          |

Nodes join one at a time; `node2` waits for `node1` to be healthy and
`node3` for `node2`. The `keyspaces` service retries until the cluster has
enough nodes for the replication factor, then exits.

Each node is its own rack (`rack1`, `rack2`, `rack3` in `datacenter1`), so
the keyspace is RF-rack-valid, which ScyllaDB requires before it accepts a
secondary index on a tablets keyspace. That is why `SCYLLA_RF` must be
either `1` or the node count.

Each node mounts its own config volume (`dev-db_node1_config` and so on)
at `/etc/scylla`. The `config` service renders the template into every
volume on each `up`; restart the nodes to pick up a change. The template
also defines the `cassandra` / `cassandra` superuser: ScyllaDB 2026.x
creates none on its own when password authentication is on.

Data lives in named volumes (`dev-db_node1_data` and so on). `down` keeps
them; wipe everything with:

```bash
docker compose -f dev-db/docker-compose.yaml down -v
```

### Settings

Put overrides in `dev-db/.env` (gitignored) or in the shell:

| Variable               | Default    | Meaning                                                   |
| ---------------------- | ---------- | --------------------------------------------------------- |
| `COMPOSE_PROFILES`     | unset      | `2-nodes` or `3-nodes` for a multi-node cluster           |
| `SCYLLA_RF`            | `1`        | Replication factor of `argus_tablets`: `1` or the node count  |
| `SCYLLA_SMP`           | `1`        | Shards per node                                           |
| `SCYLLA_MEMORY`        | `2G`       | Memory per node                                           |
| `SCYLLA_VERSION`       | `2026.3.3` | ScyllaDB image tag                                        |
| `VECTOR_STORE_VERSION` | `1.13.0`   | Vector store image tag                                    |

A three-node cluster with RF 3:

```bash
# dev-db/.env
COMPOSE_PROFILES=3-nodes
SCYLLA_RF=3
SCYLLA_SMP=2
```

The profile can also be given on the command line; the flag goes before
the subcommand and overrides the `.env` value:

```bash
docker compose --profile 3-nodes -f dev-db/docker-compose.yaml up -d
```

The driver only talks to the hosts listed in `SCYLLA_CONTACT_POINTS`, so
list every node you run:

```yaml
SCYLLA_CONTACT_POINTS:
    - 172.24.99.1
    - 172.24.99.2
    - 172.24.99.3
```

### Talking to the database

```bash
docker exec dev-db-node1-1 cqlsh 172.24.99.1 -u cassandra -p cassandra \
  -e "DESCRIBE KEYSPACES"
docker exec dev-db-node1-1 nodetool status
```

---

## Seed Script Reference

The seed script (`dev-db/seed_data.py`) runs standalone -- no backend
required. It connects directly to ScyllaDB using the settings from
`argus_web.yaml`.

### Usage

```bash
# First time: sync schemas + seed data
uv run python dev-db/seed_data.py

# Reset: wipe seed data and recreate from scratch
uv run python dev-db/seed_data.py --force

# Custom credentials
uv run python dev-db/seed_data.py --username dev --password dev123
```

### Options

| Flag                | Description                                                  |
| ------------------- | ------------------------------------------------------------ |
| `--create-keyspace` | Create the keyspace if compose has not (uses `SCYLLA_REPLICATION_FACTOR`) |
| `--force`           | Delete existing seed data before recreating                  |
| `--username NAME`   | Admin username (default: `admin`)                            |
| `--password PASS`   | Admin password (default: `admin`)                            |

### What it creates

| Entity            | Count | Details                                    |
| ----------------- | ----: | ------------------------------------------ |
| Admin user        |     1 | `admin` / `admin` with all roles           |
| Release           |     1 | `seed-release`                             |
| Groups            |     2 | `longevity-tests`, `performance-tests`     |
| Tests             |     6 | 3 per group (SCT plugin)                   |
| Test runs         |    30 | 5 per test, spread over 30 days            |
| SCT events        |   ~90 | 2-4 per run across all severities          |
| Activity events   |   ~42 | Status and investigation changes           |
| Result tables     |     3 | Throughput + latency for performance tests |
| Result data cells |   135 | 3 columns x 3 rows x 5 runs x 3 tests      |
| Best results      |    27 | Per column:row combination                 |
| Graph views       |     3 | One overview per performance test          |
| GitHub issues     |     2 | Linked to failed runs                      |
| Jira issues       |     1 | Linked to failed runs                      |

### Idempotency

The script is safe to run multiple times. On subsequent runs it skips
entities that already exist. Use `--force` to wipe and recreate.

### Without the seed script (manual setup)

Compose already created the keyspace, so syncing the table schemas is one
command:

```bash
uv run python -m argus.backend.cli sync-models
```

This does not create any user or test data. You'll need to register a user
through the UI or another method.

---

## Quick Reference

| Task              | Command                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| Start DB          | `docker compose -f dev-db/docker-compose.yaml up -d`                                                           |
| Wait for DB       | `docker logs -f dev-db-node1-1 2>&1 \| grep -m1 "initialization completed"`                                    |
| Seed (first time) | `uv run python dev-db/seed_data.py`                                                                            |
| Seed (reset)      | `uv run python dev-db/seed_data.py --force`                                                                    |
| Start backend     | `uv run uvicorn --factory argus_backend:create_app --port 5000 --reload`                                       |
| Start frontend    | `yarn build:watch`                                                                                             |
| Run linter        | `uv run ruff check`                                                                                            |
| Run backend tests | `uv run pytest argus/backend/tests`                                                                            |
| Run client tests  | `uv run pytest argus/client/tests`                                                                             |
| Stop DB           | `docker compose -f dev-db/docker-compose.yaml down`                                                            |
| Wipe DB           | `docker compose -f dev-db/docker-compose.yaml down -v`                                                         |

---

## Troubleshooting

### The backend exits on startup with a connection error

The database is not running. Start it first:

```bash
docker compose -f dev-db/docker-compose.yaml up -d
```

Then wait for ScyllaDB to finish initializing (~60-90 seconds) before
starting the backend. Check readiness with:

```bash
docker exec dev-db-node1-1 cqlsh 172.24.99.1 -u cassandra -p cassandra \
  -e "DESCRIBE KEYSPACES"
```

### `KeyError: 'EMAIL_SENDER'`

Your `argus_web.yaml` is missing email keys and `EMAIL_ENABLED` is not
set to `false`. Either add the `EMAIL_*` values or disable email entirely
with `EMAIL_ENABLED: false`.

### The `keyspaces` service keeps retrying

`SCYLLA_RF` is higher than the number of nodes that are up. Lower it, or
enable the matching profile, then run `up -d` again. `docker compose -f
dev-db/docker-compose.yaml logs keyspaces` shows the attempts.

### `Connection error: AuthenticationFailed`

ScyllaDB has authentication enabled. Always use `-u cassandra -p cassandra`
when connecting via `cqlsh`.

### ScyllaDB crashes with `Could not setup Async I/O`

The system `aio-max-nr` limit is too low for the number of CPU cores.
See the [ScyllaDB Docker image docs](https://hub.docker.com/r/scylladb/scylla)
for the formula. Increase it:

```bash
sudo sysctl -w fs.aio-max-nr=1048576
```

To make it permanent, add `fs.aio-max-nr = 1048576` to `/etc/sysctl.conf`.
