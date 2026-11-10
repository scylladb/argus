# ARGUS-272 — argus prometheus on Podman

**Date**: 2026-11-10

## Root cause

`cli/cmd/prometheus.go` uses the Docker command line. Five of its calls
depend on behavior that only Docker has.

1. `promImage` (line 30) is the short name `prom/prometheus:latest`. Podman
   enforces short-name resolution, and without a TTY it cannot ask which
   registry to use:
   `Error: short-name resolution enforced but cannot prompt without a TTY`.
2. `promDockerRunArgs` (line 788) publishes the port with `-p 0:9090`.
   Docker reads host port `0` as "any free port". Podman refuses it:
   `Error: parsing host port: port numbers must be between 1 and 65535 (inclusive), got 0`.
   The value also has no host address, so Docker binds `0.0.0.0` and `[::]`.
3. `pruneOldContainers` (lines 616-645) runs `ps --format json`. It decodes
   one JSON object per line, with `Names` as a string. It parses `CreatedAt`
   with the layout `2006-01-02 15:04:05 -0700 MST`. Podman prints one JSON array,
   `Names` is a list, and `CreatedAt` is `"Less than a second ago"`. Every
   line fails to decode, and the loop skips it with `continue`. The prune
   removes nothing and shows no error.
4. Every container call runs the literal `"docker"` (lines 241, 250, 299,
   503, 514, 520, 545, 581, 595, 605, 617, 642), and `checkDocker`
   (line 436) looks only for `docker` on the path. A host with only Podman
   fails with `docker not found in PATH`.
5. `promDockerRunArgs` runs the container as `--user <uid>:<gid>`. Rootless
   Podman maps container IDs into the subordinate ID range of the caller, so
   that user is not the owner of the run directory on the host, and
   Prometheus cannot write its TSDB there.

## Approaches

1. **Selected.** Resolve the engine once per command and pass it to the
   helpers. `ARGUS_CONTAINER_ENGINE` names the engine when set. Else the
   command uses `docker` when it is on the path, else `podman`. Use
   `docker.io/prom/prometheus:latest` and `-p 127.0.0.1::9090`, which both
   engines accept. Read `ps --format '{{.Names}}\t{{.CreatedAt}}'`. Both
   engines print it as text. Cut the zone name, and parse the rest with the
   layout `2006-01-02 15:04:05.999999999 -0700`. Docker prints
   `2026-11-10 10:05:47 +0100 CET` and Podman prints
   `2026-11-10 09:05:42.615310779 +0000 UTC`. A zone with no abbreviation
   prints the offset as the name, as in `+0545 +0545`. Before `run`, ask the engine
   `info --format '{{.Host.Security.Rootless}}'`, and add
   `--userns=keep-id` when the answer is `true`. Docker has no such field
   and fails the query, so it never gets the flag. Cost: about 60 lines in
   one file. Risk: an engine that is neither Docker nor Podman.
   Reason: one code path serves both engines, and the tests can cover both
   with the fake engine binary.
2. A Go client of the Docker API, with the Podman socket for Podman. Cost:
   a new dependency and a running socket service on every host. Risk:
   rootless Podman needs the user socket enabled. Too large for five
   command-line differences.
3. Ask the user to install `podman-docker`. Cost: none in the code. It
   fixes row 4 only, and rows 1, 2, 3 and 5 still fail.

## Regression test

- `cli/cmd/prometheus_test.go`: the run arguments carry `127.0.0.1::9090`,
  and `--userns=keep-id` only for rootless Podman. The parse of `ps` lines
  finds the stale container in the Docker and the Podman `CreatedAt`
  formats, and in a zone with no abbreviation.
- `cli/cmd/prometheus_test.go`, `TestResolveEngine_*`: the command takes
  `docker` first and `podman` when `docker` is missing.
  `ARGUS_CONTAINER_ENGINE` names the engine when it is set. With no
  engine, the error names Docker, Podman and the variable.
- `cli/cmd/prometheus_cmd_unix_test.go`: with `ARGUS_CONTAINER_ENGINE`
  set to a fake `podman`, `start` and `stop` run `podman`.
  `rootlessPodman` is true for a rootless `info` answer, and false when
  `info` fails as it does on Docker.

The image name is a constant, so no unit test covers it. The real engine
check pulls it with no TTY. The real engines are checked by hand. Section
`Validation` holds the results.

## Risks

