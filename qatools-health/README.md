# qatools-health

Health checking for the ScyllaDB QA Tools services. A service subscribes to the
dependencies it cares about, the package probes each one on its own schedule,
and the results become Prometheus metrics. Every service that uses the package
exports the same series, so one dashboard and one set of alert rules cover all
of them.

A subscription is the unit. The check instance is the subject a caller
subscribes to, the runner holds one probe loop per distinct dependency however
many subscribers it has, and closing the last subscription retires the check. A
caller therefore never asks whether a dependency is already registered.

The package opens no port and serves no route. It produces a Prometheus
collector, and the service registers that collector with the registry its own
exporter already serves.

It imports nothing from Argus. It depends on `prometheus-client` and `httpx`,
and on nothing else.

This code has no comments and no docstrings, by repository policy. This file
is the API reference.

## Install

```
pip install -e ./qatools-health
```

A service installs it as a git dependency pinned to a `qatools-health-v*` tag:

```
uv add "qatools-health @ git+https://github.com/scylladb/argus.git@qatools-health-v0.1.0#subdirectory=qatools-health"
```

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
        warn_after=900,
        fail_after=3600,
        name="jenkins_poll",
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

### Gating a component on its dependency

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
Jenkins, the GitHub API and the `gh` binary all answer.

## Status

`HealthCheckStatus` is a `StrEnum` with three members, ordered from best to
worst: `HEALTHY`, `DEGRADED`, `UNHEALTHY`.

A check that has not run yet publishes UNHEALTHY. A value that never arrived is
not evidence of health.

`worse_of(*statuses)` returns the worst of the statuses given, and `HEALTHY`
for an empty call. `is_worse(candidate, reference)` compares two statuses.

## Severity

`Severity` is a `StrEnum` with three members: `CRITICAL`, `IMPORTANT` and
`OPTIONAL`. It decides what a check's own UNHEALTHY or DEGRADED result does to
the service aggregate.

| Member | Effect on the aggregate |
| --- | --- |
| `CRITICAL` | An UNHEALTHY result turns the service UNHEALTHY. |
| `IMPORTANT` | An UNHEALTHY or DEGRADED result turns the service DEGRADED, never further. |
| `OPTIONAL` | Nothing. The result stays visible in the check's own series and in the log. |

`IMPORTANT` is the default. `strictest_severity(*severities)` returns the worst
of the severities given.

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
| `severity` | `IMPORTANT` | What a failure of this check does to the service aggregate. |
| `interval` | `300.0` | Seconds between two runs. |
| `timeout` | `10.0` | Seconds before a run is abandoned. |
| `stale_after_intervals` | `3.0` | How many missed intervals make the last value stale. |

A check therefore carries its own configuration, and a caller passes an instance
and nothing else. `OpencodeHealthCheck()` is already `Severity.CRITICAL`,
already named `opencode`, and already on its own interval.
`SqliteHealthCheck(conn, name="sqlite:context")` is the same class registered
twice under two names.

A check with no name raises at construction. A non-positive `interval`,
`timeout` or `stale_after_intervals` raises at construction.

### perform_check

```python
async def perform_check(self) -> Any
```

Runs the probe once and returns what it found. It takes no arguments. A check
author stores nothing, schedules nothing, and never sees where the result goes.

It may raise. An exception becomes an UNHEALTHY result with the exception
message as `error`, so an implementation needs no `try`/`except` of its own to
report a failure.

The return value is coerced, so a trivial check needs no imports:

| Returned | Recorded as |
| --- | --- |
| `HealthCheckResult` | itself |
| `HealthCheckStatus` | that status, no message |
| `True` or `None` | HEALTHY |
| `False` | UNHEALTHY |
| raised exception | UNHEALTHY, with the message as `error` |
| anything else | UNHEALTHY, with a `TypeError` message as `error` |

`None` counts as healthy, so a check written as "raise when it is broken" does
not have to end with a `return` statement that says nothing.

