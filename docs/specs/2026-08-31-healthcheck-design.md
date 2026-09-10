# Health checking as a standalone module (QATOOLS-392)

## Problem

Zeus, Argus and Maia depend on the same set of external things: Jenkins, Jira,
GitHub, Argus, Anthropic, Scylla, SQLite stores and several command-line tools.
When one of them is down, a service keeps accepting work and fails it. An
operator learns about the outage from a failed investigation, not from a
dashboard.

Each service also answers "am I healthy" in its own way, so no single dashboard
and no single alert rule covers all three.

A service also has code that must not run while a dependency is down. That code
polls the dependency itself today, on its own schedule, with its own timeout and
its own copy of the last answer. The same dependency therefore gets probed twice
and reported two ways.

## Design

One Python package. A service subscribes to the dependencies it cares about. The
package probes each dependency once on its own schedule, keeps the last result,
publishes every result as Prometheus metrics under one shared set of names, and
calls back the subscribers when the result changes status. All three services
export the same series, so one dashboard and one rule file cover all of them.

A subscription is the unit. The check instance is the subject a caller
subscribes to, the runner holds one probe loop per distinct dependency however
many subscribers it has, and closing the last subscription retires the check. A
caller therefore never asks whether a dependency is already registered.

The package knows nothing about the services that use it. It imports nothing
from a service and reads no service setting. It depends on `prometheus-client`
and `httpx`, and on nothing else.

It opens no port and serves no route. It produces a Prometheus collector, and
the service registers that collector with the registry its own exporter already
serves. Prometheus scrapes the exposition and Alertmanager routes the alert,
which is the path QA Tools already runs. A service that later needs an HTTP
route builds it from the last known values.

A scrape reads the last known value of every check. It never triggers a probe
and never waits for one, so scraping the exposition every second adds no load
to any dependency it reports on.

## Usage

A service writes subscriptions, plus a check body where a dependency has no
class yet. It writes no scheduling, timeouts, caching, deduplication,
aggregation, staleness, metric families, label sets or transition logging.

```python
from qatools_health import (
    HealthCheckResult,
    HealthCheckRunner,
    HealthCheckStatus,
    healthcheck,
)
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


runner = HealthCheckRunner(service="zeus", version=build_version)

runner.register(AnthropicApiHealthCheck(ANTHROPIC_API_KEY))
runner.register(OpencodeHealthCheck())
runner.register(queue_depth)
runner.register(
    StalenessHealthCheck(
        lambda: last_jenkins_poll,
        name="jenkins_poll",
        warn_after=900,
        fail_after=3600,
    )
)

for store in open_stores:
    runner.register(SqliteHealthCheck(store.connection, name=f"sqlite:{store.name}"))

if "github" in ENABLED_SOURCES:
    runner.register(GhCliHealthCheck())
    runner.register(
        GitHubApiHealthCheck(GH_TOKEN, GITHUB_BOT_LOGIN),
        on_change=lambda check, result: notify(f"{check.name}: {result.status}"),
    )

runner.register_collector()
runner.start()
```

`register_collector()` puts the collector in the default registry, so the health
series join the exposition the service already serves. `start()` arms the timers
and returns. A service that gathers its long-lived tasks passes
`runner.run(shutdown_event)` to the gather instead.

Adding a dependency later is one more `register()` call. It appears in the
metrics and in the aggregate with nothing else touched.

A component that must not run while its dependency is down owns its
subscription:

```python
class GitHubSource:
    async def run(self, shutdown: asyncio.Event) -> None:
        with runner.register(
            GitHubApiHealthCheck(GH_TOKEN, GITHUB_BOT_LOGIN),
            on_change=self._on_github_change,
        ) as github:
            while not shutdown.is_set():
                await github.wait_for(HealthCheckStatus.HEALTHY)
                await self._poll_once()
```

The source names the same dependency the wiring already named, and both get one
probe loop and one series. The source starts when GitHub answers, stops on the
transition to UNHEALTHY, and resumes on the transition back.

