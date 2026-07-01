---
status: in_progress
domain: client
created: 2026-06-01
last_updated: 2026-06-26
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
`created_from`, `creation_time`, `last_updated`, `ends_at`. **Phase 0 adds a `key`
(Text) field — a human-friendly `releaseName#planNumber` handle (e.g. `scylla-2026.2#3`)
that plan operations accept in place of a UUID.**

**Payload nuances to respect (verified in `planner_service.py`):**
- `create_plan` reads `assignments` (entity_id→user_id) and converts to
  `assignee_mapping` (`planner_service.py:119-153`). `view_id` optional → a view is
  auto-created when absent.
- Create/update/copy all enforce a uniqueness guard on `(name, target_version)` and
  raise `PlannerServiceException` on collision.
- `copy_plan` (`planner_service.py:296`) remaps tests/groups by `build_system_id`
  substring-replacing the source release name with the target release name; entities
  with no match are dropped unless present in `payload.replacements`.

#### Update mechanism — diff-based (merged to master, `planner_service.py:62`)
The diff-based plan update (commit `e1fa19db`, `fix(service/planner): Diff-based plan
updates`) is **merged to master and present on this branch**. It replaces the full-object
`TempPlanPayload` update with a **diff payload** for multi-editor safety
(last-edit-wins per field, remove-wins for list concurrency). The `PlanDiffPayload`
shape (`planner_service.py:62`, consumed by `update_plan` at `planner_service.py:178`)
is:

- `id` (required).
- Scalar fields, **only sent if changed**: `name`, `description`, `owner`,
  `target_version`, `completed`, `ends_at`, `view_id` (all `Optional`, `None` = no
  change).
- List diffs: `tests_add` / `tests_remove`, `groups_add` / `groups_remove`,
  `participants_add` / `participants_remove`.
- Map diff for assignees: `assignee_mapping_set` (dict) / `assignee_mapping_remove`
  (list of entity ids).

The server applies removes before adds, dedupes, and prunes `assignee_mapping`
entries whose entity is no longer in `tests`+`groups`. **`planner update` (Phase 5)
targets this diff-based contract** so the CLI lands aligned with the backend rather than
the legacy full-object replacement.

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

1. Ship a new `argus planner` parent command exposing **five** operations: `list`,
   `get`, `create`, `update`, `delete` — all functional against a live Argus
   backend.
2. Ship a **top-level** `argus search` command that exposes `/planning/search`
   (`TestLookup.test_lookup`) so users can discover test/group `build_system_id`s. It
   supports the backend query language — free-text substring plus `type:`, `group:`,
   `release:` facets — matching backend behavior (`test_lookup.py:114`).
3. Reference every entity by **human name or `build_system_id` only — never a raw
   UUID**. Release, `--owner`/`--participant`, test, group, and assignee references are
   resolved to UUIDs client-side at plan-build time via `/api/v1/releases`,
   `/api/v1/users`, and the release-structure endpoint
   `/api/v1/planning/release/<id>/gridview`, and only UUIDs are ever sent to the
   backend. **`build_system_id` is the canonical, recommended test reference** (globally
   unique, `web.py:216`); group-qualified `group/test` is the portable alternative.
   Group names are unique within a release (`web.py:175`); release/user names resolve by
   exact case-insensitive match. Ambiguous bare test names are **rejected with a
   candidate list**, never silently guessed. The only raw UUIDs accepted from the user
   are `--plan-id` and `--view-id` (a view has no clean unique name). A plan may instead
   be addressed by its human-friendly `releaseName#planNumber` key (Phase 0); when both a
   key and `--plan-id` are given, `--plan-id` wins.
4. **Groups are always expanded client-side to their enabled tests.** On `create` and
   on `update --add-group`, every group reference is exploded (via the gridview's
   enabled `tests` map — *not* `explode_group`/`testByGroup`, which include disabled
   tests) into individual test UUIDs; the plan's `groups` list is sent **empty**, and
   any assignment placed on a group **fans out** to each of its expanded tests.
5. Provide a **create-from-JSON round-trip**: `get --template` emits an editable plan
   spec (group-qualified `group/test` names + `release`/`target_version`), and
   `create --file` resolves it against the **target release's gridview**, warning about
   (and omitting) tests not present in the new release while still creating the plan.
   This is entirely client-side — no new backend endpoint.
6. `update` speaks the diff-based `PlanDiffPayload` contract (merged to master,
   `planner_service.py:62`): it computes add/remove deltas for lists/maps and only
   sends changed scalar fields.
7. Output respects the global `--text`/JSON modes and `--no-color`; every command
   returns a non-zero exit on API error with the backend message surfaced.
8. New code passes `go vet ./...`, `gofmt`, the repo linter, and unit tests; docs
   (`cli/README.md`, root `AGENTS.md` CLI section) describe the new commands.

