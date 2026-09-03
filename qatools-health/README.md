# qatools-health

Health checking for the ScyllaDB QA Tools services. A service declares what it
depends on, the package probes those dependencies on a schedule, and the results
become Prometheus metrics. Every service that uses the package exports the same
series, so one dashboard and one set of alert rules cover all of them.

The package opens no port and serves no route. It produces a Prometheus
collector. The service registers that collector with the registry its own
exporter already serves.

It imports nothing from Argus. It depends on `prometheus-client` and `httpx`,
and on nothing else.

This code has no comments and no docstrings, by repository policy. This file
is the API reference.

## Install

```
pip install -e ./qatools-health
```

## Usage

```python
from qatools_health import HealthCheckResult, HealthCheckRunner, healthcheck
from qatools_health.checks import (
    AnthropicApiHealthCheck,
    GhCliHealthCheck,
    GitHubApiHealthCheck,
    JenkinsApiHealthCheck,
    OpencodeHealthCheck,
    SqliteHealthCheck,
    StalenessHealthCheck,
)


@healthcheck(name="queue_depth", interval=30)
async def queue_depth():
    depth = api_queue.qsize()
    if depth > 500:
        return HealthCheckResult.degraded(f"queue depth {depth} over 500")
    return None


checks = [
    JenkinsApiHealthCheck(JENKINS_URL, JENKINS_USER, JENKINS_API_TOKEN),
    AnthropicApiHealthCheck(ANTHROPIC_API_KEY),
    OpencodeHealthCheck(),
    StalenessHealthCheck(
        lambda: last_jenkins_poll,
        warn_after=900,
        fail_after=3600,
        name="jenkins_poll",
    ),
    queue_depth,
]

if "github" in ENABLED_SOURCES:
    checks += [GitHubApiHealthCheck(GH_TOKEN, GITHUB_BOT_LOGIN), GhCliHealthCheck()]

checks += [
    SqliteHealthCheck(store.connection, name=f"sqlite:{store.name}")
    for store in open_stores
]

runner = HealthCheckRunner(checks, service="zeus", version=build_version)
runner.register()
runner.start()
```

`register()` puts the collector in the default registry. `start()` arms the
timers and returns. A service that gathers its long-lived tasks passes
`runner.run(shutdown_event)` to the gather instead of calling `start()`.

Adding a dependency later is one more entry in the list.

## Status

`HealthCheckStatus` is a `StrEnum` with three members, ordered from best to
worst: `HEALTHY`, `DEGRADED`, `UNHEALTHY`.

There is no `UNKNOWN`. A check that has not run yet is a state of the runner.
The runner reports it as the check's `failure_status` until the first result
arrives.

`worse_of(*statuses)` returns the worst of the statuses given, and `HEALTHY`
for an empty call. `is_worse(candidate, reference)` compares two statuses.

## Result

`HealthCheckResult` is a frozen dataclass with three fields.

| Field | Meaning |
| --- | --- |
| `status` | The outcome. |
| `message` | One sentence for a human. It reaches the log. It never becomes a metric label. No stack trace and no secret. |
| `error` | Exception message when the check raised. The runner sets it. |

Three constructors build one in a line: `HealthCheckResult.healthy(message="")`,
`HealthCheckResult.degraded(message)` and `HealthCheckResult.unhealthy(message)`.

The result carries no structured payload. A number worth keeping goes in the
sentence. A number worth querying is a metric of the service that owns it.

## Check

`HealthCheck` is the abstract base for one probe of one dependency. A subclass
sets the class attributes it wants as defaults. The constructor overrides any of
them per instance, by keyword.

| Attribute | Default | Meaning |
| --- | --- | --- |
| `name` | none | Stable identifier. It becomes a Prometheus label value, so the set of names must stay bounded. Never a run id, a URL or a build number. |
| `critical` | `False` | Published as a label, and used by the aggregate. An alert rule selects critical dependencies with it. |
| `failure_status` | `UNHEALTHY` | Status recorded when the probe raises or times out. |
| `interval` | `300.0` | Seconds between two runs. |
| `timeout` | `10.0` | Seconds before a run is abandoned. |
| `stale_after_intervals` | `3.0` | How many missed intervals make the last value stale. |

`critical` and `failure_status` are separate. `critical` decides whether this
failure makes the whole service unhealthy. `failure_status` decides what a
raised exception means for this dependency. An optional dependency can report
UNHEALTHY for itself while the service stays DEGRADED.

A check with no name raises at construction. A non-positive `interval`,
`timeout` or `stale_after_intervals` raises at construction.

### perform_check

```python
async def perform_check(self) -> Any
```

Runs the probe once and returns what it found. It takes no arguments. A check
author stores nothing, schedules nothing, and never sees where the result goes.

