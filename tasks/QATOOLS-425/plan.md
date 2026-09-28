# QATOOLS-425 — implementation plan

**Spec:** `tasks/QATOOLS-425/spec.md`

## Constraints

- Follow `docs/standards/backend/api.md` for the route, and keep the HTTP call to the health process in a service.
- Follow `docs/standards/frontend/components.md` for the Svelte 5 runes, and `docs/standards/frontend/css.md` for the icon colors.
- Every test under `argus/backend/tests/` needs Docker. The session fixture `argus_db` starts ScyllaDB.
- The backend tests run under `pytest-asyncio` in auto mode. A test that awaits is an `async def`, and an HTTP test of the health app goes through `httpx2.ASGITransport`.
- `gunicorn.conf.py` imports no module under `argus.backend.service.health` and nothing from `qatools_health`.
- Run the verify sequence from the `Commands` section of `CLAUDE.md` before each commit.

## Task 1 — The dependency

**Files:**
- Modify: `pyproject.toml`, the `web-backend` extra and `[tool.uv.sources]`
- Modify: `uv.lock`

- [x] Add `qatools-health ; python_version >= '3.13'` to `web-backend`, and the editable path source.
- [x] Run `uv lock` and `uv sync --all-extras`, and confirm `import qatools_health` works in `.venv`.
- [x] Commit.

## Task 2 — The Argus checks

**Files:**
- Create: `argus/backend/service/health/__init__.py`
- Create: `argus/backend/service/health/checks.py`
- Test: `argus/backend/tests/health/test_checks.py`

**Internals:** `ArgusDatabase` opens `ScyllaCluster.get(config)` in a thread and returns the cqlengine session. It keeps the open task, and a caller that arrives while the open runs awaits that task through `asyncio.shield`, so one open runs at a time. `ScyllaHealthCheck` runs `SELECT release_version FROM system.local` at `LOCAL_ONE` through `execute_async`, bridged to an asyncio future, and counts the live hosts in the cluster metadata. `NginxHealthCheck` is an `HttpHealthCheck` over `HEALTH_NGINX_URL`, `http://127.0.0.1/s/argus.png` by default. `SshKeyLookupHealthCheck` awaits `TunnelService().get_authorized_keys(SENTINEL_FINGERPRINT)` on the health loop. `S3BucketHealthCheck` builds a `boto3` client and calls `head_bucket` in a thread, on a client with a three-second connect timeout, a five-second read timeout and one attempt.

- [x] Write the failing tests: ScyllaDB answers HEALTHY against `argus_db`, a database that raises gives UNHEALTHY, some hosts down give DEGRADED, the sentinel lookup answers HEALTHY, `head_bucket` through a botocore `Stubber` gives HEALTHY and a `404` gives UNHEALTHY, and the nginx URL.
- [ ] Run them and confirm the failure.
- [x] Write the checks.
- [ ] Run the verify sequence.
- [x] Commit.

## Task 3 — The health process

**Files:**
- Create: `argus/backend/service/health/runner.py`
- Create: `argus/backend/service/health/app.py`
- Create: `argus/backend/service/health/__main__.py`
- Create: `argus/backend/service/health/logs.py`
- Create: `argus/backend/service/health/listener.py`
- Test: `argus/backend/tests/health/test_runner.py`
- Test: `argus/backend/tests/health/test_app.py`
- Test: `argus/backend/tests/health/test_logs.py`
- Test: `argus/backend/tests/health/test_listener.py`

**Internals:** `build_runner(config)` registers the checks of the spec table, with the conditions the table names, under `service="argus"` and the `argus-alm` package version. `build_app(runner, registry)` answers `/health`, `/health/ready` and `/metrics` from `runner.snapshot()`, `runner.status` and `generate_latest(registry)`. `main()` removes `PROMETHEUS_MULTIPROC_DIR`, loads the config, sets up logging, and runs the runner and a uvicorn server on `HEALTH_HOST:HEALTH_PORT` on one loop. A reader on the life pipe from `argv[1]` sets the shutdown event at EOF. SIGTERM and SIGINT set it too. A daemon timer calls `os._exit(1)` 20 seconds after the shutdown event.

