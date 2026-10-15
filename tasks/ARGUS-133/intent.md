# ARGUS-133 — Trim the run, log and pytest output of the Argus CLI

## Problem

An LLM agent reads Argus runs through the `argus` CLI. Three parts of the
command set give it more than it needs.

Two commands read one run by its ID. `argus run get` prints the summary of
the Argus Details tab. `argus run details` prints the whole run. The agent
must choose between them for every run. `run details` is also the only
command that shows some fields of a run:

- SCT: `allocated_resources`, `cloud_setup`, `junit_reports`, `packages`,
  `config_files`, `screenshots`, the `gemini_*` and `perf_*` fields.
- driver-matrix-tests: `test_collection`.
- sirenada: `results`.

`argus run logs list` prints each log name with the link stored on the run.
The link is a raw `https://<bucket>.s3.amazonaws.com/<key>` URL, or any URL
a user added. Nothing in the CLI reads it. `argus run logs download` takes the
name and fetches the log through Argus. The listing does not create S3 links,
as the issue assumes. It copies the stored strings. Only the download
endpoint presigns a link.

`argus run pytest-results` and `argus pytest results` return results of
every status. Most results of a dtest run are `passed` or `skipped`. The agent
looks for the failures and must filter them itself. The DTest tab of a run
shows the failures by default.

## Who it affects

- LLM agents that triage runs through the `argus` CLI.
- Engineers who read the same output in a terminal.

## Evidence

ARGUS-133:

```
remove run details - not needed (we have run get and other subcommands)
remove links from logs list - LLM won't be using them (also we don't have to create s3 links when listing)
pytest-results - should by default return failures (like we have defaults in Argus Dtest tab - excluding "passed","xfailed","xpass","skipped")
```

The help of `argus run get`, `cli/cmd/testrun.go`:

```
Show the basic summary of a test run — the same information visible
on the Argus Details tab — without heavy fields such as logs, screenshots,
events, nemeses, or cloud resources.
```

The log download endpoint presigns the stored link,
`argus/backend/service/testrun.py`:

```python
link = {log[0]: log[1] for log in run.logs}.get(log_name)
if not link:
    raise TestRunServiceException(f"Log name {log_name} not found.")
match = self._match_s3_link(link)
if not match:
    return link
presigned_url = await asyncio.to_thread(
    self.s3.generate_presigned_url, ClientMethod="get_object",
    Params={"Bucket": match.group("bucket"), "Key": match.group("key")}, ExpiresIn=3600)
```

The default status filter of the DTest tab,
`frontend/TestRun/Pytest/PytestRun.svelte`:

```ts
[PytestStatus.PASSED]: false,
[PytestStatus.FAILURE]: true,
[PytestStatus.ERROR]: true,
[PytestStatus.XFAILED]: false,
[PytestStatus.XPASS]: false,
[PytestStatus.PASSED_ERROR]: true,
[PytestStatus.FAILURE_ERROR]: true,
[PytestStatus.SKIPPED_ERROR]: true,
[PytestStatus.ERROR_ERROR]: true,
[PytestStatus.SKIPPED]: false,
```

## What good looks like

- One command reads a run by its ID. It prints the summary by default and the
  whole run when asked. Every field that `argus run details` shows today stays
  readable from the CLI.
- `argus run logs list` prints the log names only. Every listed name still
  downloads with `argus run logs download`.
- `argus run pytest-results` and `argus pytest results` print only the
  statuses the DTest tab shows by default. The caller can ask for other
  statuses or for every status.

## Out of scope

- A backend endpoint that returns only the log names of a run. The listing
  fetches the whole run, and for SCT that costs four more queries.
- The `get_log` lookup for plugins that store logs as a map, generic and
  sirenada. It reads the first two characters of each name. Those plugins
  store no logs today.
- The default statuses of the Pytest Stats view widget.
- What `argus run get` prints when the whole run is not asked for.
