# ARGUS-176 — Generic results cannot be read across tests

## Problem

Argus stores results per test. An engineer can read the results of one test
when they know its `test_id`. Argus cannot answer a question about the same
result across many tests. Pytest, driver matrix, sirenada and SCT run data
have the same gap. This task fixes it for generic result tables.

Every read of `generic_result_data_v1` and `generic_result_metadata_v1`
starts with `WHERE test_id = ?`. No table has a partition key that starts
from the result name or from time. Argus cannot answer "show the
`throughput` table of every test for the last two weeks" without a read of
the full metadata table and one query per `(test_id, name)` pair.

The CLI has no command that reads generic results across tests. An engineer
or an agent must find every `test_id` first, and then read each test one by
one.

The results endpoints are in `argus/backend/controller/api.py`, next to
unrelated endpoints. `api.test_results` is a per-test read, and its name does
not show that.

## Who it affects

- Engineers who use the Argus CLI to compare one metric across tests, such
  as p99 latency for every CDC or LWT test.
- AI agents (Zeus, Maia) that read Argus through the CLI and the `argus`
  skill. They need short, grouped output that they can reason about.
- Maintainers of the results endpoints in `api.py`.

## Evidence

Jira issue ARGUS-176:

```
Argus "generic result tables" are currently reachable web-only and queryable only per-test_id: every read starts WHERE test_id = ?, so there is no cross-test access path.
```

Israel Fruchter on ARGUS-176:

```
sound externally useful for agent work/analysis
```

Lukasz Sojka on ARGUS-176:

```
Anyway, this draft was wrong and we didn’t proceed with proper solution.
```

Pull request https://github.com/scylladb/argus/pull/1033 implemented the
design from the issue. It reads all of `generic_result_metadata_v1`, sends
one `ALLOW FILTERING` query per `(test_id, name)` pair, and sorts and limits
in Python. The review stopped it.

pehala on the fan-out:

```
AFAIK This pattern is constant source of performance problems, would it be possible to use different paradigm, like cache tables?
```

k0machi:

```
Agreed, this pattern should be avoided now.
```

soyacz on the response shape:

```
this response looks very bad. Not humans, nor LLM will be able to easily reason from them.

Need to group by table, -> subgroups `test_id` -> subgroups `run_id`. Stretch goal: along `test_id` show canonical name (like build_id).
```

soyacz on the time axis:

```
besdes sut_timestamp. there's a `WRITETIME` - which is the time people think when filtering by time. sut_timestamp is datetime (usually just a date) of the Scylla build.
```

soyacz on the endpoints:

```
Good idea to create this file. Let's move all results api (`argus/backend/controller/api.py`) here (you can rename endpoints and adjust frontend to use new one). Don't change client-api endpoints.
```

soyacz on the review:

```
We need to pause on this implementation and align on the design and API agreement first.
```

## What good looks like

- `argus results` lists every generic result table name across tests, with
  the number of tests and the columns of each.
- `argus results` returns the generic results for the table names that match
  a name, across all tests of a release, filtered by status and by time range.
- The output is grouped by table name, then by test with its `build_id`,
  then by run.
- Time filters use the time the result was submitted. The output also shows
  `sut_timestamp`, and a filter on `sut_timestamp` is available.
- The results endpoints from `api.py` are in their own router. The frontend
  calls the new routes. The client API endpoints do not change.

## Out of scope

- Pytest, driver matrix, sirenada and SCT run data.
- A cross-test results view in the web UI.
- Changes to the client API that submits results.
