# ARGUS-185 — implementation plan

**Spec:** `tasks/ARGUS-185/spec.md`

## Spec corrections

Two lines of the spec are wrong against the code. The plan follows the code,
and Task 1 commits the correction.

1. **`NoneAsEmptyDict` is not needed.** The spec's model snippet annotates the
   field with it. Argus reads through `CassandraDriver`, whose
   `needs_row_validation` is false, so a read takes the coodie `model_construct`
   fast path, where a `BeforeValidator` never runs. The NULL becomes `{}` one
   step earlier, in `coerce_row_none_collections`, on every read path. The
   annotation is code that cannot fire. `NoneAsEmptyList` earns its place
   because it sits inside a user-defined type, which that coercion does not
   reach.

2. **Do not ask Jenkins for `_class`.** The spec's Inputs block names it in the
   tree. `_class` arrives on every object whether or not the tree asks for it,
   and a field that is not an exported property is the one way to lose it. The
   current scan proves it: the tree asks for `url,color,name,jobs`, and the
   code reads `job["_class"]` in production.

## Constraints

- The non-goals of the spec bound this work: no search by label, no lookup
  table, no user-defined type, no new table, no read-time fetch from Jenkins,
  no parsing of `config.xml` or of a build description, no admin editing, no
  Go CLI change.
- Ruff excludes `argus/`, so no linter reads the backend diff. Read it by hand
  for a dead import and a long line.
- The column is `map<text, text>`. Every value is a string, or the write fails
  inside the cron. A list literal becomes a JSON array string.
- Refresh with `update()`. `save()` writes every column, and would clobber an
  admin edit to `assignee`, `enabled` or `pretty_name` made between the read at
  the start of the scan and the write.
- Mock Jenkins in a test. Keep the database real.
- Add no comment that justifies a change. Correct a comment the change makes
  wrong.
- Commit each task on its own, and stage by explicit path.
- Run the verify sequence from the `Commands` section of `CLAUDE.md` before
  each commit.

## Task 1 — The column

**Files:**
- Modify: `argus/backend/models/web.py:221-236`
- Modify: `tasks/ARGUS-185/spec.md`, the model snippet and the Inputs block
- Test: `argus/backend/tests/build_system_monitor/test_test_metadata_column.py`

**Internals:** the `ArgusTest.test_metadata` field.

Add the field above `class Settings`:

```python
test_metadata: dict[str, str] = Field(default_factory=dict)
```

`ArgusTest` already carries a scalar `description` column. It is a different
thing from the `description` key inside the map, no backend code writes it, and
nothing renders it. Leave it alone, and keep the map key named `description`,
because the Outputs block of the spec is the API.

- [ ] Write the failing test, marked `docker_required`: a row saved with a map
      reads it back, a row saved with an empty map reads back `{}` and not
      `None`, and a row written before the column reads as `{}`.
- [ ] Run it and confirm the failure.
- [ ] Add the field, and correct the spec.
- [ ] Apply the schema with `uv run python -m argus.backend.cli sync-models`,
      and confirm the `ALTER TABLE ... ADD`.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 2 — The parser

**Files:**
- Create: `argus/backend/service/test_metadata.py`
- Test: `argus/backend/tests/build_system_monitor/test_parse_test_metadata.py`

**Internals:** `parse_test_metadata(description: str | None) -> dict[str, str] | None`,
`apply_test_metadata(test: ArgusTest, description: str | None) -> bool`.

The module goes under `argus/backend/service/`, because `pyproject.toml` names
that directory in `norecursedirs` and sets no `testpaths`. A production module
named `test_*.py` in any other directory is collected by pytest. `test_lookup.py`
and `test_hierarchy.py` sit there for the same reason. Do not name the test file
`test_metadata.py`, so that the two base names never collide.

`parse_test_metadata` returns `None` when the heading is absent, and `None`
again when the block gives neither a pair nor prose. An empty map wipes a
populated column on the next refresh.

Rules, tighter than the four lines of the spec, because the loose reading has
three ways to corrupt the map:

- Match the heading as `^\s*#{1,6}\s*TestMetadata\s*:?\s*$`, case-insensitive.
  Take the first one when it occurs twice.
- Skip a blank line between the heading and the first pair. Markdown convention
  puts one there, and a stop at it gives an empty map.
- Match a pair as `^([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(.*)$`, and split on the
  first colon, so a value that holds a colon keeps its tail. A looser pattern
  takes in the prose line that follows the block.
