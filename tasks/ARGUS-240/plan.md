# ARGUS-240 — implementation plan

**Spec:** `tasks/ARGUS-240/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- A router and every service method it feeds change in one task. An
  unguarded `UUID(x)` fails on a `UUID`, so neither half lands alone.
- An ID parameter of a service method behind a route is `UUID`, and the
  method does not call `UUID()` or `isinstance(x, str)` on it. Its other
  callers (tests, other services) pass a `UUID`.
- These keep their conversion, because their input is a string:
  `PlanningService._resolve_plan`, `UserViewService.parse_view_entity_list`,
  `load_user`, `UserService.stop_user_impersonation`, and
  `ClientService.parse_config_values`, which
  `scripts/migration/migration_2026-09-21_backfill_run_config_param_index.py`
  calls with a string (a script that already ran is never edited).
- A response that keys a JSON object by an ID writes `str(id)`.
- An optional query or body ID that the frontend sends as `""` is
  `Annotated[UUID | None, NoneIfEmpty]` (`argus/backend/util/common.py`).
- Tests create and read rows through services or the API, never
  `Model.save()` or `Model.find()` in the test body. Every import sits at
  module top.
- A malformed-ID test asserts
  `response.json()["response"]["exception"] == "RequestValidationError"`.
- The backend suite runs with a local, uncommitted patch of
  `argus/backend/tests/conftest.py`:
  - container names `argus_test_scylla_argus240` and
    `vector-search_test_argus240`
  - Scylla `--listen-address`, `--api-address` and `--prometheus-address`
    `127.0.2.40`, `--vector-store-primary-uri http://127.0.2.40:6080`
  - vector store `VECTOR_STORE_URI=127.0.2.40:6080`,
    `VECTOR_STORE_SCYLLADB_URI=127.0.2.40:9042`
  - `container_ip = "127.0.2.40"`

  Another session's containers use the default names and ports. Stage
  by explicit path, so the patch never enters a commit.

## Task 1 — Log a validation error as a client error

**Files:**
- Modify: `argus/backend/error_handlers.py` (`api_exception_handler`)
- Test: `argus/backend/tests/asgi/test_metrics.py`

**Internals:** the INFO branch of `api_exception_handler` takes
`APIException` and `RequestValidationError`. `record_exception` runs for
the rest only.

- [x] Write the failing test: a request with a malformed UUID path
      parameter to a probe route typed `UUID` returns the envelope. No ERROR record is
      logged by `argus.backend.error_handlers`, and `record_exception` is
      not called.
- [x] Run it and confirm the failure.
- [x] Write the smallest change that passes it.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 2 — testrun_api: clone, run type, comments, assignee

**Files:**
- Modify: `argus/backend/controller/testrun_api.py`
  - `SetAssigneeRequest.assignee`, `CommentRequest.mentions`,
    `JenkinsCloneRequest.target` and `.group`
  - `get_test_type_for_run`, `get_clone_targets`, `get_groups_for_target`,
    `set_testrun_assignee`
- Modify: `argus/backend/service/testrun.py`
  - `get_test_type_for_run`, `post_run_comment`, `update_run_comment`
- Modify: `argus/backend/service/jenkins_service.py`
  - `get_releases_for_clone`, `get_groups_for_release`, `clone_job`
- Test: `argus/backend/tests/testrun_api/test_testrun_api.py`,
  `argus/backend/tests/testrun_api/test_jenkins_clone_api.py`

**Internals:**
- `SetAssigneeRequest.assignee` is
  `Annotated[UUID | None, BeforeValidator(...)]`. The validator maps
  `TestRunService.ASSIGNEE_PLACEHOLDER` to `None`.
- `post_run_comment` builds `mention_ids: set[UUID]` from `mentions` plus
  the IDs of the `@name` matches. It stores the list and notifies each ID.
- `update_run_comment` stores `mentions: list[UUID]`.

- [x] Write the failing tests:
  - submit a comment with a mention ID: the comment holds it, and the
    mentioned user gets a notification
  - update a comment with mention IDs
  - `GET /jenkins/clone/groups?targetId=<bad>` returns
    `RequestValidationError`
  - clone/create with real release and group IDs (replace `"release-1"` and
    `"group-1"` in `test_testrun_api.py`)
  - assignee set with the sentinel clears the assignee
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 3 — client_api and ClientService

**Files:**
- Modify: `argus/backend/controller/client_api.py`
  - `run_id: UUID` on `get_run_info`, `get_run`, `run_heartbeat`,
    `run_get_status`, `run_set_status`, `run_update_product_version`,
    `run_submit_logs`, `submit_run_config`, `get_all_run_configs`,
    `run_finalize`, `submit_results`
  - `submit_pytest_result` takes `payload: PytestSubmitData`
