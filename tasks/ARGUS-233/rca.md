# ARGUS-233 — HEAD on the log download endpoint answers 405

**Date**: 2026-09-16

## Root cause

Flask and Werkzeug add `HEAD` to every rule that allows `GET`. FastAPI does
not. Plain Starlette `Route` does, but `APIRoute` registers only the methods
the decorator names.

Commit `9daa451f` moved the testrun blueprint to FastAPI. The route lost the
implicit `HEAD`:

```python
@router.get("/tests/{plugin_name}/{run_id}/log/{log_name}/download", name="api.testrun_api.download_log")
def download_log(...):
    return RedirectResponse(result, status_code=302)
```

Starlette answers 405 when the path matches and the method does not, so the
client never reaches the handler and never gets a `Location` header.

A `HEAD` test against the route before the fix returns 405. The same test
returns 302 after it.

## Approaches

**1. Declare `GET` and `HEAD` on the routes that redirect to S3. Selected.**

Three routes answer a 302 that points at an external artifact:
`download_log` and `proxy_screenshot` in `argus/backend/controller/testrun_api.py`,
and `s3_generic_proxy` in `argus/backend/controller/api.py`. Each one becomes
an `api_route` with `methods=["GET", "HEAD"]` and keeps its route name.

Cost: three decorators. Risk: a fourth S3 redirect route added later repeats
the defect. The reader sees the accepted methods at the definition site, which
is the reason for the choice.

**2. Add `HEAD` to every `GET` route at application start.**

A loop over the route tree in `create_app` would restore the Flask behavior
everywhere. Rejected for two reasons. The accepted methods become invisible at
the definition site. `argus/backend/rendering.py` documents that FastAPI wraps
the application level `include_router` calls, so `app.routes` is not flat and a
naive walk misses nested routes.

**3. Change the client instead.**

Out of scope here. Pull request scylladb/scylla-cluster-tests#16080 already
does it, and it does not close this issue.

## Audit of the other migrated routes

The criterion is a redirect to an external artifact. Of the routes that commit
`9daa451f` moved, only `download_log` and `proxy_screenshot` return a redirect.
The rest return JSON. `s3_generic_proxy` arrived in commit `b71536e4` and has
the same shape, so it is in the fix.

The redirects in `auth.py` and `main.py` send a browser to another Argus page.
No client resolves those with `HEAD`.

A grep for `HEAD` in `argus/client/` finds nothing. The only known consumer is
`S3Storage.download_file` in SCT.

## Regression test

- `argus/backend/tests/testrun_api/test_testrun_api.py`:
  `test_download_log_head_redirects_to_s3_url` and
  `test_proxy_screenshot_head_redirects`.
- `argus/backend/tests/api/test_users_jobs_api.py`:
  `test_s3_generic_proxy_redirects`, parametrized over `get` and `head`.

Each case asserts the 302 status and the `Location` header. A body assertion
would test the transport: the `httpx` test client keeps the body on a `HEAD`
response, and uvicorn drops it.

## Risks

| Risk | Response |
|---|---|
| A later S3 redirect route repeats the defect | The rca records the rule: a route that redirects to an external artifact accepts `GET` and `HEAD` |
| `HEAD` runs the full handler, including the S3 signing call | The Flask application did the same. The signing call is cheap and the response carries no body |