> **Open / Needs Investigation:** the exact CLI ergonomics for specifying which tests
> and groups belong to a plan during `create`/`update` are intentionally left open in
> this plan. The proposals are captured in the Appendix and must be decided before
> Phase 4 begins. The plan provides `search` discovery and a `--file`
> JSON path as a baseline regardless of the final flag design.

## Command Reference (final design)

> Showcases the intended end-state CLI surface. Entity references are **names or
> `build_system_id` only** (no raw UUIDs); a plan is addressed by `--plan-id` (UUID) or
> its `releaseName#planNumber` key. `--plan-id` wins if both are given. All commands honor
> the global `--text` (table) / JSON-default output and `--no-color`.

### `argus planner list`
```text
List release plans for a release.

Usage:
  argus planner list --release <name> [flags]

Flags:
  -r, --release string   Release name (required)
  -h, --help             help for list

Examples:
  argus planner list --release scylla-2026.2
  argus planner list --release scylla-2026.2 --text
```

### `argus planner get`
```text
Show a single plan, or emit an editable create-spec template.

Usage:
  argus planner get (--plan-id <id|key>) [--template] [flags]

Flags:
  -p, --plan-id string   Plan UUID or key (e.g. "scylla-2026.2#3")
      --template         Emit an editable create spec (group/test names + usernames)
                         instead of the raw plan
  -h, --help             help for get

Examples:
  argus planner get --plan-id scylla-2026.2#3
  argus planner get --plan-id 7f3c1e90-... --template > plan.json
```

### `argus planner create`
```text
Create a new release plan. Groups are always expanded to their enabled tests.

Usage:
  argus planner create --release <name> --name <title> [flags]

Flags:
  -r, --release string          Release name (required)
  -n, --name string             Plan name (required)
      --description string      Plan description
      --owner string            Owner username (defaults to the calling user)
      --participant strings     Participant username (repeatable)
      --target-version string   Target version (e.g. 2026.2.0~rc3)
      --test strings            Test by build_system_id or group/test (repeatable)
      --group strings           Group by name; expanded to enabled tests (repeatable)
      --assign strings          <entity>=<username> assignment (repeatable)
      --view-id string          Existing view UUID (a view is auto-created if omitted)
  -f, --file string             JSON plan spec (get --template schema); '-' for stdin
  -h, --help                    help for create

Examples:
  argus planner create --release scylla-2026.2 --name "2026.2 Longevity" \
    --target-version 2026.2.0~rc3 \
    --test scylla-2026.2/longevity/longevity-100gb \
    --group tier1 \
    --owner alice --participant bob \
    --assign scylla-2026.2/longevity/longevity-100gb=alice

  argus planner create --release scylla-2026.2 --file plan.json
  cat plan.json | argus planner create --release scylla-2026.2 --file -
```

### `argus planner update`
```text
Update a plan via a computed diff (only changed fields are sent). --add-group
expands to the group's enabled tests; group assignments fan out to each test.

Usage:
  argus planner update (--plan-id <id|key>) [flags]

Flags:
  -p, --plan-id string             Plan UUID or key (required)
  -n, --name string                New plan name
      --description string         New description
      --owner string               New owner username
      --target-version string      New target version
      --completed                  Mark the plan completed
      --add-test strings           Add test by build_system_id or group/test (repeatable)
      --remove-test strings        Remove test by build_system_id or group/test (repeatable)
      --add-group strings          Add group (expanded to enabled tests) (repeatable)
      --remove-group strings       Remove a pre-existing group (repeatable)
      --add-participant strings    Add participant username (repeatable)
      --remove-participant strings Remove participant username (repeatable)
      --assign strings             <entity>=<username> assignment (repeatable)
      --unassign strings           Remove assignment for <entity> (repeatable)
  -f, --file string                JSON diff spec; '-' for stdin
  -h, --help                       help for update

Examples:
  argus planner update --plan-id scylla-2026.2#3 --name "2026.2 Longevity (GA)"
  argus planner update --plan-id scylla-2026.2#3 \
    --add-test scylla-2026.2/longevity/longevity-200gb \
    --remove-group tier2 \
    --assign scylla-2026.2/longevity/longevity-200gb=bob
  argus planner update --plan-id scylla-2026.2#3 --file edit.json
```

### `argus planner delete`
```text
Delete a plan (and optionally its view).

Usage:
  argus planner delete (--plan-id <id|key>) [flags]

Flags:
  -p, --plan-id string   Plan UUID or key (required)
      --delete-view      Also delete the plan's associated view
  -y, --yes              Skip the confirmation prompt
  -h, --help             help for delete

Examples:
  argus planner delete --plan-id scylla-2026.2#3 --yes
  argus planner delete --plan-id 7f3c1e90-... --delete-view --yes
```