- Stop at the first line that does not match. Keep every key, whatever its name.
- Read a list literal with `ast.literal_eval`, never `eval`, inside
  `try/except (ValueError, SyntaxError)`. Accept the result only when it is a
  `list`, apply `str()` to each element, then `json.dumps` it. Anything else
  falls back to the trimmed raw string.
- Trim every other value, and store it as written.
- The prose is the last paragraph above the heading that is neither a heading
  nor a bare Jenkinsfile path. It goes under the key `description`.
- Accept `\n` and `\r\n`.

`apply_test_metadata` assigns the parsed map to `test.test_metadata`, and
returns whether the value changed. It writes nothing.

Cases: the real description in `tasks/ARGUS-185/intent.md`; a first line in the
`test: ... | backend: ...` form in place of a Jenkinsfile path; no heading;
`None` and an empty string; a blank line after the heading; three keys and five
keys, in any order; a line that ends the block; prose after the block, which
stays out of the map; CRLF; a list literal, a double-quoted one, an empty one
and a malformed one; a value that holds a colon, and one that holds a comma; a
duplicate key; an empty value. Assert that every value is a `str`. For
`apply_test_metadata`: `True` on a change, `False` on an equal map, and `False`
with the stored map intact when the parser returns `None`.

- [ ] Write the failing tests.
- [ ] Run them and confirm the failure.
- [ ] Write the module.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 3 — The scan

**Files:**
- Modify: `argus/backend/service/build_system_monitor.py:47-59`, `:96-193`
- Test: `argus/backend/tests/build_system_monitor/test_build_system_monitor.py`

**Internals:** `_jobs_query`, `_fetch_release_jobs`, `_normalize_jobs`, the
dormant skip, the refresh branch, the `create_test` parameter.

The name case comes first. Jenkins exports `fullName`. python-jenkins never
asks for it, and `get_all_jobs` builds the lowercase `fullname` on the client.
A hand-built tree therefore returns `fullName` and no `fullname`, while
`collect()` reads the lowercase key in ten places. Without normalization the
group lookup matches nothing, the scan creates every group and every test a
second time, and `validate_build_system_id` raises `ArgusTestException` per
test into the log that the code already swallows. The failure is silent
duplication, not a crash. One recursive pass over the fetched subtree, which
sets `fullname` from `fullName` and falls back to the joined path, keeps the
rest of `collect()` unchanged. Every step below depends on it.

Six changes in `JenkinsMonitor`.

1. **The per-release tree.** Build the item as the URL path, not the job name:
   `"/".join(f"job/{s}" for s in release_fullname.split("/"))`. Pass it with the
   query to `get_info`. Do not use the private `_get_job_folder`; it returns a
   pair shaped for a different format string. Fields:
   `fullName,displayName,description,url,name`, nested nine levels, without
   `_class`. `get_info` quotes the item with `safe="/"` and appends the query
   after that, so pass a raw name and never an encoded one.

2. **The depth guard.** Below the depth of the query, Jenkins returns a child
   that holds `_class` and nothing else. Unguarded, that placeholder passes the
   `"Folder" in job["_class"]` test, reaches the stack, and raises `KeyError` on
   `group["name"]` outside a matching handler, which stops the whole run and not
   one release. Find a child that has no `url`, as python-jenkins does, and
   fetch that folder again, rooted there. Nine levels covers the observed
   `release/group/test` and `release/group/subgroup/test` layouts, so the guard
   should never fire.

3. **The dormant skip.** Resolve the release row, then skip when
   `saved_release.dormant` is true, before any per-release request. A release
   that matches a pattern and is not in Argus yet is still created and scanned,
   which is how a release is discovered. Resolve it from the in-memory
   `self._existing_releases`, which the constructor loads and no code reads
   today, with `first()` from `argus/backend/util/common.py`, in place of the
   index query per release. That change also makes `collect()` testable without
   a database.

4. **Isolation per release.** Catch `Exception`, not `jenkins.JenkinsException`.
   `get_info` turns an HTTP error into `BadHTTPException`, but a `requests`
   `ConnectionError` or `Timeout` passes through, and those are the likely
   failures. Log once with `exc_info`, and continue. Log the elapsed time per
   release, as the risk table of the spec states. Keep the read of
   `info["jobs"]` inside the existing `try/except KeyError`: two monitored
   patterns can match a `WorkflowJob`, and a tree query against a job that is
   not a folder returns no `jobs` key. That is what the "Empty release!" branch
   is for.

5. **A client timeout.** `jenkins.Jenkins` is built with no `timeout`, so it
   takes the socket default, which is none. The cron starts every five minutes
   and `scan_jobs.sh` takes no lock, so one hung connection stops the scan for
   good and the processes pile up. This task multiplies the number of requests,
   so pass an explicit `timeout`.