A component that needs several dependencies subscribes to all of them at once,
and gates on the group:

```python
class PrChecksSource:
    async def run(self, shutdown: asyncio.Event) -> None:
        with runner.register_all(
            [
                JenkinsApiHealthCheck(client=jenkins_client),
                GitHubApiHealthCheck(GH_TOKEN, GITHUB_BOT_LOGIN),
                GhCliHealthCheck(),
            ],
            on_change=self._on_dependency_change,
        ) as deps:
            while not shutdown.is_set():
                await deps.wait_for(HealthCheckStatus.HEALTHY)
                await self._poll_once()
```

The group reads the worst status of its members, so the loop runs only while
Jenkins, the GitHub API and the `gh` binary all answer. Every one of the three
is also registered by the wiring, and every one still gets one probe loop and one
series.

A dependency with no dedicated class yet is a subclass of a primitive:

```python
class NginxHealthCheck(HttpHealthCheck):
    name = "nginx"
    interval = 60.0

    def __init__(self, base_url: str, **kwargs) -> None:
        super().__init__(f"{base_url}/nginx_status", **kwargs)
```

## API

### Status and result

```python
class HealthCheckStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    status: HealthCheckStatus
    message: str = ""
    error: str | None = None

    @classmethod
    def healthy(cls, message: str = "") -> "HealthCheckResult": ...

    @classmethod
    def degraded(cls, message: str) -> "HealthCheckResult": ...

    @classmethod
    def unhealthy(cls, message: str) -> "HealthCheckResult": ...
```

`message` is one sentence for a human. It reaches the log, never a metric
label, and carries no stack trace and no secret. `error` holds the exception
message when the probe raised, and the runner sets it.

The result carries a status and a sentence, and no structured payload. A number
worth keeping goes in the sentence. A number worth querying is a metric of the
service that owns it.

### Check

```python
class Severity(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


class HealthCheck(ABC):
    name: str
    severity: Severity = Severity.IMPORTANT
    interval: float = 300.0
    timeout: float = 10.0
    stale_after_intervals: float = 3.0

    def __init__(
        self,
        *,
        name: str | None = None,
        severity: Severity | None = None,
        interval: float | None = None,
        timeout: float | None = None,
        stale_after_intervals: float | None = None,
    ) -> None: ...

    def identity(self) -> tuple[object, ...]: ...

    @abstractmethod
    async def perform_check(self) -> HealthCheckResult: ...

    async def aclose(self) -> None: ...
```

A subclass sets the class attributes it wants as defaults, and the constructor
overrides any of them per instance. A check therefore carries its own
configuration, and a caller passes an instance and nothing else.
`OpencodeHealthCheck()` is already `Severity.CRITICAL`, already named
`opencode`, and already on its own interval: opencode down means Zeus is down,
so the aggregate must turn UNHEALTHY. `SqliteHealthCheck(conn,
name="sqlite:context")` is the same class registered twice under two names.

`name` becomes a Prometheus label value, so the set of names must stay bounded.
Never a run id, a URL or a build number.

`severity` decides what this check's own UNHEALTHY or DEGRADED result does to
the aggregate. `CRITICAL` turns an UNHEALTHY result into a service-wide
UNHEALTHY. `IMPORTANT` turns either result into DEGRADED, never further.
`OPTIONAL` never changes the aggregate at all; the result stays visible in the
check's own metric series and in the log, and the dashboard shows a red cell
under a green service tile. `JenkinsApiHealthCheck` defaults to `IMPORTANT`:
losing Jenkins pauses that source, but the rest of Zeus keeps working, so the
aggregate degrades rather than fails.

`perform_check()` takes no arguments and may raise. An exception becomes an
UNHEALTHY result with the exception message as `error`, so an implementation
needs no `try`/`except` of its own. The return value is coerced:

| Returned | Recorded as |
|---|---|
| `HealthCheckResult` | itself |
| `HealthCheckStatus` | that status, no message |
| `True` or `None` | HEALTHY |
| `False` | UNHEALTHY |
| raised exception | UNHEALTHY, with the message as `error` |