Every check body awaits. A synchronous call inside one blocks the other checks
and the embedding service's whole loop. A dependency whose library has no async
client either gets a check written against an async client, or gets no check.

### identity

```python
def identity(self) -> tuple[object, ...]
```

Two instances that probe the same thing are the same check. The base class
derives an identity from the concrete class and the arguments the constructor
received, minus the five policy keywords above, and the runner keys the check by
it. A caller therefore constructs an instance wherever it needs one and never
holds a registry of its own.

Override `identity()` for the case the default gets wrong.
`JenkinsApiHealthCheck(client=jenkins_client)` and
`JenkinsApiHealthCheck(base_url, user, token)` name one Jenkins, so
`HttpHealthCheck` returns the probe URL from both forms. A subclass overrides
`identity()` when the argument list carries more than the dependency it names,
and leaves it alone otherwise.

An identity value never reaches a log line, a metric label or a `repr`. A
credential is an ordinary constructor argument, so the identity is compared and
hashed but never rendered.

Policy is not part of the identity. Two registrations of one dependency with
different severities, intervals or timeouts collapse into one check that takes
the strictest of each: the worst severity, and the shortest interval, timeout
and staleness window. A subscriber cannot be made worse off by another
subscriber it does not know about. The name must match, and a second name for
one identity raises, because the two would otherwise publish one probe under two
series. Two distinct identities under one name raise for the same reason.

### aclose

```python
async def aclose(self) -> None
```

Releases what this check opened. The runner calls it once the last subscription
closes, and again for every live check from `stop()`. Only a check that built
its own client implements it. A check that received a client does not close it.

A check builds its own client on the first probe, never in `__init__`. A
constructor that opens nothing costs nothing, which is what makes
`GitHubApiHealthCheck(GH_TOKEN, GH_LOGIN)` safe to write in three places that do
not know about each other.

### Inline checks

The `healthcheck` decorator builds a `HealthCheck` instance from an async
function, and that instance registers like any other.

```python
@healthcheck(name="queue_depth", interval=30)
async def queue_depth(): ...
```

It also works bare, and then takes the function name:

```python
@healthcheck
async def queue_depth(): ...
```

The decorator constructs the instance and does not register it, so the set of
checks never depends on which modules an interpreter happened to import. The
identity is the decorated function, so registering the same decorated function
twice yields one check.

A synchronous function raises `TypeError`.

## Subscription

`register()` returns a `HealthCheckSubscription`.

| Member | Meaning |
| --- | --- |
| `check` | The instance the runner probes, which is the first instance registered under that identity. |
| `status` | The last computed status, including the staleness rule. It never blocks and never probes. |
| `result` | The last `HealthCheckResult`, or `None` before the first probe. |
| `wait_for(*statuses, timeout=None)` | Returns as soon as the check reads one of the given statuses. |
| `close()` | Ends the subscription. It is idempotent, and the object is a context manager. |

A caller that registers a duplicate gets a subscription over the instance
already running, and its own instance is discarded unused. Nothing reads the
passed instance after `register()` returns, which is why a check must open
nothing in its constructor.

`wait_for()` returns the current result immediately when the check already reads
one of the given statuses, so a caller does not race the first probe. It raises
`TimeoutError` past `timeout`, and `SubscriptionClosedError` when the
subscription closes while it waits.

The last `close()` cancels the timer, awaits a probe in flight, calls
`aclose()`, and removes the series from the exposition. The check keeps running
while another subscription holds it.

## Group

`register_all()` returns a `HealthCheckGroup`: one handle over several checks,
with the same `status`, `wait_for()` and `close()` a single subscription has, and
the same context manager.

| Member | Meaning |
| --- | --- |
| `members` | The member subscriptions, in the order given. |
| `status` | The worst status among the members. |
| `group[check]` | The member subscription for one check, by identity. It raises `KeyError` for a check the group does not hold. |
| `wait_for(*statuses, timeout=None)` | Returns the group status as soon as it reads one of the given statuses. |
| `close()` | Closes every member. |

