---
status: draft
domain: client
created: 2026-06-01
last_updated: 2026-06-01
owner: null
---

# Release Planning Management in the Argus Go CLI

## 1. Problem Statement

Release plans (`ArgusReleasePlan`) can currently only be managed through the Svelte
web UI (`frontend/ReleasePlanner/`). Operators automating release workflows have no
scriptable way to create, edit, delete, or copy plans, forcing manual point-and-click
work for every release version. There are also no CLI primitives to discover the test
and group UUIDs a plan must reference — that discovery is locked inside the web
search box (`/api/v1/planning/search`).

Measurable pain points:
- **0** CLI commands exist for plan management today (`cli/cmd/` has `run`, `comment`,
  `ssh`, `config`, etc., but no `planner`).
- Creating a plan for N release versions requires N manual web sessions; there is no
  way to template/script plan creation or to copy a plan across releases from CI.
- Test/group UUIDs (required by the create/update payloads) are not retrievable from
  any existing CLI command, so even a hand-built API call is impractical.

## 2. Current State

### Backend API (verified)
All planner endpoints live in `argus/backend/controller/planner_api.py` (blueprint
`planning_api`, prefix `/planning`, mounted under `/api/v1`) and are backed by
`argus/backend/service/planner_service.py`:

| Operation | Route | Method | Payload / params |
| --- | --- | --- | --- |
| List plans for release | `/planning/release/<release_id>/all` | GET | — (`planner_api.py:98`) |
| Get one plan | `/planning/plan/<plan_id>/get` | GET | — (`planner_api.py:87`) |
| Create plan | `/planning/plan/create` | POST | `CreatePlanPayload` (`planner_service.py:25`) |
| Update plan | `/planning/plan/update` | POST | `TempPlanPayload` today; **`PlanDiffPayload` soon** (see below) |
| Delete plan | `/planning/plan/<plan_id>/delete?deleteView=0\|1` | DELETE | (`planner_api.py:146`) |
| Copy plan | `/planning/plan/copy` | POST | `CopyPlanPayload` (`planner_service.py:61`) |
| Copy eligibility check | `/planning/plan/<plan_id>/copy/check?releaseId=` | GET | (`planner_api.py:30`) |
| Search tests/groups | `/planning/search?query=&releaseId=` | GET | `TestLookup.test_lookup` (`test_lookup.py:99`) |
| Explode group → tests | `/planning/group/<group_id>/explode` | GET | (`planner_api.py:76`) |
| Resolve plan entities | `/planning/plan/<plan_id>/resolve_entities` | GET | (`planner_api.py:170`) |

The `ArgusReleasePlan` model (`argus/backend/models/plan.py:8`) has fields: `id`
(TimeUUID), `name`, `completed`, `description`, `owner` (UUID), `participants`
(list[UUID]), `target_version` (Ascii), `assignee_mapping` (map[UUID,UUID]),
`release_id` (UUID), `tests` (list[UUID]), `groups` (list[UUID]), `view_id`,
`created_from`, `creation_time`, `last_updated`, `ends_at`.

**Payload nuances to respect (verified in `planner_service.py`):**
- `create_plan` reads `assignments` (entity_id→user_id) and converts to
  `assignee_mapping` (`planner_service.py:119-153`). `view_id` optional → a view is
  auto-created when absent.
- Create/update/copy all enforce a uniqueness guard on `(name, target_version)` and
  raise `PlannerServiceException` on collision.
- `copy_plan` (`planner_service.py:296`) remaps tests/groups by `build_system_id`
  substring-replacing the source release name with the target release name; entities
  with no match are dropped unless present in `payload.replacements`.

#### Upcoming update mechanism — diff-based (ref `backend/release-planner-multi-edit-safety`)
The branch `backend/release-planner-multi-edit-safety` (commit
`fix(service/planner): Diff-based plan updates`) replaces the full-object
`TempPlanPayload` update with a **diff payload** for multi-editor safety
(last-edit-wins per field, remove-wins for list concurrency). The new
`PlanDiffPayload` shape is:

- `id` (required).
- Scalar fields, **only sent if changed**: `name`, `description`, `owner`,
  `target_version`, `completed`, `ends_at`, `view_id` (all `Optional`, `None` = no
  change).
- List diffs: `tests_add` / `tests_remove`, `groups_add` / `groups_remove`,
  `participants_add` / `participants_remove`.