`None` counts as healthy, so a check written as "raise when it is broken" does
not have to end with a `return` statement that says nothing.

`aclose()` releases what the check opened, and the runner calls it once the last
subscription closes. Only a check that built its own client implements it. A
check that received a client does not close it.

A check builds its own client on the first probe, never in `__init__`. A
constructor that opens nothing costs nothing, which is what makes
`GitHubApiHealthCheck(GH_TOKEN, GH_LOGIN)` safe to write in three places that do
not know about each other. The base class holds the client, so a subclass
implements `_client()` and never a lifecycle.

Every check body awaits. A synchronous call inside one blocks the other checks
and the embedding service's whole loop. A dependency whose library has no async
client either gets a check written against an async client, or gets no check.

### Identity

Two instances that probe the same thing are the same check. The base class
derives an identity from the concrete class and the arguments the constructor
received, minus the policy keywords above, and the runner keys the check by it.
A caller therefore constructs an instance wherever it needs one and never holds
a registry of its own.

`identity()` exists for the case the default gets wrong.
`JenkinsApiHealthCheck(client=jenkins_client)` and
`JenkinsApiHealthCheck(base_url, user, token)` name one Jenkins, so the class
returns the base URL from both forms. A subclass overrides `identity()` when the
argument list carries more than the dependency it names, and leaves it alone
otherwise.

An identity value never reaches a log line, a metric label or a `repr`. A
credential is an ordinary constructor argument, so the identity is compared and
hashed but never rendered.

Policy is not part of the identity. Two registrations of one dependency with
different severities, intervals or timeouts collapse into one check that takes
the strictest of each: the worst severity, the shortest interval, the shortest
timeout. A subscriber cannot be made worse off by another subscriber it does not
know about. The name must match, and a second name for one identity raises,
because the two would otherwise publish one probe under two series.

Two distinct identities under one name raise for the same reason.

### Inline checks

The `@healthcheck` decorator builds a `HealthCheck` instance from an async
function, and that instance registers like any other. The decorator constructs
the instance and does not register it, so the set of checks never depends on
which modules an interpreter happened to import. The identity is the decorated
function, so registering the same decorated function twice yields one check.

### Subscription

```python
class HealthCheckSubscription:
    @property
    def check(self) -> HealthCheck: ...

    @property
    def status(self) -> HealthCheckStatus: ...

    @property
    def result(self) -> HealthCheckResult | None: ...

    async def wait_for(
        self,
        *statuses: HealthCheckStatus,
        timeout: float | None = None,
    ) -> HealthCheckResult: ...

    def close(self) -> None: ...
```

`check` is the instance the runner probes, which is the first instance
registered under that identity. A caller that registers a duplicate gets a
subscription over the instance already running, and its own instance is
discarded unused. Nothing reads the passed instance after `register()` returns,
which is why a check must open nothing in its constructor.

`status` is the last computed status, including the staleness rule below. It
never blocks and never probes. A component that must gate one call on one
dependency reads this instead of keeping a second copy of the same state.

`wait_for()` returns as soon as the check reads one of the given statuses. It
returns the current result immediately when the check already reads one of them,
so a caller does not race the first probe. It raises `TimeoutError` past
`timeout`, and `SubscriptionClosedError` when the subscription closes while it
waits.

`close()` ends the subscription. It is idempotent, and the object is a context
manager. The check keeps running while another subscription holds it. The last
`close()` cancels the timer, awaits a probe in flight, calls `aclose()`, and
removes the series from the exposition.

### Group

A component usually depends on more than one thing. `register_all()` returns a
group: one handle over several checks, with the same `status`, `wait_for()` and
`close()` a single subscription has, and the same context manager.