It may raise. An exception becomes a result with the status `failure_status` and
the exception message as `error`, so an implementation needs no `try`/`except`
of its own to report a failure.

The return value is coerced, so a trivial check needs no imports:

| Returned | Recorded as |
| --- | --- |
| `HealthCheckResult` | itself |
| `HealthCheckStatus` | that status, no message |
| `True` or `None` | HEALTHY |
| `False` | `failure_status` |
| raised exception | `failure_status`, with the message as `error` |
| anything else | `failure_status`, with a `TypeError` message as `error` |

`None` counts as healthy, so a check written as "raise when it is broken" does
not have to end with a `return` statement that says nothing.

### aclose

```python
async def aclose(self) -> None
```

Releases what this check opened. The runner calls it once, from `stop()`. Only a
check that built its own client implements it. A check that received a client
does not close it.

### Inline checks

The `healthcheck` decorator builds a `HealthCheck` instance from an async
function. That instance goes in the list like any other check.

```python
@healthcheck(name="queue_depth", interval=30)
async def queue_depth():
    ...
```

It also works bare, and then takes the function name:

```python
@healthcheck
async def queue_depth():
    ...
```

The decorator constructs. It does not register. There is no module-level
registry and no import-time discovery, so the set of checks does not depend on
which modules an interpreter happened to import.

A synchronous function raises `TypeError`.

## Runner

```python
HealthCheckRunner(
    checks,
    *,
    service,
    version="",
    on_change=None,
    clock=time.time,
)
```

The runner takes a plain sequence. A service builds it with a list literal, a
conditional `+=`, or a comprehension. A duplicate name raises at construction.

| Member | Meaning |
| --- | --- |
| `collector` | The Prometheus collector to register with a registry. |
| `status` | The aggregate status right now. |
| `register(registry=None)` | Register the collector. Defaults to `prometheus_client.REGISTRY`. |
| `unregister(registry=None)` | Remove the collector from a registry. |
| `start()` | Arm the first timer for every check and return. Not a coroutine, and it does not block. |
| `stop()` | Cancel every armed timer, await the checks still in flight, then call `aclose()` on each check. |
| `run(shutdown)` | `start()`, wait for the `asyncio.Event`, `stop()`. The only method that blocks. |
| `snapshot()` | The last known value of every check, as plain data. |

`start()` is the whole lifecycle for a service that already has a place to put
background work. `run()` is the variant for a service that wants one awaitable
for `asyncio.gather`.

`on_change` fires on every change of the aggregate status, with the new status
and a reason that names the check behind it. It runs on the health loop, so it
must not block. It is the one way a service acts on a transition the package
knows nothing about, such as writing the systemd status line.

```python
runner = HealthCheckRunner(
    checks,
    service="zeus",
    on_change=lambda status, reason: notify(f"STATUS={status}: {reason}"),
)
```

A callback that raises is logged and does not reach the service.

## Scheduling

Every check runs on its own interval, independently of every other check.

- The next run is scheduled after the previous one returns. A check slower than
  its interval runs less often and never overlaps itself.
- A run that exceeds its timeout is recorded as the check's `failure_status`,
  with the message `timed out after Ns`.
- A scrape never triggers a check and never waits for one. There is no path from
  a scrape to a dependency.
- The first run of each check is spread over the first second, so twenty checks
  do not open twenty connections in the same millisecond.
- A status change is logged once: INFO on recovery, WARNING on failure, with the
  check name, the old status, the new status and the message. A dependency down
  for a day writes one line, not one per interval. This log is the only place
  the message reaches an operator.
- A failure inside the framework is logged, drops `healthcheck_runner_up`, and
  does not reach the service.

### Staying async

Every check body awaits. A synchronous call inside one blocks the other checks
and, in an embedding service, that service's whole loop.

A dependency whose library has no async client either gets a check written
against an async client, or gets no check. Wrapping a slow synchronous call to
make it awaitable moves the block. It does not remove it.

## Aggregation

Over every check:

1. Any UNHEALTHY on a `critical` check gives UNHEALTHY.
2. Otherwise any UNHEALTHY or DEGRADED gives DEGRADED.
3. Otherwise HEALTHY.

A check counts as stale when its last run is older than `stale_after_intervals`
of its intervals. A stale check contributes at least DEGRADED. Staleness can
only worsen a status, never soften one:

```python
effective = worse_of(published_status, DEGRADED if stale else HEALTHY)
```

A stale UNHEALTHY therefore stays UNHEALTHY. A check that fails and then falls
silent must not read better than one that only fell silent. The check's own
published value does not change either way. Staleness is a fact about the
reading, not a new reading.