| Risk | Response |
|---|---|
| A host has both engines and the user wants Podman | `ARGUS_CONTAINER_ENGINE=podman` selects it. |
| Containers started by the Docker engine stay invisible to Podman, and the reverse | The engine choice is stable on one host, and `ARGUS_CONTAINER_ENGINE` keeps it fixed. |
| A host with both engines switches the engine between calls. Both engines share the data root, so `start` and `stop --all` on one engine remove the run data of the other engine's containers. | Use one engine on each host. The QA Tools hosts have only Podman. |
| `--userns=keep-id` is missing on an older Podman | The QA Tools hosts run Rocky Linux 9, which ships Podman 5 with the flag. |
| The `info` query fails on rootless Podman | The command then runs without `--userns=keep-id`, and the start fails with the Prometheus log, which shows the permission error. |
| `127.0.0.1` breaks a caller that reads Prometheus from another host | The output names `http://localhost:<port>`, so no caller depends on the other addresses. |

## Validation

### Real engines

The check used a cached monitor-set archive, so `start` made no API call. It ran `start`, `list` and `stop`, then read the port, the listen address and the owner of the run directory.

- Docker 29.1.3 on the workstation.
- Podman 5.8.2, rootful and rootless, in `docker run --privileged rockylinux/rockylinux:9`. The storage driver is `vfs` and the cgroup manager is `cgroupfs`. The rootless user `tester` has the subordinate IDs `100000:65536`.

| Engine | upstream/master | This branch |
|---|---|---|
| Docker | — | `start`, `list` and `stop` pass. `9090/tcp -> 127.0.0.1:32768`. `ss` shows `127.0.0.1:32768` only. The files belong to `1000:1000`. |
| Rootful Podman, no `docker` | `Error: docker not found in PATH; please install Docker to use this command` | `start`, `list` and `stop` pass. `9090/tcp -> 127.0.0.1:35917`. `/-/ready` answers `Prometheus Server is Ready.` |
| Rootful Podman, `docker` calls `podman` | `Error: parsing host port: port numbers must be between 1 and 65535 (inclusive), got 0` | `start`, `list` and `stop` pass. `9090/tcp -> 127.0.0.1:33499`. |
| Rootless Podman, `docker` calls `podman` | `Error: parsing host port: port numbers must be between 1 and 65535 (inclusive), got 0` | `start`, `list` and `stop` pass. `9090/tcp -> 127.0.0.1:33993`. The files belong to `1000:1000`. |
| Rootless Podman, no `docker` | — | `start`, `list` and `stop` pass. `9090/tcp -> 127.0.0.1:45551`. The files belong to `1000:1000`. The create command holds `--user 1000:1000 --userns=keep-id`. |

Cause 5 without `--userns=keep-id`, as `tester`: `podman run --user 1000:1000 -v <dir>:/prometheus:z ...` exits with `open /prometheus/queries.active: permission denied`.

Cause 1, the short image name, did not show on upstream/master. Podman stops at the port error before it resolves the image. With the fix, rootless Podman pulled `docker.io/prom/prometheus:latest` into new storage with no prompt.

### Real metrics data

A monitor-set archive held a TSDB snapshot of a Prometheus that scraped itself, with data up to 10:37:47 UTC. Podman ran in a new Rocky Linux 9 container with empty image storage, so the fix also pulled `docker.io/prom/prometheus:latest` with no TTY. Docker ran in a separate daemon in `docker run --privileged docker:29-dind`.

| Engine | Owner of the run files | `prometheus_build_info` at 10:37:40 UTC | `count(up)` at 10:37:40 UTC |
|---|---|---|---|
| Docker 29.9.3 | `0:0` (root in the daemon) | 1 series, version 3.16.0 | `1` |
| Rootful Podman 5.8.2 | `0:0` | 1 series, version 3.16.0 | `1` |
| Rootless Podman 5.8.2 | `1000:1000` | 1 series, version 3.16.0 | `1` |

On each engine, `start` moved the TSDB block to the top of the data directory, and `list` and `stop` pass.

### Prune

The check created `argus-prom-stale001` on each engine, waited more than one hour (`promMaxTTL`), then ran `start`. The prune runs at the start of `start`.

| Engine | upstream/master | This branch |
|---|---|---|
| Rootful Podman | `argus-prom-stale001` stays. | `start` removes `argus-prom-stale001`. |
| Rootless Podman | `argus-prom-stale001` stays. | `start` removes `argus-prom-stale001`. |
| Docker 29.9.3 | — | `start` removes `argus-prom-stale001`. |

The Docker check used a separate daemon in `docker run --privileged docker:29-dind`, so no other `argus` on the workstation could prune its container. 56 minutes after the create, this branch kept the stale container on Podman. 21 seconds after the create, it kept the stale container on Docker.
