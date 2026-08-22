# Plan: Migrate from Flask to FastAPI

## Motivation

Argus currently runs on Flask 3.0 with a synchronous request model. As the project grows, several limitations of this architecture become apparent:

- **No native async support**: External calls to GitHub, Jira, Jenkins, and Cassandra block the worker thread, limiting throughput under concurrent load.
- **No built-in background tasks**: CLI commands (`refresh-issues`, `scan-jenkins`) must be invoked externally; there is no in-process task scheduling.
- **Manual request validation**: Route handlers validate payloads with ad-hoc `dict.get()` calls instead of declarative schemas.
- **No auto-generated API docs**: The ~220 endpoints have no machine-readable specification; consumers rely on hand-written `docs/api_usage.md`.

FastAPI addresses all of these through native async/await, built-in BackgroundTasks, Pydantic model validation, and automatic OpenAPI documentation.

---

## Current Architecture Snapshot

| Component | Technology | Files / Location |
|---|---|---|
| WSGI app | Flask 3.0 | `argus_backend.py` |
| Blueprints (5 top-level) | Flask Blueprint | `argus/backend/controller/` |
| Authentication | Flask-Login, PyJWT, GitHub OAuth | `service/user.py`, `controller/auth.py` |
| CSRF protection | Flask-WTF | Forms and session handling |
| Database | scylla-driver / CQLEngine ORM | `argus/backend/db.py`, `models/` |
| Metrics | prometheus-flask-exporter | `argus_backend.py` |
| Deployment | Nginx → uWSGI (4 workers × 100 threads) | `uwsgi.ini`, `Dockerfile` |
| Frontend | Svelte 5 (fetch JSON API) | `frontend/` |
| Tests | pytest | `argus/backend/tests/` |

**Key numbers**: ~220 route definitions, 25 service modules, 11 model files, 34+ test files.

---

## Migration Strategy

### Approach: Test-First, Blueprint-by-Blueprint

A full rewrite is high-risk. Instead, migrate one blueprint at a time while keeping the existing Flask app functional. Use ASGI mounting to run both frameworks in the same process during the transition.