`wait_for(HEALTHY)` therefore returns when every member reads HEALTHY, and a
group with one member reads exactly like that member.

Severity does not enter this. Severity says what a failing dependency does to
the service status on a dashboard, and a group says what a failing dependency
does to one caller's loop. A caller that puts an `OPTIONAL` check in its own
gate meant to wait for it. A caller that wants the dashboard rule reads
`runner.status` instead.

A member held by another subscriber keeps running after `close()`. A
`wait_for()` in flight when the group closes raises `SubscriptionClosedError`,
as a member's does.

## Runner

```python
HealthCheckRunner(
    *,
    service,
    version="",
    on_change=None,
    clock=time.time,
)
```

| Member | Meaning |
| --- | --- |
| `collector` | The Prometheus collector to register with a registry. |
| `status` | The aggregate status right now. |
| `register(check, *, on_change=None)` | Subscribe to one dependency. |
| `register_all(checks, *, on_change=None)` | Subscribe to several, as one group. |
| `register_collector(registry=None)` | Register the collector. Defaults to `prometheus_client.REGISTRY`. |
| `unregister_collector(registry=None)` | Remove the collector from a registry. |
| `start()` | Arm the first timer for every check registered so far and return. Not a coroutine, and it does not block. |
| `stop()` | Cancel every armed timer, await the checks still in flight, call `aclose()` on each check, and end every open subscription. |
| `run(shutdown)` | `start()`, wait for the `asyncio.Event`, `stop()`. The only method that blocks. |
| `snapshot()` | The last known value of every check, as plain data. |

`register()` is safe from any thread and at any time, before `start()` and long
after it. It returns a subscription synchronously, and it neither blocks nor
probes. The runner arms the new timer on its own loop, so a caller on another
thread gets a subscription that reads no result yet, and a `wait_for()` on it
resolves once the first probe lands. A check registered after `start()` runs at
once.

`register_all()` registers each check the same way and returns one group over
all of them. It either registers every check or none: a name or identity
conflict raises before the first timer is armed.

`start()` is the whole lifecycle for a service that already has a place to put
background work. `run()` is the variant for a service that wants one awaitable
for `asyncio.gather`.

## Callbacks

```python
OnChange = Callable[[HealthCheck, HealthCheckResult], Awaitable[None] | None]
OnGroupChange = Callable[[HealthCheckStatus, str], Awaitable[None] | None]
```

A callback fires on a change of status, never on a repeated reading. A
dependency down for a day calls back twice: once on the way down and once on the
way back. The runner caches the last result of every check to hold this
guarantee, and that same cache is what the scrape and `subscription.status`
read.

A subscriber gets the current result as its first callback when the check
already holds one, and the first probe result otherwise. A subscription created
mid-flight against a dependency that has been HEALTHY for an hour therefore
learns the status without waiting an interval.

A never-run check publishes UNHEALTHY to the metrics and to the aggregate, and
delivers no callback. Every subscriber would otherwise see one UNHEALTHY at
startup that no dependency caused.

A callback runs on the health loop. A coroutine function is awaited, a plain
function is called, and neither may block: a slow callback delays the checks. A
callback that raises is logged once per transition and changes nothing else, and
the subscription stays open.

The runner-level `on_change` fires on every change of the aggregate status, with
the new status and a reason that names the check behind it. It is the one way a
service acts on a transition the package knows nothing about, such as writing
the systemd status line.

```python
runner = HealthCheckRunner(
    service="zeus",
    on_change=lambda status, reason: notify(f"STATUS={status}: {reason}"),
)
```

The group callback takes the same pair, over the members of that group.

## Scheduling

Every check runs on its own interval, independently of every other check.

- The next run is scheduled after the previous one returns. A check slower than
  its interval runs less often and never overlaps itself.
- A run that exceeds its timeout is recorded as UNHEALTHY, with the message
  `timed out after Ns`.
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

## Aggregation

Over every check registered at that moment:

1. Any UNHEALTHY on a `CRITICAL` check gives UNHEALTHY.
2. Otherwise any UNHEALTHY or DEGRADED on a `CRITICAL` or `IMPORTANT` check
   gives DEGRADED.
3. Otherwise HEALTHY.

Registering a check and retiring one both recompute the aggregate, so a
subscription that ends takes its check out of the service status in the same
step that takes it out of the exposition.

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
this rule and UNHEALTHY by the rule above, and the worse of the two wins, so a
never-run `CRITICAL` check makes the service UNHEALTHY. That window closes after
the first run, which is armed within the first second and bounded by the check's
timeout.

## Last known value

Checks run on their own timers and take different amounts of time. A scrape
lands wherever it lands. The exposition therefore always carries the last known
value of every check.

- A check's value updates when it completes. Between completions it holds the
  previous one.
- Every check has a value from the first scrape onward. A check that has not
  completed yet publishes UNHEALTHY with a last-run timestamp of 0. The series
  exists, so an alert can see it. An absent series would instead say that the
  dependency is gone.
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

## Metrics

The collector builds the metric families on each scrape from the last result of
every check. It runs no check, blocks on nothing, and does no I/O, so it is safe
to call from whatever thread or loop the host's exporter uses.

The series follow the registered checks exactly. Retiring a check removes its
series instead of leaving a stale label combination frozen at its last value.

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
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
copy of the same fact on every dependency series would only invite a query that
recomputes the aggregate differently from the runner.

`healthcheck_subscribers` is the one series about the package rather than a
dependency. A series that disappears is either a source that shut down or a
subscription leak, and the count separates the two.

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
describe an HTTP request or a subprocess, and it does not decide what a cheap
probe of Jenkins looks like. That decision is made once, in the class, for all
three services.

Every class that talks to a dependency takes that dependency in `__init__`. The
first argument is the client, session or connection the service already built.
The credential form is the fallback for a service that has none.

```python
JenkinsApiHealthCheck(client=jenkins_client)
JenkinsApiHealthCheck(base_url, JENKINS_USER, JENKINS_API_TOKEN)
```

Pass the live client wherever one exists. A check that builds its own connection
tests a second configuration: its own timeouts, its own pool, its own view of
the credential. When the service's client is broken and the check's private one
is not, the dashboard stays green while the service fails.

### External APIs

Each one takes `client=` for an existing `httpx.AsyncClient`, or the credentials
shown. The identity is the base URL in both forms, so the two reach one check. A
class that gets neither a base URL nor a client carrying one raises.

| Class | Probe | Default name | Severity |
| --- | --- | --- | --- |
| `JenkinsApiHealthCheck(base_url, user, token)` | `GET <base>/api/json?tree=mode` | `jenkins_api` | important |
| `JiraApiHealthCheck(base_url, email, token)` | `GET /rest/api/3/myself` | `jira_api` | important |
| `GitHubApiHealthCheck(token, expected_login=None, low_budget_fraction=0.1)` | `GET /rate_limit`, plus the authenticated login when an expected login is given | `github_api` | important |
| `ArgusApiHealthCheck(base_url, token, cf_id=None, cf_secret=None)` | `GET /api/v1/notifications/get_unread`, the cheapest authenticated read | `argus_api` | important |
| `AnthropicApiHealthCheck(api_key, model="claude-haiku-4-5")` | The Claude API component on the public status page, then `POST /v1/messages` with `max_tokens: 1` | `llm_api` | critical |

`HeadroomProxyHealthCheck` and `MaiaApiHealthCheck` live in Zeus, not here.
Zeus is their only consumer today, and the promotion rule for this package is
two or more consumers.

`GitHubApiHealthCheck` keeps the expected login in its identity, so the probe
that compares the login and the probe that does not stay two checks.

A token that answers is not a token that works. `GitHubApiHealthCheck` reads the
core budget out of `/rate_limit` and reports UNHEALTHY at zero and DEGRADED
under `low_budget_fraction` of the limit, with the minutes left until the reset.
A spent budget also stops the identity read, so the check never spends the last
request on itself. GitHub answers a rate-limited call with 403 or 429 and
`x-ratelimit-remaining: 0`, so the message for a refused read names the rate
limit instead of the bare status code.