- Modify: `argus/backend/service/client_service.py`
  - `get_run`, `heartbeat`, `get_run_status`, `update_run_status`,
    `submit_product_version`, `submit_logs`, `finish_run`,
    `submit_results`, `get_run_info`, `get_config_store`,
    `get_all_configs`, `submit_config`, `submit_pytest_result`
- Modify: `argus/backend/models/pytest.py` (`PytestSubmitData`, the spec's
  shape)
- Modify: `argus/backend/service/results_service.py` (`BestResult.run_id`
  is `UUID`)
- Test, updated to pass `UUID` to direct service calls:
  - `argus/backend/tests/client_api/`, `argus/backend/tests/client_service/`
  - `argus/backend/tests/results_service/`,
    `argus/backend/tests/pytest_service/`
  - `argus/backend/tests/run_cost/test_finalize_recompute.py`,
    `argus/backend/tests/test_stats_snapshot.py`

- [x] Write the failing tests:
  - `POST /client/testrun/sct/<bad>/heartbeat` returns
    `RequestValidationError`
  - pytest result submit with `status: "internal-error"` and
    `message: null` stores the row
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 4 — SCT plugin

**Files:**
- Modify: `argus/backend/plugins/sct/controller.py` (`run_id: UUID` on
  every route, `SimilarRunsInfoRequest.run_ids: list[UUID]`)
- Modify: `argus/backend/plugins/sct/service.py` (every method behind
  those routes; `submit_event` takes `UUID`; `get_similar_runs_info` keys
  its result by `str(run_id)` and dedups on like types;
  `submit_performance_results` reads the run metric with `getattr`)
- Modify: `argus/backend/plugins/sct/testrun.py` (`get_stress_commands`)
- Test:
  - `argus/backend/tests/sct_api/test_sct_api.py`
  - `argus/backend/tests/sct_events/test_sct_events.py`,
    `argus/backend/tests/sct_events/test_event_embedding_integration.py`
    (pass `UUID` to `submit_event`)

- [x] Write the failing tests:
  - Gemini submit with `gemini_status: "FAILED"` sets the run FAILED and
    writes the status event
  - performance submit that finds a regression writes its event
  - `similar_runs_info` keys its response by the string IDs
  - `GET /client/sct/<bad>/events/get` returns `RequestValidationError`
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 5 — admin_api, ReleaseManagerService, UserService, tunnel IDs

**Files:**
- Modify: `argus/backend/controller/admin_api.py`
  - the release, group and test request models; `new_group_id` is
    `Annotated[UUID | None, NoneIfEmpty] = None`
  - `delete_user`, `toggle_admin` path IDs
  - `get_proxy_tunnel_config` `tunnel_id`
- Modify: `argus/backend/service/release_manager.py`
  - `create_group`, `create_test`, `update_group`, `update_test`,
    `delete_group`, `delete_test`, `edit_release`, `delete_release`,
    `set_release_*`, `batch_move_tests`, `toggle_*`
  - `ReleaseEditPayload.id`
- Modify: `argus/backend/service/user.py` (`delete_user`, `toggle_admin`)
- Modify: `argus/backend/controller/ssh_api.py` (`get_user_keys`
  `tunnel_id`)
- Modify: `argus/backend/service/tunnel_service.py` (`list_keys`,
  `get_proxy_tunnel_config`, and the guards in `delete_key`,
  `delete_proxy_tunnel_config`, `set_proxy_tunnel_config_active`)
- Test:
  - `argus/backend/tests/admin_api/`, `argus/backend/tests/tunnel/`
  - the fixtures and tests that call `create_group`, `create_test` or
    `delete_release` with `str(...)`: `argus/backend/tests/conftest.py`,
    `test_assignee.py`, `test_stats_snapshot.py`,
    `api/test_release_api.py`, `driver_matrix_api/`,
    `integration/conftest.py`, `planner_api/`, `testrun_api/`,
    `view_api/`

- [x] Write the failing tests:
  - group delete with `delete_tests: false` and `new_group_id: ""` is
    rejected by the service, which names the missing target group
  - `POST /admin/api/v1/user/<bad>/delete` returns
    `RequestValidationError`
  - `GET /client/ssh/tunnel/keys?tunnel_id=` lists the keys
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 6 — Planner

**Files:**
- Modify: `argus/backend/controller/planner_api.py`
  - `search_tests` `releaseId` (NoneIfEmpty)
  - `explode_group`, `get_plans_for_release` path IDs
  - `create_plan`, `update_plan` take the payload dataclasses as the body
  - `trigger_jobs_for_plans` takes `PlanTriggerPayload` as the body
  - `ChangeOwnerRequest.newOwner`
