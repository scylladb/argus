---
status: in_progress
domain: api
created: 2026-03-03
last_updated: 2026-04-23
owner: null
---

# API Tests Implementation Plan

## Background

Argus is planning a major refactor: moving from Flask to FastAPI and replacing CQLEngine with the
[coodie](https://github.com/scylladb/coodie) project. To guarantee that no regressions are
introduced during the refactor, every public API endpoint must have an integration test that:

1. Exercises the endpoint over HTTP (not through ORM or service-layer calls).
2. Asserts on the JSON response structure and values only—never on CQLEngine model objects.
3. Uses a real ScyllaDB instance (no mocks).
4. Is fully isolated: every test creates its own unique identifiers (UUIDs) so tests cannot
   interfere with each other.
5. Requires **minimal or zero changes** after the Flask → FastAPI migration.

The existing tests under `argus/backend/tests/sct_api/test_sct_api.py` already partially cover the
SCT plugin endpoints and serve as the reference style. The current weaknesses are:

- Some tests still query `SCTTestRun.get(id=…)` to verify state, which couples them to CQLEngine.
- There is no coverage of many endpoint groups (Client API, Testrun API, Release/Group/Test API,
  Admin API, etc.).

---

## Key Design Decisions

### 1. HTTP client: use `httpx` instead of Flask test client

Flask's `FlaskClient` is a WSGI-only test helper; it will break when the app migrates to FastAPI/ASGI.

Replace it with [`httpx`](https://www.python-httpx.org/), which supports both WSGI and ASGI
transports through a thin adapter:

```python
# Flask (current / WSGI)
import httpx
transport = httpx.WSGITransport(app=flask_app)
client = httpx.Client(transport=transport, base_url="http://testserver")

# FastAPI (future / ASGI) — only this line changes
transport = httpx.ASGITransport(app=fastapi_app)
client = httpx.Client(transport=transport, base_url="http://testserver")
```

All tests call `client.get(…)` / `client.post(…)` exactly the same way in both cases.
The `client` fixture in `conftest.py` is the **only** place that needs to change after the migration.

### 2. Assert on JSON responses only

Every assertion must be made against `response.json()` keys and values. CQLEngine model queries
(`Model.get(id=…)`) are **not allowed** in new tests. If you need to verify that a write
was persisted, use the corresponding read/GET endpoint to fetch the object and assert on its fields.

```python
# ✅ allowed
resp = client.get(f"/api/v1/client/testrun/scylla-cluster-tests/{run_id}/get")
assert resp.json()["response"]["status"] == "created"

# ❌ forbidden in new tests
run = SCTTestRun.get(id=run_id)
assert run.status == "created"
```

### 3. Test isolation via unique UUIDs

Every test that creates a run, test, group, or release generates a fresh `uuid4()`. Session-scoped
fixtures are allowed only for resources that are truly shared and read-only (e.g., a release and
group hierarchy). Mutable resources (individual test runs) must use function-scoped fixtures.

### 4. Authentication

Keep the existing approach: patch `argus.backend.service.user.load_logged_in_user` at the session
level (already done in the top-level `conftest.py`) so requests are treated as authenticated.
New tests must **not** mock any service layer beyond the auth mechanism.

### 5. Pytest marker

Tag all tests that require a running ScyllaDB instance with `@pytest.mark.docker_required` (already
declared in `pyproject.toml`) so they can be excluded in environments without Docker.

---

## Repository Structure

```
argus/backend/tests/
├── conftest.py                      # shared fixtures (argus_db, argus_app, http_client, …)
├── sct_api/
│   └── test_sct_api.py              # ✅ partially done — extend & migrate to httpx
├── client_api/
│   ├── __init__.py
│   └── test_client_api.py           # NEW
├── testrun_api/
│   ├── __init__.py
│   └── test_testrun_api.py          # NEW
├── release_api/
│   ├── __init__.py
│   └── test_release_api.py          # NEW
├── admin_api/
│   ├── __init__.py
│   └── test_admin_api.py            # NEW
├── driver_matrix_api/
│   ├── __init__.py
│   └── test_driver_matrix_api.py    # NEW
└── sct_events/
    └── ...                          # existing, keep as-is
```

---

## `conftest.py` Changes

### Add `http_client` fixture

```python
import httpx

@fixture(scope="session")
def http_client(argus_app) -> httpx.Client:
    """
    Framework-agnostic HTTP client.
    Swap WSGITransport for ASGITransport after the FastAPI migration.
    """
    transport = httpx.WSGITransport(app=argus_app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client
```

The existing `flask_client` fixture can remain for backward compatibility while old tests are being
migrated. New tests should use `http_client`.

### Helper: `api_post` / `api_get`

Add two thin helpers to `conftest.py` to reduce boilerplate and make the common content-type header
implicit:

```python
def api_post(client: httpx.Client, path: str, payload: dict) -> httpx.Response:
    return client.post(path, json=payload)

def api_get(client: httpx.Client, path: str, **params) -> httpx.Response:
    return client.get(path, params=params)
```

---

## Test Modules

### `test_client_api.py` — `/api/v1/client/…`

| Endpoint                                                     | Method | Test name                     |
| ------------------------------------------------------------ | ------ | ----------------------------- |
| `/client/testrun/{run_type}/submit`                          | POST   | `test_submit_run`             |
| `/client/testrun/{run_type}/{run_id}/get`                    | GET    | `test_get_run`                |
| `/client/testrun/{run_type}/{run_id}/heartbeat`              | POST   | `test_heartbeat`              |
| `/client/testrun/{run_type}/{run_id}/get_status`             | GET    | `test_get_status`             |
| `/client/testrun/{run_type}/{run_id}/set_status`             | POST   | `test_set_status`             |
| `/client/testrun/{run_type}/{run_id}/update_product_version` | POST   | `test_update_product_version` |
| `/client/testrun/{run_type}/{run_id}/logs/submit`            | POST   | `test_submit_logs`            |
| `/client/{run_id}/config/submit`                             | POST   | `test_submit_config`          |
| `/client/{run_id}/config/all`                                | GET    | `test_get_all_configs`        |
| `/client/testrun/{run_type}/{run_id}/finalize`               | POST   | `test_finalize_run`           |

Each test verifies `response.status_code == 200` and `response.json()["status"] == "ok"`.
Tests that mutate state verify the mutation via a paired GET endpoint.

Example flow for `test_set_status`:

```python
def test_set_status(http_client, sct_run_id):
    resp = http_client.post(
        f"/api/v1/client/testrun/scylla-cluster-tests/{sct_run_id}/set_status",
        json={"new_status": "failed", "schema_version": "v8"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Read back via API — no ORM
    get_resp = http_client.get(
        f"/api/v1/client/testrun/scylla-cluster-tests/{sct_run_id}/get_status"
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["response"] == "failed"
```

### `test_sct_api.py` (extended) — `/api/v1/client/sct/…`

Existing tests cover:
`packages/submit`, `screenshots/submit`, `sct_runner/set`, `resource/create`,
`resource/{name}/shards`, `resource/{name}/update`, `resource/{name}/terminate`,
`nemesis/submit`, `nemesis/finalize`, `events/submit` (legacy), `stress_cmd/submit`,
`gemini/submit`, `junit/submit`.

**New tests to add:**

| Endpoint                             | Method | Test name                         |
| ------------------------------------ | ------ | --------------------------------- |
| `/{run_id}/events/get`               | GET    | `test_get_events`                 |
| `/{run_id}/events/{severity}/get`    | GET    | `test_get_events_by_severity`     |
| `/{run_id}/events/{severity}/count`  | GET    | `test_count_events_by_severity`   |
| `/{run_id}/event/submit` (new-style) | POST   | `test_submit_single_event`        |
| `/{run_id}/performance/submit`       | POST   | `test_submit_performance_results` |
| `/{run_id}/performance/history`      | GET    | `test_get_performance_history`    |
| `/{run_id}/stress_cmd/get`           | GET    | `test_get_stress_commands`        |
| `/similar_runs_info`                 | POST   | `test_similar_runs_info`          |

For all new tests, verification must use the paired GET endpoint rather than direct DB queries.

Example:

```python
def test_get_events(http_client, sct_run_id_with_events):
    resp = http_client.get(f"/api/v1/client/sct/{sct_run_id_with_events}/events/get")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["response"], list)
    assert len(body["response"]) >= 1
    first = body["response"][0]
    assert "severity" in first
    assert "messages" in first or "message" in first
```

### `test_testrun_api.py` — `/api/v1/run/…` and `/api/v1/test/…`

| Endpoint                                                   | Method | Test name                       |
| ---------------------------------------------------------- | ------ | ------------------------------- |
| `/test/{test_id}/runs`                                     | GET    | `test_get_runs_for_test`        |
| `/run/{run_type}/{run_id}`                                 | GET    | `test_get_testrun`              |
| `/run/{run_id}/activity`                                   | GET    | `test_testrun_activity`         |
| `/run/{test_id}/{run_id}/fetch_results`                    | GET    | `test_fetch_results`            |
| `/test/{test_id}/run/{run_id}/status/set`                  | POST   | `test_set_testrun_status`       |
| `/test/{test_id}/run/{run_id}/investigation_status/set`    | POST   | `test_set_investigation_status` |
| `/test/{test_id}/run/{run_id}/assignee/set`                | POST   | `test_set_assignee`             |
| `/run/{run_id}/comments`                                   | GET    | `test_get_comments`             |
| `/test/{test_id}/run/{run_id}/comments/submit`             | POST   | `test_submit_comment`           |
| `/comment/{comment_id}/get`                                | GET    | `test_get_comment_by_id`        |
| `/test/{test_id}/run/{run_id}/comment/{comment_id}/update` | POST   | `test_update_comment`           |
| `/test/{test_id}/run/{run_id}/comment/{comment_id}/delete` | POST   | `test_delete_comment`           |

These tests require a run to already exist. They should reuse the `sct_run_id` fixture from
`conftest.py` and use the `fake_test` / `release` / `group` hierarchy fixtures.

Example:

```python
def test_set_testrun_status(http_client, fake_test, sct_run_id):
    test_id = str(fake_test.id)
    resp = http_client.post(
        f"/api/v1/test/{test_id}/run/{sct_run_id}/status/set",
        json={"status": "failed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Read back
    run_resp = http_client.get(f"/api/v1/run/scylla-cluster-tests/{sct_run_id}")
    assert run_resp.status_code == 200
    assert run_resp.json()["response"]["status"] == "failed"
```

### `test_release_api.py` — `/api/v1/releases`, `/api/v1/groups`, `/api/v1/tests`, `/api/v1/release/…`

| Endpoint                        | Method | Test name              |
| ------------------------------- | ------ | ---------------------- |
| `/releases`                     | GET    | `test_list_releases`   |
| `/groups`                       | GET    | `test_list_groups`     |
| `/tests`                        | GET    | `test_list_tests`      |
| `/release/{release_id}/details` | GET    | `test_release_details` |
| `/group/{group_id}/details`     | GET    | `test_group_details`   |
| `/test/{test_id}/details`       | GET    | `test_test_details`    |
| `/release/stats/v2`             | GET    | `test_release_stats`   |
| `/test-info`                    | GET    | `test_test_info`       |
| `/test-results`                 | GET    | `test_test_results`    |
| `/users`                        | GET    | `test_list_users`      |
| `/version`                      | GET    | `test_version`         |

These are read-only tests. They use existing session-scoped `release`, `group`, `fake_test`
fixtures and assert that the response shape is correct.

### `test_admin_api.py` — `/api/v1/…` (admin operations)

| Endpoint                | Method | Test name                   |
| ----------------------- | ------ | --------------------------- |
| `/release/create`       | POST   | `test_admin_create_release` |
| `/release/edit`         | POST   | `test_admin_edit_release`   |
| `/release/delete`       | POST   | `test_admin_delete_release` |
| `/group/create` (admin) | POST   | `test_admin_create_group`   |
| `/group/update`         | POST   | `test_admin_update_group`   |
| `/group/delete`         | POST   | `test_admin_delete_group`   |
| `/test/create` (admin)  | POST   | `test_admin_create_test`    |
| `/test/update`          | POST   | `test_admin_update_test`    |
| `/test/delete`          | POST   | `test_admin_delete_test`    |
| `/releases/get`         | GET    | `test_admin_get_releases`   |
| `/groups/get`           | GET    | `test_admin_get_groups`     |
| `/tests/get`            | GET    | `test_admin_get_tests`      |
| `/users` (admin)        | GET    | `test_admin_list_users`     |

Each create/update/delete test creates its own isolated entity (unique name / UUID).

### `test_driver_matrix_api.py` — `/api/v1/client/driver_matrix/…`

| Endpoint                       | Method | Test name                            |
| ------------------------------ | ------ | ------------------------------------ |
| `/driver_matrix/result/submit` | POST   | `test_submit_driver_matrix_result`   |
| `/driver_matrix/result/fail`   | POST   | `test_fail_driver_matrix_result`     |
| `/driver_matrix/env/submit`    | POST   | `test_submit_driver_matrix_env`      |
| `/driver_matrix/test_report`   | GET    | `test_get_driver_matrix_test_report` |

These tests require a Driver Matrix run to be submitted first. A `driver_matrix_run_id` fixture
should be created analogous to `sct_run_id`.

---

## Existing Test Migration Guide

The following changes are needed on existing tests in `test_sct_api.py` to align with the new
rules (should be applied as part of this work):

1. Replace `flask_client.post(…)` / `flask_client.get(…)` calls with `http_client.post(…)` /
   `http_client.get(…)`. `httpx` returns a `Response` whose `.json()` is a method call (not a
   property), and `.status_code` is an integer.

2. Remove all `SCTTestRun.get(id=…)` queries. Replace each one with a GET request to the
   corresponding read endpoint and assert on the JSON response.

3. The `sct_run_id` fixture should remain function-scoped (already is) so each test has its own
   run.

---

## Testing Infrastructure Requirements

- `httpx` must be added to `pyproject.toml` as a test dependency (`[dependency-groups] dev`).
- `httpx` version ≥ 0.27 recommended (supports both `WSGITransport` and `ASGITransport`).
- No additional packages are required.

---

## Rollout Order (suggested)

1. **Infrastructure**: Update `conftest.py` to add `http_client` fixture; add `httpx` dependency.
2. **Migrate existing**: Update `test_sct_api.py` to use `http_client` and remove ORM assertions.
3. **Client API**: Implement `test_client_api.py`.
4. **Testrun API**: Implement `test_testrun_api.py`.
5. **SCT extensions**: Add missing SCT endpoint tests.
6. **Release API**: Implement `test_release_api.py`.
7. **Admin API**: Implement `test_admin_api.py`.
8. **Driver Matrix API**: Implement `test_driver_matrix_api.py`.

---

## Success Criteria

- All listed endpoints have at least one happy-path test.
- No test imports or calls any CQLEngine model directly for verification.
- The test suite passes with zero changes after replacing `WSGITransport` with `ASGITransport`
  (i.e., after the FastAPI migration).
- Each test run is self-contained: running the same test twice with a fresh database produces the
  same result.

---

## Controller Coverage Matrix

This section tracks the per-controller integration-test coverage for the work that exercises every
public Flask blueprint (controllers under `argus/backend/controller/` and
`argus/backend/plugins/*/controller.py`). The work is being delivered as a sequence of small
commits — one (or two, when scope demands it) per controller module — using the `flask_client`
fixture and the `test_sct_api.py` style as the reference pattern. JSON-first verification is
mandatory; ORM (`Model.get(...)`) fallback is allowed only when no GET endpoint surfaces the
mutation.

| #   | Controller                                                | Test module                                                       | Status     | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| --- | --------------------------------------------------------- | ----------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `argus/backend/plugins/driver_matrix_tests/controller.py` | `argus/backend/tests/driver_matrix_api/test_driver_matrix_api.py` | `complete` | All 4 endpoints + 2 error paths. Verified via paired GET endpoints; `result/fail` and `env/submit` use the generic `GET /api/v1/run/<run_type>/<run_id>` (which exposes every persisted field via `dict(run.items())`), so no ORM fallback is needed.                                                                                                                                                                                                                                                                      |
| 2   | `argus/backend/plugins/sct/controller.py` (extensions)    | `argus/backend/tests/sct_api/test_sct_api.py`                     | `complete` | Added: single + batch event submit (new-style), get-by-severity, count-by-severity, stress_cmd get, similar_events (empty), similar_runs_info (success + 2 error paths). Performance endpoints intentionally skipped (deprecated). Commit `fbfacae`.                                                                                                                                                                                                                                                                       |
| 3   | `argus/backend/controller/client_api.py`                  | `argus/backend/tests/client_api/test_client_api.py`               | `complete` | Added: submit_run+get, get_run unknown, run_info success+error, heartbeat, get/set_status, update_product_version, logs (dedup), finalize, pytest submit, pytest stats avg, render email report (sender mocked). SSH/config/email-send routes covered elsewhere.                                                                                                                                                                                                                                                           |
| 4   | `argus/backend/controller/testrun_api.py`                 | `argus/backend/tests/testrun_api/test_testrun_api.py`             | `partial`  | Added: get_type, get_testrun (+null), set_status (+missing), investigation_status (+missing), assignee set/clear/missing (notification mocked), comments (post/get/single/unknown/update/delete), activity, fetch_results, get_runs_by_test_id_run_id, ignore_jobs (+empty reason), pytest results & stats. Deferred to follow-up: issues submit/get/delete (GitHub/Jira mocks), Jenkins routes, log/screenshot S3 redirects, terminate_stuck_runs.                                                                        |
| 5   | `argus/backend/controller/api.py` (releases/groups/tests) | `argus/backend/tests/api/test_release_api.py`                     | `complete` | 38 tests covering `/version`, `/releases`, `/release/<id>/{details,versions,images,pytest/results}`, `/release/{activity,planner/data,planner/comment/get/test}`, schedules CRUD (submit/update/delete/comment-update/assignee-update), `/release/assignees/{groups,tests}`, `/release/stats/v2`, `/release/create` (plus duplicate path), `/groups`, `/tests`, `/group                                                                                                                                                    | /test/<id>/details`, `/test/<id>/set_plugin`, `/test-info`. Conftest gained `GITHUB_ACCESS_TOKEN`test value (required by`ArgusService.**init**`). |
| 6   | `argus/backend/controller/api.py` (users/jobs/polls)      | `argus/backend/tests/api/test_users_jobs_api.py`                  | `complete` | 17 tests covering `/users`, `/user/token` (stable across calls), `/user/{jobs,planned_jobs}`, `/test_runs/poll` (recent + dedup with `additionalRuns[]`), `/test_run/poll` (success + unknown + empty), `/artifact/resolveSize` (HTTP HEAD mocked, success/error/missing-link), `/zeus/<endpoint>` error paths (missing host, missing token), `/test_run/comment/get` (unknown/missing/round-trip via comments/submit). Real S3/Zeus calls not exercised; happy-path Zeus proxy deferred until a Zeus mock fixture exists. |
| 7   | `argus/backend/controller/api.py` (graph views)           | `argus/backend/tests/api/test_graphs_api.py`                      | `complete` | 7 tests covering `/create-graph-view`, `/update-graph-view` (success + unknown id), and `/test-results` GET (default + date range + missing testId) and HEAD (404 on no results). Round-trip via `/test-results` `graph_views` list (no ORM fallback).                                                                                                                                                                                                                                                                     |
| 8   | `argus/backend/controller/admin_api.py` (releases)        | `argus/backend/tests/admin_api/test_admin_release_api.py`         | `complete` | 11 tests covering `/admin/api/v1/release/{create,set_perpetual,set_state,set_dormant,edit,delete}` (success + duplicate/unknown-id error paths) and `/admin/api/v1/releases/get`. Verified via `/api/v1/release/<id>/details` (no ORM). Also asserts JSON content-type validation.                                                                                                                                                                                                                                         |
| 9   | `argus/backend/controller/admin_api.py` (groups/tests)    | `argus/backend/tests/admin_api/test_admin_group_test_api.py`      | `complete` | 16 tests covering `/group/{create,update,delete}` (delete cascades + relocates), `/test/{create,update,delete,batch_move}`, `/groups/get`, `/tests/get`, group/test state toggles. Verified via `/api/v1/group                                                                                                                                                                                                                                                                                                             | test/<id>/details` (no ORM). Includes JSON content-type and unknown-id error paths.                                                               |
| 10  | `argus/backend/controller/admin_api.py` (users)           | `argus/backend/tests/admin_api/test_admin_users_api.py`           | `complete` | 13 tests covering `/admin/api/v1/users` (privileged listing strips `password`/`api_token`), `/user/<id>/email/set` (success + invalid format + duplicate), `/user/<id>/password/set` (success + too short + empty), `/user/<id>/admin/toggle` (grant/revoke + self-forbidden), `/user/<id>/delete` (success + self-forbidden + admin-forbidden + unknown-id). Verified via `/admin/api/v1/users` listing (no ORM). proxy-tunnel/ssh already covered by `tests/tunnel/`.                                                    |
| 11  | `argus/backend/controller/notification_api.py`            | `argus/backend/tests/notification_api/test_notification_api.py`   | `pending`  | `/get`, `/get_unread`, `/summary`, `/read`. Seed via service layer.                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 12  | `argus/backend/controller/view_api.py`                    | `argus/backend/tests/view_api/test_view_api.py`                   | `pending`  | view CRUD, search, stats, versions, images, resolve, pytest results.                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 13  | `argus/backend/controller/team.py`                        | `argus/backend/tests/team_api/test_team_api.py`                   | `pending`  | team CRUD, motd, user/leader endpoints.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| 14  | `argus/backend/controller/planner_api.py`                 | `argus/backend/tests/planner_api/test_planner_api.py`             | `pending`  | plan CRUD/copy/owner/resolve_entities/trigger/list/search/explode. Jenkins trigger mocked.                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 15  | `argus/backend/controller/views_widgets/summary.py`       | `argus/backend/tests/view_widgets/test_summary_widget.py`         | `pending`  | `/widgets/summary/{versioned_runs,runs_results}`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 16  | `argus/backend/controller/views_widgets/pytest.py`        | `argus/backend/tests/view_widgets/test_pytest_widget.py`          | `pending`  | `/widgets/pytest/{view,release/<id>/results,view/<id>/results,<test_name>/<id>/fields}`.                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 17  | `argus/backend/controller/views_widgets/nemesis_stats.py` | `argus/backend/tests/view_widgets/test_nemesis_widget.py`         | `pending`  | `/widgets/nemesis_data`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 18  | `argus/backend/controller/views_widgets/graphs.py`        | `argus/backend/tests/view_widgets/test_graphs_widget.py`          | `pending`  | `/widgets/graphs/graph_views`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 19  | `argus/backend/controller/views_widgets/graphed_stats.py` | `argus/backend/tests/view_widgets/test_graphed_stats_widget.py`   | `pending`  | `/widgets/graphed_stats`, `/widgets/runs_details`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 20  | `argus/backend/controller/auth.py`                        | `argus/backend/tests/auth_api/test_auth_api.py`                   | `pending`  | `/register`, `/login`, `/logout`, `/profile/api/token/generate`, `/admin/impersonate{,/stop}`. CF login mocked.                                                                                                                                                                                                                                                                                                                                                                                                            |
| 21  | `argus/backend/controller/main.py` (profile only)         | `argus/backend/tests/main_api/test_profile_api.py`                | `pending`  | `/profile/update/{picture,name,username,email,password}`, `/profile/jobs`, `/profile/schedules`, `/storage/picture/<id>`. GitHub OAuth callback mocked.                                                                                                                                                                                                                                                                                                                                                                    |
| 22  | `argus/backend/controller/views_widgets/highlights.py`    | `argus/backend/tests/view_widgets/test_highlights_api.py`         | `existing` | Already covered by pre-existing test module. No work needed.                                                                                                                                                                                                                                                                                                                                                                                                                                                               |

### Out of scope

| Controller                                     | Reason                                                           |
| ---------------------------------------------- | ---------------------------------------------------------------- |
| `argus/backend/controller/notifications.py`    | Single UI redirect — non-API.                                    |
| `argus/backend/controller/admin.py`            | UI shell only (`/admin` -> Svelte template).                     |
| `argus/backend/controller/team_ui.py`          | UI shell only.                                                   |
| `argus/backend/controller/main.py` (UI routes) | Page-rendering routes (release dashboards, test_run views).      |
| `argus/backend/controller/ssh_api.py`          | Already covered by `argus/backend/tests/tunnel/test_ssh_api.py`. |

### Per-iteration Definition of Done

Every commit in this matrix must satisfy:

- [ ] New `argus/backend/tests/<area>/__init__.py` and `test_*.py` files created.
- [ ] All in-scope endpoints have at least one happy-path test.
- [ ] Each test creates its own UUIDs / does not share mutable state.
- [ ] JSON-first verification; ORM fallback only where no GET endpoint exists, with an inline
      comment explaining why.
- [ ] External services mocked at the lowest stable boundary (Jenkins/GitHub/Jira/S3/CF JWT).
      Real ScyllaDB always.
- [ ] `uv run pytest argus/backend/tests/<area>` passes locally.
- [ ] `uv run ruff check argus/backend/tests/<area>` passes.
- [ ] This matrix row updated to `complete`.

### Risks (specific to controller coverage rollout)

| Risk                                                                                 | Likelihood | Impact | Mitigation                                                                                                                                                                  |
| ------------------------------------------------------------------------------------ | ---------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Undocumented payload shapes for `controller/api.py` endpoints.                       | Medium     | Low    | Trace through service-layer code paths to derive payloads; mark unclear endpoints as "Needs Investigation" and skip in the initial commit, file a follow-up.                |
| Mocked external clients diverge from production behavior.                            | Medium     | Medium | Mock at the lowest stable boundary (the client object on the service); keep controller-level happy-path assertions narrow; comment with a pointer to the real client class. |
| Some endpoints depend on long-running background services (CDC/Vector Store warmup). | Low        | Medium | Reuse the existing session-scoped `argus_db` fixture; no extra warmup logic in new tests.                                                                                   |
