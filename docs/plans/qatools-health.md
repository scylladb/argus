---
status: in_progress
domain: infrastructure
created: 2026-09-03
last_updated: 2026-09-03
owner: CodeLieutenant
---

# QA Tools Health Checking Package

## 1. Problem Statement

QATOOLS-392 needs one health-check subsystem in Zeus, Argus and Maia. Each
service reports its condition in a different place, and the three answers do not
agree. Zeus has a constant `/health` route, a systemd watchdog and a set of
Prometheus gauges. A source that returns early leaves all three green while that
source is dead.

Argus has the same gap in a different shape. `argus/backend/metrics.py` exports
request counters only. No series says whether Scylla answers, whether the Jenkins
credential still works, or whether the Jira token expired. An operator finds out
when a user reports a broken page.

Writing the subsystem three times produces three metric names, three label sets
and three dashboards. One package produces one of each.

## 2. Current State

Argus holds no health-check code. The relevant facts about the repository today:

| Fact | Evidence |
| --- | --- |
| The web backend is synchronous Flask under uwsgi | `uwsgi.ini`, `argus_backend.py` |
| Four worker processes serve the app | `uwsgi.ini`, `processes = 4` |
| Prometheus runs in multiprocess mode | `uwsgi.ini`, `env = PROMETHEUS_MULTIPROC_DIR=...` |
| The exporter is `prometheus-flask-exporter` | `argus/backend/metrics.py` |
| The repository contains no `asyncio` code | `grep -rl asyncio` returns nothing |
| Ruff excludes the `argus/` tree | `pyproject.toml`, `exclude = ["argus/"]` |
| CI runs Python 3.12 | `.github/workflows/test.yml` |
| Periodic work runs as one-shot Flask CLI commands | `argus/backend/cli.py` |

The package is therefore new code in a new tree. It is not an addition to
`argus/`.

The design is fixed by `docs/superpowers/specs/2026-08-31-healthcheck-design.md`
in `scylladb/zeus` (PR 179). This plan implements that spec.

## 3. Goals

1. A `qatools-health` package builds and tests on its own, and imports nothing
   from `argus`.
2. The package depends on `prometheus-client` and `httpx`, and on nothing else.
3. The public API matches the spec exactly: `HealthCheckStatus`,
   `HealthCheckResult`, `HealthCheck`, `healthcheck`, `HealthCheckRunner`.
4. The runner emits the ten metric families the spec lists, with the label sets
   the spec gives.
5. Every built-in check class the spec lists exists, except
   `ScyllaHealthCheck`, which needs `scylla-driver`.
6. Test coverage of the package is 90 percent or higher, measured by
   `pytest --cov=qatools_health`.
7. `ruff check qatools-health` reports zero findings.

## 4. Implementation Phases

### Phase 1: Package skeleton and core types

**Importance**: Critical

Create `qatools-health/` with its own `pyproject.toml`, a `src/` layout and the
value types the rest of the package builds on.

- `status.py`: `HealthCheckStatus` and `worse_of`.
- `result.py`: `HealthCheckResult`, its three constructors, and `coerce_result`
  for the return-value table in the spec.

**Definition of Done**

- [x] `uv run --directory qatools-health pytest` passes.
- [x] `HealthCheckStatus` orders HEALTHY, DEGRADED, UNHEALTHY from best to worst.
- [x] `coerce_result` maps a result, a status, `True`, `False` and `None`.
- [x] The package declares `requires-python = ">=3.11"` for `StrEnum`.

### Phase 2: Check base class and decorator

**Importance**: Critical

- `check.py`: the `HealthCheck` abstract base, its class attributes, and the
  keyword-only constructor that overrides any of them per instance.
- The `healthcheck` decorator, which builds an instance from an async function.

**Definition of Done**

- [x] A subclass that sets class attributes needs no constructor.
- [x] A constructor keyword overrides the matching class attribute.
- [x] `aclose()` is a no-op unless a subclass overrides it.
- [x] The decorator returns a `HealthCheck` instance, and registers nothing.

### Phase 3: Runner, scheduling and aggregation

**Importance**: Critical

- `runner.py`: one task per check, the next run armed after the previous
  returns, a timeout per run, and the first runs spread over one second.
- Aggregation, staleness and the `on_change` callback.
- `start()`, `stop()` and `run(shutdown)`.

