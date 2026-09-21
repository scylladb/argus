# QATOOLS-425 — Report the health of the Argus dependencies

## Problem

Argus reports nothing about the things it depends on. When ScyllaDB, the S3
bucket, Jenkins, GitHub, Jira or nginx fails, Argus keeps answering requests
and fails them one by one. An operator learns about the outage from a user or
from a failed test run, not from a dashboard or an alert.

The SSH tunnel proxies make this worse. `sshd` on every proxy asks Argus for
the authorized keys. When that lookup fails, the tunnel refuses every
connection, and nothing on the Argus side shows the failure.

The `qatools-health` package exists in this repository under
`qatools-health/`, and Argus does not use it. The package needs Python 3.13.
Argus declares `requires-python = ">=3.10, <3.14"`, and every workflow pins
3.12. The package also builds its metrics in one process, while Argus serves
four gunicorn workers that share a multiprocess Prometheus directory.

## Who it affects

The operators of Argus, who watch the "QA Tools — Service Health" dashboard
and receive its alerts. The Jenkins pipelines and the SSH tunnel proxies that
depend on Argus. The Zeus and Maia teams, whose dashboard rows use the same
series and need the Argus row next to them.

## Evidence

Jira QATOOLS-425:

> Implement Healthcheck reporting inside Argus

Jira QATOOLS-392, the parent task:

> Every dependency is marked critical or optional. Critical down = 503.
> Optional down = degraded, still 200. Jira being slow must not take the
> service out of the load balancer.
> Results are cached for 5m and served from cache. The endpoint must never
> fan out one request per caller.
> A check talks to its dependency directly (SELECT 1, a HEAD on an API, a
> stat on the disk). It never calls another service's /health. No cascading.
> No auth on the endpoint, Only Internal network (separate HTTP Port for
> Argus)

> Argus: ScyllaDB, S3 bucket, Jenkins API, GitHub API, Jira API, nginx. Also
> the SSH tunnel key-lookup path, since sshd on every proxy depends on it and
> a failure there is silent from the Argus side.

> All three services answer /health and /health/ready, and export the
> dependency metrics.
> Hammering /health/ready does not add load to any dependency.

`qatools-health/README.md`, section "Multiprocess exporters":

> `prometheus_client` in multiprocess mode builds the exposition from the files
> in `PROMETHEUS_MULTIPROC_DIR`. It does not call a custom collector. A service
> that runs several worker processes, such as Argus under uwsgi, must run the
> runner in a single process with its own exporter.

`qatools-health/pyproject.toml`:

> requires-python = ">=3.13"

## What good looks like

Argus answers `/health` and `/health/ready` on a separate internal port with
no authentication. `/health/ready` answers 503 only when a critical
dependency is down, and 200 when only an important or optional one is down.
Both answers come from the last cached results, so any number of requests
adds no load to a dependency. The port also exports the `healthcheck_*`
series with `service="argus"`, one `dependency` label value for each of
ScyllaDB, S3, Jenkins, GitHub, Jira, nginx and the SSH tunnel key lookup. The
Argus row on the service health dashboard turns red when ScyllaDB stops, and
the ScyllaDB cell names the cause.

## Out of scope

The Grafana dashboard and the alert rules, which QATOOLS-426 owns. The
Prometheus scrape job in `qatools-deployments`. Health checks for Zeus and
Maia. A change to the `argus-alm` client package or its Python floor.