### `argus search`
```text
Search tests, groups, and releases to discover their build_system_ids. Top-level
command (not under `planner`).

Usage:
  argus search <query> [--release <name>] [flags]

Flags:
  -r, --release string   Restrict results to a release by name
  -h, --help             help for search

Query language:
  A query is free text plus optional facets, combined with AND. The free text is
  matched as a case-insensitive substring against an entity's own name. Facets
  (anywhere in the query) further constrain results:
    release:<substr>   entity's release name contains <substr> (case-insensitive)
    group:<substr>     entity's group name contains <substr> (case-insensitive)
    type:<test|group|release>   exact entity type
  Facet values may be quoted to include spaces (e.g. group:"long running"). A query
  that is a bare UUID instead looks up that single run/entity directly.

Examples:
  # Tests whose name contains "longevity" in the 2026.2 release
  argus search "release:2026.2 longevity"

  # All tests in the "longevity" group (type-constrained, group substring)
  argus search "type:test group:longevity"

  # Just the groups of a release (handy to discover group names)
  argus search "type:group release:2026.2"

  # Free-text only, scoped via the flag instead of a release: facet
  argus search "100gb" --release scylla-2026.2

  # Quoted facet value with a space
  argus search 'group:"long running" upgrade'
```

## 4. Implementation Phases

> Each phase is one PR (≤200 LOC of changed code) with separate commits for logically
> distinct changes. Order is dependency-driven: types → reads → discovery → writes.

### Phase 0 — Backend prerequisite: human-friendly plan key
**Importance: Critical** (CLI commands reference plans by this key)

Adds a stable, human-friendly key to `ArgusReleasePlan` so plan operations can be
addressed without bulky UUIDs. The key is a Text column of the form
`releaseName#planNumber` (e.g. `scylla-2026.2#3`), where `releaseName` is resolved from the
plan's `release_id` → `ArgusRelease.name` and `planNumber` starts at 1 per release. The
number simply increments until the key is unique; reuse and gaps are not tracked.

- **Model** (`argus/backend/models/plan.py`): add `key = columns.Text()` to
  `ArgusReleasePlan`. Not indexed — there are few enough plans that a linear
  `filter(key=...).allow_filtering()` lookup is fine. Auto-synced via `USED_MODELS`
  (`web.py:400`) and auto-serialized into plan JSON by `ArgusJSONEncoder`
  (`encoders.py:22`), so it surfaces in `get_plan`/`get_plans_for_release` responses with
  no serializer change.
- **Key generation** (`planner_service.py`): a `_generate_plan_key(release_id)` helper
  resolves the release name, then loops `number = 1, 2, 3, …`, building
  `f"{release_name}#{number}"` and checking
  `ArgusReleasePlan.filter(key=candidate).allow_filtering().get()` in a
  `try/except ArgusReleasePlan.DoesNotExist` (mirrors the existing
  `(name, target_version)` uniqueness guard at `planner_service.py:145-152`). The first
  candidate with no existing match wins.
- **Set at both creation sites**: assign `plan.key` just before `plan.save()` in
  `create_plan` (`planner_service.py:174`) and before `new_plan.save()` in `copy_plan`
  (`planner_service.py:455`, using `target_release.id`).
- **Key-accepting operations** (resolution model): a `_resolve_plan(ref)` helper returns
  the plan by UUID id, falling back to `filter(key=ref).allow_filtering().get()` when the
  ref is not a UUID (or no plan has that id). It replaces the bare
  `ArgusReleasePlan.get(id=plan_id)` calls in `get_plan`, `delete_plan`, `resolve_plan`,
  `change_plan_owner`, `check_plan_copy_eligibility`, and `update_plan` (which resolves
  via the payload `id` and uses the resolved `plan.id` for its self-collision check). No
  new resolver endpoint is added; **`plan_id` takes precedence over the key when both are
  supplied** — the CLI decides which single ref to send.
- **Backfill migration** (`scripts/migration/`): a new dated script iterates existing
  plans grouped by `release_id`, ordered by `id` (TimeUUID ≈ creation order), and assigns
  `releaseName#1, #2, …`. Follows the `ScyllaCluster.get()` + `migrate()` pattern of
  `scripts/migration/migration_2026-05-08.py`.
- **DoD:**
  - [ ] `ArgusReleasePlan.key` column added and synced.
  - [ ] `create_plan` and `copy_plan` assign a unique `releaseName#planNumber` key
        (unit test: collision increments the number).
  - [ ] `_resolve_plan` resolves both a UUID id and a key, with id taking precedence
        (unit test).
  - [ ] Plan JSON responses include `key` (no serializer change needed).
  - [ ] Backfill migration assigns keys to all existing plans, per-release numbering
        ordered by creation time.

### Phase 1 — Foundation: routes + models
**Importance: Critical**

- Add planner route constants to `cli/internal/api/routes.go` (the 10 endpoints in
  Current State plus `/api/v1/releases`, `/api/v1/users`, and the release-structure
  endpoint `Gridview = "/api/v1/planning/release/%s/gridview"` if not already present).