`AnthropicApiHealthCheck` runs two probes. The first reads the `Claude API
(api.anthropic.com)` component from `https://status.anthropic.com/api/v2/summary.json`.
An outage there returns at once, because a key probe against a broken platform
tells the service nothing and costs a request. The status page takes no
credentials, so the check sends it no key. An unreachable status page is not a
verdict, and the check falls through to the key probe.

The second probe is `POST /v1/messages` with `max_tokens: 1`. A models list
proves that the key parses. Only a completion proves that the key is
authorized, has credit, and is inside its rate limit, which are the three ways
the LLM API fails in production. One token every five minutes costs about a
cent a year on Haiku. A 429 or a 529 is DEGRADED, because both clear on their
own. Anything else, including the 400 that carries `credit balance is too low`,
is UNHEALTHY.

The Anthropic API pins every model identifier, so `model` names a real model and
no floating alias exists to track. The probe model is a constructor argument.
Point it at the cheapest current model and move it when that model retires.

### Command-line tools

Each one confirms that the executable resolves and answers, and reports the
version it found in its message.

| Class | Binary | Default name | Severity |
| --- | --- | --- | --- |
| `OpencodeHealthCheck()` | `opencode` | `opencode` | critical |
| `GhCliHealthCheck(verify_auth=False)` | `gh` | `gh` | important |
| `AcliHealthCheck()` | `acli` | `acli` | important |
| `ArgusCliHealthCheck()` | `argus` | `argus_cli` | important |
| `JenkinsCliHealthCheck()` | `jenkins-cli` | `jenkins_cli` | important |

Argus and Jenkins carry the `_cli` suffix because an API check of the same
service already holds the plain name.

A CLI check does not verify credentials. Presence and version are local and
fast. Authentication is a network call, and it belongs to the matching API
check, so a missing binary and an expired token stay two different cells on the
dashboard. `GhCliHealthCheck(verify_auth=True)` merges them for a service that
prefers one.

### Databases

| Class | Probe | Default name | Severity |
| --- | --- | --- | --- |
| `SqliteHealthCheck(connection \| db_path, query="SELECT 1")` | The database opens and answers | `sqlite:<stem>` | critical |

The connection is `aiosqlite.Connection`, the driver Zeus's own stores already
use, so the check awaits the query instead of blocking the loop or routing
through a worker thread. A connection given without a name keeps the class
name `sqlite`, so register two of them under explicit names.

A path opens through the `file:...?mode=rw` URI, and the check reports UNHEALTHY
when the file is absent. A plain `aiosqlite.connect(path)` call creates an empty
database, which turns a lost data file into a healthy check over zero rows.

`ScyllaHealthCheck(session, keyspace=None)` lives in Argus and not here. Argus
connects through `scylla-driver`, Zeus and Maia have no driver, and the Zeus
bundle vendors every resolved dependency, so a driver in this package would put
a C extension in a service that never queries Scylla.

### Local resources

| Class | Reports | Default name |
| --- | --- | --- |
| `StalenessHealthCheck(getter, warn_after, fail_after)` | A timestamp the service supplies is recent enough | none, must be named |

The getter returns a unix timestamp, or `None` when nothing has been recorded
yet. It may be synchronous or a coroutine function.

### Primitives

For a dependency with no dedicated class yet. A new dedicated check is a
subclass of one of these, with the probe and the defaults filled in. This is how
the lists above grow.

| Class | Reports |
| --- | --- |
| `HttpHealthCheck(url, method="GET", expect=range(200, 400), latency_budget=None, headers=None, auth=None, client=None)` | Reachability of an HTTP dependency. Over the latency budget gives DEGRADED. A wrong status or a transport error gives UNHEALTHY. |
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
uv venv --python 3.12
uv pip install -e '.[dev]'
.venv/bin/pytest --cov=qatools_health
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```
