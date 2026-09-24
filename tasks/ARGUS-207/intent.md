# ARGUS-207 — Run the web backend on the async execution model

## Problem

The web backend moved from Flask to FastAPI, but the code under the routers
did not change shape. Every route handler but one is a plain `def`, so
FastAPI runs each request on a worker thread of its thread pool, and every
service call inside it blocks that thread. The database layer is the
synchronous half of the coodie mapper plus raw driver calls on a second
session. Nothing in a request runs concurrently with anything else in that
request.

The cost shows on the pages that read the most. A view's stats or a release
dashboard fetch the tests, then the plans of each release one release at a
time, then the issue links of each release one at a time, then the comments,
then the releases, then the groups, then the GitHub and Jira issues in
batches. None of those reads depend on each other's result, yet each waits
for the previous one to return. A widget that shows per-test data runs its
queries once per test in the view, in sequence. A run page loads the run,
then its junit reports, then its nemeses, then its resources. Round trips to
ScyllaDB add up, and the wall time of a page is the sum of them.

Blocking network calls to Jira, GitHub, Jenkins, the mail server and S3 sit
on the same request path and hold a thread for their whole duration.

## Who it affects

- Engineers who open a release dashboard, a view, a run page or a widget and
  wait for a page whose time is the sum of dozens of serial reads.
- Every consumer of the REST API, including the SCT pipelines and the Go and
  Python clients, whose requests share the same per-worker pool of forty
  threads and queue behind the slow pages.
- Maintainers who add a service method and today have no way to run two
  independent reads together, because the mapper and the handlers are
  synchronous.

## Evidence

Jira ARGUS-207, "FastAPI: Async Services", status New:

> After FastAPI rework we are now using synchronized services where we could
> be using async to improve performance. We need to analyze service code to
> find spots we could improve performance in by switching to async execution
> model.

Route handlers, counted over `argus/backend/controller/`,
`argus/backend/controller/views_widgets/`, the two plugin controllers and
`argus/backend/metrics.py`: 268 handlers, 267 declared `def`, one `async def`
(`zeus_proxy`, `argus/backend/controller/api.py:569`).

Model declarations, all 16 model files:

```python
from coodie.sync import Document
```

The view stats collector, `argus/backend/service/stats.py:163-168`, one
query per release, in sequence:

```python
def _fetch_multiple_release_queries(entity, releases: list[str]):
    result_set = []
    query = entity.find if hasattr(entity, "find") else entity.filter
    for release_id in releases:
        result_set.extend(query(release_id=release_id).all())
    return result_set
```

The graphed stats widget, `argus/backend/controller/views_widgets/graphed_stats.py:28-31`,
one service call per test, in sequence:

```python
    for test_id in view.tests:
        data = service.get_graphed_stats(test_id, filters)
        response_data["test_runs"].extend(data["test_runs"])
        response_data["nemesis_data"].extend(data["nemesis_data"])
```

The only place a fan-out runs in parallel today uses driver futures that the
caller blocks on, `argus/backend/plugins/core.py:136-139` and
`argus/backend/service/stats.py:553`:

```python
            futures.append(cluster.session.execute_async(query=query, parameters=(next_slice,),
                                                         execution_profile="read_fast"))
```

```python
        self.release_rows = [row for future in self.release_rows for row in future.result()]
```

Raw CQL sites in production code, counted by hand: 42, in 13 files; 3 of them
are prepared and never executed.

## What good looks like

- Every route handler is `async def`. A request runs on the event loop and
  yields while it waits for ScyllaDB or an external service.
- The models read and write through the asynchronous half of the coodie
  mapper. A query that the mapper can express goes through the mapper; raw
  CQL remains only where the mapper cannot build the statement.
- Independent reads inside one service call run together. The serial depth
  of a view's stats, a release dashboard, a run page and the per-test widgets
  drops from one round trip per item to a handful per page, and the page
  time follows.
- Blocking calls to Jira, GitHub, Jenkins, the mail server, S3 and
  subprocesses run off the event loop so they never stall other requests.
- A query that returns more rows than one driver page returns all of them.
- The test suite, the CLI commands and the schema sync keep working, and the
  REST API responds with the same shapes and status codes as before.

## Out of scope

- Changing the driver. The scylla-driver stays; no acsylla.
- Changing the deployment model: gunicorn with four uvicorn workers stays.
- Moving CPU-bound aggregation (stats collection over thousands of rows) off
  the event loop. This task adds the timing that decides whether that is
  needed.
- The one-off migration scripts under `scripts/migration/`, which already
  ran and are not edited.
- The AI workers under `argusAI/`, which own their connection.
- Admin and planner CRUD paths with single-digit round trips.
- Any change to the frontend.