- Add `cli/internal/models/planner.go`:
  - `ReleasePlan` struct (fields mirror `ArgusReleasePlan`, `json:` tags in snake_case
    matching the API: `id`, `key`, `name`, `description`, `owner`, `participants`,
    `target_version`, `assignee_mapping`, `release_id`, `tests`, `groups`, `view_id`,
    `created_from`, `completed`, `creation_time`, `last_updated`, `ends_at`).
  - `type ReleasePlanList = []ReleasePlan`.
  - `CreatePlanRequest` (uses `assignments`, `created_from`, optional `view_id`).
  - `PlanDiffRequest` (diff-based update: `id`, optional scalars, `tests_add`,
    `tests_remove`, `groups_add`, `groups_remove`, `participants_add`,
    `participants_remove`, `assignee_mapping_set`, `assignee_mapping_remove`) —
    mirrors `PlanDiffPayload` (`planner_service.py:62`, on master).
  - `GridView` response (`tests` map[id]GridEntity, `groups` map[id]GridEntity,
    `testByGroup`); `GridEntity` carries `id`, `name`, `pretty_name`,
    `build_system_id`, `group_id`, `enabled`, and decorated `group`/`release` names —
    the source for name resolution and enabled-only group expansion (Phase 2).
  - `PlanTemplate` (emitted by `get --template`): scalars + `release` name,
    `owner`/`participants` usernames, `tests` as `group/test` strings, `assignments`
    keyed by `group/test`. Reused as the `create --file` input schema.
  - `SearchHit` (`id`, `name`, `pretty_name`, `type`, `release`, `group`, `enabled`,
    `build_system_id`).
  - Hand-rolled `Headers()/Rows()` for `ReleasePlan` (list view: key, name, version,
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
  GET `/api/v1/releases`, match by `name` (exact, case-insensitive), error on
  0/ambiguous. **No raw-UUID input is accepted** — references are always names. Cache
  the release list with a short TTL (add `TTLReleases` + `ReleasesKey()` to
  `internal/cache/keys.go`).

#### Entity name resolution (foundational; used by list/create/update)

All name→UUID resolution happens client-side at plan-build time, and **only UUIDs are
sent to the backend**. Raw UUIDs are never accepted as entity input (the only
exceptions are `--plan-id` and `--view-id`). Add to `PlannerService`:

- `GetReleaseStructure(ctx, releaseID)` → GET `/planning/release/<id>/gridview`,
  returning the full enabled tests+groups set in **one** call. Cache client-side
  (`TTLGridview` + `GridviewKey(releaseID)` in `internal/cache/keys.go`).
- `ResolveUserID(ctx, ref)`: `/api/v1/users` username match (exact, case-insensitive);
  0/>1 → error listing candidates.
- `ResolveEntityID(ctx, ref, releaseID, kind)` for tests/groups, built from a single
  gridview fetch:
  - **Group:** match name within the release (unique per `web.py:175`) → single hit;
    0 → error.
  - **Test**, in priority order: (1) exact `build_system_id` (globally unique
    `web.py:216`, never ambiguous — the canonical reference); (2) group-qualified
    `group-name/test-name`, scoped to that group; (3) bare name → **1 hit resolves,
    >1 rejected** with each candidate's `build_system_id`, group, and UUID.
  - Errors are actionable, e.g.
    `ambiguous test 'longevity-100gb' (3 matches): use build_system_id or group/name`.
- `ExpandGroup(ctx, releaseID, groupRef)`: resolve the group, then return its
  **enabled** member test UUIDs by filtering the gridview's `tests` map on `group_id`.
  Deliberately **does not** use `/group/<id>/explode` or `gridview.testByGroup`, which
  include disabled tests (`test_lookup.py:28`, `planner_service.py:278`). Used by
  `create`/`update` to always expand groups into individual tests.

- Create `cli/cmd/planner/root.go` with `Register(parent *cobra.Command)`, plus
  `list.go` and `get.go`. Wire `plannerCmd` parent in a new `cli/cmd/planner.go`
  (`init()` → `planner.Register(plannerCmd)` → `rootCmd.AddCommand(plannerCmd)`),
  mirroring how `cmd/testrun.go` wires `discussions.Register`.
- `list --release <name>` → `NewTabularSlice`. `get --plan-id <id>` → `NewKVTabular`.
  `--plan-id` also accepts a plan key (`releaseName#planNumber`); it is passed through
  verbatim and the backend resolves it (Phase 0). The same applies to `--plan-id` on
  `update`/`delete`.
- **DoD:**
  - [ ] `argus planner list --release <name>` returns plans (manual against staging).
  - [ ] `argus planner get --plan-id <id>` shows a single plan.
  - [x] Release/user name resolution unit-tested with an `httptest` server (name hit,
        ambiguous error, no-match error); a raw UUID passed as a name errors (not
        silently accepted).
  - [x] Test by `build_system_id` resolves to one UUID; group by name resolves within
        release (unit tests).
  - [x] Ambiguous bare test name aborts with a candidate list incl.
        `build_system_id`+group+UUID; group-qualified `group/test` resolves an
        otherwise-ambiguous name (unit tests).
  - [x] `ExpandGroup` returns only the group's **enabled** test UUIDs (a disabled
        member is excluded), using the single cached gridview fetch (unit test).
  - [x] Resolution uses a single cached gridview fetch per release (unit test asserts
        one GET).
  - [x] `--text` and JSON modes both render (covered by `TestReleasePlan_TabularShape`
        + `TestReleasePlan_JSONRoundTrip` and the tested output package).