- [x] Write the failing tests: the registered names for a full config and for a config with no Jenkins, GitHub or Jira, one `s3:<bucket>` per bucket, `/health` answers 200 with the checks, `/health/ready` answers 503 while a critical check is UNHEALTHY and 200 with `degraded` while only an important one fails, and `/metrics` carries `healthcheck_status{service="argus"}`.
- [ ] Run them and confirm the failure.
- [x] Write the runner, the app and the entry point.
- [ ] Run the verify sequence.
- [x] Commit.

## Task 4 — The gunicorn hooks

**Files:**
- Modify: `gunicorn.conf.py`
- Modify: `argus_web.example.yaml`
- Test: `argus/backend/tests/health/test_gunicorn_hooks.py`

**Internals:** `when_ready(server)` reads `HEALTH_ENABLED` from `argus_web.yaml`, opens a life pipe and a done pipe, and starts `[sys.executable, "-m", "argus.backend.service.health", <life fd>]` through `/bin/sh -c '"$@" &'` with `start_new_session=True`. It keeps the write end of the life pipe and the read end of the done pipe on `server.health_pipes`. `post_fork` closes both in each worker. `on_exit(server)` closes the life pipe and waits up to `graceful_timeout` for the done pipe to close. `on_reload(server)` closes the life pipe without a wait and calls `when_ready`.

- [x] Write the failing tests over the module loaded with `runpy.run_path`: no `Popen` while `HEALTH_ENABLED` is false or absent, one detached `Popen` with the module command while it is true, a real process whose parent is not the test process, and `on_exit` closes the pipe and waits.
- [ ] Run them and confirm the failure.
- [x] Write the hooks and the example keys.
- [ ] Run the verify sequence.
- [x] Commit.

## Task 5 — The summary route

**Files:**
- Create: `argus/backend/service/health_service.py`
- Create: `argus/backend/controller/health_api.py`
- Modify: `argus/backend/controller/api.py`, the import and the router list
- Modify: `docs/api_usage.md`
- Test: `argus/backend/tests/health/test_health_api.py`

**Internals:** `await HealthSummaryService(config).get_summary()` returns `{"enabled", "status", "failing"}`. It answers `enabled: false` with no request when `HEALTH_ENABLED` is off. It gets `http://<host>:<port>/health` through `httpx2.AsyncClient` with a two-second timeout, and maps a transport error or a status other than 200 to `unknown`. It drops the `pending` checks. `failing` holds the name, the severity and the status of each remaining check that is not HEALTHY. `settled_status` computes the status from the remaining checks with the aggregate rule of the runner. The route `GET /api/v1/health/summary`, named `api.health.get_summary`, depends on `api_current_user`.

- [x] Write the failing tests: disabled, a healthy answer with no failing check, a degraded answer that names the failing check, an unreachable health process as `unknown`, and `0.0.0.0` mapped to `127.0.0.1`.
- [ ] Run them and confirm the failure.
- [x] Write the service and the route.
- [ ] Run the verify sequence.
- [x] Commit.

## Task 6 — The navigation bar icon

**Files:**
- Create: `frontend/Common/HealthIndicator.svelte`
- Create: `frontend/health-indicator.js`
- Modify: `vite.config.ts`, the `healthIndicator` entry
- Modify: `templates/partials/nav_bar.html.j2`, a `#healthIndicator` mount for a signed-in user
- Modify: `templates/base.html.j2`, the bundle script
- Test: `frontend/Common/HealthIndicator.test.ts`

**Internals:** the component reads the summary on mount and every five minutes. It shows no icon while `enabled` is false or `status` is `healthy`. It shows `fa-heartbeat` in red for `unhealthy`, yellow for `degraded` and grey for `unknown`, with a `title` and an `aria-label` that name the failing checks.

- [x] Write the failing tests: no icon for healthy and for disabled, one icon per status with its class, and the failing names in the label.
- [ ] Run them and confirm the failure.
- [x] Write the component, the entry and the template changes.
- [ ] Run the verify sequence and `yarn build`.
- [x] Commit.

## Task 7 — The documents

**Files:**
- Modify: `docs/project/architecture.md`
- Modify: `AGENTS.md`
- Modify: `docs/deployment.md`, the new config keys and the port

- [ ] Describe the health process, its port and its routes, and the summary route.
- [ ] Run the verify sequence.
- [ ] Commit.