```python
class HealthCheckGroup:
    @property
    def members(self) -> tuple[HealthCheckSubscription, ...]: ...

    @property
    def status(self) -> HealthCheckStatus: ...

    def __getitem__(self, check: HealthCheck) -> HealthCheckSubscription: ...

    async def wait_for(
        self,
        *statuses: HealthCheckStatus,
        timeout: float | None = None,
    ) -> HealthCheckStatus: ...

    def close(self) -> None: ...
```

`status` is the worst status among the members, so `wait_for(HEALTHY)` returns
when every member reads HEALTHY, and a group with one member reads exactly like
that member.

Severity does not enter this. Severity says what a failing dependency does to
the service status on a dashboard, and a group says what a failing dependency
does to one caller's loop. A caller that puts an `OPTIONAL` check in its own
gate meant to wait for it. A caller that wants the dashboard rule reads
`runner.status` instead.

`close()` closes every member. A member held by another subscriber keeps
running, by the rule above. A `wait_for()` in flight when the group closes
raises `SubscriptionClosedError`, as a member's does.

`__getitem__` returns the member subscription for one check, so a caller that
gates on the group and also reacts to one member reads both from one
registration. It takes any instance of that check, because the lookup is by
identity, and raises `KeyError` for a check the group does not hold.

The group callback takes the group's new status and a reason that names the
member behind it, which is the signature the runner-level `on_change` takes:

```python
OnGroupChange = Callable[[HealthCheckStatus, str], Awaitable[None] | None]
```

The runner-level `on_change` is the group over every registered check, weighted
by severity. A group is the same operation over a subset, weighted by nothing.

### Runner

```python
class HealthCheckRunner:
    def __init__(
        self,
        *,
        service: str,
        version: str = "",
        on_change: Callable[[HealthCheckStatus, str], None] | None = None,
    ) -> None: ...

    @property
    def collector(self) -> Collector: ...

    @property
    def status(self) -> HealthCheckStatus: ...

    def register(
        self,
        check: HealthCheck,
        *,
        on_change: OnChange | None = None,
    ) -> HealthCheckSubscription: ...

    def register_all(
        self,
        checks: Iterable[HealthCheck],
        *,
        on_change: OnGroupChange | None = None,
    ) -> HealthCheckGroup: ...

    def register_collector(
        self, registry: CollectorRegistry | None = None
    ) -> None: ...

    def unregister_collector(
        self, registry: CollectorRegistry | None = None
    ) -> None: ...

    def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def run(self, shutdown: asyncio.Event) -> None: ...
```

`register(check)` is safe from any thread and at any time, before `start()` and
long after it. It returns a subscription synchronously, and it neither blocks nor
probes. The runner arms the new timer on its own loop, so a caller on another
thread gets a subscription that reads no result yet, and a `wait_for()` on it
resolves once the first probe lands.

`register_all(checks)` registers each check the same way and returns one group
over all of them. It holds the same guarantees as one `register()` per check,
and it either registers every check or none: a name or identity conflict raises
before the first timer is armed.

`register_collector()` defaults to `prometheus_client.REGISTRY`.

`start()` arms the first timer for every check registered so far and returns. It
is not a coroutine and it does not block. `stop()` cancels every armed timer,
awaits the checks still in flight, then calls `aclose()` on each check that
implements it, and ends every open subscription. `run()` is a wrapper:
`start()`, wait for `shutdown`, `stop()`. It is the only method that blocks, and
it suits a service that gathers its long-lived tasks.

`status` is the last computed aggregate, over the checks registered at that
moment.

### Callbacks

A callback fires on a change of status, never on a repeated reading. A
dependency down for a day calls back twice: once on the way down and once on the
way back. The runner caches the last result of every check to hold this
guarantee, and that same cache is what the scrape and `subscription.status`
read.

```python
OnChange = Callable[[HealthCheck, HealthCheckResult], Awaitable[None] | None]
```

A subscriber gets the current result as its first callback when the check
already holds one, and the first probe result otherwise. A subscription created
mid-flight against a dependency that has been HEALTHY for an hour therefore
learns the status without waiting an interval, and a subscription created before
the first probe hears nothing until that probe lands.