**Critical prerequisite**: This repository has significant test coverage gaps (see
[Test Coverage Gaps](#test-coverage-gaps) below). Every phase **must** begin by writing
integration tests for the endpoints being migrated, verified against the existing Flask
app, before any refactoring begins. The same tests must then pass against FastAPI without
modification.

```
Per-phase workflow (mandatory for every phase):

  1. Audit   ─ List all endpoints to migrate; identify missing tests
  2. Test    ─ Write integration tests for every uncovered endpoint (run against Flask)
  3. Green   ─ All tests pass on Flask; fix any bugs the new tests uncover
  4. Refactor─ Port endpoints to FastAPI
  5. Green   ─ All tests pass on FastAPI without any test changes
  6. Ship    ─ Merge; remove old Flask routes
```

```
Phase 0  ─ Foundation & tooling
Phase 1  ─ API blueprint  (/api/v1)
Phase 2  ─ Auth, Admin, Client blueprints
Phase 3  ─ UI routes (main blueprint)
Phase 4  ─ Remove Flask entirely
```

### Test Coverage Gaps

The following controllers currently have **no endpoint-level test coverage** and must be
covered before their phase begins:

| Controller | Routes | Current Coverage | Phase |
|---|---|---|---|
| `api.py` | ~36 | Partial (results, highlights) | 1 |
| `testrun_api.py` | ~34 | Partial (SCT, assignees, events) | 1 |
| `view_api.py` | ~13 | Partial (highlights only) | 1 |
| `planner_api.py` | ~14 | ❌ None | 1 |
| `team.py` | team CRUD | ❌ None | 1 |
| `notification_api.py` | notifications | ❌ None | 1 |
| `auth.py` | login/logout/OAuth | ❌ None (unit tests for CF Access only) | 2 |
| `admin_api.py` | ~24 | ❌ None | 2 |
| `client_api.py` | client endpoints | Partial | 2 |
| `main.py` | ~30 UI routes | ❌ None | 3 |
| `admin.py` (UI) | admin UI pages | ❌ None | 3 |
| `team_ui.py` | team UI pages | ❌ None | 3 |
| `notifications.py` (UI) | notification pages | ❌ None | 3 |
| `views_widgets/*` | graphs, summary, nemesis | Mostly ❌ | 1 |

---

## Phase 0 — Foundation & Tooling

**Goal**: Set up FastAPI alongside Flask without changing any existing behavior.

### 0.1 Add dependencies

```toml
# pyproject.toml  (web-backend extras)
"fastapi >= 0.115",
"uvicorn[standard] >= 0.34",
"pydantic >= 2.0",
"httpx >= 0.27",               # async HTTP client for GitHub/Jira
"starlette >= 0.45",           # ASGI primitives
"prometheus-fastapi-instrumentator >= 7.0",
```

Remove after full migration:
```
Flask, Flask-WTF, Flask-Login, prometheus-flask-exporter, uwsgi
```

### 0.2 Create the FastAPI application shell

```
argus/backend/app.py            # FastAPI app factory
argus/backend/dependencies.py   # Dependency injection (DB session, current user)
argus/backend/middleware.py      # CORS, error handling, metrics
```

### 0.3 ASGI/WSGI co-hosting during transition

Use Starlette's `WSGIMiddleware` to mount Flask under the new ASGI app so both
can serve traffic during the transition:

```python
# argus_backend.py (transition period)
from starlette.middleware.wsgi import WSGIMiddleware
from argus.backend.app import create_fastapi_app

fastapi_app = create_fastapi_app()
flask_app = create_flask_app()

# All new /api/v1 routes handled by FastAPI; everything else falls through to Flask
fastapi_app.mount("/legacy", WSGIMiddleware(flask_app))
```

### 0.4 CQLEngine & Cassandra async strategy

**This is the biggest blocker for the migration.** CQLEngine is the ORM layer provided by `scylla-driver` and it is entirely synchronous — every `.filter()`, `.get()`, `.all()`, `.save()`, `.delete()`, and `.create()` call uses `session.execute()` internally. The `session.execute_async()` method exists on the low-level `Session` object but is **not used by CQLEngine** at all.

#### Current CQLEngine footprint

| Category | Count | Details |
|---|---|---|
| ORM models | 37 | Defined in `argus/backend/models/` and `plugins/` |
| User-Defined Types | 18 | Nested Cassandra UDTs used in models |
| ORM query sites | ~200+ | `.filter()`, `.get()`, `.all()`, `.save()`, `.delete()` across 21 service files |
| Raw CQL sites | ~35 | `session.execute()` with prepared statements across 14 files |
| ORM-to-raw ratio | ~85 / 15% | Most data access goes through CQLEngine |

Common ORM patterns in use:
- **Query chains**: `.filter(group_id=x).allow_filtering().all()` (~45 sites)
- **Single-row lookups**: `.get(id=x)` (~60 sites)
- **Column projection**: `.only(["col1", "col2"])` (~20 sites)
- **Instance mutation**: `model.field = value; model.save()` (throughout services)
- **Batch writes**: `BatchQuery` (1 site in `service/testrun.py`)
- **Schema sync**: `sync_table()` / `sync_type()` at startup via `db.py`

#### Recommended approach: Keep CQLEngine sync, run in thread pool (Phase 0–2)

Since CQLEngine has no async API and there is no drop-in async replacement for it, the
pragmatic path is to **keep CQLEngine as-is** and offload its blocking calls to a thread
pool so they don't block the asyncio event loop.

FastAPI already handles this automatically: **any route defined with `def` (not `async def`)
runs in a thread-pool executor by default.** This means existing service code that calls
CQLEngine can be used without modification in sync route handlers:

```python
# FastAPI runs sync handlers in a threadpool automatically
@router.get("/test_runs")
def get_test_runs(user: User = Depends(get_current_user)):
    # CQLEngine calls here are blocking, but FastAPI runs this in a thread
    runs = list(SCTTestRun.filter(build_id=build_id).all())
    return {"status": "ok", "response": runs}
```

For `async def` handlers that need to call CQLEngine, use `run_in_executor` explicitly:

```python
import asyncio
from functools import partial

async def async_cql(func, *args, **kwargs):
    """Run a blocking CQLEngine call in the default thread-pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))

# Usage in an async handler
@router.get("/releases")
async def get_releases():
    releases = await async_cql(lambda: list(ArgusRelease.all()))
    return {"status": "ok", "response": releases}
```

#### Raw CQL: async wrapper for `session.execute()`

The ~35 raw CQL sites that call `session.execute()` directly (mostly in `results_service.py`
and plugin modules) can use the driver's built-in `execute_async` with an asyncio bridge:

```python
# argus/backend/db_async.py
async def execute_cql_async(session, query, params=None):
    future = session.execute_async(query, params)
    return await asyncio.wrap_future(future)
```

This covers prepared statements, dynamic CQL, and any custom queries outside CQLEngine.

#### Migration phases for database access

| Phase | Database approach | Risk |
|---|---|---|
| **Phase 0–1** | Keep all CQLEngine sync; use sync `def` handlers (FastAPI threadpool) + `execute_cql_async` for raw CQL | Lowest risk; no ORM changes |
| **Phase 2** | Introduce `async_cql()` helper for `async def` handlers that need CQLEngine alongside other async work | Low risk; opt-in per handler |
| **Phase 3–4** | Evaluate whether to stay on CQLEngine-in-threadpool long-term, or begin migrating hot paths to raw async CQL for performance | Deferred decision |

#### Why not switch away from CQLEngine now?

Replacing CQLEngine would mean rewriting **all 37 models**, **18 UDTs**, and **~200+ query
sites** across the service layer — effectively a full rewrite of the data access tier. This
dwarfs the Flask-to-FastAPI migration itself and should be treated as a separate project if
ever pursued. The threadpool approach lets us migrate the web framework **without touching
the database layer**.

#### Alternative async drivers (future evaluation)

If profiling shows the threadpool approach is a bottleneck (unlikely for this workload), these
options can be evaluated later as a separate initiative:

| Driver | Async support | CQLEngine compat | Notes |
|---|---|---|---|
| `scylla-driver` (current) | `execute_async()` on raw Session | Full CQLEngine ORM | Threadpool wrapping is sufficient |
| `acsylla` | Native asyncio | No ORM, raw CQL only | Would require rewriting all 200+ ORM query sites |
| Custom async ORM layer | Build on `execute_async()` | Partial | High effort; not recommended unless performance-critical |

**Recommendation**: Defer any driver swap. Keep `scylla-driver` + CQLEngine with threadpool
wrapping through the entire FastAPI migration. Revisit only if benchmarks show thread
contention under production load.

### 0.5 Update deployment stack

| Before | After |
|---|---|
| Nginx → uWSGI (WSGI) | Nginx → Uvicorn (ASGI) |
| `uwsgi.ini` | `uvicorn argus_backend:app --workers 4` |
| `Dockerfile` installs uWSGI | `Dockerfile` installs uvicorn |

---

## Phase 1 — Migrate `/api/v1` (API Blueprint)

**Goal**: Port the largest surface area (~36 routes in `api.py`, ~34 in `testrun_api.py`, plus sub-blueprints) to FastAPI routers.

### 1.1 Write missing integration tests (before any refactoring)

Before touching any route, add integration tests for every endpoint in the API blueprint
that lacks coverage. Tests use Flask's test client and run against the existing Flask app:

```python
# argus/backend/tests/test_api_endpoints.py
def test_get_releases(flask_client):
    response = flask_client.get("/api/v1/releases")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"

def test_get_test_runs_requires_auth(flask_client):
    response = flask_client.get("/api/v1/test_runs")
    assert response.status_code in (401, 403)
```

**Checklist for Phase 1 test coverage:**
- [ ] `api.py` — all ~36 routes (currently partial coverage)
- [ ] `testrun_api.py` — all ~34 routes (currently partial)
- [ ] `planner_api.py` — all ~14 routes (currently zero coverage)
- [ ] `team.py` — team CRUD routes (currently zero coverage)
- [ ] `notification_api.py` — notification routes (currently zero coverage)
- [ ] `view_api.py` — all ~13 routes (currently highlights only)
- [ ] `views_widgets/*` — graphs, summary, nemesis stats (mostly uncovered)

**Gate**: All new tests must pass against Flask before proceeding to step 1.2.
If tests uncover existing bugs, fix them in the Flask codebase first.

### 1.2 Create Pydantic request/response models

For every endpoint, define typed models replacing raw `dict` access:

```python
# argus/backend/schemas/testrun.py
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class TestRunSubmitRequest(BaseModel):
    run_id: UUID
    build_id: str
    status: str = Field(pattern="^(passed|failed|error|aborted)$")

class TestRunResponse(BaseModel):
    status: str
    response: dict
```

### 1.3 Convert Flask blueprint to FastAPI router

```python
# Before (Flask)
@bp.route("/test_runs", methods=["GET"])
@api_login_required
def get_test_runs():
    ...

# After (FastAPI)
@router.get("/test_runs", response_model=TestRunListResponse)
async def get_test_runs(user: User = Depends(get_current_user)):
    ...
```

### 1.4 Port authentication to FastAPI dependencies

Replace `@login_required` / `@api_login_required` decorators with FastAPI dependency injection:

```python
# argus/backend/dependencies.py
from fastapi import Depends, HTTPException, Header

async def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401)
    # validate token / session
    return user

async def require_admin(user: User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403)
    return user
```

### 1.5 Port error handling

Replace `bp.register_error_handler(...)` with FastAPI exception handlers:

```python
@app.exception_handler(UserServiceException)
async def handle_user_exception(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "response": str(exc)})
```

### 1.6 Validate — all Phase 1 tests pass on FastAPI

Re-run the full test suite written in step 1.1 against the new FastAPI app. **No test
modifications are allowed** — if a test fails, the FastAPI route must be fixed to match
the original Flask behavior.

```bash
pytest argus/backend/tests/ -v
```

Response format must remain `{"status": "ok"|"error", "response": ...}` to avoid
breaking the Svelte frontend.

---

## Phase 2 — Auth, Admin, Client, and Remaining API Blueprints

### 2.1 Write missing integration tests (before any refactoring)

Cover all endpoints in the blueprints being migrated this phase:

```python
# argus/backend/tests/test_auth_endpoints.py
def test_login_page_renders(flask_client):
    response = flask_client.get("/auth/login")
    assert response.status_code == 200

def test_login_rejects_invalid_credentials(flask_client):
    response = flask_client.post("/auth/login", json={"username": "x", "password": "y"})
    assert response.status_code in (401, 403)
```

**Checklist for Phase 2 test coverage:**
- [ ] `auth.py` — login/logout, OAuth flows, CF Access (currently zero endpoint tests)
- [ ] `admin_api.py` — all ~24 admin routes (currently zero coverage)
- [ ] `client_api.py` — client endpoints (currently partial)

**Gate**: All new tests must pass against Flask before proceeding to step 2.2.

### 2.2 Auth blueprint (`/auth`)

- Replace Flask-Login session management with FastAPI session middleware or JWT-based auth.
- Port GitHub OAuth flow using `httpx.AsyncClient` for non-blocking token exchange.
- Port Cloudflare Access JWT validation (already uses PyJWT, minimal changes).
- Replace Flask-WTF CSRF with FastAPI middleware or header-based CSRF tokens for the remaining form endpoints.

### 2.3 Admin blueprint (`/admin`)

- Convert ~24 admin routes to FastAPI router.
- Use `Depends(require_admin)` for role gating.

### 2.4 Client blueprint

- Convert client-facing API endpoints.
- These are already pure JSON, making them straightforward to port.

### 2.5 Team, Planner, View, and Notification sub-blueprints

- Convert nested blueprints to nested FastAPI routers.
- Maintain URL structure for frontend compatibility.

### 2.6 Validate — all Phase 2 tests pass on FastAPI

Re-run all tests from step 2.1 against FastAPI. **No test modifications allowed.**

---

## Phase 3 — UI Routes (Main Blueprint)

### 3.1 Write missing integration tests (before any refactoring)

UI routes return HTML templates. Tests should verify status codes, redirects, and that
key content is present:

```python
# argus/backend/tests/test_ui_endpoints.py
def test_index_redirects_to_login(flask_client):
    response = flask_client.get("/")
    assert response.status_code in (200, 302)

def test_test_run_page_requires_auth(flask_client):
    response = flask_client.get("/test_runs")
    assert response.status_code in (200, 302)
```

**Checklist for Phase 3 test coverage:**
- [ ] `main.py` — all ~30 UI routes (currently zero coverage)
- [ ] `admin.py` (UI) — admin pages (currently zero coverage)
- [ ] `team_ui.py` — team pages (currently zero coverage)
- [ ] `notifications.py` (UI) — notification pages (currently zero coverage)

**Gate**: All new tests must pass against Flask before proceeding to step 3.2.

### 3.2 Template rendering

FastAPI supports Jinja2 via `Jinja2Templates`. Port the template-rendering routes:

```python
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")

@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
```

### 3.3 Port custom template filters

Register existing Jinja2 filters from `template_filters.py` on the FastAPI template environment:

```python
templates.env.filters["from_timestamp"] = from_timestamp
templates.env.filters["formatted_date"] = formatted_date
# ... remaining filters
```

### 3.4 Static file serving

```python
from fastapi.staticfiles import StaticFiles
app.mount("/s", StaticFiles(directory="public"), name="static")
```

### 3.5 Validate — all Phase 3 tests pass on FastAPI

Re-run all tests from step 3.1 against FastAPI. **No test modifications allowed.**

---

## Phase 4 — Remove Flask & Finalize

### 4.1 Remove Flask dependencies

```toml
# Remove from pyproject.toml
Flask, Flask-WTF, Flask-Login, prometheus-flask-exporter, uwsgi
```

### 4.2 Remove WSGI bridge

Delete `WSGIMiddleware` mount and legacy Flask app factory.

### 4.3 Update deployment configuration

- Replace `uwsgi.ini` with Uvicorn CLI or `gunicorn -k uvicorn.workers.UvicornWorker`.
- Update `Dockerfile` to remove uWSGI build dependencies.
- Update `docker-entrypoint.sh` and `start_argus.sh`.
- Update Nginx config (`docs/config/argus.nginx.conf`) to proxy to Uvicorn socket.

### 4.4 Update documentation

- Update `docs/dev-setup.md` with new local dev commands.
- Update `docs/api_usage.md` or replace with link to auto-generated `/docs` (Swagger UI).
- Update `README.md` and `docs/config/argus.service`.

---

## Background Tasks

One of the primary motivations for this migration. FastAPI provides two built-in mechanisms:

### In-request background tasks

For lightweight post-response work (e.g., sending notifications, updating caches):

```python
from fastapi import BackgroundTasks

@router.post("/test_runs/{run_id}/finish")
async def finish_test_run(run_id: UUID, background_tasks: BackgroundTasks):
    result = await finalize_run(run_id)
    background_tasks.add_task(send_email_notification, run_id)
    background_tasks.add_task(refresh_github_issues, run_id)
    return result
```

### Periodic / scheduled tasks

For operations currently driven by CLI commands (`refresh-issues`, `scan-jenkins`), evaluate:

1. **`asyncio.create_task` with a loop** — simplest for lightweight periodic jobs running in the same process.
2. **APScheduler with AsyncIOScheduler** — for cron-like scheduling within the app process.
3. **Dedicated task queue (arq, Celery)** — if tasks need isolation, retries, or distributed execution.

Recommended starting point: Use FastAPI `BackgroundTasks` for request-triggered work, and `APScheduler` for periodic operations that currently rely on external cron invocations.

---

## Async Opportunities

With FastAPI, these currently-blocking operations can become non-blocking:

| Operation | Current | After Migration |
|---|---|---|
| GitHub API calls | `requests` (sync) | `httpx.AsyncClient` |
| Jira API calls | `requests` (sync) | `httpx.AsyncClient` |
| Jenkins polling | `python-jenkins` (sync) | `httpx.AsyncClient` or async wrapper |
| Cassandra queries (raw CQL) | sync `session.execute()` | `execute_async()` + asyncio bridge |
| Cassandra queries (CQLEngine ORM) | sync CQLEngine API | Keep sync; FastAPI threadpool (see §0.4) |
| Email sending | sync SMTP | `aiosmtplib` or BackgroundTasks |

---

## Testing Strategy

### Principle: Tests are written before refactoring, not after

This repository currently has significant test coverage gaps (10 of 14 controllers listed in
the [Test Coverage Gaps](#test-coverage-gaps) table have no or only partial endpoint tests).
The migration **must not** begin for any blueprint until its endpoints are fully covered by
integration tests that pass against the existing Flask app.

### Test-first workflow (per phase)

```
1. Write integration tests for all endpoints being migrated
2. Run tests against Flask — all must pass
3. If tests expose bugs, fix them in Flask first (separate commits)
4. Refactor endpoints to FastAPI
5. Run the SAME tests against FastAPI — all must pass WITHOUT any test changes
6. If tests fail on FastAPI, the FastAPI code has a bug — fix the route, not the test
```

This ensures behavioral equivalence between the Flask and FastAPI implementations and
catches regressions before they reach production.

### Test infrastructure

- **Flask tests**: Use the existing `flask_client` fixture from `conftest.py`.
- **FastAPI tests**: Use `httpx.AsyncClient` with `ASGITransport` (or FastAPI's `TestClient`).
- **Shared assertions**: Both Flask and FastAPI tests assert the same response structure,
  status codes, and payloads so tests are interchangeable.

```python
# Example: Flask integration test (written first, runs against Flask)
def test_get_test_runs(flask_client):
    response = flask_client.get("/api/v1/test_runs")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"

# Example: Same test adapted for FastAPI (after migration)
def test_get_test_runs(fastapi_client):
    response = fastapi_client.get("/api/v1/test_runs")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

### Test migration order

Match the phase order: API tests → Auth tests → Admin tests → UI tests.

### Coverage target

Every endpoint migrated must have at least one integration test covering:
- Success path (200/201 response with expected shape)
- Auth rejection (401/403 when unauthenticated)
- Invalid input (400/422 for malformed requests where applicable)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Low existing test coverage (10 of 14 controllers lack full endpoint tests) | High | Mandatory test-first step at each phase; no refactoring until tests pass on Flask (see per-phase workflow) |
| Frontend breakage during migration | High | Keep JSON response format identical; co-host both frameworks |
| CQLEngine ORM is sync-only | High | Keep CQLEngine unchanged; use sync `def` handlers (FastAPI threadpool) during Phase 0–2; defer driver replacement (see §0.4) |
| Session/cookie-based auth disruption | Medium | Port Flask-Login sessions to Starlette session middleware with same cookie name/format |
| uWSGI-specific features (touch-reload, stats) | Low | Uvicorn supports similar signals; update ops runbook |
| Large number of routes (~220) | Medium | Migrate blueprint by blueprint with integration tests per phase |
| Template filter compatibility | Low | Jinja2 filters are plain Python functions; register on FastAPI template env |

---

## Estimated Effort

| Phase | Scope | Estimate |
|---|---|---|
| Phase 0 — Foundation | App shell, deps, deployment | 1–2 weeks |
| Phase 1 — API blueprint | Write tests (~100 routes), Pydantic models, port routes, validate | 4–6 weeks |
| Phase 2 — Auth, Admin, Client | Write tests (~60 routes), OAuth flow, port routes, validate | 3–4 weeks |
| Phase 3 — UI routes | Write tests (~30 routes), template routes, static files, validate | 2–3 weeks |
| Phase 4 — Cleanup | Remove Flask, update docs & deployment | 1 week |
| **Total** | | **11–16 weeks** |

> **Note**: Estimates increased from original 8–12 weeks to 11–16 weeks to account for
> the mandatory test coverage work. This is a net positive — the tests protect against
> regressions during and after the migration.

---

## Success Criteria

- [ ] All ~220 existing endpoints have integration tests passing against Flask before migration.
- [ ] All ~220 existing endpoints return identical responses under FastAPI.
- [ ] All integration tests pass against FastAPI **without any test modifications**.
- [ ] Swagger UI auto-generated at `/docs` covering all API endpoints.
- [ ] At least one background task (e.g., issue refresh) runs in-process without CLI invocation.
- [ ] Deployment uses Uvicorn (ASGI) with no Flask or uWSGI dependencies.
- [ ] No regressions in Svelte frontend behavior.

---

## Open Questions

1. **CQLEngine long-term**: After the FastAPI migration is complete, should we benchmark the threadpool approach under production load to decide if migrating hot paths to raw async CQL is worthwhile?
2. **Session storage**: Continue with cookie-based sessions, or move to server-side session store (Redis)?
3. **Task queue**: Is `APScheduler` sufficient for periodic jobs, or do we need a distributed queue like `arq` or Celery?
4. **WebSocket support**: Should we add WebSocket endpoints to replace polling (`/test_runs/poll`) during this migration?