- Map diff for assignees: `assignee_mapping_set` (dict) / `assignee_mapping_remove`
  (list of entity ids).

The server applies removes before adds, dedupes, and prunes `assignee_mapping`
entries whose entity is no longer in `tests`+`groups`. **This plan targets the
diff-based contract for `planner update` (Phase 5)** so the CLI lands aligned with the
new backend rather than the legacy full-object replacement.

### Name-resolution endpoints (verified)
- `GET /api/v1/releases` → enabled releases with `id`/`name` (`api.py:51`).
- `GET /api/v1/users` → users keyed by id with `username` (`api.py:477`).
- `GET /api/v1/release/<release_id>/versions` → distinct versions (`api.py:96`).

### Web frontend (reference for UX parity)
`frontend/ReleasePlanner/ReleasePlanner.svelte` (list + delete + copy dispatch),
`ReleasePlanCreator.svelte` (create/edit payload assembly, search, group explode),
`ReleasePlanCopyForm.svelte` (eligibility check + `EntityReplacer` mapping).

### Go CLI architecture (verified)
Module `github.com/scylladb/argus/cli`, Go 1.25.4. Layering:
**cmd (cobra) → services → api → models**, with `config`, `cache`, `output`,
`cmdctx`, `logging` cross-cutting in `internal/`.
- Routes are `fmt.Sprintf` constants in `cli/internal/api/routes.go`.
- HTTP via `api.Client.NewRequest(ctx, method, path, body)` + generic
  `api.DoJSON[T]` decoding the `models.APIResponse[T]` envelope
  (`internal/models/envelope.go`).
- Models are plain structs in `internal/models/` with `json:` tags; list payloads use
  `type XListResponse = []X` aliases. Output via `models.NewTabularSlice` /
  `models.NewKVTabular` (`internal/models/tabular.go`), rendered JSON (default) or
  text table (`--text`).
- The recommended template is the **sub-package pattern**: `cli/cmd/discussions/`
  with `Register(parent *cobra.Command)` (`cmd/discussions/root.go`) plus a
  `services.DiscussionService` (`internal/services/discussions.go`) that owns HTTP
  calls and cache invalidation. RunE preamble pulls `client`, `out`, `cache`, `log`
  from `cmdctx`. `ssh_admin.go` is the in-package CRUD+DELETE reference.
- Auth, config, output mode, and transparent re-auth are inherited from
  `rootCmd.PersistentPreRunE` automatically.

There is **no existing `planner`, `release`, or `view` command** — this is net-new.

## 3. Goals

1. Ship a new `argus planner` parent command exposing **six** operations: `list`,
   `get`, `create`, `update`, `delete`, `copy` — all functional against a live Argus
   backend.
2. Ship a `argus planner search` command that exposes `/planning/search`
   (`TestLookup.test_lookup`) so users can discover test/group UUIDs, with facet
   support (`type:`, `group:`, `release:`) matching backend behavior
   (`test_lookup.py:114`).
3. Accept **both** UUIDs and human names everywhere an entity is referenced
   (`--release`, `--owner`/`--participant`, tests/groups, assignees). Names resolve to
   UUIDs at plan-build time via `/api/v1/releases`, `/api/v1/users`, and the
   release-structure endpoint `/api/v1/planning/release/<id>/gridview`.
   **`build_system_id` is the canonical, recommended test reference** (globally unique,
   `web.py:216`). Group names are unique within a release (`web.py:175`); release/user
   names resolve by exact case-insensitive match. Ambiguous bare test names are
   **rejected with a candidate list**, never silently guessed.
4. `update` speaks the diff-based `PlanDiffPayload` contract from
   `backend/release-planner-multi-edit-safety`: it computes add/remove deltas for
   lists/maps and only sends changed scalar fields.
5. `copy` runs the eligibility check, prints dropped entities as a warning, drops them
   by default, and honors an optional `--replacements` JSON file.
6. Output respects the global `--text`/JSON modes and `--no-color`; every command
   returns a non-zero exit on API error with the backend message surfaced.
7. New code passes `go vet ./...`, `gofmt`, the repo linter, and unit tests; docs
   (`cli/README.md`, root `AGENTS.md` CLI section) describe the new commands.

> **Open / Needs Investigation:** the exact CLI ergonomics for specifying which tests
> and groups belong to a plan during `create`/`update` are intentionally left open in
> this plan. The proposals are captured in the Appendix and must be decided before
> Phase 4 begins. The plan provides `search`/`explode-group` discovery and a `--file`
> JSON path as a baseline regardless of the final flag design.