A never-run check publishes UNHEALTHY to the metrics and to the aggregate, and
delivers no callback. The published value must be pessimistic, because a value
that never arrived is not evidence of health. A callback must not be, because
every subscriber would otherwise see one UNHEALTHY at startup that no dependency
caused.

A callback runs on the health loop. A coroutine function is awaited, a plain
function is called, and neither may block: a slow callback delays the checks. A
callback that raises is logged once per transition and changes nothing else, and
the subscription stays open.

The runner-level `on_change` fires on every change of the aggregate status, with
the new status and a reason that names the check behind it. It is the one way a
service acts on a transition the package knows nothing about, such as writing
the systemd status line.

## Scheduling

Every check runs on its own interval, independently of every other check.

- The next run is scheduled after the previous one returns. A check slower than
  its interval runs less often and never overlaps itself.
- A run that exceeds its timeout is recorded as UNHEALTHY, with the message
  `timed out after Ns`.
- The first run of each check is spread over the first second, so twenty checks
  do not open twenty connections in the same millisecond. A check registered
  after `start()` runs at once.
- A status change is logged once: INFO on recovery, WARNING on failure, with the
  check name, the old status, the new status and the message. A dependency down
  for a day writes one line, not one per interval. This log is the only place
  the message reaches an operator.
- A failure inside the framework is logged, drops `healthcheck_runner_up`, and
  does not propagate into the service.

## Aggregation and staleness

Over every check registered at that moment:

- Any UNHEALTHY on a `CRITICAL` check gives UNHEALTHY.
- Otherwise any UNHEALTHY or DEGRADED on a `CRITICAL` or `IMPORTANT` check
  gives DEGRADED.
- An `OPTIONAL` check's UNHEALTHY or DEGRADED never changes the aggregate.
- Otherwise HEALTHY.

Registering a check and retiring one both recompute the aggregate, so a
subscription that ends takes its check out of the service status in the same
step that takes it out of the exposition.

A check counts as stale when its last run is older than `stale_after_intervals`
of its intervals. Staleness can only worsen a status, never soften one:

```python
effective = worse_of(published_status, DEGRADED if stale else HEALTHY)
```

A stale UNHEALTHY therefore stays UNHEALTHY. A check that fails and then falls
silent must not read better than one that only fell silent. The check's own
published value does not change either way, because staleness is a fact about
the reading, not a new reading.

A check that has not run yet publishes UNHEALTHY with a last-run timestamp of
0. It is stale by this rule and UNHEALTHY by the rule above, and the worse of
the two wins, so a never-run `CRITICAL` check makes the service UNHEALTHY.
That window closes after the first run, which is armed within the first
second and bounded by the check's timeout.

## Metrics

The collector builds the metric families on each scrape from the last result of
every check. It runs no check, blocks on nothing, and does no I/O, so it is safe
to call from whatever thread or loop the host's exporter uses.

The series follow the registered checks exactly. Retiring a check removes its
series instead of leaving a stale label combination frozen at its last value.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `healthcheck_status` | Gauge | `service` | 2 healthy, 1 degraded, 0 unhealthy. |
| `healthcheck_dependency_up` | Gauge | `service`, `dependency` | 1 healthy, 0.5 degraded, 0 unhealthy. |
| `healthcheck_duration_seconds` | Gauge | `service`, `dependency` | Duration of the last run of this check. |
| `healthcheck_last_success_timestamp_seconds` | Gauge | `service`, `dependency` | Unix time of the last HEALTHY result. |
| `healthcheck_last_run_timestamp_seconds` | Gauge | `service`, `dependency` | Unix time the last run finished. |
| `healthcheck_stale` | Gauge | `service`, `dependency` | 1 when the last value is older than `stale_after_intervals` intervals. |
| `healthcheck_subscribers` | Gauge | `service`, `dependency` | Open subscriptions holding this check. |
| `healthcheck_oldest_result_timestamp_seconds` | Gauge | `service` | Completion time of the oldest published result. |
| `healthcheck_newest_result_timestamp_seconds` | Gauge | `service` | Completion time of the newest one. |
| `healthcheck_runner_up` | Gauge | `service` | 0 once health checking has stopped. |
| `healthcheck_info` | Info | `service`, `version` | Build identity. |

