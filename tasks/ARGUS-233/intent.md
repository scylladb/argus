# ARGUS-233 — HEAD on the log download endpoint answers 405

## Problem

`GET /api/v1/tests/{plugin}/{run_id}/log/{log_name}/download` answers a 302
redirect to the signed S3 URL. The same path answers 405 Method Not Allowed to
a `HEAD` request.

A client that only wants the `Location` header sends `HEAD`, because the body
is a multi-gigabyte archive. That client now gets 405 and no `Location`.

## Who it affects

- `QA-tools/hydra-show-monitor`. Every run fails. Build 2322 on 2026-09-04
  passed, builds 2323 to 2328 up to 2026-09-15 fail.
- The SCT `pr-merge` check. Its post-build "Restore Monitor stack" step runs
  the same command, so a pull request with green stages still reports failure.
- Any `hydra investigate show-monitor` run by hand.

## Evidence

```
Download file https://argus.scylladb.com/api/v1/tests/scylla-cluster-tests/<run-id>/log/monitor-set-<short>.tar.zst/download
Failed to download monitoring stack archive: Argus communication failed: no redirect occurred.
This may indicate authentication issues or a Cloudflare access problem. Status: 405,
URL: https://argus.scylladb.com/api/v1/tests/scylla-cluster-tests/<run-id>/log/monitor-set-<short>.tar.zst/download
Errors were found when restoring Scylla monitoring stack
```

The "authentication / Cloudflare" wording in the SCT message is misleading.
Cloudflare answers `HEAD` with its own 302 login redirect. The 405 comes from
the Argus application.

## What good looks like

`HEAD` on the log download path returns the same 302 and the same `Location`
header as `GET`.

## Out of scope

- The SCT client. Pull request scylladb/scylla-cluster-tests#16080 already
  resolves the link with a non-followed `GET`.
- The wording of the SCT error message.
- The routes that redirect a browser to another Argus page.