## 4. Implementation Phases

> Each phase is one PR (≤200 LOC of changed code) with separate commits for logically
> distinct changes. Order is dependency-driven: types → reads → discovery → writes.

### Phase 1 — Foundation: routes + models
**Importance: Critical**

- Add planner route constants to `cli/internal/api/routes.go` (the 10 endpoints in
  Current State plus `/api/v1/releases`, `/api/v1/users`, and the release-structure
  endpoint `Gridview = "/api/v1/planning/release/%s/gridview"` if not already present).
- Add `cli/internal/models/planner.go`:
  - `ReleasePlan` struct (fields mirror `ArgusReleasePlan`, `json:` tags in snake_case
    matching the API: `id`, `name`, `description`, `owner`, `participants`,
    `target_version`, `assignee_mapping`, `release_id`, `tests`, `groups`, `view_id`,
    `created_from`, `completed`, `creation_time`, `last_updated`, `ends_at`).
  - `type ReleasePlanList = []ReleasePlan`.
  - `CreatePlanRequest` (uses `assignments`, `created_from`, optional `view_id`).
  - `PlanDiffRequest` (diff-based update: `id`, optional scalars, `tests_add`,
    `tests_remove`, `groups_add`, `groups_remove`, `participants_add`,
    `participants_remove`, `assignee_mapping_set`, `assignee_mapping_remove`) —
    mirrors `PlanDiffPayload` from `backend/release-planner-multi-edit-safety`.
  - `CopyPlanRequest` (`plan`, `keepParticipants`, `replacements`, `targetReleaseId`,
    `targetReleaseName`) and `CopyCheckResponse` (`status`, `targetRelease`,
    `originalRelease`, `missing.tests`, `missing.groups`).
  - `GridView` response (`tests` map[id]GridEntity, `groups` map[id]GridEntity,
    `testByGroup`); `GridEntity` carries `id`, `name`, `pretty_name`,
    `build_system_id`, `group_id`, decorated `group`/`release` names — the source for
    name resolution (Phase 2).
  - `SearchHit` (`id`, `name`, `pretty_name`, `type`, `release`, `group`, `enabled`,
    `build_system_id`).
  - Hand-rolled `Headers()/Rows()` for `ReleasePlan` (list view: id, name, version,
    owner, #tests, #groups, completed) and `SearchHit`.
- **DoD:**
  - [ ] `go build ./...` passes.
  - [ ] `models.ReleasePlan` round-trips a sample API JSON response in a unit test.
  - [ ] List/empty slices serialize as `[]` not `null` (test asserts).
  - [ ] `PlanDiffRequest` omits unset optional scalars from JSON (`omitempty` /
        pointer fields) — unit test asserts an unchanged field is absent.
  - [ ] No command wiring yet (pure types/constants).

### Phase 2 — PlannerService + read commands (`list`, `get`) + name resolution
**Importance: Critical**

- Add `cli/internal/services/planner.go` with `PlannerService{client, cache}` and
  `NewPlannerService`. Methods: `GetPlansForRelease(ctx, releaseID)`,
  `GetPlan(ctx, planID)`.
- Add a release-resolution helper (service method `ResolveReleaseID(ctx, ref)`):
  if `ref` parses as UUID use it; else GET `/api/v1/releases`, match by `name`
  (exact, case-insensitive), error on 0/ambiguous. Cache the release list with a
  short TTL (add `TTLReleases` + `ReleasesKey()` to `internal/cache/keys.go`).

#### Entity name resolution (foundational; used by list/create/update/copy)

All name→UUID resolution happens client-side at plan-build time. Add to
`PlannerService`:

- `GetReleaseStructure(ctx, releaseID)` → GET `/planning/release/<id>/gridview`,
  returning the full enabled tests+groups set in **one** call. Cache client-side
  (`TTLGridview` + `GridviewKey(releaseID)` in `internal/cache/keys.go`).
- `ResolveUserID(ctx, ref)`: UUID passthrough, else `/api/v1/users` username match
  (exact, case-insensitive); 0/>1 → error listing candidates.
- `ResolveEntityID(ctx, ref, releaseID, kind)` for tests/groups, built from a single
  gridview fetch:
  - UUID → passthrough.
  - **Group:** match name within the release (unique per `web.py:175`) → single hit;
    0 → error.
  - **Test**, in priority order: (1) exact `build_system_id` (globally unique
    `web.py:216`, never ambiguous — the canonical reference); (2) group-qualified
    `group-name/test-name`, scoped to that group; (3) bare name → **1 hit resolves,
    >1 rejected** with each candidate's `build_system_id`, group, and UUID.
  - Errors are actionable, e.g.
    `ambiguous test 'longevity-100gb' (3 matches): use build_system_id or group/name`.

- Create `cli/cmd/planner/root.go` with `Register(parent *cobra.Command)`, plus
  `list.go` and `get.go`. Wire `plannerCmd` parent in a new `cli/cmd/planner.go`
  (`init()` → `planner.Register(plannerCmd)` → `rootCmd.AddCommand(plannerCmd)`),
  mirroring how `cmd/testrun.go` wires `discussions.Register`.
- `list --release <id|name>` → `NewTabularSlice`. `get --plan-id <id>` → `NewKVTabular`.
- **DoD:**
  - [ ] `argus planner list --release <name>` returns plans (manual against staging).
  - [ ] `argus planner get --plan-id <id>` shows a single plan.
  - [ ] Release/user name resolution unit-tested with an `httptest` server (UUID
        passthrough, name hit, ambiguous error, no-match error).
  - [ ] Test by `build_system_id` resolves to one UUID; group by name resolves within
        release (unit tests).
  - [ ] Ambiguous bare test name aborts with a candidate list incl.
        `build_system_id`+group+UUID; group-qualified `group/test` resolves an
        otherwise-ambiguous name (unit tests).
  - [ ] Resolution uses a single cached gridview fetch per release (unit test asserts
        one GET).
  - [ ] `--text` and JSON modes both render.

### Phase 3 — Discovery: `search` (+ `explode-group`)
**Importance: Critical** (create/update depend on discoverable IDs)

- `planner search`/`explode-group` are interactive **discovery** aids (printing
  `build_system_id`s users can copy as canonical references); they are **not** the
  resolution path — name resolution uses the gridview endpoint (Phase 2).
- `PlannerService.Search(ctx, query, releaseRef)` → GET `/planning/search`
  (resolve release ref first; releaseId optional). Returns `[]SearchHit`, filtering
  out the synthetic `Add all...` special row (id `db6f33b2-…`, `test_lookup.py:170`).
- `planner search --query "..." [--release <id|name>]` → table with columns
  type/name/id/group/release. Document facet syntax (`type:test`, `group:foo`,
  `release:2024.1`) in `--help`.
- `PlannerService.ExplodeGroup(ctx, groupID)` + `planner explode-group --group-id`
  → list member tests (helps expand a group into individual test UUIDs).
- **DoD:**
  - [ ] `argus planner search --query foo --release X` lists matching tests/groups
        with their UUIDs (manual).
  - [ ] Special `Add all...` row is excluded (unit test on the filter helper).
  - [ ] Facet query passed through verbatim (unit test asserts query-string build).

### Phase 4 — Write: `create` + `delete`
**Importance: Critical**

- **Decide the test/group input mechanism from the Appendix proposals and record the
  decision in this plan before coding.** Baseline that ships regardless: `--file/-f`
  JSON spec (and stdin) matching `CreatePlanRequest`.
- `PlannerService.CreatePlan(ctx, CreatePlanRequest)` → POST `/planning/plan/create`,
  invalidate the release's plan-list cache.
- `planner create` flags: `--release`, `--name`, `--description`, `--owner`,
  `--participant` (repeatable), `--target-version`, `--view-id`, plus
  tests/groups/assignments per the chosen mechanism, and `--file`. Owner/participant/
  assignee and test/group references accept names or UUIDs, resolved via the Phase 2
  helpers (`ResolveUserID`, `ResolveEntityID`). Merge precedence: flags override file
  fields.
- `PlannerService.DeletePlan(ctx, planID, deleteView)` → DELETE
  `/planning/plan/<id>/delete?deleteView=`. `planner delete --plan-id <id>
  [--delete-view] [--yes]` (confirmation prompt unless `--yes`, reading stdin like
  `discussions/root.go:readMessage`).
- **DoD:**
  - [ ] `argus planner create --file plan.json` creates a plan; `get` shows it.
  - [ ] Owner/participant names resolve to UUIDs (unit test).
  - [ ] Tests/groups given by name or `build_system_id` resolve to UUIDs; an ambiguous
        bare test name aborts create with a candidate list (unit tests).
  - [ ] `argus planner delete --plan-id <id> --yes` removes it; `--delete-view`
        toggles the query param (unit test asserts URL).
  - [ ] Uniqueness-collision API error is surfaced with the backend message.

### Phase 5 — Write: `update` (diff-based)
**Importance: Important**
**Depends on:** `backend/release-planner-multi-edit-safety` being merged (or the diff
contract being final). Until then, mark as `blocked` and gate on the backend PR.

- `PlannerService.UpdatePlan(ctx, PlanDiffRequest)` → POST `/planning/plan/update`
  with the diff payload; invalidate plan + plan-list caches.
- The CLI computes the diff: GET the current plan, compare against the user's
  requested state, and emit only `*_add`/`*_remove` deltas and changed scalars. For
  simple flag edits (e.g. `--name`) only the scalar is sent. For `--add-test` /
  `--remove-test` style flags (final shape per Phase 4 decision), populate the list
  diffs directly without a full re-send.
- Assignment edits map to `assignee_mapping_set` (entity→user) and
  `assignee_mapping_remove` (entity ids). **Both sides accept names or UUIDs:** the
  entity key resolves via `ResolveEntityID` (UUID / `build_system_id` / group-qualified
  / unique bare name) and the user value via `ResolveUserID` before the map is built.
- **DoD:**
  - [ ] `argus planner update --plan-id <id> --name "new"` sends only the `name`
        scalar (unit test asserts the request body has no list/map keys).
  - [ ] Adding/removing a test produces `tests_add`/`tests_remove` and leaves other
        fields untouched (manual: `get` before/after; unit test on diff builder).
  - [ ] Assignment set/remove maps to `assignee_mapping_set`/`assignee_mapping_remove`
        (unit test). Both the entity key (name/`build_system_id`/UUID) and user value
        (name/UUID) resolve to UUIDs before the map is sent (unit test).
  - [ ] `--add-test` given a name/`build_system_id` resolves to a UUID before building
        the diff; an ambiguous bare name aborts the update with a candidate list
        (unit test).

#### Example invocations (illustrative — final flag names confirmed in Phase 4)

Both styles below edit the same plan and produce the **same** diff payload on the
wire. Names (`--owner`, `--add-participant`, `--assign`) are resolved to UUIDs
client-side; raw UUIDs are also accepted.

**Flag-based (incremental edits):**

```bash
# Rename, retarget the version, add one test, drop a group, and (re)assign an entity.
argus planner update \
  --plan-id 7f3c1e90-... \
  --name "2024.2 Longevity" \
  --target-version 2024.2.1 \
  --add-test 2f9b...e1 \                          # raw UUID, passthrough
  --add-test sct-2024-2-longevity-100gb \         # build_system_id (canonical), unique
  --add-test "tier1/longevity-200gb" \            # group-qualified name → scoped lookup
  --remove-group 9a1c...44 \
  --add-participant alice \                        # plain username → resolved to UUID
  --remove-participant bob \
  --assign sct-2024-2-longevity-100gb=alice \      # build_system_id=username → assignee_mapping_set
  --unassign "tier1/longevity-200gb"               # group-qualified name → assignee_mapping_remove
```

The three `--add-test` forms show the supported reference styles: a raw UUID (passed
through), a **canonical `build_system_id`** (globally unique — the recommended way to
name a test unambiguously), and a **group-qualified name** that disambiguates a test
whose bare name repeats across groups. A bare `--add-test longevity-100gb` is accepted
only when it resolves to exactly one test; otherwise the CLI aborts with a candidate
list. All forms resolve to the same UUID before the diff is built.

The CLI GETs the current plan, resolves every name/`build_system_id` to a UUID,
computes deltas, and POSTs only what changed:

```json
{
  "id": "7f3c1e90-...",
  "name": "2024.2 Longevity",
  "target_version": "2024.2.1",
  "tests_add": ["2f9b...e1", "c4d0...7a", "b7e2...09"],
  "groups_remove": ["9a1c...44"],
  "participants_add": ["<alice-uuid>"],
  "participants_remove": ["<bob-uuid>"],
  "assignee_mapping_set": {"c4d0...7a": "<alice-uuid>"},
  "assignee_mapping_remove": ["b7e2...09"]
}
```

Note how `sct-2024-2-longevity-100gb` (→ `c4d0...7a`), `tier1/longevity-200gb`
(→ `b7e2...09`), and `alice` (→ `<alice-uuid>`) are all resolved to UUIDs in the map
keys and values. Fields like `description`, `owner`, `completed`, `view_id`, and
untouched list members are absent — last-edit-wins per field, and unchanged scalars
are never sent.

**JSON file (`--file` / stdin):** the file describes a diff directly (same schema as
the payload above), so it is explicit about intent and ideal for CI:

```bash
argus planner update --plan-id 7f3c1e90-... --file edit.json
# or
cat edit.json | argus planner update --plan-id 7f3c1e90-... --file -
```

```json
// edit.json
{
  "name": "2024.2 Longevity",
  "target_version": "2024.2.1",
  "tests_add": ["2f9b...e1", "c4d0...7a"],
  "groups_remove": ["9a1c...44"],
  "participants_add": ["alice"],
  "participants_remove": ["bob"],
  "assignee_mapping_set": {"2f9b...e1": "alice"},
  "assignee_mapping_remove": ["9a1c...44"]
}
```

`--plan-id` on the command line takes precedence over an `id` in the file. When both a
`--file` and overlapping flags are given, flags override the corresponding file keys
(same precedence rule as `create`). Name references inside the file (`alice`, `bob`)
are resolved the same way as flag values.

### Phase 6 — Write: `copy` (with eligibility check)
**Importance: Important**

- `PlannerService.CheckCopyEligibility(ctx, planID, targetReleaseRef)` → GET
  `/planning/plan/<id>/copy/check`. `PlannerService.CopyPlan(ctx, CopyPlanRequest)`
  → POST `/planning/plan/copy`.
- `planner copy --plan-id <id> --target-release <id|name> [--name] [--target-version]
  [--keep-participants] [--owner] [--replacements <file>] [--force]`:
  1. Resolve target release.
  2. Run eligibility check; if missing entities and no/partial `--replacements`,
     print a warning listing dropped entities; abort unless `--force`.
  3. Build `CopyPlanRequest` (the `plan` sub-object carries name/version/description/
     owner overrides) and POST.
  4. Print a note when target release differs from source (parity with
     `ReleasePlanner.svelte:89` redirect message).
- **DoD:**
  - [ ] `argus planner copy --plan-id <id> --target-release <name>` copies within the
        same release (manual).
  - [ ] Missing-entity warning lists dropped tests/groups; `--force` proceeds.
  - [ ] `--replacements` file maps a missing entity (unit test on request assembly).

### Phase 7 — Documentation + hardening
**Importance: Important**

- Update `cli/README.md` with a `planner` section (all commands + examples, the
  `--file` JSON schema, facet search syntax, diff-update behavior).
- Update the root `AGENTS.md` "Argus CLI (Go)" section to mention planner operations.
- Add any missing `_test.go` coverage; run full lint/test/build.
- **DoD:**
  - [ ] `cli/README.md` documents all 7 commands with copy-pasteable examples.
  - [ ] `AGENTS.md` references planner management.
  - [ ] `go vet ./...`, `gofmt -l` (clean), repo linter, and `go test ./...` all pass.

## 5. Testing Requirements

### Unit tests (Go, `cli/...`)
- **Models** (`internal/models/planner_test.go`): JSON round-trip of `ReleasePlan`,
  `CopyCheckResponse`, `SearchHit`; empty-slice→`[]`; `PlanDiffRequest` omits unset
  optional scalars; `Headers()/Rows()` shape.
- **Service** (`internal/services/planner_test.go`): `httptest.NewServer` emitting the
  standard envelope (pattern from `internal/api/api_test.go`), injected via
  `api.WithHTTPClient`. Cover: list, get, create, update-diff builder
  (scalar-only, list add/remove, assignee set/remove), delete (query-param URL),
  copy, eligibility check, search (special-row filtering, facet query passthrough),
  release/user name resolution (UUID passthrough, exact match, ambiguous error,
  no-match error), test/group resolution from a single gridview fetch
  (`build_system_id` hit, group-name hit, group-qualified `group/test` hit, bare-name
  unique hit, bare-name ambiguous rejection, one-GET caching), and backend-error
  surfacing (`ErrorAs *api.APIError`).
- **Command** (`cmd/planner/planner_test.go`): flag parsing/required-flag enforcement,
  confirmation-prompt bypass with `--yes`, `--file`/stdin parsing, flag-over-file
  precedence (pattern from `cmd/discussions/discussions_test.go`).

### Integration tests
- No new ScyllaDB-backed pytest suite required (CLI talks HTTP). If desired, a
  `@pytest.mark.docker_required` smoke could exercise `planner_api.py` end-to-end, but
  it is out of scope for this plan.

### Manual testing (against staging)
- For each command: run happy path + one error path (bad UUID, name collision,
  missing release). Verify `--text` vs JSON output and non-zero exit codes on failure.
- Copy across two releases and confirm the dropped-entity warning and target-release
  note appear.
- Update: confirm a single-field edit does not disturb tests/groups/assignees.

## 6. Success Criteria

The plan is complete when all phase DoD items are satisfied, plus:
- All six management commands + `search` + `explode-group` are reachable under
  `argus planner` and documented (Goals 1–2, Phase 7 DoD).
- Name/UUID dual-input works for releases and users across create/update/copy/list
  (Goal 3; Phase 2 & 4 DoD).
- `update` emits a correct `PlanDiffPayload` and never clobbers untouched fields
  (Goal 4; Phase 5 DoD).
- `copy` eligibility/replacements behavior matches Goal 5 (Phase 6 DoD).
- `go vet`, gofmt, linter, and `go test ./...` pass (Goal 7; Phase 7 DoD).

## 7. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Diff-update backend (`backend/release-planner-multi-edit-safety`) not yet merged when Phase 5 starts | High | Medium | Gate Phase 5 on the backend PR; keep Phases 1–4 & 6 independent of it. Model `PlanDiffRequest` from the branch now so types are ready. |
| CLI diff builder miscomputes deltas and silently drops tests/groups | Medium | High | Build the diff from an authoritative GET of the current plan; unit-test scalar-only, add, remove, and assignee cases. Never send full list replacements. |
| Name resolution ambiguity (duplicate release/user names) selects the wrong entity | Medium | High | Require exact case-insensitive match; on >1 match, error and list candidate UUIDs instead of guessing. Always allow raw UUID to bypass. |
| Ambiguous bare test names resolve to the wrong test (names unique only per group, `web.py:212`) | Medium | High | Reject on >1 match with a candidate list (`build_system_id`+group+UUID); document `build_system_id` as canonical; accept UUID and `group/test` qualified form. |
| Test/group flag ergonomics (open decision) prove awkward | Medium | Medium | Ship `--file` JSON as the always-available robust path first; treat flag conveniences as additive. Record the decision before Phase 4 coding. |
| `copy` build_system_id remap semantics differ from user expectation (silent drops) | Medium | Medium | Surface the eligibility check output prominently and require `--force` to drop; support `--replacements`. |
| Large `/api/v1/users` or `/api/v1/releases` payloads slow every resolving command | Low | Low | Cache both lists with a short TTL (`internal/cache`); resolve locally. |

## Appendix — Test/Group Input Proposals (decide before Phase 4)

The web UI adds tests/groups via interactive search; the CLI needs a non-interactive
equivalent. The input ergonomics are **left open** per stakeholder request. Proposals
(not mutually exclusive):

- **A. `--file/-f` JSON spec (baseline, always supported).** A single JSON object
  matching `CreatePlanRequest`/diff fields (tests/groups as UUID arrays, `assignments`
  as an entity→user map). Also readable from stdin. Robust for nested data and
  CI-generated specs.
- **B. Repeatable `--test` / `--group` flags (create) and
  `--add-test`/`--remove-test`/`--add-group`/`--remove-group` (update).** Accept
  UUIDs directly, or `build_system_id`/name resolved at plan-build time from the
  release gridview (Phase 2). Bare test names are rejected when ambiguous; use
  `build_system_id` or `group/test` to disambiguate. Assignments via repeatable
  `--assign <entity>=<user>`, where both `<entity>` (UUID/`build_system_id`/`group/test`)
  and `<user>` (UUID/username) accept names. Maps cleanly onto the diff payload.
- **C. Two-step `search`→`create`.** Users run `planner search` (Phase 3) to discover
  `build_system_id`s/UUIDs, then pass them via A or B. No extra implementation beyond
  A/B.

When the decision is made, update Phase 4/5 flag specs and this appendix accordingly.

## Tracking
- Registered under **Client** in `docs/plans/MASTER.md`.
- `progress.json` entry: id `cli-planner-command`, domain `client`, status `draft`,
  `phases_total: 7`, `phases_done: 0`.
</content>
</invoke>