`healthcheck_dependency_up` carries no `severity` label. `healthcheck_status`
already reflects what each check's severity does to the aggregate, so a second
copy of the same fact on every dependency series would only invite a query
that recomputes the aggregate differently from the runner.

`healthcheck_subscribers` is the one series about the package rather than a
dependency. A series that disappears is either a source that shut down or a
subscription leak, and the count separates the two.

Values have different ages by design. A 30-second queue check and a 15-minute
binary check are both current, as of different moments. The oldest and newest
timestamps bound the window the current exposition covers.

The duration is a gauge, not a histogram. The useful number is the duration of
the last probe, and a distribution over one sample every few minutes has no
readers.

`healthcheck_stale` publishes the bit the runner already computed for the
aggregate, so the alert is `healthcheck_stale > 0` and the threshold stays with
the check. An alert written over `healthcheck_last_run_timestamp_seconds` would
repeat each interval as a literal, and would keep looking correct after that
interval changed.

`healthcheck_runner_up` covers health checking stopping altogether. A dead
service exports nothing, so that case belongs to `up` for the scrape job, and a
panel on `healthcheck_status` must pair the two.

QATOOLS-392 writes the aggregate as `<service>_health_status`. Every metric here
starts with `healthcheck_` and carries a `service` label instead, so the
service-by-dependency matrix is one query rather than a new expression for every
service added.

## What the package includes

The framework above, the four primitives, and one class per dependency:

- **External APIs**: `JenkinsApiHealthCheck`, `JiraApiHealthCheck`,
  `GitHubApiHealthCheck`, `ArgusApiHealthCheck`, `AnthropicApiHealthCheck`,
  `HeadroomProxyHealthCheck`, `MaiaApiHealthCheck`.
- **Command-line tools**: `OpencodeHealthCheck`, `GhCliHealthCheck`,
  `AcliHealthCheck`, `ArgusCliHealthCheck`, `JenkinsCliHealthCheck`.
- **Stores and local state**: `SqliteHealthCheck`, `StalenessHealthCheck`.
- **Primitives**: `HttpHealthCheck`, `TcpHealthCheck`, `BinaryHealthCheck`,
  `CallableHealthCheck`.

A service names the dependency and hands over the client or the credentials. It
does not describe an HTTP request or a subprocess, and it does not decide what a
cheap probe of Jenkins looks like. That decision is made once, in the class, for
all three services.

**Every class that talks to a dependency takes that dependency in `__init__`.**
The first argument is the client, session or connection the service already
built. The credential form is the fallback for a service that has none:

```python
JenkinsApiHealthCheck(client=jenkins_client)
JenkinsApiHealthCheck(base_url, JENKINS_USER, JENKINS_API_TOKEN)
```

Pass the live client wherever one exists. A check that builds its own connection
tests a second configuration: its own timeouts, its own pool, its own view of
the credential, so the dashboard stays green while the service fails. A check
that built its own client owns it, and the runner closes it through `aclose()`.

A check stays out of the package when it needs a library only one service has.
`ScyllaHealthCheck` is the case today. It needs `scylla-driver`, a C extension
that Zeus and Maia would then vendor into their bundles for a dependency they
never query, so it lives in the Argus application code. Placement is not
permanent, and a check moves in or out as its dependency becomes shared or stops
being shared.

`md2adf` gets no check at all. The release bundle compiles it in, so nothing
outside the build can remove or corrupt it between one run of Zeus and the
next. A service confirms it resolves once at startup and fails to boot if it
does not; that failure belongs to the same build-integrity checks as a missing
compiled `zeus_rs`, not to a package that watches dependencies which can change
state at runtime.

### External APIs

Each one takes `client=` for an existing `httpx.AsyncClient`, or the credentials
shown. The identity is the base URL in both forms, so the two reach one check.