A check that has not run yet publishes a last-run timestamp of 0. It is stale by
this rule and `failure_status` by the rule above, and the worse of the two wins,
so a never-run critical check makes the service UNHEALTHY. That window closes
after the first run, which is armed within the first second and bounded by the
check's timeout.

## Last known value

Checks run on their own timers and take different amounts of time. A scrape
lands wherever it lands. The exposition therefore always carries the last known
value of every check.

- A check's value updates when it completes. Between completions it holds the
  previous one.
- Every check has a value from the first scrape onward. A check that has not
  completed yet publishes its `failure_status` with a last-run timestamp of 0.
  The series exists, so an alert can see it. An absent series would instead say
  that the dependency is gone.
- Values have different ages by design. A 30-second queue check and a 15-minute
  binary check are both current, as of different moments.
  `healthcheck_last_run_timestamp_seconds` gives the age of each value.
- A dead service exports nothing, so no rule over these series can see it. That
  case belongs to `up` for the scrape job. A panel or an alert on
  `healthcheck_status` must pair the two.

A check that stopped running keeps exporting its last result and looks healthy.
`healthcheck_stale` publishes the bit the runner already computed for the
aggregate, so the rule file needs:

```
healthcheck_stale > 0
```

The threshold stays with the check, as `stale_after_intervals`. An alert written
over `healthcheck_last_run_timestamp_seconds` would have to repeat each interval
as a literal, and would keep evaluating, and keep looking correct, after that
interval changed.

`healthcheck_runner_up` covers health checking stopping altogether. The
per-check rule covers one check falling silent while the rest keep running.

## Metrics

The collector builds the metric families on each scrape from the last result of
every check. It runs no check, blocks on nothing, and does no I/O, so it is safe
to call from whatever thread or loop the host's exporter uses.

The series follow the list of checks exactly. Removing a check removes its
series instead of leaving a stale label combination frozen at its last value.

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `healthcheck_status` | Gauge | `service` | 2 healthy, 1 degraded, 0 unhealthy. |
| `healthcheck_dependency_up` | Gauge | `service`, `dependency`, `critical` | 1 healthy, 0.5 degraded, 0 unhealthy. |
| `healthcheck_duration_seconds` | Gauge | `service`, `dependency` | Duration of the last run of this check. |
| `healthcheck_last_success_timestamp_seconds` | Gauge | `service`, `dependency` | Unix time of the last HEALTHY result. |
| `healthcheck_last_run_timestamp_seconds` | Gauge | `service`, `dependency` | Unix time the last run finished. |
| `healthcheck_stale` | Gauge | `service`, `dependency` | 1 when the last value is older than `stale_after_intervals` intervals. |
| `healthcheck_oldest_result_timestamp_seconds` | Gauge | `service` | Completion time of the oldest published result. |
| `healthcheck_newest_result_timestamp_seconds` | Gauge | `service` | Completion time of the newest one. |
| `healthcheck_runner_up` | Gauge | `service` | 0 once health checking has stopped. |
| `healthcheck_info` | Info | `service`, `version` | Build identity. |

The oldest and newest timestamps bound the window the current exposition covers.
Per-check intervals mean there is no synchronised pass to record, so they are
computed across the published values.
`now() - healthcheck_newest_result_timestamp_seconds` says how long it has been
since anything at all was refreshed.

The duration is a gauge, not a histogram. The useful number is the duration of
the last probe, and a distribution over one sample every few minutes has no
readers.

Every metric name starts with `healthcheck_` and carries a `service` label. One
metric name per service would make the service-by-dependency matrix a new
expression for every service added. A shared name gives the matrix in one query.

Messages are not published. An info series carrying the reason as a label would
change identity whenever the text changes, and churn the series database for a
query nobody writes.

### Multiprocess exporters

`prometheus_client` in multiprocess mode builds the exposition from the files in
`PROMETHEUS_MULTIPROC_DIR`. It does not call a custom collector. A service that
runs several worker processes, such as Argus under uwsgi, must run the runner in
a single process with its own exporter.

## Built-in checks

Every dependency the QA Tools services share has its own class. A service names
the dependency and hands over the client or the credentials. It does not
describe an HTTP request or a subprocess.

Each class carries its own name, criticality and interval, so
`OpencodeHealthCheck()` needs nothing else. Any of them can be overridden per
instance.

Every class that talks to a dependency takes that dependency in `__init__`. The
first argument is the client, session or connection the service already built.
The credential form is the fallback for a service that has none.

```python
JenkinsApiHealthCheck(client=jenkins_client)
JenkinsApiHealthCheck(base_url, JENKINS_USER, JENKINS_API_TOKEN)
```

Pass the live client wherever one exists. A check that builds its own connection
tests a second configuration: its own timeouts, its own pool, its own view of the
credential. When the service's client is broken and the check's private one is
not, the dashboard stays green while the service fails.

