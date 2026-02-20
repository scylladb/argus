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

### Approach: Incremental, Blueprint-by-Blueprint

A full rewrite is high-risk. Instead, migrate one blueprint at a time while keeping the existing Flask app functional. Use ASGI mounting to run both frameworks in the same process during the transition.

```
Phase 0  ─ Foundation & tooling
Phase 1  ─ API blueprint  (/api/v1)
Phase 2  ─ Auth, Admin, Client blueprints
Phase 3  ─ UI routes (main blueprint)
Phase 4  ─ Remove Flask entirely
```

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

### 0.4 Async Cassandra driver setup

The existing `scylla-driver` already supports asyncio via `cassandra.cluster.Session.execute_async`.
Wrap it in an async helper:

```python
# argus/backend/db_async.py
async def execute_async(session, query, params=None):
    loop = asyncio.get_event_loop()
    future = session.execute_async(query, params)
    return await asyncio.wrap_future(future, loop=loop)
```

Alternatively, evaluate adopting the `acsylla` pure-async driver later if performance warrants it.

### 0.5 Update deployment stack

| Before | After |
|---|---|
| Nginx → uWSGI (WSGI) | Nginx → Uvicorn (ASGI) |
| `uwsgi.ini` | `uvicorn argus_backend:app --workers 4` |
| `Dockerfile` installs uWSGI | `Dockerfile` installs uvicorn |

---

## Phase 1 — Migrate `/api/v1` (API Blueprint)

**Goal**: Port the largest surface area (~36 routes in `api.py`, ~34 in `testrun_api.py`, plus sub-blueprints) to FastAPI routers.

### 1.1 Create Pydantic request/response models

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

### 1.2 Convert Flask blueprint to FastAPI router

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

### 1.3 Port authentication to FastAPI dependencies

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

### 1.4 Port error handling

Replace `bp.register_error_handler(...)` with FastAPI exception handlers:

```python
@app.exception_handler(UserServiceException)
async def handle_user_exception(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "response": str(exc)})
```

### 1.5 Validate with existing tests

Run `pytest argus/backend/tests/` after each converted controller. Response format must remain `{"status": "ok"|"error", "response": ...}` to avoid breaking the Svelte frontend.

---

## Phase 2 — Auth, Admin, Client, and Remaining API Blueprints

### 2.1 Auth blueprint (`/auth`)

- Replace Flask-Login session management with FastAPI session middleware or JWT-based auth.
- Port GitHub OAuth flow using `httpx.AsyncClient` for non-blocking token exchange.
- Port Cloudflare Access JWT validation (already uses PyJWT, minimal changes).
- Replace Flask-WTF CSRF with FastAPI middleware or header-based CSRF tokens for the remaining form endpoints.

### 2.2 Admin blueprint (`/admin`)

- Convert ~24 admin routes to FastAPI router.
- Use `Depends(require_admin)` for role gating.

### 2.3 Client blueprint

- Convert client-facing API endpoints.
- These are already pure JSON, making them straightforward to port.

### 2.4 Team, Planner, View, and Notification sub-blueprints

- Convert nested blueprints to nested FastAPI routers.
- Maintain URL structure for frontend compatibility.

---

## Phase 3 — UI Routes (Main Blueprint)

### 3.1 Template rendering

FastAPI supports Jinja2 via `Jinja2Templates`. Port the template-rendering routes:

```python
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")

@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
```

### 3.2 Port custom template filters

Register existing Jinja2 filters from `template_filters.py` on the FastAPI template environment:

```python
templates.env.filters["from_timestamp"] = from_timestamp
templates.env.filters["formatted_date"] = formatted_date
# ... remaining filters
```

### 3.3 Static file serving

```python
from fastapi.staticfiles import StaticFiles
app.mount("/s", StaticFiles(directory="public"), name="static")
```

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
| Cassandra queries | sync `session.execute()` | `session.execute_async()` + asyncio bridge |
| Email sending | sync SMTP | `aiosmtplib` or BackgroundTasks |

---

## Testing Strategy

### Approach

- Use `httpx.AsyncClient` with FastAPI's `TestClient` (backed by `httpx`) for endpoint tests.
- Migrate existing pytest fixtures incrementally; keep `conftest.py` pattern.
- Maintain response format compatibility: `{"status": "ok"|"error", "response": ...}`.

### Test migration order

Match the phase order: API tests → Auth tests → Admin tests → UI tests.

```python
# Example: FastAPI test
from httpx import AsyncClient, ASGITransport

async def test_get_test_runs(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/test_runs")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Frontend breakage during migration | High | Keep JSON response format identical; co-host both frameworks |
| CQLEngine ORM compatibility | Medium | CQLEngine is sync-only; use thread-pool executor for async wrapping until a full async driver is adopted |
| Session/cookie-based auth disruption | Medium | Port Flask-Login sessions to Starlette session middleware with same cookie name/format |
| uWSGI-specific features (touch-reload, stats) | Low | Uvicorn supports similar signals; update ops runbook |
| Large number of routes (~220) | Medium | Migrate blueprint by blueprint with integration tests per phase |
| Template filter compatibility | Low | Jinja2 filters are plain Python functions; register on FastAPI template env |

---

## Estimated Effort

| Phase | Scope | Estimate |
|---|---|---|
| Phase 0 — Foundation | App shell, deps, deployment | 1–2 weeks |
| Phase 1 — API blueprint | ~100 routes, Pydantic models, auth deps | 3–4 weeks |
| Phase 2 — Auth, Admin, Client | ~60 routes, OAuth flow | 2–3 weeks |
| Phase 3 — UI routes | ~30 template routes, static files | 1–2 weeks |
| Phase 4 — Cleanup | Remove Flask, update docs & deployment | 1 week |
| **Total** | | **8–12 weeks** |

---

## Success Criteria

- [ ] All ~220 existing endpoints return identical responses under FastAPI.
- [ ] Existing pytest suite passes against FastAPI test client.
- [ ] Swagger UI auto-generated at `/docs` covering all API endpoints.
- [ ] At least one background task (e.g., issue refresh) runs in-process without CLI invocation.
- [ ] Deployment uses Uvicorn (ASGI) with no Flask or uWSGI dependencies.
- [ ] No regressions in Svelte frontend behavior.

---

## Open Questions

1. **Async Cassandra driver**: Should we adopt `acsylla` for a fully async driver, or is wrapping `execute_async` sufficient?
2. **Session storage**: Continue with cookie-based sessions, or move to server-side session store (Redis)?
3. **Task queue**: Is `APScheduler` sufficient for periodic jobs, or do we need a distributed queue like `arq` or Celery?
4. **WebSocket support**: Should we add WebSocket endpoints to replace polling (`/test_runs/poll`) during this migration?