| Class | Probe | Default name |
|---|---|---|
| `JenkinsApiHealthCheck(base_url, user, token)` | `GET <base>api/json?tree=mode` | `jenkins_api` |
| `JiraApiHealthCheck(base_url, email, token)` | `GET /rest/api/3/myself` | `jira_api` |
| `GitHubApiHealthCheck(token, expected_login=None)` | `GET /rate_limit`, plus the authenticated login when an expected login is given | `github_api` |
| `ArgusApiHealthCheck(base_url, token, cf_id=None, cf_secret=None)` | `GET notifications/get_unread`, the cheapest authenticated read | `argus_api` |
| `AnthropicApiHealthCheck(api_key)` | `GET /v1/models`. A models list is free, and a completion probe would bill every five minutes for a worse signal | `llm_api` |
| `HeadroomProxyHealthCheck(url)` | The proxy answers | `headroom_proxy` |
| `MaiaApiHealthCheck(base_url, token)` | Maia answers an authenticated caller | `maia_api` |

### Command-line tools

Each one confirms that the executable resolves and answers, and reports the
version it found in its message.

| Class | Default name |
|---|---|
| `OpencodeHealthCheck()` | `opencode` |
| `GhCliHealthCheck()` | `gh` |
| `AcliHealthCheck()` | `acli` |
| `ArgusCliHealthCheck()` | `argus_cli` |
| `JenkinsCliHealthCheck()` | `jenkins_cli` |

Argus and Jenkins carry the `_cli` suffix because an API check of the same
service already holds the plain name.

A CLI check does not verify credentials. Authentication belongs to the matching
API check, so a missing binary and an expired token stay two different cells on
the dashboard. `GhCliHealthCheck(verify_auth=True)` merges them for a service
that prefers one.

### Stores and local state

| Class | Probe | Default name |
|---|---|---|
| `SqliteHealthCheck(connection \| db_path, query="SELECT 1")` | The database opens and answers | `sqlite:<stem>` |
| `StalenessHealthCheck(getter, warn_after, fail_after)` | A timestamp the service supplies is recent enough | none, must be named |

`ScyllaHealthCheck(session, keyspace=None)` lives in the Argus application, not
in this package, for the reason above. It probes
`SELECT release_version FROM system.local` at `LOCAL_ONE`, through the live
`Session` and `execute_async`. It never builds a cluster of its own: connecting
is the expensive part, a private cluster would double the connection count, and
a probe that connects successfully proves nothing about the pool the service
uses. It reports UNHEALTHY when the query fails or no coordinator answers, and
DEGRADED with the live host count when the session works but some hosts are
down.

### Primitives

Every primitive is public. A new dedicated check is a subclass of one, with the
probe and the defaults filled in.

| Class | Reports |
|---|---|
| `HttpHealthCheck(url, method="GET", expect=range(200, 400), latency_budget=None, headers=None)` | Reachability of an HTTP dependency. Over the latency budget gives DEGRADED. A wrong status or a transport error gives the failure status. |
| `TcpHealthCheck(host, port)` | A port accepts a connection. For a tunnel, or a database with no cheap query. |
| `BinaryHealthCheck(binary, version_args=("--version",))` | An executable is on `PATH` and answers. |
| `CallableHealthCheck(fn)` | Adapter for an async function. |

No check targets another service's health surface. Nothing in the code can
enforce that, so it is a review rule.

## Zeus integration

Zeus owns `src/health/wiring.py`: one function that registers the checks the
service always wants, built from the clients and stores the service already
constructed. A source that gates its loop on a dependency registers that
dependency itself, in its own `run()`, and the two registrations collapse.

