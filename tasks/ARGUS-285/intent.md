# ARGUS-285 — Mark SCT runs that ran on minicloud

## Problem

SCT can provision a run through minicloud, a local cloud emulator, instead of
the real cloud. Such a run reports to Argus as a plain `aws`, `gce` or
`azure` run, with real instance types and regions. Nothing in the run view
says it ran on minicloud, so readers take it for a real cloud run.

## Evidence

Jira: [ARGUS-285](https://scylladb.atlassian.net/browse/ARGUS-285). Example
run: <https://argus.scylladb.com/tests/scylla-cluster-tests/7d6abc4a-b8d3-4042-91ef-11f5d910aa42>.

SCT turns minicloud on through the `minicloud_endpoint_url` config param
(`sdcm/utils/minicloud/endpoint.py`, `is_minicloud_active`). SCT submits its
config, so Argus stores it per run as `sct_config.minicloud_endpoint_url`.

## What good looks like

The run view shows a clear "minicloud" marker at the top of the run and next
to the backend, so a reader sees at a glance that the run did not use the
real cloud.

## Out of scope

Filtering or marking minicloud runs in the run lists and release dashboards.
