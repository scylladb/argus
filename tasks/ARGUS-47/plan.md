# ARGUS-47 — implementation plan

**Spec:** `tasks/ARGUS-47/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- The branch builds on `fix/nemesis-same-second-key` (ARGUS-150): the
  nemesis table is `sct_nemesis_v2`, keyed `(run_id, start_time, name)`.
  The pull request body states `Builds on #1133`.
- Standards: `docs/standards/backend/models.md`, `migrations.md`, `api.md`,
  `global/validation.md`, `error-handling.md`, `minimal-implementation.md`,
  `frontend/components.md`, `css.md`, `responsive.md`, `accessibility.md`,
  `testing/test-writing.md`.
- Every import at the top of its module. No rationale comments.
- Backend tests create and read rows through the API or `SCTService`,
  never `Model.save()` or `Model.find()` in the test body. Existing lines
  that do so stay as they are.
- Frontend: Svelte 5 runes, typed props, no `querySelector`, no fixed
  widths, Bootstrap utilities and the theme classes `bg-light-one/two/three`.
- Commits: `type(scope): subject`, scope at least 5 characters, body at
  least 30 characters, last line `Task: ARGUS-47`. Stage by explicit path.
- Verify sequence, from `CLAUDE.md`: `uv run pre-commit run --all-files`,
  `uv run pytest` (Docker), `yarn test`; for `frontend/` also `yarn build`;
  for `cli/` `make fmt && make lint && go test -race ./...`.

## Task 1 — Store the description by digest and attach it on read

**Files:**
- Modify: `argus/backend/plugins/sct/testrun.py:133-145` (new
  `SCTNemesisDescription` above `SCTNemesis`, the `description_digest`
  column, `with_descriptions`), `:485` (`get_run_response`)
- Modify: `argus/backend/plugins/sct/plugin.py:3,20-28` (`all_models`)
- Modify: `argus/backend/plugins/sct/service.py:1-33` (imports), `:432-433`
  (`get_nemesis`), `:449-477` (`submit_nemesis`, new
  `store_nemesis_description`)
- Test: `argus/backend/tests/sct_api/test_sct_api.py:384-500`
- Test: `argus/backend/tests/integration/test_sct_methods.py:91-111`

**Internals:**
- `SCTNemesisDescription(Document)`: `digest: Annotated[str, PrimaryKey(), Ascii()]`,
  `description: str`, `Settings.name = "sct_nemesis_description"`.
- `SCTNemesis.description_digest: Annotated[Optional[str], Ascii()] = None`.
- `SCTNemesis.with_descriptions(cls, nemeses) -> list[dict]`: the distinct
  digests, `asyncio.gather` of `SCTNemesisDescription.find(digest__in=batch).all()`
  per `chunk`, then `{**nem.model_dump(), "description": text}` per row.
- `get_run_response`: `response["nemesis_data"] = await SCTNemesis.with_descriptions(nemesis_data)`.
- `SCTService.store_nemesis_description(raw) -> str | None`: `None` for a
  falsy text or an empty `inspect.cleandoc`; else SHA-256 hex, save the
  row, return the digest. `import hashlib`, `import inspect`.
- `submit_nemesis`: inside the `try`, after `SCTTestRun.get` and before
  `nemesis_info.save()`, `nemesis_info.description_digest = await SCTService.store_nemesis_description(nem_req.description)`.
- `get_nemesis`: `await SCTNemesis.with_descriptions(await SCTNemesis.find(run_id=run_id).all())`.
- Tests: `_nemesis_submit_payload(name, start_time, description="parallel nemesis")`,
  a new `_run_nemeses(api_client, run_id)` on `GET /api/v1/run/scylla-cluster-tests/{id}`.