6. **The writes.** Give `create_test` a keyword parameter
   `test_metadata: dict[str, str] | None = None`, and assign it before `save()`.
   Pydantic applies a `default_factory` under `model_construct`, so the field
   defaults to `{}` on its own, and the parameter only carries the parsed map.
   On the branch for an existing test, which only logs today, call
   `apply_test_metadata`, and write the one column with
   `saved_test.update(test_metadata=...)` when it returns `True`.

   Use a plain update, not a lightweight transaction. The SCT packages fix needs
   one because it merges a value it read. This write assigns a value that comes
   wholly from Jenkins, so two scans that race compute the same map and the last
   write wins. A lightweight transaction costs a Paxos round per test on the
   first scan after the deployment.

   Wrap the parse, the comparison and the write of one job in
   `except Exception: LOGGER.error(..., exc_info=True)`. The branch has only
   `except StopIteration` today, so one odd description stops the run.

Two more changes in the same code. First, the eager default:
`group.get("displayName", self._jenkins.get_job_info(...))` evaluates its
default argument for every new group, so it calls Jenkins even when the value is
there. With `displayName` in the tree, change it to `group.get("displayName")
or ...`. Jenkins returns the same value the extra call fetched, so the behavior
holds, and an N+1 on the first scan of a new release goes away.

Second, the discovery request. Every monitored pattern is two segments deep at
most, so `get_all_jobs(folder_depth=1, folder_depth_per_request=2)` returns what
discovery needs in one request, with a three-level payload in place of a
ten-level one. It is safe only because change 1 stops the reads of
`release["jobs"]`, so confirm that both readers now take the fetched subtree.
Without it the change is a net increase in traffic, because the global tree and
the per-release trees overlap.

The monitor has no test today, and its constructor opens a real Jenkins
connection and reads three tables. Follow the fake-client pattern in
`argus/backend/tests/jenkins_service/test_jenkins_service.py`: build the
instance with `object.__new__`, set a fake that exposes `get_all_jobs` and
`get_info`, and set the four in-memory attributes. Stub the three writer methods
on the instance, to keep these tests off Docker.

Cases: the item string for a nested release; the nine-level query; `fullName`
normalized at every level; a placeholder child fetched again in place of a
raise; a subtree with no `jobs` key, which reaches the "Empty release!" branch;
a dormant release, which makes no `get_info` call; a `ConnectionError` on one
release, which does not stop the next; an unknown release, created and scanned;
a new test that carries the map; a description that did not change, which writes
nothing; a description that changed, which writes the one column; a description
with no block, which leaves the stored map alone.

Add one `docker_required` test beside them for the real write: `update()`
changes the column, and leaves `assignee` and `enabled` untouched.

- [ ] Write the failing tests.
- [ ] Run them and confirm the failure.
- [ ] Make the six changes, the `displayName` fix and the discovery cut.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 4 — The shared metadata component

**Files:**
- Create: `frontend/Common/TestMetadata.svelte`
- Test: `frontend/Common/TestMetadata.test.ts`

**Internals:** the props `metadata` and `compact`, a derived label list, a
`supported_backends` parse.

One presentational component for all four surfaces. Svelte 5 runes, `lang="ts"`,
typed props, in the shape of `frontend/Common/IssueBadge.svelte`.

- `metadata: Record<string, string> = {}` and `compact = false`.
- Derive the label list in the script block, never in the markup. Take
  `description` out of the map, and render the rest as badges. Put the four keys
  SCT writes today first, then any other key in the order it arrives, so that a
  key SCT adds later renders with no frontend change.
- Read `supported_backends` as a JSON array, and render one badge per backend.
  Treat every other value as text, and fall back to the raw string when the
  parse throws.
- Use the Bootstrap `badge text-bg-*` variants, which pair the background and
  the foreground in one rule. Write no custom color rule. Check both themes.
- `compact` renders the badges only.
- An empty map renders nothing.

- [ ] Write the failing test: the badges render, the backends split, a bad JSON
      value falls back to text, an unknown key renders, an empty map renders
      nothing.
- [ ] Run it and confirm the failure.
- [ ] Write the component.
- [ ] Run `yarn test` and `yarn build`.
- [ ] Commit.

## Task 5 — The planner surfaces

**Files:**
- Modify: `frontend/AdminPanel/ViewSelectItem.svelte:26-53`
- Modify: `frontend/ReleasePlanner/ReleasePlanCreator.svelte:376-405`, `:647-699`
- Modify: `frontend/ReleasePlanner/ReleasePlannerGridView.svelte:308-350`

