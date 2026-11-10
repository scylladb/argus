# ARGUS-272 — argus prometheus on Podman

## Problem

`argus prometheus` calls the `docker` command. On a host with Podman and no
Docker, the command stops with `docker not found in PATH`. With the
`podman-docker` command in place of `docker`, four more calls fail:

- The short image name does not resolve without a TTY.
- Podman refuses the host port `0`.
- Podman prints a different `ps --format json`. The prune removes nothing,
  and it shows no error.
- Rootless Podman maps the container user into the subordinate IDs. That
  user cannot write the run directory, which the caller owns.

Docker also publishes Prometheus on `0.0.0.0` and `[::]`, so a host on the
network can read the metrics of a run.

## Who it affects

Callers of `argus prometheus` on a host with Podman. The QA Tools hosts move
to rootless Podman (QATOOLS-668), and the Zeus metrics skills need
`argus prometheus` there (QATOOLS-593).

## Evidence

From ARGUS-272, a test with Podman 5 on Rocky Linux 9 at upstream/master
8c519abe:

| # | Code in `cli/cmd/prometheus.go` | Result on Podman |
|---|---|---|
| 1 | `promImage = "prom/prometheus:latest"` | `Error: short-name resolution enforced but cannot prompt without a TTY` |
| 2 | `-p 0:9090` in `promDockerRunArgs` | `Error: parsing host port: port numbers must be between 1 and 65535 (inclusive), got 0` |
| 3 | `pruneOldContainers` reads `ps --format json` | Podman prints one JSON array, `Names` is a list, and `CreatedAt` is `"Less than a second ago"`. The prune removes nothing, and it shows no error. |
| 4 | `exec.Command("docker", ...)` and `checkDocker` | `docker not found in PATH` when only Podman is installed. |
| 5 | `--user <uid>:<gid>` from scylladb/argus#1127 | Rootless Podman maps the container user into the subordinate IDs. That user cannot write the run directory, which the caller owns. |

> These calls work on Podman with no change: rm -f, logs --tail,
> inspect -f '{{.State.Running}}', port <name> 9090/tcp, and
> ps --filter 'name=^/<name>$'.

## What good looks like

- `argus prometheus start`, `list` and `stop` work on Docker, on rootful
  Podman, and on rootless Podman.
- The prune removes a container older than `promMaxTTL` on both engines.
- Prometheus listens only on `127.0.0.1`.
- Unit tests cover the run arguments of each engine and the parse of both
  `CreatedAt` formats.

## Out of scope

- The Podman setup on the QA Tools hosts (QATOOLS-668).
- The Zeus metrics skills (QATOOLS-593).
- Engines other than Docker and Podman.