- [ ] Write the failing tests: `test_nemesis_submit_and_finalize` asserts
      `description == "Killing nodes randomly"` from `_nemeses_of` after
      submit and after finalize;
      `test_nemesis_submit_keeps_two_nemeses_with_one_start_time` asserts
      both entries carry `"parallel nemesis"`;
      `test_nemesis_description_is_dedented_and_stripped`;
      `test_nemeses_with_equal_descriptions_share_one_digest`;
      `test_nemesis_resubmit_keeps_the_first_description`;
      `test_nemesis_without_description_returns_null` parametrized over
      `{}`, `{"description": None}`, `{"description": "  \n  "}`;
      `test_nemesis_cycle` asserts `nem["description"]` twice.
- [ ] Run `uv run pytest argus/backend/tests/sct_api/test_sct_api.py argus/backend/tests/integration/test_sct_methods.py -k nemesis`
      and confirm the failure.
- [ ] Write the smallest change that passes it.
- [ ] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [ ] Commit, with the boxes of this task checked.

## Task 2 — `argus run nemeses --with-description`

**Files:**
- Modify: `cli/internal/models/runs.go:124-133` (`NemesisRunInfo`),
  `:839-896` (`NemesisResponse`, `NewNemesisResponse`, `Headers`, `Rows`)
- Modify: `cli/cmd/run_nemeses_events.go:346-466` (`runNemesesCmd`),
  `:476-480` (flags)
- Test: `cli/internal/models/runs_test.go`

**Internals:**
- `NemesisRunInfo.Description string \`json:"description"\``.
- `NemesisResponse.WithDescription bool`;
  `NewNemesisResponse(runID string, nemeses []NemesisRunInfo, withDescription bool)`.
- `Headers()` appends `"Description"` and `Rows()` appends `nem.Description`
  when `WithDescription`. `MarshalJSON` is unchanged.
- `runNemesesCmd`: `withDescription, _ := cmd.Flags().GetBool("with-description")`,
  passed to the six `NewNemesisResponse` calls; the flag registered in
  `init()`; one line in `Long`.

- [ ] Write the failing tests: `TestNemesisRunInfoDecodeDescription`,
      `TestNemesisResponseRowsWithoutDescriptionFlag`,
      `TestNemesisResponseRowsWithDescriptionFlag`,
      `TestNemesisResponseMarshalJSONCarriesDescription`.
- [ ] Run `cd cli && go test -race ./internal/models/` and confirm the failure.
- [ ] Write the smallest change that passes it, then `make fmt`.
- [ ] Run `cd cli && make lint && go test -race ./...`.
- [ ] Commit, with the boxes of this task checked.

## Task 3 — Move the nemesis types to their own module

**Files:**
- Create: `frontend/TestRun/Nemesis/types.ts`
- Modify: `frontend/TestRun/TestRun.svelte:35-48` (drop the interface, add
  the import)
- Modify: `frontend/TestRun/SCT/SctNemesis.svelte:3`,
  `frontend/TestRun/SCT/SctEvents.svelte:73` (the import)

**Internals:** `NemesisTargetNode { name; ip: string | null; shards: number | null }`,
`NemesisInfo` (the fields of the spec contract), `NemesisResource { name; state; instance_info: { private_ip: string } }`.

- [ ] Write the types and switch the three importers.
- [ ] Run `yarn build` and `yarn test`.
- [ ] Commit, with the boxes of this task checked.

## Task 4 — The sort, filter and label helpers

**Files:**
- Create: `frontend/TestRun/Nemesis/nemesisListing.ts`
- Modify: `frontend/Common/TestStatus.js:189-203` (`terminated` in
  `NemesisStatusBg` and `NemesisStatusFg`)
- Test: `frontend/TestRun/Nemesis/nemesisListing.test.ts`

**Internals:** `SortKey`, `SortDirection`, `SortState`, `DEFAULT_SORT`,
`nextSort`, `sortNemeses` (`toSorted`, `localeCompare` numeric, a running
nemesis as the latest end, tie-break on `start_time`), `nemesisMatches`
and `filterNemeses` (regex with a substring fallback), `nemesisKey`,
`statusLabel`, `statusClasses`, `formatNemesisTime`, `endTimeLabel`,
`descriptionSummary`, `reasonLabel`.

