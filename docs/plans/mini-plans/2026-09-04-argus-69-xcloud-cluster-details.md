# ARGUS-69: Surface xCloud Cluster Details, Stop Faking Instance Type / Node Amount

**Jira**: [ARGUS-69](https://issues.scylladb.com/browse/ARGUS-69)
**Status**: plan-only (awaiting SCT-side field confirmation before Phase 1 implementation)

## Problem

xCloud test runs use a declarative scaling policy instead of a fixed
instance-type/node-count topology. Today the SCT run Details page shows
Instance Type and Node Amount for every run, including xCloud runs, but for
xCloud those values are fabricated: they fall through to unknown-backend
sentinels (`"UNKNOWN"` / `-1`) rather than reflecting reality. Meanwhile the
three facts that *do* describe an xCloud run — cluster type, network type,
deployment type — are not modelled or displayed anywhere on Details, even
though they are almost certainly already present in the raw `sct_config`
blob every run submits.

Goal: surface cluster type / network type / deployment type on Details, and
hide Instance Type / Node Amount when SCT has not supplied real values for
them (instead of showing fabricated ones).

## Findings

- `argus/backend/models/run_config.py:8-14` — the class the ticket calls
  `RuntimeConfiguration` is actually `RunConfiguration`. Fields: `run_id: UUID`
  (partition key), `name: str` (clustering key), `content: str`, table
  `run_configuration`. It does **not** contain cluster type / network type /
  deployment type as fields — it is a generic blob store: one row per
  (run, config name) holding raw config text. The ticket's hypothesis is only
  half true: the three new values are probably already inside the stored
  `sct_config` blob, but they are not modelled fields and nothing on the
  Details page reads them today.

- `argus/backend/service/client_service.py:247-308` +
  `argus/backend/controller/client_api.py:117-134` — this is the "send
  arbitrary configs to Argus, visible in a separate tab" feature referenced
  in the ticket. `POST /api/v1/client/{run_id}/config/submit` (base64 body)
  stores into `RunConfiguration` and flattens every scalar leaf into
  `RunConfigParam`; `GET /api/v1/client/{run_id}/config/all` returns them.
  Frontend: `frontend/TestRun/SCT/SctConfig.svelte:37-57` under the "SCT
  Runtime" tab (`frontend/TestRun/TestRun.svelte:401-406`), rendered by
  `frontend/TestRun/RuntimeConfig.svelte:57-79`, whose `walkConfig` already
  recurses into nested objects/arrays. Consequence: a nested xCloud scaling
  policy submitted inside `sct_config` is already fully browsable today, with
  no Argus change. Argus therefore needs no new "scaling policy" model.

- Instance Type / Node Amount on Details come from
  `frontend/TestRun/TestRunInfo.svelte:228-235` reading
  `test_run.cloud_setup.db_node.instance_type` / `.node_amount`. That's the
  `CloudNodesInfo` UDT (`argus/backend/plugins/sct/udt.py:45-52`) nested in
  `CloudSetupDetails` (`udt.py:55-62`), stored on column
  `SCTTestRun.cloud_setup` (`argus/backend/plugins/sct/testrun.py:169`),
  populated once at run submission by
  `ResourceSetup.get_resource_setup(...)` (`testrun.py:337-338` →
  `argus/backend/plugins/sct/resource_setup.py:224-226`).

- Why wrong for xCloud: `resource_setup.py:209-222` `BACKEND_MAP` has no
  xCloud entry, so `get_resource_setup` falls through to
  `_prepare_unknown_resource_setup` (`resource_setup.py:124-141`), which
  writes literal sentinels `instance_type="UNKNOWN"` and `node_amount=-1`.
  Even if mapped to AWS, `sct_config.get("instance_type_db")` /
  `_resolve_node_count(config.get("n_db_nodes"))` (`resource_setup.py:7-40`)
  have no meaning under a declarative scaling policy. The response path
  needs no change: `SCTTestRun.get_run_response` returns
  `run.model_dump()` (`testrun.py:490-502`), so any new UDT field is
  auto-exposed via `GET /api/v1/run/{run_type}/{run_id}`.

## Approach

### Phase 1 — Backend / model (single PR, ~80 lines)

1. `argus/backend/plugins/sct/udt.py:55-62` — add
   `cluster_type: Optional[str] = None`, `network_type: Optional[str] = None`,
   `deployment_type: Optional[str] = None` to `CloudSetupDetails`, keeping
   `__type_name__ = "cloudsetupdetails"` unversioned. Same shape of change as
   commit `49b7845` ("Add instance_type to CloudInstanceDetails") —
   established precedent for additive UDT fields.

2. `resource_setup.py:208-226` — add a module-level key map constant (e.g.
   `CLUSTER_DETAIL_CONFIG_KEYS = {"cluster_type": ..., "network_type": ...,
   "deployment_type": ...}`) applied once inside
   `ResourceSetup.get_resource_setup` after the per-backend preparer returns,
   so every backend gets these fields populated when present in
   `sct_config`, `None` otherwise.

3. `resource_setup.py:183-226` — add
   `_prepare_xcloud_resource_setup(sct_config)`, register the xCloud backend
   string in `BACKEND_MAP`. Composes `_prepare_aws_resource_setup` (same
   "compose base preparer, then override" pattern as
   `_prepare_k8s_eks_resource_setup` / `_prepare_k8s_gke_resource_setup`),
   then sets `cloud_setup.db_node.instance_type = None` and `.node_amount =
   None` unless SCT supplied resolved values — replacing the `"UNKNOWN"` /
   `-1` sentinels with null ("not applicable").

4. No `plugin.py` change needed: `CloudSetupDetails` is already in
   `all_types`, so `cli.py sync-models` → `sync_type()` issues
   `ALTER TYPE ... ADD` on deploy. There is no alembic/migrations package in
   this repo; `scripts/migration/migration_YYYY-MM-DD.py` files are for data
   backfills only. This is additive schema only — no migration script
   required; old rows deserialize the new fields as `None`.

5. No API/controller/client changes needed.

### Phase 2 — Frontend (single PR, ~60 lines)

1. `frontend/TestRun/TestRun.svelte` — extend the `CloudNodesInfo` interface
   (`instance_type` / `node_amount` nullable), add `cluster_type` /
   `network_type` / `deployment_type` to the `cloud_setup` shape in
   `SCTTestRun`.

2. `frontend/TestRun/TestRunInfo.svelte:228-235` — wrap the "Instance type" /
   "Node amount" `<li>`s in `{#if ...}` guards, omitting them when
   null/undefined/empty (replacing the current unconditional `?? "Unknown"`).

3. `frontend/TestRun/TestRunInfo.svelte:141-236` — add three `{#if}`-guarded
   `<li>` rows for Cluster Type, Network Type, Deployment Type, following the
   existing conditional-row pattern already used for the test_method row and
   package rows. Svelte 5 runes only, no new component/fetch.

### Reuse

`ResourceSetup.get_resource_setup`; the k8s "compose base then override"
pattern; `CloudSetupDetails` + commit `49b7845` precedent;
`sync-models`/`sync_core_tables` schema mechanism; `get_run_response` /
`model_dump`; the existing `{#if}` row pattern in `TestRunInfo.svelte`; the
already-shipped "SCT Runtime" config tab; the `sct_run_id` test fixture.

## Standards Deviations

Declared explicitly, not papered over:

1. `standards/backend/migrations.md` wants reversible migrations; a CQL
   `ALTER TYPE ... ADD` on a UDT is one-way. Accepted, consistent with
   precedent commit `49b7845`.
2. `standards/backend/models.md` describes `cassandra.cqlengine.Model`; the
   SCT plugin has already moved to `coodie` (commit `a34e6e1`) — follow the
   code, not the doc's literal ORM reference.
3. `standards/global/coding-style.md` says "no backward compatibility unless
   required" — here it **is** required: existing non-xCloud runs must render
   unchanged (instance type / node amount still shown as today).
4. Per `docs/plans/INSTRUCTIONS.md` this is a mini-plan, filed standalone
   under `docs/plans/mini-plans/`, not registered in `MASTER.md` or
   `progress.json`.
5. Commit scoping per `standards/global/commits-and-prs.md`: Conventional
   Commits with mandatory scope (`feature(plugins/sct): ...`,
   `feature(frontend): ...`), matching the `49b7845` style.

## Scope Boundary

**Out of scope:**

- The `scylla-cluster-tests` repo itself (SCT must be updated separately to
  send the three new `sct_config` keys — see Open Questions).
- `IssueTemplate.svelte` issue text.
- Go CLI tabular view (`cli/internal/models/runs.go`).
- Email templates.
- Any new "scaling policy" model/table/UDT/evaluator.
- Any new API endpoint.
- Any `RunConfiguration` / `RunConfigParam` changes.
- Any data-migration script (schema change is purely additive; new columns
  default to `None` on old rows).

**Rejected alternative:** reading the three values live from
`GET /api/v1/client/{run_id}/config/all` instead of a schema change —
rejected as more complex and less robust than three nullable UDT fields
populated once at submission time.

## Test Strategy

- New unit tests in `argus/backend/tests/sct_api/test_resource_setup.py`:
  - xCloud backend is not routed to `_prepare_unknown_resource_setup`.
  - `instance_type` / `node_amount` are left `None` for xCloud.
  - The three new fields are populated from `sct_config` when present.
  - Backward-compat test proving a plain AWS config is unaffected.
- One Docker-backed integration test in `test_sct_api.py` proving the UDT
  round-trips through ScyllaDB (this is what actually catches a failed
  `ALTER TYPE`).
- Co-located vitest component tests for `TestRunInfo.svelte`: render the new
  rows when present; omit instance type/node amount when null. Downgrade to
  manual verification if jsdom setup proves disproportionate, and record that
  decision explicitly in the eventual PR.

**Commands:**

```
uv run pytest argus/backend/tests/sct_api
uv run ruff check
yarn vitest run frontend/TestRun
```

## Open Questions

- Exact xCloud `cluster_backend` string SCT will use is unknown (the repo
  only knows `aws`, `aws-siren`, `azure`, `oci`, `gce`, `gce-siren`,
  `k8s-eks`, `k8s-gke`, `k8s-gce-minikube`, `baremetal`, `docker`); zero hits
  for "xcloud"/"byoa" anywhere in this repo. Must be confirmed against SCT
  before Phase 1 merges.
- The ticket lists "xcloud" as one *cluster type* value alongside free
  trial/sandbox/standard, suggesting these three fields may apply broadly to
  Scylla Cloud (siren) runs, not just a distinct xcloud backend. This plan
  handles the fields generically; only the `BACKEND_MAP` entry depends on the
  answer.
- Exact `sct_config` key names for the three new fields are assumed
  (`cluster_type`, `network_type`, `deployment_type`) and unverified against
  SCT.
- Whether SCT will ever send resolved `instance_type`/`node_amount` for
  xCloud at all, vs. only resolvable mid-run via a provider API — if only
  resolvable mid-run, a follow-up ticket is needed for a post-submission
  update path; not planned here.
- Whether legacy runs with existing `"UNKNOWN"`/`-1` sentinel values should
  also be hidden by the new frontend guard, or only actual
  null/undefined/empty — this plan defaults to hiding only
  null/undefined/empty; confirm with requester.
- `coodie`'s exact `ALTER TYPE ADD` behavior on `sync_type()` is inferred
  from precedent commit `49b7845`, not directly verified; the planned
  Docker-backed integration test is the actual proof — if `sync_type()`
  doesn't emit `ALTER TYPE`, fall back to a raw migration script.
