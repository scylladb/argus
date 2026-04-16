# Local Development Setup

## Prerequisites

- Python 3.12+
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
docker logs -f dev-db-alpha-1 2>&1 | grep -m1 "initialization completed"

# 2. Start the backend (in one terminal)
FLASK_ENV=development \
  FLASK_APP=argus_backend:start_server \
  CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 \
  uv run flask run

# 3. Start the frontend (in another terminal)
ROLLUP_ENV=development yarn rollup -c --watch

# 4. Open http://localhost:5000 — login with admin/admin
```

When you're done:

```bash
# Stop Flask with Ctrl+C, then stop the database
docker compose -f dev-db/docker-compose.yaml down
```

> The database **must be running** before you start Flask. Flask connects
> to ScyllaDB at startup and will crash immediately if it can't reach it.

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

> **Note:** `uv sync --all-extras` may fail on Python 3.14 due to
> `onnxruntime`. Use the explicit extras above instead.

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
    - 172.18.0.2
SCYLLA_USERNAME: cassandra
SCYLLA_PASSWORD: cassandra
SCYLLA_KEYSPACE_NAME: argus

APP_LOG_LEVEL: INFO
SECRET_KEY: MUSTBEUNIQUE

LOGIN_METHODS:
    - password

# Placeholders -- the app requires these keys at startup even if you
# aren't using GitHub or email features. Without them every API call
# fails with a KeyError.
GITHUB_CLIENT_ID: "dev-placeholder"
GITHUB_CLIENT_SECRET: "dev-placeholder"
GITHUB_ACCESS_TOKEN: "dev-placeholder"

EMAIL_SENDER: "dev@localhost"
EMAIL_SENDER_USER: ""
EMAIL_SENDER_PASS: ""
EMAIL_SERVER: "localhost"
EMAIL_SERVER_PORT: "587"

JOB_VALIDITY_PERIOD_DAYS: 30
```

**Why the placeholders?** `ArgusService.__init__` eagerly reads
`GITHUB_ACCESS_TOKEN`, and `NotificationManagerService` reads the
`EMAIL_*` keys at init time. Without them every API request returns a
`KeyError`.

### 3. Start the database and seed it

```bash
# Pre-create data directories so Docker doesn't create them as root
mkdir -p dev-db/scylla dev-db/alpha-config.d

# Start ScyllaDB + vector store
docker compose -f dev-db/docker-compose.yaml up -d

# Wait for ScyllaDB to be ready (~60-90 seconds)
docker logs -f dev-db-alpha-1 2>&1 | grep -m1 "initialization completed"

# Create keyspaces, sync schemas, create admin user, populate test data
uv run python dev-db/seed_data.py --create-keyspace
```