- [ ] Write the failing tests, one `describe` per helper.
- [ ] Run `yarn test frontend/TestRun/Nemesis` and confirm the failure.
- [ ] Write the helpers.
- [ ] Run `yarn test`.
- [ ] Commit, with the boxes of this task checked.

## Task 5 — The details panel

**Files:**
- Create: `frontend/TestRun/Nemesis/NemesisDetails.svelte`
- Test: `frontend/TestRun/Nemesis/NemesisDetails.test.ts`

**Internals:** `Props { nemesis: NemesisInfo; resource?: NemesisResource }`.
Two `col-12 col-lg-6` definition lists (nemesis facts, target node), the
description with `white-space: pre-line`, the reason `pre` with
`white-space: pre-wrap`, a copy button behind `{#if navigator.clipboard}`.

- [ ] Write the failing tests: facts and duration; no duration at zero;
      private IP and state from the resource; "not found" without one;
      description line breaks; no description block on null; reason label
      per status; copy calls `writeText`; no copy button without clipboard.
- [ ] Run `yarn test frontend/TestRun/Nemesis` and confirm the failure.
- [ ] Write the component.
- [ ] Run `yarn test`.
- [ ] Commit, with the boxes of this task checked.

## Task 6 — The list and the row, wired into the run page

**Files:**
- Create: `frontend/TestRun/Nemesis/NemesisRow.svelte`,
  `frontend/TestRun/Nemesis/NemesisList.svelte`
- Modify: `frontend/TestRun/TestRun.svelte:149,476`
- Delete: `frontend/TestRun/NemesisTable.svelte`,
  `frontend/TestRun/NemesisReason.svelte`, `frontend/TestRun/NemesisData.svelte`
- Modify: `frontend/Common/TestStatus.js:181-187` (drop `NemesisStatusBackgrounds`)
- Test: `frontend/TestRun/Nemesis/NemesisList.test.ts`

**Internals:**
- `NemesisList`: `Props { nemeses?: NemesisInfo[]; resources?: NemesisResource[] }`;
  `sort`, `filterText` in `$state`; `expanded = new SvelteSet<string>()`
  keyed by `nemesisKey`; `visible` and `resourcesByName` in `$derived`;
  `$props.id()` for the filter input; the toolbar, the `lg`-only header
  with `role="columnheader"` and `aria-sort`, the keyed `{#each}`, the two
  empty states; `:global(.status-col)` 7rem and `:global(.time-col)` 10.5rem
  at the `lg` breakpoint.
- `NemesisRow`: `Props { nemesis; resource?; open?; onToggle }`; the name
  button with `aria-expanded`, the description subline, the wrap break,
  the node chip, the status pill, the two times, `{#if open}` with
  `transition:slide` around `NemesisDetails`.
- `TestRun.svelte`: `import NemesisList from "./Nemesis/NemesisList.svelte"`,
  `<NemesisList nemeses={testRun.nemesis_data} resources={testRun.allocated_resources} />`.

- [ ] Write the failing tests: a row per nemesis; "In progress"; the
      description subline with the full text as `title`; no subline on
      null; default order; sort and reverse with `aria-sort`; no direction
      inheritance; regex, description and invalid-pattern filters; the
      match count; both empty states; expand shows the details; the
      details stay open across `rerender`; two nemeses with one start time
      expand independently; collapse; the labelled input.
- [ ] Run `yarn test frontend/TestRun/Nemesis` and confirm the failure.
- [ ] Write the two components, wire `TestRun.svelte`, delete the old files.
- [ ] Run `yarn test`, `yarn build`, `npx eslint frontend/TestRun/Nemesis`,
      `npx svelte-check`, and the verify sequence.
- [ ] Commit, with the boxes of this task checked.

## Task 7 — Live check

**Files:** none.

- [ ] `uv run python -m argus.backend.cli sync-models` on the dev cluster;
      `sct_nemesis_description` exists and `sct_nemesis_v2` has
      `description_digest`.
- [ ] Submit a run and a nemesis with the client and a real class
      docstring; the run page shows the description at a desktop and a
      narrow width, in both themes; `argus run nemeses --with-description`
      shows the column and `--output json` the field.
