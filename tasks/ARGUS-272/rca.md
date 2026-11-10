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
   engines print it as text. Parse it with the layout
   `2006-01-02 15:04:05.999999999 -0700 MST`. Docker prints
   `2026-11-10 10:05:47 +0100 CET` and Podman prints
   `2026-11-10 09:05:42.615310779 +0000 UTC`. Before `run`, ask the engine
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

- `cli/cmd/prometheus_test.go`: the run arguments carry the qualified
  image, `127.0.0.1::9090`, and `--userns=keep-id` only for rootless
  Podman. The parse of `ps` lines finds the stale container in the Docker
  and the Podman `CreatedAt` formats.
- `cli/cmd/prometheus_test.go`, `TestResolveEngine_*`: the command takes
  `docker` first and `podman` when `docker` is missing.
  `ARGUS_CONTAINER_ENGINE` names the engine when it is set. With no
  engine, the error names Docker, Podman and the variable.
- `cli/cmd/prometheus_cmd_unix_test.go`: with `ARGUS_CONTAINER_ENGINE`
  set to a fake `podman`, `start` and `stop` run `podman`. A rootless
  `info` answer adds `--userns=keep-id` to `run`.

The real engines are checked by hand: Docker on the workstation, and
rootful and rootless Podman 5 in a Rocky Linux 9 container.

## Risks

| Risk | Response |
|---|---|
| A host has both engines and the user wants Podman | `ARGUS_CONTAINER_ENGINE=podman` selects it. |
| Containers started by the Docker engine stay invisible to Podman, and the reverse | The engine choice is stable on one host, and `ARGUS_CONTAINER_ENGINE` keeps it fixed. |
| A host with both engines switches the engine between calls. Both engines share the data root, so `start` and `stop --all` on one engine remove the run data of the other engine's containers. | Use one engine on each host. The QA Tools hosts have only Podman. |
| `--userns=keep-id` is missing on an older Podman | The QA Tools hosts run Rocky Linux 9, which ships Podman 5 with the flag. |
| The `info` query fails on rootless Podman | The command then runs without `--userns=keep-id`, and the start fails with the Prometheus log, which shows the permission error. |
| `127.0.0.1` breaks a caller that reads Prometheus from another host | The output names `http://localhost:<port>`, so no caller depends on the other addresses. |