### Phase 3 — Discovery: top-level `argus search`
**Importance: Critical** (create/update depend on discoverable IDs)

- `argus search` is a **top-level** command (registered on `rootCmd`, not under
  `planner`) — an interactive **discovery** aid (printing `build_system_id`s users can
  copy as canonical references); it is **not** the resolution path — name resolution
  uses the gridview endpoint (Phase 2).
- Add `cli/cmd/search/` with `Register(parent *cobra.Command)` wired from a new
  `cli/cmd/search.go` (`init()` → `search.Register(rootCmd)`), mirroring how other
  top-level commands are registered. It reuses `PlannerService.Search` (or a small
  dedicated `SearchService`) for the HTTP call.
- `Search(ctx, query, releaseRef)` → GET `/planning/search` (resolve release ref
  first; releaseId optional). Returns `[]SearchHit`, filtering out the synthetic
  `Add all...` special row (id `db6f33b2-…`, `test_lookup.py:170`).
- `argus search <query> [--release <name>]` → table with columns
  type/name/build_system_id/group/release (no UUIDs surfaced as the suggested
  reference). The `query` is a positional argument passed verbatim to the backend.
- **Query language** (mirrors `TestLookup.test_lookup`, `test_lookup.py:114-149`):
  free text is a case-insensitive substring match on the entity's own name; optional
  facets `release:<substr>`, `group:<substr>` (substring match on the related entity's
  name) and `type:<test|group|release>` (exact type) combine with AND. **Facet values
  must NOT be quoted and cannot contain spaces** — the backend facet regex
  (`test_lookup.py:115`, char class `[\w\d\.\-]*`) captures quote characters into the
  value and excludes spaces, so quoting/spaces break the match. A bare-UUID query
  short-circuits to a single run/entity lookup. Document this in `--help` with examples
  (incl. `argus search "release:2026.2 longevity"`).
- **DoD:**
  - [ ] `argus search "release:2026.2 longevity"` lists matching tests with their
        `build_system_id`s (manual).
  - [x] `argus search "type:group release:2026.2"` lists groups; `--release` flag and
        the `release:` facet both scope results (unit test).
  - [x] Special `Add all...` row is excluded (unit test on the filter helper).
  - [x] Query (free text + facets, quoted values) passed through verbatim (unit test
        asserts query-string build).

### Phase 4 — Write: `create` + `delete`
**Importance: Critical**

- **Input mechanism (decided — Appendix proposals A + B):** both a `--file/-f` JSON
  spec (and `-` for stdin) matching the `PlanTemplate` schema **and** repeatable flags
  (`--test`, `--group`, `--assign entity=user`, `--participant`) plus scalars. Flags
  override / augment matching file fields (scalars override; collections append/merge).
- `PlannerService.CreatePlan(ctx, CreatePlanRequest)` → POST `/planning/plan/create`,
  invalidate the release's plan-list cache.
- `planner create` flags: `--release`, `--name`, `--description`, `--owner`,
  `--participant` (repeatable), `--target-version`, `--view-id`, plus
  tests/groups/assignments per the chosen mechanism, and `--file`. Owner/participant/
  assignee and test/group references accept **names or `build_system_id` only** (no raw
  UUIDs), resolved via the Phase 2 helpers (`ResolveUserID`, `ResolveEntityID`). Merge
  precedence: flags override file fields.
- **Group expansion (always):** any group passed to `create` is exploded to its enabled
  test UUIDs via `ExpandGroup` (Phase 2). The `groups` field sent to the backend is left
  **empty**; expanded tests are merged into `tests`; an assignment on a group **fans
  out** to each expanded test in `assignments`.

#### Create-from-JSON round-trip

- `planner get --plan-id <id> --template` emits an editable create spec instead of the
  raw plan: scalars (`name`, `description`, `target_version`), `release` (name),
  `owner`/`participants` (usernames), `tests` as **group-qualified `group/test`
  names**, and `assignments` keyed by `group/test`. UUIDs from the stored plan are
  back-resolved to names via the source release gridview + `/api/v1/users`. The result
  is release-independent, so retargeting is just editing `release`/`target_version`.