| Class | Severity | Notes |
|---|---|---|
| `JenkinsApiHealthCheck` | important | Takes the client from `create_jenkins_http_client()`. There is no `JENKINS_URL` setting, so the base comes from the first entry of `JENKINS_MONITORED_JOB_URLS`. Skipped when that list is empty. Jenkins down pauses that source and degrades Zeus; it does not take the whole service down. |
| `JiraApiHealthCheck` | important | |
| `GitHubApiHealthCheck` | important | Given `GITHUB_BOT_LOGIN`, so a credential that rotates to another account is caught, not only one that stops working. |
| `AnthropicApiHealthCheck` | critical | |
| `HeadroomProxyHealthCheck` | important | Registered only when `HEADROOM_PROXY_URL` is set. |
| `ArgusApiHealthCheck` | important | |
| `MaiaApiHealthCheck` | important | Registered only when `MAIA_ENABLED`. |
| `OpencodeHealthCheck` | critical | Always registered. `zeus.agent` fails every investigation without it. |
| `GhCliHealthCheck`, `AcliHealthCheck`, `ArgusCliHealthCheck`, `JenkinsCliHealthCheck` | important, per source | Registered only when the source that needs the tool is in `ENABLED_SOURCES`. |
| `SqliteHealthCheck` | critical | One per open store, given that store's connection, registered per enabled source. |
| `StalenessHealthCheck` | important | Over `JENKINS_LAST_POLL_TIMESTAMP`, warning at three poll intervals. |
| `queue_depth` | important | The one check with no class. A decorated function reading the `MeteredQueue` depths. |

A source that is not in `ENABLED_SOURCES` contributes no checks. There is no
disabled status, because a status that means "ignore me" gets ignored when it
matters.

`queue_depth` and `QUEUE_DEPTH` in `src/monitoring/metrics.py` read the same
queue and answer different questions. The metric is a time series for a graph,
updated on every enqueue and dequeue. The check turns saturation into a status
that reaches the aggregate and the alert.

Wiring points in `src/main/app.py`:

- Build the runner inside the existing `MONITORING_ENABLED and not cli_mode`
  branch, next to the samplers, and call the wiring function on it.
- Add `runner.run(shutdown_event)` to `monitoring_tasks` through the same
  `_guarded()` wrapper that already protects them.
- Call `runner.register_collector()` once. `MetricsServer` on `MONITORING_PORT` (9300)
  already serves the default registry, so the health series join that exposition
  and Zeus keeps one scrape job.
- Hand the runner to every source, so a source that gates its polling loop
  subscribes to its own dependency. A source that gates on nothing ignores it.
- CLI mode builds nothing, for the same reason the samplers are excluded there.
  `CLISource.run()` returns without setting the shutdown event, and a serving
  task would hang `gather()`. A source that runs in both modes therefore takes
  the runner as optional and skips the gate when it has none.
- Pass `on_change`, wired to the `_notify()` helper in
  `src/main/systemd_watchdog.py`, for example
  `STATUS=degraded: github_api unhealthy`. `systemctl status zeus` then carries
  the reason on the box, with no HTTP call and no Prometheus. `_notify()` takes
  a public name, because it gains a caller outside its own module.
- Declare `GITHUB_TOKEN` in `src/config.py`. It sits in `.env.example` and
  nothing reads it today, because Zeus reaches GitHub only through `gh`.
  `GitHubApiHealthCheck` is the first Zeus code that needs the value itself.

`notify_ready()` keeps firing where it does today, before the first checks
complete. Holding `READY=1` until every dependency answered would make unit
activation depend on Jenkins being up, and risk `TimeoutStartSec` during an
outage. For the same reason the watchdog stays independent of the runner: a
watchdog ping derived from a health result would let a failed Jira probe kill a
process that is holding queued work.

`src/monitoring/server.py` keeps its constant `/health` route until the metrics
and the dashboard are live, then loses it, together with
`tests/test_monitoring_server.py::test_health_endpoint`.

## Where it lives

The package lives in the `qatools-health/` subdirectory of `scylladb/argus`.
Each service installs it as a git dependency pinned to a `qatools-health-v*`
tag:

```
uv add "qatools-health @ git+https://github.com/scylladb/argus.git@qatools-health-v0.1.0#subdirectory=qatools-health"
```