- Modify: `argus/backend/service/planner_service.py`
  - `CreatePlanPayload`, `TempPlanPayload`, `PlanDiffPayload`,
    `CopyPlanPayload`, `PlanTriggerPayload` as in the spec;
    `TempPlanPayload.ends_at` and `.options` accept null and the stored
    JSON string
  - `create_plan`, `update_plan` (`view_id` compare on `UUID`),
    `copy_plan`, `change_plan_owner`, `get_plans_for_release`,
    `get_assignments_for_*`, `_generate_plan_key`
- Modify: `argus/backend/service/test_lookup.py` (`test_lookup`,
  `explode_group`)
- Test: `argus/backend/tests/planner_api/test_planner_api.py`,
  `argus/backend/tests/planner_api/test_planner_options.py` (build the
  payload dataclasses with `UUID`)

- [x] Write the failing tests:
  - plan update with a new `owner` saves it
  - plan copy with `replacements` keeps the mapped test and group
  - search with a bare `releaseId=` returns results
  - plan update with `view_id` relinks the view
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 7 — Views and widgets

**Files:**
- Modify: `argus/backend/controller/view_api.py`
  - `UpdateViewRequest`: `viewId: UUID`, `updateData: ViewUpdateRequest`
  - `DeleteViewRequest.viewId`
  - `view_stats` `viewId`, and the `view_id` paths
- Modify: `argus/backend/service/views.py`
  - `ViewUpdateRequest` as in the spec
  - `update_view`, `delete_view`, `get_view`, `resolve_view_tests`,
    `get_versions_for_view`, `get_images_for_view`,
    `resolve_view_for_edit`, `get_pytest_view_results`
- Modify: `argus/backend/service/stats.py` (`ViewStatsCollector.__init__`)
- Modify: `argus/backend/controller/views_widgets/pytest.py`,
  `argus/backend/controller/views_widgets/graphed_stats.py` (`run_ids:
  list[UUID]`), `argus/backend/controller/views_widgets/summary.py` (typed
  body, `str` response keys)
- Modify: `argus/backend/service/views_widgets/graphed_stats.py`
  (`get_runs_details`, `str(run_id)` keys in both branches)
- Modify: `argus/backend/service/views_widgets/highlights.py` (drop
  `_coerce_uuid` and the `__post_init__` methods that call it)
- Test:
  - `argus/backend/tests/view_api/`, `argus/backend/tests/widgets/`,
    `argus/backend/tests/view_widgets/`
  - `argus/backend/tests/issues/test_jira_unification.py` (pass `UUID` to
    `get_runs_details`)

**Internals:** `VersionedRun(BaseModel)` with `run_id: UUID` in
`summary.py`.

- [x] Write the failing tests:
  - `runs_details` with a run that fails to load returns its error entry
    under the string ID
  - `/views/update` with `plan_id: "<bad>"` returns
    `RequestValidationError`
  - `summary/runs_results` with a malformed key returns
    `RequestValidationError`
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 8 — api, notifications, and the guards behind UUID routes

**Files:**
- Modify: `argus/backend/controller/api.py`
  (`release_schedules_comment_update` takes
  `ScheduleCommentUpdateRequest`)
- Modify: `argus/backend/service/argus_service.py`
  - `update_schedule_comment` takes the IDs and the comment
  - drop the guards in `get_planner_data`,
    `get_distinct_release_versions`, `get_distinct_release_images`,
    `get_groups_assignees`, `get_tests_assignees`
- Modify: `argus/backend/controller/notification_api.py` (`afterId`
  NoneIfEmpty)
- Modify: `argus/backend/service/notification_manager.py` (drop the guards
  in `get_notificaton`, `read_notification`, `get_notifications`)
- Modify: `argus/backend/service/issue_service.py` (drop the guards in
  `get`, `delete`, `submit`, `submit_for_sct_event`)
- Modify: `argus/backend/service/testrun.py` (drop the guards in `get_run`,
  `get_pytest_release_results`, `get_pytest_run_results`,
  `resolve_run_build_id_and_number_multiple`)
- Modify: `argus/backend/plugins/driver_matrix_tests/service.py` and
  `argus/backend/plugins/driver_matrix_tests/model.py` (drop the guards
  behind the UUID routes)
- Modify: `argus/backend/service/run_cost_service.py` (`_run_id` goes)
- Test:
  - `argus/backend/tests/api/test_release_api.py`,
    `argus/backend/tests/notification_api/`
  - the direct callers that pass a string: `get_run` (about 30 sites built
    on `run_req.run_id`), `IssueService` in `issues/`, `sct_api/`
- [x] Write the failing tests:
  - `GET /notifications/summary?afterId=` returns the first page
  - schedule comment update with a malformed `testId` returns
    `RequestValidationError`
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 9 — Smoke on dev data

- [ ] An authenticated TestClient over `create_app()` with the dev config
      calls one retyped route per router, with a valid ID, a malformed ID
      and, where it applies, an empty optional ID.
- [ ] `docker ps` after the suite shows the other session's containers
      untouched.