- On `create --file <edited>`, the CLI resolves every `group/test` against the **target
  release's gridview**; tests absent from the new release are **warned about
  individually and omitted**, and the plan is **created anyway** (no `--force`). This
  existence check is fully client-side (no `/copy/check`, no backend change).
- `PlannerService.DeletePlan(ctx, planID, deleteView)` → DELETE
  `/planning/plan/<id>/delete?deleteView=`. `planner delete --plan-id <id>
  [--delete-view] [--yes]` (confirmation prompt unless `--yes`, reading stdin like
  `discussions/root.go:readMessage`).
- **DoD:**
  - [x] `argus planner create --file plan.json` creates a plan; `get` shows it.
  - [x] Owner/participant names resolve to UUIDs; a raw UUID as a name errors (unit
        test).
  - [x] Tests/groups given by name or `build_system_id` resolve to UUIDs; an ambiguous
        bare test name aborts create with a candidate list (unit tests).
  - [x] A group passed to `create` expands to its enabled tests; the plan stores no
        groups; a group assignment fans out to each expanded test (unit test).
  - [x] `get --template` emits group-qualified `group/test` names + usernames (unit
        test on the transform).
  - [x] `create --file` from a template warns about and omits tests missing in the
        target release, but still creates the plan (unit test).
  - [x] `argus planner delete --plan-id <id> --yes` removes it; `--delete-view`
        toggles the query param (unit test asserts URL).
  - [x] Uniqueness-collision API error is surfaced with the backend message.

### Phase 5 — Write: `update` (diff-based)
**Importance: Important**

- `PlannerService.UpdatePlan(ctx, PlanDiffRequest)` → POST `/planning/plan/update`
  with the diff payload; invalidate plan + plan-list caches.
- The CLI computes the diff: GET the current plan, compare against the user's
  requested state, and emit only `*_add`/`*_remove` deltas and changed scalars. For
  simple flag edits (e.g. `--name`) only the scalar is sent. For `--add-test` /
  `--remove-test` style flags (final shape per Phase 4 decision), populate the list
  diffs directly without a full re-send.
- Assignment edits map to `assignee_mapping_set` (entity→user) and
  `assignee_mapping_remove` (entity ids). **Both sides accept names only (no UUIDs):**
  the entity key resolves via `ResolveEntityID` (`build_system_id` / group-qualified /
  unique bare name) and the user value via `ResolveUserID` before the map is built.
- **`--add-group` always expands (Phase 2 `ExpandGroup`):** the group's enabled tests
  are emitted as `tests_add`, no `groups_add` is sent, and any assignment on the group
  fans out to each expanded test in `assignee_mapping_set`.
- **DoD:**
  - [x] `argus planner update --plan-id <id> --name "new"` sends only the `name`
        scalar (unit test asserts the request body has no list/map keys).
  - [x] Adding/removing a test produces `tests_add`/`tests_remove` and leaves other
        fields untouched (manual: `get` before/after; unit test on diff builder).
  - [x] `--add-group` expands to the group's enabled tests in `tests_add` (no
        `groups_add`); a group assignment fans out to each test (unit test).
  - [x] Assignment set/remove maps to `assignee_mapping_set`/`assignee_mapping_remove`
        (unit test). Both the entity key (name/`build_system_id`) and user value
        (username) resolve to UUIDs before the map is sent (unit test).
  - [x] `--add-test` given a name/`build_system_id` resolves to a UUID before building
        the diff; an ambiguous bare name aborts the update with a candidate list
        (unit test).

#### Example invocations (illustrative — final flag names confirmed in Phase 4)

Both styles below edit the same plan and produce the **same** diff payload on the
wire. Names (`--owner`, `--add-participant`, `--assign`) are resolved to UUIDs
client-side; raw UUIDs are not accepted as entity references.

**Flag-based (incremental edits):**

```bash
# Rename, retarget the version, add one test, drop a group, and (re)assign an entity.
argus planner update \
  --plan-id 7f3c1e90-... \
  --name "2026.2 Longevity" \
  --target-version 2026.2.0~rc3 \
  --add-test scylla-2026.2/longevity/longevity-100gb \         # build_system_id (canonical), unique
  --add-test "tier1/longevity-200gb" \            # group-qualified name → scoped lookup
  --remove-group "tier2" \                         # group name → groups_remove (pre-existing group)
  --add-participant alice \                        # plain username → resolved to UUID
  --remove-participant bob \
  --assign scylla-2026.2/longevity/longevity-100gb=alice \      # build_system_id=username → assignee_mapping_set
  --unassign "tier1/longevity-200gb"               # group-qualified name → assignee_mapping_remove
```