No backend change. Every planner payload comes from `TestLookup.index_mapper`,
which calls `model_dump()`, so the new column already reaches the search, the
gridview, the explode and the resolve responses.

The search item. `ViewSelectItem.svelte` renders a hit from
`/api/v1/planning/search`. It also serves a group, a release and an "Add all"
hit, and the admin views manager shares it, so guard the block on
`item.type === "test"` and on a map that is not empty. Render the component
below the name.

The selected list. `handleAllItemSelect` and `handleItemSelect` cut a hit down
to `{name, release, group, type, id}` and drop the rest. Carry `test_metadata`
through both, then render the component in the selected row. The other three
producers, `explodeGroup`, `resolvePlan` and `handleGridConfirmation`, push the
payload objects unchanged, and already carry the map.

The grid tile. Render the component in `compact` mode in the tile, and put the
description in the `title` attribute of the tile. The tile is 178px wide with a
196px maximum height, set by `.status-block`. Badges hold that density, and the
prose arrives on hover.

- [ ] Write the failing test for the search item: a test hit with a map renders
      the badges, a group hit does not.
- [ ] Run it and confirm the failure.
- [ ] Make the three edits.
- [ ] Check the grid at two widths and in both themes.
- [ ] Run `yarn test` and `yarn build`.
- [ ] Commit.

## Task 6 — The run page tab

**Files:**
- Modify: `frontend/TestRun/TestRun.svelte:55-68`, `:317-393`, `:395-479`

**Internals:** the `test_metadata` entry on the `TestInfo` interface, the
`testinfo` tab.

`GET /api/v1/test-info` already returns `test.model_dump()`, so
`testInfo.test.test_metadata` arrives with no backend change.

- Add `test_metadata: Record<string, string>` to the exported `TestInfo`
  interface.
- Add the tab button to the bar, and the matching entry to the `<select>`. Both
  lists are written by hand and must agree.
- Add the panel in the established shape: `role="tabpanel"`, `style:display`,
  and the lazy `{#if visitedTabs["testinfo"]}` guard.
- Render the component in full mode, with the description and the badges. Show
  a plain line when the map is empty.

The tab goes on the scylla-cluster-tests run page only. The Generic, Sirenada
and DriverMatrix run pages each hold a copy of the tab bar, and their jobs carry
no metadata today.

- [ ] Add the type entry, the two list entries and the panel.
- [ ] Run `yarn test` and `yarn build`.
- [ ] Load a run page, and check the tab, the deep link
      `/tests/<plugin>/<run>/testinfo`, and both themes.
- [ ] Commit.

## Verification

The sequence from the `Commands` section of `CLAUDE.md`, which needs Docker for
the backend suite:

```bash
uv run pre-commit run --all-files
uv run pytest
yarn test
yarn build
```

End to end, against the local database and a real Jenkins token:

1. `uv run python -m argus.backend.cli sync-models`, then confirm
   `test_metadata` on `argus_test_v2` in `cqlsh`.
2. `uv run python -m argus.backend.cli scan-jenkins`, then read the row of
   `scylla-master/longevity/longevity-10gb-3h-test`, and confirm that the map
   holds the four SCT keys and the prose.
3. Confirm in the log of the same run that no group was created a second time
   and that no `ArgusTestException` was logged. That is the name case, and the
   log is where it shows.
4. Mark a release dormant in the admin panel, scan again, and confirm that the
   log skips it and that it makes no request for it.
5. Scan twice with no change in Jenkins, and confirm that the second run writes
   nothing.
6. Read the test info endpoint, and confirm that the payload agrees with the
   Outputs block of the spec.
7. Start the application, then open the planner, search a test, add it to a
   plan, open the grid, and open the tab on the run page. Check both themes.

```bash
uv run uvicorn --factory argus_backend:create_app --port 5000 --reload
```

## Out of plan

The pull request states these. The spec defers the first four. The rest are
scope decisions of this plan.

- A lookup table for a search by label.
- The Go CLI output of `argus plan search`.
- A copy of the metadata on a run.
- The upstream findings for scylla-cluster-tests#14818.
- The Test Info tab on the Generic, Sirenada and DriverMatrix run pages.
- The prose description in the grid tile, which arrives on hover in its place.
- A `flock` in `scan_jobs.sh`. The cron starts every five minutes and takes no
  lock, so two scans can overlap. That is harmless for this column, and it
  exists today for the rest.
- An index of `_existing_groups` and `_existing_tests` by `build_system_id` in
  the constructor. Both take a linear scan per job today, which is quadratic,
  and which exists today.