The seed script creates everything you need in one shot: both keyspaces
(`argus` + `argus_tablets`), all table schemas, an admin user, and
synthetic test data. See [Seed Script Reference](#seed-script-reference)
below for details.

### 4. Verify it works

```bash
# Start the backend
FLASK_ENV=development \
  FLASK_APP=argus_backend:start_server \
  CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 \
  uv run flask run
```

Open <http://localhost:5000> and log in with `admin` / `admin`.

You should see the "Seed Release" with longevity and performance test
groups populated with runs, events, and results.

> Use `localhost` (not `127.0.0.1`) if you later configure GitHub OAuth,
> since the callback URL is registered against `localhost`.

---

## Seed Script Reference

The seed script (`dev-db/seed_data.py`) runs standalone -- no Flask
required. It connects directly to ScyllaDB using the settings from
`argus_web.yaml`.

### Usage

```bash
# First time: create keyspaces + seed data
uv run python dev-db/seed_data.py --create-keyspace

# Reset: wipe seed data and recreate from scratch
uv run python dev-db/seed_data.py --force --create-keyspace

# Custom credentials
uv run python dev-db/seed_data.py --username dev --password dev123
```

### Options

| Flag                | Description                                          |
| ------------------- | ---------------------------------------------------- |
| `--create-keyspace` | Create `argus` + `argus_tablets` keyspaces if needed |
| `--force`           | Delete existing seed data before recreating          |
| `--username NAME`   | Admin username (default: `admin`)                    |
| `--password PASS`   | Admin password (default: `admin`)                    |

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

If you prefer to create the keyspace and sync tables by hand:

```bash
# Create keyspace via CQL
docker exec dev-db-alpha-1 cqlsh 172.18.0.2 -u cassandra -p cassandra \
  -e "CREATE KEYSPACE IF NOT EXISTS argus WITH replication = \
      {'class': 'NetworkTopologyStrategy', 'replication_factor': 1};"

# Sync table schemas via Flask CLI
CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 FLASK_ENV=development \
  FLASK_APP=argus_backend:start_server uv run flask cli sync-models
```

Note: this does **not** create the `argus_tablets` keyspace (needed by AI
embedding models) and does not create any user or test data. You'll need
to register a user through the UI or another method.

---

## Quick Reference

| Task              | Command                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| Pre-create dirs   | `mkdir -p dev-db/scylla dev-db/alpha-config.d` (first time only)                                               |
| Start DB          | `docker compose -f dev-db/docker-compose.yaml up -d`                                                           |
| Wait for DB       | `docker logs -f dev-db-alpha-1 2>&1 \| grep -m1 "initialization completed"`                                    |
| Seed (first time) | `uv run python dev-db/seed_data.py --create-keyspace`                                                          |
| Seed (reset)      | `uv run python dev-db/seed_data.py --force --create-keyspace`                                                  |
| Start backend     | `FLASK_ENV=development FLASK_APP=argus_backend:start_server CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 uv run flask run` |
| Start frontend    | `ROLLUP_ENV=development yarn rollup -c --watch`                                                                |
| Run linter        | `uv run ruff check`                                                                                            |
| Run backend tests | `uv run pytest argus/backend/tests`                                                                            |
| Run client tests  | `uv run pytest argus/client/tests`                                                                             |
| Stop DB           | `docker compose -f dev-db/docker-compose.yaml down`                                                            |

---

## Troubleshooting

### Flask crashes on startup with a connection error

The database is not running. Start it first:

```bash
docker compose -f dev-db/docker-compose.yaml up -d
```

Then wait for ScyllaDB to finish initializing (~60-90 seconds) before
starting Flask. Check readiness with:

```bash
docker exec dev-db-alpha-1 cqlsh 172.18.0.2 -u cassandra -p cassandra \
  -e "DESCRIBE KEYSPACES"
```

### `KeyError: 'EMAIL_SENDER'` or `KeyError: 'GITHUB_ACCESS_TOKEN'`

Your `argus_web.yaml` is missing required keys. The app reads these
eagerly at startup. Add the placeholder values shown in the config
section above.

### ScyllaDB won't start -- permission denied

Docker volumes (`dev-db/scylla/`, `dev-db/alpha-config.d/`) may have
wrong ownership. See the permissions fix in the first-time setup section.

### `Connection error: AuthenticationFailed`

ScyllaDB has authentication enabled. Always use `-u cassandra -p cassandra`
when connecting via `cqlsh`.

### `uv sync --all-extras` fails

Use `uv sync --extra web-backend --extra dev` instead. The `onnxruntime`
dependency may not build on your Python version. If you don't have
Python 3.12 installed, `uv` can fetch it for you:

```bash
uv sync --python 3.12 --extra web-backend --extra dev
```

### ScyllaDB crashes with `Could not setup Async I/O`

The system `aio-max-nr` limit is too low for the number of CPU cores.
See the [ScyllaDB Docker image docs](https://hub.docker.com/r/scylladb/scylla)
for the formula. Increase it:

```bash
sudo sysctl -w fs.aio-max-nr=1048576
```

To make it permanent, add `fs.aio-max-nr = 1048576` to `/etc/sysctl.conf`.