The two `--add-test` forms show the supported reference styles: a **canonical
`build_system_id`** (globally unique — the recommended way to name a test
unambiguously) and a **group-qualified `group/test` name** that disambiguates a test
whose bare name repeats across groups. A bare `--add-test longevity-100gb` is accepted
only when it resolves to exactly one test; otherwise the CLI aborts with a candidate
list. Raw UUIDs are not accepted. `--remove-group` targets a group still stored on the
plan (e.g. one created via the web UI); newly *added* groups are always expanded to
tests instead. All references resolve to UUIDs before the diff is built.

The CLI GETs the current plan, resolves every name/`build_system_id` to a UUID,
computes deltas, and POSTs only what changed:

```json
{
  "id": "7f3c1e90-...",
  "name": "2026.2 Longevity",
  "target_version": "2026.2.0~rc3",
  "tests_add": ["c4d0...7a", "b7e2...09"],
  "groups_remove": ["9a1c...44"],
  "participants_add": ["<alice-uuid>"],
  "participants_remove": ["<bob-uuid>"],
  "assignee_mapping_set": {"c4d0...7a": "<alice-uuid>"},
  "assignee_mapping_remove": ["b7e2...09"]
}
```

Note how `scylla-2026.2/longevity/longevity-100gb` (→ `c4d0...7a`), `tier1/longevity-200gb`
(→ `b7e2...09`), `tier2` (→ `9a1c...44`), and `alice` (→ `<alice-uuid>`) are all
resolved to UUIDs in the lists and map keys/values. Fields like `description`,
`owner`, `completed`, `view_id`, and untouched list members are absent — last-edit-wins
per field, and unchanged scalars are never sent.

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
  "name": "2026.2 Longevity",
  "target_version": "2026.2.0~rc3",
  "tests_add": ["scylla-2026.2/longevity/longevity-100gb", "tier1/longevity-200gb"],
  "groups_remove": ["tier2"],
  "participants_add": ["alice"],
  "participants_remove": ["bob"],
  "assignee_mapping_set": {"scylla-2026.2/longevity/longevity-100gb": "alice"},
  "assignee_mapping_remove": ["tier1/longevity-200gb"]
}
```

`--plan-id` on the command line takes precedence over an `id` in the file. When both a
`--file` and overlapping flags are given, flags override the corresponding file keys
(same precedence rule as `create`). Every reference in the file
(`build_system_id`, `group/test`, usernames) is resolved to a UUID the same way as flag
values — the file never contains raw UUIDs.

### Phase 6 — Documentation + hardening
**Importance: Important**

- Update `cli/README.md` with a `planner` section (all commands + examples, the
  `--file` JSON schema, diff-update behavior) and a top-level `search` section
  documenting the query language (free text + `type:`/`group:`/`release:` facets).
- Update the root `AGENTS.md` "Argus CLI (Go)" section to mention planner operations
  and the `search` command.
- Add any missing `_test.go` coverage; run full lint/test/build.
- **DoD:**
  - [ ] `cli/README.md` documents all `planner` subcommands with copy-pasteable
        examples (incl. the `get --template` → `create --file` round-trip).
  - [ ] `AGENTS.md` references planner management.
  - [ ] `go vet ./...`, `gofmt -l` (clean), repo linter, and `go test ./...` all pass.

## 5. Testing Requirements

### Unit tests (Go, `cli/...`)
- **Models** (`internal/models/planner_test.go`): JSON round-trip of `ReleasePlan`,
  `SearchHit`; empty-slice→`[]`; `PlanDiffRequest` omits unset
  optional scalars; `Headers()/Rows()` shape.
- **Service** (`internal/services/planner_test.go`): `httptest.NewServer` emitting the
  standard envelope (pattern from `internal/api/api_test.go`), injected via
  `api.WithHTTPClient`. Cover: list, get, create, update-diff builder
  (scalar-only, list add/remove, assignee set/remove), delete (query-param URL),
  search (special-row filtering, facet query passthrough),
  release/user name resolution (exact match, ambiguous error, no-match error, raw UUID
  rejected), test/group resolution from a single gridview fetch (`build_system_id` hit,
  group-name hit, group-qualified `group/test` hit, bare-name unique hit, bare-name
  ambiguous rejection, one-GET caching), enabled-only group expansion + assignment
  fan-out, `get --template` emission (`group/test` names + usernames), create-from-JSON
  missing-test warn-and-omit, and backend-error surfacing (`ErrorAs *api.APIError`).
- **Command** (`cmd/planner/planner_test.go`): flag parsing/required-flag enforcement,
  confirmation-prompt bypass with `--yes`, `--file`/stdin parsing, flag-over-file
  precedence (pattern from `cmd/discussions/discussions_test.go`).

### Integration tests
- No new ScyllaDB-backed pytest suite required (CLI talks HTTP). If desired, a
  `@pytest.mark.docker_required` smoke could exercise `planner_api.py` end-to-end, but
  it is out of scope for this plan.

### Manual testing (against staging)
- For each command: run happy path + one error path (unknown name, name collision,
  missing release). Verify `--text` vs JSON output and non-zero exit codes on failure.
- Round-trip: `get --template` a plan, edit `release`/`target_version`, `create --file`
  it; confirm tests missing in the new release are warned about and the plan still
  creates. Confirm a plan with groups expands to enabled tests only.
- Update: confirm a single-field edit does not disturb tests/groups/assignees.

## 6. Success Criteria

The plan is complete when all phase DoD items are satisfied, plus:
- All five management commands are reachable under `argus planner`, plus the top-level
  `argus search`, and documented (Goals 1–2, Phase 7 DoD).
- Every entity is referenced by name/`build_system_id` (no raw UUIDs except
  `--plan-id`/`--view-id`) and resolved client-side to UUIDs (Goal 3; Phase 2 & 4 DoD).
- Groups are always expanded to their enabled tests on create/update, with group
  assignments fanned out to each test (Goal 4; Phase 4 & 5 DoD).
- The create-from-JSON round-trip works: `get --template` → edit → `create --file`
  warns about and omits tests missing in the target release but still creates the plan
  (Goal 5; Phase 4 DoD).
- `update` emits a correct `PlanDiffPayload` and never clobbers untouched fields
  (Goal 6; Phase 5 DoD).
- `go vet`, gofmt, linter, and `go test ./...` pass (Goal 8; Phase 6 DoD).

## 7. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| CLI diff builder miscomputes deltas and silently drops tests/groups | Medium | High | Build the diff from an authoritative GET of the current plan; unit-test scalar-only, add, remove, and assignee cases. Never send full list replacements. |
| Name resolution ambiguity (duplicate release/user names) selects the wrong entity | Medium | High | Require exact case-insensitive match; on >1 match, error and list candidates instead of guessing. (No raw-UUID escape hatch by design — see next row.) |
| Ambiguous bare test names resolve to the wrong test (names unique only per group, `web.py:212`) | Medium | High | Reject on >1 match with a candidate list (`build_system_id`+group+UUID); document `build_system_id` as the canonical reference and accept `group/test` qualified form. With UUIDs dropped from input, these two forms are the disambiguators. |
| Create-from-JSON silently drops tests missing in the target release | Medium | Medium | Warn per-missing-entity (by `build_system_id`/`group/test`) before creating; document that the plan is created without them. Users re-check with `get`. |
| Test/group flag ergonomics (open decision) prove awkward | Medium | Medium | Ship `--file` JSON (the `get --template` schema) as the always-available robust path first; treat flag conveniences as additive. Record the decision before Phase 4 coding. |
| Always-expanding groups balloons the test list or surprises users by excluding disabled tests | Low | Medium | Document enabled-only expansion explicitly; `search` discovery shows membership; assignment fan-out is deterministic and unit-tested. |
| Large `/api/v1/users` or `/api/v1/releases` payloads slow every resolving command | Low | Low | Cache both lists with a short TTL (`internal/cache`); resolve locally. |

## Appendix — Test/Group Input Proposals (DECIDED: A + B for Phase 4)

**Decision (Phase 4):** ship **A + B together** — the `--file/-f` JSON spec (baseline)
*and* the repeatable convenience flags. Flags override/augment file fields (scalars
override; `--test`/`--group`/`--participant`/`--assign` append/merge). C falls out for
free (search → flags). The proposals below are retained for context.

The web UI adds tests/groups via interactive search; the CLI needs a non-interactive
equivalent. Proposals (not mutually exclusive):

- **A. `--file/-f` JSON spec (baseline, always supported).** A single JSON object
  matching the `get --template` schema (tests as `group/test`/`build_system_id`
  strings, `assignments` as an entity→username map). Also readable from stdin. Robust
  for nested data and CI-generated specs.
- **B. Repeatable `--test` / `--group` flags (create) and
  `--add-test`/`--remove-test`/`--add-group`/`--remove-group` (update).** Accept
  `build_system_id`/name resolved at plan-build time from the release gridview
  (Phase 2) — **no raw UUIDs**. Bare test names are rejected when ambiguous; use
  `build_system_id` or `group/test` to disambiguate. Groups are always expanded to
  enabled tests. Assignments via repeatable `--assign <entity>=<user>`, where
  `<entity>` (`build_system_id`/`group/test`) and `<user>` (username) are both names.
  Maps cleanly onto the diff payload.
- **C. Two-step `search`→`create`.** Users run `argus search` (Phase 3) to discover
  `build_system_id`s, then pass them via A or B. No extra implementation beyond A/B.

When the decision is made, update Phase 4/5 flag specs and this appendix accordingly.

## Tracking
- Registered under **Client** in `docs/plans/MASTER.md`.
- `progress.json` entry: id `cli-planner-command`, domain `client`, status `draft`,
  `phases_total: 8`, `phases_done: 0`.
</content>
</invoke>