A check that built its own client owns it, and the runner closes it through
`aclose()` at shutdown.

### External APIs

Each one takes `client=` for an existing `httpx.AsyncClient`, or the credentials
shown.

| Class | Probe | Default name | Critical |
| --- | --- | --- | --- |
| `JenkinsApiHealthCheck(base_url, user, token)` | `GET <base>/api/json?tree=mode` | `jenkins_api` | yes |
| `JiraApiHealthCheck(base_url, email, token)` | `GET /rest/api/3/myself` | `jira_api` | no |
| `GitHubApiHealthCheck(token, expected_login=None)` | `GET /rate_limit`, plus the authenticated login when an expected login is given | `github_api` | no |
| `ArgusApiHealthCheck(base_url, token, cf_id=None, cf_secret=None)` | `GET /api/v1/notifications/get_unread`, the cheapest authenticated read | `argus_api` | no |
| `AnthropicApiHealthCheck(api_key)` | `GET /v1/models`. A models list is free. A completion probe would bill every five minutes for a worse signal | `llm_api` | yes |
| `HeadroomProxyHealthCheck(url)` | The proxy answers | `headroom_proxy` | no |
| `MaiaApiHealthCheck(base_url, token, path="")` | Maia answers an authenticated caller | `maia_api` | no |

### Command-line tools

Each one confirms that the executable resolves and answers, and reports the
version it found in its message.

| Class | Binary | Default name |
| --- | --- | --- |
| `OpencodeHealthCheck()` | `opencode` | `opencode` |
| `GhCliHealthCheck(verify_auth=False)` | `gh` | `gh` |
| `AcliHealthCheck()` | `acli` | `acli` |
| `Md2AdfHealthCheck()` | `md2adf` | `md2adf` |
| `ArgusCliHealthCheck()` | `argus` | `argus_cli` |
| `JenkinsCliHealthCheck()` | `jenkins-cli` | `jenkins_cli` |

Argus and Jenkins carry the `_cli` suffix because an API check of the same
service already holds the plain name.

A CLI check does not verify credentials. Presence and version are local and
fast. Authentication is a network call, and it belongs to the matching API
check, so a missing binary and an expired token stay two different cells on the
dashboard. `GhCliHealthCheck(verify_auth=True)` merges them for a service that
prefers one.

### Databases

| Class | Probe | Default name |
| --- | --- | --- |
| `SqliteHealthCheck(connection \| db_path, query="SELECT 1")` | The database opens and answers | `sqlite:<stem>` |

A live connection is queried on the calling loop, because a `sqlite3.Connection`
belongs to the thread that created it. A path is opened and closed in a worker
thread. A connection given without a name keeps the class name `sqlite`, so
register two of them under explicit names.

`ScyllaHealthCheck(session, keyspace=None)` lives in Argus and not here. Argus
connects through `scylla-driver`, Zeus and Maia have no driver, and the Zeus
bundle vendors every resolved dependency, so a driver in this package would put a
C extension in a service that never queries Scylla.

### Local resources

| Class | Reports | Default name |
| --- | --- | --- |
| `StalenessHealthCheck(getter, warn_after, fail_after)` | A timestamp the service supplies is recent enough | none, must be named |

The getter returns a unix timestamp, or `None` when nothing has been recorded
yet. It may be synchronous or a coroutine function.

There is no disk check. Host monitoring already reports disk usage for every box
QA Tools runs, and a second reading of the same filesystem adds a series and no
information.

### Primitives

For a dependency with no dedicated class yet. A new dedicated check is a subclass
of one of these, with the probe and the defaults filled in. This is how the lists
above grow.

| Class | Reports |
| --- | --- |
| `HttpHealthCheck(url, method="GET", expect=range(200, 400), latency_budget=None, headers=None, auth=None, client=None)` | Reachability of an HTTP dependency. Over the latency budget gives DEGRADED. A wrong status or a transport error gives the failure status. |
| `TcpHealthCheck(host, port)` | A port accepts a connection. For a tunnel, or a database with no cheap query. |
| `BinaryHealthCheck(binary, version_args=("--version",))` | An executable is on `PATH` and answers. |
| `CallableHealthCheck(fn)` | Adapter for an async function. The `healthcheck` decorator builds one. |

Every primitive is public:

```python
class NginxHealthCheck(HttpHealthCheck):
    name = "nginx"
    interval = 60.0

    def __init__(self, base_url, **kwargs):
        super().__init__(f"{base_url}/nginx_status", **kwargs)
```

No check targets another service's health surface. Nothing in the code can
enforce that, so it is a review rule.

## Development

```
uv venv --python 3.12 .venv
uv pip install --python .venv -e '.[dev]'
.venv/bin/pytest --cov=qatools_health
.venv/bin/ruff check src tests
```
