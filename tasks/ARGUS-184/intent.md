# ARGUS-184 — Run links need the run UUID, not the Jenkins build

## Problem

A person who finishes a CI run holds the Jenkins job path and the build
number. Most Argus links to a run page carry the run UUID and the plugin
name, `/tests/<plugin>/<run_id>`. Nobody holds that pair after a build, and
nobody can produce it from the build.

Argus can already resolve a run from its build, at
`/test/<build_id>/<build_number>`. The CLI test commands, chat, the issue
links, the release summary and the cost explorer use that form. Most other
places still use the UUID form:

- The run page header link.
- The address that the run page rewrites on a tab switch. A person who opens
  a run by its build lands back on the UUID form after one click.
- The similar events list.
- The view widgets for nemesis stats, graphed stats, the summary and pytest.
- The results graph tooltip.
- The report email.
- The links that `argus replay` prints.

`argus run get` accepts only `--run-id`. The CLI has no way to show a run
from its build.

One Jenkins build can submit several runs, one per parallel stage. They all
carry the same build_id and build_number. The build lookup returns only the
first of them. The other runs of that build cannot be reached by the build at
all.

## Who it affects

- Engineers who hold a Jenkins job path and a build number, from a CI
  notification, a chat message or a ticket, and want the Argus results.
- Engineers who copy a run link from the run page, a widget or an email to
  share it. The link carries a UUID that says nothing about the build.
- CLI users who script `argus run get` from a build.
- Pipelines with parallel stages that report several runs from one build.

## Evidence

Jira ARGUS-184, "View test run results by build ID and build number (web +
CLI)", status In Progress:

> Today, viewing a run's results requires its run UUID, e.g. https://argus.scylladb.com/tests/scylla-cluster-tests/403af98d-0ebb-4eff-ae59-ed033a335581.
> What's actually on hand after a CI run is the Jenkins job path and build number, not the UUID, e.g. scylla-staging/lukasz/artifacts-azure-image-test build 32. There is currently no way to jump from that information straight to the run view — you have to search Argus or dig through the job first.

> CLI: argus run details (cli/cmd/run_details.go) accepts --build-id/--build-number as an alternative to --run-id

> in case one build number points to parallel run (multiple run id’s per build) - show them all

> Acceptance: given a job path and build number (no run UUID), both the Argus web UI and the CLI can display the corresponding run's results.

The CLI has no `run details` command. The equivalent is `argus run get`.

The run page rewrites the address on a tab switch,
`frontend/TestRun/TestRun.svelte:239`:

```js
                const newUrl = `/tests/${testInfo.test.plugin_name}/${runId}/${tabName}`;
```

The run page header link, `frontend/TestRun/TestRun.svelte:267`:

```svelte
                <a class="link-dark" href="/tests/{testInfo.test.plugin_name}/{testRun.id}">
```

The report email, `templates/email/partials/main.html.j2:3`:

```html
    <h2><a class="btn-link-dark" href="http://argus.scylladb.com/tests/scylla-cluster-tests/{{ options['run_id' ]}}/details">Info</a></h2>
```

`argus replay`, `cli/cmd/replay.go:417`:

```go
			link.URL = api.RunPageURL(base, r.Type, r.ID)
```

The build lookup returns one run, `argus/backend/service/testrun.py:97-98`:

```python
        runs = await plugin.model.find(build_id=build_id, build_number=build_number).allow_filtering().all()
        return runs[0] if runs else None
```

## What good looks like

- Every link to a run page that the web UI, the report email and the CLI
  produce has the form `/test/<build_id>/<build_number>`.
- On a page opened by its build, a tab switch keeps the address in that form.
- When one build has several runs, its build link shows all of them.
- `argus run get` shows a run from its build id and build number, without a
  run UUID. It shows every run of the build.

## Out of scope

- The `/tests/<plugin>/<run_id>` route stays. Existing bookmarks and
  external links keep working.
- The links to the workspace of a test, `/test/<test_id>/runs`, are not run
  pages and stay as they are.
- Runs without a build number get no fallback link.
- The report email keeps its hard-coded host.