**Definition of Done**

- [x] A duplicate check name raises at construction.
- [x] A run over its timeout records `failure_status` with `timed out after Ns`.
- [x] A check slower than its interval never overlaps itself.
- [x] A status change logs once: INFO on recovery, WARNING on failure.
- [x] A stale check contributes at least DEGRADED, and never softens a status.
- [x] `stop()` cancels the timers, awaits the runs in flight, then calls
      `aclose()` on every check.

### Phase 4: Prometheus collector

**Importance**: Critical

- `collector.py`: a `Collector` that builds the metric families from the last
  result of every check. It runs no check and does no I/O.
- `register()` and `unregister()` on the runner.

**Definition of Done**

- [x] The ten families in the spec appear with the given names and labels.
- [x] A check that has not run publishes `failure_status` and a last-run
      timestamp of 0.
- [x] Removing a check removes its series.
- [x] `healthcheck_runner_up` reads 0 after `stop()`.
- [x] No message text reaches a label.

### Phase 5: Primitives

**Importance**: Critical

- `checks/primitives.py`: `HttpHealthCheck`, `TcpHealthCheck`,
  `BinaryHealthCheck` and `CallableHealthCheck`.

**Definition of Done**

- [x] `HttpHealthCheck` gives DEGRADED over its latency budget.
- [x] `HttpHealthCheck` closes a client it built, and never one it received.
- [x] `BinaryHealthCheck` reports the version it found in its message.
- [x] `TcpHealthCheck` closes the connection it opened.

### Phase 6: Built-in checks

**Importance**: Important

- `checks/http_apis.py`: Jenkins, Jira, GitHub, Argus, Anthropic, Headroom and
  Maia.
- `checks/cli_tools.py`: opencode, gh, acli, md2adf, argus and jenkins.
- `checks/databases.py`: `SqliteHealthCheck`.
- `checks/local.py`: `StalenessHealthCheck`.

**Definition of Done**

- [x] Every class carries its own default name, criticality and interval.
- [x] Every class that talks over HTTP accepts `client=` for a live client.
- [x] `GitHubApiHealthCheck` compares the login when one is given.
- [x] `SqliteHealthCheck` names itself `sqlite:<stem>` from a path.
- [x] `StalenessHealthCheck` raises when no name is given.

### Phase 7: Documentation and CI

**Importance**: Important

- `qatools-health/README.md` carries the public API, because the repository
  bans docstrings.
- A GitHub Actions job runs ruff and pytest over the package.

**Definition of Done**

- [x] The README documents every public class and every metric.
- [x] The workflow runs on a change under `qatools-health/`.

## 5. Testing Requirements

**Unit tests** live in `qatools-health/tests/` and run with `pytest-asyncio`.
They cover:

- The coercion table, one case per row.
- Aggregation, one case per rule, including the stale interaction.
- Scheduling, with a fake clock, covering timeout, overlap and spread.
- The collector, over a registry built for the test.
- Each primitive, against a local HTTP server or a fake client.

**Integration tests** are not needed. The package opens no port, reads no
configuration and talks to no service of its own.

**Manual testing**: register a runner with two checks in a Python shell, call
`start()`, and read `generate_latest()` twice to confirm the values move.

## 6. Success Criteria

Every Definition of Done above is met, and:

- A second service can adopt the package by adding one dependency and one list
  of checks.
- The package tree contains no import of `argus`, verified by grep in CI.

## 7. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Argus has no process to host an async runner, so the package ships unused | High | Medium | Accepted for now. This plan builds the package only. Argus wiring is a separate plan, and it must first choose a host process. |
| A custom collector is invisible under `PROMETHEUS_MULTIPROC_DIR` | High | High | Argus wiring must either run the runner in a single-process daemon with its own exporter, or write `mostrecent` gauges. The package keeps the collector, because Zeus and Maia are single-process. |
| The spec ties checks to async, and every Argus client library is synchronous | High | Medium | Argus checks will need a thread hop. The package stays async, as the spec requires. |
| A check name reaches a label and grows unbounded | Low | High | Names are class attributes or constructor keywords. The runner rejects duplicates. Tests assert that no message text becomes a label. |
| The package drifts from the Zeus copy of the spec | Medium | Medium | One repository holds the package. Zeus and Maia install it, and do not copy it. |
